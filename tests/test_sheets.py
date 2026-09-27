from vsn_lead_engine.sheets import (
    GoogleSheetsStore,
    count_current_countries,
    count_current_rows,
    daily_workbook_title,
    escape_drive_query_value,
    registry_status_blocks_dedupe,
)


def test_count_current_rows_excludes_needs_review():
    dates=[["2026-09-27"],["2026-09-27"],["2026-09-26"],["2026-09-27"]]
    statuses=[["New"],["Needs Review"],["New"],[]]
    assert count_current_rows(dates,statuses,"2026-09-27")==2


def test_count_current_rows_handles_sparse_status_column():
    dates=[["2026-09-27"],["2026-09-27"]]
    statuses=[]
    assert count_current_rows(dates,statuses,"2026-09-27")==2


def test_registry_active_and_pending_rows_block_dedupe():
    assert registry_status_blocks_dedupe("Active")
    assert registry_status_blocks_dedupe("PendingDaily")
    assert registry_status_blocks_dedupe("")


def test_registry_quarantine_rows_do_not_block_dedupe():
    assert not registry_status_blocks_dedupe("NeedsReview")
    assert not registry_status_blocks_dedupe("Needs Review")
    assert not registry_status_blocks_dedupe("Rejected")
    assert not registry_status_blocks_dedupe("Invalid")


def test_count_current_countries_excludes_quarantine_and_other_dates():
    date_country_rows=[
        ["2026-09-27","United States"],
        ["2026-09-27","Canada"],
        ["2026-09-27","Canada"],
        ["2026-09-26","Canada"],
    ]
    statuses=[["New"],["New"],["Needs Review"],["New"]]
    assert count_current_countries(date_country_rows,statuses,"2026-09-27")=={
        "United States":1,
        "Canada":1,
    }


def test_daily_workbook_title_uses_exact_requested_format():
    assert daily_workbook_title(
        "US + Canada Business Leads — ","2026-09-24"
    )=="US + Canada Business Leads — 2026-09-24"


def test_drive_query_escaping_is_safe_for_quotes_and_backslashes():
    assert escape_drive_query_value("A'B\\C")=="A\\'B\\\\C"


def test_daily_overview_uses_fixed_workbook_date_not_today_formula():
    store=object.__new__(GoogleSheetsStore)
    store.config={
        "runtime":{"daily_target_per_category":1000},
        "categories":["Category 1","Category 2"],
    }
    rows=store._overview_seed("2026-09-27")
    assert rows[2]==["Tracking Date","2026-09-27"]
    assert "$B$3" in rows[6][1]
    assert "TODAY()" not in rows[6][1]
