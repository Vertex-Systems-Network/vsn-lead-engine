import importlib
import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from lead_saas.local_fulfilment import (
    OVERTURE,
    PRODUCTION_SOURCES,
    SOURCE_CODE,
    derived_keys,
    load_keys_file,
    new_keys,
    verifier_maps,
)

from .fulfilment import run_pending
from .models import Entitlement, JobOutbox, User
from .services import create_workspace
from .sources import OvertureSource
from .test_fulfilment import queued_job
from .test_sources import GEOS, FakePlaces, place


def write(path, data, mode=0o600):
    Path(path).write_text(json.dumps(data))
    os.chmod(path, mode)


class KeysFileTests(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "keys.json")

    def test_generated_file_is_owner_only_loadable_and_never_overwritten(self):
        call_command("generate_fulfilment_keys", self.path, stdout=StringIO())
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        keys = load_keys_file(self.path)
        self.assertEqual(len(set(keys.values())), 4)
        self.assertTrue(all(len(key) == 32 for key in keys.values()))
        with self.assertRaises(CommandError):
            call_command("generate_fulfilment_keys", self.path, stdout=StringIO())

    def test_rejects_readable_short_duplicate_or_incomplete_keys(self):
        keys = new_keys()
        write(self.path, keys, mode=0o644)
        with self.assertRaisesRegex(ValueError, "owner only"):
            load_keys_file(self.path)
        for bad in (
            {**keys, "receipt": "ab" * 8},
            {**keys, "receipt": keys["candidate"]},
            {k: v for k, v in keys.items() if k != "dedupe"},
        ):
            write(self.path, bad)
            with self.assertRaises(ValueError):
                load_keys_file(self.path)

    def test_settings_load_production_keys_without_debug(self):
        import lead_saas.settings as module

        write(self.path, new_keys())
        env = {
            "SAAS_DEBUG": "0",
            "SAAS_SQLITE_SMOKE": "0",
            "SAAS_LOCAL_FULFILMENT": "0",
            "SAAS_FULFILMENT_KEYS_FILE": self.path,
        }
        try:
            with patch.dict(os.environ, env):
                importlib.reload(module)
                self.assertEqual(module.SAAS_FULFILMENT_SOURCES, PRODUCTION_SOURCES)
                self.assertEqual(set(module.SAAS_RESULT_VERIFIERS), {OVERTURE})
            os.chmod(self.path, 0o640)
            with patch.dict(os.environ, env), self.assertRaises(ImproperlyConfigured):
                importlib.reload(module)
            with patch.dict(os.environ, {**env, "SAAS_LOCAL_FULFILMENT": "1"}):
                with self.assertRaises(ImproperlyConfigured):
                    importlib.reload(module)
        finally:
            importlib.reload(module)


@override_settings(**verifier_maps(derived_keys("x" * 50), PRODUCTION_SOURCES))
class ProductionFulfilmentTests(TestCase):
    def setUp(self):
        call_command("seed_local_source", "--source", OVERTURE, stdout=StringIO())
        self.user = User.objects.create_user(username="prod-owner")
        self.workspace = create_workspace(self.user, {"name": "Prod", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=self.workspace, active=True, lead_limit=50, job_limit=5, provider_call_limit=5
        )

    def test_overture_jobs_run_and_fixture_is_not_a_production_source(self):
        with self.assertRaises(CommandError):
            call_command("seed_local_source", stdout=StringIO())
        job = queued_job(self.user, self.workspace, source_codes=[OVERTURE], result_limit=3)
        adapter = OvertureSource(
            place_source=FakePlaces([place(i) for i in range(1, 6)]), geographies_for=GEOS.get
        )
        with patch("core.fulfilment.adapter_for", return_value=adapter):
            self.assertEqual(run_pending()["completed"], 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.result_count), ("completed", 3))
        self.assertNotIn(SOURCE_CODE, JobOutbox.objects.get(job=job).source_snapshot)
