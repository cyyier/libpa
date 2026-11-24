#!/usr/bin/env python3
"""Unified Monorepo build, check, and test runner for libpa packages.

Usage:
    python tools/build.py check [pkg]
    python tools/build.py build [pkg] [--mode dev|prod]
    python tools/build.py test  [pkg]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES_DIR = ROOT / "packages"
SHARED_EXT = ".pyd" if sys.platform == "win32" else ".so"


def find_pac() -> str:
    env = os.environ.get("PA_PAC")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("pac")
    if found:
        return found
    sibling = ROOT.parent / "pa" / ".venv" / "bin" / "pac"
    if sibling.is_file():
        return str(sibling)
    raise SystemExit("error: `pac` compiler not found (install `pa-lang` or set PA_PAC)")


def discover_packages(target: str | None = None) -> list[Path]:
    pkgs = sorted(
        p for p in PACKAGES_DIR.iterdir()
        if p.is_dir() and (p / "pyproject.toml").is_file() and (p / "binding" / "export.pa").is_file()
    )
    if target:
        pkgs = [p for p in pkgs if p.name == target]
        if not pkgs:
            raise SystemExit(f"error: unknown package '{target}'")
    return pkgs


def mod_name_for(pkg_dir: Path) -> str:
    # packages/libpa-text -> "text"
    return pkg_dir.name.removeprefix("libpa-").replace("-", "_")


def run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env, cwd=cwd)


def cmd_check(pac: str, pkgs: list[Path]) -> None:
    for pkg in pkgs:
        pa_dir = pkg / "pa"
        targets = sorted(pa_dir.glob("*.pa")) + [pkg / "binding" / "export.pa"]
        loop_pa = pkg / "loop-template" / "custom_batch.pa"
        if loop_pa.is_file():
            targets.append(loop_pa)
        for f in targets:
            run([pac, "check", "-I", str(pa_dir), str(f)])


def cmd_build(pac: str, pkgs: list[Path], mode: str = "prod") -> None:
    for pkg in pkgs:
        mod = mod_name_for(pkg)
        pa_dir = pkg / "pa"
        export_pa = pkg / "binding" / "export.pa"
        out_dir = pkg / "python" / "libpa" / mod
        out_dir.mkdir(parents=True, exist_ok=True)
        out_so = out_dir / f"_{mod}{SHARED_EXT}"
        run([pac, "check", "--mode", mode, "-I", str(pa_dir), str(export_pa)])
        run([pac, "build", "--shared", "--mode", mode, "-I", str(pa_dir), str(export_pa), "-o", str(out_so)])


def cmd_test(pac: str, pkgs: list[Path]) -> None:
    cmd_build(pac, pkgs, mode="prod")
    py = sys.executable
    for pkg in pkgs:
        pa_dir = pkg / "pa"
        tests_dir = pkg / "tests"

        # 1. Pure Pa standalone tests (zero Python runtime)
        for pa_test in sorted(tests_dir.glob("test_*.pa")):
            with tempfile.TemporaryDirectory() as tmp:
                bin_path = Path(tmp) / pa_test.stem
                run([pac, "check", "-I", str(pa_dir), str(pa_test)])
                run([pac, "build", "--mode", "dev", "-I", str(pa_dir), str(pa_test), "-o", str(bin_path)])
                run([str(bin_path)])

        # 2. Compile loop-template/custom_batch.pa and verify importability
        loop_dir = pkg / "loop-template"
        loop_pa = loop_dir / "custom_batch.pa"
        if loop_pa.is_file():
            with tempfile.TemporaryDirectory() as tmp:
                so_path = Path(tmp) / f"custom_batch{SHARED_EXT}"
                run([pac, "check", "-I", str(pa_dir), str(loop_pa)])
                run([pac, "build", "--shared", "--mode", "prod", "-I", str(pa_dir), str(loop_pa), "-o", str(so_path)])

        # 3. Python differential tests via pytest
        env = dict(os.environ)
        py_root = str(pkg / "python")
        env["PYTHONPATH"] = py_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["PA_PAC"] = pac
        run([py, "-m", "pytest", "-v", str(tests_dir)], env=env)


def main() -> int:
    ap = argparse.ArgumentParser(description="libpa monorepo build & test tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("check", "test"):
        sp = sub.add_parser(name)
        sp.add_argument("package", nargs="?", help="package name (e.g. libpa-text); omit for all")

    bp = sub.add_parser("build")
    bp.add_argument("package", nargs="?", help="package name (e.g. libpa-text); omit for all")
    bp.add_argument("--mode", choices=("dev", "prod"), default="prod")

    args = ap.parse_args()
    pac = find_pac()
    pkgs = discover_packages(args.package)

    if args.cmd == "check":
        cmd_check(pac, pkgs)
    elif args.cmd == "build":
        cmd_build(pac, pkgs, mode=args.mode)
    elif args.cmd == "test":
        cmd_test(pac, pkgs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
