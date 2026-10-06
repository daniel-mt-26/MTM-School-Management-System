from datetime import date, datetime, timezone
from decimal import Decimal
from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import AttendanceRecord, SchoolClass, Timetable, FinancialLedgerEntry, Payment, StudentFeeAssignment
from .finance import reverse_payment


class UsabilityTests(APITestCase):
    setUp = fixtures.TenantIsolationTests.setUp
    make_user = fixtures.TenantIsolationTests.make_user
    make_school_calendar = fixtures.TenantIsolationTests.make_school_calendar
    make_student = fixtures.TenantIsolationTests.make_student
    make_private_records = fixtures.TenantIsolationTests.make_private_records
    authenticate = fixtures.TenantIsolationTests.authenticate

    def test_attendance_history_uses_enrollment_and_scopes_filters(self):
        for school, enrollment, year, term, actor in [(self.school_a, self.enrollment_a, self.year_a, self.term_a, self.admin_a), (self.school_b, self.enrollment_b, self.year_b, self.term_b, self.admin_b)]:
            for day, status in [(12, 'absent'), (13, 'late')]:
                AttendanceRecord.objects.create(school=school, enrollment=enrollment, academic_year=year, term=term, recorded_by=actor, attendance_date=date(2026, 1, day), status=status)
        self.student_a.school_class = SchoolClass.objects.create(school=self.school_a, name='New class')
        self.student_a.save()
        self.authenticate(self.admin_a)
        url = '/api/school/attendance/history/'
        data = self.client.get(url, {'school_class': self.class_a.pk, 'academic_year': self.year_a.pk, 'student': self.student_a.pk, 'date_from': '2026-01-12', 'date_to': '2026-01-12'}).data
        self.assertEqual(len(data['records']), 1)
        self.assertEqual(data['records'][0]['class_name'], self.class_a.name)
        self.assertEqual(data['summary']['absent'], 1)
        self.assertEqual(self.client.get(url, {'student': self.student_b.pk}).data['records'], [])
        self.assertEqual(self.client.get(url, {'academic_year': self.year_b.pk}).status_code, 404)
        self.assertEqual(self.client.get(url, {'date_from': 'bad'}).status_code, 400)
        self.assertEqual(AttendanceRecord.objects.count(), 4)

    def plan(self, scope, classes):
        return {'name': 'Schedule', 'scope': scope, 'classes': classes, 'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'entries': [{'day_of_week': 'Monday', 'start_time': '08:00', 'end_time': '08:30', 'label': 'Break'}]}

    def test_whole_school_is_dynamic_and_conflicts_in_both_directions(self):
        self.authenticate(self.admin_a)
        url = '/api/school/timetable-plans/'
        result = self.client.post(url, self.plan('WHOLE_SCHOOL', []), format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertFalse(Timetable.objects.get(pk=result.data['id']).classes.exists())
        new = SchoolClass.objects.create(school=self.school_a, name='Later class')
        self.assertIn(new.name, self.client.get(url).data[0]['class_names'])
        self.assertEqual(len(self.client.get('/api/school/timetables/', {'school_class': new.pk}).data), 1)
        self.assertEqual(self.client.post(url, self.plan('SINGLE', [new.pk]), format='json').status_code, 400)
        self.client.delete(f"{url}{result.data['id']}/")
        self.assertEqual(self.client.post(url, self.plan('SINGLE', [new.pk]), format='json').status_code, 201)
        self.assertEqual(self.client.post(url, self.plan('WHOLE_SCHOOL', []), format='json').status_code, 400)
        self.assertEqual(self.client.post(url, self.plan('SINGLE', [self.class_a.pk, new.pk]), format='json').status_code, 400)
        self.assertEqual(self.client.post(url, self.plan('WHOLE_SCHOOL', [self.class_b.pk]), format='json').status_code, 400)

    def test_fee_methods_accept_visible_fields_and_cents(self):
        self.authenticate(self.admin_a)
        for method in ('MONTHLY', 'TERMLY', 'ONE_OFF'):
            response = self.client.post('/api/school/recurring-fees/', {'name': method, 'billing_method': method, 'amount': '75.50', 'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'school_class': None, 'student': None}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['amount'], '75.50')
            self.assertEqual(response.data['currency'], 'USD')
        response = self.client.post('/api/school/recurring-fees/', {'name': 'Missing', 'billing_method': 'MONTHLY', 'amount': '75.50'}, format='json')
        self.assertEqual(set(response.data), {'academic_year', 'term'})

    def test_generated_charge_class_filter_uses_period_enrollment(self):
        from .models import RecurringFeeTemplate
        from .finance import fee_plan, generate_fee_structure
        from .serializers import StudentFeeAssignmentSerializer
        template = RecurringFeeTemplate.objects.create(school=self.school_a, academic_year=self.year_a, term=self.term_a, name='Monthly', billing_method='MONTHLY', amount=75, currency='USD', start_month=self.term_a.start_date, end_month=self.term_a.end_date)
        plan, _ = fee_plan(template)
        generate_fee_structure(template=template, preview_token=plan['preview_token'])
        charge = StudentFeeAssignment.objects.filter(fee__recurring_template=template).order_by('assigned_on').first()
        self.assertLess(charge.assigned_on, self.enrollment_a.enrolled_on)
        data = StudentFeeAssignmentSerializer(charge, context={'school': self.school_a}).data
        self.assertIn(self.class_a.pk, data['historical_class_ids'])

    def statement(self, user=None, parent=False, **params):
        self.authenticate(user or self.admin_a)
        path = f'/api/parent/students/{self.student_a.pk}/statement/' if parent else f'/api/school/finance/students/{self.student_a.pk}/statement/'
        return self.client.get(path, params)

    def test_statement_totals_references_and_no_financial_mutations(self):
        before = (StudentFeeAssignment.objects.count(), Payment.objects.count(), FinancialLedgerEntry.objects.count())
        result = self.statement()
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['summary']['closing_balance'], Decimal('75.00'))
        charge, payment = result.data['transactions']
        self.assertEqual(charge['debit'], Decimal('100'))
        self.assertEqual(charge['balance'], Decimal('100'))
        self.assertEqual(payment['credit'], Decimal('25'))
        self.assertEqual(payment['reference'], 'R-A-001')
        self.assertIsNone(result.data['school']['logo'])
        self.assertEqual(before, (StudentFeeAssignment.objects.count(), Payment.objects.count(), FinancialLedgerEntry.objects.count()))

    def test_statement_authorization_and_read_only_parent(self):
        self.assertEqual(self.statement(self.parent_a_user, parent=True).status_code, 200)
        self.assertEqual(self.statement(self.parent_b_user, parent=True).status_code, 404)
        self.assertEqual(self.statement(self.admin_b).status_code, 404)
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.post(f'/api/parent/students/{self.student_a.pk}/statement/', {}, format='json').status_code, 405)

    def test_statement_reversal_opening_and_period_filters(self):
        self.payment_a.paid_at = datetime(2026, 1, 20, tzinfo=timezone.utc)
        self.payment_a.save()
        reverse_payment(payment_id=self.payment_a.pk, reversed_by=self.admin_a, reason='Correction')
        data = self.statement(date_from='2026-02-01', academic_year=self.year_a.pk, term=self.term_a.pk).data
        self.assertEqual(data['summary']['opening_balance'], Decimal('75'))
        self.assertEqual(data['summary']['closing_balance'], Decimal('100'))
        self.assertEqual(data['summary']['adjustments_reversals'], Decimal('25'))
        self.assertEqual(len(data['transactions']), 1)
        self.assertIn('Correction', data['transactions'][0]['description'])
        self.assertEqual(self.statement(date_to='2026-01-15').data['summary']['closing_balance'], Decimal('100'))
        self.assertEqual(self.statement(term=self.term_b.pk).status_code, 404)

    def test_statement_letterhead_and_adjustments(self):
        self.school_a.address = '1 School Road'
        self.school_a.logo = 'school_logos/test.png'
        self.school_a.save()
        FinancialLedgerEntry.objects.create(student=self.student_a, entry_type='adjustment', amount=Decimal('5'), currency='USD', occurred_at=datetime(2026, 1, 21, tzinfo=timezone.utc), description='Adjustment')
        data = self.statement().data
        self.assertEqual(data['school']['address'], '1 School Road')
        self.assertIn('test.png', data['school']['logo'])
        self.assertEqual(data['summary']['closing_balance'], Decimal('80'))
