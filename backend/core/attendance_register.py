import calendar
from collections import Counter
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AcademicYear, Term, StudentEnrollment, AttendanceRecord
from .staff_access import IsAcademicStaff, staff_school, assigned_class


class RegisterFilters(serializers.Serializer):
    academic_year = serializers.IntegerField()
    term = serializers.IntegerField()
    school_class = serializers.IntegerField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    calendar_year = serializers.IntegerField(min_value=1900, max_value=9999)
    export = serializers.ChoiceField(choices=["json", "pdf", "xlsx"], default="json")


def register_data(request):
    serializer = RegisterFilters(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    school = staff_school(request.user)
    cls = assigned_class(request.user, data["school_class"])
    year = get_object_or_404(AcademicYear, pk=data["academic_year"], school=school)
    term = get_object_or_404(Term, pk=data["term"], academic_year=year)
    days = calendar.monthrange(data["calendar_year"], data["month"])[1]
    start, end = date(data["calendar_year"], data["month"], 1), date(data["calendar_year"], data["month"], days)
    enrollments = StudentEnrollment.objects.filter(school_class=cls, academic_year=year, student__school=school, enrolled_on__lte=end).filter(Q(left_on__isnull=True) | Q(left_on__gte=start)).select_related("student").order_by("student__last_name", "student__first_name")
    records = AttendanceRecord.objects.filter(school=school, enrollment__school_class=cls, academic_year=year, term=term, attendance_date__range=(start, end))
    saved = {(r.enrollment_id, r.attendance_date.day): r.status for r in records}
    rows = []
    codes = {"present": "P", "absent": "A", "late": "L", "excused": "E"}
    for enrollment in enrollments:
        statuses = [saved.get((enrollment.pk, day)) for day in range(1, days + 1)]
        counts = Counter(s for s in statuses if s)
        marked = sum(counts.values())
        rows.append(dict(id=enrollment.pk, student_name=enrollment.student.get_full_name() if hasattr(enrollment.student, "get_full_name") else f"{enrollment.student.first_name} {enrollment.student.last_name}",
            admission_number=enrollment.student.admission_number, days=[codes.get(s, "") for s in statuses],
            **{s: counts[s] for s in codes}, percentage=round(100 * (counts["present"] + counts["late"]) / marked, 2) if marked else None))
    return dict(school=school.name, school_class=cls.name, academic_year=year.name, term=term.name,
        month=f"{calendar.month_name[data['month']]} {data['calendar_year']}", generated_at=timezone.now().isoformat(),
        teachers=list(cls.teacher_assignments.values_list("teacher__user__first_name", "teacher__user__last_name")),
        days=list(range(1, days + 1)), rows=rows, export_format=data["export"])


def export_rows(data):
    return [[data["school"], data["school_class"], data["academic_year"], data["term"], data["month"]],
        ["Generated", data["generated_at"], "Teachers", ", ".join(" ".join(t) for t in data["teachers"])],
        ["No.", "Student Name", "Admission Number", *data["days"], "Present", "Absent", "Late", "Excused", "Attendance %"],
        *[[i + 1, r["student_name"], r["admission_number"], *r["days"], r["present"], r["absent"], r["late"], r["excused"], r["percentage"] if r["percentage"] is not None else ""] for i, r in enumerate(data["rows"])]]


def excel(data):
    rows = []
    for i, row in enumerate(export_rows(data), 1):
        cells = []
        for value in row:
            if isinstance(value, (int, float)):
                cells.append(f'<c><v>{value}</v></c>')
            else:
                cells.append(f'<c t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Register" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(rows)}</sheetData></worksheet>')
    return buffer.getvalue()


def pdf(data):
    # Landscape pages with repeated metadata/header and monospaced day cells.
    lines = export_rows(data)
    header = [" | ".join(str(v) for v in row) for row in lines[:2]]
    heading = "No. Student Name             Admission    " + " ".join(f"{d:2}" for d in data["days"]) + "  P  A  L  E     %"
    body = [f"{i+1:3} {r['student_name'][:24]:24} {r['admission_number'][:12]:12} " + " ".join(f"{s:>2}" for s in r["days"]) + f" {r['present']:2} {r['absent']:2} {r['late']:2} {r['excused']:2} {str(r['percentage'] if r['percentage'] is not None else ''):>5}" for i, r in enumerate(data["rows"])]
    pages = [body[i:i + 42] for i in range(0, len(body), 42)] or [[]]
    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    page_ids = []
    for chunk in pages:
        page_id = len(objects) + 1
        page_ids.append(page_id)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id+1} 0 R >>".encode())
        content = "BT /F1 8 Tf 20 570 Td 12 TL\n"
        for line in [*header, heading, *chunk, "P Present; A Absent; L Late; E Excused. Attendance % = (P + L) / marked days."]:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content += f"({safe}) Tj T*\n"
        stream = (content + "ET").encode("latin-1", "replace")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{n} 0 R' for n in page_ids)}] >>".encode()
    output, offsets = b"%PDF-1.4\n", [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return output + f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()


class AttendanceRegister(APIView):
    permission_classes = [IsAcademicStaff]

    def get(self, request):
        data = register_data(request)
        kind = data.pop("export_format")
        if kind == "json":
            return Response(data)
        response = HttpResponse(pdf(data) if kind == "pdf" else excel(data), content_type="application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="attendance-register.{kind}"'
        return response
