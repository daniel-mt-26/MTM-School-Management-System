import copy
from io import StringIO
import json
import os
from pathlib import Path
import secrets
import tempfile
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from rest_framework.test import APITestCase

from core.models import (
    AcademicYear, AuditLog, Parent, Payment, School, SchoolAdministrator,
    SchoolClass, Student, Term, User,
)


class ProvisionSchoolTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "school.json"
        self.password = secrets.token_urlsafe(32)
        self.data = {
            "school": {"name": "Provisioning Test School", "email": "school@example.test",
                       "phone_number": "+263771234567", "address": "Test address", "default_currency": "USD"},
            "administrator": {"username": "provision-admin", "email": "admin@example.test",
                              "first_name": "Test", "last_name": "Administrator"},
            "academic_year": {"name": "2026", "start_date": "2026-01-01", "end_date": "2026-12-31"},
            "terms": [{"name": "Term 1", "start_date": "2026-01-12", "end_date": "2026-04-01"}],
            "classes": [{"name": "Grade 1 A"}, {"name": "Grade 2 A"}],
        }

    def run_command(self, **options):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        output = StringIO()
        with patch.dict(os.environ, {"MTM_PROVISION_ADMIN_PASSWORD": self.password}):
            call_command("provision_school", input=str(self.path), stdout=output, **options)
            self.assertNotIn("MTM_PROVISION_ADMIN_PASSWORD", os.environ)
        self.assertNotIn(self.password, output.getvalue())
        return output.getvalue()

    def assert_empty(self):
        for model in (School, User, SchoolAdministrator, AcademicYear, Term, SchoolClass, AuditLog):
            self.assertEqual(model.objects.count(), 0, model.__name__)

    def test_creation_assignment_hashing_and_no_extra_data(self):
        self.assertIn("school_id=", self.run_command())
        school = School.objects.get()
        user = User.objects.get()
        self.assertEqual(user.school_administrator.school, school)
        self.assertEqual(user.role, User.Role.SCHOOL_ADMIN)
        self.assertTrue(user.must_change_password)
        self.assertFalse(user.is_superuser or user.is_staff or school.is_demo)
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(authenticate(username=user.username, password=self.password), user)
        self.assertTrue(AcademicYear.objects.get(school=school).is_current)
        self.assertEqual(Term.objects.get().academic_year.school, school)
        self.assertEqual(school.classes.count(), 2)
        self.assertEqual(AuditLog.objects.filter(school=school, actor=None).count(), 2)
        for event in AuditLog.objects.all():
            self.assertNotIn(self.password, event.description)
        for model in (Student, Parent, Payment):
            self.assertFalse(model.objects.exists())

    def test_dry_run_has_no_writes(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            self.assertIn("DRY RUN OK", self.run_command(dry_run=True))
        self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries))
        self.assert_empty()

    def test_duplicate_school_name_and_email_including_case_and_whitespace(self):
        self.run_command()
        original = copy.deepcopy(self.data)
        for key in ("name", "email"):
            with self.subTest(key=key):
                self.data = copy.deepcopy(original)
                self.data["school"]["name"] = "Another school"
                self.data["school"]["email"] = "another@example.test"
                self.data["school"][key] = "  " + original["school"][key].upper().replace(" ", "  ") + "  "
                with self.assertRaisesMessage(CommandError, f"Duplicate School {key}"):
                    self.run_command()
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_existing_user_is_never_reused(self):
        for key in ("username", "email"):
            with self.subTest(key=key):
                candidate = {"username": "unrelated", "email": "unrelated@example.test"}
                candidate[key] = self.data["administrator"][key].upper()
                user = User.objects.create_user(**candidate, role=User.Role.PARENT, is_active=False)
                with self.assertRaisesMessage(CommandError, f"Duplicate User {key}"):
                    self.run_command()
                self.assertFalse(School.objects.exists())
                user.delete()

    def test_rolls_back_on_administrator_calendar_and_audit_failure(self):
        for target in ("core.models.SchoolAdministrator.save", "core.models.Term.save",
                       "core.management.commands.provision_school.log_action"):
            with self.subTest(target=target):
                with patch(target, side_effect=IntegrityError("private database details")):
                    with self.assertRaisesMessage(CommandError, "nothing provisioned") as error:
                        self.run_command()
                self.assertNotIn("private database details", str(error.exception))
                self.assert_empty()

    def test_invalid_input_rejected_before_any_save(self):
        original = copy.deepcopy(self.data)
        cases = [
            ("school", "school_id", "1"), ("school", "name", ""),
            ("school", "default_currency", "usd"), ("administrator", "email", "bad"),
            ("academic_year", "end_date", "2025-01-01"),
        ]
        for section, key, value in cases:
            with self.subTest(section=section, key=key):
                self.data = copy.deepcopy(original)
                self.data[section][key] = value
                with patch("core.models.School.save") as save:
                    with self.assertRaises(CommandError):
                        self.run_command()
                    save.assert_not_called()
                self.assert_empty()

    def test_calendar_and_class_errors(self):
        original = copy.deepcopy(self.data)
        for change in ("outside", "overlap", "duplicate_term", "duplicate_class", "empty_classes"):
            with self.subTest(change=change):
                self.data = copy.deepcopy(original)
                if change == "outside":
                    self.data["terms"][0]["end_date"] = "2027-01-01"
                elif change in ("overlap", "duplicate_term"):
                    self.data["terms"].append({"name": "Term 2" if change == "overlap" else "TERM 1",
                                               "start_date": "2026-03-01", "end_date": "2026-06-01"})
                elif change == "duplicate_class":
                    self.data["classes"].append({"name": "grade 1 a"})
                else:
                    self.data["classes"] = []
                with self.assertRaises(CommandError):
                    self.run_command()
                self.assert_empty()

    def test_password_is_required_and_validated_including_dry_run(self):
        for password in ("", "12345678"):
            self.password = password
            for dry_run in (True, False):
                with self.assertRaises(CommandError):
                    self.run_command(dry_run=dry_run)
                self.assert_empty()

    def test_secure_prompt_and_mismatch(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        with patch.dict(os.environ):
            os.environ.pop("MTM_PROVISION_ADMIN_PASSWORD", None)
            with patch("sys.stdin.isatty", return_value=True), patch(
                "core.management.commands.provision_school.getpass.getpass",
                side_effect=[self.password, self.password],
            ):
                call_command("provision_school", input=str(self.path), dry_run=True, stdout=StringIO())
            with patch("sys.stdin.isatty", return_value=True), patch(
                "core.management.commands.provision_school.getpass.getpass", side_effect=[self.password, "different"],
            ):
                with self.assertRaisesMessage(CommandError, "Passwords do not match"):
                    call_command("provision_school", input=str(self.path))
        self.assert_empty()

    def test_real_jwt_password_change_and_tenant_isolation(self):
        self.run_command()
        own = School.objects.get()
        other = School.objects.create(name="Other Test School", email="other@example.test", phone_number="200")
        other_class = SchoolClass.objects.create(school=other, name="Private class")
        other_year = AcademicYear.objects.create(school=other, name="2026", start_date="2026-01-01", end_date="2026-12-31")
        other_term = Term.objects.create(academic_year=other_year, name="Private term", sequence=1,
                                        start_date="2026-01-01", end_date="2026-03-31")
        login = self.client.post("/api/auth/token/", {"username": self.data["administrator"]["username"], "password": self.password})
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
        self.assertEqual(self.client.get("/api/school/classes/").status_code, 403)
        changed = self.client.post("/api/auth/change-password/", {
            "current_password": self.password, "new_password": secrets.token_urlsafe(32),
        })
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.get("/api/school/profile/", {"school_id": other.pk}).data["name"], own.name)
        for endpoint, foreign, expected_ids in (
            ("classes", other_class, list(own.classes.values_list("pk", flat=True))),
            ("academic-years", other_year, list(own.academic_years.values_list("pk", flat=True))),
            ("terms", other_term, list(Term.objects.filter(academic_year__school=own).values_list("pk", flat=True))),
        ):
            response = self.client.get(f"/api/school/{endpoint}/", {"school_id": other.pk})
            self.assertEqual(response.status_code, 200)
            self.assertCountEqual([row["id"] for row in response.data], expected_ids)
            url = f"/api/school/{endpoint}/{foreign.pk}/"
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.patch(url, {"name": "Tampered"}).status_code, 404)
            self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.client.get("/api/platform/schools/").status_code, 403)
        other_class.refresh_from_db()
        self.assertEqual(other_class.name, "Private class")
        response = self.client.post("/api/school/terms/", {
            "academic_year": other_year.pk, "name": "Injected", "sequence": 2,
            "start_date": "2026-04-01", "end_date": "2026-06-01",
        })
        self.assertEqual(response.status_code, 400)
