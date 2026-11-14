"""A long posting must keep its requirements when it is cut down for the model."""


def test_long_posting_keeps_the_requirements_not_just_the_company_blurb():
    from app.services import job_terms
    blurb = "We are a global company with a long history. " * 200          # ~8,800 chars
    posting = blurb + "\n\nRequirements\n- 7+ years of IT audit\n- CISA preferred\n- M&A diligence experience\n"
    old = posting[:6000]
    assert "CISA preferred" not in old                                      # what the model used to see
    new = job_terms.focus_text(posting, 6000)
    assert "CISA preferred" in new and "M&A diligence experience" in new
    assert len(new) <= 6000 + 10
    assert job_terms.focus_text("short posting", 6000) == "short posting"
    assert job_terms.focus_text("x" * 9000, 6000) == "x" * 6000             # no heading: plain cut
