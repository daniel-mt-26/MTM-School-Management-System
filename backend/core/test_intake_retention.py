"""School retention policy, using synthetic data only."""
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.utils import timezone
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_intake as fixtures
from .test_intake import CONFIG, application, enquiry
from .intake_models import AdmissionApplication, ContactEnquiry, PublicIntakeKey
from .intake_services import review, one_calendar_month_after


@override_settings(**CONFIG)
class IntakeRetentionTests(APITestCase):
    setUp = fixtures.IntakeAPITests.setUp
    post = fixtures.IntakeAPITests.post
    def test_calendar_boundaries(self):
        for year, month, day, expected in [
            (2024, 1, 31, (2024, 2, 29)), (2025, 1, 31, (2025, 2, 28)),
            (2025, 3, 31, (2025, 4, 30)), (2025, 12, 31, (2026, 1, 31)),
        ]:
            value = datetime(year, month, day, 10, 15, tzinfo=dt_timezone.utc)
            result = one_calendar_month_after(value)
            self.assertEqual((result.year, result.month, result.day), expected)
            self.assertEqual(result.astimezone(dt_timezone.utc).hour, 10)
            self.assertEqual(result.minute, 15)

    def test_every_status_transition_and_same_status_edits(self):
        for kind, body, model, statuses in [
            ('application', application(), AdmissionApplication, ['rejected', 'pending', 'approved', 'rejected', 'approved']),
            ('enquiry', enquiry(), ContactEnquiry, ['in_progress', 'resolved', 'new', 'resolved', 'in_progress']),
        ]:
            self.assertEqual(self.post(body, kind='applications' if kind == 'application' else 'enquiries').status_code, 201)
            row = model.objects.get()
            self.assertIsNone(row.retention_expires_at)
            terminal = 'rejected' if kind == 'application' else 'resolved'
            for index, status in enumerate(statuses):
                now = datetime(2025, 1, 31, 10, tzinfo=dt_timezone.utc) + timedelta(days=index)
                with patch('core.intake_services.timezone.now', return_value=now):
                    row = review(kind, self.school, self.admin, row.pk, {'version': row.version, 'status': status})
                expiry = one_calendar_month_after(now) if status == terminal else None
                self.assertEqual(row.retention_expires_at, expiry)
                row = review(kind, self.school, self.admin, row.pk, {'version': row.version, 'status': status, 'note': 'TEST note'})
                self.assertEqual(row.retention_expires_at, expiry)
                row = review(kind, self.school, self.admin, row.pk, {'version': row.version, 'note': 'TEST note only'})
                self.assertEqual(row.retention_expires_at, expiry)

    def test_cleanup_status_hold_null_and_key_safeguards(self):
        past = timezone.now() - timedelta(days=90)
        for status, hold, expiry, deleted in [
            ('pending', False, past, False), ('approved', False, past, False),
            ('rejected', True, past, False), ('rejected', False, None, False),
            ('rejected', False, timezone.now() + timedelta(days=1), False),
            ('rejected', False, past, True),
        ]:
            self.post(); row = AdmissionApplication.objects.latest('created_at')
            AdmissionApplication.objects.filter(pk=row.pk).update(status=status, retention_hold=hold, retention_expires_at=expiry)
            call_command('purge_intake_records', stdout=StringIO())
            self.assertTrue(AdmissionApplication.objects.filter(pk=row.pk).exists())
            call_command('purge_intake_records', execute=True, stdout=StringIO())
            self.assertEqual(AdmissionApplication.objects.filter(pk=row.pk).exists(), not deleted)
        for status, hold, expiry, deleted in [
            ('new', False, past, False), ('in_progress', False, past, False),
            ('resolved', True, past, False), ('resolved', False, None, False),
            ('resolved', False, past, True),
        ]:
            self.post(enquiry(), kind='enquiries'); row = ContactEnquiry.objects.latest('created_at')
            ContactEnquiry.objects.filter(pk=row.pk).update(status=status, retention_hold=hold, retention_expires_at=expiry)
            call_command('purge_intake_records', execute=True, stdout=StringIO())
            self.assertEqual(ContactEnquiry.objects.filter(pk=row.pk).exists(), not deleted)
        retained = AdmissionApplication.objects.count()
        PublicIntakeKey.objects.update(expires_at=past)
        call_command('purge_intake_records', execute=True, stdout=StringIO())
        self.assertFalse(PublicIntakeKey.objects.exists())
        self.assertEqual(AdmissionApplication.objects.count(), retained)

    def test_migration_repairs_legacy_expiry_from_transition_evidence(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        from django.db import connection
        migration = import_module('core.migrations.0023_intake_retention_lifecycle')
        for kind, body, model, terminal in [
            ('application', application(), AdmissionApplication, 'rejected'),
            ('enquiry', enquiry(), ContactEnquiry, 'resolved'),
        ]:
            self.post(body, kind='applications' if kind == 'application' else 'enquiries')
            row = model.objects.latest('created_at')
            row = review(kind, self.school, self.admin, row.pk, {'version': 1, 'status': terminal})
            decided = datetime(2024, 1, 31, 10, tzinfo=dt_timezone.utc)
            row.history.update(created_at=decided)
            review(kind, self.school, self.admin, row.pk, {'version': 2, 'note': 'TEST later note'})
            self.post(body, kind='applications' if kind == 'application' else 'enquiries')
            missing = model.objects.latest('created_at')
            model.objects.filter(pk=missing.pk).update(status=terminal)
            self.post(body, kind='applications' if kind == 'application' else 'enquiries')
            pending = model.objects.latest('created_at')
            model.objects.all().update(retention_expires_at=timezone.now())
            migration.repair_retention(apps, SimpleNamespace(connection=connection))
            row.refresh_from_db(); missing.refresh_from_db(); pending.refresh_from_db()
            self.assertEqual(row.retention_expires_at, one_calendar_month_after(decided))
            self.assertIsNone(missing.retention_expires_at)
            self.assertIsNone(pending.retention_expires_at)
