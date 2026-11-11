from app.services import apply_guard, resume_customizer as rc, resume_voice


def _b(texts, headline="Compliance Analyst | SOX, NIST"):
    return [{"type": "headline", "text": headline}] + [{"type": "bullet", "text": t} for t in texts]


def test_stock_phrases_and_repeated_openers_are_flagged():
    flags = resume_voice.voice_flags(_b([
        "Spearheaded a results-driven audit of 12 systems",
        "Spearheaded vendor reviews for 20 suppliers",
        "Spearheaded training for 200 staff",
        "Wrote the control narrative",
    ]))
    assert any("Stock phrases" in f for f in flags)
    assert any('start with "spearheaded"' in f for f in flags)


def test_uneven_plain_resume_has_no_flags():
    assert resume_voice.voice_flags(_b([
        "Audited 12 payment systems against PCI-DSS.",
        "Trained 200 staff.",
        "Found 40 access control gaps across cloud and on-premise systems and tracked each fix to closure with system owners.",
        "Led SWIFT testing.",
        "Reviewed vendor risk for 20 suppliers and escalated six high-risk integrations.",
        "Wrote templates.",
    ])) == []


def test_keyword_pile_headline_and_dashes_flagged():
    flags = resume_voice.voice_flags(_b(["a — b — c — d"], headline="AI Security | A, B, C, D, E, F"))
    assert any("headline" in f for f in flags) and any("em dashes" in f for f in flags)


def test_ats_checks_include_the_voice_check():
    blocks = [{"type": "heading", "text": "Experience"}] + _b(["Spearheaded x results-driven", "Spearheaded y", "Spearheaded z"])
    c = next(x for x in rc.ats_checks(blocks)["checks"] if x["label"] == "Sounds like a person")
    assert not c["ok"] and "Make it sound more human" in c["detail"]


def test_fit_note_only_for_weak_or_stretch_pending_matches():
    assert "Low match" in apply_guard.fit_note(30, "pending_approval")
    assert "Stretch" in apply_guard.fit_note(55, "pending_approval")
    assert apply_guard.fit_note(80, "pending_approval") == ""
    assert apply_guard.fit_note(30, "submitted") == ""
