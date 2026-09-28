from vsn_lead_engine.taxonomy_audit import (
    select_balanced_geographies,
    summarize_taxonomy_rows,
)


def test_select_balanced_geographies_interleaves_countries():
    geographies=[
        {"country":"United States","region":"A","city":"US1"},
        {"country":"United States","region":"B","city":"US2"},
        {"country":"Canada","region":"C","city":"CA1"},
        {"country":"Canada","region":"D","city":"CA2"},
    ]

    selected=select_balanced_geographies(geographies,4)

    assert [item["city"] for item in selected]==[
        "US1","CA1","US2","CA2",
    ]


def test_taxonomy_summary_exposes_recognized_and_gap_counts_without_names():
    rows=[
        {
            "taxonomy_primary":"motorcycle_dealer",
            "basic_category":"motorcycle_dealer",
            "taxonomy_hierarchy":["shopping","motorcycle_dealer"],
            "name":"Example Moto",
            "phone":"+12025550100",
            "website":"https://example.test",
            "name_match":True,
            "taxonomy_match":True,
            "_country":"United States",
            "_metro":"Austin, Texas",
        },
        {
            "taxonomy_primary":"powersports_dealer",
            "basic_category":"vehicle_dealer",
            "taxonomy_hierarchy":["shopping","vehicle_dealer","powersports_dealer"],
            "name":"Example Powersports",
            "phone":"+12025550101",
            "website":"",
            "name_match":True,
            "taxonomy_match":True,
            "_country":"Canada",
            "_metro":"Toronto, Ontario",
        },
    ]

    summary=summarize_taxonomy_rows(rows)

    assert summary[0]["with_phone"]==1
    assert sum(item["recognized_by_current_rule"] for item in summary)==1
    assert sum(item["unrecognized_by_current_rule"] for item in summary)==1
    assert all("name" not in item for item in summary)
