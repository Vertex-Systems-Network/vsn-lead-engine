from pathlib import Path


WORKFLOWS = [
    "lead-engine.yml",
    "daily-workbook-readiness.yml",
    "quota-recovery-supervisor.yml",
    "r2-registry.yml",
    "registry-collision-probe.yml",
    "registry-maintenance.yml",
    "source-probe.yml",
    "taxonomy-audit.yml",
    "main-protection-controller.yml",
    "dependency-lock.yml",
    "google-drive-capability.yml",
]

CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"


def test_first_party_workflows_pin_node24_action_releases_by_sha():
    root=Path(".github/workflows")
    checkout_ref=f"actions/checkout@{CHECKOUT_SHA}"
    setup_ref=f"actions/setup-python@{SETUP_PYTHON_SHA}"

    for name in WORKFLOWS:
        content=(root/name).read_text(encoding="utf-8")
        assert checkout_ref in content, name
        assert setup_ref in content, name
        assert "actions/checkout@v7" not in content, name
        assert "actions/setup-python@v7" not in content, name
        assert "actions/checkout@v4" not in content, name
        assert "actions/setup-python@v5" not in content, name
