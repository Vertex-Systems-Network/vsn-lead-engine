from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from core.recovery import expire_pending_intents


class Command(BaseCommand):
    help = "Close at most 100 expired pre-dispatch intents and release unused reservations."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        try:
            result = expire_pending_intents(limit=options["limit"])
        except ValidationError as exc:
            raise CommandError(str(exc.detail)) from exc
        self.stdout.write(f"Examined {result['examined']}; expired {result['expired']}.")
