import re

from vsn_lead_engine.sources.overture import (
    CATEGORY_PATTERNS,
    OverturePlaceSource,
    category_match_reason,
)


def test_category_patterns_cover_core_verticals():
    samples={
        "Medical & Clinics":"medical_clinic",
        "Property & Real Estate":"real_estate_agency",
        "IT & Software":"software_development",
        "Salon":"hair_salon",
        "Insurance":"insurance_agency",
    }
    for category,value in samples.items():
        assert re.fullmatch(CATEGORY_PATTERNS[category],value,re.I)


def test_retirement_home_never_matches_cars():
    assert category_match_reason(
        "Cars",
        primary="retirement_home",
        basic="retirement_home",
        hierarchy=["health_care","retirement_home"],
        name="Riverview Manor Elderly Development",
    ) is None


def test_dermatology_never_matches_salon_from_beauty_name():
    assert category_match_reason(
        "Salon",
        primary="dermatology",
        basic="dermatology",
        hierarchy=["health_care","medical_specialist","dermatology"],
        name="BeautyAllure Dermatology",
    ) is None


def test_pet_salon_name_cannot_override_pet_taxonomy():
    assert category_match_reason(
        "Salon",
        primary="pet_groomer",
        basic="pet_groomer",
        hierarchy=["services_and_business","pet_service","pet_groomer"],
        name="Petiamo Pet Salon",
    ) is None


def test_shoe_repair_cannot_enter_salon():
    assert category_match_reason(
        "Salon",
        primary="shoe_repair",
        basic="shoe_repair",
        hierarchy=["services_and_business","repair_service","shoe_repair"],
        name="Stewart's Supreme Shine",
    ) is None


def test_spa_is_spa_not_salon():
    assert category_match_reason(
        "Spa",
        primary="spa",
        basic="spa",
        hierarchy=["lifestyle_services","spa"],
        name="Awesome Nails",
    ) == "taxonomy:spa"
    assert category_match_reason(
        "Salon",
        primary="spa",
        basic="spa",
        hierarchy=["lifestyle_services","spa"],
        name="Awesome Nails",
    ) is None


def test_observed_good_taxonomies_still_match():
    cases=[
        ("Cars","automotive_repair"),
        ("Cars","auto_glass_service"),
        ("Cars","tire_dealer_and_repair"),
        ("Cars","towing_service"),
        ("Motorbikes","motorcycle_repair"),
        ("Motorbikes","motorcycle_dealer"),
        ("Insurance","insurance_agency"),
        ("Salon","hair_salon"),
        ("Salon","nail_salon"),
        ("Salon","hair_stylist"),
        ("AI & Automation","automation_service"),
        ("AI & Automation","home_automation"),
        ("Medical & Clinics","doctors_office"),
    ]
    for category,taxonomy in cases:
        assert category_match_reason(
            category,
            primary=taxonomy,
            basic=taxonomy,
            hierarchy=[taxonomy],
            name="Example",
        ) == f"taxonomy:{taxonomy}"


def test_conflicting_taxonomy_blocks_name_fallback():
    assert category_match_reason(
        "AI & Automation",
        primary="marketing_agency",
        basic="marketing_agency",
        hierarchy=["services_and_business","marketing_agency"],
        name="Lava Automation",
    ) is None
    assert category_match_reason(
        "AI & Automation",
        primary="vocational_and_technical_school",
        basic="vocational_and_technical_school",
        hierarchy=["education","vocational_and_technical_school"],
        name="Oregon Robotics Tournament & Outreach Program",
    ) is None


def test_name_fallback_requires_missing_taxonomy():
    reason=category_match_reason(
        "Insurance",
        primary="",
        basic="",
        hierarchy=[],
        name="Sandra Jardine American Family Insurance",
    )
    assert reason and reason.startswith("name_fallback:")

    assert category_match_reason(
        "Insurance",
        primary="bank",
        basic="bank",
        hierarchy=["services_and_business","financial_service","bank"],
        name="Example Insurance",
    ) is None


def test_sql_clause_uses_taxonomy_token_boundaries():
    clause=OverturePlaceSource._sql_category_clause("Cars")
    assert "(^|\\|)" in clause
    assert "(\\||$)" in clause
    assert "names.primary" in clause  # only guarded fallback


def test_social_urls_are_routed():
    result=OverturePlaceSource._social_fields([
        "https://www.facebook.com/example",
        "https://www.instagram.com/example",
        "https://www.linkedin.com/company/example",
        "https://x.com/example",
        "https://www.tiktok.com/@example",
    ])
    assert result["facebook"].startswith("https://www.facebook.com/")
    assert result["instagram"].startswith("https://www.instagram.com/")
    assert result["linkedin"].startswith("https://www.linkedin.com/")
    assert result["twitter"].startswith("https://x.com/")
    assert result["tiktok"].startswith("https://www.tiktok.com/")


def test_maps_url_is_search_url():
    url=OverturePlaceSource._maps_url("Example Inc","1 Main St","Phoenix","Arizona")
    assert url.startswith("https://www.google.com/maps/search/?api=1&query=")
    assert "Example+Inc" in url
