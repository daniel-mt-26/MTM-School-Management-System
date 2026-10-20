"""Versioned, tenant-locked demo fixtures with explicit row ownership.

The command's IdempotencyRecord holds its durable replay/provenance manifest.
It never adopts an existing row for deletion, nor infers ownership from a name.
"""
import hashlib
import logging
import os
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from . import models as m
from .academic_history import capture_publication, freeze_grade
from .credentials import temporary_password
from .finance import assign_fee, billing_periods, record_payment
from .finance_documents import generate_invoice

DEMO_NAME = "Sunrise Primary School"
DEMO_EMAIL = "demo@sunrise.invalid"
MANIFEST_PATH = "/management/seed_demo_school/v1/"
VERSION = 1
FIRST_NAMES = ("Daniel", "Tariro", "Nyasha", "Ruva", "Farai", "Chipo", "Tinashe", "Rudo", "Kuda", "Tendai")
SURNAMES = ("Grey", "Moyo", "Sibanda", "Ncube", "Dube", "Banda", "Mlambo", "Chirwa", "Mare", "Zhou", "Shumba", "Duma")
SUBJECTS = (("English", "ENG"), ("Mathematics", "MAT"), ("Science and Technology", "SCI"),
            ("Social Science", "SOC"), ("Indigenous Language - Shona", "SHO"), ("Physical Education", "PE"))

# Include every tenant-bearing relation, not just the most convenient parent.
SCOPES = {
    "schooladministrator": ("school",), "teacher": ("school",), "parent": ("school",),
    "academicyear": ("school",), "term": ("academic_year__school",), "schoolclass": ("school",),
    "student": ("school", "school_class__school"),
    "parentstudent": ("parent__school", "student__school"), "subject": ("school",),
    "classsubject": ("school_class__school", "subject__school", "academic_year__school"),
    "teacherassignment": ("teacher__school", "school_class__school"),
    "studentenrollment": ("student__school", "school_class__school", "academic_year__school"),
    "timetable": ("school", "academic_year__school", "term__academic_year__school"),
    "timetableentry": ("school_class__school", "academic_year__school", "term__academic_year__school"),
    "attendancerecord": ("school", "enrollment__student__school", "enrollment__school_class__school", "academic_year__school"),
    "homework": ("school", "school_class__school"), "staffannouncement": ("school",),
    "notification": ("school",), "announcement": ("school",),
    "academicresult": ("student_enrollment__student__school", "class_subject__school_class__school", "class_subject__subject__school"),
    "reportcomment": ("teacher__school", "enrollment__student__school"),
    "reportcard": ("student_enrollment__student__school",),
    "reportcardpublication": ("report_card__student_enrollment__student__school",),
    "schooldocumentsettings": ("school",), "schoolcommunicationsettings": ("school",),
    "schoolinvoicesequence": ("school",), "recurringfeetemplate": ("school", "academic_year__school", "term__academic_year__school"),
    "fee": ("school", "academic_year__school", "term__academic_year__school"),
    "studentfeeassignment": ("student__school", "fee__school"),
    "payment": ("student_fee_assignment__student__school", "student_fee_assignment__fee__school"),
    "receipt": ("payment__student_fee_assignment__student__school",),
    "financialledgerentry": ("student__school",),
    "studentinvoice": ("school", "assignment__student__school", "assignment__fee__school"),
    "financeaccount": ("school",), "financecategory": ("school",), "manualincome": ("school",),
    "expense": ("school",), "expenseattachment": ("expense__school",),
    "financialreportnote": ("school",), "inventorycategory": ("school",),
    "inventoryitem": ("school", "category__school"), "inventoryvariant": ("item__school",),
    "inventorystockmovement": ("school", "item__school"), "teachingresource": ("teacher__school", "school_class__school"),
    "auditlog": ("school",),
}


def target_school(name, *, lock=False):
    query = m.School.objects.select_for_update() if lock else m.School.objects
    try:
        school = query.get(name=name)
    except m.School.DoesNotExist as exc:
        raise CommandError("Target school does not exist. Create the controlled demo school first.") from exc
    if not school.is_demo:
        raise CommandError("Refusing: target school is not explicitly marked is_demo=True.")
    return school


def manifest_for(school):
    records = list(m.IdempotencyRecord.objects.filter(school=school, request_method="COMMAND", request_path=MANIFEST_PATH)[:2])
    if len(records) > 1:
        raise CommandError("Multiple demo manifests found; refusing ambiguous ownership.")
    return records[0] if records else None


def scope_query(model, school):
    if model is m.User:
        return (Q(school_administrator__school=school) | Q(teacher_profile__school=school) | Q(parent_profile__school=school))
    if model._meta.model_name not in SCOPES:
        raise CommandError(f"Unknown manifest model: {model._meta.label_lower}")
    query = Q()
    for lookup in SCOPES[model._meta.model_name]:
        query &= Q(**{lookup: school})
    return query


