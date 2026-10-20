"""Read-only checks of seeded provenance, relationships and canonical reports."""
from collections import Counter
from datetime import date
from decimal import Decimal

from django.core.management.base import CommandError
from django.db.models import Count, F, Q, Sum

from . import models as m
from .demo_seed import manifest_for, manifest_objects
from .financial_reports import BUCKETS, ageing_report, statement_events
from .school_finance import cash_events, financial_report, movement_report


def verify_demo(school):
    if not school.is_demo:
        raise CommandError("Verification requires an explicitly marked demo school.")
    record = manifest_for(school)
    if record is None:
        raise CommandError("No demo seed manifest found; run seed_demo_school first.")
    manifest = record.response_body
    cache = manifest_objects(manifest, school)
    day = date.fromisoformat(manifest["as_of"])
    errors = []

    def check(ok, message):
        if not ok:
            errors.append(message)

    def seeded(model):
        return model.objects.filter(pk__in=cache.get(model, {}))

    students = seeded(m.Student)
    check(students.count() == 60, "Expected 60 managed demo students")
    check(seeded(m.Teacher).count() == 5, "Expected five teachers")
    check(set(students.values('school_class').annotate(n=Count('id')).values_list('n', flat=True)) == {10}, "Expected ten learners in each demo class")
    check(not students.filter(parent_links__isnull=True).exists(), "Learner without guardian")
    check(not students.filter(enrollments__isnull=True).exists(), "Learner without enrollment")
    check(not students.filter(fee_assignments__isnull=True).exists(), "Learner without finance history")
    for link in seeded(m.ParentStudent).select_related('student', 'parent'):
        check(link.parent.school_id == link.student.school_id == school.pk, "Cross-school guardian link")
    assignments = seeded(m.TeacherAssignment).prefetch_related('subjects')
    authorized = set()
    for item in assignments:
        for subject in item.subjects.all():
            check(subject.school_class_id == item.school_class_id, "Assignment contains a subject from another class")
            authorized.add((item.teacher_id, subject.pk))
    teachers_by_user = dict(seeded(m.Teacher).values_list('user_id', 'pk'))
    for result in seeded(m.AcademicResult).select_related('class_subject', 'student_enrollment', 'term'):
        enrollment = result.student_enrollment
        check(result.class_subject.school_class_id == enrollment.school_class_id and result.class_subject.academic_year_id == enrollment.academic_year_id == result.term.academic_year_id,
              "Result class/year/term mismatch")
        check((teachers_by_user.get(result.recorded_by_id), result.class_subject_id) in authorized, "Result has no authorized assigned teacher")
    check(set(seeded(m.AcademicResult).values_list('status', flat=True)) == {'draft', 'submitted', 'approved', 'published'}, "Missing result workflow states")
    check(set(seeded(m.Homework).values_list('status', flat=True)) == {'draft', 'published', 'closed'}, "Missing homework states")
    attendance = seeded(m.AttendanceRecord)
    check(set(attendance.values_list('status', flat=True)) == {'present', 'absent', 'late', 'excused'}, "Missing attendance statuses")
    check(len({d.strftime('%Y-%m') for d in attendance.values_list('attendance_date', flat=True)}) >= 2, "Insufficient attendance months")
    check(not attendance.exclude(academic_year_id=F('enrollment__academic_year_id')).exists(), "Attendance enrollment/year mismatch")
    check(not attendance.exclude(academic_year_id=F('term__academic_year_id')).exists(), "Attendance term/year mismatch")
    check(not attendance.filter(Q(attendance_date__lt=F('term__start_date')) | Q(attendance_date__gt=F('term__end_date'))).exists(), "Attendance outside its term")
    for publication in seeded(m.ReportCardPublication):
        check(bool(publication.snapshot.get('results')), "Empty official publication")
    for resource in seeded(m.TeachingResource):
        check((resource.teacher_id, resource.class_subject_id) in authorized, "Resource has no assigned teacher")
        check(bool(resource.file) and resource.file.storage.exists(resource.file.name), "Missing resource fixture")
    for attachment in seeded(m.ExpenseAttachment):
        check(bool(attachment.file) and attachment.file.storage.exists(attachment.file.name), "Missing expense fixture")
        if attachment.file:
            check(attachment.file.size == attachment.size, "Attachment size mismatch")
    payments = seeded(m.Payment).select_related('receipt', 'ledger_entry')
    for payment in payments:
        check(hasattr(payment, 'receipt') and hasattr(payment, 'ledger_entry'), "Payment missing receipt or ledger")
        if hasattr(payment, 'ledger_entry'):
            check(payment.ledger_entry.amount == payment.amount and payment.ledger_entry.fee_assignment_id == payment.student_fee_assignment_id,
                  "Payment ledger mismatch")
    for charge in seeded(m.StudentFeeAssignment).prefetch_related('payments'):
        check(sum((p.amount for p in charge.payments.all() if not p.is_reversed), Decimal(0)) <= charge.amount_owed, "Payment exceeds charge")
    for invoice in seeded(m.StudentInvoice).select_related('assignment'):
        check(invoice.total == invoice.assignment.amount_owed == sum((Decimal(line['total']) for line in invoice.snapshot['lines']), Decimal(0)), "Invoice total mismatch")
        check(invoice.snapshot['student']['id'] == invoice.assignment.student_id, "Invoice learner mismatch")
    for student in students:
        events = statement_events(student)
        closing = sum((e['debit'] - e['credit'] for e in events), Decimal(0))
        charges = student.fee_assignments.aggregate(n=Sum('amount_owed'))['n'] or Decimal(0)
        paid = m.Payment.objects.filter(student_fee_assignment__student=student, is_reversed=False).aggregate(n=Sum('amount'))['n'] or Decimal(0)
        adjustments = student.ledger_entries.filter(entry_type='adjustment').aggregate(n=Sum('amount'))['n'] or Decimal(0)
        check(closing == charges + adjustments - paid, "Statement balance does not reconcile")
    ageing = ageing_report(school, {'reporting_date': day})
    for bucket in BUCKETS:
        check(ageing['totals'][bucket] > 0, f"Empty ageing bucket: {bucket}")
    events = cash_events(school, day)
    ids = [row['id'] for row in events]
    check(len(ids) == len(set(ids)), "Duplicate cashbook source movement")
    check(sum(row['linked_type'] == 'payment' and not row['correction'] for row in events) == m.Payment.objects.filter(student_fee_assignment__student__school=school, paid_at__date__lte=day).count(), "Cashbook payment linkage count differs")
    book = movement_report(school, {}, date(day.year, 1, 1), day, 'cash-books')
    summary = book['summary']
    check(summary['closing_balance'] == summary['opening_balance'] + summary['money_in'] - summary['money_out'], "Cashbook does not reconcile")
    report = financial_report(school, {}, date(day.year, 1, 1), day)
    for field in ('billed_fees', 'fees_collected', 'other_income', 'expenses', 'surplus_deficit'):
        check(sum((month[field] for month in report['months']), Decimal(0)) == report['summary'][field], f"Monthly/annual mismatch: {field}")
    for variant in seeded(m.InventoryVariant).prefetch_related('stock_movements'):
        stock = sum(row.quantity if row.direction == 'in' else -row.quantity for row in variant.stock_movements.all())
        check(stock > 0, "Non-positive demo stock")
    check(seeded(m.AuditLog).exists(), "Missing demo audit events")
    if errors:
        raise CommandError("Demo verification failed: " + "; ".join(dict.fromkeys(errors)))
    counts = Counter(entry['model'].split('.')[-1] for entry in manifest['objects'].values())
    counts['published_results'] = seeded(m.AcademicResult).filter(status='published').count()
    counts['cashbook_records'] = len(events)
    return dict(counts), report['summary']
