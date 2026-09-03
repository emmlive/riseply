"""Customizable PDF report of org analytics -- lets an administrator
pick which sections to include rather than always getting the full
CSV dump. Same reportlab approach as mentor_export.py, same reasoning
for choosing it (pure Python, no system graphics dependencies to
install on Render).

This is deliberately "customizable" in the sense of section
selection, not a drag-and-drop report *builder* with arbitrary layout
control -- a real, useful middle ground between "always the same fixed
CSV" and a much bigger report-builder feature we're not attempting
right now (see roadmap).
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

VALID_SECTIONS = {"checklist", "lessons", "qa_gaps", "departments", "mentorship"}


def _section_table(headers: list, rows: list, col_widths: list, cell_style) -> Table:
    data = [headers] + [[Paragraph(str(v), cell_style) for v in row] for row in rows]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def generate_analytics_pdf(org_name: str, analytics, sections: set) -> bytes:
    """analytics is a schemas.OrgAnalyticsOut instance (or matching
    duck-typed object -- tests pass a plain object with the same
    attributes rather than constructing a real Pydantic model, and
    that's fine here since this function only reads attributes).

    sections is a subset of VALID_SECTIONS; unrecognized values are
    silently ignored by the caller (see the router) rather than
    erroring, since a stale/unexpected query param shouldn't break
    report generation -- it should just mean that section is skipped.
    An empty/all-invalid selection still produces a valid PDF with
    just the summary line, not an error.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
    subtitle_style = ParagraphStyle("SubtitleStyle", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=16)
    section_heading = ParagraphStyle("SectionHeading", parent=styles["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=6)
    cell_style = ParagraphStyle("CellStyle", parent=styles["Normal"], fontSize=9, leading=12)
    body_style = ParagraphStyle("BodyStyle", parent=styles["Normal"], fontSize=10, leading=14)

    elements = [
        Paragraph(f"{org_name} — Onboarding & Mentorship Report", title_style),
        Paragraph(f"Generated {date.today().isoformat()} · Riseply Mentorship (part of the Org Buddy onboarding platform)", subtitle_style),
        Paragraph(f"Total employees: {analytics.total_employees}", body_style),
    ]
    if analytics.avg_days_to_complete_onboarding is not None:
        elements.append(Paragraph(f"Average days to complete onboarding: {analytics.avg_days_to_complete_onboarding}", body_style))

    if "checklist" in sections and analytics.checklist_items:
        elements.append(Paragraph("Checklist completion", section_heading))
        rows = [[s.title, f"{s.completion_rate}%"] for s in analytics.checklist_items]
        elements.append(_section_table(["Item", "Completion"], rows, [4.5 * inch, 1.8 * inch], cell_style))

    if "lessons" in sections and analytics.lesson_quizzes:
        elements.append(Paragraph("Lesson quiz performance", section_heading))
        rows = [[s.title, f"{s.correct_rate}%"] for s in analytics.lesson_quizzes]
        elements.append(_section_table(["Lesson", "Pass rate"], rows, [4.5 * inch, 1.8 * inch], cell_style))

    if "qa_gaps" in sections and analytics.qa_gaps:
        elements.append(Paragraph("Content gaps (unanswered questions)", section_heading))
        rows = [[s.question, str(s.count)] for s in analytics.qa_gaps[:15]]
        elements.append(_section_table(["Question", "Times asked"], rows, [5 * inch, 1.3 * inch], cell_style))

    if "departments" in sections and analytics.departments:
        elements.append(Paragraph("By department", section_heading))
        rows = [[s.department_name, str(s.total_employees)] for s in analytics.departments]
        elements.append(_section_table(["Department", "Employees"], rows, [4.5 * inch, 1.8 * inch], cell_style))

    if "mentorship" in sections:
        m = analytics.mentorship
        elements.append(Paragraph("Mentorship program", section_heading))
        rows = [
            ["Total pairings", str(m.total_pairings)],
            ["Employees with a mentor", f"{m.employees_with_mentor_pct}%"],
            ["Total meetings logged", str(m.total_meetings_logged)],
            ["Avg meetings per pairing", str(m.avg_meetings_per_pairing)],
            ["Avg feedback rating", f"{m.avg_feedback_rating}/5" if m.avg_feedback_rating is not None else "N/A"],
            ["Pairings ended", str(m.pairings_ended)],
            ["Would recommend mentor", f"{m.would_recommend_mentor_pct}%" if m.would_recommend_mentor_pct is not None else "N/A"],
            ["Group relationships", str(m.total_group_relationships)],
            ["Reciprocal relationships", str(m.total_reciprocal_relationships)],
            ["Group/reciprocal meetings logged", str(m.total_relationship_meetings_logged)],
        ]
        elements.append(_section_table(["Metric", "Value"], rows, [4.5 * inch, 1.8 * inch], cell_style))

    elements.append(Spacer(1, 12))
    doc.build(elements)
    return buffer.getvalue()