def manifest_objects(manifest, school):
    if manifest.get("version") != VERSION or not isinstance(manifest.get("objects"), dict):
        raise CommandError("Unsupported or damaged demo seed manifest; refusing changes.")
    grouped = defaultdict(set)
    for entry in manifest["objects"].values():
        try:
            model = apps.get_model(entry["model"])
            if not isinstance(entry["pk"], int) or entry["pk"] <= 0 or type(entry["owned"]) is not bool:
                raise ValueError("Invalid ownership entry")
            grouped[model].add(entry["pk"])
        except (KeyError, LookupError, TypeError, ValueError) as exc:
            raise CommandError("Damaged demo seed ownership entry.") from exc
    result = {}
    for model, ids in grouped.items():
        rows = model.objects.filter(pk__in=ids)
        if model is m.User and rows.filter(Q(is_superuser=True) | Q(role="platform_admin")).exists():
            raise CommandError("Platform/superuser accounts cannot belong to a demo seed manifest.")
        if rows.count() != len(ids) or rows.filter(scope_query(model, school)).count() != len(ids):
            raise CommandError(f"Missing or foreign demo rows in {model._meta.label}; refusing changes.")
        # Check optional tenant-bearing FKs as well (account, category, subject...).
        for field in model._meta.fields:
            related = field.remote_field.model if field.is_relation else None
            if related is m.User:
                valid_actor = (Q(**{field.name + '__school_administrator__school': school}) |
                               Q(**{field.name + '__teacher_profile__school': school}) |
                               Q(**{field.name + '__parent_profile__school': school}))
                if rows.filter(**{field.name + '__isnull': False}).exclude(valid_actor).exists():
                    raise CommandError(f"Foreign account reference in {model._meta.label}.{field.name}.")
            if related and related._meta.model_name in SCOPES:
                for lookup in SCOPES[related._meta.model_name]:
                    if rows.filter(**{field.name + "__isnull": False}).exclude(**{field.name + "__" + lookup: school}).exists():
                        raise CommandError(f"Cross-school reference in {model._meta.label}.{field.name}.")
        for field in model._meta.many_to_many:
            related = field.remote_field.model
            targets = related.objects.filter(**{field.related_query_name() + '__pk__in': ids})
            for lookup in SCOPES.get(related._meta.model_name, ()):
                if targets.exclude(**{lookup: school}).exists():
                    raise CommandError(f"Cross-school many-to-many reference in {model._meta.label}.{field.name}.")
        result[model] = {obj.pk: obj for obj in rows}
    return result


def reset_owned(manifest, school):
    """Delete only proven generated rows; any external dependent aborts reset."""
    cache = manifest_objects(manifest, school)
    owned = defaultdict(set)
    for entry in manifest["objects"].values():
        if entry["owned"]:
            owned[apps.get_model(entry["model"])].add(entry["pk"])
    # Lock deletion targets before inspecting dependents. New FK/M2M references
    # must wait, so concurrent walkthrough writes cannot slip into a cascade.
    for model in sorted(owned, key=lambda item: item._meta.label_lower):
        list(model.objects.select_for_update().filter(pk__in=owned[model]).order_by('pk').values_list('pk', flat=True))
    # Refuse even CASCADE/SET_NULL or M2M side effects on unowned data.
    for model, ids in owned.items():
        for relation in model._meta.get_fields(include_hidden=True):
            if not relation.auto_created or relation.concrete or not relation.one_to_many and not relation.one_to_one:
                continue
            child = relation.related_model
            linked = child.objects.filter(**{relation.field.attname + "__in": ids})
            if child._meta.auto_created:
                other_fields = [f for f in child._meta.fields if f.is_relation and f.name != relation.field.name]
                # A through row is safe only when its owning object is also deleted.
                if not any(linked.exclude(**{f.attname + "__in": owned.get(f.remote_field.model, set())}).count() == 0 for f in other_fields):
                    raise CommandError(f"Reset would change unowned links to {model._meta.label}.")
            elif linked.exclude(pk__in=owned.get(child, set())).exists():
                raise CommandError(f"Reset blocked by unowned {child._meta.label} records; nothing deleted.")
    old_files = []
    for model, ids in owned.items():
        for obj in cache[model].values():
            if obj.pk in ids and hasattr(obj, "file") and obj.file:
                old_files.append((obj.file.storage, obj.file.name))
    pending = dict(owned)
    while pending:
        progress = False
        for model, ids in list(pending.items()):
            try:
                # ProtectedError can be raised before Django enters its delete transaction.
                with transaction.atomic():
                    model.objects.filter(pk__in=ids).delete()
            except ProtectedError:
                continue
            del pending[model]
            progress = True
        if not progress:
            raise CommandError("Demo reset has protected dependencies; transaction rolled back.")
    manifest["objects"] = {key: value for key, value in manifest["objects"].items() if not value["owned"]}
    return old_files


