from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from lead_saas.local_fulfilment import OVERTURE

from .fulfilment import run_pending
from .models import AcceptedResult, Entitlement, User
from .services import create_workspace
from .sources import OvertureSource, adapter_for, geographies, nanp_e164, valid_public_website
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
        for malformed in (None, 5125551234, [], {}, False):
            self.assertEqual(nanp_e164(malformed), "")

    def test_public_lead_website_check_is_conservative_and_never_fetches(self):
        for valid in (
            "https://salon2.example",
            "http://shop.example.com/",
            "https://www.example.ca/path?q=hello#about",
            "https://xn--bcher-kva.example",
            "https://salon.example:8443/catalog",
        ):
            with self.subTest(valid=valid):
                self.assertTrue(valid_public_website(valid))
        for invalid in (
            None,
            ["https://salon.example"],
            "",
            "salon.example",
            "//salon.example",
            "javascript:alert(1)",
            "data:text/html,hello",
            "file:///etc/passwd",
            "ftp://salon.example",
            "https://user:secret@salon.example",
            "https://[broken",
            "https://localhost",
            "https://127.0.0.1/private",
            "https://domain.123",
            "https://salon.example:99999",
            "https://salon.example:abc",
            "https://salon.example\\\\@fake.example",
            "https://salon.example/path\\nnewline",
            "https://salon.example/path with spaces",
            "https://salon.example./",
            "https://-salon.example",
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(valid_public_website(invalid))

    def test_unsafe_optional_overture_websites_are_omitted_not_fatal(self):
        bad = (
            "javascript:alert(1)",
            "//provider.example",
            "shop.example.com",
            "http://127.0.0.1/internal",
            "https://user:pass@provider.example",
            "ftp://provider.example",
            "https://[broken",
            "https://provider.example\\\\@invalid.example",
        )
        fake = FakePlaces([place(i + 10, website=url) for i, url in enumerate(bad)])
        adapter = OvertureSource(place_source=fake, geographies_for=GEOS.get)
        leads = adapter.fetch({"countries": ["US"], "categories": ["Salon"]}, 10)
        self.assertEqual(len(leads), len(bad))
        self.assertTrue(all("website" not in lead for lead in leads))

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

    def test_malformed_place_isolated_and_bad_optional_fields_discarded(self):
        fake = FakePlaces(
            [
                place(1, phone=5125551001),
                place(2, business_name=None),
                place(3, source_id=None),
                place(4, website="https://[unbalanced"),
                place(5, website="https://user:secret@provider.example"),
                place(6, city={"bad": "data"}, region=[], street_address=123),
                place(7, business_name="CRLF\nInjected"),
                place(8),
            ]
        )
        source = OvertureSource(place_source=fake, geographies_for=GEOS.get)
        leads = source.fetch({"countries": ["US"], "categories": ["Salon"]}, 10)
        self.assertEqual(
            [item["source_id"] for item in leads],
            ["ov-08f2a0004abc", "ov-08f2a0005abc", "ov-08f2a0006abc", "ov-08f2a0008abc"],
        )
        self.assertNotIn("website", leads[0])
        self.assertNotIn("website", leads[1])
        self.assertNotIn("city", leads[2])
        self.assertNotIn("region", leads[2])
        self.assertNotIn("address", leads[2])
        self.assertEqual(leads[-1]["business_name"], "Salon 8")

    def test_source_identifiers_never_collide_after_normalization_or_truncation(self):
        colliding_before = [
            place(1, source_id="abc/id"),
            place(2, source_id="abcid"),
            place(3, source_id="x" * 94),
            place(4, source_id="x" * 93),
            place(5, source_id="abc\\ndef"),
            place(6, source_id="valid.a:b-1"),
        ]
        source = OvertureSource(place_source=FakePlaces(colliding_before), geographies_for=GEOS.get)
        leads = source.fetch({"countries": ["US"], "categories": ["Salon"]}, 10)
        self.assertEqual(
            [lead["source_id"] for lead in leads],
            ["ov-abcid", "ov-" + "x" * 93, "ov-valid.a:b-1"],
        )
        self.assertEqual(len({lead["source_id"] for lead in leads}), 3)
        self.assertTrue(all(len(lead["source_id"]) <= 96 for lead in leads))

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
    def test_malformed_upstream_place_does_not_block_valid_synthetic_overture_job(self):
        call_command("seed_local_source", "--source", OVERTURE, stdout=StringIO())
        user = User.objects.create_user(username="overture-partial-record-owner")
        workspace = create_workspace(user, {"name": "Overture partial", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=workspace, active=True, lead_limit=50, job_limit=5, provider_call_limit=5
        )
        job = queued_job(user, workspace, source_codes=[OVERTURE], result_limit=2)
        fake = FakePlaces(
            [
                place(1, phone={"private": "not-a-phone"}),
                place(2, website="https://[broken"),
                place(3, source_id=None),
                place(4, business_name="Valid place", website=""),
            ]
        )
        adapter = OvertureSource(place_source=fake, geographies_for=GEOS.get)
        with patch("core.fulfilment.adapter_for", return_value=adapter):
            counts = run_pending(limit=1)
        self.assertEqual(counts["completed"], 1)
        self.assertEqual(counts["unknown"], 0)
        job.refresh_from_db()
        self.assertEqual((job.status, job.result_count), ("completed", 2))
        rows = AcceptedResult.objects.filter(job=job)
        self.assertEqual(rows.count(), 2)
        self.assertTrue(all("website" not in row.fields for row in rows))

    def test_distinct_overture_ids_survive_colliding_untrusted_id_inputs(self):
        call_command("seed_local_source", "--source", OVERTURE, stdout=StringIO())
        user = User.objects.create_user(username="overture-safe-id-owner")
        workspace = create_workspace(user, {"name": "Overture IDs", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=workspace, active=True, lead_limit=50, job_limit=5, provider_call_limit=5
        )
        job = queued_job(user, workspace, source_codes=[OVERTURE], result_limit=2)
        places = FakePlaces(
            [
                place(1, source_id="xy/z"),
                place(2, source_id="xyz"),
                place(3, source_id="x" * 94),
                place(4, source_id="x" * 93),
            ]
        )
        adapter = OvertureSource(place_source=places, geographies_for=GEOS.get)
        with patch("core.fulfilment.adapter_for", return_value=adapter):
            summary = run_pending(limit=1)
        self.assertEqual((summary["completed"], summary["unknown"]), (1, 0))
        self.assertEqual(
            set(AcceptedResult.objects.filter(job=job).values_list("record_ref", flat=True)),
            {"ov-xyz", "ov-" + "x" * 93},
        )
        self.assertEqual(AcceptedResult.objects.filter(job=job).count(), 2)

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
