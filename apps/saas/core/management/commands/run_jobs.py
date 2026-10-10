from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from core.fulfilment import run_pending


class Command(BaseCommand):
    help = "Fulfil at most --limit queued jobs through the v2 accepted-result path."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        try:
            counts = run_pending(limit=options["limit"])
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(", ".join(f"{key} {value}" for key, value in counts.items()) + ".")
