"""Read-only projections of obligations and their existing payment allocations."""
from decimal import Decimal
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import StudentFeeAssignment, Payment, FinancialLedgerEntry, SchoolClass, Student, StudentEnrollment

ZERO = Decimal('0.00')
BUCKETS = ('not_due', 'days_0_30', 'days_31_60', 'days_61_90', 'days_90_plus')


def charges_for(school, selected, student=None):
    rows = StudentFeeAssignment.objects.filter(student__school=school, fee__school=school,
        fee__academic_year__school=school, fee__term__academic_year__school=school).select_related(
        'student__school_class', 'fee__academic_year', 'fee__term', 'fee__recurring_template__term').prefetch_related(
        'payments__receipt', 'ledger_entries', 'student__parent_links__parent__user', 'student__enrollments')
    if student:
        rows = rows.filter(student=student)
    for key in ('academic_year', 'term'):
        if key in selected:
            rows = rows.filter(**{'fee__' + key + '_id': selected[key]})
    if selected.get('school_class'):
        get_object_or_404(SchoolClass, school=school, pk=selected['school_class'])
    if selected.get('student'):
        get_object_or_404(Student, school=school, pk=selected['student'])
        rows = rows.filter(student_id=selected['student'])
    if text := selected.get('search'):
        rows = rows.filter(Q(student__first_name__icontains=text) | Q(student__last_name__icontains=text) | Q(student__admission_number__icontains=text))
    rows = rows.order_by('student_id', 'assigned_on', 'pk')
    if selected.get('school_class'):
        from .finance import assignment_period
        selected_rows = []
        for charge in rows:
            start, end = assignment_period(charge)
            if any(e.school_class_id == selected['school_class'] and e.academic_year_id == charge.fee.academic_year_id
                   and e.enrolled_on < end and (not e.left_on or e.left_on >= start) for e in charge.student.enrollments.all()):
                selected_rows.append(charge)
        return selected_rows
    return rows


def valid_payment(payment, as_of):
    return payment.paid_at.date() <= as_of and not (
        payment.is_reversed and (not payment.reversed_at or payment.reversed_at.date() <= as_of))


def paid_as_of(assignment, as_of):
    return sum((p.amount for p in assignment.payments.all() if valid_payment(p, as_of)), ZERO)


def guardian(student):
    return ', '.join(link.parent.user.get_full_name() or link.parent.user.username
                     for link in student.parent_links.all() if link.parent.school_id == student.school_id)


