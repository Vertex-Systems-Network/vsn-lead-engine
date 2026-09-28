from vsn_lead_engine.sheets import (
    GoogleSheetsStore,
    OVERVIEW_INCREMENT_METRICS,
    OVERVIEW_LATEST_METRICS,
    count_current_countries,
    count_current_rows,
    daily_workbook_title,
    escape_drive_query_value,
    extract_spreadsheet_id,
    pending_recovery_status,
    registry_status_blocks_dedupe,
    overview_schema_is_current,
    category_tabs_are_blank,
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
    assert not registry_status_blocks_dedupe("Retryable")
    assert not registry_status_blocks_dedupe("WriteFailed")


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


def test_extract_spreadsheet_id_from_registry_url():
    assert extract_spreadsheet_id(
        "https://docs.google.com/spreadsheets/d/abc_DEF-123/edit"
    )=="abc_DEF-123"


def test_pending_recovery_promotes_only_written_unique_key():
    present={"domain:example.com","phone-name:+12025550123|example"}
    assert pending_recovery_status("domain:example.com",present)=="Active"
    assert pending_recovery_status("domain:missing.example",present)=="Retryable"
    assert pending_recovery_status("",present)=="Retryable"


def test_store_run_date_is_frozen_for_the_run():
    store=object.__new__(GoogleSheetsStore)
    store.run_date="2026-09-27"
    assert store._today()=="2026-09-27"


def test_overview_schema_includes_quality_observability_metrics():
    expected_incremental={
        "Accepted Leads",
        "Source-Batch Duplicates",
        "Remote Prefilter Duplicates",
        "Source Phone Candidates",
        "Website-Only Candidates",
        "Phones Recovered",
        "Enrichment Candidates",
        "Official-Site Phone Recoveries",
        "Common-Crawl Phone Recoveries",
        "Common Crawl Attempts",
        "Enrichment Budget Skips",
        "Enrichment Errors",
        "Zero-Progress Cycles",
    }
    assert expected_incremental.issubset(set(OVERVIEW_INCREMENT_METRICS))
    assert set(OVERVIEW_LATEST_METRICS)=={
        "Last Acceptance Rate %",
        "Last Phone Recovery Rate %",
        "Last Partitions Visited",
    }


def test_daily_overview_seed_contains_quality_metrics():
    store=object.__new__(GoogleSheetsStore)
    store.config={
        "runtime":{"daily_target_per_category":1000},
        "categories":["Category 1","Category 2"],
    }
    rows=store._overview_seed("2026-09-27")
    names={row[0] for row in rows if row}
    assert "Phones Recovered" in names
    assert "Accepted Leads" in names
    assert "Source-Batch Duplicates" in names
    assert "Remote Prefilter Duplicates" in names
    assert "Source Phone Candidates" in names
    assert "Website-Only Candidates" in names
    assert "Enrichment Candidates" in names
    assert "Last Acceptance Rate %" in names


def test_overview_schema_current_requires_sentinel_and_matching_tracking_date():
    assert overview_schema_is_current(
        [
            ["VSN Lead Engine — Daily US + Canada Workbook",""],
            ["Metric","Value"],
            ["Tracking Date","2026-09-28"],
        ],
        "2026-09-28",
    )
    assert not overview_schema_is_current(
        [
            ["Metric","Value"],
            ["Date","2026-09-28"],
        ],
        "2026-09-28",
    )
    assert not overview_schema_is_current(
        [
            ["VSN Lead Engine — Daily US + Canada Workbook",""],
            ["Metric","Value"],
            ["Tracking Date","2026-09-27"],
        ],
        "2026-09-28",
    )


def test_category_tabs_are_blank_only_when_all_value_ranges_have_no_data():
    assert category_tabs_are_blank([
        {"values":[]},
        {"values":[[]]},
    ])
    assert not category_tabs_are_blank([
        {"values":[]},
        {"values":[["2026-09-28"]]},
    ])


class _ExecResult:
    def __init__(self,payload):
        self.payload=payload

    def execute(self,**_kwargs):
        return self.payload


class _BootstrapValues:
    def __init__(self,overview,value_ranges):
        self.overview=overview
        self.value_ranges=value_ranges
        self.batch_get_calls=0
        self.clear_ranges=[]
        self.update_ranges=[]

    def get(self,**_kwargs):
        return _ExecResult({"values":self.overview})

    def batchGet(self,**_kwargs):
        self.batch_get_calls+=1
        return _ExecResult({"valueRanges":self.value_ranges})

    def clear(self,**kwargs):
        self.clear_ranges.append(kwargs.get("range"))
        return _ExecResult({})

    def update(self,**kwargs):
        self.update_ranges.append(kwargs.get("range"))
        return _ExecResult({})


class _BootstrapSpreadsheets:
    def __init__(self,values):
        self._values=values

    def values(self):
        return self._values


class _BootstrapSheetsService:
    def __init__(self,values):
        self._spreadsheets=_BootstrapSpreadsheets(values)

    def spreadsheets(self):
        return self._spreadsheets


def _bootstrap_store(overview,value_ranges):
    store=object.__new__(GoogleSheetsStore)
    store.run_date="2026-09-28"
    store.api_retries=0
    store.config={
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
        },
        "categories":["A","B"],
    }
    values=_BootstrapValues(overview,value_ranges)
    store.sheets=_BootstrapSheetsService(values)
    return store,values


