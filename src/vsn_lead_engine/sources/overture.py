from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from urllib.parse import quote_plus

import duckdb
import requests

from ..models import Lead


@dataclass(frozen=True)
class CategoryRule:
    taxonomy_pattern: str
    name_fallback_pattern: str = ""


# Taxonomy-first classification.
#
# Patterns are matched against complete taxonomy tokens (primary, basic and
# hierarchy entries), not arbitrary substrings. A name fallback is allowed only
# when Overture has no taxonomy at all for the place and only for distinctive
# business terms.
CATEGORY_RULES: dict[str, CategoryRule] = {
    "AI & Automation": CategoryRule(
        r"(?:automation_service|home_automation|information_technology_company|"
        r"software_development|software_company|robotics_company|"
        r"artificial_intelligence_company|machine_learning_company)"
    ),
    "Medical & Clinics": CategoryRule(
        r"(?:health_care|medical_center|medical_clinic|.*_clinic|doctors_office|"
        r".*_doctor|physician|dentist|dental_clinic|hospital|pharmacy|"
        r"chiropractor|optometrist|physical_therapist|dermatology|pediatrician|"
        r"urgent_care|mental_health_clinic)",
        r"\b(?:medical|clinic|dental|dentist|doctor|physician|hospital|pharmacy|"
        r"chiropractic|optometry|dermatology|urgent care)\b",
    ),
    "Property & Real Estate": CategoryRule(
        r"(?:real_estate_agency|real_estate_agent|commercial_real_estate_agency|"
        r"property_management|property_management_company|real_estate_developer|"
        r"apartment_rental_agency|real_estate_consultant)",
        r"\b(?:real estate|realty|realtor|property management)\b",
    ),
    "Business & Consulting": CategoryRule(
        r"(?:business_management_consultant|management_consultant|"
        r"business_consultant|consulting_service|accounting_firm|"
        r"bookkeeping_service|law_firm|legal_service)",
        r"\b(?:business consulting|management consulting|consultants?)\b",
    ),
    "IT & Software": CategoryRule(
        r"(?:software_development|software_company|information_technology_company|"
        r"computer_support_and_services|computer_repair_service|computer_consultant|"
        r"it_consulting|web_designer|website_designer|electronics_repair)",
        r"\b(?:software|information technology|IT services?|web development|"
        r"website design|computer support)\b",
    ),
    "Media & Creative": CategoryRule(
        r"(?:marketing_agency|advertising_agency|graphic_designer|"
        r"video_production_service|photographer|photography_service|"
        r"public_relations_firm|printing_service|media_company|creative_agency)",
        r"\b(?:marketing agency|advertising agency|graphic design|"
        r"video production|public relations|creative agency)\b",
    ),
    "Other Website-Critical": CategoryRule(
        r"(?:architect|architecture_firm|general_contractor|construction_company|"
        r"plumber|plumbing_service|electrician|electrical_service|roofing_contractor|"
        r"hvac_contractor|landscaper|landscaping_service|fitness_center|"
        r"education_center|home_service)",
        r"\b(?:contractor|plumbing|electrician|roofing|hvac|landscaping|architect)\b",
    ),
    "Spa": CategoryRule(
        r"(?:spa|day_spa|medical_spa|massage_service|massage_therapist|"
        r"wellness_center|wellness_spa)",
        r"\b(?:day spa|medical spa|massage therapy|wellness spa)\b",
    ),
    "Salon": CategoryRule(
        r"(?:hair_salon|kids_hair_salon|beauty_salon|nail_salon|tanning_salon|"
        r"hair_stylist|barber_shop|barber|threading_service|eyebrow_bar|"
        r"waxing_service|waxing|beautician|eyelash_service|makeup_artist|"
        r"hair_extensions|hair_replacement|permanent_makeup|hair_removal|"
        r"laser_hair_removal|sugaring|blow_dry_blow_out_service|spray_tanning|"
        r"skin_care_and_makeup|personal_or_beauty_service)",
        r"\b(?:hair salon|nail salon|beauty salon|barber shop|hair stylist|"
        r"threading service|eyebrow bar)\b",
    ),
    "Cars": CategoryRule(
        r"(?:automotive_repair|auto_repair|auto_glass_service|auto_body_shop|"
        r"automobile_registration_service|vehicle_inspection|car_inspection|"
        r"car_dealer|auto_dealer|used_car_dealer|used_auto_dealer|car_rental|"
        r"car_wash|auto_parts_store|automotive_service|tire_dealer_and_repair|"
        r"tire_shop|towing_service|auto_detailing|truck_repair|"
        r"auto_restoration_service|auto_customization|transmission_repair|"
        r"brake_service_and_repair|oil_change_station|auto_electrical_repair|"
        r"engine_repair_service|wheel_and_rim_repair|car_window_tinting|"
        r"windshield_installation_and_repair)",
        r"\b(?:auto repair|automotive repair|car dealer|used cars?|tire shop|"
        r"tyre shop|towing service|auto body|car wash)\b",
    ),
    "Motorbikes": CategoryRule(
        r"(?:motorcycle_repair|motorcycle_dealer|motorcycle_manufacturer|"
        r"motorcycle_rental|motorcycle_rental_service|motorcycle_parts_store|"
        r"scooter_dealer|scooter_rental)",
        r"\b(?:motorcycle|motorbike|motor cycle|powersports)\b",
    ),
    "Insurance": CategoryRule(
        r"(?:insurance_agency|insurance_company|insurance_broker|insurance_service|"
        r"auto_insurance|life_insurance|health_insurance|property_insurance)",
        r"\b(?:insurance|medicare insurance|assurance agency)\b",
    ),
}

