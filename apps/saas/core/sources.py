"""Lead source adapters for job fulfilment.

Only the deterministic local fixture source exists today. Real sources (the
collector's Overture adapter) plug in through ``adapter_for`` with the same
``fetch(search, limit)`` contract.
"""

import hashlib

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

    def fetch(self, search, limit):
        leads = []
        for country in search["countries"]:
            for category in search["categories"]:
                for index in range(POOL_SIZE):
                    leads.append(self._lead(country, category, index))
        leads.sort(key=lambda lead: lead["source_id"])
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


ADAPTERS = {LOCAL_FIXTURE: FixtureSource}


def adapter_for(source_code):
    adapter = ADAPTERS.get(source_code)
    return adapter() if adapter else None
