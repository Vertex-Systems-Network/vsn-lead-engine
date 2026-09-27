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
        ("Salon","eyelash_service"),
        ("Salon","skin_care_and_makeup"),
        ("Salon","blow_dry_blow_out_service"),
        ("Cars","auto_detailing"),
        ("Cars","auto_dealer"),
        ("Cars","used_auto_dealer"),
        ("Cars","truck_repair"),
        ("Cars","oil_change_station"),
        ("Insurance","auto_insurance"),
        ("Insurance","life_insurance"),
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


def test_duckdb_connection_is_reused_and_closed(monkeypatch):
    class FakeConnection:
        def __init__(self):
            self.closed=False
            self.commands=[]

        def execute(self, command, params=None):
            self.commands.append((command,params))
            return self

        def close(self):
            self.closed=True

    created=[]
    def fake_connect(database):
        conn=FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr("vsn_lead_engine.sources.overture.duckdb.connect",fake_connect)
    source=OverturePlaceSource(release="2026-09-24.0")
    first=source._get_connection()
    second=source._get_connection()

    assert first is second
    assert len(created)==1
    assert [cmd for cmd,_ in first.commands[:3]]==[
        "INSTALL httpfs",
        "LOAD httpfs",
        "SET s3_region='us-west-2'",
    ]

    source.close()
    assert first.closed
    assert source._connection is None


def test_search_keeps_website_only_candidate_for_enrichment(monkeypatch):
    source=OverturePlaceSource(release="2026-09-24.0")
    columns=[
        "id","name","basic_category","taxonomy_primary","taxonomy_hierarchy",
        "phone","website","email","socials","address","locality",
        "address_region","postcode","address_country","longitude","latitude",
        "confidence","source_dataset",
    ]
    row=(
        "place-1","Example Software","software_company","software_company",
        ["services_and_business","software_company"],None,
        "https://example.com","",[],"1 Main St","Austin","Texas","78701",
        "US",-97.74,30.27,0.9,"example-dataset",
    )

    class FakeCursor:
        description=[(name,) for name in columns]

        def fetchall(self):
            return [row]

    class FakeConnection:
        def __init__(self):
            self.sql=""

        def execute(self, sql, params=None):
            self.sql=sql
            return FakeCursor()

    connection=FakeConnection()
    monkeypatch.setattr(source,"_get_connection",lambda:connection)

    leads=source.search(
        "IT & Software",
        {
            "country":"United States",
            "region":"Texas",
            "city":"Austin",
            "bbox":[-98.0,30.0,-97.0,31.0],
        },
        limit=10,
    )

    assert len(leads)==1
    assert leads[0].phone==""
    assert leads[0].website=="https://example.com"
    assert "websites IS NOT NULL" in connection.sql


def test_search_applies_hash_partition_to_duckdb_query(monkeypatch):
    source=OverturePlaceSource(release="2026-09-24.0")
    columns=[
        "id","name","basic_category","taxonomy_primary","taxonomy_hierarchy",
        "phone","website","email","socials","address","locality",
        "address_region","postcode","address_country","longitude","latitude",
        "confidence","source_dataset",
    ]
    row=(
        "place-2","Partitioned Software","software_company","software_company",
        ["services_and_business","software_company"],"+1 202 555 0199",
        "https://partitioned.example","",[],"2 Main St","Austin","Texas","78701",
        "US",-97.74,30.27,0.9,"example-dataset",
    )

    class FakeCursor:
        description=[(name,) for name in columns]

        def fetchall(self):
            return [row]

    class FakeConnection:
        def __init__(self):
            self.sql=""
            self.params=[]

        def execute(self, sql, params=None):
            self.sql=sql
            self.params=list(params or [])
            return FakeCursor()

    connection=FakeConnection()
    monkeypatch.setattr(source,"_get_connection",lambda:connection)

    leads=source.search(
        "IT & Software",
        {
            "country":"United States",
            "region":"Texas",
            "city":"Austin",
            "bbox":[-98.0,30.0,-97.0,31.0],
            "_candidate_partition_count":8,
            "_candidate_partition":3,
        },
        limit=10,
    )

    assert len(leads)==1
    assert "(hash(id) % ?) = ?" in connection.sql
    assert connection.params[-3:]==[8,3,10]
