"""Small, tenant-safe replay support for queued client mutations."""

from hashlib import sha256
from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework.response import Response

from .models import IdempotencyRecord


class IdempotentCreateMixin:
    """Replay a successful create when the same client operation is retried."""

    idempotency_header = "Idempotency-Key"

    def create(self, request, *args, **kwargs):
        return self.idempotent_create(request, lambda: self.create_once(request, *args, **kwargs))

    def create_once(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def idempotent_create(self, request, create_once):
        raw_key = request.headers.get(self.idempotency_header)
        if not raw_key:
            return create_once()
        try:
            operation_id = UUID(raw_key)
        except (TypeError, ValueError):
            return Response({"detail": "Idempotency-Key must be a UUID."}, status=400)

        school = self.get_school()
        actor = request.user
        payload_hash = sha256(request.body).hexdigest()
        existing = IdempotencyRecord.objects.filter(school=school, actor=actor, operation_id=operation_id).first()
        if existing:
            return self.replay_or_reject(existing, request, payload_hash)

        with transaction.atomic():
            try:
                record = IdempotencyRecord.objects.create(
                    school=school,
                    actor=actor,
                    operation_id=operation_id,
                    request_method=request.method,
                    request_path=request.path,
                    payload_hash=payload_hash,
                    response_status=200,
                )
            except IntegrityError:
                existing = IdempotencyRecord.objects.get(school=school, actor=actor, operation_id=operation_id)
                return self.replay_or_reject(existing, request, payload_hash)
            response = create_once()
            record.response_status = response.status_code
            record.response_body = response.data
            record.save(update_fields=["response_status", "response_body"])
            return response

    def replay_or_reject(self, record, request, payload_hash):
        if record.request_method != request.method or record.request_path != request.path or record.payload_hash != payload_hash:
            return Response({"detail": "Idempotency-Key was already used for a different operation."}, status=409)
        return Response(record.response_body, status=record.response_status)
