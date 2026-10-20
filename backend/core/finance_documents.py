"""Tenant-authorized official invoices, debtor reports and statement exports."""
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from .audit import log_action
from .documents import SchoolDocument, branding, money, excel, attachment
from .financial_reports import BUCKETS, ZERO, ageing_report, guardian, paid_as_of
from .models import School, SchoolDocumentSettings, SchoolInvoiceSequence, StudentInvoice, StudentFeeAssignment, Student, AcademicYear, Term, SchoolClass
from .permissions import IsSchoolAdministrator, IsParent
from .reporting_api import ReportFilters, filters, account_statement


class DocumentSettingsSerializer(serializers.ModelSerializer):
    def validate_grading_scale(self, value):
        if not isinstance(value, list) or len(value) > 30:
            raise serializers.ValidationError('Use up to 30 grade bands.')
        result, seen = [], set()
        for band in value:
            if not isinstance(band, dict) or set(band) != {'minimum', 'grade'}:
                raise serializers.ValidationError('Each band requires minimum and grade.')
            minimum = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100).run_validation(band['minimum'])
            grade = serializers.CharField(max_length=30).run_validation(band['grade'])
            if minimum in seen:
                raise serializers.ValidationError('Grade thresholds must be unique.')
            seen.add(minimum); result.append({'minimum': str(minimum), 'grade': grade})
        if result and Decimal('0') not in seen:
            raise serializers.ValidationError('Include a minimum of 0 to cover all published marks.')
        return sorted(result, key=lambda b: Decimal(b['minimum']), reverse=True)

    class Meta:
        model = SchoolDocumentSettings
        fields = ['motto', 'website', 'additional_contacts', 'contact_person', 'brand_color', 'parent_invoice_access', 'grading_scale']


class DocumentSettingsView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request):
        obj = SchoolDocumentSettings.objects.filter(school=request.user.school_administrator.school).first()
        return Response(DocumentSettingsSerializer(obj or SchoolDocumentSettings()).data)

    @transaction.atomic
    def patch(self, request):
        school = request.user.school_administrator.school
        if set(request.data) - set(DocumentSettingsSerializer.Meta.fields):
            raise serializers.ValidationError('Only document settings can be changed here.')
        obj, _ = SchoolDocumentSettings.objects.get_or_create(school=school)
        serializer = DocumentSettingsSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True); serializer.save()
        log_action(school=school, actor=request.user, action='document_settings_updated', resource=obj)
        return Response(serializer.data)


class FinanceReportFilters(ReportFilters):
    reporting_date = serializers.DateField(required=False)
    sort = serializers.ChoiceField(required=False, choices=[prefix + key for prefix in ('', '-') for key in ('student_name', 'admission_number', 'class_name', 'guardian', 'charges', 'payments', 'adjustments', 'outstanding', *BUCKETS)])
    export = serializers.ChoiceField(required=False, choices=['json', 'pdf', 'xlsx'])