# Backward-compatible export used by earlier tests/integrations. These patterns
# now represent complete taxonomy tokens rather than loose substring searches.
CATEGORY_PATTERNS: dict[str, str] = {
    category: rule.taxonomy_pattern for category, rule in CATEGORY_RULES.items()
}

COUNTRY_CODES = {
    "United States": "US",
    "Canada": "CA",
}


class OvertureQueryTimeout(TimeoutError):
    """Raised when one remote DuckDB/httpfs Overture query exceeds its budget."""



def _taxonomy_tokens(primary: str = "", basic: str = "", hierarchy=None) -> list[str]:
    tokens: list[str] = []
    for raw in [primary, basic, *(hierarchy or [])]:
        value = str(raw or "").strip().lower()
        if value and value not in tokens:
            tokens.append(value)
    return tokens


def category_match_reason(
    category: str,
    *,
    primary: str = "",
    basic: str = "",
    hierarchy=None,
    name: str = "",
) -> str | None:
    rule = CATEGORY_RULES.get(category)
    if not rule:
        return None

    tokens = _taxonomy_tokens(primary, basic, hierarchy)
    taxonomy_re = re.compile(rf"^(?:{rule.taxonomy_pattern})$", re.IGNORECASE)
    for token in tokens:
        if taxonomy_re.fullmatch(token):
            return f"taxonomy:{token}"

    # A business-name fallback is intentionally allowed only when Overture
    # supplies no taxonomy token. This prevents a name like "Pet Salon" or
    # "BeautyAllure Dermatology" from overriding a conflicting taxonomy.
    if not tokens and rule.name_fallback_pattern:
        match = re.search(rule.name_fallback_pattern, name or "", re.IGNORECASE)
        if match:
            return f"name_fallback:{match.group(0).lower()}"

    return None


