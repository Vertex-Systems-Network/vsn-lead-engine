import re
import tomllib
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/"requirements.txt"
PYPROJECT=ROOT/"pyproject.toml"
WORKFLOW_DIR=ROOT/".github/workflows"


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+","-",name).lower()


def _locked_versions() -> dict[str,str]:
    result={}
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line, line
        name,version=line.split("==",1)
        normalized=_normalize(name)
        assert normalized not in result, normalized
        assert version and not any(token in version for token in ["<",">","~","*"]), line
        result[normalized]=version
    return result


def test_lock_is_exact_and_covers_all_declared_dependencies():
    locked=_locked_versions()
    assert len(locked)==35

    project=tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    declared=list(project["dependencies"])
    for values in project.get("optional-dependencies",{}).values():
        declared.extend(values)

    for requirement in declared:
        name=re.split(r"[<>=!~\[; ]",requirement,1)[0]
        assert _normalize(name) in locked, requirement


def test_build_backend_is_exactly_pinned():
    data=tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert data["build-system"]["requires"] == [
        "setuptools==84.0.0",
        "wheel==0.48.0",
    ]


def test_every_editable_install_uses_dependency_lock():
    offenders=[]
    constrained=0
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "python -m pip install" not in line or "-e " not in line:
                continue
            if "-c requirements.txt" not in line:
                offenders.append(f"{path.name}: {line.strip()}")
            constrained+=1

    assert constrained >= 1
    assert offenders == []


def test_primary_workflow_runs_pip_check_for_ci_and_production():
    content=(WORKFLOW_DIR/"lead-engine.yml").read_text(encoding="utf-8")
    assert content.count("python -m pip check") == 2
