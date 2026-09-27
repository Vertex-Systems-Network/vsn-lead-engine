from __future__ import annotations

from types import SimpleNamespace

import vsn_lead_engine.enrichment as enrichment
from vsn_lead_engine.engine import run_once
from vsn_lead_engine.models import Lead
from vsn_lead_engine.normalize import normalize_phone


def config():
    return {
        "enrichment": {
            "enabled": True,
            "max_candidates_per_run": 4,
            "workers": 2,
            "request_timeout_seconds": 2,
            "max_pages_per_site": 2,
            "max_response_bytes": 131072,
            "respect_robots_txt": True,
            "user_agent": "VSN-Lead-Engine-Test/0.7",
            "common_crawl": {
                "enabled": True,
                "max_lookups_per_run": 2,
                "min_interval_seconds": 1,
                "index_url": "https://index.commoncrawl.org",
                "data_url": "https://data.commoncrawl.org",
            },
        }
    }


def lead(**changes):
    data = {
        "country": "United States",
        "category": "IT & Software",
        "business_name": "Example Systems",
        "phone": "",
        "city": "Austin",
        "region": "Texas",
        "source": "Overture Maps Places",
        "source_id": "overture:example",
        "website": "https://example.com",
    }
    data.update(changes)
    return Lead(**data)


def test_contact_parser_extracts_public_phone_email_social_and_contact_link():
    html = """
    <html><body>
      <p>Call us at (202) 555-0199</p>
      <a href="mailto:hello@example.com">Email</a>
      <a href="/contact-us">Contact</a>
      <a href="https://www.linkedin.com/company/example">LinkedIn</a>
      <script>fake +1 202 555 0100</script>
    </body></html>
    """
    data = enrichment._contact_data(
        html, "https://example.com/", "United States"
    )
    assert data["phones"] == ["+12025550199"]
    assert data["emails"] == ["hello@example.com"]
    assert data["socials"]["linkedin"].startswith("https://www.linkedin.com/")
    assert data["contact_links"] == ["https://example.com/contact-us"]


def test_private_dns_target_is_rejected(monkeypatch):
    monkeypatch.setattr(
        enrichment.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    assert enrichment._public_host("internal.example", 443) is False


def test_public_dns_target_is_allowed(monkeypatch):
    monkeypatch.setattr(
        enrichment.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("8.8.8.8", 443)),
        ],
    )
    assert enrichment._public_host("public.example", 443) is True


def test_enricher_uses_common_crawl_only_after_live_phone_miss(monkeypatch):
    worker = enrichment.ContactEnricher(config())
    item = lead()

    def live(_lead):
        return {
            "attempted": True,
            "changed": False,
            "phone": False,
            "error": "",
        }

    def common(target):
        target.phone = "+12025550199"
        target.notes = "contact enrichment common_crawl:CC-MAIN-test"
        return True

    monkeypatch.setattr(worker, "_live_enrich", live)
    monkeypatch.setattr(worker, "_common_enrich", common)

    result = worker.enrich([item])
    assert result["live_attempted"] == 1
    assert result["live_phone_recovered"] == 0
    assert result["common_crawl_attempted"] == 1
    assert result["common_crawl_phone_recovered"] == 1
    assert normalize_phone(item.phone, item.country) == "+12025550199"


def test_enricher_budget_caps_network_candidates(monkeypatch):
    cfg = config()
    cfg["enrichment"]["max_candidates_per_run"] = 1
    cfg["enrichment"]["common_crawl"]["enabled"] = False
    worker = enrichment.ContactEnricher(cfg)

    monkeypatch.setattr(
        worker,
        "_live_enrich",
        lambda item: {
            "attempted": True,
            "changed": False,
            "phone": False,
            "error": "",
        },
    )
    result = worker.enrich(
        [
            lead(source_id="overture:a", website="https://a.example"),
            lead(source_id="overture:b", website="https://b.example"),
        ]
    )
    assert result["candidates"] == 1
    assert result["skipped_budget"] == 1
    assert result["live_attempted"] == 1


class WebsiteOnlySource:
    name = "Website Only"

    def search(self, category, geography, limit):
        return [
            Lead(
                country="United States",
                category=category,
                business_name="Recovered Phone LLC",
                phone="",
                city=geography["city"],
                region=geography["region"],
                source=self.name,
                source_id="website-only:1",
                website="https://recovered.example",
            )
        ]