def report_filters(request, school):
    filters(request, school)  # validate calendar ownership as well as dates
    serializer = FinanceReportFilters(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def export_kind(request, choices=('json', 'pdf', 'xlsx')):
    return serializers.ChoiceField(choices=choices).run_validation(request.query_params.get('export', 'json'))


class DebtorsView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request, outstanding=False):
        school = request.user.school_administrator.school
        selected = report_filters(request, school)
        data = ageing_report(school, selected)
        data['school'] = branding(school, request)
        data['years'] = list(AcademicYear.objects.filter(school=school).values('id', 'name'))
        data['terms'] = list(Term.objects.filter(academic_year__school=school).values('id', 'name', 'academic_year'))
        data['classes'] = list(SchoolClass.objects.filter(school=school).values('id', 'name'))
        kind = selected.get('export', 'json')
        if kind == 'json':
            return Response(data)
        keys = ['admission_number', 'student_name', 'class_name', 'guardian', *(['charges', 'payments', 'adjustments', 'outstanding'] if outstanding else ['outstanding', *BUCKETS])]
        labels = {'admission_number': 'Admission No.', 'student_name': 'Student', 'class_name': 'Class', 'guardian': 'Parent / Guardian', 'charges': 'Billed charges', 'payments': 'Cash collected', 'adjustments': 'Adjustments', 'outstanding': 'Outstanding', 'not_due': 'Not due', 'days_0_30': '0–30 days', 'days_31_60': '31–60 days', 'days_61_90': '61–90 days', 'days_90_plus': '90+ days'}
        title = 'Outstanding Balances' if outstanding else 'Ageing Debtors'
        headers = [labels[k] for k in keys]
        rows = [[r[k] for k in keys] for r in data['rows']]
        total_row = ['School totals', '', '', '', *[data['totals'][k] for k in keys[4:]]]
        if kind == 'xlsx':
            return attachment(excel([[school.name, title, str(data['reporting_date']), data['currency']],
                ['Filters', str({k: str(v) for k, v in selected.items() if k != 'export'})], headers, *rows, total_row], title), 'debtors', kind)
        doc = SchoolDocument(branding(school, request, snapshot=True), title, wide=True)
        doc.text(f'Reporting date: {data["reporting_date"]} | Currency: {data["currency"]}')
        doc.text('Filters: ' + ', '.join(f'{k}: {v}' for k, v in selected.items() if k != 'export'))
        doc.text(data['note'])
        doc.table(headers, [[money(v) if isinstance(v, Decimal) else v for v in row] for row in [*rows, total_row]], [1, 1.6, 1, 1.5, *([1] * (len(keys) - 4))], footer=True)
        doc.text('Billed income, cash collected and outstanding receivables are separate figures. Totals cover the displayed learners and selected filters.')
        return attachment(doc.render(), 'debtors', kind)


def student_info(student):
    return dict(id=student.pk, name=f'{student.first_name} {student.last_name}', admission_number=student.admission_number,
                class_name=student.school_class.name, guardian=guardian(student))


@transaction.atomic
def generate_invoice(*, school, assignment_id, actor, request=None):
    # One school-local sequence, serialized by its school row (also handles first
    # use); one-to-one obligation constraint makes retries duplicate-safe.
    School.objects.select_for_update().get(pk=school.pk)
    charge = get_object_or_404(StudentFeeAssignment.objects.select_for_update().select_related('student__school', 'student__school_class', 'fee__academic_year', 'fee__term'),
                              pk=assignment_id, student__school=school, fee__school=school)
    existing = StudentInvoice.objects.filter(assignment=charge, school=school).first()
    if existing:
        return existing, False
    sequence, _ = SchoolInvoiceSequence.objects.get_or_create(school=school)
    number = f'INV-{sequence.next_number:06d}'
    sequence.next_number += 1; sequence.save(update_fields=['next_number'])
    snapshot = dict(school=branding(school, request, snapshot=True), student=student_info(charge.student),
        academic_year=charge.fee.academic_year.name, academic_year_id=charge.fee.academic_year_id,
        term=charge.fee.term.name, term_id=charge.fee.term_id,
        lines=[dict(quantity=1, description=charge.fee.name, unit_amount=str(charge.amount_owed), total=str(charge.amount_owed))],
        obligation_date=str(charge.assigned_on))
    invoice = StudentInvoice.objects.create(school=school, assignment=charge, number=number, issued_on=timezone.localdate(),
        due_date=charge.fee.due_date or charge.assigned_on, currency=charge.currency, total=charge.amount_owed, snapshot=snapshot, generated_by=actor)
    log_action(school=school, actor=actor, action='invoice_generated', resource=invoice, description=f'Official invoice {number}; obligation {charge.pk}')
    return invoice, True


def invoice_data(invoice, summary=False):
    paid = paid_as_of(invoice.assignment, timezone.localdate())
    snapshot = dict(student=invoice.list_student, academic_year=invoice.list_year, academic_year_id=invoice.list_year_id,
                    term=invoice.list_term, term_id=invoice.list_term_id) if summary else invoice.snapshot
    return dict(id=invoice.pk, number=invoice.number, assignment=invoice.assignment_id, issued_on=invoice.issued_on,
        due_date=invoice.due_date, currency=invoice.currency, subtotal=invoice.total, total=invoice.total,
        payments_allocated=paid, outstanding_balance=invoice.total - paid, total_amount_due=max(invoice.total - paid, ZERO),
        payment_status='Paid' if paid >= invoice.total else 'Part paid' if paid else 'Unpaid',
        **snapshot)


