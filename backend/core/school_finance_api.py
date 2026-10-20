"""School-admin finance entry, configuration and read-only report endpoints."""
import json
from copy import copy
from decimal import Decimal
from pathlib import Path
from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .audit import log_action
from .documents import SchoolDocument, attachment, branding, excel, money
from .idempotency import IdempotentCreateMixin
from .models import (FinanceAccount, FinanceCategory, ManualIncome, Expense, ExpenseRevision, ExpenseAttachment,
                     FinancialReportNote, AcademicYear, Term, SchoolClass, Payment)
from .permissions import IsSchoolAdministrator
from .serializers import ExpenseSerializer, validate_homework_file
from .school_finance import report_period, financial_report, movement_report
from .views import SchoolAdminViewSet, ExpenseViewSet


def reject_extra(serializer, allowed=None, ignored=()):
    submitted = set(serializer.initial_data) - set(ignored)
    if submitted - set(allowed or serializer.fields):
        raise ValidationError('Unsupported fields. School ownership and linked student payments are controlled by the server.')
    for key in ('school', 'school_id', 'recorded_by', 'is_reversed', 'reversed_by', 'reversed_at'):
        if key in submitted:
            raise ValidationError({key: 'This field is controlled by the server.'})


def validate_links(data, school, category_field, kind, instance=None):
    for field, model in [('account', FinanceAccount), (category_field, FinanceCategory)]:
        value = data.get(field)
        if value and (value.school_id != school.pk or (field == category_field and value.kind != kind)):
            raise ValidationError({field: 'Choose a matching record in this school.'})
        if value and not value.is_active and (not instance or getattr(instance, field + '_id') != value.pk):
            raise ValidationError({field: 'Choose an active record.'})


class ConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinanceAccount
        fields = ['id', 'name', 'kind', 'is_active']
        read_only_fields = ['id']
        validators = []

    def validate(self, attrs):
        reject_extra(self)
        school = self.context['school']
        name = attrs.get('name', getattr(self.instance, 'name', ''))
        duplicates = self.Meta.model.objects.filter(school=school, name=name)
        if self.Meta.model == FinanceCategory:
            duplicates = duplicates.filter(kind=attrs.get('kind', getattr(self.instance, 'kind', '')))
        if self.instance: duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists(): raise ValidationError({'name': 'This name already exists in this school.'})
        if self.instance and any(getattr(self.instance, relation).exists() for relation in ('payments', 'expenses', 'manual_income')):
            if any(key != 'is_active' and getattr(self.instance, key) != value for key, value in attrs.items()):
                raise ValidationError('Used account/category details are preserved. Deactivate it and create a replacement.')
        return attrs


class CategorySerializer(ConfigurationSerializer):
    class Meta(ConfigurationSerializer.Meta):
        model = FinanceCategory


class FinanceConfigurationViewSet(SchoolAdminViewSet):
    queryset = FinanceAccount.objects.all()
    serializer_class = ConfigurationSerializer

    def get_queryset(self): return super().get_queryset().order_by('name', 'pk')

    def perform_create(self, serializer):
        record = serializer.save(school=self.get_school())
        log_action(school=self.get_school(), actor=self.request.user, action='finance_configuration_created', resource=record)

    def perform_update(self, serializer):
        record = serializer.save()
        log_action(school=self.get_school(), actor=self.request.user, action='finance_configuration_updated', resource=record)

    def destroy(self, request, *args, **kwargs): raise MethodNotAllowed('DELETE')


class FinanceCategoryViewSet(FinanceConfigurationViewSet):
    queryset = FinanceCategory.objects.all()
    serializer_class = CategorySerializer


class OtherIncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualIncome
        fields = ['id', 'income_date', 'source', 'description', 'category', 'account', 'amount', 'currency', 'payment_method',
                  'reference', 'notes', 'recorded_by', 'created_at', 'is_reversed', 'reversed_at', 'reversal_reason']
        read_only_fields = ['id', 'currency', 'recorded_by', 'created_at', 'is_reversed', 'reversed_at', 'reversal_reason']

    def get_fields(self):
        fields = super().get_fields()
        for key, model in [('category', FinanceCategory), ('account', FinanceAccount)]:
            fields[key].queryset = model.objects.filter(school=self.context['school'])
        return fields

    def validate(self, attrs):
        reject_extra(self)
        validate_links(attrs, self.context['school'], 'category', 'income')
        return attrs


def reverse_cash_record(record, request):
    if set(request.data) != {'reason'}: raise ValidationError('Supply only a reversal reason.')
    reason = serializers.CharField(min_length=3, max_length=1000).run_validation(request.data.get('reason'))
    if record.is_reversed: raise ValidationError('This record is already reversed.')
    record.is_reversed, record.reversed_at, record.reversed_by, record.reversal_reason = True, timezone.now(), request.user, reason
    record.save(update_fields=['is_reversed', 'reversed_at', 'reversed_by', 'reversal_reason'])
    log_action(school=record.school, actor=request.user, action='expense_reversed' if isinstance(record, Expense) else 'manual_income_reversed', resource=record)


class OtherIncomeViewSet(IdempotentCreateMixin, SchoolAdminViewSet):
    queryset = ManualIncome.objects.all()
    serializer_class = OtherIncomeSerializer

    def get_queryset(self): return super().get_queryset().order_by('-income_date', '-pk')

    @transaction.atomic
    def perform_create(self, serializer):
        record = serializer.save(school=self.get_school(), currency=self.get_school().default_currency, recorded_by=self.request.user)
        log_action(school=self.get_school(), actor=self.request.user, action='manual_income_created', resource=record)

    def update(self, request, *args, **kwargs): raise MethodNotAllowed(request.method)
    def destroy(self, request, *args, **kwargs): raise MethodNotAllowed('DELETE')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reverse(self, request, pk=None):
        record = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
        reverse_cash_record(record, request)
        return Response(self.get_serializer(record).data)


class SchoolExpenseSerializer(ExpenseSerializer):
    attachments = serializers.SerializerMethodField()

    class Meta(ExpenseSerializer.Meta):
        fields = ExpenseSerializer.Meta.fields + ['account', 'finance_category', 'payee', 'is_reversed', 'reversed_at', 'reversal_reason', 'attachments']
        read_only_fields = ExpenseSerializer.Meta.read_only_fields + ['is_reversed', 'reversed_at', 'reversal_reason', 'attachments']

    def get_fields(self):
        fields = super().get_fields()
        for key, model in [('account', FinanceAccount), ('finance_category', FinanceCategory)]:
            fields[key].queryset = model.objects.filter(school=self.get_school())
        return fields

    def get_attachments(self, expense):
        return [dict(id=a.pk, name=a.original_name, size=a.size, download_url=f'/school/expenses/{expense.pk}/attachments/{a.pk}/download/') for a in expense.attachments.all()]

    def validate(self, attrs):
        # Preserve the established expense API: ownership hints are ignored,
        # and school/currency are always derived from the authenticated admin.
        reject_extra(self, ignored=('school', 'school_id'))
        validate_links(attrs, self.get_school(), 'finance_category', 'expense', self.instance)
        if self.instance and self.instance.is_reversed: raise ValidationError('Reversed expenses are preserved and cannot be edited.')
        candidate = copy(self.instance) if self.instance else Expense(school=self.get_school(), currency=self.get_school().default_currency)
        for key, value in attrs.items(): setattr(candidate, key, value)
        try: candidate.clean()
        except ModelValidationError as exc: raise ValidationError(getattr(exc, 'message_dict', exc.messages)) from exc
        return attrs


