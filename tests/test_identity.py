from vsn_lead_engine import __version__
from vsn_lead_engine.enrichment import ContactEnricher
from vsn_lead_engine.identity import default_user_agent


def test_default_user_agent_tracks_package_version():
    assert default_user_agent() == (
        f"VSN-Lead-Engine/{__version__} (+https://vertexsystemsnetwork.com/)"
    )


def test_enricher_uses_canonical_identity_without_override():
    worker = ContactEnricher({"enrichment": {}})
    assert worker.user_agent == default_user_agent()


def test_enricher_keeps_explicit_operator_override():
    worker = ContactEnricher(
        {"enrichment": {"user_agent": "VSN-Lead-Engine/custom-test"}}
    )
    assert worker.user_agent == "VSN-Lead-Engine/custom-test"
