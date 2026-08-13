from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("core", "0005_parent_school")]

    operations = [
        migrations.CreateModel(
            name="TimetableEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day_of_week", models.CharField(max_length=20)),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("label", models.CharField(blank=True, max_length=100)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="timetable_entries", to="core.academicyear")),
                ("school_class", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="timetable_entries", to="core.schoolclass")),
                ("subject", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="timetable_entries", to="core.subject")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="timetable_entries", to="core.term")),
            ],
            options={"ordering": ["day_of_week", "start_time", "end_time"]},
        ),
        migrations.AddConstraint(
            model_name="timetableentry",
            constraint=models.UniqueConstraint(fields=("school_class", "academic_year", "term", "day_of_week", "start_time", "end_time"), name="unique_timetable_class_period"),
        ),
        migrations.AddIndex(
            model_name="timetableentry",
            index=models.Index(fields=["school_class", "academic_year", "term", "day_of_week"], name="timetable_class_period_idx"),
        ),
    ]
