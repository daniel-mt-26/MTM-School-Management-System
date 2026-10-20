from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import connections, IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import (Fee, StudentFeeAssignment, Payment, FinancialLedgerEntry, StudentInvoice, SchoolInvoiceSequence,
    SchoolDocumentSettings, ReportCardPublication, AcademicResult, ReportCard, StudentEnrollment, AcademicYear, Term,
    Teacher, TeacherAssignment, Subject, ClassSubject, User, AuditLog, ParentStudent)
from .finance_documents import generate_invoice
from .finance import record_payment
from .financial_reports import BUCKETS


class DocumentFixtures:
    setUp = fixtures.TenantIsolationTests.setUp
    make_user = fixtures.TenantIsolationTests.make_user
    make_school_calendar = fixtures.TenantIsolationTests.make_school_calendar
    make_student = fixtures.TenantIsolationTests.make_student
    make_private_records = fixtures.TenantIsolationTests.make_private_records
    authenticate = fixtures.TenantIsolationTests.authenticate


class StudentDocumentTests(DocumentFixtures, APITestCase):
    def invoice(self, assignment=None, user=None):
        self.authenticate(user or self.admin_a)
        return self.client.post('/api/school/finance/invoices/', {'assignment': (assignment or self.assignment_a).pk}, format='json')

    def report(self, **params):
        self.authenticate(self.admin_a)
        return self.client.get('/api/school/finance/ageing/', params)

    def statement(self, **params):
        self.authenticate(self.admin_a)
        return self.client.get(f'/api/school/finance/students/{self.student_a.pk}/statement/', params)

    def charge(self, days, due_days=None, amount='100'):
        as_of = date(2026, 10, 16)
        fee = Fee.objects.create(school=self.school_a, academic_year=self.year_a, term=self.term_a, name=f'Charge {days}', amount=amount,
            due_date=as_of - timedelta(days=due_days if due_days is not None else days))
        return StudentFeeAssignment.objects.create(student=self.student_a, fee=fee, amount_owed=amount, assigned_on=as_of - timedelta(days=days))

    def test_school_local_numbering_duplicates_and_no_ledger_mutation(self):
        before = (Payment.objects.count(), FinancialLedgerEntry.objects.count(), StudentFeeAssignment.objects.count())
        first = self.invoice(); repeated = self.invoice()
        other = self.invoice(self.assignment_b, self.admin_b)
        self.assertEqual((first.status_code, repeated.status_code, other.status_code), (201, 200, 201))
        self.assertEqual(first.data['id'], repeated.data['id'])
        self.assertEqual(first.data['number'], 'INV-000001')
        self.assertEqual(other.data['number'], 'INV-000001')
        self.assertEqual(SchoolInvoiceSequence.objects.get(school=self.school_a).next_number, 2)
        self.assertEqual(before, (Payment.objects.count(), FinancialLedgerEntry.objects.count(), StudentFeeAssignment.objects.count()))
        self.assertEqual(AuditLog.objects.filter(action='invoice_generated').count(), 2)

    def test_invoice_snapshot_is_immutable_and_payment_totals_are_live(self):
        response = self.invoice(); invoice = StudentInvoice.objects.get(pk=response.data['id'])
        invoice.number = 'CHANGED'
        with self.assertRaises(ModelValidationError): invoice.save()
        fee = self.assignment_a.fee; fee.name = 'Future fee name'; fee.amount = 999; fee.save()
        self.school_a.name = 'Renamed school'; self.school_a.save()
        self.student_a.first_name = 'Renamed learner'; self.student_a.save()
        data = self.client.get(f'/api/school/finance/invoices/{invoice.pk}/').data
        self.assertEqual(data['school']['name'], 'School A')
        self.assertEqual(data['student']['name'], 'Alice Learner')
        self.assertEqual(data['lines'][0]['description'], 'Tuition A')
        self.assertEqual(data['total'], Decimal('100'))
        self.assertEqual(data['payments_allocated'], Decimal('25'))
        self.assertEqual(data['outstanding_balance'], Decimal('75'))
        self.payment_a.is_reversed = True; self.payment_a.reversed_at = timezone.now(); self.payment_a.save()
        self.assertEqual(self.client.get(f'/api/school/finance/invoices/{invoice.pk}/').data['outstanding_balance'], Decimal('100'))

    def test_invoice_database_duplicate_constraints(self):
        self.invoice(); original = StudentInvoice.objects.get(assignment=self.assignment_a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentInvoice.objects.create(school=self.school_a, assignment=self.assignment_a, number='OTHER', issued_on=original.issued_on,
                due_date=original.due_date, currency='USD', total=100, snapshot={}, generated_by=self.admin_a)

    def test_direct_object_access_and_forged_tenant_ids(self):
        invoice = self.invoice().data
        self.authenticate(self.admin_b)
        for suffix in ('', '?export=pdf'):
            self.assertEqual(self.client.get(f'/api/school/finance/invoices/{invoice["id"]}/{suffix}').status_code, 404)
        self.assertEqual(self.invoice(self.assignment_b).status_code, 404)
        self.assertEqual(self.client.post('/api/school/finance/invoices/', {'assignment': self.assignment_a.pk, 'school_id': self.school_b.pk}, format='json').status_code, 400)
        self.assertEqual(self.report(academic_year=self.year_b.pk).status_code, 404)
        self.assertEqual(self.report(term=self.term_b.pk).status_code, 404)
        self.assertEqual(self.report(school_class=self.class_b.pk).status_code, 404)
        self.assertEqual(self.report(student=self.student_b.pk).status_code, 404)

    def test_parent_link_and_feature_flag_for_list_detail_and_pdf(self):
        invoice = self.invoice().data
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get('/api/parent/invoices/').status_code, 403)
        SchoolDocumentSettings.objects.create(school=self.school_a, parent_invoice_access=True)
        self.assertEqual(len(self.client.get('/api/parent/invoices/').data), 1)
        url = f'/api/parent/invoices/{invoice["id"]}/'
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url, {'export': 'pdf'}).status_code, 200)
        self.assertEqual(self.client.post('/api/parent/invoices/', {'assignment': self.assignment_a.pk}).status_code, 403)
        ParentStudent.objects.filter(student=self.student_a, parent=self.parent_a).delete()
        self.assertEqual(self.client.get('/api/parent/invoices/').data, [])
        self.assertEqual(self.client.get(url).status_code, 404)
        SchoolDocumentSettings.objects.create(school=self.school_b, parent_invoice_access=True)
        self.authenticate(self.parent_b_user)
        self.assertEqual(self.client.get(url, {'export': 'pdf'}).status_code, 404)

    def test_teacher_and_platform_cannot_access_financial_documents(self):
        teacher = self.make_user('finance-teacher', User.Role.TEACHER)
        Teacher.objects.create(user=teacher, school=self.school_a)
        for user in (teacher, self.platform_admin):
            self.authenticate(user)
            for path in ('/api/school/finance/invoices/', '/api/school/finance/ageing/', '/api/school/finance/outstanding/',
                         f'/api/school/finance/students/{self.student_a.pk}/statement/', f'/api/parent/students/{self.student_a.pk}/statement/'):
                self.assertEqual(self.client.get(path, {'export': 'pdf'}).status_code, 403, path)

    def test_ageing_boundaries_due_dates_and_allocated_partial_payment(self):
        self.assignment_a.assigned_on = date(2027, 1, 1); self.assignment_a.save()
        charges = [self.charge(120, days) for days in (-1, 0, 30, 31, 60, 61, 90, 91)]
        self.payment_a.student_fee_assignment = charges[-1]; self.payment_a.paid_at = datetime(2026, 10, 1, tzinfo=dt_timezone.utc); self.payment_a.save()
        data = self.report(reporting_date='2026-10-16').data
        row = data['rows'][0]
        self.assertEqual([row[k] for k in BUCKETS], [Decimal(100), Decimal(200), Decimal(200), Decimal(200), Decimal(75)])
        self.assertEqual(sum(row[k] for k in BUCKETS), row['outstanding'])
        self.assertEqual(row['charges'], Decimal(800))
        self.assertEqual(row['payments'], Decimal(25))
        self.assertEqual(row['outstanding'], Decimal(775))
        self.assertEqual(data['totals']['outstanding'], row['outstanding'])
        self.assertNotIn('Beth', str(data))

    def test_ageing_as_of_handles_future_payments_and_later_reversal(self):
        self.payment_a.paid_at = datetime(2026, 2, 1, tzinfo=dt_timezone.utc)
        self.payment_a.is_reversed = True; self.payment_a.reversed_at = datetime(2026, 4, 1, tzinfo=dt_timezone.utc); self.payment_a.save()
        for day, balance in [('2026-01-20', '100'), ('2026-03-01', '75'), ('2026-04-02', '100')]:
            self.assertEqual(self.report(reporting_date=day).data['totals']['outstanding'], Decimal(balance))

    def test_outstanding_reuses_ageing_and_filters_search_sort(self):
        self.authenticate(self.admin_a)
        params = {'reporting_date': '2026-12-31', 'search': 'Alice', 'sort': '-outstanding', 'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'school_class': self.class_a.pk}
        a = self.client.get('/api/school/finance/ageing/', params).data
        b = self.client.get('/api/school/finance/outstanding/', params).data
        self.assertEqual(a['rows'], b['rows']); self.assertEqual(a['totals'], b['totals'])
        self.assertEqual(self.report(search='missing').data['rows'], [])
        self.assertEqual(self.report(reporting_date='bad').status_code, 400)
        self.assertEqual(self.report(sort='school_id').status_code, 400)

    def test_statement_opening_running_and_closing_with_original_dates(self):
        self.payment_a.paid_at = datetime(2026, 2, 10, tzinfo=dt_timezone.utc); self.payment_a.save()
        self.charge(200, amount='50')  # March 30, outside selected February
        data = self.statement(date_from='2026-02-01', date_to='2026-02-28').data
        self.assertEqual(data['summary']['opening_balance'], Decimal(100))
        self.assertEqual(data['summary']['charges'], Decimal(0))
        self.assertEqual(data['summary']['payments'], Decimal(25))
        self.assertEqual(data['summary']['closing_balance'], Decimal(75))
        balance = data['summary']['opening_balance']
        for row in data['transactions']:
            balance += row['debit'] - row['credit']; self.assertEqual(balance, row['balance'])
        self.assertEqual(balance, data['summary']['closing_balance'])

    def test_statement_term_carries_prior_year_balance_and_old_fee_payment(self):
        old_year = AcademicYear.objects.create(school=self.school_a, name='2025', start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        old_term = Term.objects.create(academic_year=old_year, name='Old', sequence=1, start_date=date(2025, 1, 1), end_date=date(2025, 4, 1))
        fee = self.assignment_a.fee; fee.academic_year = old_year; fee.term = old_term; fee.save()
        self.assignment_a.assigned_on = date(2025, 12, 1); self.assignment_a.save()
        self.payment_a.paid_at = datetime(2026, 2, 1, tzinfo=dt_timezone.utc); self.payment_a.save()
        data = self.statement(academic_year=self.year_a.pk, term=self.term_a.pk).data
        self.assertEqual(data['summary']['opening_balance'], Decimal(100))
        self.assertEqual(data['summary']['payments'], Decimal(25))
        self.assertEqual(data['summary']['closing_balance'], Decimal(75))

    def test_statement_adjustments_and_mirror_entries_are_not_duplicated(self):
        FinancialLedgerEntry.objects.create(student=self.student_a, fee_assignment=self.assignment_a, entry_type='charge', amount=100,
            occurred_at=timezone.now(), description='Mirror', currency='USD')
        FinancialLedgerEntry.objects.create(student=self.student_a, fee_assignment=self.assignment_a, entry_type='adjustment', amount=5,
            occurred_at=timezone.now(), description='Adjustment', currency='USD')
        self.assertEqual(self.statement().data['summary']['closing_balance'], Decimal(80))
        self.assertEqual(self.report(reporting_date='2026-12-31').data['totals']['outstanding'], Decimal(80))

    def test_settled_credit_adjusted_account_has_no_due_date_or_receivable(self):
        FinancialLedgerEntry.objects.create(student=self.student_a, fee_assignment=self.assignment_a, entry_type='adjustment', amount=-100,
            occurred_at=timezone.now(), description='Existing credit adjustment', currency='USD')
        self.assertEqual(self.statement().data['summary']['closing_balance'], Decimal(-25))
        self.assertIsNone(self.statement().data['due_date'])
        self.assertEqual(self.report(reporting_date='2026-12-31').data['rows'], [])

    def test_payment_allocation_service_and_invoice_generation_do_not_duplicate_cash(self):
        payment, _ = record_payment(student_fee_assignment=self.assignment_a, amount=Decimal('15'), paid_at=timezone.now(), method='cash', recorded_by=self.admin_a)
        self.invoice(); self.invoice()
        self.assertEqual(Payment.objects.filter(student_fee_assignment=self.assignment_a).count(), 2)
        self.assertEqual(self.report(reporting_date='2026-12-31').data['totals']['payments'], Decimal(40))
        self.assertEqual(self.statement().data['summary']['payments'], Decimal(40))
        self.assertEqual(payment.student_fee_assignment_id, self.assignment_a.pk)

    def test_exports_are_valid_branded_a4_and_formula_safe(self):
        from pypdf import PdfReader
        from .documents import excel
        invoice = self.invoice().data
        paths = [f'/api/school/finance/invoices/{invoice["id"]}/', '/api/school/finance/ageing/', '/api/school/finance/outstanding/',
                 f'/api/school/finance/students/{self.student_a.pk}/statement/']
        for path in paths:
            response = self.client.get(path, {'export': 'pdf'})
            self.assertEqual(response.status_code, 200, path)
            pdf = PdfReader(BytesIO(response.content)); text = '\n'.join(p.extract_text() for p in pdf.pages)
            self.assertIn('School A', text); self.assertNotIn('School B', text)
            self.assertAlmostEqual(min(float(pdf.pages[0].mediabox.width), float(pdf.pages[0].mediabox.height)), 595.276, places=2)
        for path in paths[1:]:
            response = self.client.get(path, {'export': 'xlsx'})
            self.assertEqual(response.status_code, 200)
            with ZipFile(BytesIO(response.content)) as archive:
                ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        with ZipFile(BytesIO(excel([['=HYPERLINK("bad")', Decimal('10.50')]]))) as archive:
            xml = archive.read('xl/worksheets/sheet1.xml').decode()
            self.assertIn('inlineStr', xml); self.assertNotIn('<f>', xml); self.assertIn('<v>10.50</v>', xml)

    def test_document_settings_validate_school_owned_brand_and_grading(self):
        self.authenticate(self.admin_a)
        url = '/api/school/document-settings/'
        self.assertFalse(self.client.get(url).data['parent_invoice_access'])
        self.assertEqual(self.client.patch(url, {'brand_color': 'red'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'grading_scale': [{'minimum': 80, 'grade': 'A'}]}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'school_id': self.school_b.pk}, format='json').status_code, 400)
        result = self.client.patch(url, {'motto': 'Learning together', 'grading_scale': [{'minimum': 80, 'grade': 'A'}, {'minimum': 0, 'grade': 'B'}]}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(SchoolDocumentSettings.objects.filter(school=self.school_b).exists())

    def test_academic_history_published_only_and_cross_tenant_protection(self):
        self.authenticate(self.admin_a)
        url = f'/api/school/students/{self.student_a.pk}/academic-history/'
        data = self.client.get(url).data
        self.assertEqual(len(data['periods']), 1)
        self.assertEqual(data['periods'][0]['results'][0]['score'], '80.00')
        self.assertEqual(data['periods'][0]['results'][0]['grade'], '')
        self.result_a.status = 'draft'; self.result_a.save()
        self.assertEqual(self.client.get(url).data['periods'], [])
        self.authenticate(self.admin_b); self.assertEqual(self.client.get(url).status_code, 404)
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get(f'/api/parent/students/{self.student_b.pk}/academic-history/').status_code, 404)

    def test_historical_grade_and_comments_survive_grading_configuration_changes(self):
        settings = SchoolDocumentSettings.objects.create(school=self.school_a, grading_scale=[{'minimum': '75', 'grade': 'A'}, {'minimum': '0', 'grade': 'C'}])
        self.result_a.status = 'approved'; self.result_a.comment = 'Official comment'; self.result_a.save()
        self.report_a.is_published = False; self.report_a.save()
        self.authenticate(self.admin_a)
        self.assertEqual(self.client.post(f'/api/school/results/{self.result_a.pk}/transition/', {'status': 'published'}).status_code, 200)
        self.assertEqual(self.client.post(f'/api/school/report-cards/{self.report_a.pk}/publish/').status_code, 200)
        settings.grading_scale = [{'minimum': '0', 'grade': 'NEW'}]; settings.save()
        self.result_a.refresh_from_db(); self.assertEqual(self.result_a.official_grade, 'A')
        data = self.client.get(f'/api/school/students/{self.student_a.pk}/academic-history/').data
        official = data['periods'][0]['results'][0]
        self.assertEqual(official['grade'], 'A'); self.assertEqual(official['comment'], 'Official comment')
        publication = ReportCardPublication.objects.get(report_card=self.report_a)
        with self.assertRaises(ModelValidationError): publication.save()
        self.assertEqual(self.client.post(f'/api/school/report-cards/{self.report_a.pk}/publish/').status_code, 200)
        # Re-publication without result edits is idempotent.
        self.assertEqual(ReportCardPublication.objects.filter(report_card=self.report_a).count(), 1)

    def test_teacher_history_is_restricted_to_assigned_subjects(self):
        teacher_user = self.make_user('history-teacher', User.Role.TEACHER)
        teacher = Teacher.objects.create(user=teacher_user, school=self.school_a)
        assignment = TeacherAssignment.objects.create(teacher=teacher, school_class=self.class_a)
        assignment.subjects.add(self.result_a.class_subject)
        subject = Subject.objects.create(school=self.school_a, name='Unassigned subject')
        cs = ClassSubject.objects.create(subject=subject, school_class=self.class_a, academic_year=self.year_a)
        AcademicResult.objects.create(student_enrollment=self.enrollment_a, term=self.term_a, class_subject=cs, score=20, maximum_score=100, recorded_by=self.admin_a)
        self.authenticate(teacher_user)
        data = self.client.get(f'/api/teacher/students/{self.student_a.pk}/academic-history/').data
        self.assertEqual(len(data['periods'][0]['results']), 1)
        self.assertNotIn('Unassigned subject', str(data))
        self.assertNotIn('guardian', data['student'])
        self.assertEqual(self.client.get(f'/api/teacher/students/{self.student_b.pk}/academic-history/').status_code, 404)

    def test_pdf_multiple_pages_repeat_headers_and_keep_summary_together(self):
        from pypdf import PdfReader
        for i in range(95):
            self.charge(150 + i, amount='1.25')
        response = self.statement(export='pdf')
        self.assertEqual(response.status_code, 200)
        pdf = PdfReader(BytesIO(response.content))
        self.assertGreater(len(pdf.pages), 2)
        for page in pdf.pages[1:]:
            self.assertIn('Running Balance', page.extract_text().replace('\n', ' '))
        last = pdf.pages[-1].extract_text()
        self.assertIn('Total Amount Due', last)
        self.assertIn('Current / Closing Balance', last)
        for page in pdf.pages[:-1]:
            self.assertNotIn('Total Amount Due', page.extract_text())

    def test_invoice_logo_snapshot_survives_replaced_logo(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from django.core.files.base import ContentFile
        from PIL import Image
        from pypdf import PdfReader
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            stream = BytesIO(); Image.new('RGB', (40, 40), 'blue').save(stream, 'PNG')
            self.school_a.logo.save('original.png', ContentFile(stream.getvalue()))
            data = self.invoice().data
            old_logo = self.school_a.logo.name
            self.school_a.logo.storage.delete(old_logo)
            response = self.client.get(f'/api/school/finance/invoices/{data["id"]}/', {'export': 'pdf'})
            pdf = PdfReader(BytesIO(response.content))
            self.assertEqual(len(list(pdf.pages[0].images)), 1)
            self.assertTrue(data['school']['logo_data'])
            listed = self.client.get('/api/school/finance/invoices/').data[0]
            self.assertNotIn('school', listed)
            self.assertEqual(listed['student']['name'], 'Alice Learner')

    def test_existing_receipts_share_a4_branding_without_changing_payment_history(self):
        from pypdf import PdfReader
        SchoolDocumentSettings.objects.create(school=self.school_a, motto='Learning together', additional_contacts='Office extension 2')
        self.authenticate(self.admin_a)
        response = self.client.get(f'/api/school/receipts/{self.receipt_a.pk}/pdf/')
        pdf = PdfReader(BytesIO(response.content))
        text = pdf.pages[0].extract_text()
        self.assertIn('Learning together', text); self.assertIn('Office extension 2', text)
        self.assertIn('R-A-001', text); self.assertIn('USD 25.00', text)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), 595.276, places=2)
        self.assertEqual(Payment.objects.count(), 2)

    def test_academic_history_compiles_multiple_years_and_preserves_correction_versions(self):
        old_year = AcademicYear.objects.create(school=self.school_a, name='2025', start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        old_term = Term.objects.create(academic_year=old_year, name='Term 3', sequence=3, start_date=date(2025, 9, 1), end_date=date(2025, 12, 1))
        old_enrollment = StudentEnrollment.objects.create(student=self.student_a, school_class=self.class_a, academic_year=old_year, enrolled_on=date(2025, 1, 1), left_on=date(2025, 12, 1))
        old_subject = ClassSubject.objects.create(school_class=self.class_a, subject=self.result_a.class_subject.subject, academic_year=old_year)
        AcademicResult.objects.create(student_enrollment=old_enrollment, term=old_term, class_subject=old_subject, score=70, maximum_score=100,
            recorded_by=self.admin_a, official_grade='Original Grade', comment='Prior official comment')
        ReportCard.objects.create(student_enrollment=old_enrollment, term=old_term)
        self.authenticate(self.admin_a)
        url = f'/api/school/students/{self.student_a.pk}/academic-history/'
        self.assertEqual([p['academic_year'] for p in self.client.get(url).data['periods']], ['2025', '2026'])
        self.assertEqual(self.client.get(url).data['periods'][0]['results'][0]['grade'], 'Original Grade')
        self.client.post(f'/api/school/report-cards/{self.report_a.pk}/publish/')
        original = ReportCardPublication.objects.get(report_card=self.report_a).snapshot
        self.client.post(f'/api/school/results/{self.result_a.pk}/correction/', {'reason': 'Correct verified marking error'})
        self.assertEqual(len(self.client.get(url).data['periods']), 1)
        self.client.patch(f'/api/school/results/{self.result_a.pk}/', {'score': '90'}, format='json')
        for status in ('submitted', 'approved', 'published'):
            self.assertEqual(self.client.post(f'/api/school/results/{self.result_a.pk}/transition/', {'status': status}).status_code, 200)
        self.assertEqual(self.client.post(f'/api/school/report-cards/{self.report_a.pk}/publish/').status_code, 200)
        versions = list(ReportCardPublication.objects.filter(report_card=self.report_a).order_by('version'))
        self.assertEqual(len(versions), 2); self.assertEqual(versions[0].snapshot, original)
        self.assertEqual(versions[1].snapshot['results'][0]['score'], '90.00')
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get(f'/api/parent/students/{self.student_a.pk}/academic-history/', {'export': 'pdf'}).status_code, 200)

    def test_additive_backfill_preserves_existing_published_values_idempotently(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        migration = import_module('core.migrations.0029_preserve_published_academic_history')
        before = list(AcademicResult.objects.order_by('pk').values())
        migration.preserve_published(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        migration.preserve_published(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        self.assertEqual(before, list(AcademicResult.objects.order_by('pk').values()))
        self.assertEqual(ReportCardPublication.objects.count(), 2)
        snapshot = ReportCardPublication.objects.get(report_card=self.report_a).snapshot
        self.assertEqual(snapshot['results'][0]['score'], '80.00')
        self.assertEqual(snapshot['results'][0]['grade'], '')


class InvoiceConcurrencyTests(DocumentFixtures, TransactionTestCase):
    def test_concurrent_generation_has_one_invoice_and_consumes_one_number(self):
        def generate(_):
            try:
                invoice, created = generate_invoice(school=self.school_a, assignment_id=self.assignment_a.pk, actor=self.admin_a)
                return invoice.pk, invoice.number, created
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(generate, range(2)))
        self.assertEqual(results[0][:2], results[1][:2])
        self.assertEqual(sum(r[2] for r in results), 1)
        self.assertEqual(StudentInvoice.objects.count(), 1)
        self.assertEqual(SchoolInvoiceSequence.objects.get(school=self.school_a).next_number, 2)

    def test_concurrent_different_obligations_receive_distinct_local_numbers(self):
        fee = Fee.objects.create(school=self.school_a, academic_year=self.year_a, term=self.term_a, name='Transport', amount=50)
        charge = StudentFeeAssignment.objects.create(student=self.student_a, fee=fee, amount_owed=50, assigned_on=date(2026, 1, 1))
        def generate(assignment_id):
            try:
                invoice, _ = generate_invoice(school=self.school_a, assignment_id=assignment_id, actor=self.admin_a)
                return invoice.number
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            numbers = list(executor.map(generate, [self.assignment_a.pk, charge.pk]))
        self.assertEqual(set(numbers), {'INV-000001', 'INV-000002'})
