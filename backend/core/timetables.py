"""Shared schedule conflict rules for legacy entries and reusable timetables."""
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .models import ClassSubject, School, Timetable, TimetableEntry


def conflicts(*, classes, year, term, entry, exclude_timetable=None, exclude_entry=None):
    rows = TimetableEntry.objects.filter(
        Q(timetable__classes__in=classes) | Q(timetable__isnull=True, school_class__in=classes),
        academic_year=year, term=term, day_of_week=entry['day_of_week'],
        start_time__lt=entry['end_time'], end_time__gt=entry['start_time'],
    ).distinct()
    if exclude_timetable:
        rows = rows.exclude(timetable_id=exclude_timetable)
    if exclude_entry:
        rows = rows.exclude(pk=exclude_entry)
    conflict = rows.select_related('school_class', 'timetable').first()
    if conflict:
        affected = conflict.timetable.classes.filter(pk__in=[c.pk for c in classes]).first() if conflict.timetable_id else conflict.school_class
        raise ValidationError({'entries': f'{affected.name}: {conflict.day_of_week} conflicts with {conflict.start_time:%H:%M}–{conflict.end_time:%H:%M}.'})


@transaction.atomic
def save_timetable(*, school, data, instance=None):
    # Both legacy entry writes and shared timetable writes use this school lock.
    School.objects.select_for_update().get(pk=school.pk)
    if instance:
        instance = Timetable.objects.select_for_update().get(pk=instance.pk, school=school)
    classes = data.get('classes', list(instance.classes.all()) if instance else [])
    year = data.get('academic_year', instance.academic_year if instance else None)
    term = data.get('term', instance.term if instance else None)
    entries = data.get('entries')
    if entries is None:
        entries = [
            {'id': row.pk, 'day_of_week': row.day_of_week, 'start_time': row.start_time,
             'end_time': row.end_time, 'subject': row.subject, 'label': row.label}
            for row in instance.entries.select_related('subject')
        ] if instance else []
    if not classes or not entries:
        raise ValidationError('Select at least one class and add at least one entry.')
    if year.school_id != school.pk or term.academic_year_id != year.pk or any(c.school_id != school.pk for c in classes):
        raise ValidationError('Classes, academic year and term must belong to this school and year.')
    existing_ids = set(instance.entries.values_list('id', flat=True)) if instance else set()
    submitted_ids = [row['id'] for row in entries if row.get('id')]
    if len(submitted_ids) != len(set(submitted_ids)) or not set(submitted_ids) <= existing_ids:
        raise ValidationError({'entries': 'Entry IDs must be unique and belong to this timetable.'})
    for index, row in enumerate(entries):
        subject = row.get('subject')
        if subject and (subject.school_id != school.pk or not subject.is_active):
            raise ValidationError({'entries': 'Choose an active subject belonging to this school.'})
        if row['start_time'] >= row['end_time']:
            raise ValidationError({'entries': 'End time must be after start time.'})
        conflicts(classes=classes, year=year, term=term, entry=row, exclude_timetable=instance.pk if instance else None)
        for other in entries[:index]:
            if row['day_of_week'] == other['day_of_week'] and row['start_time'] < other['end_time'] and row['end_time'] > other['start_time']:
                raise ValidationError({'entries': f"{classes[0].name}: overlapping {row['day_of_week']} rows at {row['start_time']:%H:%M}."})
    plan = instance or Timetable(school=school)
    plan.name = data.get('name', plan.name)
    plan.academic_year, plan.term = year, term
    plan.save()
    plan.classes.set(classes)
    # Remove only rows explicitly removed by this edit. Preserve existing IDs.
    plan.entries.exclude(pk__in=submitted_ids).delete()
    # The deferred legacy uniqueness constraint allows time-slot swaps in one edit.
    for row in entries:
        values = {key: value for key, value in row.items() if key != 'id'}
        values.update(timetable=plan, school_class=classes[0], academic_year=year, term=term)
        if row.get('id'):
            TimetableEntry.objects.filter(pk=row['id'], timetable=plan).update(**values)
        else:
            TimetableEntry.objects.create(**values)
        if row.get('subject'):
            for school_class in classes:
                ClassSubject.objects.get_or_create(school_class=school_class, academic_year=year, subject=row['subject'])
    return plan
