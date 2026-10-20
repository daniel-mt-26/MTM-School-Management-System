from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission
from .models import User, SchoolClass


def staff_school(user):
    return (user.teacher_profile if user.role == User.Role.TEACHER else user.school_administrator).school


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and user.role == User.Role.TEACHER and
                    hasattr(user, "teacher_profile") and user.teacher_profile.is_active and
                    user.teacher_profile.school.is_operational and not user.must_change_password)


class IsAcademicStaff(BasePermission):
    def has_permission(self, request, view):
        from .permissions import IsSchoolAdministrator
        return IsTeacher().has_permission(request, view) or IsSchoolAdministrator().has_permission(request, view)


def assigned_class(user, class_id):
    from rest_framework import serializers
    class_id = serializers.IntegerField(min_value=1).run_validation(class_id)
    classes = SchoolClass.objects.filter(school=staff_school(user))
    if user.role == User.Role.TEACHER:
        classes = classes.filter(teacher_assignments__teacher=user.teacher_profile)
    return get_object_or_404(classes, pk=class_id)


def assigned_subject(user, class_id, subject_id, year_id=None):
    from rest_framework.exceptions import PermissionDenied
    assigned_class(user, class_id)
    assignments = user.teacher_profile.assignments.filter(school_class_id=class_id, subjects__subject_id=subject_id)
    if year_id:
        assignments = assignments.filter(subjects__academic_year_id=year_id)
    if not assignments.exists():
        raise PermissionDenied("This subject is not assigned to you for this class and year.")
