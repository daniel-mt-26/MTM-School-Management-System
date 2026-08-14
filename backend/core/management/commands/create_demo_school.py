import os
import secrets
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.finance import assign_fee, record_payment
from core.models import (
    AcademicResult, AcademicYear, Announcement, AuditLog, ClassSubject,
    CommunicationMessage, Fee, FinancialLedgerEntry, Notification, Parent,
    ParentCommunicationPreference, ParentStudent, Payment, Receipt, ReportCard,
    School, SchoolAdministrator, SchoolClass, SchoolCommunicationSettings,
    Student, StudentEnrollment, StudentFeeAssignment, Subject, Term, TimetableEntry, User,
)

DEMO_EMAIL = "demo@sunrise.invalid"


class Command(BaseCommand):
    help = "Create or safely reset the synthetic Sunrise Primary School demo tenant."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Demo admin password; never saved in source.")
        parser.add_argument("--reset", action="store_true", help="Delete and recreate only the marked demo tenant.")
        parser.add_argument("--yes", action="store_true", help="Required with --reset.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"] and not options["yes"]:
            raise CommandError("Demo reset is destructive. Re-run with --reset --yes.")
        school = School.objects.filter(email=DEMO_EMAIL).first()
        if school and not school.is_demo:
            raise CommandError("The controlled demo identifier is owned by a non-demo school; refusing to modify it.")
        if school and options["reset"]:
            self._clear_demo_school(school)
        school, _ = School.objects.get_or_create(
            email=DEMO_EMAIL,
            defaults={"name": "Sunrise Primary School", "phone_number": "+00000000000", "address": "100 Fictional Avenue", "is_demo": True},
        )
        if not school.is_demo:
            raise CommandError("Refusing to use an unmarked school as demo data.")
        generated_password = self._ensure_admin(school, options.get("password"))
        self._populate(school)
        self.stdout.write(self.style.SUCCESS(f"Demo school ready: {school.name}"))
        if generated_password:
            self.stdout.write(f"Generated demo admin password (shown once): {generated_password}")

    def _ensure_admin(self, school, supplied_password):
        user, created = User.objects.get_or_create(
            username="sunrise-admin",
            defaults={"role": User.Role.SCHOOL_ADMIN, "email": "admin@sunrise.invalid", "first_name": "Sam", "last_name": "Demo"},
        )
        if user.role != User.Role.SCHOOL_ADMIN:
            raise CommandError("The controlled demo admin username is not a school administrator.")
        password = supplied_password or os.getenv("MTM_DEMO_ADMIN_PASSWORD")
        generated = None
        if created and not password:
            generated = secrets.token_urlsafe(18)
            password = generated
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        SchoolAdministrator.objects.get_or_create(user=user, defaults={"school": school})
        if user.school_administrator.school_id != school.id:
            raise CommandError("The controlled demo admin belongs to another school.")
        return generated

    def _clear_demo_school(self, school):
        # Explicit, ordered deletion keeps the blast radius to is_demo=True only.
        CommunicationMessage.objects.filter(school=school).delete(); AuditLog.objects.filter(school=school).delete()
        Notification.objects.filter(school=school).delete(); Announcement.objects.filter(school=school).delete()
        ReportCard.objects.filter(student_enrollment__student__school=school).delete(); AcademicResult.objects.filter(student_enrollment__student__school=school).delete()
        Receipt.objects.filter(payment__student_fee_assignment__student__school=school).delete(); FinancialLedgerEntry.objects.filter(student__school=school).delete(); Payment.objects.filter(student_fee_assignment__student__school=school).delete()
        ParentStudent.objects.filter(student__school=school).delete(); StudentFeeAssignment.objects.filter(student__school=school).delete(); StudentEnrollment.objects.filter(student__school=school).delete(); Student.objects.filter(school=school).delete()
        ParentCommunicationPreference.objects.filter(parent__school=school).delete(); Parent.objects.filter(school=school).delete()
        TimetableEntry.objects.filter(school_class__school=school).delete(); ClassSubject.objects.filter(school_class__school=school).delete(); Subject.objects.filter(school=school).delete()
        Fee.objects.filter(school=school).delete(); Term.objects.filter(academic_year__school=school).delete(); AcademicYear.objects.filter(school=school).delete(); SchoolClass.objects.filter(school=school).delete()
        SchoolCommunicationSettings.objects.filter(school=school).delete()

    def _populate(self, school):
        year, _ = AcademicYear.objects.get_or_create(school=school, name="2026", defaults={"start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "is_current": True})
        term, _ = Term.objects.get_or_create(academic_year=year, name="Term 1", defaults={"sequence": 1, "start_date": date(2026, 1, 1), "end_date": date(2026, 4, 10)})
        classes = [SchoolClass.objects.get_or_create(school=school, name=name)[0] for name in ("Grade 4A", "Grade 4B", "Grade 5A")]
        subjects = [Subject.objects.get_or_create(school=school, name=name, defaults={"code": code})[0] for name, code in (("Mathematics", "MATH"), ("English", "ENG"), ("Science", "SCI"))]
        for school_class in classes:
            for subject in subjects:
                ClassSubject.objects.get_or_create(school_class=school_class, subject=subject, academic_year=year)
            TimetableEntry.objects.get_or_create(school_class=school_class, academic_year=year, term=term, day_of_week="Monday", start_time="08:00", end_time="09:00", subject=subjects[0])
        admin = school.administrators.select_related("user").first().user
        parents = []
        for index in range(12):
            user, _ = User.objects.get_or_create(username=f"sunrise-parent-{index + 1}", defaults={"role": User.Role.PARENT, "first_name": f"Parent{index + 1}", "last_name": "Demo"})
            user.set_unusable_password(); user.save(update_fields=["password"])
            parent, _ = Parent.objects.get_or_create(school=school, user=user, defaults={"phone_number": "+00000000000"})
            parents.append(parent)
        students = []
        for index in range(24):
            school_class = classes[index % len(classes)]
            student, _ = Student.objects.get_or_create(school=school, admission_number=f"SUN-2026-{index + 1:03d}", defaults={"first_name": f"Learner{index + 1}", "last_name": "Demo", "date_of_birth": date(2015, 1, 1), "school_class": school_class, "enrolled_on": date(2026, 1, 5)})
            students.append(student); ParentStudent.objects.get_or_create(parent=parents[index % len(parents)], student=student)
            StudentEnrollment.objects.get_or_create(student=student, school_class=school_class, academic_year=year, defaults={"enrolled_on": date(2026, 1, 5)})
        fee, _ = Fee.objects.get_or_create(school=school, academic_year=year, term=term, name="Term 1 Tuition", defaults={"amount": Decimal("120.00"), "currency": school.default_currency, "due_date": date(2026, 2, 15)})
        for student in students:
            assignment, _ = assign_fee(student=student, fee=fee, amount_owed=fee.amount, assigned_on=date(2026, 1, 5))
            if student.id % 3 == 0 and not assignment.payments.exists():
                record_payment(student_fee_assignment=assignment, amount=Decimal("60.00"), paid_at=timezone.now(), method="demo", recorded_by=admin)
        for student in students:
            enrollment = student.enrollments.get(academic_year=year, left_on__isnull=True)
            for class_subject in ClassSubject.objects.filter(school_class=student.school_class, academic_year=year):
                AcademicResult.objects.get_or_create(student_enrollment=enrollment, term=term, class_subject=class_subject, defaults={"score": Decimal("75.00"), "maximum_score": Decimal("100.00"), "recorded_by": admin})
            ReportCard.objects.get_or_create(student_enrollment=enrollment, term=term)
        Notification.objects.get_or_create(school=school, recipient=parents[0].user, title="Welcome to Sunrise", defaults={"message": "This is synthetic demo data.", "student": students[0]})
        SchoolCommunicationSettings.objects.get_or_create(school=school, defaults={"whatsapp_enabled": False})
