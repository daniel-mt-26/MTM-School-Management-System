from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from . import models as m
from .demo_seed import DEMO_EMAIL, DEMO_NAME, manifest_for, seed_demo
from .demo_verify import verify_demo
from .finance import student_totals
from .financial_reports import BUCKETS, ageing_report
from .reporting_api import account_statement
from .school_finance import financial_report, movement_report


class DemoSeedTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = TemporaryDirectory()
        cls.media_override = override_settings(MEDIA_ROOT=cls.media.name, STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        })
        cls.media_override.enable()
        try:
            super().setUpClass()
        except Exception:
            cls.media_override.disable(); cls.media.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable(); cls.media.cleanup()

    @classmethod
    def setUpTestData(cls):
        cls.school = m.School.objects.create(name=DEMO_NAME, email=DEMO_EMAIL, phone_number='+263000000001', is_demo=True)
        cls.day = date(2026, 10, 20)
        seeded = seed_demo(DEMO_NAME, confirmed=True, as_of=cls.day,
            passwords={'school_admin': 'Synthetic-admin-test-482!', 'parent': 'Synthetic-parent-test-482!', 'teacher': 'Synthetic-teacher-test-482!'})
        cls.actor = seeded.actor

    def obj(self, key):
        entry = manifest_for(self.school).response_body['objects'][key]
        from django.apps import apps
        return apps.get_model(entry['model']).objects.get(pk=entry['pk'])

    def test_refuses_missing_school_live_school_and_missing_confirmation(self):
        customer = m.School.objects.create(name='Beavers Junior School', email='customer@example.invalid', phone_number='0')
        for name, confirmed in [('Missing', True), (customer.name, True), (DEMO_NAME, False)]:
            with self.assertRaises(CommandError):
                seed_demo(name, confirmed=confirmed)
        self.assertFalse(customer.students.exists())
        self.assertEqual(self.school.students.count(), 60)

    def test_repeat_run_is_idempotent_and_keeps_credentials_and_calendar(self):
        before = manifest_for(self.school).response_body
        password = self.obj('user:teacher:0').password
        counts = (m.Payment.objects.count(), m.Receipt.objects.count(), m.AuditLog.objects.count(), m.AttendanceRecord.objects.count())
        again = seed_demo(DEMO_NAME, confirmed=True)
        self.assertEqual(again.day, self.day)
        self.assertEqual(again.credentials, [])
        self.assertEqual(manifest_for(self.school).response_body, before)
        self.assertEqual(self.obj('user:teacher:0').password, password)
        self.assertEqual(counts, (m.Payment.objects.count(), m.Receipt.objects.count(), m.AuditLog.objects.count(), m.AttendanceRecord.objects.count()))
        with self.assertRaises(CommandError):
            seed_demo(DEMO_NAME, confirmed=True, as_of=date(2026, 11, 1))

    def test_reset_first_preserves_other_schools_unowned_rows_and_configuration(self):
        other = m.School.objects.create(name='Customer school', email='other@example.invalid', phone_number='0')
        foreign_class = m.SchoolClass.objects.create(school=other, name='Private class')
        platform = m.User.objects.create_user(username='platform-keep', role='platform_admin', password='Synthetic-platform-test!')
        extra = m.InventoryCategory.objects.create(school=self.school, name='Operator-owned category')
        settings = self.obj('document-settings')
        settings.motto = 'Operator configured motto'; settings.save()
        before_ids = set(self.school.students.values_list('pk', flat=True))
        before_values = list(self.school.students.order_by('admission_number').values_list('admission_number', 'first_name', 'last_name'))
        before_summary = verify_demo(self.school)[1]
        seed_demo(DEMO_NAME, confirmed=True, reset=True)
        self.assertTrue(m.SchoolClass.objects.filter(pk=foreign_class.pk).exists())
        self.assertTrue(m.User.objects.get(pk=platform.pk).check_password('Synthetic-platform-test!'))
        self.assertTrue(m.InventoryCategory.objects.filter(pk=extra.pk).exists())
        settings.refresh_from_db(); self.assertEqual(settings.motto, 'Operator configured motto')
        self.assertFalse(before_ids & set(self.school.students.values_list('pk', flat=True)))
        self.assertEqual(before_values, list(self.school.students.order_by('admission_number').values_list('admission_number', 'first_name', 'last_name')))
        self.assertEqual(before_summary, verify_demo(self.school)[1])

    def test_reset_refuses_unowned_dependents_without_partial_deletion(self):
        manual = m.Homework.objects.create(school=self.school, school_class=self.obj('class:2'), title='Operator lesson',
            due_date=self.day, created_by=self.actor)
        ids = set(self.school.students.values_list('pk', flat=True))
        with self.assertRaisesMessage(CommandError, 'unowned'):
            seed_demo(DEMO_NAME, confirmed=True, reset=True)
        self.assertTrue(m.Homework.objects.filter(pk=manual.pk).exists())
        self.assertEqual(ids, set(self.school.students.values_list('pk', flat=True)))

    def test_reset_failure_rolls_back_and_keeps_original_fixture_files(self):
        original_manifest = manifest_for(self.school).response_body
        original_file = self.obj('resource:0').file
        original_files = {p for p in Path(self.media.name).rglob('*') if p.is_file()}
        with patch('core.demo_verify.verify_demo', side_effect=CommandError('forced failure')):
            with self.assertRaisesMessage(CommandError, 'forced failure'):
                seed_demo(DEMO_NAME, confirmed=True, reset=True)
        self.assertEqual(manifest_for(self.school).response_body, original_manifest)
        self.assertTrue(original_file.storage.exists(original_file.name))
        self.assertEqual(original_files, {p for p in Path(self.media.name).rglob('*') if p.is_file()})
        self.assertEqual(self.school.students.count(), 60)

    def test_foreign_manifest_reference_is_rejected(self):
        other = m.School.objects.create(name='Unrelated school', email='foreign@example.invalid', phone_number='0')
        foreign = m.InventoryCategory.objects.create(school=other, name='Private category')
        record = manifest_for(self.school)
        original_pk = record.response_body['objects']['stock-category:Stationery']['pk']
        record.response_body['objects']['stock-category:Stationery']['pk'] = foreign.pk
        record.save()
        with self.assertRaises(CommandError):
            seed_demo(DEMO_NAME, confirmed=True, reset=True)
        self.assertTrue(m.InventoryCategory.objects.filter(pk=foreign.pk).exists())
        record.response_body['objects']['stock-category:Stationery']['pk'] = original_pk
        record.save()
        foreign_class = m.SchoolClass.objects.create(school=other, name='Private class')
        # A valid link must not hide a foreign link in the same M2M collection.
        self.obj('timetable:0').classes.add(foreign_class)
        with self.assertRaisesMessage(CommandError, 'many-to-many'):
            verify_demo(self.school)

    def test_teacher_and_parent_relationships_and_portal_scope(self):
        teacher = self.obj('teacher:0')
        self.assertGreater(teacher.assignments.count(), 1)
        self.assertTrue(any(a.subjects.count() > 1 for a in teacher.assignments.all()))
        parent = self.obj('parent:0')
        self.assertEqual(parent.student_links.count(), 2)
        self.assertEqual(parent.student_links.values('student__school_class').distinct().count(), 2)
        self.assertEqual(self.obj('student:0').parent_links.count(), 2)
        self.assertEqual(self.obj('parent:30').user.email, '')
        client = APIClient()
        parent.user.must_change_password = False; parent.user.save()
        client.force_authenticate(parent.user)
        response = client.get('/api/parent/students/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        response = client.get('/api/parent/results/')
        self.assertEqual(response.status_code, 200)
        expected = m.AcademicResult.objects.filter(student_enrollment__student__parent_links__parent=parent, status='published').values_list('pk', flat=True)
        self.assertEqual({row['id'] for row in response.data}, set(expected))

    def test_username_collision_never_reassigns_a_platform_account(self):
        target = m.School.objects.create(name='Separate Demo', email='separate@example.invalid', phone_number='0', is_demo=True)
        user = m.User.objects.create_user(username=f'demo-{target.pk}-admin', role='platform_admin', password='Private-platform-482!')
        with self.assertRaises(CommandError):
            seed_demo(target.name, confirmed=True)
        user.refresh_from_db()
        self.assertEqual(user.role, 'platform_admin')
        self.assertTrue(user.check_password('Private-platform-482!'))
        self.assertFalse(target.students.exists())

    def test_attendance_has_real_months_codes_and_enrollment_context(self):
        rows = self.school.attendance_records.all()
        self.assertGreater(rows.count(), 3000)
        self.assertEqual(set(rows.values_list('status', flat=True)), {'present', 'absent', 'late', 'excused'})
        self.assertTrue(rows.filter(attendance_date__month=9).exists())
        self.assertTrue(rows.filter(attendance_date__month=10).exists())
        self.assertFalse(rows.filter(attendance_date__gt=self.day).exists())

    def test_results_comments_and_official_history(self):
        self.assertEqual(set(m.AcademicResult.objects.values_list('status', flat=True)), {'draft', 'submitted', 'approved', 'published'})
        publication = self.obj('publication:0:2025:3')
        self.assertEqual(len(publication.snapshot['results']), 6)
        self.assertTrue(publication.snapshot['comments'])
        self.assertTrue(all(row['grade'] for row in publication.snapshot['results']))
        self.assertTrue(self.obj('teacher:0').report_comments.exists())
        self.assertFalse(self.obj('card:0:2026:3').is_published)

    def test_payment_receipt_invoice_and_statement_reconcile(self):
        self.assertEqual(student_totals(self.obj('student:0'))[2], Decimal(0))
        self.assertEqual(student_totals(self.obj('student:1'))[2], Decimal(75))
        self.assertGreater(student_totals(self.obj('student:5'))[2], 0)
        invoice = self.obj('invoice:0')
        self.assertEqual(invoice.total, invoice.assignment.amount_owed)
        self.assertEqual(self.obj('invoice:1').assignment.payments.aggregate(n=Sum('amount'))['n'], Decimal(45))
        payment = self.obj('payment:0:tuition')
        self.assertEqual(payment.receipt.payment_id, payment.pk)
        self.assertEqual(payment.ledger_entry.amount, payment.amount)
        from types import SimpleNamespace
        statement = account_statement(self.obj('student:15'), SimpleNamespace(query_params={'date_from': '2026-10-01'}))
        self.assertGreater(statement['summary']['opening_balance'], 0)
        self.assertEqual(statement['summary']['closing_balance'], student_totals(self.obj('student:15'))[2])

    def test_ageing_is_calculated_from_real_due_dates(self):
        report = ageing_report(self.school, {'reporting_date': self.day})
        for key in BUCKETS:
            self.assertGreater(report['totals'][key], 0, key)

    def test_cashbook_income_expenses_and_monthly_annual_source_totals(self):
        book = movement_report(self.school, {}, date(2026, 1, 1), self.day, 'cash-books')
        self.assertEqual(len(book['rows']), len({r['id'] for r in book['rows']}))
        self.assertEqual({r['linked_type'] for r in book['rows']}, {'payment', 'manual_income', 'expense'})
        report = financial_report(self.school, {}, date(2026, 1, 1), self.day)
        for key in ('billed_fees', 'fees_collected', 'other_income', 'expenses', 'surplus_deficit'):
            self.assertEqual(sum((row[key] for row in report['months']), Decimal(0)), report['summary'][key])
        month = financial_report(self.school, {}, date(2026, 10, 1), self.day)
        for key in ('billed_fees', 'fees_collected', 'other_income', 'expenses', 'outstanding_receivables'):
            self.assertGreater(month['summary'][key], 0, key)

    def test_inventory_resources_and_audit_are_real(self):
        variant = self.obj('variant:0:0')
        moves = list(variant.stock_movements.all())
        self.assertEqual(sum(row.quantity if row.direction == 'in' else -row.quantity for row in moves), 62)
        resource = self.obj('resource:0')
        with resource.file.open('rb') as content:
            self.assertTrue(content.read().startswith(b'%PDF-'))
        actions = set(m.AuditLog.objects.filter(school=self.school).values_list('action', flat=True))
        self.assertTrue({'demo_seed_teacher_created', 'demo_seed_assignment_created', 'demo_seed_payment_recorded', 'demo_seed_inventory_populated'}.issubset(actions))

    def test_seeding_never_sends_messages_or_creates_reset_tokens(self):
        self.assertEqual(m.CommunicationMessage.objects.filter(school=self.school).count(), 0)
        self.assertEqual(m.PasswordRecovery.objects.count(), 0)
        with patch('core.communications.create_payment_receipt_messages') as notify:
            seed_demo(DEMO_NAME, confirmed=True)
            notify.assert_not_called()

    def test_verify_command_is_read_only_and_detects_damage(self):
        output = StringIO()
        before = m.AuditLog.objects.count()
        call_command('verify_demo_school', school=DEMO_NAME, stdout=output)
        self.assertIn('Demo integrity verified', output.getvalue())
        self.assertEqual(before, m.AuditLog.objects.count())
        m.Receipt.objects.filter(pk=self.obj('receipt:payment:0:tuition').pk).delete()
        with self.assertRaises(CommandError):
            call_command('verify_demo_school', school=DEMO_NAME, stdout=StringIO())

    def test_command_output_has_counts_and_usernames_but_no_supplied_passwords(self):
        output = StringIO()
        call_command('seed_demo_school', school=DEMO_NAME, yes=True, stdout=output)
        text = output.getvalue()
        self.assertIn('Students: 60', text)
        self.assertIn('sunrise-teacher-01', text)
        self.assertIn('demo.parent', text)
        self.assertNotIn('Synthetic-admin-test', text)
        self.assertNotIn('Generated temporary demo password', text)

    def test_bootstrap_refuses_a_live_sunrise_identifier(self):
        self.school.is_demo = False; self.school.save()
        with self.assertRaises(CommandError):
            call_command('create_demo_school', stdout=StringIO())
        self.school.refresh_from_db(); self.assertFalse(self.school.is_demo)
