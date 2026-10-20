from datetime import date, datetime, timezone as dt_timezone
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile
from xml.etree import ElementTree
from django.test import override_settings, TransactionTestCase
from django.db import connections
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase, APIClient
from .test_student_documents import DocumentFixtures
from .models import (FinanceAccount, FinanceCategory, ManualIncome, Expense, ExpenseRevision, Payment, Receipt,
    FinancialLedgerEntry, StudentFeeAssignment, StudentInvoice, Teacher, User, AuditLog, SchoolClass, SchoolDocumentSettings, School, SchoolAdministrator)


class SchoolFinanceTests(DocumentFixtures, APITestCase):
    def setUp(self):
        super().setUp()
        self.payment_a.paid_at = datetime(2026, 1, 15, tzinfo=dt_timezone.utc); self.payment_a.save()
        self.account = FinanceAccount.objects.create(school=self.school_a, name='Main Cash', kind='cash')
        self.bank_b = FinanceAccount.objects.create(school=self.school_b, name='Private Bank', kind='bank')
        self.category = FinanceCategory.objects.create(school=self.school_a, name='Donations', kind='income')
        self.expense_category = FinanceCategory.objects.create(school=self.school_a, name='Cleaning', kind='expense')
        self.income = ManualIncome.objects.create(school=self.school_a, income_date=date(2026, 1, 25), source='Community', description='Donation',
            amount=20, currency='USD', payment_method='cash', account=self.account, category=self.category, recorded_by=self.admin_a)
        self.expense = Expense.objects.create(school=self.school_a, expense_date=date(2026, 1, 20), category='utilities', description='Water',
            amount=10, currency='USD', payment_method='cash', account=self.account, payee='Water supplier', recorded_by=self.admin_a)
        self.authenticate(self.admin_a)

    def report(self, kind='monthly', **params):
        return self.client.get(f'/api/school/finance/reports/{kind}/', {'year': 2026, 'month': 1, **params})

    def income_payload(self):
        return dict(income_date='2026-01-26', source='Donor', description='School event proceeds', amount='15.50', payment_method='bank',
            account=self.account.pk, category=self.category.pk, reference='DON-2', notes='Confirmed received')

    def expense_payload(self):
        return dict(expense_date='2026-01-26', description='Cleaning supplies', amount='5.50', category='other', finance_category=self.expense_category.pk,
            payment_method='cash', account=self.account.pk, payee='Supplier', notes='Confirmed paid')

    def test_monthly_accounting_separates_billed_cash_and_receivables(self):
        response = self.report(); self.assertEqual(response.status_code, 200, response.data)
        summary = response.data['summary']
        for key, expected in [('billed_fees', 100), ('fees_collected', 25), ('other_income', 20), ('total_cash_income', 45), ('expenses', 10), ('surplus_deficit', 35), ('outstanding_receivables', 75)]:
            self.assertEqual(summary[key], Decimal(expected), key)
        self.assertFalse(response.data['budget_configured'])
        self.assertNotIn('budget', str(response.data['categories']))

    def test_cashbook_references_each_canonical_record_once_and_never_charges(self):
        before = (Payment.objects.count(), Receipt.objects.count(), FinancialLedgerEntry.objects.count(), StudentFeeAssignment.objects.count())
        for _ in range(2):
            response = self.report('cash-books')
            self.assertEqual(response.status_code, 200, response.data)
            rows = response.data['rows']
            self.assertEqual(len(rows), 3); self.assertEqual(len({r['id'] for r in rows}), 3)
            self.assertEqual({r['linked_type'] for r in rows}, {'payment', 'manual_income', 'expense'})
            self.assertEqual(response.data['summary']['money_in'], Decimal(45))
            self.assertEqual(response.data['summary']['money_out'], Decimal(10))
            self.assertEqual(response.data['summary']['closing_balance'], Decimal(35))
        self.assertEqual(before, (Payment.objects.count(), Receipt.objects.count(), FinancialLedgerEntry.objects.count(), StudentFeeAssignment.objects.count()))

    def test_cashbook_opening_running_closing_and_account_filter(self):
        ManualIncome.objects.create(school=self.school_a, income_date=date(2025, 12, 1), source='Opening recorded history', description='Prior income',
            amount=5, currency='USD', payment_method='cash', account=self.account, recorded_by=self.admin_a)
        data = self.report('cash-books').data
        self.assertEqual(data['summary']['opening_balance'], Decimal(5))
        running = Decimal(5)
        for row in data['rows']:
            running += row['money_in'] - row['money_out']; self.assertEqual(row['balance'], running)
        self.assertEqual(running, Decimal(40)); self.assertEqual(running, data['summary']['closing_balance'])
        scoped = self.report('cash-books', account=self.account.pk).data
        self.assertEqual(scoped['summary']['closing_balance'], Decimal(15))  # 5 + 20 - 10; legacy payment unassigned
        self.assertEqual(self.report('cash-books', account='unassigned').data['summary']['closing_balance'], Decimal(25))

    def test_reversals_preserve_original_period_and_offset_correction_period(self):
        self.payment_a.is_reversed = True; self.payment_a.reversed_at = datetime(2026, 2, 5, tzinfo=dt_timezone.utc); self.payment_a.reversal_reason = 'Incorrect duplicate'; self.payment_a.save()
        jan = self.report().data; feb = self.report(month=2).data
        self.assertEqual(jan['summary']['fees_collected'], Decimal(25))
        self.assertEqual(jan['summary']['outstanding_receivables'], Decimal(75))
        self.assertEqual(feb['summary']['fees_collected'], Decimal(-25))
        self.assertEqual(feb['summary']['outstanding_receivables'], Decimal(100))
        book = self.report('cash-books', period='annual').data
        payment_rows = [r for r in book['rows'] if r['linked_type'] == 'payment']
        self.assertEqual(len(payment_rows), 2); self.assertEqual(sum(r['amount'] for r in payment_rows), Decimal(0))
        self.assertTrue(payment_rows[1]['correction'])

    def test_expense_and_other_income_reversals_preserve_records_and_audit(self):
        for endpoint, record in [('expenses', self.expense), ('finance/other-income', self.income)]:
            with patch('core.school_finance_api.timezone.now', return_value=datetime(2026, 2, 10, tzinfo=dt_timezone.utc)):
                response = self.client.post(f'/api/school/{endpoint}/{record.pk}/reverse/', {'reason': 'Correct invalid entry'}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(self.client.post(f'/api/school/{endpoint}/{record.pk}/reverse/', {'reason': 'Repeat correction'}).status_code, 400)
            self.assertEqual(self.client.delete(f'/api/school/{endpoint}/{record.pk}/').status_code, 405)
        self.assertEqual(self.report().data['summary']['surplus_deficit'], Decimal(35))
        feb = self.report(month=2).data['summary']
        self.assertEqual(feb['other_income'], Decimal(-20)); self.assertEqual(feb['expenses'], Decimal(-10)); self.assertEqual(feb['surplus_deficit'], Decimal(-10))
        self.assertTrue(AuditLog.objects.filter(action='expense_reversed').exists())

    def test_annual_totals_reconcile_to_monthly_breakdown(self):
        self.payment_a.is_reversed = True; self.payment_a.reversed_at = datetime(2026, 2, 5, tzinfo=dt_timezone.utc); self.payment_a.save()
        annual = self.report('annual').data
        self.assertEqual(len(annual['months']), 12)
        for key in ('billed_fees', 'fees_collected', 'other_income', 'expenses', 'surplus_deficit'):
            self.assertEqual(sum((m[key] for m in annual['months']), Decimal(0)), annual['summary'][key], key)
        self.assertEqual(annual['summary']['fees_collected'], Decimal(0))
        self.assertEqual(annual['summary']['surplus_deficit'], Decimal(10))

    def test_dashboard_and_report_metrics_share_the_period(self):
        dashboard = self.report('dashboard').data
        monthly = self.report().data
        self.assertEqual(dashboard['summary'], monthly['summary'])
        self.assertEqual(dashboard['categories'], monthly['categories'])
        daily = self.report('cash-books', period='daily', date='2026-01-15').data
        self.assertEqual(daily['summary']['money_in'], Decimal(25))
        custom = self.report('cash-books', period='custom', start_date='2026-01-20', end_date='2026-01-25').data
        self.assertEqual(custom['summary']['opening_balance'], Decimal(25))
        self.assertEqual(custom['summary']['closing_balance'], Decimal(35))

    def test_academic_year_term_and_bad_period_filters_are_validated(self):
        annual = self.report('annual', academic_year=self.year_a.pk).data
        self.assertEqual(annual['period'], {'start': self.year_a.start_date, 'end': self.year_a.end_date})
        self.assertEqual(self.report('dashboard', period='academic', academic_year=self.year_a.pk, term=self.term_a.pk).status_code, 200)
        for params in [dict(month=13), dict(period='custom', start_date='2026-02-01', end_date='2026-01-01'), dict(sort='school_id')]:
            self.assertEqual(self.report('cash-books', **params).status_code, 400)
        self.assertEqual(self.report('dashboard', account=self.account.pk).status_code, 400)

    def test_cash_received_reference_receipt_receiver_method_totals(self):
        data = self.report('cash-received').data
        payment = next(r for r in data['rows'] if r['linked_type'] == 'payment')
        self.assertEqual(payment['receipt_number'], self.receipt_a.receipt_number)
        self.assertEqual(payment['linked_id'], self.payment_a.pk)
        self.assertEqual(payment['student'], self.student_a.pk)
        self.assertEqual(payment['amount'], Decimal(25)); self.assertEqual(payment['received_by'], self.admin_a.username)
        self.assertEqual(data['method_totals']['cash'], Decimal(45))

    def test_historical_class_context_survives_current_student_transfer(self):
        previous = self.class_a
        next_class = SchoolClass.objects.create(school=self.school_a, name='Next class')
        self.student_a.school_class = next_class; self.student_a.save()
        data = self.report('cash-received', school_class=previous.pk).data
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['class_name'], previous.name)
        self.assertEqual(self.report('cash-received', school_class=next_class.pk).data['rows'], [])

    def test_income_and_expense_category_method_search_and_sort_preserve_scope(self):
        data = self.report('income', category=f'configured:{self.category.pk}', account=self.account.pk, payment_method='cash', search='Donation', sort='-amount').data
        self.assertEqual(len(data['rows']), 1); self.assertEqual(data['rows'][0]['linked_id'], self.income.pk)
        self.assertEqual(self.report('cash-books', transaction_type='expense').data['summary']['money_out'], Decimal(10))
        self.assertEqual(self.report('cash-books', search='missing').data['rows'], [])

    def test_manual_income_rejects_payment_links_and_replays_idempotently(self):
        url = '/api/school/finance/other-income/'
        payload = self.income_payload(); key = str(uuid4())
        first = self.client.post(url, payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        repeated = self.client.post(url, payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(first.status_code, 201, first.data); self.assertEqual(repeated.data['id'], first.data['id'])
        self.assertEqual(ManualIncome.objects.filter(school=self.school_a).count(), 2)
        self.assertEqual(self.client.post(url, payload | {'amount': '1.00'}, format='json', HTTP_IDEMPOTENCY_KEY=key).status_code, 409)
        for extra in ({'payment': self.payment_a.pk}, {'student': self.student_a.pk}, {'school_id': self.school_b.pk}):
            self.assertEqual(self.client.post(url, payload | extra, format='json').status_code, 400)

    def test_expense_create_duplicate_protection_and_revision_history(self):
        url = '/api/school/expenses/'; payload = self.expense_payload(); key = str(uuid4())
        first = self.client.post(url, payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        repeated = self.client.post(url, payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(first.status_code, 201, first.data); self.assertEqual(first.data['id'], repeated.data['id'])
        target = f'{url}{first.data["id"]}/'
        response = self.client.patch(target, {'amount': '6.75', 'payee': 'Correct supplier'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        old = ExpenseRevision.objects.get(expense_id=first.data['id'])
        self.assertEqual(old.snapshot['amount'], '5.50'); self.assertEqual(old.snapshot['payee'], 'Supplier')
        self.assertEqual(self.client.get(target + 'revisions/').data[0]['actor_id'], self.admin_a.pk)

    def test_payment_duplicate_submission_creates_one_payment_receipt_and_cash_representation(self):
        payload = dict(student_fee_assignment=self.assignment_a.pk, amount='5.00', paid_at='2026-01-28T12:00:00Z', method='bank', account=self.account.pk, income_category=self.category.pk)
        key = str(uuid4()); before = Payment.objects.count()
        first = self.client.post('/api/school/payments/', payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        repeated = self.client.post('/api/school/payments/', payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(first.status_code, 201, first.data); self.assertEqual(repeated.data['id'], first.data['id'])
        self.assertEqual(Payment.objects.count(), before + 1)
        rows = self.report('cash-books').data['rows']
        self.assertEqual(len([r for r in rows if r['linked_type'] == 'payment' and r['linked_id'] == first.data['id']]), 1)

    def test_cross_school_ids_and_roles_cannot_access_school_finance(self):
        for params in [dict(account=self.bank_b.pk), dict(academic_year=self.year_b.pk), dict(term=self.term_b.pk), dict(student=self.student_b.pk), dict(school_class=self.class_b.pk)]:
            self.assertEqual(self.report('cash-books', **params).status_code, 404)
        for endpoint, payload in [('/api/school/expenses/', self.expense_payload() | {'account': self.bank_b.pk}), ('/api/school/finance/other-income/', self.income_payload() | {'account': self.bank_b.pk})]:
            self.assertEqual(self.client.post(endpoint, payload, format='json').status_code, 400)
        self.authenticate(self.admin_b)
        for suffix in ('', 'revisions/', 'reverse/'):
            response = self.client.get(f'/api/school/expenses/{self.expense.pk}/{suffix}') if suffix != 'reverse/' else self.client.post(f'/api/school/expenses/{self.expense.pk}/reverse/', {'reason': 'Attempt correction'})
            self.assertEqual(response.status_code, 404)
        teacher_user = self.make_user('school-finance-teacher', User.Role.TEACHER); Teacher.objects.create(school=self.school_a, user=teacher_user)
        for actor in (teacher_user, self.parent_a_user, self.platform_admin):
            self.authenticate(actor)
            for kind in ('income', 'cash-books', 'cash-received', 'monthly', 'annual', 'dashboard', 'expense-report'):
                self.assertEqual(self.report(kind, export='pdf').status_code, 403)
            self.assertEqual(self.client.get('/api/school/finance/lookups/').status_code, 403)

    def test_private_supporting_documents_validate_content_and_block_direct_media_access(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            url = f'/api/school/expenses/{self.expense.pk}/attachments/'
            response = self.client.post(url, {'file': SimpleUploadedFile('supplier.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')}, format='multipart')
            self.assertEqual(response.status_code, 201, response.data)
            item = self.expense.attachments.get()
            self.assertEqual(self.client.get('/media/' + item.file.name).status_code, 404)
            download = self.client.get('/api' + response.data['attachments'][0]['download_url'])
            self.assertEqual(download.status_code, 200)
            self.assertTrue(b''.join(download.streaming_content).startswith(b'%PDF'))
            self.assertEqual(self.client.post(url, {'file': SimpleUploadedFile('fake.pdf', b'not a PDF')}, format='multipart').status_code, 400)
            self.authenticate(self.admin_b)
            self.assertEqual(self.client.get(f'{url}{item.pk}/download/').status_code, 404)

    def test_report_notes_are_school_scoped_and_audited(self):
        payload = {'start_date': '2026-01-01', 'end_date': '2026-01-31', 'body': 'Utilities include annual service payment.'}
        self.assertEqual(self.client.post('/api/school/finance/report-notes/', payload, format='json').status_code, 200)
        self.assertEqual(self.report().data['notes'], payload['body'])
        self.authenticate(self.admin_b); self.assertEqual(self.report().data['notes'], '')
        self.assertTrue(AuditLog.objects.filter(school=self.school_a, action='financial_report_note_updated').exists())

    def test_used_categories_and_accounts_preserve_original_labels_and_can_deactivate(self):
        for kind, obj in [('accounts', self.account), ('categories', self.category)]:
            url = f'/api/school/finance/{kind}/{obj.pk}/'
            self.assertEqual(self.client.patch(url, {'name': 'Rewrite history'}, format='json').status_code, 400)
            self.assertEqual(self.client.patch(url, {'is_active': False}, format='json').status_code, 200)
            self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(self.client.post('/api/school/finance/other-income/', self.income_payload(), format='json').status_code, 400)

    def test_exports_are_branded_numeric_and_read_only(self):
        from pypdf import PdfReader
        SchoolDocumentSettings.objects.create(school=self.school_a, motto='Learning together')
        before = (Payment.objects.count(), Expense.objects.count(), ManualIncome.objects.count(), Receipt.objects.count(), StudentInvoice.objects.count())
        for kind in ('income', 'cash-books', 'cash-received', 'monthly', 'annual', 'dashboard', 'expense-report'):
            pdf = self.report(kind, export='pdf'); self.assertEqual(pdf.status_code, 200, kind)
            reader = PdfReader(BytesIO(pdf.content)); text = '\n'.join(page.extract_text() for page in reader.pages)
            self.assertIn('School A', text); self.assertIn('Learning together', text); self.assertNotIn('School B', text)
            self.assertAlmostEqual(min(float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height)), 595.276, places=2)
            xlsx = self.report(kind, export='xlsx'); self.assertEqual(xlsx.status_code, 200)
            with ZipFile(BytesIO(xlsx.content)) as archive:
                xml = archive.read('xl/worksheets/sheet1.xml'); ElementTree.fromstring(xml)
                self.assertIn(b'School A', xml); self.assertIn(b'<v>', xml)
        self.assertEqual(before, (Payment.objects.count(), Expense.objects.count(), ManualIncome.objects.count(), Receipt.objects.count(), StudentInvoice.objects.count()))
        self.assertEqual(AuditLog.objects.filter(action='financial_report_generated').count(), 14)

    def test_large_cashbook_pdf_repeats_headers_and_excel_freezes_styled_header(self):
        from pypdf import PdfReader
        ManualIncome.objects.bulk_create([ManualIncome(school=self.school_a, income_date=date(2026, 1, 25), source='Community',
            description=f'Donation {i}: ' + 'LongDescription' * 12, amount=1, currency='USD', payment_method='cash', recorded_by=self.admin_a) for i in range(75)])
        response = self.report('cash-books', export='pdf')
        self.assertEqual(response.status_code, 200)
        reader = PdfReader(BytesIO(response.content))
        self.assertGreater(len(reader.pages), 2)
        self.assertGreater(sum('Running Balance' in p.extract_text().replace('\n', ' ') for p in reader.pages), 1)
        xlsx = self.report('cash-books', export='xlsx')
        with ZipFile(BytesIO(xlsx.content)) as archive:
            self.assertIn(b'ySplit="3"', archive.read('xl/worksheets/sheet1.xml'))
            self.assertIn(b'<b/>', archive.read('xl/styles.xml'))
            self.assertIn(b'numFmtId="4"', archive.read('xl/styles.xml'))

    def test_foreign_category_and_income_ids_are_denied_and_frontend_school_id_is_not_trusted(self):
        foreign = FinanceCategory.objects.create(school=self.school_b, name='Private Donations', kind='income')
        self.assertEqual(self.report('cash-books', category=f'configured:{foreign.pk}').status_code, 404)
        self.assertEqual(self.client.post('/api/school/finance/other-income/', self.income_payload() | {'category': foreign.pk}, format='json').status_code, 400)
        self.assertEqual(self.report(school_id=self.school_b.pk).data['school']['name'], 'School A')
        self.authenticate(self.admin_b)
        self.assertEqual(self.client.get(f'/api/school/finance/other-income/{self.income.pk}/').status_code, 404)

    def test_currency_cannot_change_with_only_expense_or_manual_income_history(self):
        for kind in ('expense', 'income'):
            school = School.objects.create(name=f'{kind} only school', email=f'{kind}-only@example.test', phone_number='123', default_currency='USD')
            actor = self.make_user(f'{kind}-only-admin', User.Role.SCHOOL_ADMIN)
            SchoolAdministrator.objects.create(school=school, user=actor)
            if kind == 'expense':
                Expense.objects.create(school=school, expense_date=date(2026, 1, 1), category='other', description='Original expense', amount=10, currency='USD', payment_method='cash', recorded_by=actor)
            else:
                ManualIncome.objects.create(school=school, income_date=date(2026, 1, 1), source='Donor', description='Original income', amount=10, currency='USD', payment_method='cash', recorded_by=actor)
            self.authenticate(actor)
            self.assertEqual(self.client.patch('/api/school/profile/', {'default_currency': 'ZAR'}, format='json').status_code, 400)
            school.refresh_from_db(); self.assertEqual(school.default_currency, 'USD')


class SchoolFinanceConcurrencyTests(DocumentFixtures, TransactionTestCase):
    def submit_twice(self, path, payload):
        key = str(uuid4())
        def submit(_):
            try:
                client = APIClient(); client.force_authenticate(self.admin_a)
                response = client.post(path, payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
                return response.status_code, response.data
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit, range(2)))
        self.assertEqual([r[0] for r in responses], [201, 201], responses)
        self.assertEqual(responses[0][1]['id'], responses[1][1]['id'])

    def test_concurrent_manual_income_retry_has_one_record(self):
        self.submit_twice('/api/school/finance/other-income/', dict(income_date='2026-01-10', source='Community', description='Donation', amount='10', payment_method='cash'))
        self.assertEqual(ManualIncome.objects.count(), 1)

    def test_concurrent_expense_retry_has_one_record(self):
        self.submit_twice('/api/school/expenses/', dict(expense_date='2026-01-10', category='utilities', description='Water', amount='10', payment_method='cash'))
        self.assertEqual(Expense.objects.count(), 1)
