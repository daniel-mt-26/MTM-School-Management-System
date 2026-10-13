"""Synthetic records and mocked SMTP only; tests cannot send real email."""
import smtplib
import ssl
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import AuditLog, Student, Parent, StudentEnrollment
from .intake_models import AdmissionApplication, ContactEnquiry, IntakeEmailOutbox
from .intake_email import build_message, claim_job, process_email, smtp_ready
from .test_intake import CONFIG, application, enquiry, school

SMTP_PATH = "django.core.mail.backends.smtp.EmailBackend.send_messages"
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.smtp.EmailBackend", "OPTIONS": {"host": "smtp.example.invalid", "port": 587, "username": "TEST_SMTP_USER", "password": "TEST_SMTP_PASSWORD", "use_tls": True, "use_ssl": False, "timeout": 15}}}
EMAIL_CONFIG = dict(CONFIG, MTM_INTAKE_EMAIL_ENABLED=True, MTM_INTAKE_SMTP_VERIFIED=True, MAILERS=MAILERS, DEFAULT_FROM_EMAIL="approved-sender@example.invalid", MTM_INTAKE_DASHBOARD_URL="https://mtm.example.invalid", MTM_INTAKE_CONTACT_EMAIL="beaversecdcentre@gmail.com", MTM_INTAKE_CONTACT_PHONES="+263 775 177 935 / +263 772 405 912")


