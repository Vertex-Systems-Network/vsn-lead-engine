from __future__ import annotations

import re
from urllib.parse import quote_plus

import duckdb
import requests

from ..models import Lead

CATEGORY_PATTERNS: dict[str, str] = {
    "AI & Automation": r"artificial_intelligence|artificial intelligence|automation|robotic|machine_learning|machine learning|ai_consult|ai consulting",
    "Medical & Clinics": r"health_care|medical|clinic|doctor|physician|dentist|dental|hospital|chiropract|optometr|therapy|pharmacy",
    "Property & Real Estate": r"real_estate|real estate|estate_agent|property_management|property management|realty|realtor",
    "Business & Consulting": r"consult|business_service|management_service|professional_service|accounting|bookkeeping|legal_service|lawyer|attorney",
    "IT & Software": r"software|computer|information_technology|information technology|it_service|web_development|web development|technology_service|electronics_repair",
    "Media & Creative": r"advertis|marketing|graphic_design|graphic design|media|photograph|video_production|video production|creative|public_relations|printing",
    "Other Website-Critical": r"architect|contractor|construction|plumb|electric|roof|hvac|landscap|lawyer|accounting|fitness|education|home_service",
    "Spa": r"spa|massage|wellness",
    "Salon": r"salon|hairdresser|hair_salon|barber|nail|beauty",
    "Cars": r"automotive|car_dealer|car dealer|car_repair|car repair|auto_repair|vehicle_repair|tire|tyre",
    "Motorbikes": r"motorcycle|motorbike|scooter_dealer|motorcycle_repair",
    "Insurance": r"insurance",
}

COUNTRY_CODES = {
    "United States": "US",
    "Canada": "CA",
}


