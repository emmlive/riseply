"""Things that quietly made a tailored resume worse to a machine or a reader:
bullets that read back as control characters, em dashes everywhere, and Word
resumes whose tables and headers were never read."""
import io

import pdfplumber
from docx import Document

from app.services import resume_customizer as rc
from app.services import resume_pdf
from app.services.resume_parser import extract_text_from_docx

RESUME = {
    "name": "Pat Example", "headline": "IT Audit | NIST CSF",
    "contact": ["pat@example.com", "(555) 010-2000"],
    "sections": [
        {"heading": "Professional Summary", "kind": "text",
         "text": "Auditor with 9 years of experience — mostly banks — and a CISA."},
        {"heading": "Experience", "kind": "entries", "entries": [
            {"title": "IT Auditor", "org": "Big Bank", "location": "Chicago, IL", "dates": "Jan 2018 – Present",
             "bullets": ["Led 12 ITGC audits — cut findings 30%.", "Tested IAM controls on 40 apps."]}]},
        {"heading": "Certifications", "kind": "bullets", "bullets": ["CISA"]},
    ],
}


def _pdf_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return "\n".join(p.extract_text() or "" for p in d.pages)


def test_pdf_bullets_read_back_as_bullets_not_control_characters():
    pdf = rc.build_pdf_from_blocks(rc.structure_to_blocks(RESUME))
    text = _pdf_text(pdf)
    assert "(cid:" not in text and "\x7f" not in text
    assert "• Led 12 ITGC audits" in text
    assert "• CISA" in text


def test_pdf_fonts_are_embedded():
    pdf = rc.build_pdf_from_blocks(rc.structure_to_blocks(RESUME))
    # an embedded TrueType subset carries its font name; the old built-in Helvetica never did
    assert b"Carlito" in pdf


def test_pasted_text_pdf_also_reads_back_cleanly():
    pdf = resume_pdf.build("PAT EXAMPLE\n• Led audits → saved 30%\n✓ CISA")
    text = _pdf_text(pdf)
    assert "(cid:" not in text and "Led audits" in text
    assert "✓" not in text     # no glyph for it, so it is dropped instead of printed as a box


def test_em_dashes_come_out_of_sentences_but_date_ranges_stay():
    blocks = rc.structure_to_blocks(RESUME)
    prose = " ".join(b.get("text", "") for b in blocks if b["type"] in ("text", "bullet", "sub"))
    assert "—" not in prose and "--" not in prose
    assert "mostly banks, and a CISA" in prose
    assert "Led 12 ITGC audits, cut findings 30%." in prose
    entry = next(b for b in blocks if b["type"] == "entry")
    assert entry["right"] == "Jan 2018 – Present"
    assert next(b for b in blocks if b["type"] == "sub")["text"] == "Big Bank, Chicago, IL"


def test_dedash_leaves_numbers_and_hyphenated_words_alone():
    assert rc.dedash("zero-trust, 2018 – 2020 and 10-15 users") == "zero-trust, 2018 – 2020 and 10-15 users"
    assert rc.dedash("a—b") == "a, b"


def test_docx_text_includes_header_and_tables():
    d = Document()
    d.sections[0].header.paragraphs[0].text = "Pat Example | pat@example.com | (555) 010-2000"
    d.add_paragraph("SUMMARY")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Skills"
    t.cell(0, 1).text = "NIST CSF, SOC 2"
    d.add_paragraph("EXPERIENCE")
    buf = io.BytesIO()
    d.save(buf)
    text = extract_text_from_docx(buf.getvalue())
    assert "pat@example.com" in text           # was in the header: used to vanish
    assert "Skills | NIST CSF, SOC 2" in text  # was in a table: used to vanish
    assert text.index("SUMMARY") < text.index("EXPERIENCE")
