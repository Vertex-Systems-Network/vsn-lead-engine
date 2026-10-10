"""Read-only by default; explicit development-only fixture draft creation."""

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.http import Http404
from rest_framework.exceptions import APIException

from core.daily_tick import tick_daily_plans
from core.models import User


class Command(BaseCommand):
    help = (
        "Preview due daily plans (no writes). --apply-dev can create fixture "
        "drafts only when SAAS_DEBUG=1, SAAS_LOCAL_FULFILMENT=1 and "
        "SAAS_DAILY_DEV_APPLY=1; never enqueue or call a provider."
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor", type=UUID, required=True)
        parser.add_argument("--workspace", type=UUID, required=True)
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument("--after", type=UUID)
        parser.add_argument("--apply-dev", action="store_true", default=False)

    def handle(self, *args, **options):
        try:
            actor = User.objects.get(pk=options["actor"], is_active=True)
            report = tick_daily_plans(
                actor,
                options["workspace"],
                limit=options["limit"],
                after=options["after"],
                apply_dev=options["apply_dev"],
            )
        except (User.DoesNotExist, Http404, APIException):
            # Do not print tenant identities, sensitive requests or provider data.
            raise CommandError(
                "Daily tick unavailable: role, workspace, bound or fixture development gate denied."
            ) from None
        self.stdout.write(json.dumps(report, sort_keys=True))
