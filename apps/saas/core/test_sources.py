from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from lead_saas.local_fulfilment import OVERTURE

from .fulfilment import run_pending
from .models import AcceptedResult, Entitlement, User
from .services import create_workspace
from .sources import OvertureSource, adapter_for, geographies, nanp_e164
from .test_fulfilment import LOCAL, queued_job


def place(i, **changes):
    data = {
        "source_id": f"08f2a{i:04d}abc",
        "business_name": f"Salon {i}",
        "phone": f"(512) 555-{1000 + i}",
        "city": "Austin",
        "region": "Texas",
        "street_address": f"{i} Congress Ave",
        "website": "" if i % 2 else f"https://salon{i}.example",
    }
    data.update(changes)
    return SimpleNamespace(**data)


class FakePlaces:
    def __init__(self, places):
        self.places = places
        self.calls = []

    def search(self, category, location, limit=None):
        self.calls.append((category, location["city"]))
        return self.places


GEOS = {"US": [{"country": "United States", "city": "Austin"}, {"city": "Dallas"}], "CA": []}


class OvertureAdapterTests(SimpleTestCase):
    def test_nanp_normalisation(self):
        self.assertEqual(nanp_e164("(512) 555-1234"), "+15125551234")
        self.assertEqual(nanp_e164("+1 512 555 1234"), "+15125551234")
        for bad in ("", "555-1234", "+44 20 7946 0958", "(112) 555-1234", "512 055 1234"):
            self.assertEqual(nanp_e164(bad), "")

    def test_maps_places_to_lead_dicts_and_skips_unusable_rows(self):
        fake = FakePlaces([place(1), place(2), place(3, phone="n/a"), place(4, business_name=" ")])
        source = OvertureSource(place_source=fake, geographies_for=GEOS.get)
        leads = source.fetch({"countries": ["US"], "categories": ["Salon"]}, 10)
        self.assertEqual(
            [lead["source_id"] for lead in leads], ["ov-08f2a0001abc", "ov-08f2a0002abc"]
        )
        self.assertEqual(leads[0]["phone"], "+15125551001")
        self.assertEqual((leads[0]["country"], leads[0]["category"]), ("US", "Salon"))
        self.assertNotIn("website", leads[0])
        self.assertEqual(leads[1]["website"], "https://salon2.example")
        self.assertEqual(leads[1]["address"], "2 Congress Ave")

    def test_keeps_searching_past_known_leads_and_bounds_queries(self):
        fake = FakePlaces([place(i) for i in range(1, 4)])
        source = OvertureSource(place_source=fake, geographies_for=GEOS.get)
        leads = source.fetch(
            {"countries": ["US"], "categories": ["Salon"]},
            10,
            is_new=lambda lead: lead["source_id"] != "ov-08f2a0001abc",
        )
        self.assertEqual(len(leads), 2)
        self.assertEqual(fake.calls, [("Salon", "Austin"), ("Salon", "Dallas")])

    def test_registry_and_real_geographies(self):
        self.assertIsInstance(adapter_for(OVERTURE), OvertureSource)
        self.assertIsNone(adapter_for("unknown"))
        us, ca = geographies("US"), geographies("CA")
        self.assertTrue(us and ca)
        self.assertTrue(all(len(g["bbox"]) == 4 for g in us + ca))


@override_settings(**LOCAL)
class OvertureFulfilmentTests(TestCase):
    def test_overture_job_fulfils_end_to_end_with_injected_places(self):
        call_command("seed_local_source", "--source", OVERTURE, stdout=StringIO())
        user = User.objects.create_user(username="overture-owner")
        workspace = create_workspace(user, {"name": "Overture", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=workspace, active=True, lead_limit=50, job_limit=5, provider_call_limit=5
        )
        job = queued_job(user, workspace, source_codes=[OVERTURE], result_limit=5)
        fake = FakePlaces([place(i) for i in range(1, 9)])
        adapter = OvertureSource(place_source=fake, geographies_for=GEOS.get)
        with patch("core.fulfilment.adapter_for", return_value=adapter):
            self.assertEqual(run_pending()["completed"], 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.result_count), ("completed", 5))
        rows = AcceptedResult.objects.filter(job=job)
        self.assertTrue(all(r.fields["phone"].startswith("+1512555") for r in rows))
        self.assertTrue(all(r.record_ref.startswith("ov-") for r in rows))
