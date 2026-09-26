from __future__ import annotations

import re
from urllib.parse import urlparse
import phonenumbers

def normalize_domain(url: str) -> str:
    if not url:
        return ""
    value=url.strip()
    if "://" not in value:
        value="https://"+value
    try:
        host=(urlparse(value).hostname or "").lower().strip(".")
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host

def normalize_phone(phone: str, country: str) -> str:
    if not phone:
        return ""
    region="US" if country=="United States" else "CA" if country=="Canada" else None
    try:
        parsed=phonenumbers.parse(phone, region)
    except phonenumbers.NumberParseException:
        return ""
    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        return ""
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

def normalize_name(name: str) -> str:
    value=re.sub(r"[^a-z0-9]+"," ",(name or "").lower()).strip()
    return re.sub(r"\s+"," ",value)

def business_location_key(name: str, city: str, region: str) -> str:
    return "|".join([normalize_name(name),normalize_name(city),normalize_name(region)])

def unique_key(source_id: str, domain: str, phone: str, name: str, city: str, region: str) -> str:
    if source_id:
        return f"source:{source_id.lower()}"
    if domain:
        return f"domain:{domain.lower()}"
    if phone:
        return f"phone-name:{phone}|{normalize_name(name)}"
    return f"bizloc:{business_location_key(name,city,region)}"
