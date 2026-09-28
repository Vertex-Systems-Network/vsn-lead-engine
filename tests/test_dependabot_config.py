from pathlib import Path


CONFIG=Path(".github/dependabot.yml")


def test_dependabot_monitors_actions_and_python_weekly():
    content=CONFIG.read_text(encoding="utf-8")
    assert content.startswith("version: 2\n")
    assert 'package-ecosystem: "github-actions"' in content
    assert 'package-ecosystem: "pip"' in content
    assert content.count('directory: "/"') == 2
    assert content.count('interval: "weekly"') == 2
    assert content.count('timezone: "Asia/Karachi"') == 2
    assert 'versioning-strategy: "increase-if-necessary"' in content


def test_dependabot_groups_updates_to_limit_pr_noise():
    content=CONFIG.read_text(encoding="utf-8")
    assert "github-actions:" in content
    assert "python-dependencies:" in content
    assert content.count('open-pull-requests-limit: 4') == 2
    assert content.count('patterns:') == 2
