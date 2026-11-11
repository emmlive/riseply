import io

from docx import Document

from app.services import resume_customizer as rc


def _props(blocks):
    return Document(io.BytesIO(rc.build_docx_from_blocks(blocks))).core_properties


def test_resume_carries_no_python_docx_tag_and_uses_the_candidates_name():
    cp = _props([{"type": "name", "text": "Jane Doe"}, {"type": "body", "text": "x"}])
    assert cp.author == "Jane Doe" and cp.last_modified_by == "Jane Doe"
    assert "python-docx" not in (cp.comments or "") and cp.comments == ""


def test_no_name_block_leaves_author_empty_not_python_docx():
    cp = _props([{"type": "body", "text": "x"}])
    assert cp.author == "" and "python-docx" not in (cp.comments or "")
