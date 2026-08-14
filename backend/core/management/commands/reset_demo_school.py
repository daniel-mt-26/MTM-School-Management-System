from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Safely reset only the is_demo Sunrise tenant; requires --yes."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Required confirmation.")
        parser.add_argument("--password", help="Optional replacement demo admin password.")
        parser.add_argument("--parent-password", help="Optional replacement demo parent password.")

    def handle(self, *args, **options):
        arguments = ["--reset"]
        if options["yes"]:
            arguments.append("--yes")
        if options.get("password"):
            arguments.extend(["--password", options["password"]])
        if options.get("parent_password"):
            arguments.extend(["--parent-password", options["parent_password"]])
        call_command("create_demo_school", *arguments)
