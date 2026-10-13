from django.core.management.base import BaseCommand, CommandError
from core.intake_email import process_email


class Command(BaseCommand):
    help = "Process the existing intake outbox with explicitly verified SMTP configuration."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--require-enabled", action="store_true", help="Fail the scheduler run if approved email configuration is missing.")
        parser.add_argument("--fail-on-error", action="store_true", help="Fail the scheduler run if this batch has delivery failures.")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("Limit must be between 1 and 1000.")
        counts = process_email(options["limit"])
        self.stdout.write(f"enabled={counts['enabled']} sent={counts['sent']} failed={counts['failed']}")
        if options["require_enabled"] and not counts["enabled"]:
            raise CommandError("Intake email delivery is disabled or its approved configuration is incomplete.")
        if options["fail_on_error"] and counts["failed"]:
            raise CommandError("Delivery failures were recorded in the private outbox. Retryable jobs remain scheduled.")
