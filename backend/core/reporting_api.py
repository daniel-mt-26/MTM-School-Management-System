"""Read-only reports over the original attendance and financial records."""
from collections import Counter
from decimal import Decimal
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AcademicYear, Term, Student, AttendanceRecord, StudentFeeAssignment, Payment, FinancialLedgerEntry
from .permissions import IsSchoolAdministrator, IsParent


class ReportFilters(serializers.Serializer):
    academic_year = serializers.IntegerField(required=False)
    term = serializers.IntegerField(required=False)
    school_class = serializers.IntegerField(required=False)
    student = serializers.IntegerField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get('date_from') and attrs.get('date_to') and attrs['date_from'] > attrs['date_to']:
            raise serializers.ValidationError({'date_to': 'End date must follow start date.'})
        return attrs


def filters(request, school):
    serializer = ReportFilters(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if data.get('academic_year'):
        get_object_or_404(AcademicYear, pk=data['academic_year'], school=school)
    if data.get('term'):
        term = get_object_or_404(Term, pk=data['term'], academic_year__school=school)
        if data.get('academic_year') and term.academic_year_id != data['academic_year']:
            raise serializers.ValidationError({'term': 'Choose a term in the selected year.'})
    return data


class AttendanceHistoryView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request):
        school = request.user.school_administrator.school
        selected = filters(request, school)
        rows = AttendanceRecord.objects.filter(school=school, enrollment__student__school=school, enrollment__school_class__school=school).select_related('enrollment__student', 'enrollment__school_class', 'academic_year', 'term')
        for key, lookup in {'academic_year': 'academic_year_id', 'term': 'term_id', 'school_class': 'enrollment__school_class_id', 'student': 'enrollment__student_id', 'date_from': 'attendance_date__gte', 'date_to': 'attendance_date__lte'}.items():
            if key in selected:
                rows = rows.filter(**{lookup: selected[key]})
        if text := selected.get('search'):
            rows = rows.filter(Q(enrollment__student__first_name__icontains=text) | Q(enrollment__student__last_name__icontains=text) | Q(enrollment__student__admission_number__icontains=text))
        items = [dict(id=r.pk, student=r.enrollment.student_id, student_name=f'{r.enrollment.student.first_name} {r.enrollment.student.last_name}', admission_number=r.enrollment.student.admission_number, class_name=r.enrollment.school_class.name, academic_year=r.academic_year.name, term=r.term.name, date=r.attendance_date, status=r.status) for r in rows.order_by('-attendance_date', 'id')]
        counts = Counter(item['status'] for item in items)
        return Response({'records': items, 'summary': {key: counts[key] for key in ('present', 'absent', 'late', 'excused')}})


def account_statement(student, request):
    school = student.school
    selected = filters(request, school)
    charges = StudentFeeAssignment.objects.filter(student=student, fee__school=school).select_related('fee')
    for key in ('academic_year', 'term'):
        if key in selected:
            charges = charges.filter(**{'fee__' + key + '_id': selected[key]})
    events = []
    def add(date, key, reference, description, debit, credit, kind):
        events.append(dict(date=date, key=key, reference=reference, description=description, debit=debit, credit=credit, kind=kind))
    for charge in charges:
        add(charge.assigned_on, (0, charge.pk), f'FEE-{charge.fee_id}', charge.fee.name, charge.amount_owed, Decimal(0), 'charge')
    for payment in Payment.objects.filter(student_fee_assignment__in=charges).select_related('receipt', 'student_fee_assignment__fee'):
        reference = payment.receipt.receipt_number if hasattr(payment, 'receipt') else payment.reference or f'PAY-{payment.pk}'
        add(payment.paid_at.date(), (1, payment.pk), reference, 'Payment: ' + payment.student_fee_assignment.fee.name, Decimal(0), payment.amount, 'payment')
        if payment.is_reversed and payment.reversed_at:
            add(payment.reversed_at.date(), (2, payment.pk), reference, 'Payment reversal: ' + payment.reversal_reason, payment.amount, Decimal(0), 'reversal')
    # Charge/payment ledger entries mirror the obligations above. Include only
    # independent adjustments, avoiding duplicate charges or reversal entries.
    adjustments = FinancialLedgerEntry.objects.filter(student=student, entry_type='adjustment')
    if selected.get('academic_year') or selected.get('term'):
        adjustments = adjustments.filter(fee_assignment__in=charges)
    for entry in adjustments:
        add(entry.occurred_at.date(), (3, entry.pk), f'ADJ-{entry.pk}', entry.description, max(entry.amount, Decimal(0)), max(-entry.amount, Decimal(0)), 'adjustment')
    events.sort(key=lambda row: (row['date'], row['key']))
    opening = Decimal(0)
    balance = Decimal(0)
    totals = {key: Decimal(0) for key in ('charges', 'payments', 'adjustments_reversals')}
    rows = []
    for row in events:
        delta = row['debit'] - row['credit']
        if selected.get('date_to') and row['date'] > selected['date_to']:
            continue
        if selected.get('date_from') and row['date'] < selected['date_from']:
            opening += delta
            balance += delta
            continue
        balance += delta
        totals['charges' if row['kind'] == 'charge' else 'payments' if row['kind'] == 'payment' else 'adjustments_reversals'] += row['credit'] if row['kind'] == 'payment' else delta
        row.pop('key')
        rows.append({**row, 'balance': balance})
    return {'school': {'name': school.name, 'logo': request.build_absolute_uri(school.logo.url) if school.logo else None, 'address': school.address, 'phone': school.phone_number, 'email': school.email},
            'student': {'id': student.pk, 'name': f'{student.first_name} {student.last_name}', 'admission_number': student.admission_number, 'class_name': student.school_class.name},
            'currency': school.default_currency, 'generated_at': timezone.now(), 'filters': selected,
            'years': list(AcademicYear.objects.filter(school=school).values('id', 'name')),
            'terms': list(Term.objects.filter(academic_year__school=school).values('id', 'name', 'academic_year')),
            'transactions': rows, 'summary': {'opening_balance': opening, **totals, 'closing_balance': balance}}


class SchoolAccountStatementView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request, student_id):
        student = get_object_or_404(Student.objects.select_related('school', 'school_class'), pk=student_id, school=request.user.school_administrator.school)
        return Response(account_statement(student, request))


class ParentAccountStatementView(APIView):
    permission_classes = [IsParent]

    def get(self, request, student_id):
        student = get_object_or_404(Student.objects.select_related('school', 'school_class'), pk=student_id, parent_links__parent=request.user.parent_profile)
        return Response(account_statement(student, request))
