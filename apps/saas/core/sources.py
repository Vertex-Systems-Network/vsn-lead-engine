"""Lead source adapters for job fulfilment.

Every adapter implements ``fetch(search, limit, is_new=None)`` and returns plain
lead dicts (source_id, country, category, business_name, phone, city, region,
address, optional website). ``is_new`` lets a source keep looking past leads the
workspace already has instead of returning the same first page every time.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from lead_saas.local_fulfilment import OVERTURE
from lead_saas.local_fulfilment import SOURCE_CODE as LOCAL_FIXTURE

CITIES = {
    "US": [("Austin", "TX"), ("Denver", "CO"), ("Columbus", "OH"), ("Raleigh", "NC")],
    "CA": [("Toronto", "ON"), ("Calgary", "AB"), ("Ottawa", "ON"), ("Halifax", "NS")],
}
POOL_SIZE = 40


class FixtureSource:
    """Synthetic but well-formed NANP businesses, stable per country and category.

    The same search always yields the same pool, so a repeated job in one
    workspace exercises cross-job dedupe instead of inventing new leads.
    """

    code = LOCAL_FIXTURE

    def fetch(self, search, limit, is_new=None):
        leads = []
        for country in search["countries"]:
            for category in search["categories"]:
                for index in range(POOL_SIZE):
                    leads.append(self._lead(country, category, index))
        leads.sort(key=lambda lead: lead["source_id"])
        if is_new is not None:
            leads = [lead for lead in leads if is_new(lead)]
        return leads[: max(0, limit) * 4]

    @staticmethod
    def _lead(country, category, index):
        digest = hashlib.sha256(f"{country}|{category}|{index}".encode()).hexdigest()
        number = int(digest[:12], 16)
        area = 200 + number % 800
        exchange = 200 + (number // 800) % 800
        line = (number // 640000) % 10000
        city, region = CITIES[country][index % len(CITIES[country])]
        name = f"{category.title()} {city} {index + 1:02d}"
        lead = {
            "source_id": f"fx-{digest[:20]}",
            "country": country,
            "category": category,
            "business_name": name,
            "phone": f"+1{area:03d}{exchange:03d}{line:04d}",
            "city": city,
            "region": region,
            "address": f"{100 + index} Main St, {city}, {region}",
        }
        if index % 3:
            lead["website"] = f"https://{digest[:10]}.example.com"
        return lead


COUNTRY_NAMES = {"US": "United States", "CA": "Canada"}
REPO_ROOT = Path(__file__).resolve().parents[3]


def nanp_e164(raw):
    """+1NXXNXXXXXX for a well-formed US/Canada number, else empty."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if not re.fullmatch(r"[2-9][0-9]{2}[2-9][0-9]{6}", digits):
        return ""
    return "+1" + digits


def geographies(country):
    """Collector geographies (city + bbox) for one ISO country code."""
    path = Path(os.environ.get("VSN_RUNTIME_CONFIG", REPO_ROOT / "config" / "runtime.json"))
    if not path.is_absolute():
        path = REPO_ROOT / path
    name = COUNTRY_NAMES[country]
    return [g for g in json.loads(path.read_text())["geographies"] if g.get("country") == name]


class OvertureSource:
    """Overture Maps Places through the production collector's query code.

    Imported lazily: the worker needs ``requirements-runtime.txt`` (duckdb) and
    outbound access to the Overture STAC catalog and public S3 release, while the
    web app and its CI do not.
    """

    code = OVERTURE
    MAX_QUERIES = 6

    def __init__(self, place_source=None, geographies_for=geographies):
        self._place_source = place_source
        self._geographies_for = geographies_for

    def _source(self, limit):
        if self._place_source is not None:
            return self._place_source
        from vsn_lead_engine.sources.overture import OverturePlaceSource

        return OverturePlaceSource(candidate_limit=max(50, limit * 4), query_timeout_seconds=45)

    def fetch(self, search, limit, is_new=None):
        want = max(0, limit) * 2
        source = self._source(limit)
        leads, seen, queries = [], set(), 0
        try:
            for country in search["countries"]:
                for category in search["categories"]:
                    for geography in self._geographies_for(country):
                        if len(leads) >= want or queries >= self.MAX_QUERIES:
                            return leads
                        queries += 1
                        for place in source.search(category, geography, limit=max(50, limit * 4)):
                            lead = self._lead(country, category, place)
                            if lead is None or lead["source_id"] in seen:
                                continue
                            if is_new is not None and not is_new(lead):
                                continue
                            seen.add(lead["source_id"])
                            leads.append(lead)
            return leads
        finally:
            if self._place_source is None:
                source.close()

    @staticmethod
    def _lead(country, category, place):
        phone = nanp_e164(place.phone)
        ref = re.sub(r"[^A-Za-z0-9._:-]", "", f"ov-{place.source_id}")[:96]
        if not phone or not place.business_name.strip() or ref == "ov-":
            return None
        lead = {
            "source_id": ref,
            "country": country,
            "category": category,
            "business_name": place.business_name.strip()[:300],
            "phone": phone,
            "city": (place.city or "").strip()[:200],
            "region": (place.region or "").strip()[:200],
            "address": (place.street_address or "").strip()[:500],
        }
        if place.website:
            lead["website"] = place.website.strip()[:500]
        return {key: value for key, value in lead.items() if value}


ADAPTERS = {LOCAL_FIXTURE: FixtureSource, OVERTURE: OvertureSource}


def adapter_for(source_code):
    adapter = ADAPTERS.get(source_code)
    return adapter() if adapter else None
