from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.http import Http404
from rest_framework.exceptions import APIException

from core.models import User
from core.result_retention import expire_result_payloads


class Command(BaseCommand):
    help = "Erase at most 100 source-expired SaaS payloads in one authorized workspace; retain dedupe tombstones."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", required=True, type=UUID)
        parser.add_argument("--actor", required=True, type=UUID)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        try:
            user = User.objects.get(pk=options["actor"], is_active=True)
            result = expire_result_payloads(user, options["workspace"], limit=options["limit"])
        except (User.DoesNotExist, Http404, APIException):
            raise CommandError("Authorized workspace cleanup is unavailable.") from None
        self.stdout.write(f"Erased {result['erased_count']}; more due: {result['more_due']}.")
