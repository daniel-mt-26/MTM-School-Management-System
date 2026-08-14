"""Authoritative finance workflows kept outside model save hooks.

These functions deliberately make a charge/payment and its audit records in one
database transaction. Future communication can consume their returned objects
without being coupled to financial persistence.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Fee, FinancialLedgerEntry, Payment, Receipt, RecurringFeeTemplate, Student, StudentFeeAssignment


def assignment_totals(assignment):
    paid = assignment.payments.filter(is_reversed=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return assignment.amount_owed, paid, assignment.amount_owed - paid


def student_totals(student):
    charges = student.fee_assignments.aggregate(total=Sum("amount_owed"))["total"] or Decimal("0.00")
    payments = Payment.objects.filter(student_fee_assignment__student=student, is_reversed=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return charges, payments, charges - payments


@transaction.atomic
def assign_fee(*, student, fee, amount_owed, assigned_on):
    assignment, created = StudentFeeAssignment.objects.get_or_create(
        student=student,
        fee=fee,
        defaults={"amount_owed": amount_owed, "currency": fee.currency, "assigned_on": assigned_on},
    )
    if created:
        assignment.full_clean()
        assignment.save()
        FinancialLedgerEntry.objects.create(
            student=student,
            entry_type=FinancialLedgerEntry.EntryType.CHARGE,
            amount=assignment.amount_owed,
            currency=assignment.currency,
            occurred_at=timezone.now(),
            description=f"Fee assigned: {fee.name}",
            fee_assignment=assignment,
        )
    return assignment, created


@transaction.atomic
def record_payment(*, student_fee_assignment, amount, paid_at, method, reference="", notes="", recorded_by):
    # Lock the obligation before calculating the remaining amount so concurrent
    # administrators cannot both spend the same outstanding balance.
    assignment = StudentFeeAssignment.objects.select_for_update().select_related("student", "fee").get(pk=student_fee_assignment.pk)
    _, _, outstanding = assignment_totals(assignment)
    if amount > outstanding:
        raise ValidationError({"amount": f"Payment cannot exceed the outstanding amount of {outstanding}."})
    payment = Payment.objects.create(
        student_fee_assignment=assignment,
        amount=amount,
        currency=assignment.currency,
        paid_at=paid_at,
        method=method,
        reference=reference,
        notes=notes,
        recorded_by=recorded_by,
    )
    FinancialLedgerEntry.objects.create(
        student=assignment.student,
        entry_type=FinancialLedgerEntry.EntryType.PAYMENT,
        amount=amount,
        currency=assignment.currency,
        occurred_at=paid_at,
        description=f"Payment for {assignment.fee.name}",
        fee_assignment=assignment,
        payment=payment,
    )
    receipt = Receipt.objects.create(
        receipt_number=f"RCPT-{payment.pk:08d}",
        payment=payment,
        issued_at=timezone.now(),
    )
    return payment, receipt


@transaction.atomic
def reverse_payment(*, payment_id, reason, reversed_by):
    payment = Payment.objects.select_for_update().select_related("student_fee_assignment__student").get(pk=payment_id)
    if payment.is_reversed:
        raise ValidationError({"detail": "This payment has already been reversed."})
    if not reason.strip():
        raise ValidationError({"reason": "A reversal reason is required."})
    payment.is_reversed = True
    payment.reversed_at = timezone.now()
    payment.reversed_by = reversed_by
    payment.reversal_reason = reason.strip()
    payment.save(update_fields=["is_reversed", "reversed_at", "reversed_by", "reversal_reason"])
    receipt = Receipt.objects.select_for_update().get(payment=payment)
    receipt.is_reversed = True
    receipt.save(update_fields=["is_reversed"])
    FinancialLedgerEntry.objects.create(
        student=payment.student_fee_assignment.student,
        entry_type=FinancialLedgerEntry.EntryType.CHARGE,
        amount=payment.amount,
        currency=payment.currency,
        occurred_at=payment.reversed_at,
        description=f"Payment reversal: {reason.strip()}",
        fee_assignment=payment.student_fee_assignment,
    )
    return payment


def month_start(value):
    return value.replace(day=1)


@transaction.atomic
def generate_recurring_charges(*, school, for_month):
    charge_month = month_start(for_month)
    templates = RecurringFeeTemplate.objects.select_for_update().filter(school=school, is_active=True, start_month__lte=charge_month).filter(Q(end_month__isnull=True) | Q(end_month__gte=charge_month))
    fees_created = assignments_created = already_generated = 0
    for template in templates:
        fee, created = Fee.objects.get_or_create(
            recurring_template=template,
            charge_month=charge_month,
            defaults={"school": school, "academic_year": template.academic_year, "term": template.term, "school_class": template.school_class, "name": f"{template.name} ({charge_month:%Y-%m})", "amount": template.amount, "currency": template.currency, "due_date": None, "is_active": True},
        )
        fees_created += int(created)
        already_generated += int(not created)
        students = Student.objects.filter(school=school, is_active=True)
        if template.school_class_id:
            students = students.filter(school_class=template.school_class)
        for student in students:
            _, assignment_created = assign_fee(student=student, fee=fee, amount_owed=fee.amount, assigned_on=charge_month)
            assignments_created += int(assignment_created)
    return {"fees_created": fees_created, "assignments_created": assignments_created, "already_generated": already_generated}
