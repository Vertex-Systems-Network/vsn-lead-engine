from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run([sys.executable,"-m","pip",*args],cwd=ROOT,check=True)


def main() -> int:
    parser=argparse.ArgumentParser(
        description="Install the reviewed VSN Lead Engine dependency surface."
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Install runtime plus test/development dependencies.",
    )
    args=parser.parse_args()

    if sys.version_info[:2] != (3,12):
        raise SystemExit(
            f"Locked CI/runtime surface requires CPython 3.12; got {platform.python_version()}."
        )
    if not sys.platform.startswith("linux"):
        raise SystemExit(
            f"Locked CI/runtime surface requires Linux; got {sys.platform}."
        )

    run("install","--require-hashes","-r","requirements-bootstrap.txt")
    lock="requirements-dev.txt" if args.dev else "requirements-runtime.txt"
    run("install","--require-hashes","-r",lock)
    run(
        "install",
        "--no-deps",
        "--no-build-isolation",
        "-e",
        ".",
    )
    run("check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
