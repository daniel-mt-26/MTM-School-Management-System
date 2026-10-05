from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response

from .curriculum import ACTIVITIES, DAYS
from .models import AcademicYear, SchoolClass, Subject, Term, Timetable
from .views import SchoolAdminViewSet
from .timetables import save_timetable


class ScheduleRowSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    day_of_week = serializers.ChoiceField(choices=DAYS)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.none(), allow_null=True, required=False)
    label = serializers.CharField(max_length=100, allow_blank=True, required=False, default='')

    def get_fields(self):
        fields = super().get_fields()
        fields['subject'].queryset = Subject.objects.filter(school=self.context['school'])
        return fields

    def validate(self, attrs):
        if any(key not in attrs for key in ('day_of_week', 'start_time', 'end_time')):
            raise serializers.ValidationError('Each submitted entry requires a day, start time and end time.')
        attrs.setdefault('subject', None)
        attrs.setdefault('label', '')
        if attrs.get('subject'):
            if attrs.get('label') and self.context.get('existing_labels', {}).get(attrs.get('id')) != attrs.get('label'):
                raise serializers.ValidationError('Choose either a subject or an activity.')
        elif attrs.get('label') not in ACTIVITIES:
            # Keep arbitrary historical labels readable/editable without losing data.
            old = self.context.get('existing_labels', {})
            if old.get(attrs.get('id')) != attrs.get('label'):
                raise serializers.ValidationError('Choose a timetable activity.')
        return attrs


class TimetableSerializer(serializers.ModelSerializer):
    entries = ScheduleRowSerializer(many=True)
    class_names = serializers.SerializerMethodField()
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)

    class Meta:
        model = Timetable
        fields = ['id', 'name', 'academic_year', 'academic_year_name', 'term', 'term_name', 'classes', 'class_names', 'entries']

    def get_class_names(self, obj):
        return [c.name for c in obj.classes.all()]

    def get_fields(self):
        fields = super().get_fields()
        school = self.context['school']
        fields['academic_year'].queryset = AcademicYear.objects.filter(school=school)
        fields['term'].queryset = Term.objects.filter(academic_year__school=school)
        fields['classes'].child_relation.queryset = SchoolClass.objects.filter(school=school)
        if isinstance(self.instance, Timetable):
            self.context['existing_labels'] = dict(self.instance.entries.values_list('id', 'label'))
        return fields

    def validate(self, attrs):
        if 'school' in self.initial_data or 'school_id' in self.initial_data:
            raise serializers.ValidationError('School ownership is controlled by the authenticated account.')
        return attrs

    def create(self, validated_data):
        return save_timetable(school=self.context['school'], data=validated_data)

    def update(self, instance, validated_data):
        return save_timetable(school=self.context['school'], data=validated_data, instance=instance)


class TimetableViewSet(SchoolAdminViewSet):
    queryset = Timetable.objects.all()
    serializer_class = TimetableSerializer
    school_lookup = 'school'

    def get_queryset(self):
        rows = super().get_queryset().prefetch_related('classes', 'entries').select_related('academic_year', 'term')
        for field in ('academic_year', 'term'):
            if value := self.request.query_params.get(field):
                rows = rows.filter(**{field + '_id': value})
        if value := self.request.query_params.get('school_class'):
            rows = rows.filter(classes__id=value)
        return rows.distinct().order_by('name', 'id')

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        from .models import School
        School.objects.select_for_update().get(pk=self.get_school().pk)
        plan = self.get_object()
        plan.entries.all().delete()
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
