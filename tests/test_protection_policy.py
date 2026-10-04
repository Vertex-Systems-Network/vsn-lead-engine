import copy
import sys
import json
from pathlib import Path

sys.path.insert(0,str(Path("scripts").resolve()))
import github_ruleset_common as ruleset_common


def policy():
    return json.loads(
        Path(".github/main-protection-ruleset.json").read_text(encoding="utf-8")
    )


def test_main_protection_policy_targets_main_only():
    value=policy()
    assert value["name"]=="VSN Main Protection"
    assert value["target"]=="branch"
    assert value["enforcement"]=="active"
    assert value["bypass_actors"]==[]
    assert value["conditions"]["ref_name"]=={
        "include":["refs/heads/main"],
        "exclude":[],
    }


def test_main_protection_requires_pr_and_strict_validate_and_anpos_checks():
    value=policy()
    rules={item["type"]:item for item in value["rules"]}

    assert "deletion" in rules
    assert "non_fast_forward" in rules
    assert "required_linear_history" in rules

    pull=rules["pull_request"]["parameters"]
    assert pull["allowed_merge_methods"]==["squash"]
    assert pull["required_approving_review_count"]==0
    assert pull["dismiss_stale_reviews_on_push"] is True
    assert pull["required_review_thread_resolution"] is True
    assert pull["require_code_owner_review"] is False
    assert pull["require_last_push_approval"] is False

    checks=rules["required_status_checks"]["parameters"]
    assert checks["strict_required_status_checks_policy"] is True
    assert checks["do_not_enforce_on_create"] is True
    assert checks["required_status_checks"]==[
        {"context":"validate"},
        {"context":"repository-integrity"},
    ]


def test_lead_engine_pr_check_name_matches_required_context():
    workflow=Path(".github/workflows/lead-engine.yml").read_text(encoding="utf-8")
    assert "\n  validate:\n" in workflow
    assert "github.event_name == 'pull_request'" in workflow
    assert "pytest -q" in workflow


def test_protection_controller_never_embeds_admin_token():
    workflow=Path(
        ".github/workflows/main-protection-controller.yml"
    ).read_text(encoding="utf-8")
    assert "secrets.GH_ADMIN_TOKEN" in workflow
    assert "apply_main_protection.py --confirm" in workflow
    assert "verify_main_protection.py" in workflow
    assert 'echo "::error::GH_ADMIN_TOKEN is required before P12 live enforcement can be certified."' in workflow
    assert "exit 2" in workflow
    assert "permissions:\n  contents: read" in workflow


def test_recovery_trigger_remains_pr_compatible():
    workflow=Path(".github/workflows/lead-engine.yml").read_text(encoding="utf-8")
    assert 'paths:\n      - ".github/lead-run-trigger"' in workflow
    assert "github.event_name == 'push'" in workflow


def test_ruleset_comparator_ignores_github_server_added_pull_request_defaults():
    expected=policy()
    actual=copy.deepcopy(expected)
    pull=next(
        item for item in actual["rules"]
        if item["type"]=="pull_request"
    )["parameters"]
    pull.update({
        "required_reviewers":[],
        "dismissal_restriction":{
            "enabled":False,
            "allowed_actors":[],
        },
        "require_extra_approval_for_unattributed_changes":True,
    })

    assert ruleset_common.policy_diff(expected,actual)=={}


def test_ruleset_comparator_still_detects_real_required_check_drift():
    expected=policy()
    actual=copy.deepcopy(expected)
    checks=next(
        item for item in actual["rules"]
        if item["type"]=="required_status_checks"
    )["parameters"]
    checks["required_status_checks"]=[{"context":"wrong-check"}]

    drift=ruleset_common.policy_diff(expected,actual)
    assert "rules" in drift
    assert drift["rules"]["expected"] != drift["rules"]["actual"]
