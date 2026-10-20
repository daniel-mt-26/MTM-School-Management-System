from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.demo_seed import DEMO_NAME


class Command(BaseCommand):
    help = 'Reset only seed-manifest-owned data in a marked demo school; requires --yes.'

    def add_arguments(self, parser):
        parser.add_argument('--school', default=DEMO_NAME)
        parser.add_argument('--yes', action='store_true')
        parser.add_argument('--password')
        parser.add_argument('--parent-password')

    def handle(self, *args, **options):
        call_command('seed_demo_school', school=options['school'], yes=options['yes'], reset_first=True,
                     password=options.get('password'), parent_password=options.get('parent_password'),
                     stdout=self.stdout, stderr=self.stderr)
