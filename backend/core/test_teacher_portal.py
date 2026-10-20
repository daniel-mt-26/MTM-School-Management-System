import hashlib
import re
from datetime import date, timedelta
from io import BytesIO
from zipfile import ZipFile
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import (Teacher, TeacherAssignment, SchoolClass, User, AcademicResult,
    AttendanceRecord, PasswordRecovery, AuditLog, Homework, ReportCard, Subject, ClassSubject, Parent)


class TeacherPortalTests(APITestCase):
    make_user = fixtures.TenantIsolationTests.make_user
    make_school_calendar = fixtures.TenantIsolationTests.make_school_calendar
    make_student = fixtures.TenantIsolationTests.make_student
    make_private_records = fixtures.TenantIsolationTests.make_private_records
    authenticate = fixtures.TenantIsolationTests.authenticate

    def setUp(self):
        fixtures.TenantIsolationTests.setUp(self)
        self.teacher_user = self.make_user('teacher-a', User.Role.TEACHER)
        self.teacher = Teacher.objects.create(user=self.teacher_user, school=self.school_a)
        self.assignment = TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.class_a)
        self.assignment.subjects.add(self.result_a.class_subject)
        self.unassigned = SchoolClass.objects.create(school=self.school_a, name='Unassigned')
        self.authenticate(self.teacher_user)

    def test_teacher_only_sees_assigned_roster_and_denies_admin_apis(self):
        self.assertEqual([x['id'] for x in self.client.get('/api/teacher/students/').data], [self.student_a.pk])
        self.assertEqual(self.client.get(f'/api/teacher/students/{self.student_b.pk}/').status_code, 404)
        for path in ('fees', 'payments', 'parents', 'inventory/items', 'academic-years', 'teachers'):
            self.assertEqual(self.client.get(f'/api/school/{path}/').status_code, 403, path)
        self.assertEqual(self.client.get('/api/platform/dashboard/').status_code, 403)
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get('/api/teacher/lookups/').status_code, 403)

    def test_teacher_creation_generated_credentials_assignments_and_uniqueness(self):
        self.authenticate(self.admin_a)
        payload = {'first_name': 'Jane', 'last_name': 'Smith', 'assignments': [{'school_class': self.class_a.pk, 'subjects': [self.result_a.class_subject_id]}, {'school_class': self.unassigned.pk, 'subjects': []}]}
        for name in ('jane.smith', 'jane.smith2'):
            result = self.client.post('/api/school/teachers/', payload, format='json')
            self.assertEqual(result.status_code, 201, result.data)
            self.assertEqual(result.data['username'], name)
            user = User.objects.get(username=name)
            self.assertTrue(user.must_change_password)
            self.assertTrue(user.check_password(result.data['temporary_password']))
            detail = self.client.get(f"/api/school/teachers/{result.data['id']}/")
            self.assertNotIn('temporary_password', detail.data)
            self.assertEqual(len(detail.data['assignments']), 2)
            self.assertFalse(AuditLog.objects.filter(description__contains=result.data['temporary_password']).exists())

    def test_admin_cannot_assign_cross_school_class_or_subject(self):
        self.authenticate(self.admin_a)
        for assignment in ({'school_class': self.class_b.pk, 'subjects': []}, {'school_class': self.class_a.pk, 'subjects': [self.result_b.class_subject_id]}):
            response = self.client.patch(f'/api/school/teachers/{self.teacher.pk}/', {'assignments': [assignment]}, format='json')
            self.assertIn(response.status_code, (400, 404))
        self.authenticate(self.admin_b)
        self.assertEqual(self.client.post(f'/api/school/teachers/{self.teacher.pk}/reset-password/').status_code, 404)

    def test_attendance_denies_unassigned_and_cross_tenant_classes(self):
        data = {'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'attendance_date': '2026-02-01'}
        for cls in (self.unassigned, self.class_b):
            self.assertEqual(self.client.get('/api/school/attendance/roster/', {**data, 'school_class': cls.pk}).status_code, 404)
            self.assertEqual(self.client.post('/api/school/attendance/bulk/', {**data, 'school_class': cls.pk, 'entries': []}, format='json').status_code, 404)
        self.assertEqual(self.client.get('/api/school/attendance/roster/', {**data, 'school_class': self.class_a.pk}).status_code, 200)

    def test_homework_authorization_and_closed_workflow(self):
        data = {'title': 'Worksheet', 'school_class': self.class_a.pk, 'subject': self.result_a.class_subject.subject_id, 'date_assigned': '2026-02-01', 'due_date': '2026-02-02'}
        self.assertEqual(self.client.post('/api/teacher/homework/', {**data, 'school_class': self.unassigned.pk}, format='json').status_code, 404)
        response = self.client.post('/api/teacher/homework/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        path = f"/api/teacher/homework/{response.data['id']}/"
        self.assertEqual(self.client.patch(path, {'status': 'published'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(path, {'title': 'Overwrite'}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(path, {'status': 'closed'}, format='json').status_code, 200)

    def test_unassigned_subject_is_denied(self):
        subject = Subject.objects.create(school=self.school_a, name='Science', code='SCI')
        cs = ClassSubject.objects.create(subject=subject, school_class=self.class_a, academic_year=self.year_a)
        payload = {'student_enrollment': self.enrollment_a.pk, 'term': self.term_a.pk, 'class_subject': cs.pk, 'score': 5, 'maximum_score': 10}
        self.assertEqual(self.client.post('/api/teacher/results/', payload, format='json').status_code, 403)

    def test_result_workflow_and_parent_publication(self):
        self.result_a.delete()
        payload = {'student_enrollment': self.enrollment_a.pk, 'term': self.term_a.pk, 'class_subject': self.assignment.subjects.first().pk, 'score': 5, 'maximum_score': 10}
        result = self.client.post('/api/teacher/results/', payload, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['status'], 'draft')
        pk = result.data['id']; path = f'/api/teacher/results/{pk}/'
        self.assertEqual(self.client.patch(path, {'score': 6}, format='json').status_code, 200)
        self.assertEqual(self.client.post(path+'transition/', {'status': 'published'}, format='json').status_code, 403)
        self.assertEqual(self.client.post(path+'transition/', {'status': 'submitted'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(path, {'score': 7}, format='json').status_code, 403)
        self.authenticate(self.parent_a_user)
        self.assertEqual(self.client.get('/api/parent/results/').data, [])
        self.authenticate(self.admin_a)
        for state in ('approved', 'published'):
            self.assertEqual(self.client.post(f'/api/school/result-review/{pk}/transition/', {'status': state}, format='json').status_code, 200)
        self.authenticate(self.teacher_user)
        self.assertEqual(self.client.patch(path, {'score': 8}, format='json').status_code, 403)
        self.authenticate(self.parent_a_user)
        self.assertEqual(len(self.client.get('/api/parent/results/').data), 1)

    def test_register_codes_counts_month_and_exports(self):
        for day, status in enumerate(('present', 'absent', 'late', 'excused'), 1):
            AttendanceRecord.objects.create(school=self.school_a, enrollment=self.enrollment_a, academic_year=self.year_a, term=self.term_a, attendance_date=date(2026, 2, day), status=status, recorded_by=self.teacher_user)
        filters = {'academic_year': self.year_a.pk, 'term': self.term_a.pk, 'school_class': self.class_a.pk, 'calendar_year': 2026, 'month': 2}
        response = self.client.get('/api/school/attendance/register/', filters)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['days']), 28)
        row = response.data['rows'][0]
        self.assertEqual(row['days'][:4], ['P', 'A', 'L', 'E'])
        self.assertEqual([row[s] for s in ('present', 'absent', 'late', 'excused')], [1]*4)
        self.assertEqual(row['percentage'], 50)
        self.assertEqual(len(self.client.get('/api/school/attendance/register/', {**filters, 'calendar_year': 2028}).data['days']), 29)
        pdf = self.client.get('/api/school/attendance/register/', {**filters, 'export': 'pdf'})
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        xlsx = self.client.get('/api/school/attendance/register/', {**filters, 'export': 'xlsx'})
        with ZipFile(BytesIO(xlsx.content)) as archive:
            self.assertIn(b'Alice', archive.read('xl/worksheets/sheet1.xml'))
        self.assertEqual(self.client.get('/api/school/attendance/register/', {**filters, 'school_class': self.unassigned.pk}).status_code, 404)

    def test_teacher_announcements_targeting_and_admin_recipients(self):
        payload = {'title': 'Reminder', 'message': 'Bring books', 'recipients': [self.class_a.pk]}
        self.assertEqual(self.client.post('/api/teacher/announcements/', payload, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/teacher/announcements/', {**payload, 'recipients': [self.unassigned.pk]}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/teacher/announcements/', {**payload, 'all_recipients': True}, format='json').status_code, 201)
        self.authenticate(self.admin_a)
        self.assertEqual(self.client.post('/api/school/teacher-announcements/', {**payload, 'recipients': [self.teacher.pk]}, format='json').status_code, 201)
        self.authenticate(self.teacher_user)
        self.assertEqual(len(self.client.get('/api/teacher/announcements/').data), 3)

    def test_report_comment_locked_after_publication(self):
        data = {'enrollment': self.enrollment_a.pk, 'term': self.term_a.pk, 'comment': 'Good work'}
        self.assertEqual(self.client.post('/api/teacher/comments/', data, format='json').status_code, 403)
        ReportCard.objects.filter(pk=self.report_a.pk).update(is_published=False)
        self.assertEqual(self.client.post('/api/teacher/comments/', data, format='json').status_code, 201)

    def test_deactivation_and_reset_revoke_jwts(self):
        self.client.force_authenticate(user=None)
        tokens = self.client.post('/api/auth/token/', {'username': self.teacher_user.username, 'password': 'secure-pass-123'}, format='json').data
        self.authenticate(self.admin_a)
        reset = self.client.post(f'/api/school/teachers/{self.teacher.pk}/reset-password/')
        self.assertEqual(reset.status_code, 200)
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+tokens['access'])
        self.assertEqual(self.client.get('/api/teacher/students/').status_code, 401)
        self.client.credentials()
        self.authenticate(self.admin_a)
        self.assertEqual(self.client.patch(f'/api/school/teachers/{self.teacher.pk}/', {'is_active': False}, format='json').status_code, 200)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post('/api/auth/token/', {'username': self.teacher_user.username, 'password': reset.data['temporary_password']}, format='json').status_code, 401)

    def test_parent_generated_credentials_and_reset(self):
        self.authenticate(self.admin_a)
        response = self.client.post('/api/school/parents/', {'first_name': 'New', 'last_name': 'Guardian', 'phone_number': '123', 'children': [self.student_a.pk]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        parent = Parent.objects.get(pk=response.data['id'])
        self.assertTrue(parent.user.check_password(response.data['temporary_password']))
        self.assertTrue(parent.user.must_change_password)
        self.assertNotIn('temporary_password', self.client.get(f'/api/school/parents/{parent.pk}/').data)
        self.assertEqual(self.client.post(f'/api/school/parents/{parent.pk}/reset-password/').status_code, 200)

    @override_settings(MAILER_BACKEND='django.core.mail.backends.locmem.EmailBackend', MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}})
    def test_recovery_neutral_single_use_and_revoke(self):
        self.client.force_authenticate(user=None)
        self.teacher_user.email = 'teacher@example.test'; self.teacher_user.save()
        known = self.client.post('/api/auth/forgot-password/', {'identifier': self.teacher_user.username}, format='json')
        unknown = self.client.post('/api/auth/forgot-password/', {'identifier': 'unknown'}, format='json')
        self.assertEqual(known.data, unknown.data)
        token = re.search(r'#token=([^\s]+)', mail.outbox[-1].body)[1]
        self.assertTrue(PasswordRecovery.objects.filter(digest=hashlib.sha256(token.encode()).hexdigest()).exists())
        payload = {'token': token, 'new_password': 'New-secure-password-975!'}
        self.assertEqual(self.client.post('/api/auth/reset-password/', payload, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/reset-password/', payload, format='json').status_code, 400)
        self.teacher_user.refresh_from_db()
        self.assertEqual(self.teacher_user.token_version, 2)
        self.assertTrue(self.teacher_user.check_password(payload['new_password']))
        self.assertFalse(AuditLog.objects.filter(description__contains=token).exists())

    def test_recovery_expired_token(self):
        self.client.force_authenticate(user=None)
        PasswordRecovery.objects.create(user=self.teacher_user, digest=hashlib.sha256(b'expired').hexdigest(), expires_at=timezone.now()-timedelta(minutes=1))
        self.assertEqual(self.client.post('/api/auth/reset-password/', {'token': 'expired', 'new_password': 'Strong-new-password-45!'}, format='json').status_code, 400)

    def test_recovery_rate_limit(self):
        self.client.force_authenticate(user=None)
        for _ in range(5):
            self.assertEqual(self.client.post('/api/auth/forgot-password/', {'identifier': 'unknown'}, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/forgot-password/', {'identifier': 'unknown'}, format='json').status_code, 429)

    def test_resources_are_protected_and_reject_unassigned_class(self):
        from tempfile import TemporaryDirectory
        from django.core.files.uploadedfile import SimpleUploadedFile
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            data = {'title': 'Notes', 'school_class': self.class_a.pk, 'file': SimpleUploadedFile('notes.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')}
            result = self.client.post('/api/teacher/resources/', data, format='multipart')
            self.assertEqual(result.status_code, 201, result.data)
            path = f"/api/teacher/resources/{result.data['id']}/download/"
            download = self.client.get(path)
            self.assertEqual(download.status_code, 200)
            # The test client replaces FileResponse.streaming_content, clearing
            # file_to_stream. Close only the file, not request_finished inside
            # this TestCase transaction.
            stream = next(closer.__self__ for closer in download._resource_closers if hasattr(getattr(closer, '__self__', None), 'read'))
            self.assertTrue(stream.read().startswith(b'%PDF'))
            stream.close()
            self.assertEqual(self.client.get('/media/protected_resources/notes.pdf').status_code, 404)
            self.authenticate(self.parent_a_user)
            self.assertEqual(self.client.get(path).status_code, 403)
            self.authenticate(self.teacher_user)
            data['school_class'] = self.unassigned.pk
            data['file'] = SimpleUploadedFile('notes.pdf', b'%PDF-1.4\n%%EOF')
            self.assertEqual(self.client.post('/api/teacher/resources/', data, format='multipart').status_code, 404)

    def test_shared_timetable_hides_unassigned_class_names(self):
        from datetime import time
        from .models import Timetable, TimetableEntry
        plan = Timetable.objects.create(school=self.school_a, name='Shared', academic_year=self.year_a, term=self.term_a)
        plan.classes.add(self.class_a, self.unassigned)
        TimetableEntry.objects.create(timetable=plan, school_class=self.unassigned, academic_year=self.year_a, term=self.term_a, day_of_week='Monday', start_time=time(8), end_time=time(9), label='Assembly')
        response = self.client.get('/api/teacher/timetable/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['class_name'], self.class_a.name)
        self.assertEqual(response.data[0]['school_class'], self.class_a.pk)
        self.assertEqual(self.client.post('/api/teacher/timetable/', {}, format='json').status_code, 405)

    def test_published_correction_preserves_snapshot_and_retracts_report(self):
        from .models import ResultRevision
        path = f'/api/school/result-review/{self.result_a.pk}/correction/'
        self.assertEqual(self.client.post(path, {'reason': 'Correct data entry mistake'}, format='json').status_code, 403)
        self.authenticate(self.admin_a)
        response = self.client.post(path, {'reason': 'Correct data entry mistake'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ResultRevision.objects.get(result=self.result_a).snapshot['score'], str(self.result_a.score))
        self.report_a.refresh_from_db()
        self.assertFalse(self.report_a.is_published)

    @override_settings(MAILER_BACKEND='django.core.mail.backends.locmem.EmailBackend', MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}})
    def test_recovery_supports_every_role_and_obsoletes_links_after_admin_reset(self):
        from django.core.cache import cache
        from .credentials import reset_login
        self.client.force_authenticate(user=None)
        for user in (self.teacher_user, self.admin_a, self.parent_a_user, self.platform_admin):
            cache.clear()
            user.email = f'{user.role}@example.test'; user.save()
            response = self.client.post('/api/auth/forgot-password/', {'identifier': user.email}, format='json')
            self.assertEqual(response.status_code, 200)
            token = re.search(r'#token=([^\s]+)', mail.outbox[-1].body)[1]
            self.assertEqual(self.client.post('/api/auth/reset-password/', {'token': token, 'new_password': 'Secure-new-pass-478!'}, format='json').status_code, 200)
        cache.clear()
        self.teacher_user.refresh_from_db()
        self.client.post('/api/auth/forgot-password/', {'identifier': self.teacher_user.email}, format='json')
        token = re.search(r'#token=([^\s]+)', mail.outbox[-1].body)[1]
        reset_login(self.teacher_user)
        self.assertEqual(self.client.post('/api/auth/reset-password/', {'token': token, 'new_password': 'Secure-new-pass-487!'}, format='json').status_code, 400)
