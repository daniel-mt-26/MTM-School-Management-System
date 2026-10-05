"""Authoritative finance workflows kept outside model save hooks.

These functions deliberately make a charge/payment and its audit records in one
database transaction. Future communication can consume their returned objects
without being coupled to financial persistence.
"""

from decimal import Decimal
from calendar import monthrange
from datetime import date
from hashlib import sha256
import json

from django.db import transaction, IntegrityError
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Fee, FinancialLedgerEntry, Payment, Receipt, RecurringFeeTemplate, Student, StudentFeeAssignment, StudentEnrollment


def calendar_month(start, offset):
    """Add months anchored to the original day, clamping at month end."""
    year, month = divmod(start.year * 12 + start.month - 1 + offset, 12)
    return date(year, month + 1, min(start.day, monthrange(year, month + 1)[1]))


def billing_periods(template):
    start, end = template.term.start_date, template.term.end_date
    if end <= start:
        raise ValidationError("Term end must follow its start.")
    if template.billing_method != "MONTHLY":
        return [(start, end)]
    # [start, end): an exact anniversary adds no extra period.
    result = []
    while calendar_month(start, len(result)) < end:
        result.append((calendar_month(start, len(result)), min(calendar_month(start, len(result) + 1), end)))
    return result


def eligible_students(template, start, end):
    enrollments = StudentEnrollment.objects.filter(
        student__school=template.school, school_class__school=template.school,
        academic_year=template.academic_year, enrolled_on__lt=end,
    ).filter(Q(left_on__isnull=True) | Q(left_on__gte=start))
    if template.school_class_id:
        enrollments = enrollments.filter(school_class_id=template.school_class_id)
    if template.student_id:
        enrollments = enrollments.filter(student_id=template.student_id)
    return list(Student.objects.filter(pk__in=enrollments.values("student_id")).order_by("pk"))


def fee_plan(template):
    template.amount = Decimal(template.amount).quantize(Decimal("0.01"))
    if template.billing_method == "LEGACY":
        raise ValidationError("This legacy template retains calendar-month generation. Create a term-based structure for the new workflow.")
    if not template.is_active:
        raise ValidationError("Activate this structure before generating charges.")
    if template.generated_fees.exists() and (template.start_month != template.term.start_date or template.end_month != template.term.end_date):
        raise ValidationError("Term dates changed after charges were generated. Preserve this structure and review the existing charges before creating a replacement.")
    periods = billing_periods(template)
    rows, public, students = [], [], set()
    for sequence, (start, end) in enumerate(periods, 1):
        eligible = eligible_students(template, start, end)
        existing = set(StudentFeeAssignment.objects.filter(fee__recurring_template=template, fee__period_sequence=sequence).values_list("student_id", flat=True))
        ids = [s.pk for s in eligible]
        students.update(ids)
        rows.append((start, eligible, existing))
        public.append({"sequence": sequence, "start": str(start), "end": str(end), "student_ids": ids, "existing_ids": sorted(existing), "charges_to_create": len(set(ids) - existing)})
    count = sum(p["charges_to_create"] for p in public)
    candidates = Student.objects.filter(school=template.school)
    if template.student_id:
        candidates = candidates.filter(pk=template.student_id)
    missing = list(candidates.exclude(enrollments__academic_year=template.academic_year).values("id", "admission_number", "first_name", "last_name"))
    data = {"structure": template.pk, "name": template.name, "academic_year": template.academic_year.name, "term": template.term.name,
            "billing_method": template.billing_method, "currency": template.currency, "amount": str(template.amount),
            "term_start": str(template.term.start_date), "term_end": str(template.term.end_date),
            "charges_per_student": len(periods), "amount_per_student": str(template.amount * len(periods)),
            "eligible_students": len(students), "total_charges": count, "total_value": str(template.amount * count),
            "periods": public, "missing_enrollments": missing}
    data["preview_token"] = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return data, rows


@transaction.atomic
def generate_fee_structure(*, template, preview_token):
    template = RecurringFeeTemplate.objects.select_for_update().get(pk=template.pk)
    data, rows = fee_plan(template)
    if preview_token != data["preview_token"]:
        raise ValidationError({"preview_token": "The fee, enrollment roster or existing charges changed. Preview again before confirming."})
    created_count = 0
    for sequence, (start, students, existing) in enumerate(rows, 1):
        fee, _ = Fee.objects.get_or_create(recurring_template=template, period_sequence=sequence, defaults={"charge_month": start,
            "school": template.school, "academic_year": template.academic_year, "term": template.term,
            "school_class": template.school_class, "name": f"{template.name} / Period {sequence}",
            "amount": template.amount, "currency": template.currency})
        for student in students:
            _, created = assign_fee(student=student, fee=fee, amount_owed=fee.amount, assigned_on=start)
            created_count += int(created)
    return {**data, "assignments_created": created_count}


