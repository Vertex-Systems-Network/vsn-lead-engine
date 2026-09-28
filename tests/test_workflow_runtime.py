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
]


def test_first_party_workflows_use_node24_action_majors():
    root=Path(".github/workflows")
    for name in WORKFLOWS:
        content=(root/name).read_text(encoding="utf-8")
        assert "actions/checkout@v7" in content, name
        assert "actions/setup-python@v7" in content, name
        assert "actions/checkout@v4" not in content, name
        assert "actions/setup-python@v5" not in content, name
