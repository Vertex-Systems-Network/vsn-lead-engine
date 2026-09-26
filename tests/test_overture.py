import re

from vsn_lead_engine.sources.overture import CATEGORY_PATTERNS, OverturePlaceSource


def test_category_patterns_cover_core_verticals():
    samples={
        "Medical & Clinics":"medical clinic",
        "Property & Real Estate":"real_estate_agency",
        "IT & Software":"software company",
        "Salon":"hair_salon",
        "Insurance":"insurance agency",
    }
    for category,value in samples.items():
        assert re.search(CATEGORY_PATTERNS[category],value,re.I)


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
