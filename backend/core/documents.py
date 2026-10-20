"""Reusable A4 document renderer and typed, formula-safe Excel workbooks."""
import base64
import logging
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image

from .models import SchoolDocumentSettings


def branding(school, request=None, snapshot=False):
    settings = SchoolDocumentSettings.objects.filter(school=school).first()
    data = dict(name=school.name, address=school.address, phone=school.phone_number, email=school.email,
                logo=request.build_absolute_uri(school.logo.url) if request and school.logo else None,
                motto=settings.motto if settings else '', website=settings.website if settings else '',
                additional_contacts=settings.additional_contacts if settings else '',
                contact_person=settings.contact_person if settings else '', brand_color=settings.brand_color if settings else '#244768')
    if snapshot and school.logo:
        # Embed the validated image: replacing a school's uploaded logo must not
        # change or break previously issued documents. Never fetch arbitrary URLs.
        try:
            with school.logo.open('rb') as source:
                raw = source.read(2 * 1024 * 1024 + 1)
            if len(raw) <= 2 * 1024 * 1024:
                ImageReader(BytesIO(raw)).getSize()
                data['logo_data'] = base64.b64encode(raw).decode('ascii')
        except Exception as exc:
            # A private storage outage or missing logo must not prevent an
            # otherwise valid financial document from being downloaded.
            logging.getLogger(__name__).warning('Document logo unavailable (%s)', type(exc).__name__)
    return data


def money(value, currency=''):
    return f'{currency} {Decimal(value):,.2f}'.strip()


class SchoolDocument:
    def __init__(self, brand, title, wide=False):
        self.brand, self.title = brand, title
        self.buffer = BytesIO()
        self.doc = SimpleDocTemplate(self.buffer, pagesize=landscape(A4) if wide else A4,
                                     leftMargin=36, rightMargin=36, topMargin=32, bottomMargin=36,
                                     title=title, author=brand['name'])
        self.width = self.doc.width
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle('Cell', fontName='Helvetica', fontSize=8, leading=11, splitLongWords=True))
        self.styles.add(ParagraphStyle('Brand', parent=self.styles['Heading1'], alignment=TA_CENTER, textColor=colors.HexColor(brand['brand_color'])))
        self.story = []
        self.last_table = None
        text = [self.p(brand['name'], 'Brand')]
        for key in ('motto', 'address', 'phone', 'additional_contacts', 'email', 'website'):
            if brand.get(key):
                text.append(self.p(brand[key]))
        logo = ''
        if brand.get('logo_data'):
            raw = BytesIO(base64.b64decode(brand['logo_data']))
            w, h = ImageReader(raw).getSize()
            scale = min(66 / w, 66 / h)
            logo = Image(raw, width=w * scale, height=h * scale)
        header = Table([[logo, text]], colWidths=[80, self.width - 80])
        header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor(brand['brand_color']))]))
        self.story.extend([header, Spacer(1, 14), self.p(title, 'Heading1')])

    def p(self, text, style='Cell'):
        return Paragraph(escape(str(text if text is not None else '')).replace('\n', '<br/>'), self.styles[style])

    def text(self, value, style='Cell'):
        self.story.extend([self.p(value, style), Spacer(1, 5)])

    def table(self, headers, rows, weights=None, footer=False):
        weights = weights or [1] * len(headers)
        widths = [self.width * w / sum(weights) for w in weights]
        values = [[self.p(v) for v in headers], *[[self.p(v) for v in row] for row in rows]]
        table = Table(values,
                      colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9eff4')),
                                  ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                                  ('TOPPADDING', (0, 0), (-1, -1), 7), ('LINEBELOW', (0, 0), (-1, 0), .7, colors.grey),
                                  ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#d8dfe5'))]))
        self.story.extend([table, Spacer(1, 10)])
        self.last_table = (len(self.story) - 2, values, widths)
        if footer and len(rows) > 1:
            table.wrap(self.width, self.doc.height)
            if sum(table._rowHeights[-2:]) + table._rowHeights[0] < self.doc.height - 24:
                table.setStyle(TableStyle([('NOSPLIT', (0, -2), (-1, -1))]))

    def totals(self, pairs):
        table = Table([[self.p(k), self.p(v)] for k, v in pairs], colWidths=[self.width * .65, self.width * .35])
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f8')),
                                  ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        if self.last_table and self.last_table[0] == len(self.story) - 2:
            index, values, widths = self.last_table
            # Make totals the last spanning row of the transaction table. A
            # pagination constraint keeps the last transaction and totals on the
            # same page; long descriptions may still split across prior pages.
            footer = Table(values + [[table, *([''] * (len(widths) - 1))]], colWidths=widths,
                           repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
            footer.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9eff4')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -2), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -2), 7), ('LINEBELOW', (0, 0), (-1, -2), .25, colors.HexColor('#d8dfe5')),
                ('SPAN', (0, -1), (-1, -1)), ('LEFTPADDING', (0, -1), (-1, -1), 0), ('RIGHTPADDING', (0, -1), (-1, -1), 0),
                ('NOSPLIT', (0, -1), (-1, -1)),
            ]))
            footer.wrap(self.width, self.doc.height)
            if len(values) > 1 and sum(footer._rowHeights[-2:]) + footer._rowHeights[0] < self.doc.height - 24:
                footer.setStyle(TableStyle([('NOSPLIT', (0, -2), (-1, -1))]))
            self.story[index] = footer
        else:
            self.story.append(KeepTogether([table, Spacer(1, 10)]))
        self.last_table = None

    def render(self):
        def footer(canvas, doc):
            canvas.setFont('Helvetica', 8)
            name = self.brand['name']
            while stringWidth(name, 'Helvetica', 8) > self.width - 80:
                name = name[:-1]
            canvas.drawString(36, 22, name)
            canvas.drawRightString(doc.pagesize[0] - 36, 22, f'Page {doc.page}')
        self.doc.build(self.story, onFirstPage=footer, onLaterPages=footer)
        return self.buffer.getvalue()


def excel(rows, title='Report', header_row=1):
    """Real numeric cells; user text is always inlineStr, never a formula."""
    output = BytesIO()
    xml_rows = []
    for i, row in enumerate(rows, 1):
        cells = []
        for value in row:
            style = 2 if i == header_row else 3 if i == 1 else 0
            if isinstance(value, (int, float, Decimal)):
                cells.append(f'<c s="{style or 1}"><v>{value}</v></c>')
            else:
                # XML 1.0 excludes control characters even inside escaped text.
                value = ''.join(c for c in str(value or '') if ord(c) >= 32 or c in '\t\n\r')
                cells.append(f'<c s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>')
        xml_rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('xl/styles.xml', '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE9EFF4"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="4" fontId="1" fillId="2" borderId="0" xfId="0" applyNumberFormat="1" applyFill="1" applyFont="1"><alignment wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape(title)}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="{header_row}" topLeftCell="A{header_row + 1}" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="30" width="23" customWidth="1"/></cols><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    return output.getvalue()


def attachment(content, name, kind):
    response = HttpResponse(content, content_type='application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{name}.{kind}"'
    response['Cache-Control'] = 'private, no-store'
    return response
