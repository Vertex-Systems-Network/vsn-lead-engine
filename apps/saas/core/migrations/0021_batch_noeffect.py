import django.db.models.deletion
from django.db import migrations, models


def protect_noeffect_rollback(apps, schema_editor):
    if apps.get_model("core", "SourceBatchNoEffect").objects.using(
        schema_editor.connection.alias
    ).exists():
        raise RuntimeError("V3 no-effect evidence exists; rollback requires a preservation plan.")


class Migration(migrations.Migration):
    dependencies = [("core", "0020_batch_payload_links")]

    operations = [
        migrations.CreateModel(
            name="SourceBatchNoEffect",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("source_code", models.CharField(max_length=64)),
                ("receipt_ref", models.CharField(max_length=96)),
                ("source_key_id", models.CharField(max_length=64)),
                ("body_hash", models.CharField(max_length=64)),
                ("batch_set_hash", models.CharField(max_length=64)),
                ("batch_count", models.PositiveIntegerField()),
                ("provider_calls", models.PositiveIntegerField(default=0)),
                ("issued_at", models.DateTimeField()),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "operation",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT, to="core.dispatchoperation"
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("source_code", "receipt_ref"), name="saas_batch_noeffect_ref"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(provider_calls=0), name="saas_batch_noeffect_zero_calls"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(batch_count__lte=1000), name="saas_batch_noeffect_bound"
                    ),
                ],
            },
        ),
        migrations.RunPython(migrations.RunPython.noop, protect_noeffect_rollback),
    ]
