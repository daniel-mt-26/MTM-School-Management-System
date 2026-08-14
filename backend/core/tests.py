from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    AcademicResult,
    AcademicYear,
    ClassSubject,
    Fee,
    FinancialLedgerEntry,
    Notification,
    Parent,
    ParentStudent,
    Payment,
    Receipt,
    RecurringFeeTemplate,
    ReportCard,
    School,
    SchoolAdministrator,
    SchoolClass,
    Student,
    StudentEnrollment,
    StudentFeeAssignment,
    Subject,
    Term,
    User,
)


class TenantIsolationTests(APITestCase):
    """Two-school tests: every private endpoint must scope objects server-side."""

    def setUp(self):
        self.school_a = School.objects.create(name="School A", email="a@example.test", phone_number="100")
        self.school_b = School.objects.create(name="School B", email="b@example.test", phone_number="200")
        self.admin_a = self.make_user("admin-a", User.Role.SCHOOL_ADMIN)
        self.admin_b = self.make_user("admin-b", User.Role.SCHOOL_ADMIN)
        self.platform_admin = self.make_user("platform", User.Role.PLATFORM_ADMIN)
        SchoolAdministrator.objects.create(user=self.admin_a, school=self.school_a)
        SchoolAdministrator.objects.create(user=self.admin_b, school=self.school_b)

        self.parent_a_user = self.make_user("parent-a", User.Role.PARENT)
        self.parent_b_user = self.make_user("parent-b", User.Role.PARENT)
        self.parent_a = Parent.objects.create(school=self.school_a, user=self.parent_a_user, phone_number="300")
        self.parent_b = Parent.objects.create(school=self.school_b, user=self.parent_b_user, phone_number="400")

        self.class_a, self.year_a, self.term_a = self.make_school_calendar(self.school_a, "A")
        self.class_b, self.year_b, self.term_b = self.make_school_calendar(self.school_b, "B")
        self.student_a = self.make_student(self.class_a, "A-001", "Alice")
        self.student_b = self.make_student(self.class_b, "B-001", "Beth")
        ParentStudent.objects.create(parent=self.parent_a, student=self.student_a)
        ParentStudent.objects.create(parent=self.parent_b, student=self.student_b)
        self.enrollment_a = StudentEnrollment.objects.create(student=self.student_a, school_class=self.class_a, academic_year=self.year_a, enrolled_on=date(2026, 1, 10))
        self.enrollment_b = StudentEnrollment.objects.create(student=self.student_b, school_class=self.class_b, academic_year=self.year_b, enrolled_on=date(2026, 1, 10))

        self.assignment_a, self.payment_a, self.result_a, self.report_a, self.notification_a = self.make_private_records(
            self.school_a, self.class_a, self.year_a, self.term_a, self.student_a, self.enrollment_a, self.admin_a, "A"
        )
        self.assignment_b, self.payment_b, self.result_b, self.report_b, self.notification_b = self.make_private_records(
            self.school_b, self.class_b, self.year_b, self.term_b, self.student_b, self.enrollment_b, self.admin_b, "B"
        )
        self.receipt_a = Receipt.objects.get(payment=self.payment_a)
        self.receipt_b = Receipt.objects.get(payment=self.payment_b)

    def make_user(self, username, role):
        return User.objects.create_user(username=username, password="secure-pass-123", role=role)

    def make_school_calendar(self, school, suffix):
        school_class = SchoolClass.objects.create(school=school, name=f"Grade 2{suffix}")
        year = AcademicYear.objects.create(school=school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), is_current=True)
        term = Term.objects.create(academic_year=year, name="Term 1", sequence=1, start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
        return school_class, year, term

    def make_student(self, school_class, admission_number, first_name):
        return Student.objects.create(
            school=school_class.school,
            school_class=school_class,
            admission_number=admission_number,
            first_name=first_name,
            last_name="Learner",
            date_of_birth=date(2018, 5, 1),
            enrolled_on=date(2026, 1, 10),
        )

    def make_private_records(self, school, school_class, year, term, student, enrollment, recorded_by, suffix):
        fee = Fee.objects.create(school=school, academic_year=year, term=term, school_class=school_class, name=f"Tuition {suffix}", amount=Decimal("100.00"))
        assignment = StudentFeeAssignment.objects.create(student=student, fee=fee, amount_owed=Decimal("100.00"), assigned_on=date(2026, 1, 10))
        payment = Payment.objects.create(student_fee_assignment=assignment, amount=Decimal("25.00"), paid_at=timezone.now(), method="cash", recorded_by=recorded_by)
        Receipt.objects.create(receipt_number=f"R-{suffix}-001", payment=payment, issued_at=timezone.now())
        subject = Subject.objects.create(school=school, name=f"Mathematics {suffix}", code=f"MATH-{suffix}")
        class_subject = ClassSubject.objects.create(school_class=school_class, subject=subject, academic_year=year)
        result = AcademicResult.objects.create(student_enrollment=enrollment, term=term, class_subject=class_subject, score=Decimal("80.00"), maximum_score=Decimal("100.00"), recorded_by=recorded_by)
        report_card = ReportCard.objects.create(student_enrollment=enrollment, term=term)
        notification = Notification.objects.create(school=school, title=f"Notice {suffix}", message="Private school notice")
        return assignment, payment, result, report_card, notification

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_school_admin_sees_only_own_students(self):
        self.authenticate(self.admin_a)
        response = self.client.get("/api/school/students/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.student_a.id])

    def test_school_a_admin_receives_only_school_a_profile_with_logo_url(self):
        self.school_a.address = "1 Alpha Road"
        self.school_a.logo.name = "school_logos/school-a.png"
        self.school_a.save(update_fields=["address", "logo"])
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/profile/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            "name": "School A",
            "email": "a@example.test",
            "phone": "100",
            "address": "1 Alpha Road",
            "default_currency": "USD",
            "logo": "http://testserver/media/school_logos/school-a.png",
        })

    def test_school_b_admin_receives_only_school_b_profile(self):
        self.authenticate(self.admin_b)

        response = self.client.get("/api/school/profile/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            "name": "School B",
            "email": "b@example.test",
            "phone": "200",
            "address": "",
            "default_currency": "USD",
            "logo": None,
        })

    def test_school_profile_does_not_accept_school_id(self):
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/profile/", {"school_id": self.school_b.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], self.school_a.name)
        self.assertEqual(
            self.client.get(f"/api/school/{self.school_b.id}/profile/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_platform_admin_is_denied_school_profile(self):
        self.authenticate(self.platform_admin)
        self.assertEqual(self.client.get("/api/school/profile/").status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_is_denied_school_profile(self):
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get("/api/school/profile/").status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_is_denied_school_profile(self):
        self.assertEqual(self.client.get("/api/school/profile/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_school_a_admin_can_update_only_school_a_profile(self):
        self.authenticate(self.admin_a)

        response = self.client.patch("/api/school/profile/", {
            "name": "Updated School A",
            "email": "updated-a@example.test",
            "phone": "111",
            "address": "New address",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.school_a.refresh_from_db()
        self.school_b.refresh_from_db()
        self.assertEqual(self.school_a.name, "Updated School A")
        self.assertEqual(self.school_a.phone_number, "111")
        self.assertEqual(self.school_b.name, "School B")

    def test_school_id_cannot_change_profile_update_tenant(self):
        self.authenticate(self.admin_a)

        response = self.client.patch("/api/school/profile/", {
            "school_id": self.school_b.id,
            "address": "School A only",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.school_a.refresh_from_db()
        self.school_b.refresh_from_db()
        self.assertEqual(self.school_a.address, "School A only")
        self.assertEqual(self.school_b.address, "")

    def test_parent_cannot_update_school_profile(self):
        self.authenticate(self.parent_a_user)
        response = self.client.patch("/api/school/profile/", {"name": "Attack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_admin_cannot_update_school_profile(self):
        self.authenticate(self.platform_admin)
        response = self.client.patch("/api/school/profile/", {"name": "Attack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_update_school_profile(self):
        response = self.client.patch("/api/school/profile/", {"name": "Attack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_logo_upload_is_rejected(self):
        self.authenticate(self.admin_a)
        invalid_logo = SimpleUploadedFile("not-an-image.txt", b"not an image", content_type="text/plain")

        response = self.client.patch("/api/school/profile/", {"logo": invalid_logo}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("logo", response.data)

    def test_oversized_logo_upload_is_rejected(self):
        self.authenticate(self.admin_a)
        oversized_logo = SimpleUploadedFile("large.png", b"x" * (2 * 1024 * 1024 + 1), content_type="image/png")

        response = self.client.patch("/api/school/profile/", {"logo": oversized_logo}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("logo", response.data)

    def test_valid_logo_upload_succeeds(self):
        self.authenticate(self.admin_a)
        gif = (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
            b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00"
            b"\x02\x02D\x01\x00;"
        )
        valid_logo = SimpleUploadedFile("school.gif", gif, content_type="image/gif")

        response = self.client.patch("/api/school/profile/", {"logo": valid_logo}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["logo"].endswith(".gif"))
        self.school_a.refresh_from_db()
        saved_logo = self.school_a.logo
        self.addCleanup(saved_logo.storage.delete, saved_logo.name)
        self.assertTrue(saved_logo.storage.exists(saved_logo.name))

    def test_school_search_returns_only_own_matching_students(self):
        other_alice = self.make_student(self.class_b, "B-ALICE", "Alice")
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/search/", {"q": "  aLiCe  "})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["students"]], [self.student_a.id])
        self.assertNotIn(other_alice.id, [item["id"] for item in response.data["students"]])
        self.assertNotIn("school_id", response.data["students"][0])

    def test_school_search_returns_only_own_classes(self):
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/search/", {"q": "Grade"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["classes"], [{"id": self.class_a.id, "name": self.class_a.name}])

    def test_school_search_scopes_parent_results_through_own_students(self):
        self.parent_a_user.first_name = "Shared"
        self.parent_b_user.first_name = "Shared"
        self.parent_a_user.save(update_fields=["first_name"])
        self.parent_b_user.save(update_fields=["first_name"])
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/search/", {"q": "shared"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["parents"]], [self.parent_a.id])
        self.assertEqual(set(response.data["parents"][0]), {"id", "display_name", "username", "phone"})

    def test_school_search_ignores_school_id_tenant_override(self):
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/search/", {"q": "Beth", "school_id": self.school_b.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["students"], [])

    def test_school_search_denies_unauthenticated_parent_and_platform_users(self):
        self.assertEqual(self.client.get("/api/school/search/", {"q": "Al"}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get("/api/school/search/", {"q": "Al"}).status_code, status.HTTP_403_FORBIDDEN)
        self.authenticate(self.platform_admin)
        self.assertEqual(self.client.get("/api/school/search/", {"q": "Al"}).status_code, status.HTTP_403_FORBIDDEN)

    def test_school_search_short_and_empty_queries_are_safe(self):
        self.authenticate(self.admin_a)
        empty_results = {"students": [], "parents": [], "classes": []}

        for query in ("", " ", "A", " A "):
            response = self.client.get("/api/school/search/", {"q": query})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data, empty_results)

    def test_school_search_limits_each_result_category_to_ten(self):
        for index in range(12):
            self.make_student(self.class_a, f"LIMIT-{index:02d}", f"Limit{index:02d}")
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/search/", {"q": "Limit"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["students"]), 10)

    def test_school_admin_cannot_retrieve_update_or_delete_other_school_student(self):
        self.authenticate(self.admin_a)
        detail_url = f"/api/school/students/{self.student_b.id}/"
        self.assertEqual(self.client.get(detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.patch(detail_url, {"first_name": "Changed"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Student.objects.filter(pk=self.student_b.id).exists())

    def test_school_admin_cannot_create_student_with_other_school_class(self):
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/students/", {
            "admission_number": "A-ATTACK",
            "first_name": "Attempt",
            "last_name": "Student",
            "date_of_birth": "2018-01-01",
            "enrolled_on": "2026-01-10",
            "school_class": self.class_b.id,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Student.objects.filter(admission_number="A-ATTACK").exists())

    def test_student_list_search_and_filters_are_tenant_scoped(self):
        inactive_a = self.make_student(self.class_a, "A-002", "Aaron")
        inactive_a.is_active = False
        inactive_a.save(update_fields=["is_active"])
        other_class_a = SchoolClass.objects.create(school=self.school_a, name="Grade 3A")
        self.make_student(other_class_a, "A-003", "April")
        self.authenticate(self.admin_a)

        search = self.client.get("/api/school/students/", {"q": "Ali", "school_id": self.school_b.id})
        self.assertEqual([item["id"] for item in search.data], [self.student_a.id])
        self.assertNotIn("school_id", search.data[0])

        class_filter = self.client.get("/api/school/students/", {"school_class": other_class_a.id})
        self.assertEqual(len(class_filter.data), 1)
        self.assertEqual(class_filter.data[0]["class_name"], "Grade 3A")
        cross_tenant_class = self.client.get("/api/school/students/", {"school_class": self.class_b.id})
        self.assertEqual(cross_tenant_class.data, [])

        inactive = self.client.get("/api/school/students/", {"is_active": "false"})
        self.assertEqual([item["id"] for item in inactive.data], [inactive_a.id])

    def test_school_admin_creates_student_with_server_controlled_school(self):
        self.authenticate(self.admin_a)
        attempted_override = self.client.post("/api/school/students/", {
            "school_id": self.school_b.id,
            "school": self.school_b.id,
            "admission_number": "A-NEW",
            "first_name": "New",
            "last_name": "Learner",
            "date_of_birth": "2018-01-01",
            "school_class": self.class_a.id,
            "enrolled_on": "2026-02-01",
            "is_active": True,
        }, format="json")
        self.assertEqual(attempted_override.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("school", attempted_override.data)

        response = self.client.post("/api/school/students/", {
            "admission_number": "A-NEW",
            "first_name": "New",
            "last_name": "Learner",
            "date_of_birth": "2018-01-01",
            "school_class": self.class_a.id,
            "enrolled_on": "2026-02-01",
            "is_active": True,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        student = Student.objects.get(pk=response.data["id"])
        self.assertEqual(student.school_class.school, self.school_a)
        self.assertEqual(student.school, self.school_a)
        enrollment = student.enrollments.get()
        self.assertEqual(enrollment.school_class, self.class_a)
        self.assertEqual(enrollment.academic_year, self.year_a)

    def test_same_admission_number_is_allowed_in_different_schools(self):
        self.authenticate(self.admin_b)
        response = self.client.post("/api/school/students/", {
            "admission_number": self.student_a.admission_number,
            "first_name": "Duplicate",
            "last_name": "Number",
            "date_of_birth": "2018-01-01",
            "school_class": self.class_b.id,
            "enrolled_on": "2026-02-01",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Student.objects.filter(admission_number=self.student_a.admission_number).count(), 2)
        created = Student.objects.get(pk=response.data["id"])
        self.assertEqual(created.school, self.school_b)

    def test_duplicate_admission_number_is_rejected_within_each_school(self):
        for admin, school_class, admission_number in (
            (self.admin_a, self.class_a, self.student_a.admission_number),
            (self.admin_b, self.class_b, self.student_b.admission_number),
        ):
            self.authenticate(admin)
            response = self.client.post("/api/school/students/", {
                "admission_number": admission_number,
                "first_name": "Duplicate",
                "last_name": "Number",
                "date_of_birth": "2018-01-01",
                "school_class": school_class.id,
                "enrolled_on": "2026-02-01",
            }, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("admission_number", response.data)

    def test_student_detail_contains_only_safe_profile_relationships_and_history(self):
        self.authenticate(self.admin_a)
        response = self.client.get(f"/api/school/students/{self.student_a.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([link["parent"] for link in response.data["parents"]], [self.parent_a.id])
        self.assertNotIn(self.parent_b.id, [link["parent"] for link in response.data["parents"]])
        self.assertEqual([item["id"] for item in response.data["enrollment_history"]], [self.enrollment_a.id])
        self.assertNotIn("school_id", response.data)
        self.assertNotIn("payments", response.data)
        self.assertEqual(self.client.get(f"/api/school/students/{self.student_b.id}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_student_class_transfer_preserves_same_year_history(self):
        new_class = SchoolClass.objects.create(school=self.school_a, name="Grade 3A")
        self.authenticate(self.admin_a)

        response = self.client.post(f"/api/school/students/{self.student_a.id}/transfer/", {
            "school_class": new_class.id,
            "transfer_effective_date": "2026-05-12",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student_a.refresh_from_db()
        self.enrollment_a.refresh_from_db()
        self.assertEqual(self.student_a.school_class, new_class)
        self.assertEqual(str(self.enrollment_a.left_on), "2026-05-11")
        history = self.student_a.enrollments.filter(academic_year=self.year_a).order_by("enrolled_on", "id")
        self.assertEqual(history.count(), 2)
        self.assertEqual(history.last().school_class, new_class)
        self.assertEqual(str(history.last().enrolled_on), "2026-05-12")
        self.assertIsNone(history.last().left_on)
        self.assertEqual(history.filter(left_on__isnull=True).count(), 1)
        self.assertEqual(self.student_a.school, self.school_a)

    def test_student_cannot_transfer_to_other_school_class(self):
        self.authenticate(self.admin_a)
        response = self.client.post(
            f"/api/school/students/{self.student_a.id}/transfer/",
            {"school_class": self.class_b.id, "transfer_effective_date": "2026-05-12"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.school_class, self.class_a)
        self.assertEqual(self.student_a.school, self.school_a)

    def test_backdated_transfer_rejects_invalid_date_and_preserves_history(self):
        new_class = SchoolClass.objects.create(school=self.school_a, name="Grade 3B")
        self.authenticate(self.admin_a)
        url = f"/api/school/students/{self.student_a.id}/transfer/"

        response = self.client.post(url, {
            "school_class": new_class.id,
            "transfer_effective_date": "2026-01-09",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.enrollment_a.refresh_from_db()
        self.assertIsNone(self.enrollment_a.left_on)
        self.assertEqual(self.student_a.enrollments.count(), 1)

        response = self.client.post(url, {
            "school_class": new_class.id,
            "transfer_effective_date": "2027-01-01",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.student_a.enrollments.count(), 1)

    def test_transfer_requires_one_open_enrollment(self):
        new_class = SchoolClass.objects.create(school=self.school_a, name="Grade 4A")
        self.enrollment_a.left_on = date(2026, 3, 31)
        self.enrollment_a.save(update_fields=["left_on"])
        self.authenticate(self.admin_a)
        response = self.client.post(f"/api/school/students/{self.student_a.id}/transfer/", {
            "school_class": new_class.id,
            "transfer_effective_date": "2026-05-12",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("transfer_effective_date", response.data)

    def test_unchanged_class_transfer_creates_no_enrollment(self):
        self.authenticate(self.admin_a)
        response = self.client.post(f"/api/school/students/{self.student_a.id}/transfer/", {
            "school_class": self.class_a.id,
            "transfer_effective_date": "2026-05-12",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.student_a.enrollments.count(), 1)

    def test_ordinary_patch_cannot_change_class_or_school(self):
        new_class = SchoolClass.objects.create(school=self.school_a, name="Grade 5A")
        self.authenticate(self.admin_a)
        school_response = self.client.patch(f"/api/school/students/{self.student_a.id}/", {
            "school": self.school_b.id,
            "school_id": self.school_b.id,
        }, format="json")
        self.assertEqual(school_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("school", school_response.data)

        response = self.client.patch(f"/api/school/students/{self.student_a.id}/", {
            "school_class": new_class.id,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.school, self.school_a)
        self.assertEqual(self.student_a.school_class, self.class_a)

    def test_parent_and_platform_users_cannot_access_student_crud(self):
        urls = ["/api/school/students/", f"/api/school/students/{self.student_a.id}/"]
        for user in (self.parent_a_user, self.platform_admin):
            self.authenticate(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(
                self.client.patch(urls[1], {"first_name": "Attack"}, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )

    def test_available_parent_list_is_tenant_scoped_and_includes_unlinked_owned_parent(self):
        unowned_user = self.make_user("unowned-parent", User.Role.PARENT)
        unlinked_parent = Parent.objects.create(school=self.school_a, user=unowned_user, phone_number="500")
        self.authenticate(self.admin_a)

        response = self.client.get("/api/school/available-parents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.parent_a.id, unlinked_parent.id])

    def test_school_admin_can_link_and_unlink_available_parent(self):
        second_student = self.make_student(self.class_a, "A-LINK", "Linked")
        self.authenticate(self.admin_a)

        response = self.client.post("/api/school/parent-links/", {
            "parent": self.parent_a.id,
            "student": second_student.id,
            "relationship": "Mother",
            "is_primary_contact": True,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        link = ParentStudent.objects.get(pk=response.data["id"])
        self.assertEqual(link.student, second_student)
        self.assertEqual(self.client.delete(f"/api/school/parent-links/{link.id}/").status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ParentStudent.objects.filter(pk=link.id).exists())

    def test_school_admin_cannot_link_other_school_parent(self):
        second_student = self.make_student(self.class_a, "A-NOLINK", "Safe")
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/parent-links/", {
            "parent": self.parent_b.id,
            "student": second_student.id,
            "relationship": "Guardian",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ParentStudent.objects.filter(parent=self.parent_b, student=second_student).exists())

    def test_primary_contact_constraint_returns_clean_validation_error(self):
        self.parent_a.student_links.update(is_primary_contact=True)
        second_user = self.make_user("parent-a-second", User.Role.PARENT)
        second_parent = Parent.objects.create(school=self.school_a, user=second_user, phone_number="501")
        ParentStudent.objects.create(parent=second_parent, student=self.make_student(self.class_a, "A-OWNER", "Owner"))
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/parent-links/", {
            "parent": second_parent.id,
            "student": self.student_a.id,
            "relationship": "Father",
            "is_primary_contact": True,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_primary_contact", response.data)

    def test_parent_admin_crud_is_tenant_safe_and_password_is_hashed(self):
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/parents/", {
            "username": "new-guardian", "first_name": "New", "last_name": "Guardian",
            "email": "guardian@example.test", "phone_number": "777", "password": "Safe-pass-123!",
            "children": [self.student_a.id], "school": self.school_b.id,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post("/api/school/parents/", {
            "username": "new-guardian", "first_name": "New", "last_name": "Guardian",
            "email": "guardian@example.test", "phone_number": "777", "password": "Safe-pass-123!",
            "children": [self.student_a.id],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        parent = Parent.objects.get(pk=response.data["id"])
        self.assertEqual(parent.school, self.school_a)
        self.assertTrue(parent.user.check_password("Safe-pass-123!"))
        self.assertFalse(parent.user.password == "Safe-pass-123!")
        self.assertEqual(self.client.get(f"/api/school/parents/{self.parent_b.id}/").status_code, status.HTTP_404_NOT_FOUND)

        login = self.client.post("/api/auth/token/", {"username": "new-guardian", "password": "Safe-pass-123!"}, format="json")
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_parent_link_rejects_cross_school_student_and_parent_crud_roles(self):
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/parent-links/", {
            "parent": self.parent_a.id, "student": self.student_b.id, "relationship": "Guardian",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for user in (self.parent_a_user, self.platform_admin):
            self.authenticate(user)
            self.assertEqual(self.client.get("/api/school/parents/").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/school/parents/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_timetable_is_class_year_term_scoped_and_rejects_overlaps(self):
        from .models import TimetableEntry
        ClassSubject.objects.create(school_class=self.class_a, subject=Subject.objects.create(school=self.school_a, name="English", code="ENG"), academic_year=self.year_a)
        subject = self.class_a.class_subjects.first().subject
        self.authenticate(self.admin_a)
        payload = {"school_class": self.class_a.id, "academic_year": self.year_a.id, "term": self.term_a.id, "day_of_week": "Monday", "start_time": "08:00", "end_time": "08:40", "subject": subject.id}
        response = self.client.post("/api/school/timetables/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TimetableEntry.objects.filter(school_class=self.class_a).count(), 1)
        overlap = self.client.post("/api/school/timetables/", {**payload, "start_time": "08:30", "end_time": "09:00", "label": ""}, format="json")
        self.assertEqual(overlap.status_code, status.HTTP_400_BAD_REQUEST)
        foreign = self.client.post("/api/school/timetables/", {**payload, "school_class": self.class_b.id}, format="json")
        self.assertEqual(foreign.status_code, status.HTTP_400_BAD_REQUEST)
        self.authenticate(self.parent_a_user)
        self.assertEqual(
            self.client.get(f"/api/parent/students/{self.student_a.id}/timetable/").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(f"/api/parent/students/{self.student_b.id}/timetable/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_school_admin_cannot_use_other_school_fee_or_payment_ids(self):
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/fee-assignments/", {
            "student": self.student_a.id,
            "fee": self.assignment_b.fee_id,
            "amount_owed": "100.00",
            "assigned_on": "2026-01-10",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post("/api/school/payments/", {
            "student_fee_assignment": self.assignment_b.id,
            "amount": "10.00",
            "paid_at": "2026-02-01T10:00:00Z",
            "method": "cash",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_school_admin_cannot_access_other_school_academic_private_records(self):
        self.authenticate(self.admin_a)
        for url in (
            f"/api/school/results/{self.result_b.id}/",
            f"/api/school/report-cards/{self.report_b.id}/",
            f"/api/school/notifications/{self.notification_b.id}/",
        ):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_academic_result_list_has_navigation_labels_and_scoped_filters(self):
        self.authenticate(self.admin_a)

        response = self.client.get(f"/api/school/results/?academic_year={self.year_a.id}&school_class={self.class_a.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.result_a.id])
        item = response.data[0]
        self.assertEqual(item["student_name"], "Alice Learner")
        self.assertEqual(item["class_name"], self.class_a.name)
        self.assertEqual(item["academic_year_name"], self.year_a.name)
        self.assertEqual(item["term_name"], self.term_a.name)
        self.assertEqual(item["subject_name"], "Mathematics A")

        response = self.client.get(f"/api/school/results/?academic_year={self.year_b.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_finance_payment_is_atomic_partial_and_generates_receipt_and_ledger(self):
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/payments/", {
            "student_fee_assignment": self.assignment_a.id,
            "amount": "20.00",
            "paid_at": "2025-06-14T09:30:00Z",
            "method": "cash",
            "reference": "HIST-20",
            "recorded_by": self.admin_b.id,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recorded_by", response.data)
        response = self.client.post("/api/school/payments/", {
            "student_fee_assignment": self.assignment_a.id,
            "amount": "20.00",
            "paid_at": "2025-06-14T09:30:00Z",
            "method": "cash",
            "reference": "HIST-20",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(pk=response.data["id"])
        self.assertEqual(payment.paid_at.date(), date(2025, 6, 14))
        self.assertEqual(payment.recorded_by, self.admin_a)
        self.assertTrue(hasattr(payment, "receipt"))
        self.assertTrue(hasattr(payment, "ledger_entry"))
        self.assertEqual(payment.ledger_entry.entry_type, "payment")
        self.assertEqual(payment.receipt.receipt_number, response.data["receipt_number"])
        overpayment = self.client.post("/api/school/payments/", {
            "student_fee_assignment": self.assignment_a.id,
            "amount": "56.00",
            "paid_at": "2026-01-11T09:30:00Z",
            "method": "cash",
        }, format="json")
        self.assertEqual(overpayment.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", overpayment.data)

    def test_finance_is_tenant_scoped_and_parent_finance_is_child_scoped(self):
        self.authenticate(self.admin_a)
        self.assertEqual([item["id"] for item in self.client.get("/api/school/finance/balances/").data], [self.student_a.id])
        self.assertEqual(self.client.get(f"/api/school/finance/students/{self.student_b.id}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f"/api/school/receipts/{self.receipt_b.id}/").status_code, status.HTTP_404_NOT_FOUND)
        self.authenticate(self.parent_a_user)
        own = self.client.get(f"/api/parent/students/{self.student_a.id}/finance/")
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(own.data["student"]["id"], self.student_a.id)
        self.assertEqual(self.client.get(f"/api/parent/students/{self.student_b.id}/finance/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post("/api/parent/payments/", {}, format="json").status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_bulk_fee_assignment_creates_only_missing_student_assignments(self):
        fee = Fee.objects.create(school=self.school_a, academic_year=self.year_a, term=self.term_a, school_class=self.class_a, name="Activity", amount=Decimal("30.00"))
        second = self.make_student(self.class_a, "A-SECOND", "Second")
        self.authenticate(self.admin_a)
        response = self.client.post("/api/school/fee-assignments/assign-to-class/", {"school_class": self.class_a.id, "fee": fee.id, "assigned_on": "2026-01-10"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assignments_created"], 2)
        response = self.client.post("/api/school/fee-assignments/assign-to-class/", {"school_class": self.class_a.id, "fee": fee.id, "assigned_on": "2026-01-10"}, format="json")
        self.assertEqual(response.data["assignments_created"], 0)
        self.assertEqual(response.data["already_assigned"], 2)
        self.assertEqual(StudentFeeAssignment.objects.filter(student=second, fee=fee).count(), 1)

    def test_payment_reversal_preserves_history_and_restores_balance(self):
        self.authenticate(self.admin_a)
        payment_response = self.client.post("/api/school/payments/", {"student_fee_assignment": self.assignment_a.id, "amount": "20.00", "paid_at": "2026-02-01T09:00:00Z", "method": "cash"}, format="json")
        payment_id = payment_response.data["id"]
        receipt_id = payment_response.data["receipt_id"]
        response = self.client.post(f"/api/school/payments/{payment_id}/reverse/", {"reason": "Entered twice"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment = Payment.objects.get(pk=payment_id)
        self.assertTrue(payment.is_reversed)
        self.assertTrue(Receipt.objects.get(pk=receipt_id).is_reversed)
        self.assertEqual(FinancialLedgerEntry.objects.filter(payment=payment).count(), 1)
        self.assertEqual(FinancialLedgerEntry.objects.filter(student=self.student_a, description__startswith="Payment reversal").count(), 1)
        self.assertEqual(self.client.post(f"/api/school/payments/{payment_id}/reverse/", {"reason": "Again"}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(f"/api/school/payments/{self.payment_b.id}/reverse/", {"reason": "Attack"}, format="json").status_code, status.HTTP_404_NOT_FOUND)

    def test_receipt_pdf_and_recurring_generation_are_tenant_safe_and_idempotent(self):
        self.authenticate(self.admin_a)
        pdf = self.client.get(f"/api/school/receipts/{self.receipt_a.id}/pdf/")
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(f"/api/school/receipts/{self.receipt_b.id}/pdf/").status_code, status.HTTP_404_NOT_FOUND)
        template = RecurringFeeTemplate.objects.create(school=self.school_a, academic_year=self.year_a, term=self.term_a, school_class=self.class_a, name="Monthly tuition", amount=Decimal("40.00"), currency="USD", start_month=date(2026, 1, 1))
        response = self.client.post("/api/school/recurring-fees/generate/", {"month": "2026-02-01"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fees_created"], 1)
        self.assertEqual(self.client.post("/api/school/recurring-fees/generate/", {"month": "2026-02-01"}, format="json").data["fees_created"], 0)
        self.assertEqual(self.client.post("/api/school/recurring-fees/generate/", {"month": "2026-03-01"}, format="json").data["fees_created"], 1)
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get(f"/api/parent/receipts/{self.receipt_a.id}/pdf/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post("/api/school/recurring-fees/generate/", {"month": "2026-04-01"}, format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_school_currency_is_profile_scoped_and_future_finance_inherits_it(self):
        school = School.objects.create(name="Currency School", email="currency@example.test", phone_number="900")
        admin = self.make_user("currency-admin", User.Role.SCHOOL_ADMIN)
        SchoolAdministrator.objects.create(user=admin, school=school)
        school_class, year, term = self.make_school_calendar(school, "C")
        self.authenticate(admin)
        response = self.client.patch("/api/school/profile/", {"default_currency": "zar"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["default_currency"], "ZAR")
        fee = self.client.post("/api/school/fees/", {"name": "Currency fee", "academic_year": year.id, "term": term.id, "amount": "20.00", "currency": "ZAR"}, format="json")
        self.assertEqual(fee.status_code, status.HTTP_201_CREATED)
        self.assertEqual(fee.data["currency"], "ZAR")
        self.assertEqual(self.client.patch("/api/school/profile/", {"default_currency": "USD"}, format="json").status_code, status.HTTP_400_BAD_REQUEST)

    def test_parent_can_access_only_linked_children_and_private_records(self):
        self.authenticate(self.parent_a_user)
        response = self.client.get("/api/parent/students/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.student_a.id])
        self.assertEqual(self.client.get(f"/api/parent/students/{self.student_b.id}/").status_code, status.HTTP_404_NOT_FOUND)
        for url in (
            f"/api/parent/receipts/{self.receipt_b.id}/",
            f"/api/parent/results/{self.result_b.id}/",
            f"/api/parent/report-cards/{self.report_b.id}/",
        ):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_platform_admin_has_platform_access_but_no_private_school_access(self):
        self.authenticate(self.platform_admin)
        self.assertEqual(self.client.get("/api/platform/schools/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/school/students/").status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_access_private_resources(self):
        response = self.client.get("/api/school/students/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_jwt_login_and_current_user_endpoint(self):
        response = self.client.post("/api/auth/token/", {"username": "admin-a", "password": "secure-pass-123"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], User.Role.SCHOOL_ADMIN)
