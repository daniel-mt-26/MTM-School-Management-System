"""Single-use, hashed recovery tokens; never return or log token material."""
import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from .models import User, PasswordRecovery
from .authentication import user_can_use_mtm
from .audit import log_action

NEUTRAL = "If an account matching those details exists, password reset instructions have been sent."


class RecoveryThrottle(SimpleRateThrottle):
    scope = "password_recovery"
    rate = "5/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RecoveryRequest(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)


class RecoveryConfirm(serializers.Serializer):
    token = serializers.CharField(max_length=100)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)


class ForgotPassword(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [RecoveryThrottle]

    def post(self, request):
        serializer = RecoveryRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()
        users = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier), is_active=True)
        for user in users:
            if not user.email or not user_can_use_mtm(user):
                continue
            # Console/file backends would persist reset secrets. Recovery is
            # deliberately unavailable through those development backends.
            backend = getattr(settings, "MAILER_BACKEND", "")
            if backend in {"django.core.mail.backends.console.EmailBackend", "django.core.mail.backends.filebased.EmailBackend"}:
                continue
            token = secrets.token_urlsafe(32)
            recovery = PasswordRecovery.objects.create(user=user, token_version=user.token_version, digest=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now() + timedelta(minutes=45))
            origin = getattr(settings, "MTM_PASSWORD_RESET_ORIGIN", "http://localhost:5173").rstrip("/")
            link = f"{origin}/reset-password#token={token}"
            try:
                send_mail("MTM SMS password recovery", f"Reset your MTM SMS password:\n{link}\n\nThis link expires in 45 minutes and can be used once. If you did not request this, ignore this email.", settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
            except Exception:
                recovery.delete()
        return Response({"detail": NEUTRAL})


class ResetPassword(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [RecoveryThrottle]

    @transaction.atomic
    def post(self, request):
        serializer = RecoveryConfirm(data=request.data)
        serializer.is_valid(raise_exception=True)
        digest = hashlib.sha256(serializer.validated_data["token"].encode()).hexdigest()
        recovery = PasswordRecovery.objects.select_for_update().filter(digest=digest, used_at__isnull=True, expires_at__gt=timezone.now()).first()
        if not recovery:
            raise serializers.ValidationError("This reset link is invalid or expired.")
        user = User.objects.select_for_update().get(pk=recovery.user_id)
        if not user_can_use_mtm(user) or recovery.token_version != user.token_version:
            raise serializers.ValidationError("This reset link is invalid or expired.")
        try:
            validate_password(serializer.validated_data["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages}) from exc
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.token_version += 1
        user.save(update_fields=["password", "must_change_password", "token_version"])
        PasswordRecovery.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
        school = None
        for profile in ("school_administrator", "parent_profile", "teacher_profile"):
            if hasattr(user, profile):
                school = getattr(user, profile).school
        log_action(school=school, actor=user, action="password_recovery_completed", resource=user)
        return Response({"detail": "Password reset successfully. Sign in with your new password."})
