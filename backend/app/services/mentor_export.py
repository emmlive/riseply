"""Generates a printable/downloadable PDF of a mentor-mentee pairing's
meeting history -- what the RFI calls "download and print specific
meeting dates that are documented."

Uses reportlab rather than a browser-rendering approach (e.g.
weasyprint/wkhtmltopdf): it's pure Python with no system-level
graphics dependencies to install on Render, which matters more for a
one-page tabular document like this than any layout sophistication
those tools would offer.

Deliberately excludes feedback_note from the PDF even though it's
already visible to the pairing in-app (see list_mentor_meetings): this
document is meant to be downloaded and potentially shared/printed
outside the platform (e.g. handed to an HR contact as documentation
that meetings occurred), and a private feedback comment ending up in a
printed handout is a much easier privacy mistake to make than the same
text staying on-screen. Rating is included since a bare number carries
far less risk of accidentally exposing something someone wrote in
confidence.
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


def generate_meeting_history_pdf(employee_name: str, mentor_name: str, meetings: list) -> bytes:
    """meetings is a list of MentorMeetingLog rows, most-recent-first
    (same ordering list_mentor_meetings already returns) -- reversed
    here to chronological order, since a printed record of "what
    happened over time" reads more naturally oldest-to-newest than a
    live in-app feed does."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
    subtitle_style = ParagraphStyle("SubtitleStyle", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=16)
    cell_style = ParagraphStyle("CellStyle", parent=styles["Normal"], fontSize=9, leading=12)

    elements = [
        Paragraph("Mentorship Meeting History", title_style),
        Paragraph(
            f"{employee_name} &amp; {mentor_name} &middot; Generated {date.today().isoformat()} &middot; Riseply Mentorship",
            subtitle_style,
        ),
    ]

    if not meetings:
        elements.append(Paragraph("No meetings have been logged for this pairing yet.", cell_style))
    else:
        chronological = list(reversed(meetings))
        table_data = [["Date", "Notes", "Rating"]]
        for m in chronological:
            rating_str = f"{m.rating}/5" if m.rating else "—"
            table_data.append([
                Paragraph(m.meeting_date.isoformat(), cell_style),
                Paragraph(m.notes or "—", cell_style),
                Paragraph(rating_str, cell_style),
            ])

        table = Table(table_data, colWidths=[1.1 * inch, 4.4 * inch, 0.8 * inch], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            f"Total meetings logged: {len(meetings)}",
            ParagraphStyle("Footer", parent=styles["Normal"], fontSize=9, textColor=colors.grey),
        ))

    doc.build(elements)
    return buffer.getvalue()
