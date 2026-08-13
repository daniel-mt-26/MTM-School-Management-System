from django.db import migrations, models
import django.db.models.deletion


def backfill_parent_school(apps, schema_editor):
    Parent = apps.get_model("core", "Parent")
    for parent in Parent.objects.all().iterator():
        school_ids = set(parent.student_links.values_list("student__school_id", flat=True))
        if len(school_ids) != 1:
            raise RuntimeError(
                "Cannot backfill Parent.school: every existing parent must have links to students in exactly one school."
            )
        parent.school_id = school_ids.pop()
        parent.save(update_fields=["school"])


class Migration(migrations.Migration):

    dependencies = [("core", "0004_student_school_and_admission_constraint")]

    operations = [
        migrations.AddField(
            model_name="parent",
            name="school",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="parents",
                to="core.school",
            ),
        ),
        migrations.RunPython(backfill_parent_school, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="parent",
            name="school",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="parents",
                to="core.school",
            ),
        ),
    ]
