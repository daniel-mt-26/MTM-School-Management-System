from django.db import migrations


def copy_legacy_timetables(apps, schema_editor):
    Entry = apps.get_model('core', 'TimetableEntry')
    Timetable = apps.get_model('core', 'Timetable')
    SchoolClass = apps.get_model('core', 'SchoolClass')
    alias = schema_editor.connection.alias
    contexts = Entry.objects.using(alias).filter(timetable__isnull=True).order_by().values_list('school_class_id', 'academic_year_id', 'term_id').distinct()
    for class_id, year_id, term_id in list(contexts):
        school_class = SchoolClass.objects.using(alias).get(pk=class_id)
        plan = Timetable.objects.using(alias).create(school_id=school_class.school_id, name=f'{school_class.name} timetable', academic_year_id=year_id, term_id=term_id)
        plan.classes.add(class_id)
        Entry.objects.using(alias).filter(school_class_id=class_id, academic_year_id=year_id, term_id=term_id, timetable__isnull=True).update(timetable_id=plan.pk)


class Migration(migrations.Migration):
    dependencies = [('core', '0019_timetable_and_more')]
    operations = [migrations.RunPython(copy_legacy_timetables, migrations.RunPython.noop)]
