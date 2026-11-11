from app.services import resume_customizer as rc


def _blocks(headline):
    return [
        {"type": "name", "text": "Jane Doe"},
        {"type": "headline", "text": headline},
        {"type": "heading", "text": "Professional Experience"},
        {"type": "entry", "left": "Sr. IT Cybersecurity Compliance Analyst", "right": "Nov 2024 – Present"},
        {"type": "entry", "left": "IT Auditor", "right": "Jan 2016 – Aug 2019"},
    ]


def test_headline_claiming_a_role_not_held_is_flagged_and_replaced():
    b = _blocks("Senior AI Security Architect | LLM Governance, NIST")
    assert rc.unsupported_headline_words(b) == ["architect"]
    fixed, note = rc.ground_headline(b)
    head = next(x["text"] for x in fixed if x["type"] == "headline")
    assert head == "Sr. IT Cybersecurity Compliance Analyst | LLM Governance, NIST"
    assert "architect" in note
    assert rc.unsupported_headline_words(fixed) == []


def test_honest_headline_is_left_alone():
    b = _blocks("AI Security Specialist | LLM Governance, NIST")
    assert rc.unsupported_headline_words(b) == []
    assert rc.ground_headline(b) == (b, "")


def test_senior_abbreviation_counts_as_senior():
    assert rc.unsupported_headline_words(_blocks("Senior Compliance Analyst | SOX")) == []


def test_ats_checks_report_the_headline_mismatch():
    r = rc.ats_checks(_blocks("Principal Security Engineer | NIST"))
    c = next(x for x in r["checks"] if x["label"] == "Headline matches your history")
    assert not c["ok"] and "principal" in c["detail"]
    ok = rc.ats_checks(_blocks("IT Audit | SOX"))
    assert next(x for x in ok["checks"] if x["label"] == "Headline matches your history")["ok"]
