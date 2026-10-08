import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.http import Http404
from rest_framework.exceptions import APIException

from core.billing_status import billing_status
from core.models import User


class Command(BaseCommand):
    help = "Read redacted billing/ledger status for one workspace without writes or repairs."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--workspace", required=True)

    def handle(self, *args, **options):
        try:
            actor_id, workspace_id = UUID(options["actor"]), UUID(options["workspace"])
            user = User.objects.get(pk=actor_id, is_active=True)
            status = billing_status(user, workspace_id)
        except (ValueError, TypeError, User.DoesNotExist, Http404, APIException):
            raise CommandError(
                "Billing diagnostics are unavailable for this actor/workspace."
            ) from None
        self.stdout.write(json.dumps(status, sort_keys=True))
