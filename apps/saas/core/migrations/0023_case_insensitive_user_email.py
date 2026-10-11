"""Enforce unique nonblank account recovery identity case-insensitively.

Existing case-insensitive duplicate email addresses must be reconciled before
applying this migration. Never pick a password-reset recipient silently.
"""

from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [("core", "0022_workspace_invitation")]

    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="saas_user_email_ci_unique",
            ),
        ),
    ]
