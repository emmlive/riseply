import io
from fastapi import HTTPException


def extract_text_from_pdf(file_bytes: bytes) -> str:
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
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


def extract_text_from_docx(file_bytes: bytes) -> str:
    from docx import Document
    try:
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs]
        text = "\n".join(paragraphs).strip()
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
