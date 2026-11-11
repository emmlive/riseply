from unittest.mock import patch

from app.services import resume_customizer as rc


def _long(roles=6, bullets=10):
    b = [{"type": "name", "text": "Jane Doe"}, {"type": "headline", "text": "IT Auditor | SOX"},
         {"type": "contact", "text": "j@x.com  |  202-555-0100"}, {"type": "heading", "text": "Professional Experience"}]
    for r in range(roles):
        b.append({"type": "entry", "left": f"Auditor {r}", "right": f"Jan 20{10 + r} – Dec 20{11 + r}"})
        b.append({"type": "sub", "text": f"Company {r}, Chicago, IL"})
        for i in range(bullets):
            b.append({"type": "bullet", "text": f"Tested access controls for system {r}-{i} across SOX, PCI-DSS and NIST scope, then wrote findings for the audit committee and tracked each fix to closure."})
    return b


def test_a_long_resume_is_brought_to_two_pages_in_the_real_pdf():
    blocks = _long()
    assert rc.pdf_page_count(rc.build_pdf_from_blocks(blocks)) > 2
    with patch.object(rc, "_condense_with_claude", return_value=None):
        out, note = rc.fit_for_delivery(blocks, {"title": "Auditor", "description": "SOX access controls"})
    assert rc.pdf_page_count(rc.build_pdf_from_blocks(out)) <= 2
    assert note.startswith("Shortened to fit two pages")
    assert [b for b in out if b["type"] == "entry"] == [b for b in blocks if b["type"] == "entry"], "no job is removed"


def test_a_resume_that_already_fits_is_untouched():
    blocks = _long(roles=2, bullets=3)
    out, note = rc.fit_for_delivery(blocks, {"title": "x", "description": ""})
    assert out == blocks and note == ""