def assignment_totals(assignment):
    paid = assignment.payments.filter(is_reversed=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return assignment.amount_owed, paid, assignment.amount_owed - paid


def student_totals(student):
    charges = student.fee_assignments.aggregate(total=Sum("amount_owed"))["total"] or Decimal("0.00")
    payments = Payment.objects.filter(student_fee_assignment__student=student, is_reversed=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return charges, payments, charges - payments


@transaction.atomic
def assign_fee(*, student, fee, amount_owed, assigned_on):
    if student.school_id != fee.school_id:
        raise ValidationError("Student and fee must belong to the same school.")
    if fee.recurring_template_id and fee.recurring_template.billing_method != "LEGACY":
        template = fee.recurring_template
        periods = billing_periods(template)
        if not fee.period_sequence or fee.period_sequence > len(periods):
            raise ValidationError("This charge has no valid billing period.")
        start, end = periods[fee.period_sequence - 1]
        if student.pk not in [s.pk for s in eligible_students(template, start, end)]:
            raise ValidationError("This learner is not enrolled in the fee's scope during this billing period.")
        if Decimal(amount_owed) != fee.amount:
            raise ValidationError("Generated charges must use the configured fee amount.")
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
def record_payment(*, student_fee_assignment, amount, paid_at, method, reference="", notes="", recorded_by, receipt_number=""):
    # Lock the obligation before calculating the remaining amount so concurrent
    # administrators cannot both spend the same outstanding balance.
    assignment = StudentFeeAssignment.objects.select_for_update().select_related("student", "fee").get(pk=student_fee_assignment.pk)
    _, _, outstanding = assignment_totals(assignment)
    if amount > outstanding:
        raise ValidationError({"amount": f"Payment cannot exceed the outstanding amount of {outstanding}."})
    if receipt_number and Receipt.objects.filter(receipt_number=receipt_number).exists():
        raise ValidationError({"receipt_number": "This receipt number is already in use."})
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
    try:
        with transaction.atomic():
            receipt = Receipt.objects.create(
                receipt_number=receipt_number or f"RCPT-{payment.pk:08d}",
                payment=payment,
                issued_at=timezone.now(),
            )
    except IntegrityError as exc:
        raise ValidationError({"receipt_number": "Receipt number is already in use. Enter a unique number."}) from exc
    # This creates only local durable in-app/outbox records. It deliberately
    # performs no provider or n8n HTTP call inside the financial transaction.
    from .communications import create_payment_receipt_messages
    create_payment_receipt_messages(payment, receipt)
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


def recurring_preview(*, school, for_month):
    charge_month = month_start(for_month)
    templates = RecurringFeeTemplate.objects.filter(school=school, billing_method="LEGACY", is_active=True, start_month__lte=charge_month).filter(Q(end_month__isnull=True) | Q(end_month__gte=charge_month))
    rows = []
    for template in templates.order_by("pk"):
        ids = [s.pk for s in eligible_students(template, charge_month, calendar_month(charge_month, 1))]
        existing = list(StudentFeeAssignment.objects.filter(fee__recurring_template=template, fee__charge_month=charge_month).order_by("student_id").values_list("student_id", flat=True))
        rows.append({"id": template.pk, "name": template.name, "amount": str(template.amount), "currency": template.currency, "students": ids, "existing": existing, "new_charges": len(set(ids) - set(existing))})
    result = {"month": str(charge_month), "fees": rows, "total_charges": sum(r["new_charges"] for r in rows), "total_value": str(sum((Decimal(r["amount"]) * r["new_charges"] for r in rows), Decimal("0.00")))}
    result["preview_token"] = sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


@transaction.atomic
def generate_recurring_charges(*, school, for_month, preview_token=None):
    charge_month = month_start(for_month)
    templates = RecurringFeeTemplate.objects.select_for_update().filter(school=school, billing_method="LEGACY", is_active=True, start_month__lte=charge_month).filter(Q(end_month__isnull=True) | Q(end_month__gte=charge_month))
    templates = list(templates)
    if preview_token is not None and preview_token != recurring_preview(school=school, for_month=for_month)["preview_token"]:
        raise ValidationError("Charges changed. Preview again before generating.")
    fees_created = assignments_created = already_generated = 0
    for template in templates:
        fee, created = Fee.objects.get_or_create(
            recurring_template=template,
            charge_month=charge_month,
            defaults={"school": school, "academic_year": template.academic_year, "term": template.term, "school_class": template.school_class, "name": f"{template.name} ({charge_month:%Y-%m})", "amount": template.amount, "currency": template.currency, "due_date": None, "is_active": True},
        )
        fees_created += int(created)
        already_generated += int(not created)
        students = eligible_students(template, charge_month, calendar_month(charge_month, 1))
        for student in students:
            _, assignment_created = assign_fee(student=student, fee=fee, amount_owed=fee.amount, assigned_on=charge_month)
            assignments_created += int(assignment_created)
    return {"fees_created": fees_created, "assignments_created": assignments_created, "already_generated": already_generated}
