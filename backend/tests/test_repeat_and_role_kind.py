from app.services import search_terms as st


def test_same_opening_in_two_towns_is_one_key():
    a = st.dupe_key("Green Bay Packaging", "Senior Security Engineer - Preble, WI")
    b = st.dupe_key("Green Bay Packaging, Inc.", "Senior Security Engineer – Oneida, WI")
    assert a == b


def test_different_title_or_company_is_a_different_key():
    assert st.dupe_key("Acme", "Security Architect") != st.dupe_key("Acme", "Security Engineer")
    assert st.dupe_key("Acme", "Security Architect") != st.dupe_key("Beta", "Security Architect")


def test_architect_search_does_not_get_engineer_jobs():
    prof = [{"titles": ["IT Security Architect"], "active": True}]
    assert not st.title_fits("Senior Security Engineer", prof)
    assert st.title_fits("Cybersecurity Architect", prof)
    assert st.title_fits("Security Architecture Lead", prof)  # no hard kind word: let it through


def test_engineer_and_developer_still_interchange():
    prof = [{"titles": ["Software Engineer"], "active": True}]
    assert st.title_fits("Backend Developer", prof)


def test_profile_listing_both_kinds_sees_both():
    prof = [{"titles": ["Security Architect", "Security Engineer"], "active": True}]
    assert st.title_fits("Security Engineer", prof) and st.title_fits("Security Architect", prof)