class SchoolExpenseViewSet(IdempotentCreateMixin, ExpenseViewSet):
    serializer_class = SchoolExpenseSerializer

    def get_queryset(self):
        rows = super().get_queryset().select_related('account', 'finance_category').prefetch_related('attachments')
        school = self.get_school()
        for field, model in [('account', FinanceAccount), ('finance_category', FinanceCategory)]:
            if value := self.request.query_params.get(field):
                if field == 'account' and value == 'unassigned':
                    rows = rows.filter(account__isnull=True)
                else:
                    pk = serializers.IntegerField(min_value=1).run_validation(value)
                    get_object_or_404(model, school=school, pk=pk)
                    rows = rows.filter(**{field + '_id': pk})
        if value := self.request.query_params.get('payment_method'): rows = rows.filter(payment_method=value)
        return rows

    @transaction.atomic
    def perform_create(self, serializer): super().perform_create(serializer)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=kwargs['pk'])
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        snapshot = json.loads(json.dumps(model_to_dict(serializer.instance, exclude=['reversed_by']), cls=DjangoJSONEncoder))
        ExpenseRevision.objects.create(expense=serializer.instance, snapshot=snapshot, actor=self.request.user)
        super().perform_update(serializer)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reverse(self, request, pk=None):
        record = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        reverse_cash_record(record, request)
        return Response(self.get_serializer(record).data)

    @action(detail=True, methods=['get'])
    def revisions(self, request, pk=None):
        record = self.get_object()
        return Response(list(record.revisions.order_by('-created_at').values('id', 'snapshot', 'actor_id', 'created_at')))

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def attachments(self, request, pk=None):
        record = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        if set(request.data) != {'file'}: raise ValidationError('Supply one supporting file.')
        upload = serializers.FileField().run_validation(request.data.get('file'))
        content_type = validate_homework_file(upload)
        if record.attachments.count() >= 5: raise ValidationError('An expense supports up to five preserved documents.')
        item = ExpenseAttachment.objects.create(expense=record, file=upload, original_name=Path(upload.name).name[:255], content_type=content_type,
            size=upload.size, uploaded_by=request.user)
        log_action(school=self.get_school(), actor=request.user, action='expense_attachment_added', resource=item)
        record._prefetched_objects_cache = {}
        return Response(self.get_serializer(record).data, status=201)

    @action(detail=True, methods=['get'], url_path=r'attachments/(?P<attachment_id>[^/.]+)/download')
    def attachment_download(self, request, attachment_id=None, pk=None):
        item = get_object_or_404(ExpenseAttachment, expense=self.get_object(), pk=attachment_id)
        try:
            response = FileResponse(item.file.open('rb'), as_attachment=True, filename=item.original_name, content_type=item.content_type)
        except OSError as exc: raise Http404('Supporting document is unavailable.') from exc
        response['Cache-Control'] = 'private, no-store'
        return response


class FinanceLookupsView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request):
        school = request.user.school_administrator.school
        methods = set(Payment.objects.filter(student_fee_assignment__student__school=school).values_list('method', flat=True))
        methods.update(Expense.objects.filter(school=school).values_list('payment_method', flat=True))
        methods.update(ManualIncome.objects.filter(school=school).values_list('payment_method', flat=True))
        return Response(dict(accounts=list(FinanceAccount.objects.filter(school=school).order_by('name').values('id', 'name', 'kind', 'is_active')),
            categories=list(FinanceCategory.objects.filter(school=school).order_by('kind', 'name').values('id', 'name', 'kind', 'is_active')),
            expense_categories=[dict(id=value, name=label) for value, label in Expense.Category.choices],
            years=list(AcademicYear.objects.filter(school=school).values('id', 'name', 'start_date', 'end_date')), terms=list(Term.objects.filter(academic_year__school=school).values('id', 'name', 'academic_year')),
            classes=list(SchoolClass.objects.filter(school=school).values('id', 'name')), currency=school.default_currency,
            payment_methods=sorted(methods | {'cash', 'bank', 'mobile_money'})))


