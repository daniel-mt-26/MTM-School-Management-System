from django.db import migrations, models
import django.db.models.deletion


def backfill_student_school(apps, schema_editor):
    Student = apps.get_model("core", "Student")
    unresolved = Student.objects.filter(school_class__school__isnull=True)
    if unresolved.exists():
        raise RuntimeError("Cannot backfill Student.school: one or more students have no resolvable class school.")

    for student in Student.objects.select_related("school_class").iterator():
        student.school_id = student.school_class.school_id
        student.save(update_fields=["school"])

    duplicates = (
        Student.objects.values("school_id", "admission_number")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError("Cannot enforce per-school admission uniqueness: duplicate admission numbers exist within a school.")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_remove_studentenrollment_one_enrollment_per_student_per_year_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="school",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="students",
                to="core.school",
            ),
        ),
        migrations.RunPython(backfill_student_school, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="student",
            name="school",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="students",
                to="core.school",
            ),
        ),
        migrations.AlterField(
            model_name="student",
            name="admission_number",
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name="student",
            constraint=models.UniqueConstraint(
                fields=("school", "admission_number"),
                name="unique_student_admission_per_school",
            ),
        ),
    ]