def test_precreated_blank_stale_workbook_requires_full_bootstrap():
    store,values=_bootstrap_store(
        [["Metric","Value"],["Date","2026-09-26"]],
        [{"values":[]},{"values":[]}],
    )
    assert store._precreated_workbook_state("sheet123")=="blank-stale"
    assert values.batch_get_calls==1


def test_precreated_populated_stale_workbook_uses_overview_only_upgrade():
    store,values=_bootstrap_store(
        [["Metric","Value"],["Date","2026-09-26"]],
        [{"values":[["2026-09-28"]]},{"values":[]}],
    )
    assert store._precreated_workbook_state("sheet123")=="populated-stale"
    assert values.batch_get_calls==1


def test_current_schema_skips_category_scan():
    store,values=_bootstrap_store(
        [
            ["VSN Lead Engine — Daily US + Canada Workbook",""],
            ["Metric","Value"],
            ["Tracking Date","2026-09-28"],
        ],
        [{"values":[["should-not-be-read"]]}],
    )
    assert store._precreated_workbook_state("sheet123")=="current"
    assert values.batch_get_calls==0


def test_populated_overview_upgrade_never_clears_category_ranges():
    store,values=_bootstrap_store(
        [
            ["Metric","Value"],
            ["Duplicate Rejections",12],
            ["Source Phone Candidates",34],
        ],
        [{"values":[["2026-09-28"]]},{"values":[]}],
    )
    captured={}
    store.set_overview_metrics=lambda _sid,preserved: captured.update(preserved)

    store._upgrade_overview_only("sheet123")

    assert values.clear_ranges==["'Overview'!A:B"]
    assert values.update_ranges==["'Overview'!A1"]
    assert captured["Duplicate Rejections"]==12
    assert captured["Source Phone Candidates"]==34


class _SnapshotValues:
    def __init__(self,value_ranges):
        self.value_ranges=value_ranges
        self.batch_get_calls=0
        self.last_ranges=[]

    def batchGet(self,**kwargs):
        self.batch_get_calls+=1
        self.last_ranges=list(kwargs.get("ranges",[]))
        return _ExecResult({"valueRanges":self.value_ranges})


def test_daily_state_snapshot_combines_category_and_country_counts_in_one_batch():
    store=object.__new__(GoogleSheetsStore)
    store.run_date="2026-09-28"
    store.api_retries=0
    store.config={
        "runtime":{"timezone":"Asia/Karachi"},
        "categories":["A","B"],
    }
    values=_SnapshotValues([
        {
            "values":[
                ["2026-09-28","United States"],
                ["2026-09-28","Canada"],
                ["2026-09-27","Canada"],
            ]
        },
        {"values":[["New"],["Needs Review"],["New"]]},
        {
            "values":[
                ["2026-09-28","Canada"],
                ["2026-09-28","United States"],
            ]
        },
        {"values":[["New"],["New"]]},
    ])
    store.sheets=_BootstrapSheetsService(values)

    snapshot=store.daily_state_snapshot("sheet123")

    assert values.batch_get_calls==1
    assert values.last_ranges==[
        "'A'!A2:B","'A'!AA2:AA",
        "'B'!A2:B","'B'!AA2:AA",
    ]
    assert snapshot["category_counts"]=={"A":1,"B":2}
    assert snapshot["country_counts"]=={
        "United States":2,
        "Canada":1,
    }


def test_daily_state_snapshot_keeps_zero_countries_when_no_rows_exist():
    store=object.__new__(GoogleSheetsStore)
    store.run_date="2026-09-28"
    store.api_retries=0
    store.config={
        "runtime":{"timezone":"Asia/Karachi"},
        "categories":["A"],
    }
    values=_SnapshotValues([
        {"values":[]},
        {"values":[]},
    ])
    store.sheets=_BootstrapSheetsService(values)

    snapshot=store.daily_state_snapshot("sheet123")

    assert snapshot["category_counts"]=={"A":0}
    assert snapshot["country_counts"]=={
        "United States":0,
        "Canada":0,
    }
