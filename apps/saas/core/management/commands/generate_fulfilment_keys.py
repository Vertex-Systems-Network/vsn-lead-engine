import json
import os

from django.core.management.base import BaseCommand, CommandError
from lead_saas.local_fulfilment import new_keys


class Command(BaseCommand):
    help = "Write four new random fulfilment signing keys to an owner-only JSON file."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **options):
        path = options["path"]
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise CommandError(f"{path} already exists; keys are never overwritten.") from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(new_keys(), handle)
        self.stdout.write(f"Wrote {path}. Set SAAS_FULFILMENT_KEYS_FILE={path} for the worker.")
