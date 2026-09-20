from rest_framework.permissions import BasePermission

from .models import User


class IsSchoolAdministrator(BasePermission):
    message = "A school administrator account is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.SCHOOL_ADMIN
            and hasattr(user, "school_administrator")
            and not user.must_change_password
        )


class IsParent(BasePermission):
    message = "A parent account is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.PARENT
            and hasattr(user, "parent_profile")
            and not user.must_change_password
        )


class IsPlatformAdministrator(BasePermission):
    message = "An MTM platform administrator account is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.PLATFORM_ADMIN)