@override_settings(**EMAIL_CONFIG)
class IntakeEmailTests(APITestCase):
    def setUp(self):
        self.school = school("TEST email school")
        self.binding = override_settings(MTM_INTAKE_BEAVERS_SCHOOL_ID=self.school.pk)
        self.binding.enable()
        self.addCleanup(self.binding.disable)

    def submit(self, kind="applications", key=None):
        body = application() if kind == "applications" else enquiry()
        return self.client.post(f"/api/public/beavers/{kind}/", body, format="json", HTTP_IDEMPOTENCY_KEY=str(key or uuid4()))

    def deliver(self, **kwargs):
        with patch(SMTP_PATH, return_value=1, **kwargs) as send:
            result = process_email()
        messages = [call.args[0][0] for call in send.call_args_list]
        return result, messages

    def test_all_four_templates_subjects_recipients_and_minimal_content(self):
        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(self.submit("enquiries").status_code, 201)
        result, messages = self.deliver()
        self.assertEqual(result, {"enabled": True, "sent": 4, "failed": 0})
        by_subject = {message.subject: message for message in messages}
        school_app = by_subject["New Admission Application \u2013 Beavers Junior School"]
        ack_app = by_subject["Admission Application Received \u2013 Beavers Junior School"]
        school_enquiry = by_subject["New Website Enquiry \u2013 Beavers Junior School"]
        ack_enquiry = by_subject["Enquiry Received \u2013 Beavers Junior School"]
        app, contact = AdmissionApplication.objects.get(), ContactEnquiry.objects.get()
        for message, record, route in [(school_app, app, "admissions"), (school_enquiry, contact, "enquiries")]:
            self.assertEqual(message.to, ["beaversecdcentre@gmail.com"])
            self.assertIn(record.reference, message.body)
            self.assertIn("Submission date:", message.body)
            self.assertIn("CAT", message.body)
            self.assertIn(f"https://mtm.example.invalid/school/{route}/{record.pk}", message.body)
        self.assertIn("Requested grade: Grade 1", school_app.body)
        for message, record in [(ack_app, app), (ack_enquiry, contact)]:
            self.assertEqual(message.to, [record.email])
            self.assertIn(record.reference, message.body)
            self.assertIn("Beavers Junior School", message.body)
            self.assertIn("beaversecdcentre@gmail.com", message.body)
            self.assertIn("+263 775 177 935", message.body)
        self.assertIn("pending review", ack_app.body)
        self.assertIn("does not guarantee admission", ack_app.body)
        self.assertIn("respond through the contact information", ack_enquiry.body)
        private = [app.student_name, app.guardian_name, app.address, str(app.date_of_birth), contact.full_name, contact.subject, contact.message, "TEST_SMTP_USER", "TEST_SMTP_PASSWORD"]
        for message in messages:
            self.assertEqual(message.from_email, "approved-sender@example.invalid")
            self.assertEqual(message.reply_to, ["beaversecdcentre@gmail.com"])
            self.assertFalse(message.attachments)
            for value in private:
                self.assertNotIn(value, message.subject + message.body)
            self.assertNotIn("24 hours", message.body)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(Parent.objects.count(), 0)
        self.assertEqual(StudentEnrollment.objects.count(), 0)

    def test_idempotent_retries_do_not_duplicate_or_resend_acknowledgements(self):
        for kind in ["applications", "enquiries"]:
            key = uuid4()
            first = self.submit(kind, key)
            self.assertEqual(first.status_code, 201)
            self.assertEqual(self.submit(kind, key).status_code, 200)
            self.assertEqual(self.deliver()[0]["sent"], 2)
            again = self.submit(kind, key)
            self.assertEqual(again.data["reference"], first.data["reference"])
            self.assertEqual(self.deliver()[0]["sent"], 0)
        self.assertEqual(IntakeEmailOutbox.objects.count(), 4)
        self.assertTrue(all(job.attempts == 1 for job in IntakeEmailOutbox.objects.all()))

    def test_outbox_creation_is_atomic_and_does_not_call_smtp(self):
        with patch(SMTP_PATH) as send:
            self.submit()
            send.assert_not_called()
        self.assertEqual(IntakeEmailOutbox.objects.count(), 2)
        AdmissionApplication.objects.all().delete()
        with patch("core.intake_services.IntakeEmailOutbox.objects.create", side_effect=RuntimeError("TEST transaction failure")):
            self.assertEqual(self.submit().status_code, 500)
        self.assertEqual(AdmissionApplication.objects.count(), 0)
        self.assertEqual(IntakeEmailOutbox.objects.count(), 0)

    def test_temporary_smtp_error_backoff_and_successful_retry(self):
        self.submit()
        with patch(SMTP_PATH, side_effect=smtplib.SMTPDataError(451, b"PRIVATE PROVIDER DETAIL")) as send:
            self.assertEqual(process_email()["failed"], 2)
            self.assertEqual(send.call_count, 2)
        jobs = list(IntakeEmailOutbox.objects.all())
        self.assertTrue(all(job.failure_code == "smtp_temporary" and job.attempts == 1 and job.next_attempt_at > timezone.now() for job in jobs))
        with patch(SMTP_PATH) as send:
            self.assertEqual(process_email()["sent"], 0)
            send.assert_not_called()
        IntakeEmailOutbox.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        result, _ = self.deliver()
        self.assertEqual(result["sent"], 2)
        self.assertEqual(AdmissionApplication.objects.count(), 1)
        self.assertTrue(all(job.status == "sent" and job.attempts == 2 for job in IntakeEmailOutbox.objects.all()))

    def test_permanent_recipient_failure_is_not_retried_or_count_inflated(self):
        self.submit()
        with patch(SMTP_PATH, side_effect=smtplib.SMTPRecipientsRefused({"test@example.invalid": (550, b"PRIVATE ADDRESS DETAIL")})):
            self.assertEqual(process_email()["failed"], 2)
        IntakeEmailOutbox.objects.update(next_attempt_at=timezone.now() - timedelta(days=1))
        with patch(SMTP_PATH) as send:
            self.assertEqual(process_email()["sent"], 0)
            send.assert_not_called()
        self.assertTrue(all(job.failure_code == "smtp_permanent" and job.attempts == 1 for job in IntakeEmailOutbox.objects.all()))

    def test_temporary_recipient_and_authentication_errors_retry(self):
        self.submit()
        for failure in [smtplib.SMTPRecipientsRefused({"test@example.invalid": (450, b"PRIVATE")}), smtplib.SMTPAuthenticationError(454, b"PRIVATE")]:
            with patch(SMTP_PATH, side_effect=failure):
                self.assertEqual(process_email()["failed"], 2)
            self.assertTrue(all(job.failure_code == "smtp_temporary" for job in IntakeEmailOutbox.objects.all()))
            IntakeEmailOutbox.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))

    def test_permanent_sender_auth_or_certificate_failure_stops_batch(self):
        self.submit()
        for failure in [smtplib.SMTPAuthenticationError(535, b"PRIVATE credentials"), smtplib.SMTPSenderRefused(550, b"PRIVATE sender", "private@example.invalid"), ssl.SSLCertVerificationError("PRIVATE certificate")]:
            IntakeEmailOutbox.objects.update(status="pending", failure_code="", attempts=0, next_attempt_at=timezone.now() - timedelta(seconds=1))
            with patch(SMTP_PATH, side_effect=failure) as send:
                self.assertEqual(process_email()["failed"], 1)
                self.assertEqual(send.call_count, 1)
            self.assertEqual(IntakeEmailOutbox.objects.filter(failure_code="smtp_configuration").count(), 1)
            self.assertEqual(AdmissionApplication.objects.count(), 1)

    def test_retry_exhaustion_is_bounded_and_no_submission_rollback(self):
        self.submit()
        with override_settings(MTM_INTAKE_EMAIL_MAX_ATTEMPTS=2), patch(SMTP_PATH, side_effect=TimeoutError("PRIVATE timeout")) as send:
            self.assertEqual(process_email()["failed"], 2)
            IntakeEmailOutbox.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
            self.assertEqual(process_email()["failed"], 2)
            IntakeEmailOutbox.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
            self.assertEqual(process_email()["failed"], 0)
            self.assertEqual(send.call_count, 4)
        self.assertEqual(AdmissionApplication.objects.count(), 1)
        self.assertTrue(all(job.attempts == 2 for job in IntakeEmailOutbox.objects.all()))

    def test_stable_message_id_on_retry_and_metadata_only_audit(self):
        self.submit()
        captured = []
        def fail(messages):
            captured.extend(messages)
            raise OSError("PRIVATE credentials, child details and provider response")
        with patch(SMTP_PATH, side_effect=fail):
            process_email()
        previous = {message.to[0]: message.extra_headers["Message-ID"] for message in captured}
        IntakeEmailOutbox.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        _, messages = self.deliver()
        self.assertEqual(previous, {message.to[0]: message.extra_headers["Message-ID"] for message in messages})
        self.assertEqual(AuditLog.objects.filter(action="intake.email.failed").count(), 2)
        self.assertEqual(AuditLog.objects.filter(action="intake.email.sent").count(), 2)
        details = " ".join(AuditLog.objects.values_list("description", flat=True)) + " ".join(IntakeEmailOutbox.objects.values_list("failure_code", flat=True))
        for value in ["PRIVATE", "test@example.invalid", "TEST learner", "TEST_SMTP_PASSWORD"]:
            self.assertNotIn(value, details)

    def test_command_execution_failure_flags_and_limit_validation(self):
        self.submit()
        stream = StringIO()
        with patch(SMTP_PATH, return_value=1) as send:
            call_command("process_intake_email", limit=1, require_enabled=True, fail_on_error=True, stdout=stream)
            self.assertEqual(send.call_count, 1)
        self.assertIn("enabled=True sent=1 failed=0", stream.getvalue())
        with patch(SMTP_PATH, side_effect=OSError("PRIVATE")):
            with self.assertRaises(CommandError):
                call_command("process_intake_email", fail_on_error=True, stdout=StringIO())
        for limit in [0, 1001]:
            with self.assertRaises(CommandError):
                call_command("process_intake_email", limit=limit, stdout=StringIO())
        with override_settings(MTM_INTAKE_EMAIL_ENABLED=False), patch(SMTP_PATH) as send:
            with self.assertRaises(CommandError):
                call_command("process_intake_email", require_enabled=True, stdout=StringIO())
            send.assert_not_called()

    def test_settings_gates_fail_closed_without_spending_attempts(self):
        self.submit()
        for config in [dict(MTM_INTAKE_EMAIL_ENABLED=False), dict(MTM_INTAKE_SMTP_VERIFIED=False), dict(MTM_INTAKE_DASHBOARD_URL="http://unapproved.invalid"), dict(MTM_INTAKE_DASHBOARD_URL="https://user:password@mtm.example.invalid"), dict(MTM_INTAKE_DASHBOARD_URL="https://mtm.example.invalid/login"), dict(DEFAULT_FROM_EMAIL="webmaster@localhost"), dict(MTM_INTAKE_BEAVERS_SCHOOL_ID=0), dict(MTM_INTAKE_CONTACT_EMAIL="invalid"), dict(MTM_INTAKE_EMAIL_LEASE_SECONDS=10)]:
            with override_settings(**config), patch(SMTP_PATH) as send:
                self.assertFalse(process_email()["enabled"])
                send.assert_not_called()
        self.assertTrue(all(job.attempts == 0 for job in IntakeEmailOutbox.objects.all()))

    def test_implicit_tls_supported_but_plaintext_or_conflicting_tls_rejected(self):
        options = {**MAILERS["default"]["OPTIONS"], "use_tls": False, "use_ssl": True, "port": 465}
        with override_settings(MAILERS={"default": {"BACKEND": MAILERS["default"]["BACKEND"], "OPTIONS": options}}):
            self.assertTrue(smtp_ready())
        for tls, ssl_flag in [(False, False), (True, True)]:
            with override_settings(MAILERS={"default": {"BACKEND": MAILERS["default"]["BACKEND"], "OPTIONS": {**options, "use_tls": tls, "use_ssl": ssl_flag}}}):
                self.assertFalse(smtp_ready())

    def test_expired_record_is_never_delivered(self):
        self.submit()
        AdmissionApplication.objects.update(retention_expires_at=timezone.now() - timedelta(seconds=1))
        with patch(SMTP_PATH) as send:
            self.assertEqual(process_email()["sent"], 0)
            send.assert_not_called()

    def test_leases_prevent_reclaim_and_recover_stale_attempt(self):
        self.submit()
        claimed = claim_job()
        other = claim_job()
        self.assertNotEqual(claimed.pk, other.pk)
        self.assertIsNone(claim_job())
        IntakeEmailOutbox.objects.filter(pk=claimed.pk).update(claimed_at=timezone.now() - timedelta(seconds=601))
        reclaimed = claim_job()
        self.assertEqual(reclaimed.pk, claimed.pk)
        self.assertNotEqual(reclaimed.claim_token, claimed.claim_token)
        self.assertEqual(reclaimed.attempts, 2)

    def test_exhausted_crashed_lease_becomes_delivery_uncertain(self):
        self.submit()
        IntakeEmailOutbox.objects.update(status="sending", attempts=5, claimed_at=timezone.now() - timedelta(seconds=601))
        with patch(SMTP_PATH) as send:
            self.assertEqual(process_email()["failed"], 2)
            send.assert_not_called()
        self.assertTrue(all(job.failure_code == "delivery_uncertain" and job.status == "failed" and job.attempts == 5 for job in IntakeEmailOutbox.objects.all()))

    def test_worker_only_delivers_configured_school(self):
        self.submit()
        other_school = school("TEST other email school")
        with override_settings(MTM_INTAKE_BEAVERS_SCHOOL_ID=other_school.pk):
            self.submit("enquiries")
        result, _ = self.deliver()
        self.assertEqual(result["sent"], 2)
        self.assertEqual(IntakeEmailOutbox.objects.filter(enquiry__school=other_school, attempts=0).count(), 2)

    def test_recipient_tampering_or_configuration_change_requires_review(self):
        self.submit()
        IntakeEmailOutbox.objects.update(recipient="unexpected@example.invalid")
        with patch(SMTP_PATH) as send:
            self.assertEqual(process_email()["failed"], 2)
            send.assert_not_called()
        self.assertTrue(all(job.failure_code == "recipient_mismatch" for job in IntakeEmailOutbox.objects.all()))

    def test_invalid_recipient_and_unconfirmed_send_are_not_success(self):
        self.submit()
        IntakeEmailOutbox.objects.filter(purpose="ack").update(recipient="bad\r\nBcc: private@example.invalid")
        with patch(SMTP_PATH, return_value=0) as send:
            self.assertEqual(process_email()["failed"], 2)
            self.assertEqual(send.call_count, 1)
        self.assertFalse(IntakeEmailOutbox.objects.filter(status="sent").exists())

    def test_acknowledgement_after_review_is_still_a_receipt_not_a_decision(self):
        self.submit()
        record = AdmissionApplication.objects.get()
        AdmissionApplication.objects.filter(pk=record.pk).update(status="approved")
        message = build_message(IntakeEmailOutbox.objects.get(purpose="ack"), record)
        self.assertIn("pending review when submitted", message.body)
        self.assertIn("does not guarantee admission", message.body)
        self.assertNotIn("approved", message.body)