class OverturePlaceSource:
    name = "Overture Maps Places"

    def __init__(
        self,
        *,
        release: str = "latest",
        stac_url: str = "https://stac.overturemaps.org/catalog.json",
        candidate_limit: int = 500,
    ):
        self.release = release
        self.stac_url = stac_url
        self.candidate_limit = candidate_limit
        self._resolved_release: str | None = None

    def _resolve_release(self) -> str:
        if self._resolved_release:
            return self._resolved_release
        if self.release and self.release != "latest":
            candidate = self.release
        else:
            response = requests.get(
                self.stac_url,
                timeout=20,
                headers={"User-Agent": "VSN-Lead-Engine/0.2"},
            )
            response.raise_for_status()
            payload = response.json()
            candidate = payload.get("latest")
            if isinstance(candidate, dict):
                candidate = candidate.get("id") or candidate.get("release")
        if not isinstance(candidate, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", candidate):
            raise RuntimeError(f"Invalid Overture release identifier: {candidate!r}")
        self._resolved_release = candidate
        return candidate

    @staticmethod
    def _social_fields(socials) -> dict[str, str]:
        result = {
            "instagram": "",
            "facebook": "",
            "linkedin": "",
            "twitter": "",
            "tiktok": "",
        }
        for raw in socials or []:
            url = str(raw)
            low = url.lower()
            if "instagram.com" in low and not result["instagram"]:
                result["instagram"] = url
            elif "facebook.com" in low and not result["facebook"]:
                result["facebook"] = url
            elif "linkedin.com" in low and not result["linkedin"]:
                result["linkedin"] = url
            elif ("twitter.com" in low or "x.com" in low) and not result["twitter"]:
                result["twitter"] = url
            elif "tiktok.com" in low and not result["tiktok"]:
                result["tiktok"] = url
        return result

    @staticmethod
    def _maps_url(name: str, address: str, city: str, region: str) -> str:
        query = ", ".join(p for p in [name, address, city, region] if p)
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}" if query else ""

    def search(self, category: str, location: dict, limit: int | None = None) -> list[Lead]:
        pattern = CATEGORY_PATTERNS.get(category)
        bbox = location.get("bbox")
        if not pattern or not isinstance(bbox, list) or len(bbox) != 4:
            return []

        xmin, ymin, xmax, ymax = [float(v) for v in bbox]
        row_limit = max(1, min(int(limit or self.candidate_limit), self.candidate_limit))
        release = self._resolve_release()
        path = (
            f"s3://overturemaps-us-west-2/release/{release}/"
            "theme=places/type=place/*"
        )

        # Pattern is repository-controlled, not user input.
        sql = f"""
        SELECT
            id,
            names.primary AS name,
            basic_category,
            taxonomy.primary AS taxonomy_primary,
            taxonomy.hierarchy AS taxonomy_hierarchy,
            phones[1] AS phone,
            websites[1] AS website,
            emails[1] AS email,
            socials,
            addresses[1].freeform AS address,
            addresses[1].locality AS locality,
            addresses[1].region AS address_region,
            addresses[1].postcode AS postcode,
            addresses[1].country AS address_country,
            bbox.xmin AS longitude,
            bbox.ymin AS latitude,
            confidence,
            sources[1].dataset AS source_dataset
        FROM read_parquet(
            '{path}',
            filename=true,
            hive_partitioning=1
        )
        WHERE
            bbox.xmin BETWEEN ? AND ?
            AND bbox.ymin BETWEEN ? AND ?
            AND phones IS NOT NULL
            AND len(phones) > 0
            AND names.primary IS NOT NULL
            AND (
                operating_status IS NULL
                OR CAST(operating_status AS VARCHAR) <> 'permanently_closed'
            )
            AND (
                regexp_matches(lower(coalesce(taxonomy.primary, '')), '{pattern}')
                OR regexp_matches(lower(coalesce(CAST(taxonomy.hierarchy AS VARCHAR), '')), '{pattern}')
                OR regexp_matches(lower(coalesce(basic_category, '')), '{pattern}')
                OR regexp_matches(lower(coalesce(names.primary, '')), '{pattern}')
            )
        LIMIT ?
        """

        connection = duckdb.connect(database=":memory:")
        try:
            connection.execute("INSTALL httpfs")
            connection.execute("LOAD httpfs")
            connection.execute("SET s3_region='us-west-2'")
            cursor = connection.execute(sql, [xmin, xmax, ymin, ymax, row_limit])
            columns = [item[0] for item in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

        expected_country = COUNTRY_CODES.get(location.get("country", ""))
        leads: list[Lead] = []
        for record in records:
            address_country = str(record.get("address_country") or "").upper()
            if expected_country and address_country and address_country != expected_country:
                continue

            name = str(record.get("name") or "").strip()
            phone = str(record.get("phone") or "").strip()
            if not name or not phone:
                continue

            socials = self._social_fields(record.get("socials"))
            address = str(record.get("address") or "").strip()
            city = str(record.get("locality") or location.get("city") or "").strip()
            region = str(record.get("address_region") or location.get("region") or "").strip()
            overture_id = str(record.get("id") or "").strip()
            dataset = str(record.get("source_dataset") or "Overture").strip()
            taxonomy = str(record.get("taxonomy_primary") or record.get("basic_category") or "").strip()

            leads.append(
                Lead(
                    country=location["country"],
                    category=category,
                    business_name=name,
                    phone=phone,
                    city=city,
                    region=region,
                    source=self.name,
                    source_id=f"overture:{overture_id}",
                    street_address=address,
                    postal_code=str(record.get("postcode") or ""),
                    latitude=float(record["latitude"]) if record.get("latitude") is not None else None,
                    longitude=float(record["longitude"]) if record.get("longitude") is not None else None,
                    website=str(record.get("website") or ""),
                    email=str(record.get("email") or ""),
                    source_url="https://explore.overturemaps.org/",
                    instagram=socials["instagram"],
                    facebook=socials["facebook"],
                    linkedin=socials["linkedin"],
                    twitter=socials["twitter"],
                    tiktok=socials["tiktok"],
                    google_maps_url=self._maps_url(name, address, city, region),
                    notes=(
                        f"Overture Maps Foundation Places; release {release}; "
                        f"provider dataset {dataset}; taxonomy {taxonomy}"
                    ),
                )
            )
        return leads
