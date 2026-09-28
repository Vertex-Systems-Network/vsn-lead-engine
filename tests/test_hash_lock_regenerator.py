import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/regenerate_hash_locks.py"
WORKFLOW=ROOT/".github/workflows/dependency-lock.yml"


def _load_module():
    spec=importlib.util.spec_from_file_location("vsn_regenerate_hash_locks",SCRIPT)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module


def test_lock_parser_accepts_hashed_exact_versions(tmp_path):
    module=_load_module()
    lock=tmp_path/"lock.txt"
    lock.write_text(
        "# test\n"
        "pip==25.2 --hash=sha256:" + "a"*64 + "\n"
        "setuptools==84.0.0 --hash=sha256:" + "b"*64 + "\n",
        encoding="utf-8",
    )
    assert module.parse_existing_versions(lock)=={
        "pip":"25.2",
        "setuptools":"84.0.0",
    }


def test_build_requirements_must_stay_exact():
    module=_load_module()
    assert module.exact_build_requirements(
        {"build-system":{"requires":["setuptools==84.0.0","wheel==0.48.0"]}}
    )==["setuptools==84.0.0","wheel==0.48.0"]

    with pytest.raises(SystemExit,match="exact-pinned"):
        module.exact_build_requirements(
            {"build-system":{"requires":["setuptools>=84","wheel==0.48.0"]}}
        )


def test_report_parser_requires_sha256(tmp_path):
    module=_load_module()
    report=tmp_path/"report.json"
    report.write_text(
        json.dumps(
            {
                "install":[
                    {
                        "metadata":{"name":"Example_Pkg","version":"1.2.3"},
                        "download_info":{
                            "archive_info":{
                                "hashes":{"sha256":"c"*64}
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rows=module.artifacts_from_report(report)
    assert rows["example-pkg"].version=="1.2.3"
    assert rows["example-pkg"].sha256=="c"*64

    report.write_text(
        json.dumps(
            {
                "install":[
                    {
                        "metadata":{"name":"bad","version":"1"},
                        "download_info":{"archive_info":{"hashes":{}}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit,match="missing SHA-256"):
        module.artifacts_from_report(report)


def test_dev_render_rejects_runtime_drift():
    module=_load_module()
    runtime={
        "requests":module.ResolvedArtifact("requests","2.34.2","d"*64)
    }
    drifted={
        "requests":module.ResolvedArtifact("requests","2.35.0","e"*64),
        "pytest":module.ResolvedArtifact("pytest","8.4.2","f"*64),
    }
    with pytest.raises(SystemExit,match="Development resolution changed"):
        module.render_dev(runtime,drifted)


def test_dependency_lock_workflow_is_manual_write_only_and_main_safe():
    content=WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in content
    assert "workflow_dispatch:" in content
    assert "contents: read" in content
    assert "contents: write" in content
    assert "main|master" in content
    assert "dependabot/*|deps/*" in content
    assert "Direct dependency-lock regeneration on main/master is forbidden." in content
    assert content.count(
        "python -m pip install --require-hashes -r .github/dependency-resolver.txt"
    ) == 2
    assert "python scripts/regenerate_hash_locks.py --write" in content
    assert content.count("python scripts/regenerate_hash_locks.py --check") >= 2
    assert "python scripts/install_locked.py --dev" in content
    assert "pytest -q" in content
    assert 'git push origin "HEAD:$TARGET_BRANCH"' in content
    assert "pull-requests: write" not in content
