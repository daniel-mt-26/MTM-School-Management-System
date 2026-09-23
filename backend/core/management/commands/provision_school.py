"""Provision only a confirmed tenant, administrator and academic structure."""

import getpass
import json
import os
from pathlib import Path
import re
import sys
import warnings

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from core.audit import log_action
from core.models import AcademicYear, School, SchoolClass, Term
from core.platform_services import provision_school


def identity(value):
    return " ".join(value.split()).casefold()


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional):
        raise CommandError("Invalid input object or unsupported fields; see docs/SCHOOL_PROVISIONING.md.")
    if set(required) - set(value):
        raise CommandError("Missing fields: " + ", ".join(sorted(set(required) - set(value))))
    result = {}
    for key, item in value.items():
        if not isinstance(item, str) or (key in required and not item.strip()):
            raise CommandError(f"{key} must be a nonempty string.")
        result[key] = item.strip()
    return result


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CommandError("Duplicate JSON keys are not allowed.")
        result[key] = value
    return result


class Command(BaseCommand):
    help = "Provision a real school from confirmed JSON; no learner or financial data is created."
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="Path to confirmed JSON without passwords.")
        parser.add_argument("--dry-run", action="store_true", help="Validate without database writes.")

    def handle(self, *args, **options):
        # Consume only the dedicated temporary variable, never expose it in errors.
        password = os.environ.pop("MTM_PROVISION_ADMIN_PASSWORD", None)
        try:
            with Path(options["input"]).open(encoding="utf-8-sig") as source:
                data = json.load(source, object_pairs_hook=reject_duplicate_keys)
        except (OSError, ValueError):
            raise CommandError("Cannot read valid provisioning JSON from --input.") from None
        try:
            with transaction.atomic():
                school, user, year, terms, classes = self.validate_input(data)
                if password is None:
                    if not sys.stdin.isatty():
                        raise CommandError("Use a secure terminal prompt or set MTM_PROVISION_ADMIN_PASSWORD temporarily.")
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", getpass.GetPassWarning)
                        try:
                            password = getpass.getpass("Administrator password: ")
                            confirmation = getpass.getpass("Confirm administrator password: ")
                        except (getpass.GetPassWarning, EOFError):
                            raise CommandError("A secure password prompt is unavailable.") from None
                    if password != confirmation:
                        raise CommandError("Passwords do not match.")
                if not password:
                    raise CommandError("Administrator password is required.")
                validate_password(password, user)
                if options["dry_run"]:
                    self.stdout.write(self.style.SUCCESS(
                        f"DRY RUN OK: school, administrator, current academic year, {len(terms)} terms, "
                        f"{len(classes)} classes validated. No records saved. Password change required on first login."
                    ))
                    return
                school, administrator, _ = provision_school(
                    school_data={key: getattr(school, key) for key in
                                 ("name", "email", "phone_number", "address", "default_currency")},
                    admin_data={key: getattr(user, key) for key in
                                ("username", "email", "first_name", "last_name")},
                    password=password,
                )
                year.school = school
                year.save()
                for term in terms:
                    term.academic_year = year
                    term.save()
                for school_class in classes:
                    school_class.school = school
                    school_class.save()
                log_action(school=school, actor=None, action="school_provisioned", resource=school,
                           description="Management command created tenant and confirmed academic structure.")
                log_action(school=school, actor=None, action="school_administrator_created", resource=administrator,
                           description="Management command created initial administrator; password change required.")
        except ValidationError as exc:
            # Model validators can interpolate supplied values. Return field names only.
            invalid = ", ".join(sorted(exc.message_dict)) if hasattr(exc, "message_dict") else "input or password"
            raise CommandError(f"Validation failed for {invalid}. Check field formats, lengths and password policy.") from None
        except DatabaseError:
            raise CommandError("Database operation failed or a concurrent duplicate was detected; nothing provisioned.") from None
        finally:
            password = None
        self.stdout.write(self.style.SUCCESS(
            f"Provisioned school_id={school.pk} user_id={administrator.user_id} "
            f"administrator_id={administrator.pk} academic_year_id={year.pk} "
            f"term_ids={','.join(str(term.pk) for term in terms)} "
            f"class_ids={','.join(str(item.pk) for item in classes)}. Password change required on first login."
        ))

    def validate_input(self, data):
        if not isinstance(data, dict) or set(data) != {"school", "administrator", "academic_year", "terms", "classes"}:
            raise CommandError("Expected only school, administrator, academic_year, terms and classes objects.")
        school_data = fields(data["school"], ("name", "email", "phone_number", "default_currency"), ("address",))
        school_data["name"] = " ".join(school_data["name"].split())
        school_data["email"] = school_data["email"].lower()
        if not re.fullmatch(r"[A-Z]{3}", school_data["default_currency"]):
            raise CommandError("default_currency must be the confirmed three-letter uppercase currency code.")
        school = School(**school_data)
        user_data = fields(data["administrator"], ("username", "email", "first_name"), ("last_name",))
        User = get_user_model()
        user_data["username"] = User.normalize_username(user_data["username"])
        user_data["email"] = user_data["email"].lower()
        user = User(**user_data, role=User.Role.SCHOOL_ADMIN, must_change_password=True)
        user.set_unusable_password()
        # Include inactive/archived/demo schools and inactive users. Never reuse accounts.
        for model, candidate, keys in ((School, school, ("name", "email")), (User, user, ("username", "email"))):
            for row in model.objects.values("pk", *keys).iterator():
                for key in keys:
                    if identity(row[key]) == identity(getattr(candidate, key)):
                        raise CommandError(f"Duplicate {model.__name__} {key}: existing record id={row['pk']}. No records saved.")
        school.full_clean()
        user.full_clean()
        year = AcademicYear(**fields(data["academic_year"], ("name", "start_date", "end_date")), is_current=True)
        year.full_clean(exclude=["school"])
        if year.end_date <= year.start_date:
            raise CommandError("Academic year end_date must follow start_date.")
        if not isinstance(data["terms"], list) or not data["terms"]:
            raise CommandError("At least one confirmed term is required.")
        terms = []
        for sequence, item in enumerate(data["terms"], 1):
            term = Term(**fields(item, ("name", "start_date", "end_date")), sequence=sequence)
            term.full_clean(exclude=["academic_year"])
            if not year.start_date <= term.start_date < term.end_date <= year.end_date:
                raise CommandError("Term dates must be ordered and contained in the academic year.")
            if any(identity(term.name) == identity(other.name) for other in terms):
                raise CommandError("Duplicate term name in input.")
            if terms and term.start_date <= terms[-1].end_date:
                raise CommandError("Terms must be in chronological order without overlapping dates.")
            terms.append(term)
        if not isinstance(data["classes"], list) or not data["classes"]:
            raise CommandError("At least one confirmed class is required.")
        classes = []
        for item in data["classes"]:
            school_class = SchoolClass(**fields(item, ("name",)))
            school_class.full_clean(exclude=["school"])
            if any(identity(school_class.name) == identity(other.name) for other in classes):
                raise CommandError("Duplicate class name in input.")
            classes.append(school_class)
        return school, user, year, terms, classes
