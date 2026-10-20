from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from core.demo_seed import DEMO_EMAIL, DEMO_NAME
from core.models import School


class Command(BaseCommand):
    help = 'Create the controlled Sunrise demo tenant and populate it using seed_demo_school.'

    def add_arguments(self, parser):
        parser.add_argument('--password', help='Optional demo admin password; prefer environment configuration.')
        parser.add_argument('--parent-password', help='Optional demo parent password; prefer environment configuration.')
        parser.add_argument('--reset', action='store_true', help='Reset only manifest-owned data, then repopulate.')
        parser.add_argument('--yes', action='store_true', help='Required with --reset.')

    def handle(self, *args, **options):
        if options['reset'] and not options['yes']:
            raise CommandError('Demo reset requires --reset --yes.')
        output = StringIO()
        with transaction.atomic():
            candidates = School.objects.select_for_update().filter(Q(email=DEMO_EMAIL) | Q(name=DEMO_NAME))
            if candidates.count() > 1:
                raise CommandError('Conflicting Sunrise demo identifiers; refusing changes.')
            school = candidates.first()
            if school and (not school.is_demo or school.email != DEMO_EMAIL or school.name != DEMO_NAME):
                raise CommandError('Controlled Sunrise identifier belongs to another school; no school was converted to demo.')
            if not school:
                school = School.objects.create(name=DEMO_NAME, email=DEMO_EMAIL, is_demo=True,
                    phone_number='+263000000001', address='100 Fictional Learning Avenue, Harare, Zimbabwe', default_currency='USD')
            # Explicit invocation of this controlled bootstrap confirms Sunrise only.
            call_command('seed_demo_school', school=school.name, yes=True, reset_first=options['reset'],
                         password=options.get('password'), parent_password=options.get('parent_password'),
                         stdout=output, stderr=self.stderr)
        self.stdout.write(output.getvalue(), ending="")
