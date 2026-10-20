"""Read-only reports over the original attendance and financial records."""
from collections import Counter
from decimal import Decimal
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AcademicYear, Term, Student, AttendanceRecord
from .permissions import IsSchoolAdministrator, IsParent
from .staff_access import IsAcademicStaff, staff_school


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
    permission_classes = [IsAcademicStaff]

    def get(self, request):
        school = staff_school(request.user)
        selected = filters(request, school)
        rows = AttendanceRecord.objects.filter(school=school, enrollment__student__school=school, enrollment__school_class__school=school).select_related('enrollment__student', 'enrollment__school_class', 'academic_year', 'term')
        if request.user.role == 'teacher':
            rows = rows.filter(enrollment__school_class__teacher_assignments__teacher=request.user.teacher_profile)
        for key, lookup in {'academic_year': 'academic_year_id', 'term': 'term_id', 'school_class': 'enrollment__school_class_id', 'student': 'enrollment__student_id', 'date_from': 'attendance_date__gte', 'date_to': 'attendance_date__lte'}.items():
            if key in selected:
                rows = rows.filter(**{lookup: selected[key]})
        if text := selected.get('search'):
            rows = rows.filter(Q(enrollment__student__first_name__icontains=text) | Q(enrollment__student__last_name__icontains=text) | Q(enrollment__student__admission_number__icontains=text))
        items = [dict(id=r.pk, student=r.enrollment.student_id, student_name=f'{r.enrollment.student.first_name} {r.enrollment.student.last_name}', admission_number=r.enrollment.student.admission_number, class_name=r.enrollment.school_class.name, academic_year=r.academic_year.name, term=r.term.name, date=r.attendance_date, status=r.status) for r in rows.order_by('-attendance_date', 'id')]
        counts = Counter(item['status'] for item in items)
        return Response({'records': items, 'summary': {key: counts[key] for key in ('present', 'absent', 'late', 'excused')}})


def account_statement(student, request):
    from .financial_reports import statement_events, charges_for, paid_as_of
    from .documents import branding
    school = student.school
    selected = filters(request, school)
    context = (Term.objects.get(pk=selected['term']) if selected.get('term') else
               AcademicYear.objects.get(pk=selected['academic_year']) if selected.get('academic_year') else None)
    start = selected.get('date_from') or (context.start_date if context else None)
    end = selected.get('date_to') or (context.end_date if context else None)
    if start and end and start > end:
        raise serializers.ValidationError('The selected statement period is empty.')
    events = statement_events(student)
    opening = Decimal(0)
    balance = Decimal(0)
    totals = {key: Decimal(0) for key in ('charges', 'payments', 'adjustments_reversals')}
    rows = []
    for row in events:
        delta = row['debit'] - row['credit']
        if end and row['date'] > end:
            continue
        if start and row['date'] < start:
            opening += delta
            balance += delta
            continue
        balance += delta
        totals['charges' if row['kind'] == 'charge' else 'payments' if row['kind'] == 'payment' else 'adjustments_reversals'] += row['credit'] if row['kind'] == 'payment' else delta
        row.pop('key')
        rows.append({**row, 'balance': balance})
    as_of = end or timezone.localdate()
    due_dates = [c.fee.due_date or c.assigned_on for c in charges_for(school, {}, student)
                 if c.assigned_on <= as_of and c.amount_owed + sum((e.amount for e in c.ledger_entries.all()
                     if e.entry_type == 'adjustment' and e.occurred_at.date() <= as_of), Decimal(0)) > paid_as_of(c, as_of)]
    return {'school': branding(school, request), 'due_date': min(due_dates) if due_dates and balance > 0 else None,
            'student': {'id': student.pk, 'name': f'{student.first_name} {student.last_name}', 'admission_number': student.admission_number, 'class_name': student.school_class.name},
            'currency': school.default_currency, 'generated_at': timezone.now(), 'filters': selected, 'period': {'start': start, 'end': end},
            'years': list(AcademicYear.objects.filter(school=school).values('id', 'name')),
            'terms': list(Term.objects.filter(academic_year__school=school).values('id', 'name', 'academic_year')),
            'transactions': rows, 'summary': {'opening_balance': opening, **totals, 'closing_balance': balance}}


class SchoolAccountStatementView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request, student_id):
        student = get_object_or_404(Student.objects.select_related('school', 'school_class'), pk=student_id, school=request.user.school_administrator.school)
        from .finance_documents import statement_response
        return statement_response(student, request)


class ParentAccountStatementView(APIView):
    permission_classes = [IsParent]

    def get(self, request, student_id):
        student = get_object_or_404(Student.objects.select_related('school', 'school_class'), pk=student_id, school=request.user.parent_profile.school, parent_links__parent=request.user.parent_profile)
        from .finance_documents import statement_response
        return statement_response(student, request)
