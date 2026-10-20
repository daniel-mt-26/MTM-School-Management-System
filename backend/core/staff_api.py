"""Teacher endpoints: every lookup derives ownership from the signed-in user."""
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (Teacher, TeacherAssignment, User, SchoolClass, ClassSubject, Student,
    StudentEnrollment, AcademicYear, Term, Homework, AcademicResult, ReportComment,
    StaffAnnouncement, TeachingResource, TimetableEntry)
from .permissions import IsSchoolAdministrator
from .staff_access import IsTeacher, IsAcademicStaff, staff_school, assigned_class, assigned_subject
from .credentials import create_login, reset_login
from .audit import log_action
from . import serializers as existing
from .views import HomeworkViewSet


class AssignmentInput(serializers.Serializer):
    school_class = serializers.IntegerField()
    subjects = serializers.ListField(child=serializers.IntegerField(), default=list)


class TeacherInput(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    assignments = AssignmentInput(many=True, required=False)


def teacher_data(teacher):
    user = teacher.user
    return dict(id=teacher.pk, username=user.username, first_name=user.first_name,
        last_name=user.last_name, email=user.email, is_active=teacher.is_active and user.is_active,
        last_login=user.last_login, must_change_password=user.must_change_password,
        assignments=[dict(school_class=a.school_class_id, class_name=a.school_class.name,
                         subjects=list(a.subjects.values_list("id", flat=True))) for a in teacher.assignments.select_related("school_class")])


class TeacherManagement(viewsets.ViewSet):
    permission_classes = [IsSchoolAdministrator]

    def get_object(self, pk, lock=False):
        rows = Teacher.objects.select_related("user").filter(school=staff_school(self.request.user))
        if lock:
            rows = rows.select_for_update()
        return get_object_or_404(rows, pk=pk)

    def list(self, request):
        return Response([teacher_data(t) for t in Teacher.objects.filter(school=staff_school(request.user)).select_related("user")])

    def retrieve(self, request, pk=None):
        return Response(teacher_data(self.get_object(pk)))

    def save_assignments(self, teacher, assignments):
        school = teacher.school
        if len({a["school_class"] for a in assignments}) != len(assignments):
            raise ValidationError("Each class may be assigned once.")
        validated = []
        for item in assignments:
            cls = get_object_or_404(SchoolClass, pk=item["school_class"], school=school)
            subjects = ClassSubject.objects.filter(pk__in=item["subjects"], school_class=cls, subject__school=school, academic_year__school=school)
            if subjects.count() != len(set(item["subjects"])):
                raise ValidationError("Subjects must belong to the assigned class and school.")
            validated.append((cls, list(subjects)))
        teacher.assignments.exclude(school_class_id__in=[cls.pk for cls, _ in validated]).delete()
        for cls, subjects in validated:
            assignment, _ = TeacherAssignment.objects.get_or_create(teacher=teacher, school_class=cls)
            assignment.subjects.set(subjects)
        log_action(school=school, actor=self.request.user, action="teacher_assignments_changed", resource=teacher)

    @transaction.atomic
    def create(self, request):
        serializer = TeacherInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user, password = create_login(role=User.Role.TEACHER, **{k: data.get(k, "") for k in ("first_name", "last_name", "email")})
        teacher = Teacher.objects.create(user=user, school=staff_school(request.user))
        if data.get("is_active") is False:
            teacher.is_active = user.is_active = False
            teacher.save(update_fields=["is_active"])
            user.save(update_fields=["is_active"])
        self.save_assignments(teacher, data.get("assignments", []))
        log_action(school=teacher.school, actor=request.user, action="teacher_created", resource=teacher)
        return Response({**teacher_data(teacher), "temporary_password": password}, status=201)

    @transaction.atomic
    def partial_update(self, request, pk=None):
        teacher = self.get_object(pk, lock=True)
        serializer = TeacherInput(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        for field in ("first_name", "last_name", "email"):
            if field in data:
                setattr(teacher.user, field, data[field])
        if "is_active" in data:
            teacher.is_active = teacher.user.is_active = data["is_active"]
            teacher.user.token_version += 1
        teacher.user.save()
        teacher.save()
        if "assignments" in data:
            self.save_assignments(teacher, data["assignments"])
        log_action(school=teacher.school, actor=request.user, action="teacher_updated", resource=teacher, description=f"Active: {teacher.is_active}")
        return Response(teacher_data(teacher))

    @action(detail=True, methods=["post"], url_path="reset-password")
    @transaction.atomic
    def reset_password(self, request, pk=None):
        teacher = self.get_object(pk, lock=True)
        user = User.objects.select_for_update().get(pk=teacher.user_id)
        password = reset_login(user)
        log_action(school=teacher.school, actor=request.user, action="teacher_password_reset", resource=teacher)
        return Response({"username": user.username, "temporary_password": password})


class TeacherLookups(APIView):
    permission_classes = [IsTeacher]

    def get(self, request):
        teacher = request.user.teacher_profile
        school = teacher.school
        classes = SchoolClass.objects.filter(school=school, teacher_assignments__teacher=teacher)
        subjects = ClassSubject.objects.filter(teacher_assignments__teacher=teacher, school_class__school=school).distinct()
        enrollments = StudentEnrollment.objects.filter(school_class__in=classes, student__school=school)
        from django.utils import timezone
        from .models import AttendanceRecord
        today = timezone.localdate()
        pending = []
        for cls in classes:
            roster = enrollments.filter(school_class=cls, academic_year__start_date__lte=today, academic_year__end_date__gte=today, enrolled_on__lte=today).filter(Q(left_on__isnull=True) | Q(left_on__gte=today))
            if roster.exists() and Term.objects.filter(academic_year__school=school, start_date__lte=today, end_date__gte=today).exists():
                marked = AttendanceRecord.objects.filter(school=school, enrollment__in=roster, attendance_date=today).values('enrollment_id').distinct().count()
                if marked < roster.count():
                    pending.append(cls.name)
        return Response(dict(profile=teacher_data(teacher), school_name=school.name, attendance_pending=pending,
            classes=list(classes.values("id", "name")),
            subjects=list(subjects.values("id", "school_class", "subject", "subject__name", "academic_year")),
            years=list(AcademicYear.objects.filter(school=school).values("id", "name", "is_current")),
            terms=list(Term.objects.filter(academic_year__school=school).values("id", "name", "academic_year", "start_date", "end_date")),
            enrollments=list(enrollments.values("id", "student", "school_class", "academic_year", "student__first_name", "student__last_name"))))


class TeacherCatalog(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, resource):
        school, teacher = staff_school(request.user), request.user.teacher_profile
        context = {"school": school, "request": request}
        from .models import Subject
        catalog = {
            "classes": (SchoolClass.objects.filter(school=school, teacher_assignments__teacher=teacher), existing.SchoolClassSerializer),
            "academic-years": (AcademicYear.objects.filter(school=school), existing.AcademicYearSerializer),
            "terms": (Term.objects.filter(academic_year__school=school), existing.TermSerializer),
            "subjects": (Subject.objects.filter(school=school, class_subjects__teacher_assignments__teacher=teacher).distinct(), existing.SubjectSerializer),
            "class-subjects": (ClassSubject.objects.filter(school_class__school=school, teacher_assignments__teacher=teacher).distinct(), existing.ClassSubjectSerializer),
        }
        if resource not in catalog:
            from django.http import Http404
            raise Http404
        rows, serializer = catalog[resource]
        data = serializer(rows, many=True, context=context).data
        if resource == "subjects":
            for item in data:
                item["assigned_classes"] = list(ClassSubject.objects.filter(subject_id=item["id"], teacher_assignments__teacher=teacher).values_list("school_class_id", flat=True).distinct())
        return Response(data)


class TeacherStudentSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    class Meta:
        model = Student
        fields = ["id", "admission_number", "first_name", "last_name", "school_class", "class_name", "date_of_birth", "is_active"]


class TeacherStudents(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTeacher]
    serializer_class = TeacherStudentSerializer

    def get_queryset(self):
        return Student.objects.filter(school=staff_school(self.request.user), school_class__teacher_assignments__teacher=self.request.user.teacher_profile).select_related("school_class")


class TeacherHomework(HomeworkViewSet):
    permission_classes = [IsTeacher]

    def get_school(self):
        return staff_school(self.request.user)

    def create(self, request, *args, **kwargs):
        request.body
        assigned_class(request.user, request.data.get("school_class"))
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(school_class__teacher_assignments__teacher=self.request.user.teacher_profile)

    def check_payload(self, serializer):
        data = serializer.validated_data
        instance = serializer.instance
        cls = data.get("school_class", getattr(instance, "school_class", None))
        assigned_class(self.request.user, cls.pk)
        subject = data.get("subject", getattr(instance, "subject", None))
        if subject:
            assigned_subject(self.request.user, cls.pk, subject.pk)
        if instance and instance.created_by_id != self.request.user.pk:
            raise PermissionDenied("Only the creating teacher can change this homework.")
        if instance and instance.status != "draft":
            if set(data) - {"status", "uploaded_attachments"} or data.get("uploaded_attachments") or data.get("status") != "closed" or instance.status != "published":
                raise PermissionDenied("Published homework can only be closed.")

    def perform_create(self, serializer):
        if serializer.validated_data.get("status", "draft") == "closed":
            raise ValidationError("Create draft or published homework first.")
        self.check_payload(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self.check_payload(serializer)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    @action(detail=True, methods=["delete"], url_path=r"attachments/(?P<attachment_id>[^/.]+)")
    def remove_attachment(self, request, *args, **kwargs):
        item = self.get_object()
        if item.status != "draft" or item.created_by_id != request.user.pk:
            raise PermissionDenied("Only your draft attachments can be removed.")
        return super().remove_attachment(request, *args, **kwargs)


class ResultWorkflow(viewsets.ModelViewSet):
    permission_classes = [IsAcademicStaff]
    serializer_class = existing.AcademicResultSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "school": staff_school(self.request.user)}

    def get_queryset(self):
        rows = AcademicResult.objects.filter(student_enrollment__student__school=staff_school(self.request.user))
        if self.request.user.role == "teacher":
            rows = rows.filter(class_subject__teacher_assignments__teacher=self.request.user.teacher_profile,
                               student_enrollment__school_class__teacher_assignments__teacher=self.request.user.teacher_profile)
        for key, lookup in {"academic_year": "student_enrollment__academic_year_id", "term": "term_id", "school_class": "student_enrollment__school_class_id", "subject": "class_subject__subject_id", "student": "student_enrollment__student_id"}.items():
            if value := self.request.query_params.get(key):
                rows = rows.filter(**{lookup: value})
        return rows

    def validate_assignment(self, serializer):
        user = self.request.user
        if user.role == "teacher":
            data, instance = serializer.validated_data, serializer.instance
            enrollment = data.get("student_enrollment", getattr(instance, "student_enrollment", None))
            subject = data.get("class_subject", getattr(instance, "class_subject", None))
            assigned_subject(user, enrollment.school_class_id, subject.subject_id, enrollment.academic_year_id)

    def perform_create(self, serializer):
        self.validate_assignment(serializer)
        item = serializer.save(recorded_by=self.request.user, status="draft")
        log_action(school=staff_school(self.request.user), actor=self.request.user, action="result_drafted", resource=item)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        item = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=kwargs["pk"])
        if item.status != "draft":
            raise PermissionDenied("Return the result to draft through the review workflow before editing.")
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        self.validate_assignment(serializer)
        item = serializer.save()
        log_action(school=staff_school(self.request.user), actor=self.request.user, action="result_updated", resource=item)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def correction(self, request, pk=None):
        if request.user.role != User.Role.SCHOOL_ADMIN:
            raise PermissionDenied("Only School Admin can reopen official results.")
        from .models import School
        School.objects.select_for_update().get(pk=staff_school(request.user).pk)
        item = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
        reason = serializers.CharField(min_length=10, max_length=1000).run_validation(request.data.get("reason"))
        if item.status != "published":
            raise ValidationError("Use the normal review workflow for unpublished results.")
        from .models import ResultRevision, ReportCard
        # Preserve the previous official compilation before the correction
        # hides its report card, including legacy cards created after migration.
        from .academic_history import capture_publication
        for card in ReportCard.objects.filter(student_enrollment=item.student_enrollment, term=item.term, is_published=True):
            if not card.publications.exists():
                capture_publication(card, request)
        revision = ResultRevision.objects.create(result=item, actor=request.user, reason=reason, snapshot={
            "score": str(item.score), "maximum_score": str(item.maximum_score), "comment": item.comment,
            "status": item.status, "student_enrollment": item.student_enrollment_id,
            "term": item.term_id, "class_subject": item.class_subject_id, "recorded_by": item.recorded_by_id,
            "recorded_at": item.recorded_at.isoformat()})
        item.status = "draft"
        item.save(update_fields=["status"])
        ReportCard.objects.filter(student_enrollment=item.student_enrollment, term=item.term).update(is_published=False)
        log_action(school=staff_school(request.user), actor=request.user, action="published_result_reopened", resource=item, description=f"Preserved official result in revision {revision.pk}")
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def transition(self, request, pk=None):
        from .models import School
        School.objects.select_for_update().get(pk=staff_school(request.user).pk)
        item = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
        target = request.data.get("status")
        allowed = {"draft": {"submitted"}} if request.user.role == "teacher" else {"draft": {"submitted"}, "submitted": {"approved", "draft"}, "approved": {"published", "draft"}}
        if target not in allowed.get(item.status, set()):
            raise PermissionDenied("This workflow transition is not allowed.")
        item.status = target
        if target == 'published':
            from .academic_history import freeze_grade
            freeze_grade(item, staff_school(request.user))
        item.save(update_fields=["status", "official_grade", "grading_snapshot"])
        log_action(school=staff_school(request.user), actor=request.user, action=f"result_{target}", resource=item)
        return Response(self.get_serializer(item).data)


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportComment
        fields = ["id", "enrollment", "term", "comment", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        user = self.context["request"].user
        enrollment = attrs.get("enrollment", getattr(self.instance, "enrollment", None))
        term = attrs.get("term", getattr(self.instance, "term", None))
        assigned_class(user, enrollment.school_class_id)
        if enrollment.student.school_id != staff_school(user).pk or term.academic_year_id != enrollment.academic_year_id:
            raise ValidationError("Choose an enrollment and term in the same school and year.")
        from .models import ReportCard
        if ReportCard.objects.filter(student_enrollment=enrollment, term=term, is_published=True).exists():
            raise PermissionDenied("Comments on a published report are locked.")
        return attrs


class TeacherComments(viewsets.ModelViewSet):
    permission_classes = [IsTeacher]
    serializer_class = CommentSerializer

    def get_queryset(self):
        return ReportComment.objects.filter(teacher=self.request.user.teacher_profile,
            enrollment__school_class__teacher_assignments__teacher=self.request.user.teacher_profile)

    def perform_create(self, serializer):
        item = serializer.save(teacher=self.request.user.teacher_profile)
        log_action(school=staff_school(self.request.user), actor=self.request.user, action="report_comment_created", resource=item)

    def perform_update(self, serializer):
        item = serializer.save()
        log_action(school=staff_school(self.request.user), actor=self.request.user, action="report_comment_updated", resource=item)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")


class AnnouncementInput(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    message = serializers.CharField()
    all_recipients = serializers.BooleanField(default=False)
    recipients = serializers.ListField(child=serializers.IntegerField(), default=list)

    def validate(self, attrs):
        if any(k in self.initial_data for k in ("school", "school_id", "audience", "all_parents", "school_wide")):
            raise ValidationError("Use only assigned class or authorized teacher recipients.")
        return attrs


class StaffAnnouncements(viewsets.ViewSet):
    permission_classes = [IsAcademicStaff]

    def list(self, request):
        rows = StaffAnnouncement.objects.filter(school=staff_school(request.user))
        if request.user.role == "teacher":
            rows = rows.filter(Q(teachers=request.user.teacher_profile) | Q(author=request.user)).distinct()
        return Response(list(rows.order_by("-created_at").values("id", "title", "message", "author", "created_at")))

    @transaction.atomic
    def create(self, request):
        serializer = AnnouncementInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = staff_school(request.user)
        teacher = request.user.role == "teacher"
        recipients = SchoolClass.objects.filter(school=school, teacher_assignments__teacher=request.user.teacher_profile) if teacher else Teacher.objects.filter(school=school, is_active=True)
        if not data["all_recipients"]:
            recipients = recipients.filter(pk__in=data["recipients"])
            if recipients.count() != len(set(data["recipients"])):
                raise PermissionDenied("All recipients must be authorized members of your school.")
        recipients = list(recipients)
        if not recipients:
            raise ValidationError("Select at least one recipient.")
        item = StaffAnnouncement.objects.create(school=school, author=request.user, title=data["title"], message=data["message"])
        (item.classes if teacher else item.teachers).set(recipients)
        if teacher:
            from .models import Notification
            parents = User.objects.filter(parent_profile__school=school, parent_profile__student_links__student__school_class__in=recipients).distinct()
            for parent in parents:
                Notification.objects.create(school=school, recipient=parent, title=item.title, message=item.message)
        log_action(school=school, actor=request.user, action="announcement_sent", resource=item, description=f"Recipients: {len(recipients)}")
        return Response({"id": item.pk}, status=201)


class ResourceSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    class Meta:
        model = TeachingResource
        fields = ["id", "title", "school_class", "class_subject", "file", "created_at"]
        read_only_fields = ["created_at"]

    def validate_file(self, value):
        existing.validate_homework_file(value)
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        cls = attrs.get("school_class", getattr(self.instance, "school_class", None))
        assigned_class(user, cls.pk)
        subject = attrs.get("class_subject", getattr(self.instance, "class_subject", None))
        if subject:
            if subject.school_class_id != cls.pk:
                raise ValidationError("Subject must belong to the selected class.")
            assigned_subject(user, cls.pk, subject.subject_id, subject.academic_year_id)
        return attrs


class TeacherResources(viewsets.ModelViewSet):
    permission_classes = [IsTeacher]
    serializer_class = ResourceSerializer

    def get_queryset(self):
        return TeachingResource.objects.filter(teacher__school=staff_school(self.request.user), school_class__teacher_assignments__teacher=self.request.user.teacher_profile)

    def perform_create(self, serializer):
        item = serializer.save(teacher=self.request.user.teacher_profile)
        log_action(school=staff_school(self.request.user), actor=self.request.user, action="teaching_resource_uploaded", resource=item)

    def perform_update(self, serializer):
        if serializer.instance.teacher_id != self.request.user.teacher_profile.pk:
            raise PermissionDenied("Only the uploading teacher can edit this resource.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        item = self.get_object()
        return FileResponse(item.file.open("rb"), as_attachment=True, filename=item.file.name.rsplit("/", 1)[-1])


class TeacherTimetableSerializer(existing.TimetableEntrySerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = self.context['request'].user
        classes = SchoolClass.objects.filter(school=user.teacher_profile.school, teacher_assignments__teacher=user.teacher_profile)
        visible = classes.filter(pk=instance.school_class_id).first()
        if not visible and instance.timetable_id:
            visible = classes.filter(timetables=instance.timetable).first()
        if visible:
            data['school_class'], data['class_name'] = visible.pk, visible.name
        return data


class TeacherTimetable(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTeacher]
    serializer_class = TeacherTimetableSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "school": staff_school(self.request.user)}

    def get_queryset(self):
        teacher = self.request.user.teacher_profile
        return TimetableEntry.objects.filter(school_class__school=teacher.school).filter(Q(school_class__teacher_assignments__teacher=teacher) | Q(timetable__classes__teacher_assignments__teacher=teacher)).distinct()

    def list(self, request, *args, **kwargs):
        classes = SchoolClass.objects.filter(school=request.user.teacher_profile.school, teacher_assignments__teacher=request.user.teacher_profile)
        result = []
        for entry in self.get_queryset().select_related('school_class', 'subject', 'academic_year', 'term'):
            visible = classes.filter(timetables=entry.timetable) if entry.timetable_id else classes.filter(pk=entry.school_class_id)
            for cls in visible:
                result.append({**self.get_serializer(entry).data, 'school_class': cls.pk, 'class_name': cls.name})
        return Response(result)
