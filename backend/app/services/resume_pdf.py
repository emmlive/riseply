"""A plain, ATS-friendly PDF made from resume text, for people who pasted their
resume instead of uploading a file. One column, standard font, real text."""
import io
import re
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

MAX_CHARS = 30000


def safe_filename(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip()).strip("_")[:40]
    return f"{stem}_Resume.pdf" if stem else "Resume.pdf"


def build(resume_text: str) -> bytes:
    body = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=13)
    head = ParagraphStyle("h", parent=body, fontName="Helvetica-Bold", spaceBefore=8)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    flow = []
    for raw in (resume_text or "")[:MAX_CHARS].splitlines():
        line = raw.rstrip()
        if not line.strip():
            flow.append(Spacer(1, 5))
            continue
        # Short all-caps lines read as section headings.
        is_head = len(line) <= 40 and line.upper() == line and re.search(r"[A-Z]", line)
        flow.append(Paragraph(escape(line.strip()), head if is_head else body))
    if not flow:
        flow.append(Paragraph("Resume", body))
    doc.build(flow)
    return buf.getvalue()


_GENERIC_COMPANY = {"", "apply", "careers", "career", "jobs", "job", "www", "company not stated", "resume", "unknown"}


def resume_stem(person: str, company: str) -> str:
    """File name for a resume sent to one employer: Jane_Doe_Acme_Corp. The
    employer's name tells the recruiter whose resume it is at a glance, and the
    person's name keeps it findable among hundreds of files."""
    def part(v: str, n: int) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", (v or "").strip()).strip("_")[:n]
    name = part(person, 30)
    co = "" if (company or "").strip().lower() in _GENERIC_COMPANY else part(company, 30)
    return "_".join(x for x in (name, co) if x) or "Resume"
