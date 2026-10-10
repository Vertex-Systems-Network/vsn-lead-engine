# One-time existing-account invitation workflow, no email delivery or billing.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def refuse_invitation_evidence_loss(apps, schema_editor):
    if apps.get_model("core", "WorkspaceInvitation").objects.using(
        schema_editor.connection.alias
    ).exists():
        raise RuntimeError("Invitation records exist; rollback requires an evidence preservation plan.")


class Migration(migrations.Migration):
    dependencies = [("core", "0021_batch_noeffect")]

    operations = [
        migrations.CreateModel(
            name="WorkspaceInvitation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("admin", "admin"),
                            ("member", "member"),
                            ("viewer", "viewer"),
                        ],
                        max_length=8,
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(null=True)),
                ("revoked_at", models.DateTimeField(null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="issued_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="workspace_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.workspace",
                    ),
                ),
            ],
        ),
        migrations.RunPython(migrations.RunPython.noop, refuse_invitation_evidence_loss),
    ]
