"""Safe, append-only audit helpers for state-changing application actions."""

from .models import AuditLog


def log_action(*, school, actor, action, resource, description=""):
    """Record concise metadata only; callers must not pass request bodies or secrets."""
    return AuditLog.objects.create(
        school=school,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        resource_type=resource.__class__.__name__,
        resource_id=str(resource.pk or ""),
        description=description[:500],
    )