class DemoSeeder:
    def __init__(self, school, *, as_of=None, reset=False, passwords=None):
        self.school = school
        self.prefix = "sunrise" if school.name == DEMO_NAME else f"demo-{school.pk}"
        self.passwords = passwords or {}
        self.credentials = []
        self.files_written = []
        self.old_files = []
        self.actor = self.admin()
        self.record = manifest_for(school)
        if self.record:
            self.manifest = self.record.response_body
            manifest_objects(self.manifest, school)
            try:
                date.fromisoformat(self.manifest["as_of"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CommandError("Damaged demo calendar; refusing changes.") from exc
            if self.record.actor_id != self.actor.pk:
                raise CommandError("Demo manifest administrator changed; refusing to adopt it.")
            if as_of and as_of.isoformat() != self.manifest["as_of"] and not reset:
                raise CommandError("Use --reset-first --yes to change the demo calendar.")
            if reset:
                self.old_files = reset_owned(self.manifest, school)
                if as_of:
                    self.manifest["as_of"] = as_of.isoformat()
        else:
            self.manifest = {"version": VERSION, "as_of": (as_of or timezone.localdate()).isoformat(), "objects": {}}
        self.day = date.fromisoformat(self.manifest["as_of"])
        self.cache = manifest_objects(self.manifest, school)

    def admin(self):
        username = f"{self.prefix}-admin"
        user = m.User.objects.filter(username=username).first()
        if user:
            if user.role != m.User.Role.SCHOOL_ADMIN or user.is_superuser or not m.SchoolAdministrator.objects.filter(user=user, school=self.school).exists():
                raise CommandError("Demo admin username belongs to another account; refusing changes.")
            return user
        user = self.new_user(username, m.User.Role.SCHOOL_ADMIN, "Sam", "Demo", "admin@sunrise.invalid")
        m.SchoolAdministrator.objects.create(user=user, school=self.school)
        return user

    def new_user(self, username, role, first, last, email):
        password = self.passwords.get(role) or os.getenv(f"MTM_DEMO_{'ADMIN' if role == 'school_admin' else role.upper()}_PASSWORD")
        generated = not password
        password = password or temporary_password()
        user = m.User.objects.create_user(username=username, password=password, role=role, first_name=first, last_name=last,
                                          email=email, must_change_password=True)
        self.credentials.append((username, password if generated else None))
        return user

    def remember(self, key, obj, *, owned=True):
        self.manifest["objects"][key] = {"model": obj._meta.label_lower, "pk": obj.pk, "owned": owned}
        self.cache.setdefault(type(obj), {})[obj.pk] = obj
        return obj

    def get(self, key):
        item = self.manifest["objects"].get(key)
        return self.cache[apps.get_model(item["model"])][item["pk"]] if item else None

    def ensure(self, model, key, *, lookup=None, retain=False, **values):
        obj = self.get(key)
        if obj:
            return obj
        obj = model.objects.filter(**lookup).first() if lookup else None
        owned = obj is None and not retain
        if obj is None:
            obj = model(**values)
            obj.full_clean()
            obj.save()
        return self.remember(key, obj, owned=owned)

    def bulk(self, model, pairs):
        fresh = [(key, obj) for key, obj in pairs if not self.get(key)]
        model.objects.bulk_create([obj for _, obj in fresh], batch_size=500)
        for key, obj in fresh:
            self.remember(key, obj)

    def event(self, key, resource, topic):
        return self.ensure(m.AuditLog, "audit:" + key, school=self.school, actor=self.actor,
                           action="demo_seed_" + topic, resource_type=resource.__class__.__name__, resource_id=str(resource.pk),
                           description="Synthetic demo fixture action; not a real customer or security event.")

    def account(self, index, role, first, last, email):
        key = f"user:{role}:{index}"
        user = self.get(key)
        if user:
            return user
        username = "demo.parent" if self.prefix == "sunrise" and role == "parent" and index == 0 else f"{self.prefix}-{role}-{index + 1:02d}"
        user = m.User.objects.filter(username=username).first()
        if user:
            profile = m.Parent if role == "parent" else m.Teacher
            if user.role != role or user.is_superuser or not profile.objects.filter(user=user, school=self.school).exists():
                raise CommandError(f"Demo username collision: {username}; no account reassigned.")
            return self.remember(key, user, owned=False)
        return self.remember(key, self.new_user(username, role, first, last, email))

    def term_for(self, day):
        return self.terms[(day.year, min((day.month - 1) // 4 + 1, 3))]

    def seed(self):
        self.setup()
        self.people()
        self.teaching()
        self.academics()
        self.finances()
        self.inventory()
        self.resources()
        if self.record is None:
            self.record = m.IdempotencyRecord(school=self.school, actor=self.actor,
                operation_id=uuid5(NAMESPACE_URL, f"mtm:demo-seed:v1:{self.school.pk}"), request_method="COMMAND",
                request_path=MANIFEST_PATH, payload_hash=hashlib.sha256(b"demo-seed-v1").hexdigest(), response_status=200)
        self.record.response_body = self.manifest
        self.record.save()
        for storage, name in self.old_files:
            transaction.on_commit(lambda storage=storage, name=name: storage.delete(name), robust=True)

    def setup(self):
        if self.school.name == DEMO_NAME and self.school.email == DEMO_EMAIL and not self.school.address:
            self.school.address = "100 Fictional Learning Avenue, Harare, Zimbabwe"
            self.school.save(update_fields=["address"])
        self.settings = self.ensure(m.SchoolDocumentSettings, "document-settings", lookup={"school": self.school}, retain=True,
            school=self.school, motto="Learning today, leading tomorrow", website="https://sunrise.invalid", contact_person="Demo school office",
            parent_invoice_access=True, grading_scale=[{"minimum": "80", "grade": "A"}, {"minimum": "65", "grade": "B"},
                {"minimum": "50", "grade": "C"}, {"minimum": "0", "grade": "D"}])
        self.ensure(m.SchoolCommunicationSettings, "communications", lookup={"school": self.school}, retain=True,
                    school=self.school, whatsapp_enabled=False)
        self.years, self.terms = {}, {}
        for number in (self.day.year - 1, self.day.year):
            year = self.ensure(m.AcademicYear, f"year:{number}", lookup={"school": self.school, "name": str(number)},
                school=self.school, name=str(number), start_date=date(number, 1, 1), end_date=date(number, 12, 31), is_current=number == self.day.year)
            self.years[number] = year
            for sequence in (1, 2, 3):
                month = (sequence - 1) * 4 + 1
                end = date(number + 1, 1, 1) - timedelta(days=1) if sequence == 3 else date(number, month + 4, 1) - timedelta(days=1)
                self.terms[number, sequence] = self.ensure(m.Term, f"term:{number}:{sequence}",
                    lookup={"academic_year": year, "sequence": sequence}, academic_year=year, sequence=sequence,
                    name=f"Term {sequence}", start_date=date(number, month, 1), end_date=end)
        self.classes = [self.ensure(m.SchoolClass, f"class:{grade}", lookup={"school": self.school, "name": f"Grade {grade}"},
                                    school=self.school, name=f"Grade {grade}") for grade in range(2, 8)]
        self.subjects = [self.ensure(m.Subject, f"subject:{code}", lookup={"school": self.school, "code": code},
                                     school=self.school, name=name, code=code) for name, code in SUBJECTS]

    def people(self):
        self.teachers, self.parents, self.students, self.enrollments = [], [], [], {}
        for index, first in enumerate(("Tendai", "Rudo", "Farai", "Nyasha", "Chipo")):
            user = self.account(index, "teacher", first, SURNAMES[index + 1], f"teacher{index + 1}@sunrise.invalid")
            teacher = self.ensure(m.Teacher, f"teacher:{index}", lookup={"user": user}, user=user, school=self.school)
            self.teachers.append(teacher)
            self.event(f"teacher:{index}", teacher, "teacher_created")
        for index in range(31):
            user = self.account(index, "parent", "Nomsa" if index == 0 else FIRST_NAMES[index % 10], SURNAMES[index % 12],
                                "" if index == 30 else f"parent{index + 1}@sunrise.invalid")
            parent = self.ensure(m.Parent, f"parent:{index}", lookup={"user": user}, user=user, school=self.school,
                                 phone_number=f"+263000{index:06d}", address="Fictional Sunrise demonstration community, Zimbabwe")
            self.parents.append(parent)
        for index in range(60):
            cls = self.classes[index % 6]
            # No admission allocator exists in the current model/API; reserve a demo namespace.
            admission = f"DEMO-{self.day.year}-{index + 1:04d}"
            student = self.ensure(m.Student, f"student:{index}", school=self.school, admission_number=admission,
                first_name=FIRST_NAMES[index % 10], last_name=SURNAMES[index // 5], school_class=cls,
                date_of_birth=date(self.day.year - 7 - index % 6, index % 12 + 1, index % 25 + 1), enrolled_on=date(self.day.year - 1, 1, 1))
            self.students.append(student)
            for number, year in self.years.items():
                self.enrollments[index, number] = self.ensure(m.StudentEnrollment, f"enrollment:{index}:{number}",
                    student=student, school_class=cls, academic_year=year, enrolled_on=year.start_date,
                    left_on=year.end_date if number < self.day.year else None)
            parent = self.parents[0 if index < 2 else 1 + (index - 2) // 2]
            self.ensure(m.ParentStudent, f"guardian:{index}", lookup={"parent": parent, "student": student},
                        parent=parent, student=student, relationship="Parent", is_primary_contact=True)
        self.ensure(m.ParentStudent, "second-guardian", parent=self.parents[30], student=self.students[0], relationship="Guardian")

    def teaching(self):
        self.class_subjects = {}
        for ci, cls in enumerate(self.classes):
            for number, year in self.years.items():
                for si, subject in enumerate(self.subjects):
                    cs = self.ensure(m.ClassSubject, f"class-subject:{ci}:{number}:{si}",
                        lookup={"school_class": cls, "subject": subject, "academic_year": year}, school_class=cls, subject=subject, academic_year=year)
                    self.class_subjects[ci, number, si] = cs
            for ti, teacher in enumerate(self.teachers):
                assignment = self.ensure(m.TeacherAssignment, f"assignment:{ci}:{ti}", teacher=teacher, school_class=cls)
                desired = [self.class_subjects[ci, number, si] for number in self.years for si in range(6) if (ci + si) % 5 == ti]
                if not assignment.subjects.exists():
                    assignment.subjects.add(*desired)
                self.event(f"assignment:{ci}:{ti}", assignment, "assignment_created")
        term = self.term_for(self.day)
        for ci, cls in enumerate(self.classes):
            plan = self.ensure(m.Timetable, f"timetable:{ci}", school=self.school, name=f"Demo {cls.name} Week",
                               scope="SINGLE", academic_year=self.years[self.day.year], term=term)
            if not plan.classes.exists():
                plan.classes.add(cls)
            for weekday in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
                # Grade slots are staggered, so shared teachers are never double-booked.
                start = datetime.combine(self.day, time(8)) + timedelta(minutes=ci * 50)
                for slot in range(3):
                    si = (ci + ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday").index(weekday)) % 6
                    begin = start + timedelta(minutes=slot * 15)
                    self.ensure(m.TimetableEntry, f"period:{ci}:{weekday}:{slot}", timetable=plan, school_class=cls,
                        academic_year=self.years[self.day.year], term=term, day_of_week=weekday, start_time=begin.time(),
                        end_time=(begin + timedelta(minutes=15)).time(), subject=self.subjects[si] if slot != 1 else None,
                        label="Break / lunch and reading" if slot == 1 else "")
            for status, offset in (("draft", 0), ("published", 2), ("closed", 12)):
                teacher = self.teachers[(ci + 0) % 5]
                self.ensure(m.Homework, f"homework:{ci}:{status}", school=self.school, school_class=cls, subject=self.subjects[0],
                    title=f"{cls.name} English: {status} comprehension", instructions="Synthetic exercise: read a short story and write five sentences.",
                    date_assigned=self.day - timedelta(days=offset), due_date=self.day - timedelta(days=offset) + timedelta(days=5), status=status, created_by=teacher.user)
        for audience, indexes in (("all", range(5)), ("selected", (0, 2)), ("one", (1,))):
            notice = self.ensure(m.StaffAnnouncement, f"staff-notice:{audience}", school=self.school, author=self.actor,
                                 title=f"Demo staff meeting - {audience}", message="Synthetic notice: review the sports day and teaching timetable.")
            notice.teachers.add(*[self.teachers[i] for i in indexes])
            for i in indexes:
                self.ensure(m.Notification, f"staff-notification:{audience}:{i}", school=self.school, recipient=self.teachers[i].user,
                            title=notice.title, message=notice.message)
            self.event(f"staff-notice:{audience}", notice, "announcement_created")
        for audience, count in (("all", 6), ("selected", 2), ("one", 1)):
            notice = self.ensure(m.StaffAnnouncement, f"teacher-notice:{audience}", school=self.school, author=self.teachers[0].user,
                                 title=f"Demo homework reminder - {audience}", message="Synthetic notice: bring your revision book for the school trip activity.")
            notice.classes.add(*self.classes[:count])
            for i, parent in enumerate(self.parents):
                if parent.student_links.filter(student__school_class__in=self.classes[:count]).exists():
                    self.ensure(m.Notification, f"parent-notification:{audience}:{i}", school=self.school, recipient=parent.user,
                                title=notice.title, message=notice.message)
            self.event(f"teacher-notice:{audience}", notice, "announcement_created")
        self.ensure(m.Announcement, "school-notice", school=self.school, title="Demo sports day", message="Synthetic school notice: families are welcome.",
                    audience="all_parents", channels=["in_app"], status="sent", recipient_count=len(self.parents), created_by=self.actor)

    def academics(self):
        attendance = []
        for index, student in enumerate(self.students):
            cursor = self.day - timedelta(days=89)
            while cursor <= self.day:
                if cursor.weekday() < 5:
                    code = (index + cursor.day) % 17
                    status = "absent" if code == 0 else "late" if code == 1 else "excused" if code == 2 else "present"
                    attendance.append((f"attendance:{index}:{cursor}", m.AttendanceRecord(school=self.school,
                        enrollment=self.enrollments[index, cursor.year], academic_year=self.years[cursor.year], term=self.term_for(cursor),
                        attendance_date=cursor, status=status, recorded_by=self.teachers[index % 5].user)))
                cursor += timedelta(days=1)
        self.bulk(m.AttendanceRecord, attendance)
        self.event("attendance", self.school, "attendance_populated")
        self.results = []
        for index, student in enumerate(self.students):
            ci = index % 6
            periods = [(self.day.year - 1, 3), (self.day.year, 1), (self.day.year, 2), (self.day.year, 3)]
            for number, seq in periods:
                term = self.terms[number, seq]
                if term.start_date > self.day:
                    continue
                current = term.pk == self.term_for(self.day).pk
                status = ("draft", "submitted", "approved", "published")[index % 4] if current else "published"
                enrollment = self.enrollments[index, number]
                for si in range(6):
                    key = f"result:{index}:{number}:{seq}:{si}"
                    result = self.get(key)
                    if not result:
                        result = m.AcademicResult(student_enrollment=enrollment, term=term, class_subject=self.class_subjects[ci, number, si],
                            score=Decimal(45 + (index * 7 + si * 3) % 51), maximum_score=100, status=status,
                            comment=("Strong progress", "Good effort", "Revise key ideas", "Consistent participation")[index % 4],
                            recorded_by=self.teachers[(ci + si) % 5].user)
                        if status == "published":
                            freeze_grade(result, self.school)
                        result.full_clean(); result.save(); self.remember(key, result)
                    self.results.append(result)
                teacher = self.teachers[ci % 5]
                self.ensure(m.ReportComment, f"comment:{index}:{number}:{seq}", teacher=teacher, enrollment=enrollment, term=term,
                    comment=("Strong academic performance and positive conduct.", "Good effort; continue regular revision.",
                             "Improvement needed in independent study.", "Attendance and punctuality deserve attention.")[index % 4])
                card = self.ensure(m.ReportCard, f"card:{index}:{number}:{seq}", student_enrollment=enrollment, term=term, is_published=status == "published")
                if card.is_published and not self.get(f"publication:{index}:{number}:{seq}"):
                    publication = capture_publication(card, SimpleNamespace(user=self.actor))
                    self.remember(f"publication:{index}:{number}:{seq}", publication)
                    for event in m.AuditLog.objects.filter(school=self.school, action="academic_record_published", resource_id=str(publication.pk)):
                        self.remember(f"publication-audit:{publication.pk}:{event.pk}", event)
        self.event("results", self.school, "result_workflow_populated")

    def charge(self, key, student, fee, day):
        charge = self.get(key)
        if charge:
            return charge
        charge, created = assign_fee(student=student, fee=fee, amount_owed=fee.amount, assigned_on=day)
        self.remember(key, charge, owned=created)
        if created:
            ledger = charge.ledger_entries.get(entry_type="charge")
            m.FinancialLedgerEntry.objects.filter(pk=ledger.pk).update(occurred_at=datetime.combine(day, time(10), dt_timezone.utc))
            self.remember("ledger:" + key, ledger)
        return charge

    def pay(self, key, charge, amount, day, method):
        payment = self.get(key)
        if payment:
            return payment
        payment, receipt = record_payment(student_fee_assignment=charge, amount=Decimal(amount),
            paid_at=datetime.combine(day, time(11), dt_timezone.utc), method=method, reference=f"DEMO-{self.school.pk}-{key}",
            recorded_by=self.actor, receipt_number=f"DEMO-{self.school.pk}-{key}"[:50], account=self.accounts[method != "cash"],
            income_category=self.fee_category, notify=False)
        self.remember(key, payment); self.remember("receipt:" + key, receipt); self.remember("ledger:" + key, payment.ledger_entry)
        self.event(key, payment, "payment_recorded")
        return payment

    def finances(self):
        self.accounts = [self.ensure(m.FinanceAccount, "account:" + kind, lookup={"school": self.school, "name": "Demo " + kind.title()},
            school=self.school, name="Demo " + kind.title(), kind=kind) for kind in ("cash", "bank")]
        self.fee_category = self.ensure(m.FinanceCategory, "category:fees", school=self.school, name="Demo School Fees", kind="income")
        other_category = self.ensure(m.FinanceCategory, "category:fundraising", school=self.school, name="Demo Fundraising", kind="income")
        term = self.term_for(self.day)
        templates = []
        for name, amount, method in (("Tuition", 120, "TERMLY"), ("Transport", 30, "MONTHLY"), ("Development Levy", 45, "ONE_OFF"),
                                      ("Stationery", 20, "ONE_OFF"), ("After School Care", 25, "MONTHLY"), ("Meal Contribution", 15, "MONTHLY")):
            templates.append(self.ensure(m.RecurringFeeTemplate, "template:" + name, school=self.school,
                academic_year=self.years[self.day.year], term=term, name="Demo " + name, amount=Decimal(amount), currency=self.school.default_currency,
                billing_method=method, start_month=term.start_date, end_month=term.end_date))
        tuition = self.ensure(m.Fee, "fee:tuition", school=self.school, academic_year=term.academic_year, term=term,
            name="Demo Tuition / Period 1", amount=templates[0].amount, currency=self.school.default_currency, due_date=min(self.day, term.start_date + timedelta(days=14)),
            recurring_template=templates[0], period_sequence=1)
        for index, student in enumerate(self.students):
            charge = self.charge(f"charge:{index}:tuition", student, tuition, term.start_date)
            if index % 6 in (0, 4, 5):
                self.pay(f"payment:{index}:tuition", charge, "120", self.day if index % 2 == 0 else min(self.day, term.start_date + timedelta(days=10)), ("cash", "bank", "mobile money")[index % 3])
            elif index % 6 == 1:
                self.pay(f"payment:{index}:tuition", charge, "45", self.day, "mobile money")
            if index % 6 in (4, 5):
                for template in templates[1:3]:
                    starts = billing_periods(template)
                    for sequence, (start, _) in enumerate(starts, 1):
                        if start > self.day:
                            continue
                        fee = self.ensure(m.Fee, f"fee:{template.name}:{sequence}", school=self.school, academic_year=term.academic_year, term=term,
                            name=f"{template.name} / Period {sequence}", amount=template.amount, currency=self.school.default_currency,
                            due_date=start + timedelta(days=10), recurring_template=template, period_sequence=sequence, charge_month=start)
                        extra = self.charge(f"charge:{index}:{template.name}:{sequence}", student, fee, start)
                        if index % 6 == 4:
                            self.pay(f"payment:{index}:{template.name}:{sequence}", extra, str(extra.amount_owed), min(self.day, start + timedelta(days=3)), "bank")
        # Real obligation dates drive ageing and carried-forward balances.
        for offset, student_index in ((10, 2), (45, 3), (75, 8), (120, 9), (-14, 14), (self.day.timetuple().tm_yday + 15, 15)):
            due = self.day - timedelta(days=offset)
            assigned = due - timedelta(days=7) if offset >= 0 else self.day
            fee_term = self.term_for(assigned)
            fee = self.ensure(m.Fee, f"fee:age:{offset}", school=self.school, academic_year=fee_term.academic_year, term=fee_term,
                name=f"Demo carried balance / due {due}", amount=Decimal(35 + student_index), currency=self.school.default_currency, due_date=due)
            self.charge(f"charge:age:{student_index}", self.students[student_index], fee, assigned)
        # All canonical invoices remain one charge each; never fabricate multi-line invoices.
        invoice_targets = [(f"invoice:{index}", self.get(f"charge:{index}:tuition")) for index in range(18)]
        for index in (4, 5):
            for extra in self.students[index].fee_assignments.exclude(fee=tuition).select_related('fee').order_by('assigned_on', 'pk'):
                # Include only managed charges, never unrelated operator obligations.
                if extra.pk in {entry['pk'] for entry in self.manifest['objects'].values() if entry['model'] == 'core.studentfeeassignment'}:
                    invoice_targets.append((f"invoice:extra:{index}:{extra.fee.name}", extra))
        for key, charge in invoice_targets:
            if not self.get(key):
                invoice, created = generate_invoice(school=self.school, assignment_id=charge.pk, actor=self.actor)
                self.remember(key, invoice, owned=created)
                for event in m.AuditLog.objects.filter(school=self.school, action="invoice_generated", resource_id=str(invoice.pk)):
                    self.remember(f"invoice-audit:{invoice.pk}:{event.pk}", event)
        sequence = m.SchoolInvoiceSequence.objects.get(school=self.school)
        self.remember("invoice-sequence", sequence, owned=False)
        categories = ("Salaries", "Utilities", "Stationery", "Transport", "Repairs and Maintenance", "Cleaning Supplies", "Food/Groceries", "Learning Materials", "Administration", "Other")
        for index, name in enumerate(categories):
            category = self.ensure(m.FinanceCategory, f"expense-category:{index}", school=self.school, name="Demo " + name, kind="expense")
            for month_offset in (0, 1, 2):
                day = self.day - timedelta(days=month_offset * 31 + index % 10)
                self.ensure(m.Expense, f"expense:{index}:{month_offset}", school=self.school, account=self.accounts[index % 2], finance_category=category,
                    category="other", expense_date=day, description=f"Demo {name} purchase", payee="Synthetic school supplier",
                    amount=Decimal(18 + index * 13 + month_offset), currency=self.school.default_currency, payment_method=("cash", "bank")[index % 2],
                    reference=f"DEMO-EXP-{index}-{month_offset}", notes="Fictional walkthrough expense", recorded_by=self.actor)
        for index, source in enumerate(("Fundraising", "Uniform sales", "School event")):
            for month_offset in (0, 1, 2):
                income = self.ensure(m.ManualIncome, f"income:{index}:{month_offset}", school=self.school, account=self.accounts[index % 2], category=other_category,
                    income_date=self.day - timedelta(days=month_offset * 31 + index), source=source, description="Synthetic non-student receipts",
                    amount=Decimal(100 + index * 75), currency=self.school.default_currency, payment_method=("cash", "bank")[index % 2],
                    reference=f"DEMO-IN-{index}-{month_offset}", recorded_by=self.actor)
                self.event(f"income:{index}:{month_offset}", income, "income_recorded")
        self.event("expenses", self.school, "expenses_created")
        self.ensure(m.FinancialReportNote, "financial-note", school=self.school, start_date=self.day.replace(day=1),
                    end_date=date(self.day.year, self.day.month, monthrange(self.day.year, self.day.month)[1]),
                    body="Synthetic walkthrough figures. Billed fees, receipts and receivables are distinct. No budget or bank reconciliation is implied.", updated_by=self.actor)

    def inventory(self):
        for index, (category_name, item_name) in enumerate((("Stationery", "Exercise Books"), ("Stationery", "Pens"), ("Stationery", "Pencils"),
                ("Textbooks", "Grade 4 Mathematics Textbook"), ("Sports", "Football"), ("Cleaning", "Detergent"), ("Uniforms", "School Shirts"))):
            category = self.ensure(m.InventoryCategory, "stock-category:" + category_name,
                lookup={"school": self.school, "name": "Demo " + category_name}, school=self.school, name="Demo " + category_name)
            item = self.ensure(m.InventoryItem, f"item:{index}", school=self.school, category=category, name=item_name,
                code=f"DEMO-{index + 1:03d}", minimum_stock_level=10, storage_location="Demo storeroom", cost_per_unit=Decimal(index + 1))
            for variant_index, name in enumerate(("Standard", "Large")):
                variant = self.ensure(m.InventoryVariant, f"variant:{index}:{variant_index}", item=item, name=name)
                for move, direction, quantity in (("adjustment", "in", 50), ("restock", "in", 20), ("issued", "out", 8 + index)):
                    self.ensure(m.InventoryStockMovement, f"movement:{index}:{variant_index}:{move}", school=self.school, item=item, variant=variant,
                        movement_type=move, direction=direction, quantity=quantity, unit_cost=Decimal(index + 1), notes="Synthetic opening stock" if move == "adjustment" else "Synthetic demo movement", created_by=self.actor)
            self.event(f"inventory:{index}", item, "inventory_populated")

    def file_record(self, model, key, filename, **values):
        if self.get(key):
            return self.get(key)
        from reportlab.pdfgen.canvas import Canvas
        output = BytesIO()
        canvas = Canvas(output, invariant=True)
        canvas.drawString(50, 780, "SUNRISE DEMO - synthetic revision / supporting document")
        canvas.drawString(50, 755, "Practice: read, count, explain. No private people or financial evidence.")
        canvas.save()
        obj = model(**values)
        if model is m.ExpenseAttachment:
            obj.size = len(output.getvalue())
        obj.file.save(filename, ContentFile(output.getvalue()), save=False)
        self.files_written.append((obj.file.storage, obj.file.name))
        obj.full_clean(); obj.save()
        return self.remember(key, obj)

    def resources(self):
        for index, title in enumerate(("English Comprehension Worksheet", "Mathematics Revision Notes", "Science Revision Guide")):
            self.file_record(m.TeachingResource, f"resource:{index}", f"demo-revision-{index}.pdf", teacher=self.teachers[(index * 2) % 5],
                school_class=self.classes[index], class_subject=self.class_subjects[index, self.day.year, index], title=title)
        expense = self.get("expense:0:0")
        self.file_record(m.ExpenseAttachment, "expense-document", "demo-supporting-document.pdf", expense=expense,
                        original_name="demo-supporting-document.pdf", content_type="application/pdf", size=1, uploaded_by=self.actor)


@transaction.atomic
def seed_demo(name, *, confirmed=False, reset=False, as_of=None, passwords=None):
    if not confirmed:
        raise CommandError("Explicit demo confirmation is required: add --yes.")
    school = target_school(name, lock=True)
    seeder = None
    try:
        seeder = DemoSeeder(school, as_of=as_of, reset=reset, passwords=passwords)
        seeder.seed()
        from .demo_verify import verify_demo
        seeder.counts, seeder.summary = verify_demo(school)
        return seeder
    except Exception:
        if seeder:
            for storage, filename in seeder.files_written:
                try:
                    storage.delete(filename)
                except Exception:
                    logging.getLogger(__name__).exception("Could not clean an uncommitted demo fixture file")
        raise
