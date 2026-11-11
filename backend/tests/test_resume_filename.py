from app.services import resume_pdf


def test_file_is_named_for_the_person_and_the_employer():
    assert resume_pdf.resume_stem("Emmanuel Ogunyinka", "Constellation Brands") == "Emmanuel_Ogunyinka_Constellation_Brands"


def test_generic_or_missing_company_falls_back_to_the_name():
    assert resume_pdf.resume_stem("Jane Doe", "apply") == "Jane_Doe"
    assert resume_pdf.resume_stem("Jane Doe", "Company not stated") == "Jane_Doe"
    assert resume_pdf.resume_stem("", "") == "Resume"


def test_odd_characters_are_removed():
    assert resume_pdf.resume_stem("Jane O'Neil", "AT&T / Mobility, Inc.") == "Jane_O_Neil_AT_T_Mobility_Inc"
