from vsn_lead_engine.dedupe import fingerprints,is_duplicate
from vsn_lead_engine.models import Lead

def make_lead(**changes):
    data=dict(country="United States",category="IT & Software",business_name="Acme IT",phone="+1 212-555-1212",city="Seattle",region="Washington",source="OpenStreetMap/Overpass",source_id="osm:node/123",website="https://acme.example")
    data.update(changes)
    return Lead(**data)

def test_source_id_dedupe():
    fp=fingerprints(make_lead())
    existing={"source_id":{fp.source_id},"domain":set(),"phone_name":set(),"business_location":set(),"unique":set()}
    assert is_duplicate(fp,existing)

def test_domain_dedupe():
    fp=fingerprints(make_lead())
    existing={"source_id":set(),"domain":{fp.domain},"phone_name":set(),"business_location":set(),"unique":set()}
    assert is_duplicate(fp,existing)
