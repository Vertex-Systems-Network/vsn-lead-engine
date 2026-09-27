from vsn_lead_engine.sheets import count_current_rows


def test_count_current_rows_excludes_needs_review():
    dates=[["2026-09-27"],["2026-09-27"],["2026-09-26"],["2026-09-27"]]
    statuses=[["New"],["Needs Review"],["New"],[]]
    assert count_current_rows(dates,statuses,"2026-09-27")==2


def test_count_current_rows_handles_sparse_status_column():
    dates=[["2026-09-27"],["2026-09-27"]]
    statuses=[]
    assert count_current_rows(dates,statuses,"2026-09-27")==2
