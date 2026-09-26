from vsn_lead_engine.normalize import business_location_key,normalize_domain,normalize_phone

def test_domain_normalization():
    assert normalize_domain("https://www.Example.com/path")=="example.com"

def test_us_phone_normalization():
    assert normalize_phone("(212) 555-1212","United States")=="+12125551212"

def test_canada_phone_normalization():
    assert normalize_phone("416-555-1212","Canada")=="+14165551212"

def test_business_location_key():
    assert business_location_key("Acme, Inc.","Seattle","Washington")=="acme inc|seattle|washington"
