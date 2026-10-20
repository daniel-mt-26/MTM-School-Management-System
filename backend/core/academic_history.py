"""Compilation of official values. Historical grades are never recalculated."""
from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .audit import log_action
from .documents import branding, SchoolDocument, attachment
from .finance_documents import student_info, export_kind
from .models import Student, AcademicResult, ReportCard, ReportCardPublication, SchoolDocumentSettings, ClassSubject, Term
from .permissions import IsParent
from .reporting_api import filters
from .staff_access import IsAcademicStaff, staff_school


def freeze_grade(result, school):
    settings = SchoolDocumentSettings.objects.filter(school=school).first()
    scale = settings.grading_scale if settings else []
    percentage = result.score / result.maximum_score * 100
    result.official_grade = next((b['grade'] for b in sorted(scale, key=lambda b: Decimal(b['minimum']), reverse=True) if percentage >= Decimal(b['minimum'])), '')
    result.grading_snapshot = {'scale': scale, 'percentage': str(round(percentage, 2))}


def published_snapshot(card, request=None):
    enrollment = card.student_enrollment
    school = enrollment.student.school
    results = AcademicResult.objects.filter(student_enrollment=enrollment, term=card.term, status='published',
        class_subject__school_class__school=school, class_subject__subject__school=school).select_related('class_subject__subject')
    return dict(student=student_info(enrollment.student), school=branding(school, request, snapshot=True),
        academic_year=enrollment.academic_year.name, academic_year_id=enrollment.academic_year_id,
        term=card.term.name, term_id=card.term_id, term_sequence=card.term.sequence,
        class_name=enrollment.school_class.name, class_id=enrollment.school_class_id,
        results=[dict(id=r.pk, class_subject=r.class_subject_id, subject=r.class_subject.subject.name,
            score=str(r.score), maximum_score=str(r.maximum_score), percentage=str(round(r.score / r.maximum_score * 100, 2)),
            grade=r.official_grade, grading=r.grading_snapshot, comment=r.comment) for r in results.order_by('class_subject__subject__name', 'pk')],
        comments=list(enrollment.teacher_comments.filter(term=card.term, teacher__school=school).values_list('comment', flat=True)))


@transaction.atomic
def capture_publication(card, request):
    card = ReportCard.objects.select_for_update().select_related('student_enrollment__student__school', 'student_enrollment__student__school_class', 'student_enrollment__school_class', 'student_enrollment__academic_year', 'term').get(pk=card.pk)
    if not card.is_published:
        raise ValidationError('Publish the report card first.')
    snapshot = published_snapshot(card, request)
    if not snapshot['results']:
        raise ValidationError('A published report requires published results.')
    previous = card.publications.order_by('-version').first()
    if previous and previous.snapshot == snapshot:
        return previous
    publication = ReportCardPublication.objects.create(report_card=card, version=previous.version + 1 if previous else 1, snapshot=snapshot)
    log_action(school=card.student_enrollment.student.school, actor=request.user, action='academic_record_published', resource=publication)
    return publication


class AcademicHistoryView(APIView):
    permission_classes = [IsAcademicStaff | IsParent]

    def get(self, request, student_id):
        user = request.user
        school = user.parent_profile.school if user.role == 'parent' else staff_school(user)
        students = Student.objects.filter(school=school)
        if user.role == 'parent':
            students = students.filter(parent_links__parent=user.parent_profile)
        elif user.role == 'teacher':
            students = students.filter(enrollments__school_class__teacher_assignments__teacher=user.teacher_profile)
        student = get_object_or_404(students.distinct().select_related('school', 'school_class'), pk=student_id)
        selected = filters(request, school)
        cards = ReportCard.objects.filter(student_enrollment__student=student, is_published=True,
            student_enrollment__school_class__school=school, student_enrollment__academic_year__school=school,
            term__academic_year__school=school).select_related('term', 'student_enrollment__academic_year', 'student_enrollment__school_class', 'student_enrollment__student__school', 'student_enrollment__student__school_class').prefetch_related('publications')
        for key, lookup in [('academic_year', 'student_enrollment__academic_year_id'), ('term', 'term_id')]:
            if selected.get(key):
                cards = cards.filter(**{lookup: selected[key]})
        allowed_subjects = None
        if user.role == 'teacher':
            cards = cards.filter(student_enrollment__school_class__teacher_assignments__teacher=user.teacher_profile)
            allowed_subjects = set(ClassSubject.objects.filter(teacher_assignments__teacher=user.teacher_profile,
                school_class__school=school).values_list('pk', flat=True))
        periods = []
        for card in cards.distinct().order_by('student_enrollment__academic_year__start_date', 'term__sequence', 'pk'):
            publications = sorted(card.publications.all(), key=lambda p: p.version)
            publication = publications[-1] if publications else None
            snapshot = dict(publication.snapshot if publication else published_snapshot(card, request))
            if allowed_subjects is not None:
                snapshot['results'] = [r for r in snapshot['results'] if r['class_subject'] in allowed_subjects]
                snapshot['comments'] = []
            if not snapshot['results']:
                continue
            periods.append(dict(report_card=card.pk, version=publication.version if publication else None,
                published_at=publication.published_at if publication else card.generated_at,
                source='official_snapshot' if publication else 'legacy_published_values', **snapshot))
        data = dict(school=branding(school, request), student=student_info(student), periods=periods,
            years=list(school.academic_years.values('id', 'name')),
            terms=list(Term.objects.filter(academic_year__school=school).values('id', 'name', 'academic_year')),
            note='Compiled from published report cards. Blank grades indicate no preserved official grade. Existing report-card downloads remain the official visual record.')
        if user.role == 'teacher':
            data['student'].pop('guardian', None)
            for period in periods:
                period['student'] = {k: v for k, v in period['student'].items() if k != 'guardian'}
        kind = export_kind(request, ('json', 'pdf'))
        if kind == 'json':
            return Response(data)
        doc = SchoolDocument(branding(school, request, snapshot=True), 'Historical Academic Record')
        doc.text(f'{data["student"]["name"]} | Admission: {student.admission_number}')
        doc.text(data['note'])
        for period in periods:
            doc.text(f'{period["academic_year"]} / {period["term"]} — {period["class_name"]}', 'Heading2')
            doc.text(f'Report #{period["report_card"]}; publication version: {period["version"] or "legacy"}')
            doc.table(['Subject', 'Mark', 'Maximum', 'Percentage', 'Official Grade', 'Published Comment'],
                [[r['subject'], r['score'], r['maximum_score'], r['percentage'], r['grade'], r['comment']] for r in period['results']], [2, 1, 1, 1, 1, 3])
            for comment in period.get('comments', []):
                doc.text(comment)
        log_action(school=school, actor=user, action='academic_record_downloaded', resource=student)
        return attachment(doc.render(), f'academic-history-{student.pk}', 'pdf')
