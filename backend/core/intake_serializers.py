"""Strict input allowlists; public callers cannot set ownership or review fields."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from django.conf import settings
from rest_framework import serializers
from .intake_models import AdmissionApplication, ContactEnquiry, GRADE_CHOICES


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({"detail": "Unknown fields or invalid input object."})
        for name, value in data.items():
            if isinstance(self.fields[name], serializers.CharField) and value is not None and not isinstance(value, str):
                raise serializers.ValidationError({name: "Provide a text value."})
        return super().to_internal_value(data)


class PublicInput(StrictSerializer):
    phone = serializers.CharField(max_length=25)
    email = serializers.EmailField(max_length=254)
    consent = serializers.BooleanField(write_only=True)
    privacyPolicyVersion = serializers.CharField(max_length=100, source="privacy_policy_version")
    website = serializers.CharField(required=False, allow_blank=True, max_length=200, write_only=True)
    challengeToken = serializers.CharField(required=False, allow_blank=True, max_length=2048, write_only=True)

    def validate_phone(self, value):
        if not re.fullmatch(r"\+?[0-9 ()-]+", value) or not 7 <= len(re.sub(r"\D", "", value)) <= 15:
            raise serializers.ValidationError("Enter a valid telephone number with 7 to 15 digits.")
        return re.sub(r"[ ()-]", "", value)

    def validate_consent(self, value):
        if self.initial_data.get("consent") is not True:
            raise serializers.ValidationError("Consent must be explicitly acknowledged.")
        return True

    def validate_privacyPolicyVersion(self, value):
        if value != settings.MTM_INTAKE_PRIVACY_VERSION:
            raise serializers.ValidationError("Please use the current privacy notice.")
        return value

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError("Unable to accept this submission.")
        return value


class ApplicationInput(PublicInput):
    studentName = serializers.CharField(max_length=150, source="student_name")
    dateOfBirth = serializers.DateField(source="date_of_birth")
    grade = serializers.ChoiceField(choices=GRADE_CHOICES)
    guardianName = serializers.CharField(max_length=150, source="guardian_name")
    address = serializers.CharField(max_length=500)
    previousSchool = serializers.CharField(required=False, allow_blank=True, max_length=150, source="previous_school")
    additionalInformation = serializers.CharField(required=False, allow_blank=True, max_length=2000, source="additional_information")

    def validate_dateOfBirth(self, value):
        if value > datetime.now(ZoneInfo("Africa/Harare")).date():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value


class EnquiryInput(PublicInput):
    fullName = serializers.CharField(max_length=150, source="full_name")
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField(max_length=3000)


class ApplicationDetail(serializers.ModelSerializer):
    class Meta:
        model = AdmissionApplication
        fields = ["id", "reference", "student_name", "date_of_birth", "grade", "guardian_name", "phone", "email", "address", "previous_school", "additional_information", "status", "consent_at", "privacy_policy_version", "created_at", "updated_at", "reviewer", "reviewed_at", "retention_expires_at", "version"]
        read_only_fields = fields


class EnquiryDetail(serializers.ModelSerializer):
    class Meta:
        model = ContactEnquiry
        fields = ["id", "reference", "full_name", "email", "phone", "subject", "message", "status", "consent_at", "privacy_policy_version", "created_at", "updated_at", "assigned_administrator", "retention_expires_at", "version"]
        read_only_fields = fields


class ApplicationReview(StrictSerializer):
    version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=AdmissionApplication.Status.choices, required=False)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=False)

    def validate(self, attrs):
        if not any(k in attrs for k in ["status", "note", "assignedAdministratorId"]):
            raise serializers.ValidationError("Supply a status, note or assignment.")
        return attrs


class EnquiryReview(ApplicationReview):
    status = serializers.ChoiceField(choices=ContactEnquiry.Status.choices, required=False)
    assignedAdministratorId = serializers.IntegerField(min_value=1, required=False, allow_null=True)
