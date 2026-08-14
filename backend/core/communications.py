"""Tenant-safe local communication generation and outbox state transitions.

This module intentionally performs no HTTP calls. Django creates durable rows;
n8n later claims WhatsApp rows through separately authenticated integration APIs.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .finance import student_totals
from .models import (
    Announcement,
    CommunicationMessage,
    Notification,
    Parent,
    ParentCommunicationPreference,
    SchoolCommunicationSettings,
)


def communication_settings(school):
    settings, _ = SchoolCommunicationSettings.objects.get_or_create(school=school)
    return settings


def display_name(student):
    return f"{student.first_name} {student.last_name}".strip()


def whatsapp_recipient(parent, settings):
    """Return an opted-in E.164 number, otherwise None. An opt-out always wins."""
    try:
        preference = parent.communication_preference
    except ParentCommunicationPreference.DoesNotExist:
        return None
    if not settings.whatsapp_enabled or preference.whatsapp_status != ParentCommunicationPreference.WhatsAppStatus.OPTED_IN:
        return None
    phone = preference.whatsapp_phone or parent.phone_number
    if not phone.startswith("+") or not phone[1:].isdigit() or not 8 <= len(phone[1:]) <= 15:
        return None
    return phone


def _make_message(*, school, parent, student, channel, event_type, template_key, payload, key, title, body, **links):
    defaults = {
        "school": school,
        "parent": parent,
        "student": student,
        "channel": channel,
        "event_type": event_type,
        "template_key": template_key,
        "payload": payload,
        **links,
    }
    if channel == CommunicationMessage.Channel.IN_APP:
        defaults["status"] = CommunicationMessage.Status.DELIVERED
    message, created = CommunicationMessage.objects.get_or_create(idempotency_key=key, defaults=defaults)
    if created and channel == CommunicationMessage.Channel.IN_APP:
        notification = Notification.objects.create(
            school=school,
            recipient=parent.user,
            student=student,
            title=title,
            message=body,
        )
        message.notification = notification
        message.delivered_at = timezone.now()
        message.save(update_fields=["notification", "delivered_at"])
    return message, created


def create_event_messages(*, school, parent, student, event_type, template_key, payload, title, body, base_key, whatsapp_allowed=True, create_in_app=True, **links):
    """Create in-app plus eligible WhatsApp records with per-channel idempotency."""
    created = []
    if create_in_app:
        in_app, was_created = _make_message(
            school=school, parent=parent, student=student,
            channel=CommunicationMessage.Channel.IN_APP, event_type=event_type,
            template_key=template_key, payload=payload, key=f"{base_key}:in_app",
            title=title, body=body, **links,
        )
        if was_created:
            created.append(in_app)
    settings = communication_settings(school)
    if whatsapp_allowed and (phone := whatsapp_recipient(parent, settings)):
        whatsapp_payload = {**payload, "recipient": phone}
        message, was_created = _make_message(
            school=school, parent=parent, student=student,
            channel=CommunicationMessage.Channel.WHATSAPP, event_type=event_type,
            template_key=template_key, payload=whatsapp_payload, key=f"{base_key}:whatsapp",
            title=title, body=body, **links,
        )
        if was_created:
            created.append(message)
    return created


def announcement_recipients(announcement):
    parents = Parent.objects.filter(school=announcement.school)
    if announcement.audience == Announcement.Audience.SCHOOL_CLASS:
        return parents.filter(student_links__student__school_class=announcement.school_class).distinct()
    if announcement.audience == Announcement.Audience.STUDENT:
        return parents.filter(student_links__student=announcement.student).distinct()
    if announcement.audience == Announcement.Audience.PARENT:
        return parents.filter(pk=announcement.parent_id)
    return parents


@transaction.atomic
def send_announcement(announcement):
    if announcement.status == Announcement.Status.SENT:
        return announcement, 0
    recipients = list(announcement_recipients(announcement).select_related("user"))
    send_in_app = CommunicationMessage.Channel.IN_APP in announcement.channels
    settings = communication_settings(announcement.school)
    send_whatsapp = (
        CommunicationMessage.Channel.WHATSAPP in announcement.channels
        and settings.whatsapp_announcements_enabled
    )
    for parent in recipients:
        student = announcement.student if announcement.audience == Announcement.Audience.STUDENT else None
        if not send_in_app and not send_whatsapp:
            continue
        create_event_messages(
            school=announcement.school,
            parent=parent,
            student=student,
            event_type=CommunicationMessage.EventType.ANNOUNCEMENT,
            template_key="school_announcement",
            payload={"school_name": announcement.school.name, "title": announcement.title, "message": announcement.message},
            title=announcement.title,
            body=announcement.message,
            base_key=f"announcement:{announcement.pk}:{parent.pk}",
            whatsapp_allowed=send_whatsapp,
            create_in_app=send_in_app,
            announcement=announcement,
        )
    announcement.status = Announcement.Status.SENT
    announcement.recipient_count = len(recipients)
    announcement.sent_at = timezone.now()
    announcement.save(update_fields=["status", "recipient_count", "sent_at"])
    return announcement, len(recipients)


def create_payment_receipt_messages(payment, receipt):
    """Called from the finance service after Payment, Ledger and Receipt exist."""
    student = payment.student_fee_assignment.student
    school = student.school
    settings = communication_settings(school)
    if payment.is_reversed:
        return []
    payload = {
        "school_name": school.name,
        "student_name": display_name(student),
        "amount": str(payment.amount),
        "currency": payment.currency,
        "receipt_number": receipt.receipt_number,
        "payment_date": payment.paid_at.date().isoformat(),
    }
    messages = []
    for parent in Parent.objects.filter(school=school, student_links__student=student).select_related("user").distinct():
        messages.extend(create_event_messages(
            school=school, parent=parent, student=student,
            event_type=CommunicationMessage.EventType.PAYMENT_RECEIPT,
            template_key="payment_receipt", payload=payload,
            title="Payment received", body=f"Payment received for {display_name(student)}. Receipt {receipt.receipt_number}.",
            base_key=f"payment_receipt:{receipt.pk}:{parent.pk}",
            whatsapp_allowed=settings.payment_receipt_notifications_enabled,
            receipt=receipt,
        ))
    return messages


@transaction.atomic
def create_fee_reminders(*, school, students=None, reminder_date=None):
    """Django calculates balances; selected students are always scoped to school."""
    settings = communication_settings(school)
    students = students if students is not None else school.students.filter(is_active=True)
    reminder_date = reminder_date or timezone.localdate()
    created = 0
    considered = 0
    for student in students.select_related("school_class"):
        charges, payments, balance = student_totals(student)
        if balance <= 0:
            continue
        considered += 1
        payload = {"school_name": school.name, "student_name": display_name(student), "amount_due": str(balance), "currency": school.default_currency, "as_of": reminder_date.isoformat()}
        for parent in Parent.objects.filter(school=school, student_links__student=student).select_related("user").distinct():
            messages = create_event_messages(
                school=school, parent=parent, student=student,
                event_type=CommunicationMessage.EventType.FEE_REMINDER,
                template_key="fee_reminder", payload=payload,
                title="Fee reminder", body=f"{display_name(student)} has an outstanding balance of {school.default_currency} {balance}.",
                base_key=f"fee_reminder:{student.pk}:{reminder_date.isoformat()}:{parent.pk}",
                whatsapp_allowed=settings.fee_reminders_enabled,
            )
            created += len(messages)
    return {"students_considered": considered, "messages_created": created}


@transaction.atomic
def create_report_card_messages(report_card):
    student = report_card.student_enrollment.student
    school = student.school
    settings = communication_settings(school)
    messages = []
    for parent in Parent.objects.filter(school=school, student_links__student=student).select_related("user").distinct():
        messages.extend(create_event_messages(
            school=school, parent=parent, student=student,
            event_type=CommunicationMessage.EventType.REPORT_CARD_AVAILABLE,
            template_key="report_card_available",
            payload={"school_name": school.name, "student_name": display_name(student), "term": report_card.term.name},
            title="Report card available", body=f"A report card is available for {display_name(student)}.",
            base_key=f"report_card:{report_card.pk}:{parent.pk}",
            whatsapp_allowed=settings.report_card_notifications_enabled,
            report_card=report_card,
        ))
    return messages


STATUS_RANK = {
    CommunicationMessage.Status.PENDING: 0,
    CommunicationMessage.Status.PROCESSING: 1,
    CommunicationMessage.Status.SENT: 2,
    CommunicationMessage.Status.DELIVERED: 3,
    CommunicationMessage.Status.READ: 4,
}


def transition_message(message, new_status, provider_message_id="", failure_reason=""):
    """Apply monotonic provider status changes and make repeated callbacks harmless."""
    now = timezone.now()
    if new_status == CommunicationMessage.Status.FAILED:
        if message.status not in (CommunicationMessage.Status.DELIVERED, CommunicationMessage.Status.READ, CommunicationMessage.Status.CANCELLED):
            message.status = new_status
            message.failed_at = now
            message.failure_reason = failure_reason[:255]
    elif STATUS_RANK.get(new_status, -1) >= STATUS_RANK.get(message.status, -1):
        message.status = new_status
        if new_status == CommunicationMessage.Status.SENT:
            message.sent_at = message.sent_at or now
        elif new_status == CommunicationMessage.Status.DELIVERED:
            message.delivered_at = message.delivered_at or now
        elif new_status == CommunicationMessage.Status.READ:
            message.read_at = message.read_at or now
    if provider_message_id and not message.provider_message_id:
        message.provider_message_id = provider_message_id[:255]
    message.save()
    return message


def claim_whatsapp_messages(*, batch_size, stale_after_seconds, max_attempts):
    now = timezone.now()
    stale_before = now - timedelta(seconds=stale_after_seconds)
    with transaction.atomic():
        CommunicationMessage.objects.filter(
            channel=CommunicationMessage.Channel.WHATSAPP,
            status=CommunicationMessage.Status.PROCESSING,
            claimed_at__lt=stale_before,
            attempt_count__gte=max_attempts,
        ).update(status=CommunicationMessage.Status.FAILED, failed_at=now, failure_reason="Maximum delivery attempts reached")
        messages = list(
            CommunicationMessage.objects.select_for_update(skip_locked=True)
            .filter(channel=CommunicationMessage.Channel.WHATSAPP, attempt_count__lt=max_attempts)
            .filter(Q(status=CommunicationMessage.Status.PENDING) | Q(status=CommunicationMessage.Status.PROCESSING, claimed_at__lt=stale_before))
            .order_by("created_at", "id")[:batch_size]
        )
        for message in messages:
            message.status = CommunicationMessage.Status.PROCESSING
            message.claimed_at = now
            message.attempt_count += 1
            message.save(update_fields=["status", "claimed_at", "attempt_count"])
    return messages
