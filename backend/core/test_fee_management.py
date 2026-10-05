from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from .finance import billing_periods, fee_plan, generate_fee_structure
from .models import AcademicYear, Term, RecurringFeeTemplate, StudentFeeAssignment, FinancialLedgerEntry
from . import tests as existing_tests


class BillingCalendarTests(SimpleTestCase):
    def test_calendar_boundaries(self):
        examples = [('2025-01-01', '2025-03-01', 2), ('2025-01-01', '2025-03-02', 3),
                    ('2025-01-15', '2025-03-14', 2), ('2025-01-15', '2025-03-15', 2),
                    ('2025-01-15', '2025-03-16', 3), ('2025-01-14', '2025-04-10', 3),
                    ('2025-05-13', '2025-08-07', 3), ('2025-09-09', '2025-12-04', 3),
                    ('2025-01-14', '2025-01-15', 1), ('2024-01-31', '2024-02-29', 1),
                    ('2025-01-31', '2025-03-31', 2), ('2025-12-15', '2026-01-16', 2)]
        for start, end, expected in examples:
            with self.subTest(start=start, end=end):
                template = SimpleNamespace(billing_method='MONTHLY', term=SimpleNamespace(start_date=date.fromisoformat(start), end_date=date.fromisoformat(end)))
                self.assertEqual(len(billing_periods(template)), expected)


class FeeManagementTests(APITestCase):
    setUp = existing_tests.TenantIsolationTests.setUp
    make_user = existing_tests.TenantIsolationTests.make_user
    make_school_calendar = existing_tests.TenantIsolationTests.make_school_calendar
    make_student = existing_tests.TenantIsolationTests.make_student
    make_private_records = existing_tests.TenantIsolationTests.make_private_records
    authenticate = existing_tests.TenantIsolationTests.authenticate

    def historical(self, method='MONTHLY'):
        year = AcademicYear.objects.create(school=self.school_a, name='2025', start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        term = Term.objects.create(academic_year=year, name='Term 1', sequence=1, start_date=date(2025, 1, 14), end_date=date(2025, 4, 10))
        self.enrollment_a.academic_year = year
        self.enrollment_a.enrolled_on = date(2025, 1, 1)
        self.enrollment_a.save()
        self.authenticate(self.admin_a)
        response = self.client.post('/api/school/recurring-fees/', {'name': 'School fees', 'amount': '75.00', 'academic_year': year.pk, 'term': term.pk, 'billing_method': method}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return RecurringFeeTemplate.objects.get(pk=response.data['id'])

    def test_historical_preview_generation_retry_and_ledger(self):
        template = self.historical()
        before = StudentFeeAssignment.objects.count()
        preview, _ = fee_plan(template)
        self.assertEqual(StudentFeeAssignment.objects.count(), before)
        self.assertEqual(preview['total_charges'], 3)
        self.assertEqual(preview['total_value'], '225.00')
        self.assertEqual(preview['amount_per_student'], '225.00')
        result = generate_fee_structure(template=template, preview_token=preview['preview_token'])
        self.assertEqual(result['assignments_created'], 3)
        self.assertEqual(FinancialLedgerEntry.objects.filter(fee_assignment__fee__recurring_template=template).count(), 3)
        preview, _ = fee_plan(template)
        self.assertEqual(generate_fee_structure(template=template, preview_token=preview['preview_token'])['assignments_created'], 0)

    def test_termly_and_one_off_are_single_obligations(self):
        for method in ['TERMLY', 'ONE_OFF']:
            with self.subTest(method=method):
                template = self.historical(method) if method == 'TERMLY' else RecurringFeeTemplate.objects.create(school=self.school_a, academic_year=self.enrollment_a.academic_year, term=Term.objects.get(academic_year=self.enrollment_a.academic_year), name='Trip', amount=20, currency='USD', billing_method=method, start_month=date(2025, 1, 14))
                preview, _ = fee_plan(template)
                self.assertEqual(preview['total_charges'], 1)
                self.assertEqual(generate_fee_structure(template=template, preview_token=preview['preview_token'])['assignments_created'], 1)

    def test_stale_preview_and_confirmation(self):
        template = self.historical()
        url = f'/api/school/recurring-fees/{template.pk}/'
        preview = self.client.get(url + 'preview/').data
        self.assertEqual(self.client.post(url + 'generate-charges/', {'preview_token': preview['preview_token']}, format='json').status_code, 400)
        self.enrollment_a.left_on = date(2025, 1, 1)
        self.enrollment_a.save()
        self.assertEqual(self.client.post(url + 'generate-charges/', {'confirm': True, 'preview_token': preview['preview_token']}, format='json').status_code, 400)
        self.assertFalse(template.generated_fees.exists())

    def test_scope_and_missing_enrollment(self):
        template = self.historical()
        self.enrollment_a.left_on = date(2025, 2, 13)
        self.enrollment_a.save()
        preview, _ = fee_plan(template)
        self.assertEqual(preview['total_charges'], 1)
        self.enrollment_a.academic_year = self.year_a
        self.enrollment_a.save()
        preview, _ = fee_plan(template)
        self.assertEqual(preview['total_charges'], 0)
        self.assertEqual([x['id'] for x in preview['missing_enrollments']], [self.student_a.pk])

    def test_tenant_validation_and_delete_deactivate(self):
        template = self.historical()
        url = f'/api/school/recurring-fees/{template.pk}/'
        for key, value in [('academic_year', self.year_b.pk), ('term', self.term_b.pk), ('school_class', self.class_b.pk), ('student', self.student_b.pk), ('school_id', self.school_b.pk), ('term', self.term_a.pk)]:
            with self.subTest(key=key):
                self.assertEqual(self.client.patch(url, {key: value}, format='json').status_code, 400)
        self.authenticate(self.admin_b)
        self.assertEqual(self.client.get(url + 'preview/').status_code, 404)
        self.assertEqual(self.client.post(url + 'generate-charges/', {'confirm': True}, format='json').status_code, 404)
        self.authenticate(self.admin_a)
        preview, _ = fee_plan(template)
        generate_fee_structure(template=template, preview_token=preview['preview_token'])
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertEqual(self.client.patch(url, {'amount': '99.00'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'is_active': False}, format='json').status_code, 200)
        self.assertEqual(template.generated_fees.count(), 3)

    def test_current_year_and_unused_deletion(self):
        self.authenticate(self.admin_a)
        for method in ['MONTHLY', 'TERMLY', 'ONE_OFF']:
            response = self.client.post('/api/school/recurring-fees/', {'name': method, 'amount': '75.00', 'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'billing_method': method}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(self.client.delete(f"/api/school/recurring-fees/{response.data['id']}/").status_code, 204)

    def test_historical_payment_preserves_date_and_original_receipt(self):
        self.authenticate(self.admin_a)
        result = self.client.post('/api/school/payments/', {'student_fee_assignment': self.assignment_a.pk, 'amount': '5.00', 'paid_at': '2025-02-15T10:00:00Z', 'method': 'cash', 'receipt_number': 'HIST-2025-001'}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['receipt_number'], 'HIST-2025-001')
        self.assertTrue(result.data['paid_at'].startswith('2025-02-15'))
