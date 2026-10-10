from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from lead_saas.local_fulfilment import SOURCE_CODE

from core.jobs import CONTROLS, EVIDENCE
from core.models import SourcePolicy

CATEGORIES = [
    "AI & Automation",
    "Medical & Clinics",
    "Property & Real Estate",
    "Business & Consulting",
    "IT & Software",
    "Media & Creative",
    "Other Website-Critical",
    "Spa",
    "Salon",
    "Cars",
    "Motorbikes",
    "Insurance",
]
RESULT_CONTRACT = {
    "version": 1,
    "purpose": "local-development-only",
    "retention_version": "local-v1",
    "max_age_seconds": 2592000,
    "display_fields": ["address", "business_name", "city", "phone", "status", "website"],
    "storage_fields": ["address", "business_name", "city", "phone", "status", "website"],
    "display_allowed": True,
    "storage_allowed": True,
}


def local_policy_defaults():
    marker = "local-development-only: synthetic fixture data, no real business records"
    return {
        "enabled": True,
        "free_collection": True,
        "countries": ["CA", "US"],
        "categories": CATEGORIES,
        "statuses": ["active"],
        "fields": ["address", "name", "phone", "website"],
        "evidence": {key: marker for key in EVIDENCE},
        "controls": {
            **{key: marker for key in CONTROLS},
            "result_contract": RESULT_CONTRACT,
        },
        "max_provider_calls": 1,
    }


class Command(BaseCommand):
    help = "Create or refresh the synthetic local-fixture source policy (dev only)."

    def handle(self, *args, **options):
        if not settings.SAAS_LOCAL_FULFILMENT:
            raise CommandError("seed_local_source requires SAAS_LOCAL_FULFILMENT=1.")
        _, created = SourcePolicy.objects.update_or_create(
            code=SOURCE_CODE, defaults=local_policy_defaults()
        )
        self.stdout.write(f"{'Created' if created else 'Updated'} source policy {SOURCE_CODE}.")
