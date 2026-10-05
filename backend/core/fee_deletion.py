"""Delete mistaken setup records only; never cascade financial obligations."""

import json

from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import ValidationError

from .audit import log_action
from .models import Fee, RecurringFeeTemplate


def can_delete_fee(fee):
    # Assignments ARE charges, even if unpaid, zero-valued or missing a ledger row.
    # A generated period fee is itself retained as generation history.
    return not fee.recurring_template_id and not fee.student_assignments.exists()


def can_delete_template(template):
    return not template.generated_fees.exists()


@transaction.atomic
def delete_unused_fee(*, record, school, actor):
    is_template = isinstance(record, RecurringFeeTemplate)
    model = RecurringFeeTemplate if is_template else Fee
    # Lock the parent: PostgreSQL foreign-key inserts and generation cannot race
    # past deletion. Existing PROTECT relationships are a second line of defense.
    record = model.objects.select_for_update().get(pk=record.pk, school=school)
    code = "recurring_fee_has_generated_charges" if is_template else "fee_has_financial_history"
    message = (
        "This recurring fee cannot be permanently deleted because charges have already been generated. Deactivate it instead."
        if is_template else
        "This fee cannot be permanently deleted because financial records already exist. Deactivate it instead."
    )
    if not (can_delete_template(record) if is_template else can_delete_fee(record)):
        raise ValidationError({"detail": message, "code": code})
    metadata = {
        "name": record.name, "amount": str(record.amount), "currency": record.currency,
        "billing_method": record.billing_method if is_template else "ONE_OFF",
        "academic_year": record.academic_year_id, "term": record.term_id,
    }
    # Capture identity before delete clears the object's primary key. Both writes
    # roll back together if audit persistence or protected deletion fails.
    log_action(school=school, actor=actor,
               action="finance_recurring_fee_deleted" if is_template else "finance_fee_deleted",
               resource=record, description=json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
    try:
        record.delete()
    except ProtectedError as exc:
        raise ValidationError({"detail": message, "code": code}) from exc