def ageing_report(school, selected):
    as_of = selected.get('reporting_date', timezone.localdate())
    grouped = {}
    for charge in charges_for(school, selected):
        if charge.assigned_on > as_of:
            continue
        student = charge.student
        row = grouped.setdefault(student.pk, dict(student=student.pk, student_name=f'{student.first_name} {student.last_name}',
            admission_number=student.admission_number, class_name=student.school_class.name, guardian=guardian(student),
            charges=ZERO, payments=ZERO, adjustments=ZERO, outstanding=ZERO, **{key: ZERO for key in BUCKETS}))
        adjustments = sum((e.amount for e in charge.ledger_entries.all() if e.entry_type == 'adjustment' and e.occurred_at.date() <= as_of), ZERO)
        paid = paid_as_of(charge, as_of)
        row['charges'] += charge.amount_owed
        row['payments'] += paid
        row['adjustments'] += adjustments
        due = charge.fee.due_date or charge.assigned_on
        remaining = charge.amount_owed + adjustments - paid
        age = (as_of - due).days
        bucket = 'not_due' if age < 0 else 'days_0_30' if age <= 30 else 'days_31_60' if age <= 60 else 'days_61_90' if age <= 90 else 'days_90_plus'
        row[bucket] += remaining
        row['outstanding'] += remaining
    # Independent adjustments have their own obligation date. They are never
    # inferred from the ledger's mirrored charge/payment/reversal entries.
    independent = FinancialLedgerEntry.objects.filter(student__school=school, entry_type='adjustment', fee_assignment__isnull=True, occurred_at__date__lte=as_of).select_related('student__school_class').prefetch_related('student__parent_links__parent__user')
    if any(selected.get(k) for k in ('academic_year', 'term')):
        independent = independent.none()  # unassigned entries have no academic context
    for entry in independent:
        s = entry.student
        if selected.get('student') and s.pk != selected['student']:
            continue
        if selected.get('school_class') and s.school_class_id != selected['school_class']:
            continue
        if selected.get('search') and selected['search'].lower() not in f'{s.first_name} {s.last_name} {s.admission_number}'.lower():
            continue
        row = grouped.setdefault(s.pk, dict(student=s.pk, student_name=f'{s.first_name} {s.last_name}', admission_number=s.admission_number,
            class_name=s.school_class.name, guardian=guardian(s), charges=ZERO, payments=ZERO, adjustments=ZERO, outstanding=ZERO, **{key: ZERO for key in BUCKETS}))
        age = (as_of - entry.occurred_at.date()).days
        key = 'days_0_30' if age <= 30 else 'days_31_60' if age <= 60 else 'days_61_90' if age <= 90 else 'days_90_plus'
        row[key] += entry.amount
        row['adjustments'] += entry.amount
        row['outstanding'] += entry.amount
    # Unallocated credit adjustments offset oldest obligations, without
    # manufacturing a payment or moving any actual charge allocation.
    for row in grouped.values():
        credit = -sum((min(row[k], ZERO) for k in BUCKETS), ZERO)
        for key in BUCKETS:
            row[key] = max(row[key], ZERO)
        for key in reversed(BUCKETS):
            used = min(credit, row[key]); row[key] -= used; credit -= used
    rows = [r for r in grouped.values() if r['outstanding'] > 0]
    sort = selected.get('sort', 'student_name')
    rows.sort(key=lambda r: r[sort.lstrip('-')].casefold() if isinstance(r[sort.lstrip('-')], str) else r[sort.lstrip('-')], reverse=sort.startswith('-'))
    totals = {key: sum((r[key] for r in rows), ZERO) for key in ('charges', 'payments', 'adjustments', 'outstanding', *BUCKETS)}
    return dict(reporting_date=as_of, currency=school.default_currency, rows=rows, totals=totals,
        filters=selected, note='Ageing uses due date, or assignment date when no due date exists. 90+ means over 90 days. Future due amounts are shown separately. Payments remain allocated to their original charges. Class labels show the current class; class filters use enrollment history for the billed year.')


def statement_events(student):
    events = []
    def add(day, order, reference, description, debit, credit, kind, charge=None):
        events.append(dict(date=day, key=order, reference=reference, description=description, debit=debit, credit=credit, kind=kind,
            period=f'{charge.fee.academic_year.name} / {charge.fee.term.name}' if charge else 'Account adjustment'))
    for charge in charges_for(student.school, {}, student):
        add(charge.assigned_on, (0, charge.pk), f'FEE-{charge.fee_id}', charge.fee.name, charge.amount_owed, ZERO, 'charge', charge)
        for p in charge.payments.all():
            reference = p.receipt.receipt_number if hasattr(p, 'receipt') else p.reference or f'PAY-{p.pk}'
            add(p.paid_at.date(), (1, p.pk), reference, 'Payment: ' + charge.fee.name, ZERO, p.amount, 'payment', charge)
            if p.is_reversed:
                # All supported reversals carry their original reversal date.
                add(p.reversed_at.date() if p.reversed_at else p.paid_at.date(), (2, p.pk), reference, 'Payment reversal: ' + p.reversal_reason, p.amount, ZERO, 'reversal', charge)
    for entry in FinancialLedgerEntry.objects.filter(student=student, entry_type='adjustment').select_related('fee_assignment__fee__academic_year', 'fee_assignment__fee__term'):
        add(entry.occurred_at.date(), (3, entry.pk), f'ADJ-{entry.pk}', entry.description, max(entry.amount, ZERO), max(-entry.amount, ZERO), 'adjustment', entry.fee_assignment)
    return sorted(events, key=lambda row: (row['date'], row['key']))
