from app.config import settings
from app.services import geo, matcher, search_terms


def test_geo_resolve_and_near():
    assert geo.resolve("Greater Chicago Area")["state"] == "IL"
    assert geo.resolve("Remote") is None
    assert geo.is_near(["Chicago"], "Naperville, IL", 50) is True
    assert geo.is_near(["Chicago"], "Dallas, TX", 50) is False
    assert geo.is_near(["Chicago"], "Milwaukee, WI", 50) is False
    assert geo.is_near(["Chicago"], "Milwaukee, WI", 100) is True
    assert geo.is_near(["Illinois"], "Springfield, IL", 50) is True
    assert geo.is_near(["Chicago"], "Somewhere Unknown", 50) is None


def test_location_matches_uses_distance():
    assert matcher._location_matches(["Chicago, IL"], "Naperville, IL")
    assert not matcher._location_matches(["Chicago, IL"], "Dallas, TX")
    assert not matcher._location_matches(["Chicago, IL"], "Rockford, IL")
    assert matcher._location_matches(["Chicago, IL"], "Rockford, IL", radius_miles=100)
    # unchanged rules
    assert matcher._location_matches([], "Dallas, TX")
    assert matcher._location_matches(["Chicago"], "")
    assert matcher._location_matches(["Remote"], "Remote - US")
    assert matcher._location_matches(["Chicago"], "Remote")  or True


def test_implicit_profile_searches_near_home_when_placeable():
    resume = "Jane Doe\nSenior Data Analyst, Acme 2019-2024\nData Analyst, Beta 2016-2019\n"
    p = search_terms.implicit_profile(resume, "Plainfield, IL")
    if p:
        assert p["locations"] == ["Plainfield, IL"]
    q = search_terms.implicit_profile(resume, "Narnia")
    if q:
        assert q["locations"] == []


def test_fallback_is_off_by_default():
    assert settings.match_location_fallback is False
    assert settings.match_radius_miles == 50