METRICS = [('billed_fees', 'Billed Fees'), ('fees_collected', 'Fees Collected / Cash Collected'), ('other_income', 'Other Income'),
           ('total_cash_income', 'Total Cash Income'), ('expenses', 'Operating Expenses'), ('surplus_deficit', 'Operating Surplus / Deficit'),
           ('outstanding_receivables', 'Outstanding Receivables at Period End')]
TITLES = {'income': 'Income Records', 'cash-books': 'Cash Book', 'cash-received': 'Cash Received Report', 'monthly': 'Monthly Financial Report',
          'annual': 'Annual Financial Report', 'dashboard': 'Financial Dashboard', 'expense-report': 'Expense Report'}


class SchoolFinancialReportView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request, report):
        school = request.user.school_administrator.school
        if report not in TITLES: raise Http404
        selected, start, end = report_period(request, school, report)
        is_summary = report in ('monthly', 'annual', 'dashboard')
        data = financial_report(school, selected, start, end) if is_summary else movement_report(school, selected, start, end, report)
        academic_label = AcademicYear.objects.get(pk=selected['academic_year']).name if selected.get('academic_year') else 'All academic years'
        term = Term.objects.select_related('academic_year').get(pk=selected['term']) if selected.get('term') else None
        term_label = term.name if term else 'All terms'
        if term and not selected.get('academic_year'): academic_label = term.academic_year.name
        data.update(school=branding(school, request), currency=school.default_currency, generated_at=timezone.now(),
            title=TITLES[report], report=report, period=dict(start=start, end=end), filters=selected, academic_year_label=academic_label, term_label=term_label)
        kind = selected['export']
        if kind == 'json': return Response(data)
        rows = export_rows(data, is_summary)
        if kind == 'xlsx':
            content = excel([[school.name, TITLES[report]], ['Period', str(start), str(end), 'Currency', school.default_currency, academic_label, term_label], *rows], 'School Finance', header_row=3)
        else:
            doc = SchoolDocument(branding(school, request, snapshot=True), TITLES[report], wide=True)
            doc.text(f'Reporting period: {start} to {end} | Academic year: {academic_label} | Term: {term_label} | Generated: {timezone.now():%Y-%m-%d %H:%M} | {school.default_currency}')
            doc.text(data['note'])
            if is_summary:
                for section, label in [('income', 'INCOME'), ('expenditure', 'EXPENDITURE')]:
                    doc.text(label, 'Heading2')
                    table_rows = [[r['category'], money(r['actual'], school.default_currency)] for r in data['categories'] if r['section'] == section]
                    total = data['summary']['total_cash_income' if section == 'income' else 'expenses']
                    doc.table(['Detail / Category', 'Actual'], [*table_rows, ['Total ' + label.title(), money(total, school.default_currency)]], [4, 1], footer=True)
                doc.totals([(label, money(data['summary'][key], school.default_currency)) for key, label in METRICS])
                doc.text('Notes / Comments / Explanation', 'Heading2'); doc.text(data['notes'] or 'No management notes recorded.')
                if report == 'annual':
                    doc.table(['Month', 'Billed Fees', 'Fees Collected', 'Other Income', 'Expenses', 'Surplus / Deficit'],
                        [[r['month'], *[money(r[k]) for k in ('billed_fees', 'fees_collected', 'other_income', 'expenses', 'surplus_deficit')]] for r in data['months']])
            else:
                headers, values = movement_table(data)
                weights = [1, 1.1, 2.1, 1.2, 1, 1, 1, 1, 1.2, 1.3] if len(headers) == 10 else [1, 1.2, 1.3, 1, 1.2, 1.2, 2, 1, 1.2, 1, 1.2, 1.2]
                doc.table(headers, [[money(v) if isinstance(v, Decimal) else v for v in row] for row in values], weights)
                doc.totals([(label, money(data['summary'][key], school.default_currency)) for key, label in
                    [('opening_balance', 'Opening Balance'), ('money_in', 'Money In'), ('money_out', 'Money Out'), ('closing_balance', 'Closing Balance'), ('net_movement', 'Net Period Movement')]])
                doc.text('Net period totals by payment method', 'Heading2')
                doc.table(['Payment Method', 'Net Amount'], [[k, money(v, school.default_currency)] for k, v in data['method_totals'].items()])
            content = doc.render()
        log_action(school=school, actor=request.user, action='financial_report_generated', resource=school, description=f'{report}; {start} to {end}; {kind}')
        return attachment(content, f'{report}-{start}-{end}', kind)