class InvoiceView(APIView):
    permission_classes = [IsSchoolAdministrator | IsParent]

    def scoped(self, request):
        rows = StudentInvoice.objects.select_related('assignment__student', 'assignment__fee', 'school').prefetch_related('assignment__payments')
        if request.user.role == 'parent':
            parent = request.user.parent_profile
            if not SchoolDocumentSettings.objects.filter(school=parent.school, parent_invoice_access=True).exists():
                raise PermissionDenied('Parent invoice access is not enabled by this school.')
            return rows.filter(school=parent.school, assignment__student__school=parent.school, assignment__student__parent_links__parent=parent).distinct()
        return rows.filter(school=request.user.school_administrator.school, assignment__student__school=request.user.school_administrator.school)

    def get(self, request, invoice_id=None):
        rows = self.scoped(request)
        if invoice_id is None:
            school = request.user.parent_profile.school if request.user.role == 'parent' else request.user.school_administrator.school
            selected = report_filters(request, school)
            for key, lookup in [('student', 'assignment__student_id'), ('academic_year', 'snapshot__academic_year_id'), ('term', 'snapshot__term_id')]:
                if selected.get(key):
                    rows = rows.filter(**{lookup: selected[key]})
            if selected.get('search'):
                text = selected['search']
                rows = rows.filter(Q(number__icontains=text) | Q(snapshot__student__name__icontains=text) | Q(snapshot__student__admission_number__icontains=text))
            # List responses need billing metadata, not the embedded historical
            # logo. Select JSON keys in PostgreSQL to avoid loading megabytes of
            # image snapshots for every invoice in a school's list.
            rows = rows.defer('snapshot').annotate(list_student=F('snapshot__student'), list_year=F('snapshot__academic_year'),
                list_year_id=F('snapshot__academic_year_id'), list_term=F('snapshot__term'), list_term_id=F('snapshot__term_id'))
            return Response([invoice_data(i, summary=True) for i in rows.order_by('-issued_on', '-id')])
        invoice = get_object_or_404(rows, pk=invoice_id)
        data = invoice_data(invoice)
        kind = export_kind(request, ('json', 'pdf'))
        if kind == 'json':
            return Response(data)
        doc = SchoolDocument(data['school'], f'Invoice No. {invoice.number}')
        s = data['student']
        doc.table(['Student / Billing Information', 'Invoice / School Contact'], [
            [f'{s["name"]}\nAdmission: {s["admission_number"]}\nClass: {s["class_name"]}\nGuardian: {s["guardian"]}\nTerm: {data["academic_year"]} / {data["term"]}\nStatus: {data["payment_status"]}',
             f'Invoice date: {invoice.issued_on}\nDue date: {invoice.due_date}\n{data["school"]["contact_person"]}\n{data["school"]["phone"]}\n{data["school"]["email"]}']])
        doc.table(['Quantity', 'Description', 'Unit Amount', 'Total'], [[line['quantity'], line['description'], money(line['unit_amount'], invoice.currency), money(line['total'], invoice.currency)] for line in data['lines']], [1, 4, 2, 2])
        doc.totals([(label, money(data[key], invoice.currency)) for key, label in [('subtotal', 'Subtotal'), ('payments_allocated', 'Payments Allocated'), ('outstanding_balance', 'Outstanding Balance'), ('total_amount_due', 'Total Amount Due')]])
        doc.text('Payments and status are current at download. Issued charges and billing details are preserved. Account adjustments appear on the student financial statement.')
        log_action(school=invoice.school, actor=request.user, action='invoice_downloaded', resource=invoice)
        return attachment(doc.render(), invoice.number, 'pdf')

    def post(self, request, invoice_id=None):
        if request.user.role != 'school_admin':
            raise PermissionDenied('Only School Admin can generate invoices.')
        if invoice_id is not None:
            raise PermissionDenied('Official invoices cannot be edited or reissued.')
        if set(request.data) != {'assignment'}:
            raise serializers.ValidationError('Supply only the billed assignment.')
        assignment_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('assignment'))
        invoice, created = generate_invoice(school=request.user.school_administrator.school, assignment_id=assignment_id, actor=request.user, request=request)
        return Response(invoice_data(invoice), status=201 if created else 200)


