import re
import tomllib
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"requirements-runtime.txt"
DEV=ROOT/"requirements-dev.txt"
BOOTSTRAP=ROOT/"requirements-bootstrap.txt"
PYPROJECT=ROOT/"pyproject.toml"
WORKFLOW_DIR=ROOT/".github/workflows"
INSTALLER=ROOT/"scripts/install_locked.py"

HASHED_RE=re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s]+) "
    r"--hash=sha256:(?P<hash>[0-9a-f]{64})$"
)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+","-",name).lower()


def _hashed_rows(path: Path) -> dict[str,tuple[str,str]]:
    result={}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        match=HASHED_RE.fullmatch(line)
        assert match, f"{path.name}: {line}"
        normalized=_normalize(match.group("name"))
        assert normalized not in result, normalized
        result[normalized]=(match.group("version"),match.group("hash"))
    return result


def test_hash_lock_surfaces_are_exact_and_expected_size():
    runtime=_hashed_rows(RUNTIME)
    dev=_hashed_rows(DEV)
    bootstrap=_hashed_rows(BOOTSTRAP)

    assert len(runtime)==30
    assert len(dev)==5
    assert len(bootstrap)==4
    assert set(dev)=={"iniconfig","packaging","pluggy","pygments","pytest"}
    assert set(bootstrap)=={"packaging","pip","setuptools","wheel"}
    assert "-r requirements-runtime.txt" in DEV.read_text(encoding="utf-8")


def test_hash_locks_cover_all_declared_project_dependencies():
    runtime=_hashed_rows(RUNTIME)
    dev=_hashed_rows(DEV)
    locked=set(runtime)|set(dev)

    project=tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    declared=list(project["dependencies"])
    for values in project.get("optional-dependencies",{}).values():
        declared.extend(values)

    for requirement in declared:
        name=re.split(r"[<>=!~\[; ]",requirement,1)[0]
        assert _normalize(name) in locked, requirement


def test_build_backend_is_exactly_pinned_and_hash_locked():
    data=tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert data["build-system"]["requires"] == [
        "setuptools==84.0.0",
        "wheel==0.48.0",
    ]
    bootstrap=_hashed_rows(BOOTSTRAP)
    assert bootstrap["setuptools"][0]=="84.0.0"
    assert bootstrap["wheel"][0]=="0.48.0"


def test_unhashed_legacy_lock_is_retired():
    assert not (ROOT/"requirements.txt").exists()


def test_installer_is_fail_closed_and_hash_enforced():
    content=INSTALLER.read_text(encoding="utf-8")
    assert '"--require-hashes"' in content
    assert '"--no-deps"' in content
    assert '"--no-build-isolation"' in content
    assert 'run("check")' in content
    assert "sys.version_info[:2] != (3,12)" in content
    assert 'not sys.platform.startswith("linux")' in content


def test_project_installing_workflows_use_locked_installer_only():
    installer_calls=0
    offenders=[]
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped=line.strip()
            if "python scripts/install_locked.py" in stripped:
                installer_calls+=1
            if "python -m pip install" in stripped and "-e " in stripped:
                offenders.append(f"{path.name}: {stripped}")

    assert installer_calls >= 8
    assert offenders == []


def test_primary_workflow_separates_ci_and_runtime_surfaces():
    content=(WORKFLOW_DIR/"lead-engine.yml").read_text(encoding="utf-8")
    assert "python scripts/install_locked.py --dev" in content
    assert "python scripts/install_locked.py\n" in content
    assert "Resolve P59 artifact hashes" not in content
