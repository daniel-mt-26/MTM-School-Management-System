"""Retention enforcement: dry run unless --execute is explicitly supplied."""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.audit import log_action
from core.models import School
from core.intake_models import AdmissionApplication, ContactEnquiry, PublicIntakeKey, IntakeRateBucket


class Command(BaseCommand):
    help = "Purge expired intake data under configured retention, or report counts by default."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        now = timezone.now()
        with transaction.atomic():
            # Match review/submission lock order; serialize cleanup with status changes.
            list(School.objects.select_for_update().order_by("pk").values_list("pk", flat=True))
            applications = AdmissionApplication.objects.filter(status="rejected", retention_hold=False, retention_expires_at__lte=now)
            enquiries = ContactEnquiry.objects.filter(status="resolved", retention_hold=False, retention_expires_at__lte=now)
            # Replays must never confirm a reference for a record deleted by retention.
            refs = list(applications.values_list("reference", flat=True)) + list(enquiries.values_list("reference", flat=True))
            keys = PublicIntakeKey.objects.filter(expires_at__lte=now) | PublicIntakeKey.objects.filter(reference__in=refs)
            buckets = IntakeRateBucket.objects.filter(expires_at__lte=now)
            self.stdout.write(f"applications={applications.count()} enquiries={enquiries.count()} keys={keys.count()} buckets={buckets.count()} execute={options['execute']}")
            if options["execute"]:
                for kind, records in [("application", applications), ("enquiry", enquiries)]:
                    for record in records.select_related("school").iterator():
                        log_action(school=record.school, actor=None, action=f"intake.{kind}.purged", resource=record)
                applications.delete()
                enquiries.delete()
                keys.delete()
                buckets.delete()
