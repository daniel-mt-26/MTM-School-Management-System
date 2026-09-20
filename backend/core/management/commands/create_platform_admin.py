from django.core.management.base import BaseCommand, CommandError

from core.models import User


class Command(BaseCommand):
    help = "Interactively create an application-level MTM platform administrator."

    def handle(self, *args, **options):
        username = self._required("Username")
        if User.objects.filter(username=username).exists():
            raise CommandError("That username is already in use.")
        email = input("Email (optional): ").strip()
        if email and User.objects.filter(email=email).exists():
            raise CommandError("That email is already in use.")
        first_name = input("First name (optional): ").strip()
        last_name = input("Last name (optional): ").strip()
        password = self._password()
        user = User(username=username, email=email, first_name=first_name, last_name=last_name, role=User.Role.PLATFORM_ADMIN)
        user.set_password(password)
        user.full_clean()
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Platform administrator '{user.username}' created."))

    def _required(self, label):
        value = input(f"{label}: ").strip()
        if not value:
            raise CommandError(f"{label} is required.")
        return value

    def _password(self):
        from getpass import getpass
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        password = getpass("Password: ")
        confirmation = getpass("Password (again): ")
        if password != confirmation:
            raise CommandError("Passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        return password
