from __future__ import annotations
from dataclasses import dataclass
from .models import Lead
from .normalize import business_location_key,normalize_domain,normalize_name,normalize_phone,unique_key

@dataclass(frozen=True)
class Fingerprints:
    place_id: str
    source_id: str
    domain: str
    phone_name: str
    business_location: str
    unique: str

def fingerprints(lead: Lead) -> Fingerprints:
    phone=normalize_phone(lead.phone,lead.country)
    domain=normalize_domain(lead.website)
    place_id=lead.google_place_id.strip().lower()
    source_id=lead.source_id.strip().lower()
    phone_name=f"{phone}|{normalize_name(lead.business_name)}" if phone else ""
    bizloc=business_location_key(lead.business_name,lead.city,lead.region)
    return Fingerprints(place_id,source_id,domain,phone_name,bizloc,unique_key(place_id,domain,phone,lead.business_name,lead.city,lead.region))

def is_duplicate(fp: Fingerprints, existing: dict[str,set[str]]) -> bool:
    return any([
        bool(fp.place_id and fp.place_id in existing.get("place_id",set())),
        bool(fp.source_id and fp.source_id in existing.get("source_id",set())),
        bool(fp.domain and fp.domain in existing.get("domain",set())),
        bool(fp.phone_name and fp.phone_name in existing.get("phone_name",set())),
        bool(fp.business_location and fp.business_location in existing.get("business_location",set())),
        bool(fp.unique and fp.unique in existing.get("unique",set())),
    ])
