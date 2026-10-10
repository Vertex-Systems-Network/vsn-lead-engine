"""Read-only workspace-scoped daily plan due-candidate diagnostics."""

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.http import Http404
from rest_framework.exceptions import APIException

from core.daily_due_diagnostics import due_plan_diagnostics
from core.models import User


class Command(BaseCommand):
    help = (
        "Inspect at most 25 daily plan candidates for an authorized owner/admin; "
        "no schedule, job, network, provider or usage writes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor", type=UUID, required=True)
        parser.add_argument("--workspace", type=UUID, required=True)
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--after", type=UUID)

    def handle(self, *args, **options):
        try:
            actor = User.objects.get(pk=options["actor"], is_active=True)
            result = due_plan_diagnostics(
                actor,
                options["workspace"],
                limit=options["limit"],
                after=options["after"],
            )
        except (User.DoesNotExist, Http404, APIException):
            raise CommandError(
                "Daily plan diagnostics are unavailable for this actor/workspace."
            ) from None
        self.stdout.write(json.dumps(result, sort_keys=True))
