"""All personal data is synthetic; provider calls are mocked, never sent."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
import json
from io import StringIO
from unittest.mock import patch, MagicMock
from uuid import uuid4
from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError, close_old_connections, connection
from django.test import override_settings, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from .models import School, User, SchoolAdministrator, Student, StudentEnrollment, AuditLog
from .intake_models import AdmissionApplication, ContactEnquiry, PublicIntakeKey, IntakeEmailOutbox, AdmissionReviewHistory, IntakeRateBucket
from .intake_services import review
from .intake_security import IntakeConflict, consume_quotas
from .intake_email import process_email, claim_job
from .authentication import MTMTokenObtainPairSerializer


CONFIG = dict(MTM_INTAKE_ENABLED=True, MTM_INTAKE_PRIVACY_APPROVED=True, MTM_INTAKE_PRIVACY_VERSION="test-v1", MTM_INTAKE_KEY_RETENTION_DAYS=10, MTM_INTAKE_ALLOWED_ORIGINS=["https://beavers.example.invalid"], MTM_INTAKE_CHALLENGE_REQUIRED=False, MTM_INTAKE_IP_LIMIT=1000, MTM_INTAKE_SCHOOL_LIMIT=2000, MTM_INTAKE_RECIPIENT_LIMIT=100, IS_PRODUCTION=False, MTM_INTAKE_EMAIL_ENABLED=False)


def school(name="Test Beavers"):
    return School.objects.create(name=name, email=name.replace(" ", "").lower()+"@example.invalid", phone_number="+263775177935")


def administrator(tenant, username):
    user = User.objects.create_user(username=username, password="Synthetic-intake-test-only-483!", role=User.Role.SCHOOL_ADMIN)
    SchoolAdministrator.objects.create(school=tenant, user=user)
    return user


def application():
    return {"studentName": "TEST learner", "dateOfBirth": "2019-02-01", "grade": "Grade 1", "guardianName": "TEST guardian", "phone": "+263 775 177 935", "email": "test@example.invalid", "address": "TEST address", "consent": True, "privacyPolicyVersion": "test-v1"}


def enquiry():
    return {"fullName": "TEST visitor", "email": "visitor@example.invalid", "phone": "+263775177935", "subject": "TEST subject", "message": "TEST enquiry", "consent": True, "privacyPolicyVersion": "test-v1"}


@override_settings(**CONFIG)
class IntakeAPITests(APITestCase):
    def setUp(self):
        self.school = school()
        self.other = school("Other test school")
        self.admin = administrator(self.school, "test-admin")
        self.other_admin = administrator(self.other, "other-test-admin")
        self.binding = override_settings(MTM_INTAKE_BEAVERS_SCHOOL_ID=self.school.pk)
        self.binding.enable()
        self.addCleanup(self.binding.disable)

    def post(self, data=None, key=None, kind="applications"):
        return self.client.post(f"/api/public/beavers/{kind}/", data if data is not None else application(), format="json", HTTP_IDEMPOTENCY_KEY=str(key or uuid4()))

    def login(self, user=None):
        token = MTMTokenObtainPairSerializer.get_token(user or self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_application_saved_reference_outbox_audit_and_no_enrolment(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        row = AdmissionApplication.objects.get()
        self.assertEqual(row.school, self.school)
        self.assertEqual(row.reference, response.data["reference"])
        self.assertEqual(row.status, "pending")
        self.assertIsNone(row.retention_expires_at)
        self.assertTrue(response.data["saved"])
        self.assertNotIn("studentName", response.data)
        self.assertEqual(IntakeEmailOutbox.objects.count(), 2)
        self.assertEqual(AuditLog.objects.get().actor, None)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(StudentEnrollment.objects.count(), 0)

    def test_enquiry_saved(self):
        response = self.post(enquiry(), kind="enquiries")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ContactEnquiry.objects.get().status, "new")
        self.assertEqual(IntakeEmailOutbox.objects.filter(purpose="school").get().recipient, "beaversecdcentre@gmail.com")

    def test_unknown_and_forged_fields_are_rejected(self):
        for key in ["school", "school_id", "schoolId", "reviewer", "status", "extra"]:
            response = self.post({**application(), key: self.other.pk})
            self.assertEqual(response.status_code, 400, key)
        self.assertFalse(AdmissionApplication.objects.exists())

    def test_missing_false_and_nonboolean_consent(self):
        for value in [False, "true", None]:
            response = self.post({**application(), "consent": value})
            self.assertEqual(response.status_code, 400)
        data = application(); data.pop("consent")
        self.assertEqual(self.post(data).status_code, 400)

    def test_invalid_fields(self):
        for field, value in [("email", "invalid"), ("phone", "letters"), ("dateOfBirth", "2099-01-01"), ("dateOfBirth", "2026-02-30"), ("grade", "Grade 8"), ("studentName", " "), ("privacyPolicyVersion", "old"), ("website", "bot-site")]:
            self.assertEqual(self.post({**application(), field: value}).status_code, 400, field)

    def test_missing_uuid_and_invalid_key(self):
        for headers in [{}, {"HTTP_IDEMPOTENCY_KEY": "bad-key"}]:
            self.assertEqual(self.client.post("/api/public/beavers/applications/", application(), format="json", **headers).status_code, 400)

    def test_idempotent_replay_and_conflict(self):
        key = uuid4()
        first = self.post(key=key)
        again = self.post(key=key)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.data, again.data)
        self.assertEqual(self.post({**application(), "studentName": "Different TEST name"}, key=key).status_code, 409)
        self.assertEqual(AdmissionApplication.objects.count(), 1)
        self.assertEqual(IntakeEmailOutbox.objects.count(), 2)
        self.assertEqual(PublicIntakeKey.objects.count(), 1)

    def test_disabled_unconfigured_or_suspended_school(self):
        for options in [dict(MTM_INTAKE_ENABLED=False), dict(MTM_INTAKE_PRIVACY_APPROVED=False), dict(MTM_INTAKE_BEAVERS_SCHOOL_ID=0), dict(MTM_INTAKE_KEY_RETENTION_DAYS=0)]:
            with override_settings(**options):
                self.assertEqual(self.post().status_code, 503)
        self.school.status = "suspended"; self.school.save()
        self.assertEqual(self.post().status_code, 503)
        self.assertFalse(AdmissionApplication.objects.exists())

    def test_demo_and_archived_school_rejected(self):
        self.school.is_demo=True; self.school.save()
        self.assertEqual(self.post().status_code, 503)
        self.school.is_demo=False; self.school.status="archived"; self.school.save()
        self.assertEqual(self.post().status_code, 503)

    def test_public_create_only_and_request_size(self):
        self.assertEqual(self.client.get("/api/public/beavers/applications/").status_code, 405)
        with override_settings(MTM_INTAKE_MAX_BYTES=100):
            self.assertEqual(self.post().status_code, 413)
        self.assertEqual(self.client.post("/api/public/beavers/applications/", '{"consent":true,"consent":false}', content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 400)

        for raw in ["[" * 1100 + "]" * 1100, '{"studentName":NaN}']:
            self.assertEqual(self.client.post("/api/public/beavers/applications/", raw, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 400)

    def test_origin_and_challenge_fail_closed(self):
        response = self.client.post("/api/public/beavers/applications/", application(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()), HTTP_ORIGIN="https://untrusted.invalid")
        self.assertEqual(response.status_code, 400)
        with override_settings(IS_PRODUCTION=True, MTM_INTAKE_CHALLENGE_REQUIRED=False):
            self.assertEqual(self.post().status_code, 503)
        with override_settings(MTM_INTAKE_CHALLENGE_REQUIRED=True, MTM_INTAKE_CHALLENGE_SECRET=""):
            self.assertEqual(self.post().status_code, 503)

    def test_ip_and_recipient_rate_limits(self):
        with override_settings(MTM_INTAKE_IP_LIMIT=1):
            self.assertEqual(self.post().status_code, 201)
            self.assertEqual(self.post().status_code, 429)
        IntakeRateBucket.objects.all().delete()
        with override_settings(MTM_INTAKE_RECIPIENT_LIMIT=1):
            self.assertEqual(self.post({**application(), "email": "limited@example.invalid"}).status_code, 201)
            self.assertEqual(self.post({**application(), "email": "limited@example.invalid"}).status_code, 429)

    def test_database_failure_rolls_back_submission(self):
        with patch("core.intake_services.log_action", side_effect=OperationalError("PRIVATE DB DETAIL")):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("PRIVATE", str(response.data))
        self.assertEqual(AdmissionApplication.objects.count(), 0)
        self.assertEqual(PublicIntakeKey.objects.count(), 0)
        self.assertEqual(IntakeEmailOutbox.objects.count(), 0)

    def test_unauthorised_and_cross_school_access(self):
        reference = self.post().data["reference"]
        row = AdmissionApplication.objects.get(reference=reference)
        endpoint = f"/api/school/applications/{row.pk}/"
        self.assertEqual(self.client.get(endpoint).status_code, 401)
        self.login(self.other_admin)
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertEqual(self.client.get(endpoint+"history/").status_code, 404)
        self.assertEqual(self.client.post(endpoint+"review/", {"version": 1, "status": "approved"}, format="json").status_code, 404)
        self.assertEqual(self.client.get("/api/school/applications/").data["count"], 0)

    def test_review_history_conflict_and_no_enrolment(self):
        self.post(); row = AdmissionApplication.objects.get(); self.login()
        endpoint=f"/api/school/applications/{row.pk}/review/"
        response=self.client.post(endpoint,{"version":1,"status":"approved","note":"TEST private note"},format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.post(endpoint,{"version":1,"status":"rejected"},format="json").status_code,409)
        row.refresh_from_db(); self.assertEqual(row.version,2); self.assertEqual(row.reviewer,self.admin)
        self.assertEqual(AdmissionReviewHistory.objects.count(),1)
        self.assertNotIn("TEST private note",AuditLog.objects.last().description)
        history=self.client.get(f"/api/school/applications/{row.pk}/history/")
        self.assertEqual(history.data["count"],1)
        self.assertEqual(Student.objects.count(),0)
        self.assertEqual(StudentEnrollment.objects.count(),0)

    def test_enquiry_assignment_and_review_scope(self):
        self.post(enquiry(),kind="enquiries"); row=ContactEnquiry.objects.get(); self.login()
        endpoint=f"/api/school/enquiries/{row.pk}/review/"
        foreign=self.other_admin.school_administrator.pk
        self.assertEqual(self.client.post(endpoint,{"version":1,"assignedAdministratorId":foreign},format="json").status_code,400)
        own=self.admin.school_administrator.pk
        response=self.client.post(endpoint,{"version":1,"status":"in_progress","assignedAdministratorId":own,"note":"TEST handling note"},format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get(f"/api/school/enquiries/{row.pk}/history/").data["count"],1)
        self.assertEqual(self.client.post(endpoint,{"version":2,"status":"resolved"},format="json").status_code,200)

    def test_parent_and_password_change_cannot_review(self):
        self.post(); row=AdmissionApplication.objects.get()
        parent=User.objects.create_user(username="test-parent",role=User.Role.PARENT)
        self.client.force_authenticate(parent)
        self.assertEqual(self.client.get("/api/school/applications/").status_code,403)
        self.client.force_authenticate(self.admin)
        self.admin.must_change_password=True
        self.assertEqual(self.client.post(f"/api/school/applications/{row.pk}/review/",{"version":1,"status":"approved"},format="json").status_code,403)

    def test_email_disabled_and_delivery_failure_preserves_saved_record(self):
        self.post()
        with patch("core.intake_email.mailers") as get_connection:
            self.assertFalse(process_email()["enabled"])
            get_connection.default.send_messages.assert_not_called()
        fake_mailers={"default":{"BACKEND":"django.core.mail.backends.smtp.EmailBackend","OPTIONS":{"host":"smtp.example.invalid","username":"test","password":"TEST ONLY","use_tls":True,"timeout":15}}}
        with override_settings(MTM_INTAKE_EMAIL_ENABLED=True,MTM_INTAKE_SMTP_VERIFIED=True,MAILERS=fake_mailers,DEFAULT_FROM_EMAIL="school@example.invalid",MTM_INTAKE_DASHBOARD_URL="https://mtm.example.invalid"):
            with patch("core.intake_email.mailers") as get_connection:
                get_connection.default.send_messages.side_effect=OSError("PRIVATE PROVIDER DETAIL")
                result=process_email()
            self.assertEqual(result["failed"],2)
            self.assertEqual(AdmissionApplication.objects.count(),1)
            self.assertTrue(all(job.failure_code=="provider_error" for job in IntakeEmailOutbox.objects.all()))
            IntakeEmailOutbox.objects.update(next_attempt_at=timezone.now()-timedelta(seconds=1))
            with patch("core.intake_email.mailers") as get_connection:
                get_connection.default.send_messages.return_value=1
                result=process_email()
            self.assertEqual(result["sent"],2)
            self.assertEqual(IntakeEmailOutbox.objects.filter(status="sent").count(),2)


    def test_turnstile_verification_and_replay_no_network_retry(self):
        mocked = MagicMock()
        mocked.__enter__.return_value.read.return_value = json.dumps({"success": True, "hostname": "beavers.example.invalid", "action": "beavers_intake"}).encode()
        key = uuid4()
        with override_settings(MTM_INTAKE_CHALLENGE_REQUIRED=True, MTM_INTAKE_CHALLENGE_SECRET="TEST ONLY SECRET"):
            with patch("core.intake_security.urlopen", return_value=mocked) as verify:
                first = self.post({**application(), "challengeToken": "TEST challenge"}, key=key)
                again = self.post(application(), key=key)
            self.assertEqual(first.status_code, 201)
            self.assertEqual(again.status_code, 200)
            self.assertEqual(verify.call_count, 1)
        self.assertEqual(AdmissionApplication.objects.count(), 1)

    def test_challenge_hostname_action_and_network_failure(self):
        with override_settings(MTM_INTAKE_CHALLENGE_REQUIRED=True, MTM_INTAKE_CHALLENGE_SECRET="TEST ONLY SECRET"):
            self.assertEqual(self.post().status_code, 400)
            for outcome in [{"success": False}, {"success": True, "hostname": "wrong.invalid", "action": "beavers_intake"}, {"success": True, "hostname": "beavers.example.invalid", "action": "wrong"}]:
                mocked = MagicMock(); mocked.__enter__.return_value.read.return_value = json.dumps(outcome).encode()
                with patch("core.intake_security.urlopen", return_value=mocked):
                    self.assertEqual(self.post({**application(), "challengeToken": "TEST challenge"}).status_code, 400)
            with patch("core.intake_security.urlopen", side_effect=OSError("PRIVATE verification failure")):
                response = self.post({**application(), "challengeToken": "TEST challenge"})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("PRIVATE", str(response.data))
        self.assertEqual(AdmissionApplication.objects.count(), 0)

    def test_no_query_ownership_or_non_text_input(self):
        response = self.client.post(f"/api/public/beavers/applications/?school_id={self.other.pk}", application(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post({**application(), "studentName": 123}).status_code, 400)

    def test_cors_idempotency_preflight(self):
        with override_settings(CORS_ALLOWED_ORIGINS=["https://beavers.example.invalid"]):
            response = self.client.options("/api/public/beavers/applications/", HTTP_ORIGIN="https://beavers.example.invalid", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,idempotency-key")
        self.assertEqual(response.status_code, 200)
        self.assertIn("idempotency-key", response["Access-Control-Allow-Headers"])

    def test_public_origin_does_not_expand_staff_cors(self):
        with override_settings(CORS_ALLOWED_ORIGINS=[]):
            headers=dict(HTTP_ORIGIN="https://beavers.example.invalid", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,idempotency-key")
            allowed=self.client.options("/api/public/beavers/applications/", **headers)
            blocked=self.client.options("/api/school/applications/", **headers)
        self.assertEqual(allowed["Access-Control-Allow-Origin"],"https://beavers.example.invalid")
        self.assertNotIn("Access-Control-Allow-Origin",blocked)

    def test_proxy_headers_only_trusted_when_configured(self):
        from rest_framework.test import APIRequestFactory
        from core.intake_security import client_ip
        request = APIRequestFactory().post("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="192.0.2.55, 10.0.0.2")
        self.assertEqual(client_ip(request), "127.0.0.1")
        with override_settings(MTM_INTAKE_TRUSTED_PROXY_CIDRS=["127.0.0.0/8", "10.0.0.0/8"]):
            self.assertEqual(client_ip(request), "192.0.2.55")
        external = APIRequestFactory().post("/", REMOTE_ADDR="192.0.2.7", HTTP_X_FORWARDED_FOR="192.0.2.99")
        with override_settings(MTM_INTAKE_TRUSTED_PROXY_CIDRS=["127.0.0.0/8"]):
            self.assertEqual(client_ip(external), "192.0.2.7")

    def test_revoked_and_suspended_admin_jwt_denied(self):
        self.post(); self.login()
        self.admin.token_version += 1; self.admin.save()
        self.assertEqual(self.client.get("/api/school/applications/").status_code, 401)
        self.login()
        self.school.status = "suspended"; self.school.save()
        self.assertEqual(self.client.get("/api/school/applications/").status_code, 401)

    def test_retention_dry_run_and_expired_jobs(self):
        self.post(); row=AdmissionApplication.objects.get()
        AdmissionApplication.objects.filter(pk=row.pk).update(status="rejected", retention_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertIsNone(claim_job())
        stream=StringIO()
        call_command("purge_intake_records", stdout=stream)
        self.assertEqual(AdmissionApplication.objects.count(), 1)
        call_command("purge_intake_records", execute=True, stdout=stream)
        self.assertEqual(AdmissionApplication.objects.count(), 0)
        self.assertEqual(IntakeEmailOutbox.objects.count(), 0)
        self.assertEqual(PublicIntakeKey.objects.count(), 0)
        self.assertTrue(AuditLog.objects.filter(action="intake.application.purged").exists())


@override_settings(**CONFIG)
class IntakeConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.school=school();self.admin=administrator(self.school,"concurrency-test-admin")
        with override_settings(MTM_INTAKE_BEAVERS_SCHOOL_ID=self.school.pk):
            client=APIClient(); client.post("/api/public/beavers/applications/",application(),format="json",HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.record=AdmissionApplication.objects.get()
        self.binding=override_settings(MTM_INTAKE_BEAVERS_SCHOOL_ID=self.school.pk)
        self.binding.enable()
        self.addCleanup(self.binding.disable)

    def test_concurrent_reviews_only_one_version_wins(self):
        self.assertEqual(connection.vendor,"postgresql")
        barrier=Barrier(2)
        def attempt(status):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    review("application",self.school,self.admin,self.record.pk,{"version":1,"status":status})
                    return "saved"
                except IntakeConflict:
                    return "conflict"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,["approved","rejected"]))
        self.assertCountEqual(results,["saved","conflict"])
        self.assertEqual(AdmissionReviewHistory.objects.count(),1)

    def test_shared_atomic_rate_counter(self):
        barrier=Barrier(2)
        def attempt(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    consume_quotas([("test","same",1,3600)])
                    return "allowed"
                except Exception as exc:
                    return exc.__class__.__name__
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,[0,1]))
        self.assertCountEqual(results,["allowed","Throttled"])


    def test_concurrent_submissions_replay_one_saved_record(self):
        from core.intake_services import submit
        from core.intake_serializers import ApplicationInput
        before = AdmissionApplication.objects.count()
        serializer=ApplicationInput(data={**application(), "email":"concurrent@example.invalid"})
        self.assertTrue(serializer.is_valid())
        operation=uuid4(); barrier=Barrier(2)
        def attempt(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                result, created=submit("application",self.school,operation,serializer.validated_data)
                return result["reference"], created
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,[0,1]))
        self.assertEqual(results[0][0],results[1][0])
        self.assertCountEqual([value[1] for value in results],[True,False])
        self.assertEqual(AdmissionApplication.objects.count(),before+1)

    def test_concurrent_email_claims_are_unique(self):
        barrier=Barrier(2)
        def attempt(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                job=claim_job()
                return job.pk if job else None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,[0,1]))
        self.assertNotIn(None,results)
        self.assertEqual(len(set(results)),2)
