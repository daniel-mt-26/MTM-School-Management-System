"""JWT authentication and issuance rules shared by every API endpoint."""

from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


def account_failure(user, *, login=False):
    """Return a safe machine-readable denial without exposing account secrets."""
    if not user.is_active:
        return AuthenticationFailed("This account is inactive.", code="user_inactive")
    if user.role == User.Role.SCHOOL_ADMIN and hasattr(user, "school_administrator"):
        status = user.school_administrator.school.status
    elif user.role == User.Role.PARENT and hasattr(user, "parent_profile"):
        status = user.parent_profile.school.status
    else:
        status = None
    if status == "suspended":
        return AuthenticationFailed("This school account is currently suspended.", code="school_suspended")
    if status == "archived":
        return AuthenticationFailed("This school is no longer active.", code="school_archived")
    # Token endpoints preserve account-enumeration resistance for any other
    # invalid login state, while authenticated requests retain a stable code.
    return AuthenticationFailed("No active account found for the given credentials." if login else "This account is not currently allowed to use MTM SMS.", code="account_unavailable")


def user_can_use_mtm(user):
    """Return whether this account may use a token right now.

    This intentionally does not treat a Django superuser as a platform
    operator.  Only the explicit application role grants that access.
    """
    if not user.is_active:
        return False
    if user.role == User.Role.PLATFORM_ADMIN:
        return True
    if user.role == User.Role.SCHOOL_ADMIN:
        return hasattr(user, "school_administrator") and user.school_administrator.school.is_operational
    if user.role == User.Role.PARENT:
        return hasattr(user, "parent_profile") and user.parent_profile.school.is_operational
    return False


def token_belongs_to_current_account(user, token):
    return user_can_use_mtm(user) and token.get("token_version") == user.token_version


def token_user_or_fail(token):
    user_id = token.get(api_settings.USER_ID_CLAIM)
    try:
        user = get_user_model().objects.select_related(
            "school_administrator__school", "parent_profile__school"
        ).get(**{api_settings.USER_ID_FIELD: user_id})
    except get_user_model().DoesNotExist as exc:
        raise AuthenticationFailed("No active account found for the given credentials.") from exc
    if not token_belongs_to_current_account(user, token):
        raise account_failure(user)
    return user


class MTMJWTAuthentication(JWTAuthentication):
    """Reject suspended schools and revoked user sessions on every request."""

    def get_user(self, validated_token):
        return token_user_or_fail(validated_token)


class MTMTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["token_version"] = user.token_version
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if not user_can_use_mtm(self.user):
            raise account_failure(self.user, login=True)
        return data


class MTMTokenRefreshSerializer(TokenRefreshSerializer):
    """A refresh must still pass the live school/account policy checks."""

    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        token_user_or_fail(refresh)
        return super().validate(attrs)
