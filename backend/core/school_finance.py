"""Cash-basis school reports projected from canonical records, never copied ledgers."""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from .finance import assignment_period
from .financial_reports import ZERO, ageing_report
from .models import (AcademicYear, Term, SchoolClass, Student, Payment, Expense, ManualIncome,
                     FinanceAccount, FinanceCategory, StudentFeeAssignment, FinancialReportNote)


SORT_FIELDS = ('date', 'reference', 'source', 'category', 'description', 'payment_method', 'account_name',
               'amount', 'money_in', 'money_out', 'balance', 'student_name', 'receipt_number', 'received_by')


class SchoolFinanceFilters(serializers.Serializer):
    period = serializers.ChoiceField(choices=['daily', 'monthly', 'annual', 'academic', 'custom'], required=False, default='monthly')
    date = serializers.DateField(required=False)
    year = serializers.IntegerField(min_value=1900, max_value=2200, required=False)
    month = serializers.IntegerField(min_value=1, max_value=12, required=False)
    academic_year = serializers.IntegerField(min_value=1, required=False)
    term = serializers.IntegerField(min_value=1, required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    account = serializers.CharField(required=False)
    category = serializers.CharField(required=False)
    payment_method = serializers.CharField(max_length=30, required=False)
    transaction_type = serializers.ChoiceField(choices=['income', 'expense', 'reversal', 'money_in', 'money_out'], required=False)
    student = serializers.IntegerField(min_value=1, required=False)
    school_class = serializers.IntegerField(min_value=1, required=False)
    search = serializers.CharField(max_length=150, required=False, allow_blank=True)
    sort = serializers.ChoiceField(choices=[p + k for p in ('', '-') for k in SORT_FIELDS], required=False, default='date')
    export = serializers.ChoiceField(choices=['json', 'pdf', 'xlsx'], required=False, default='json')


def report_period(request, school, report):
    serializer = SchoolFinanceFilters(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    selected = serializer.validated_data
    if report in ('monthly', 'annual'):
        selected['period'] = report
    context = None
    if selected.get('academic_year'):
        context = get_object_or_404(AcademicYear, school=school, pk=selected['academic_year'])
    if selected.get('term'):
        term = get_object_or_404(Term, academic_year__school=school, pk=selected['term'])
        if context and term.academic_year_id != context.pk:
            raise serializers.ValidationError({'term': 'Choose a term in the selected academic year.'})
        if selected['period'] == 'annual':
            raise serializers.ValidationError({'term': 'Annual reports use a whole year.'})
        context = term
    today = timezone.localdate()
    year = selected.get('year', context.start_date.year if context else today.year)
    month = selected.get('month', today.month)
    mode = selected['period']
    if mode == 'daily':
        start = end = selected.get('date', today)
    elif mode == 'monthly':
        start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    elif mode == 'annual':
        start, end = (context.start_date, context.end_date) if context else (date(year, 1, 1), date(year, 12, 31))
    elif mode == 'academic':
        if context is None:
            raise serializers.ValidationError('Choose an academic year or term.')
        start, end = context.start_date, context.end_date
    else:
        if not selected.get('start_date') or not selected.get('end_date'):
            raise serializers.ValidationError('Custom periods require start and end dates.')
        start, end = selected['start_date'], selected['end_date']
    if context:
        start, end = max(start, context.start_date), min(end, context.end_date)
    if start > end:
        raise serializers.ValidationError('The selected reporting period is empty or reversed.')
    for key, model, lookup in [('account', FinanceAccount, 'school'), ('student', Student, 'school'), ('school_class', SchoolClass, 'school')]:
        if selected.get(key) and selected[key] != 'unassigned':
            pk = serializers.IntegerField(min_value=1).run_validation(selected[key])
            get_object_or_404(model, pk=pk, **{lookup: school})
            if key == 'account': selected[key] = str(pk)
    if category := selected.get('category'):
        if category.startswith('configured:'):
            pk = serializers.IntegerField(min_value=1).run_validation(category.split(':', 1)[1])
            get_object_or_404(FinanceCategory, pk=pk, school=school)
        elif category not in {'income:fees', 'income:other', *['expense:' + value for value, _ in Expense.Category.choices]}:
            raise serializers.ValidationError({'category': 'Choose a category from this school.'})
    if report in ('monthly', 'annual', 'dashboard') and any(selected.get(k) for k in ('account', 'category', 'payment_method', 'transaction_type', 'student', 'school_class', 'search')):
        raise serializers.ValidationError('School financial summaries support reporting-period filters. Use cashbook/income reports for transaction filters.')
    return selected, start, end


def category_info(category, fallback_key, fallback_label):
    return (f'configured:{category.pk}', category.name) if category else (fallback_key, fallback_label)


def cash_events(school, as_of):
    """One event per original record plus, if needed, one dated correction.

    Original receipts remain visible in their original periods. Reversals offset
    them on the actual correction date, so monthly totals aggregate annually.
    """
    events = []
    def add(obj, source_type, day, effect, category, source, description, method, account, financial_kind,
            student=None, receipt=None, class_name='', correction=False, status='Valid'):
        events.append(dict(id=f'{source_type}:{obj.pk}' + (':reversal' if correction else ''), date=day,
            reference=obj.reference or (receipt.receipt_number if receipt else f'{source_type.upper()}-{obj.pk}'),
            source=source, category_key=category[0], category=category[1], description=description,
            money_in=max(effect, ZERO), money_out=max(-effect, ZERO), amount=effect,
            payment_method=method, account=account.pk if account else None, account_name=account.name if account else 'Unassigned (historical / unspecified)',
            student=student.pk if student else None, student_name=f'{student.first_name} {student.last_name}' if student else '',
            admission_number=student.admission_number if student else '', class_name=class_name,
            receipt_number=receipt.receipt_number if receipt else '', receipt=receipt.pk if receipt else None,
            received_by=obj.recorded_by.get_full_name() or obj.recorded_by.username,
            linked_type=source_type, linked_id=obj.pk, correction=correction, status=status,
            financial_kind=financial_kind, _order=(source_type, obj.pk, int(correction))))

    payments = Payment.objects.filter(student_fee_assignment__student__school=school, student_fee_assignment__fee__school=school,
        paid_at__date__lte=as_of).select_related('student_fee_assignment__student', 'student_fee_assignment__fee__recurring_template__term',
            'account', 'income_category', 'recorded_by', 'receipt').prefetch_related('student_fee_assignment__student__enrollments__school_class')
    for payment in payments:
        charge = payment.student_fee_assignment
        start, end = assignment_period(charge)
        enrollments = [e for e in charge.student.enrollments.all() if e.academic_year_id == charge.fee.academic_year_id and e.school_class.school_id == school.pk and e.enrolled_on < end and (not e.left_on or e.left_on >= start)]
        classes = ', '.join(dict.fromkeys(e.school_class.name for e in enrollments))
        receipt = payment.receipt if hasattr(payment, 'receipt') else None
        category = category_info(payment.income_category, 'income:fees', 'School Fee Payments')
        reversal_day = payment.reversed_at.date() if payment.reversed_at else payment.paid_at.date()
        status = 'Reversed' if payment.is_reversed and reversal_day <= as_of else 'Valid'
        common = dict(obj=payment, source_type='payment', category=category, source='Student payment',
            method=payment.method, account=payment.account, financial_kind='fees', student=charge.student, receipt=receipt, class_name=classes)
        add(day=payment.paid_at.date(), effect=payment.amount, description=charge.fee.name, status=status, **common)
        events[-1]['historical_class_ids'] = [e.school_class_id for e in enrollments]
        if payment.is_reversed and reversal_day <= as_of:
            add(day=reversal_day, effect=-payment.amount, description='Payment reversal: ' + payment.reversal_reason, correction=True, status='Correction', **common)
            events[-1]['historical_class_ids'] = [e.school_class_id for e in enrollments]
    for model, source_type, date_field in [(ManualIncome, 'manual_income', 'income_date'), (Expense, 'expense', 'expense_date')]:
        categories = 'category' if model == ManualIncome else 'finance_category'
        records = model.objects.filter(school=school, **{date_field + '__lte': as_of}).select_related('account', categories, 'recorded_by')
        for record in records:
            is_expense = model == Expense
            category = category_info(getattr(record, categories), 'expense:' + record.category if is_expense else 'income:other', record.get_category_display() if is_expense else 'Other Income')
            effect = -record.amount if is_expense else record.amount
            day = getattr(record, date_field)
            reversal_day = record.reversed_at.date() if record.reversed_at else day
            common = dict(obj=record, source_type=source_type, category=category, source=record.payee or 'Operating expense' if is_expense else record.source,
                method=record.payment_method, account=record.account, financial_kind='expenses' if is_expense else 'other_income')
            add(day=day, effect=effect, description=record.description, status='Reversed' if record.is_reversed and reversal_day <= as_of else 'Valid', **common)
            if record.is_reversed and reversal_day <= as_of:
                add(day=reversal_day, effect=-effect, description='Reversal: ' + record.reversal_reason, correction=True, status='Correction', **common)
    return sorted(events, key=lambda r: (r['date'], r['_order']))


def matches(row, selected):
    if selected.get('account') and (str(row['account']) if row['account'] else 'unassigned') != selected['account']: return False
    if selected.get('category') and row['category_key'] != selected['category']: return False
    if selected.get('payment_method') and row['payment_method'] != selected['payment_method']: return False
    if selected.get('student') and row['student'] != selected['student']: return False
    if selected.get('school_class') and selected['school_class'] not in row.get('historical_class_ids', []): return False
    kind = selected.get('transaction_type')
    if kind == 'income' and (row['financial_kind'] == 'expenses' or row['correction']): return False
    if kind == 'expense' and (row['financial_kind'] != 'expenses' or row['correction']): return False
    if kind == 'reversal' and not row['correction']: return False
    if kind == 'money_in' and not row['money_in']: return False
    if kind == 'money_out' and not row['money_out']: return False
    if selected.get('search') and selected['search'].casefold() not in ' '.join(str(row[k]) for k in ('reference', 'source', 'category', 'description', 'student_name', 'admission_number', 'receipt_number', 'account_name')).casefold(): return False
    return True


def movement_report(school, selected, start, end, report):
    events = cash_events(school, end)
    if report in ('income', 'cash-received'):
        events = [r for r in events if r['financial_kind'] in ('fees', 'other_income')]
    elif report == 'expense-report':
        events = [r for r in events if r['financial_kind'] == 'expenses']
    events = [r for r in events if matches(r, selected)]
    opening = sum((r['amount'] for r in events if r['date'] < start), ZERO)
    rows, balance = [], opening
    for row in events:
        if row['date'] < start: continue
        balance += row['amount']
        rows.append({k: v for k, v in row.items() if k != '_order'} | {'balance': balance})
    money_in, money_out = (sum((r[k] for r in rows), ZERO) for k in ('money_in', 'money_out'))
    methods = {}
    for row in rows:
        methods[row['payment_method']] = methods.get(row['payment_method'], ZERO) + row['amount']
    sort = selected.get('sort', 'date')
    rows.sort(key=lambda r: r[sort.lstrip('-')].casefold() if isinstance(r[sort.lstrip('-')], str) else r[sort.lstrip('-')], reverse=sort.startswith('-'))
    return dict(rows=rows, summary=dict(opening_balance=opening, money_in=money_in, money_out=money_out,
        closing_balance=opening + money_in - money_out, net_movement=money_in - money_out), method_totals=methods,
        note='Cash is projected once from original payments, other-income records and expenses. Corrections offset originals on their reversal dates. Opening/closing balances cover recorded history with the same transaction filters; they are not reconciled bank balances. Running balances retain chronological order even when displayed rows are sorted.')


def period_summary(events, charges, start, end):
    selected = [r for r in events if start <= r['date'] <= end]
    fees = sum((r['amount'] for r in selected if r['financial_kind'] == 'fees'), ZERO)
    other = sum((r['amount'] for r in selected if r['financial_kind'] == 'other_income'), ZERO)
    expenses = -sum((r['amount'] for r in selected if r['financial_kind'] == 'expenses'), ZERO)
    billed = sum((c.amount_owed for c in charges if start <= c.assigned_on <= end), ZERO)
    return dict(billed_fees=billed, fees_collected=fees, cash_collected=fees, other_income=other,
                total_cash_income=fees + other, expenses=expenses, surplus_deficit=fees + other - expenses)


def financial_report(school, selected, start, end):
    events = cash_events(school, end)
    charges = list(StudentFeeAssignment.objects.filter(student__school=school, fee__school=school, assigned_on__lte=end))
    summary = period_summary(events, charges, start, end)
    summary['outstanding_receivables'] = ageing_report(school, {'reporting_date': end})['totals']['outstanding']
    categories = {}
    for row in events:
        if not start <= row['date'] <= end: continue
        section = 'expenditure' if row['financial_kind'] == 'expenses' else 'income'
        key = (section, row['category_key'])
        target = categories.setdefault(key, dict(section=section, category=row['category'], category_key=row['category_key'], actual=ZERO))
        target['actual'] += -row['amount'] if section == 'expenditure' else row['amount']
    months, cursor = [], start.replace(day=1)
    while cursor <= end:
        last = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        months.append(dict(month=cursor.strftime('%Y-%m'), **period_summary(events, charges, max(start, cursor), min(end, last))))
        cursor = date(cursor.year + int(cursor.month == 12), cursor.month % 12 + 1, 1)
    note = FinancialReportNote.objects.filter(school=school, start_date=start, end_date=end).first()
    return dict(summary=summary, categories=sorted(categories.values(), key=lambda r: (r['section'], r['category'].casefold())),
        months=months, budget_configured=False, notes=note.body if note else '',
        note='Cash-basis management report. Billed fees use assignment dates; collections use actual payment dates; expenses use expense dates. Reversals affect their correction dates. Receivables are the outstanding snapshot at the end of the reporting period, including earlier unpaid obligations. Budget and variance columns are omitted because no budget is configured.')
