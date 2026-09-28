from importlib.metadata import version

from vsn_lead_engine import __version__


def test_distribution_version_matches_runtime_version():
    assert version("vsn-lead-engine") == __version__