class OverturePlaceSource:
    name = "Overture Maps Places"

    def __init__(
        self,
        *,
        release: str = "latest",
        stac_url: str = "https://stac.overturemaps.org/catalog.json",
        candidate_limit: int = 500,
        website_candidate_reserve_fraction: float = 0.20,
        query_timeout_seconds: float = 45,
    ):
        self.release = release
        self.stac_url = stac_url
        self.candidate_limit = candidate_limit
        self.website_candidate_reserve_fraction = max(
            0.0,
            min(0.5, float(website_candidate_reserve_fraction)),
        )
        self.query_timeout_seconds=max(1.0,float(query_timeout_seconds))
        self._resolved_release: str | None = None
        self._connection = None

    def _get_connection(self):
        """Lazily create one DuckDB/httpfs connection per source instance."""
        if self._connection is None:
            connection = duckdb.connect(database=":memory:")
            connection.execute("INSTALL httpfs")
            connection.execute("LOAD httpfs")
            connection.execute("SET s3_region='us-west-2'")
            self._connection = connection
        return self._connection

    def close(self):
        connection = self._connection
        self._connection = None
        if connection is not None:
            connection.close()

    def _resolve_release(self) -> str:
        if self._resolved_release:
            return self._resolved_release
        if self.release and self.release != "latest":
            candidate = self.release
        else:
            response = requests.get(
                self.stac_url,
                timeout=20,
                headers={"User-Agent": "VSN-Lead-Engine/0.42"},
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

    @staticmethod
    def _contact_budgets(
        row_limit: int,
        website_reserve_fraction: float,
    ) -> tuple[int,int]:
        row_limit=max(1,int(row_limit))
        fraction=max(0.0,min(0.5,float(website_reserve_fraction)))
        if row_limit <= 1 or fraction <= 0:
            return row_limit,0
        website_budget=max(1,int(round(row_limit*fraction)))
        website_budget=min(row_limit-1,website_budget)
        return row_limit-website_budget,website_budget

    @staticmethod
    def _sql_category_clause(category: str) -> str:
        rule = CATEGORY_RULES[category]
        taxonomy_pattern = rule.taxonomy_pattern
        # taxonomy_blob is pipe-delimited so (^|\|) and (\||$) force whole
        # taxonomy-token matches. This prevents "tire" from matching
        # "retirement_home".
        taxonomy_clause = (
            "regexp_matches("
            "lower(concat_ws('|', coalesce(taxonomy.primary, ''), "
            "coalesce(basic_category, ''), "
            "coalesce(array_to_string(taxonomy.hierarchy, '|'), ''))), "
            f"'(^|\\|)(?:{taxonomy_pattern})(\\||$)'"
            ")"
        )
        if not rule.name_fallback_pattern:
            return taxonomy_clause

        fallback = rule.name_fallback_pattern.replace("'", "''")
        no_taxonomy = (
            "length(trim(replace(concat_ws('|', coalesce(taxonomy.primary, ''), "
            "coalesce(basic_category, ''), "
            "coalesce(array_to_string(taxonomy.hierarchy, '|'), '')), '|', ''))) = 0"
        )
        return (
            f"({taxonomy_clause} OR "
            f"({no_taxonomy} AND regexp_matches(lower(names.primary), '{fallback}')))"
        )

    def search(self, category: str, location: dict, limit: int | None = None) -> list[Lead]:
        rule = CATEGORY_RULES.get(category)
        bbox = location.get("bbox")
        if not rule or not isinstance(bbox, list) or len(bbox) != 4:
            return []

        xmin, ymin, xmax, ymax = [float(v) for v in bbox]
        row_limit = max(1, min(int(limit or self.candidate_limit), self.candidate_limit))
        phone_budget,website_budget=self._contact_budgets(
            row_limit,
            self.website_candidate_reserve_fraction,
        )
        partition_count=max(1,min(64,int(location.get("_candidate_partition_count",1))))
        partition=int(location.get("_candidate_partition",0)) % partition_count
        release = self._resolve_release()
        path = (
            f"s3://overturemaps-us-west-2/release/{release}/"
            "theme=places/type=place/*"
        )
        category_clause = self._sql_category_clause(category)
        partition_clause=(
            "AND (hash(id) % ?) = ?"
            if partition_count > 1
            else ""
        )

        sql = f"""
        WITH base AS (
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
                sources[1].dataset AS source_dataset,
                (phones IS NOT NULL AND len(phones) > 0) AS has_phone,
                (websites IS NOT NULL AND len(websites) > 0) AS has_website
            FROM read_parquet(
                '{path}',
                filename=true,
                hive_partitioning=1
            )
            WHERE
                bbox.xmin BETWEEN ? AND ?
                AND bbox.ymin BETWEEN ? AND ?
                {partition_clause}
                AND (
                    (phones IS NOT NULL AND len(phones) > 0)
                    OR (websites IS NOT NULL AND len(websites) > 0)
                )
                AND names.primary IS NOT NULL
                AND (
                    operating_status IS NULL
                    OR CAST(operating_status AS VARCHAR) <> 'permanently_closed'
                )
                AND {category_clause}
        ),
        ranked AS (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY has_phone
                    ORDER BY hash(id)
                ) AS contact_rank
            FROM base
        )
        SELECT
            id,
            name,
            basic_category,
            taxonomy_primary,
            taxonomy_hierarchy,
            phone,
            website,
            email,
            socials,
            address,
            locality,
            address_region,
            postcode,
            address_country,
            longitude,
            latitude,
            confidence,
            source_dataset
        FROM ranked
        ORDER BY
            CASE
                WHEN has_phone AND contact_rank <= ? THEN 0
                WHEN NOT has_phone AND has_website AND contact_rank <= ? THEN 1
                ELSE 2
            END,
            CASE WHEN has_phone THEN 0 ELSE 1 END,
            contact_rank
        LIMIT ?
        """

        connection = self._get_connection()
        params=[xmin,xmax,ymin,ymax]
        if partition_count > 1:
            params.extend([partition_count,partition])
        params.extend([phone_budget,website_budget,row_limit])

        timeout_fired=threading.Event()

        def interrupt_query():
            timeout_fired.set()
            try:
                connection.interrupt()
            except Exception:
                # The worker query remains authoritative. If interrupt itself
                # fails, the workflow-level timeout is still the final guard.
                pass

        timer=threading.Timer(self.query_timeout_seconds,interrupt_query)
        timer.daemon=True
        timer.start()
        try:
            cursor=connection.execute(sql,params)
            columns=[item[0] for item in cursor.description]
            records=[dict(zip(columns,row)) for row in cursor.fetchall()]
        except Exception as exc:
            if timeout_fired.is_set():
                raise OvertureQueryTimeout(
                    "Overture query exceeded "
                    f"{self.query_timeout_seconds:g}s timeout."
                ) from exc
            raise
        finally:
            timer.cancel()

        expected_country = COUNTRY_CODES.get(location.get("country", ""))
        leads: list[Lead] = []
        for record in records:
            address_country = str(record.get("address_country") or "").upper()
            if expected_country and address_country and address_country != expected_country:
                continue

            name = str(record.get("name") or "").strip()
            phone = str(record.get("phone") or "").strip()
            website = str(record.get("website") or "").strip()
            if not name or (not phone and not website):
                continue

            reason = category_match_reason(
                category,
                primary=str(record.get("taxonomy_primary") or ""),
                basic=str(record.get("basic_category") or ""),
                hierarchy=record.get("taxonomy_hierarchy") or [],
                name=name,
            )
            if not reason:
                # Defense in depth: even if SQL/provider behavior changes, a
                # record must pass the Python classifier before becoming a lead.
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
                    website=website,
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
                        f"provider dataset {dataset}; taxonomy {taxonomy}; "
                        f"classification {reason}"
                    ),
                )
            )
        return leads
