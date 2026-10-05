import json
from datetime import date
from unittest.mock import patch

from rest_framework.test import APITestCase

from . import tests as fixtures
from .models import AuditLog, Fee, RecurringFeeTemplate, StudentFeeAssignment, Payment, Receipt, FinancialLedgerEntry


class FeeDeletionTests(APITestCase):
    setUp = fixtures.TenantIsolationTests.setUp
    make_user = fixtures.TenantIsolationTests.make_user
    make_school_calendar = fixtures.TenantIsolationTests.make_school_calendar
    make_student = fixtures.TenantIsolationTests.make_student
    make_private_records = fixtures.TenantIsolationTests.make_private_records
    authenticate = fixtures.TenantIsolationTests.authenticate

    def fee(self, **kwargs):
        return Fee.objects.create(school=self.school_a, academic_year=self.year_a, term=self.term_a, name='Mistaken fee', amount='20.00', **kwargs)

    def template(self):
        return RecurringFeeTemplate.objects.create(school=self.school_a, academic_year=self.year_a, term=self.term_a, name='Mistaken template', amount='20.00', currency='USD', start_month=date(2026, 1, 1))

    def delete(self, record, user=None):
        self.authenticate(user or self.admin_a)
        resource = 'fees' if isinstance(record, Fee) else 'recurring-fees'
        return self.client.delete(f'/api/school/{resource}/{record.pk}/', {'school_id': self.school_a.pk}, format='json')

    def assert_blocked(self, record):
        counts = [m.objects.count() for m in (Fee, RecurringFeeTemplate, StudentFeeAssignment, Payment, Receipt, FinancialLedgerEntry, AuditLog)]
        response = self.delete(record)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data['code'], 'fee_has_financial_history' if isinstance(record, Fee) else 'recurring_fee_has_generated_charges')
        self.assertIn('Deactivate', response.data['detail'])
        self.assertEqual(counts, [m.objects.count() for m in (Fee, RecurringFeeTemplate, StudentFeeAssignment, Payment, Receipt, FinancialLedgerEntry, AuditLog)])

    def test_unused_fee_and_template_delete_with_audit(self):
        for record, action in [(self.fee(), 'finance_fee_deleted'), (self.template(), 'finance_recurring_fee_deleted')]:
            with self.subTest(action=action):
                pk = record.pk
                self.assertEqual(self.delete(record).status_code, 204)
                self.assertFalse(type(record).objects.filter(pk=pk).exists())
                audit = AuditLog.objects.get(action=action, resource_id=str(pk))
                self.assertEqual(audit.school, self.school_a)
                self.assertEqual(audit.actor, self.admin_a)
                self.assertEqual(audit.resource_type, type(record).__name__)
                metadata = json.loads(audit.description)
                self.assertEqual(metadata['name'], record.name)
                self.assertEqual(metadata['amount'], '20.00')
                self.assertEqual(metadata['academic_year'], self.year_a.pk)
                self.assertEqual(metadata['term'], self.term_a.pk)

    def test_cross_tenant_delete_returns_404_without_changes(self):
        for record in (self.fee(), self.template()):
            self.assertEqual(self.delete(record, self.admin_b).status_code, 404)
            self.assertTrue(type(record).objects.filter(pk=record.pk).exists())

    def test_unpaid_and_zero_value_assignments_are_charges_not_configuration(self):
        for amount in ['20.00', '0.00']:
            fee = self.fee()
            StudentFeeAssignment.objects.create(fee=fee, student=self.student_a, amount_owed=amount, assigned_on=date(2026, 1, 1))
            self.assert_blocked(fee)

    def test_payment_receipt_ledger_and_reversal_history_preserved(self):
        self.assert_blocked(self.assignment_a.fee)
        self.payment_a.is_reversed = True
        self.payment_a.save(update_fields=['is_reversed'])
        self.assert_blocked(self.assignment_a.fee)

    def test_ledger_charge_without_payment_blocks_delete(self):
        from .finance import assign_fee
        fee = self.fee()
        assignment, _ = assign_fee(student=self.student_a, fee=fee, amount_owed=fee.amount, assigned_on=date(2026, 1, 1))
        self.assertTrue(assignment.ledger_entries.exists())
        self.assertFalse(assignment.payments.exists())
        self.assert_blocked(fee)

    def test_generated_period_fee_and_its_template_are_retained(self):
        template = self.template()
        fee = self.fee(recurring_template=template, charge_month=date(2026, 1, 1))
        self.assert_blocked(fee)
        self.assert_blocked(template)
        self.assignment_a.fee = fee
        self.assignment_a.save(update_fields=['fee'])
        self.assert_blocked(template)

    def test_deactivation_is_independent_and_does_not_allow_deletion(self):
        fee = self.assignment_a.fee
        self.authenticate(self.admin_a)
        self.assertEqual(self.client.patch(f'/api/school/fees/{fee.pk}/', {'is_active': False}, format='json').status_code, 200)
        self.assert_blocked(fee)

    def test_audit_failure_rolls_back_deletion(self):
        from .fee_deletion import delete_unused_fee
        fee = self.fee()
        with patch('core.fee_deletion.log_action', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                delete_unused_fee(record=fee, school=self.school_a, actor=self.admin_a)
        self.assertTrue(Fee.objects.filter(pk=fee.pk).exists())

    def test_read_only_delete_eligibility_uses_server_relationships(self):
        self.authenticate(self.admin_a)
        fee = self.fee()
        self.assertTrue(self.client.get(f'/api/school/fees/{fee.pk}/').data['can_delete'])
        self.assertFalse(self.client.get(f'/api/school/fees/{self.assignment_a.fee_id}/').data['can_delete'])
        template = self.template()
        self.assertTrue(self.client.get(f'/api/school/recurring-fees/{template.pk}/').data['can_delete'])
        self.fee(recurring_template=template, charge_month=date(2026, 1, 1))
        self.assertFalse(self.client.get(f'/api/school/recurring-fees/{template.pk}/').data['can_delete'])
