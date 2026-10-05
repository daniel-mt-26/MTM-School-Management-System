from datetime import date, time
from importlib import import_module
from types import SimpleNamespace
import uuid

from django.apps import apps
from rest_framework.test import APITestCase

from . import tests as fixtures
from .curriculum import SUBJECTS, subject_key
from .models import ClassSubject, SchoolClass, Subject, Timetable, TimetableEntry, AttendanceRecord


class AcademicsImprovementsTests(APITestCase):
    setUp = fixtures.TenantIsolationTests.setUp
    make_user = fixtures.TenantIsolationTests.make_user
    make_school_calendar = fixtures.TenantIsolationTests.make_school_calendar
    make_student = fixtures.TenantIsolationTests.make_student
    make_private_records = fixtures.TenantIsolationTests.make_private_records
    authenticate = fixtures.TenantIsolationTests.authenticate

    def payload(self, **changes):
        return {'name': 'General timetable', 'academic_year': self.year_a.pk, 'term': self.term_a.pk,
                'classes': [self.class_a.pk], 'entries': [{'day_of_week': 'Monday', 'start_time': '08:00', 'end_time': '08:30', 'subject': None, 'label': 'Assembly'}], **changes}

    def create_plan(self, **changes):
        self.authenticate(self.admin_a)
        return self.client.post('/api/school/timetable-plans/', self.payload(**changes), format='json')

    def test_library_activation_is_opt_in_idempotent_and_preserves_custom_subject(self):
        self.authenticate(self.admin_a)
        before = Subject.objects.count()
        library = self.client.get('/api/school/subjects/library/')
        self.assertEqual(library.status_code, 200)
        self.assertEqual(Subject.objects.count(), before)
        self.assertIn('Break', library.data['activities'])
        self.assertGreater(len(SUBJECTS), 45)
        existing = Subject.objects.create(school=self.school_a, name='English Language', code='CUSTOM-ENG', is_active=False)
        assignment = ClassSubject.objects.create(school_class=self.class_a, subject=existing, academic_year=self.year_a)
        for _ in range(2):
            response = self.client.post('/api/school/subjects/activate/', {'keys': [subject_key('English Language'), subject_key('Combined Science')]}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
        existing.refresh_from_db(); assignment.refresh_from_db()
        self.assertTrue(existing.is_active)
        self.assertEqual(existing.code, 'CUSTOM-ENG')
        self.assertEqual(assignment.subject_id, existing.pk)
        self.assertEqual(Subject.objects.count(), before + 2)
        self.assertEqual(self.client.post('/api/school/subjects/activate/', {'keys': [str(self.class_b.pk)]}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/school/subjects/{self.class_b.class_subjects.first().subject_id}/', {'is_active': True}, format='json').status_code, 404)

    def test_subject_active_filter_and_timetable_availability(self):
        inactive = Subject.objects.create(school=self.school_a, name='Inactive', code='INACTIVE', is_active=False)
        custom = Subject.objects.create(school=self.school_a, name='Robotics', code='ROBOT')
        self.authenticate(self.admin_a)
        self.assertNotIn(inactive.pk, [s['id'] for s in self.client.get('/api/school/subjects/?active=true').data])
        for subject, expected in [(inactive, 400), (custom, 201), (self.class_b.class_subjects.first().subject, 400)]:
            row = {'day_of_week': 'Tuesday', 'start_time': '09:00', 'end_time': '09:30', 'subject': subject.pk}
            result = self.create_plan(entries=[row])
            self.assertEqual(result.status_code, expected, result.data)

    def test_one_definition_applies_to_grade_three_through_seven(self):
        classes = [SchoolClass.objects.create(school=self.school_a, name=f'Grade {grade}') for grade in range(3, 8)]
        result = self.create_plan(classes=[c.pk for c in classes])
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(len(result.data['classes']), 5)
        self.assertEqual(TimetableEntry.objects.filter(timetable_id=result.data['id']).count(), 1)
        for school_class in classes:
            response = self.client.get('/api/school/timetables/', {'school_class': school_class.pk})
            self.assertEqual(len(response.data), 1)
        self.student_a.school_class = classes[-1]
        self.student_a.save(update_fields=['school_class'])
        self.authenticate(self.parent_a_user)
        self.assertEqual(len(self.client.get(f'/api/parent/students/{self.student_a.pk}/timetable/').data), 1)

    def test_tenant_ownership_and_year_term_validation(self):
        for changes in [{'classes': [self.class_b.pk]}, {'academic_year': self.year_b.pk}, {'term': self.term_b.pk}, {'school_id': self.school_b.pk}]:
            self.assertEqual(self.create_plan(**changes).status_code, 400)
        result = self.create_plan()
        self.assertEqual(result.status_code, 201, result.data)
        self.authenticate(self.admin_b)
        url = f"/api/school/timetable-plans/{result.data['id']}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {'name': 'Attack'}, format='json').status_code, 404)
        self.assertEqual(self.client.get('/api/school/timetable-plans/').data, [])

    def test_overlaps_check_every_attached_class_and_legacy_entries(self):
        other = SchoolClass.objects.create(school=self.school_a, name='Grade 4')
        self.assertEqual(self.create_plan(classes=[other.pk]).status_code, 201)
        result = self.create_plan(classes=[self.class_a.pk, other.pk])
        self.assertEqual(result.status_code, 400)
        self.assertIn('Grade 4', str(result.data))
        self.assertIn('08:00', str(result.data))
        for day, start, end in [('Monday', '08:30', '09:00'), ('Tuesday', '08:00', '08:30')]:
            result = self.create_plan(classes=[self.class_a.pk, other.pk], entries=[{'day_of_week': day, 'start_time': start, 'end_time': end, 'label': 'Break'}])
            self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(self.client.post('/api/school/timetables/', {'school_class': other.pk, 'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'day_of_week': 'Tuesday', 'start_time': '08:15', 'end_time': '08:45', 'label': 'Legacy'}, format='json').status_code, 400)

    def test_edit_add_classes_validates_conflicts_and_preserves_row_ids(self):
        one = self.create_plan()
        row_id = one.data['entries'][0]['id']
        url = f"/api/school/timetable-plans/{one.data['id']}/"
        self.assertEqual(self.client.patch(url, {'name': 'Renamed'}, format='json').status_code, 200)
        self.assertEqual(Timetable.objects.get(pk=one.data['id']).entries.get().pk, row_id)
        other = SchoolClass.objects.create(school=self.school_a, name='Another class')
        self.assertEqual(self.create_plan(classes=[other.pk]).status_code, 201)
        self.assertEqual(self.client.patch(url, {'classes': [self.class_a.pk, other.pk]}, format='json').status_code, 400)
        self.assertEqual(list(Timetable.objects.get(pk=one.data['id']).classes.values_list('pk', flat=True)), [self.class_a.pk])

    def test_invalid_rows_and_internal_overlap_are_atomic(self):
        row = self.payload()['entries'][0]
        for rows in [[{**row, 'end_time': '07:00'}], [row, {**row, 'start_time': '08:15'}], [{**row, 'label': 'Invalid activity'}], [{**row, 'id': 9999}], []]:
            self.assertEqual(self.create_plan(entries=rows).status_code, 400)
        self.assertEqual(Timetable.objects.count(), 0)

    def test_edit_subject_to_activity_clears_reference(self):
        subject = Subject.objects.create(school=self.school_a, name='Music', code='MUSIC')
        row = {'day_of_week': 'Monday', 'start_time': '08:00', 'end_time': '08:30', 'subject': subject.pk}
        created = self.create_plan(entries=[row])
        self.assertEqual(created.status_code, 201, created.data)
        row_id = created.data['entries'][0]['id']
        changed = {'id': row_id, 'day_of_week': 'Monday', 'start_time': '08:00', 'end_time': '08:30', 'label': 'Break'}
        response = self.client.patch(f"/api/school/timetable-plans/{created.data['id']}/", {'entries': [changed]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(TimetableEntry.objects.get(pk=row_id).subject_id)
        self.assertTrue(ClassSubject.objects.filter(subject=subject).exists())

    def test_legacy_data_copy_keeps_entries_and_class_relationship(self):
        entries = [TimetableEntry.objects.create(school_class=self.class_a, academic_year=self.year_a, term=self.term_a, day_of_week=day, start_time=time(8), end_time=time(9), label='Old custom activity') for day in ['Monday', 'Tuesday']]
        migrate = import_module('core.migrations.0020_copy_legacy_timetables').copy_legacy_timetables
        for _ in range(2):
            migrate(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        self.assertEqual(Timetable.objects.count(), 1)
        plan = Timetable.objects.get()
        self.assertEqual(list(plan.classes.all()), [self.class_a])
        self.assertEqual(set(plan.entries.values_list('pk', flat=True)), {e.pk for e in entries})
        self.assertEqual(set(plan.entries.values_list('label', flat=True)), {'Old custom activity'})

    def test_attendance_classes_roster_all_statuses_and_exclusions(self):
        self.authenticate(self.admin_a)
        self.assertNotIn(self.class_b.pk, [c['id'] for c in self.client.get('/api/school/classes/').data])
        context = {'school_class': self.class_a.pk, 'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'attendance_date': '2026-01-11'}
        roster = self.client.get('/api/school/attendance/roster/', context).data
        timestamp = None
        for state in ['present', 'absent', 'late', 'excused']:
            response = self.client.post('/api/school/attendance/bulk/', {**context, 'entries': [{'enrollment': roster['students'][0]['enrollment'], 'status': state, 'last_known_updated_at': timestamp}]}, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            self.assertEqual(response.status_code, 200, response.data)
            timestamp = response.data['roster']['students'][0]['attendance']['updated_at']
            self.assertEqual(AttendanceRecord.objects.get(enrollment=self.enrollment_a).status, state)
        self.enrollment_a.left_on = date(2026, 1, 10)
        self.enrollment_a.save()
        self.assertEqual(self.client.get('/api/school/attendance/roster/', context).data['students'], [])
        self.enrollment_a.left_on = None
        self.enrollment_a.save()
        self.student_a.is_active = False
        self.student_a.save(update_fields=['is_active'])
        self.assertEqual(self.client.get('/api/school/attendance/roster/', context).data['students'], [])
