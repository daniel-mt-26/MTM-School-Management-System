from django.db import migrations


def preserve_published(apps, schema_editor):
    Card = apps.get_model('core', 'ReportCard')
    Result = apps.get_model('core', 'AcademicResult')
    Publication = apps.get_model('core', 'ReportCardPublication')
    Comment = apps.get_model('core', 'ReportComment')
    alias = schema_editor.connection.alias
    cards = Card.objects.using(alias).filter(is_published=True).select_related(
        'student_enrollment__student__school', 'student_enrollment__school_class', 'student_enrollment__academic_year', 'term')
    for card in cards.iterator():
        enrollment = card.student_enrollment
        student, school = enrollment.student, enrollment.student.school
        results = Result.objects.using(alias).filter(student_enrollment=enrollment, term=card.term)
        if results.exclude(status='published').exists():
            continue
        rows = list(results.filter(class_subject__school_class__school=school, class_subject__subject__school=school).select_related('class_subject__subject').order_by('class_subject__subject__name', 'pk'))
        if not rows:
            continue
        # Existing records have marks and comments, but no grading scale or
        # grade field. Preserve exactly that truth, leaving grades blank.
        snapshot = dict(student=dict(id=student.pk, name=f'{student.first_name} {student.last_name}', admission_number=student.admission_number,
            class_name=enrollment.school_class.name, guardian=''),
            school=dict(name=school.name, address=school.address, phone=school.phone_number, email=school.email,
                        logo=None, motto='', website='', additional_contacts='', contact_person='', brand_color='#244768'),
            academic_year=enrollment.academic_year.name, academic_year_id=enrollment.academic_year_id,
            term=card.term.name, term_id=card.term_id, term_sequence=card.term.sequence,
            class_name=enrollment.school_class.name, class_id=enrollment.school_class_id,
            results=[dict(id=r.pk, class_subject=r.class_subject_id, subject=r.class_subject.subject.name,
                score=str(r.score), maximum_score=str(r.maximum_score), percentage=str(round(r.score / r.maximum_score * 100, 2)),
                grade=r.official_grade, grading=r.grading_snapshot, comment=r.comment) for r in rows],
            comments=list(Comment.objects.using(alias).filter(enrollment=enrollment, term=card.term, teacher__school=school).values_list('comment', flat=True)),
            legacy_preserved=True)
        Publication.objects.using(alias).get_or_create(report_card=card, version=1, defaults={'snapshot': snapshot, 'published_at': card.generated_at})


class Migration(migrations.Migration):
    dependencies = [('core', '0028_student_documents')]
    operations = [migrations.RunPython(preserve_published, migrations.RunPython.noop)]