class FakeEnricher:
    def enrich(self, leads):
        leads[0].phone = "+12025550199"
        return {
            "candidates": 1,
            "live_attempted": 1,
            "live_changed": 1,
            "live_phone_recovered": 1,
        }


def test_run_once_accepts_phone_recovered_before_final_phone_gate(monkeypatch):
    monkeypatch.setattr(
        "vsn_lead_engine.engine.run_cursor",
        lambda: 0,
    )
    cfg = {
        "runtime": {
            "enabled": True,
            "timezone": "Asia/Karachi",
            "daily_target_per_category": 1000,
            "max_shard_attempts": 1,
            "batch_accept_limit": 10,
            "candidate_limit_per_shard": 10,
            "source_retry_attempts": 1,
            "source_retry_backoff_seconds": 0,
        },
        "categories": ["IT & Software"],
        "geographies": [
            {
                "country": "United States",
                "region": "Texas",
                "city": "Austin",
                "bbox": [-98.0, 30.0, -97.0, 31.0],
            }
        ],
        "registry": {"mode": "sheets"},
    }

    result = run_once(
        cfg,
        dry_run=True,
        run_date="2026-09-27",
        sources=[WebsiteOnlySource()],
        enricher=FakeEnricher(),
    )

    assert result["status"] == "dry-run"
    assert result["discovered"] == 1
    assert result["accepted"] == 1
    assert result["rejections"].get("missing_or_invalid_phone", 0) == 0
    assert result["enrichment"]["live_phone_recovered"] == 1


def test_enrichment_per_call_cap_preserves_budget_for_later_shards(monkeypatch):
    cfg=config()
    cfg["enrichment"]["max_candidates_per_run"]=4
    cfg["enrichment"]["max_candidates_per_call"]=1
    cfg["enrichment"]["common_crawl"]["enabled"]=False
    worker=enrichment.ContactEnricher(cfg)

    monkeypatch.setattr(
        worker,
        "_live_enrich",
        lambda item:{
            "attempted":True,
            "changed":False,
            "phone":False,
            "error":"",
        },
    )

    first=worker.enrich([
        lead(category="A",source_id="a1",website="https://a1.example"),
        lead(category="A",source_id="a2",website="https://a2.example"),
        lead(category="A",source_id="a3",website="https://a3.example"),
    ])
    second=worker.enrich([
        lead(category="B",source_id="b1",website="https://b1.example"),
        lead(category="B",source_id="b2",website="https://b2.example"),
    ])

    assert first["candidates"]==1
    assert first["skipped_call_budget"]==2
    assert first["skipped_event_budget"]==0
    assert second["candidates"]==1
    assert second["skipped_call_budget"]==1
    assert second["skipped_event_budget"]==0
    assert worker._attempted==2


def test_common_crawl_per_call_cap_spreads_global_budget_across_calls(monkeypatch):
    cfg=config()
    cfg["enrichment"]["max_candidates_per_run"]=6
    cfg["enrichment"]["max_candidates_per_call"]=3
    cfg["enrichment"]["common_crawl"]["max_lookups_per_run"]=2
    cfg["enrichment"]["common_crawl"]["max_lookups_per_call"]=1
    worker=enrichment.ContactEnricher(cfg)

    monkeypatch.setattr(
        worker,
        "_live_enrich",
        lambda item:{
            "attempted":True,
            "changed":False,
            "phone":False,
            "error":"",
        },
    )
    monkeypatch.setattr(worker,"_common_enrich",lambda item:False)

    first=worker.enrich([
        lead(category="A",source_id="a1",website="https://a1.example"),
        lead(category="A",source_id="a2",website="https://a2.example"),
    ])
    second=worker.enrich([
        lead(category="B",source_id="b1",website="https://b1.example"),
        lead(category="B",source_id="b2",website="https://b2.example"),
    ])
    third=worker.enrich([
        lead(category="C",source_id="c1",website="https://c1.example"),
    ])

    assert first["common_crawl_attempted"]==1
    assert first["common_crawl_skipped_call_budget"]==1
    assert second["common_crawl_attempted"]==1
    assert second["common_crawl_skipped_call_budget"]==1
    assert third["common_crawl_attempted"]==0
    assert third["common_crawl_skipped_event_budget"]==1
    assert worker._common_attempted==2
