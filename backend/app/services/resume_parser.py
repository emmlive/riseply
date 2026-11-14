import io
from fastapi import HTTPException


# A resume is a few pages. Reading a 30-page PDF used to take over 300 MB
# on a 512 MB server, so only the first pages are read and each page's
# memory is released before the next one.
MAX_PDF_PAGES = 8


def extract_text_from_pdf(file_bytes: bytes) -> str:
    import pdfplumber
    try:
        pages = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages[:MAX_PDF_PAGES]:
                pages.append(page.extract_text() or "")
                page.flush_cache()
        text = "\n".join(pages).strip()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Couldn't read that PDF — it may be scanned/image-based rather than text, corrupted, or password-protected.",
        )
    if not text:
        raise HTTPException(
            status_code=400,
            detail="No text found in that PDF — it may be a scanned image rather than actual text. Try pasting your resume text directly instead.",
        )
    return text


def _docx_lines(doc) -> list[str]:
    """Every piece of text in a Word resume, in reading order: body paragraphs,
    tables (a lot of resumes are laid out in one), text boxes, and the header and
    footer, which is where many people put their contact details. Reading only
    doc.paragraphs silently drops all of that."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    lines: list[str] = []
    seen: set[str] = set()

    def add(text: str):
        t = (text or "").strip()
        if t:
            lines.append(t)

    def table_lines(tbl):
        for row in tbl.rows:
            cells, last = [], None
            for cell in row.cells:
                if cell._tc is last:            # a merged cell repeats itself
                    continue
                last = cell._tc
                cells.append(" ".join(p.text.strip() for p in cell.paragraphs if p.text.strip()))
                for inner in cell.tables:
                    table_lines(inner)
            joined = " | ".join(c for c in cells if c)
            if joined:
                lines.append(joined)

    for section in doc.sections:
        for part in (section.header, section.footer):
            for p in part.paragraphs:
                t = p.text.strip()
                if t and t not in seen:
                    seen.add(t)
                    add(t)
            for tbl in part.tables:
                table_lines(tbl)

    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            add(Paragraph(child, doc).text)
        elif tag == "tbl":
            table_lines(Table(child, doc))

    # Text boxes sit inside paragraphs; Word stores each one twice (a modern and a
    # fallback copy), so repeats are dropped.
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    boxed: set[str] = set()
    for p in body.iterfind(".//w:txbxContent//w:p", ns):
        t = "".join(x.text or "" for x in p.iterfind(".//w:t", ns)).strip()
        if t and t not in boxed:
            boxed.add(t)
            add(t)
    return lines


def extract_text_from_docx(file_bytes: bytes) -> str:
    from docx import Document
    try:
        doc = Document(io.BytesIO(file_bytes))
        text = "\n".join(_docx_lines(doc)).strip()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Couldn't read that .docx file — it may be corrupted or in an unsupported format.",
        )
    if not text:
        raise HTTPException(status_code=400, detail="No text found in that document.")
    return text


def extract_resume_text(filename: str, file_bytes: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    if name.endswith(".doc"):
        raise HTTPException(
            status_code=400,
            detail="Old-format .doc files aren't supported — please save it as .docx or .pdf and try again.",
        )
    raise HTTPException(
        status_code=400,
        detail="Unsupported file type — please upload a .pdf or .docx file.",
    )
