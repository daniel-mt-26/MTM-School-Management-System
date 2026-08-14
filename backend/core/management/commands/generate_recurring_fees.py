from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from core.finance import generate_recurring_charges
from core.models import School


class Command(BaseCommand):
    help = "Idempotently generate recurring fee obligations for a month."

    def add_arguments(self, parser):
        parser.add_argument("--month", required=True, help="Any date in the target month (YYYY-MM-DD).")
        parser.add_argument("--school", type=int, help="Optional school primary key; otherwise all schools are processed.")

    def handle(self, *args, **options):
        month = parse_date(options["month"])
        if not month:
            raise CommandError("--month must use YYYY-MM-DD.")
        schools = School.objects.all()
        if options["school"]:
            schools = schools.filter(pk=options["school"])
            if not schools.exists():
                raise CommandError("The selected school does not exist.")
        for school in schools:
            result = generate_recurring_charges(school=school, for_month=month)
            self.stdout.write(f"{school.name}: {result}")
