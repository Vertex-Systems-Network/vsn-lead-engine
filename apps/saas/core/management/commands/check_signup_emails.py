"""Read-only pre-migration check for ambiguous case-insensitive reset recipients.

Only a generic success/blocker is printed. Never log email values, identities,
database connection exceptions, or any reset token.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.db.models.functions import Lower

from core.models import User


def has_recovery_email_collisions():
    """Check current stored accounts; works before migration 0023 is applied."""
    return (
        User.objects.exclude(email="")
        .annotate(recovery_email_key=Lower("email"))
        .values("recovery_email_key")
        .annotate(duplicate_count=Count("pk"))
        .filter(duplicate_count__gt=1)
        .exists()
    )


class Command(BaseCommand):
    help = "Read-only, non-identifying email-uniqueness preflight; never migrates data."

    def handle(self, *args, **options):
        try:
            collisions = has_recovery_email_collisions()
        except Exception:
            # Database error messages may contain PII, hostnames or credentials.
            raise CommandError(
                "Account email preflight unavailable; verify database access privately."
            ) from None
        if collisions:
            raise CommandError(
                "Conflicting case-insensitive account emails exist. "
                "Reconcile them through an authorized private procedure before migration 0023."
            )
        self.stdout.write(
            "Account email preflight passed: no conflicting nonblank recovery identities. "
            "This does not migrate data or certify SMTP delivery."
        )
