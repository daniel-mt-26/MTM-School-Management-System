from django.core.management.base import BaseCommand

from core.demo_seed import DEMO_NAME, target_school
from core.demo_verify import verify_demo


class Command(BaseCommand):
    help = 'Read-only verification of demo ownership, relationships and financial reconciliation.'

    def add_arguments(self, parser):
        parser.add_argument('--school', default=DEMO_NAME)

    def handle(self, *args, **options):
        counts, summary = verify_demo(target_school(options['school']))
        self.stdout.write(self.style.SUCCESS(f"Demo integrity verified: {counts.get('student', 0)} students; {counts.get('payment', 0)} payments."))
        self.stdout.write('Annual source totals: ' + '; '.join(f'{key}={value}' for key, value in summary.items()))