def statement_response(student, request):
    data = account_statement(student, request)
    kind = export_kind(request)
    if kind == 'json':
        return Response(data)
    summary = data['summary']
    pairs = [(label, summary[key]) for key, label in [('opening_balance', 'Previous / Opening Balance'), ('charges', 'Current Charges'), ('payments', 'Current Payments'), ('adjustments_reversals', 'Adjustments / Reversals'), ('closing_balance', 'Current / Closing Balance')]]
    pairs.append(('Total Amount Due', max(summary['closing_balance'], ZERO)))
    headers = ['Term / Period', 'Date', 'Reference', 'Description', 'Debit / Charges', 'Credit / Payments', 'Running Balance']
    rows = [[r['period'], str(r['date']), r['reference'], r['description'], r['debit'], r['credit'], r['balance']] for r in data['transactions']]
    opening = ['Opening balance', '', '', '', '', '', summary['opening_balance']]
    period = f'{data["period"]["start"] or "Beginning of account"} to {data["period"]["end"] or "Full history"}'
    if kind == 'xlsx':
        content = excel([[student.school.name, 'Student Financial Statement', student.admission_number, data['student']['name']],
            ['Statement date', str(timezone.localdate()), 'Period', period, 'Currency', data['currency']], ['Due date', str(data['due_date'] or '')], headers, opening, *rows, [], *[[k, v] for k, v in pairs]], 'Statement')
    else:
        doc = SchoolDocument(branding(student.school, request, snapshot=True), 'Student Financial Statement')
        doc.text(f'{data["student"]["name"]} | Admission: {student.admission_number} | Current class: {data["student"]["class_name"]}')
        doc.text(f'Statement date: {timezone.localdate()} | Period: {period} | Currency: {data["currency"]}')
        if data['due_date']:
            doc.text(f'Earliest outstanding due date: {data["due_date"]}')
        doc.table(headers, [[money(v) if isinstance(v, Decimal) else v for v in row] for row in [opening, *rows]], [1.5, 1.2, 1.2, 2.6, 1.1, 1.1, 1.3])
        doc.totals([(k, money(v, data['currency'])) for k, v in pairs])
        doc.text('Opening balance includes all earlier transactions. Payments retain their original transaction dates. Reversals are separate debits on their reversal dates.')
        content = doc.render()
    log_action(school=student.school, actor=request.user, action='statement_generated', resource=student, description=f'Statement export: {kind}')
    return attachment(content, f'statement-{student.pk}', kind)


def receipt_document_response(receipt):
    """Retain the existing receipt actions and records, sharing A4 branding."""
    from .finance import assignment_totals
    payment = receipt.payment
    assignment = payment.student_fee_assignment
    student, school = assignment.student, assignment.student.school
    _, _, outstanding = assignment_totals(assignment)
    doc = SchoolDocument(branding(school, snapshot=True), 'PAYMENT RECEIPT')
    doc.text('STATUS: REVERSED' if receipt.is_reversed or payment.is_reversed else 'STATUS: PAID', 'Heading2')
    doc.table(['Receipt / Student', 'Payment Details'], [[
        f'Receipt number: {receipt.receipt_number}\nStudent: {student.first_name} {student.last_name}\nAdmission number: {student.admission_number}\nClass: {student.school_class.name}',
        f'Payment date: {payment.paid_at:%Y-%m-%d %H:%M}\nPayment method: {payment.method}\nReference: {payment.reference or "-"}\nRecorded date: {payment.created_at:%Y-%m-%d %H:%M}'
    ]])
    doc.table(['Fee / Charge', 'Amount Paid'], [[assignment.fee.name, money(payment.amount, payment.currency)]], [3, 1])
    doc.totals([('Amount paid', money(payment.amount, payment.currency)), ('Outstanding balance', money(outstanding, payment.currency))])
    import re
    filename = re.sub(r'[^A-Za-z0-9_.-]', '_', receipt.receipt_number)
    return attachment(doc.render(), f'receipt-{filename}', 'pdf')