def movement_table(data):
    if data['report'] in ('income', 'cash-received'):
        return ['Date', 'Receipt Number', 'Student', 'Admission Number', 'Source', 'Category', 'Description', 'Method', 'Account', 'Amount', 'Received By', 'Reference / Linked Record'], [
            [str(r['date']), r['receipt_number'], r['student_name'], r['admission_number'], r['source'], r['category'], r['description'], r['payment_method'], r['account_name'],
             r['amount'], r['received_by'], f'{r["reference"]}\n{r["linked_type"]} #{r["linked_id"]}'] for r in data['rows']]
    headers = ['Date', 'Reference / Receipt', 'Description / Source / Student', 'Category', 'Money In', 'Money Out', 'Running Balance', 'Method', 'Account', 'Linked Record / Received By']
    rows = [[str(r['date']), r['reference'] + (f' / {r["receipt_number"]}' if r['receipt_number'] and r['reference'] != r['receipt_number'] else ''),
             f'{r["description"]}\n{r["source"]}\n{r["student_name"]} {r["admission_number"]}\n{r["class_name"]}', r['category'],
             r['money_in'], r['money_out'], r['balance'], r['payment_method'], r['account_name'], f'{r["linked_type"]} #{r["linked_id"]}\n{r["received_by"]}'] for r in data['rows']]
    return headers, rows


def export_rows(data, is_summary):
    if is_summary:
        return [['Section', 'Detail / Category', 'Actual'], *[[r['section'], r['category'], r['actual']] for r in data['categories']],
            [], ['SUMMARY'], *[[label, data['summary'][key]] for key, label in METRICS], [], ['Notes / Comments / Explanation', data['notes']], [],
            ['Month', 'Billed Fees', 'Fees Collected', 'Other Income', 'Expenses', 'Surplus / Deficit'],
            *[[r['month'], *[r[k] for k in ('billed_fees', 'fees_collected', 'other_income', 'expenses', 'surplus_deficit')]] for r in data['months']]]
    headers, rows = movement_table(data)
    return [headers, *rows, [], ['Opening Balance', data['summary']['opening_balance']], ['Period Money In', data['summary']['money_in']],
        ['Period Money Out', data['summary']['money_out']], ['Closing Balance', data['summary']['closing_balance']],
        ['Net Period Movement', data['summary']['net_movement']], [], ['Method', 'Net Amount'], *[[k, v] for k, v in data['method_totals'].items()]]


class FinancialReportNoteView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def post(self, request):
        if set(request.data) != {'start_date', 'end_date', 'body'}: raise ValidationError('Supply the period and note only.')
        start = serializers.DateField().run_validation(request.data.get('start_date'))
        end = serializers.DateField().run_validation(request.data.get('end_date'))
        if start > end: raise ValidationError('End date must follow start date.')
        body = serializers.CharField(max_length=10000, allow_blank=True).run_validation(request.data.get('body'))
        school = request.user.school_administrator.school
        record, _ = FinancialReportNote.objects.update_or_create(school=school, start_date=start, end_date=end, defaults={'body': body, 'updated_by': request.user})
        log_action(school=school, actor=request.user, action='financial_report_note_updated', resource=record)
        return Response(dict(body=record.body))
