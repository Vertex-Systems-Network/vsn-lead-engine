from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from lead_saas.local_fulfilment import LOCAL_SOURCES, OVERTURE, SOURCE_CODE

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


OVERTURE_EVIDENCE = (
    "Overture Maps Places public release (CDLA Permissive 2.0 / Apache 2.0 / CC0 by "
    "contributing source); attribution and handling per DATA_SOURCES.md"
)


def local_policy_defaults(code=SOURCE_CODE):
    marker = (
        OVERTURE_EVIDENCE
        if code == OVERTURE
        else "local-development-only: synthetic fixture data, no real business records"
    )
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
    help = "Create or refresh a dev source policy: local-fixture (default) or overture."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=LOCAL_SOURCES, default=SOURCE_CODE)

    def handle(self, *args, **options):
        if not settings.SAAS_LOCAL_FULFILMENT:
            raise CommandError("seed_local_source requires SAAS_LOCAL_FULFILMENT=1.")
        code = options["source"]
        _, created = SourcePolicy.objects.update_or_create(
            code=code, defaults=local_policy_defaults(code)
        )
        self.stdout.write(f"{'Created' if created else 'Updated'} source policy {code}.")
