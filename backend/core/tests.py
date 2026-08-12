from datetime import date
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    AcademicResult,
    AcademicYear,
    ClassSubject,
    Fee,
    Notification,
    Parent,
    ParentStudent,
    Payment,
    Receipt,
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
        self.parent_a = Parent.objects.create(user=self.parent_a_user, phone_number="300")
        self.parent_b = Parent.objects.create(user=self.parent_b_user, phone_number="400")

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
