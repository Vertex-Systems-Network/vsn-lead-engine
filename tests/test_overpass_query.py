from vsn_lead_engine.sources.overpass import escape_overpass_string


def test_overpass_string_escape_neutralises_quotes_backslashes_and_newlines():
    assert escape_overpass_string('St. John"s') == 'St. John\\"s'
    assert escape_overpass_string("a\\b") == "a\\\\b"
    assert escape_overpass_string('x\\"];out;') == 'x\\\\\\"];out;'
    assert escape_overpass_string("a\nb") == "a\\nb"
