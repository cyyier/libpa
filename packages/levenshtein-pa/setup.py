"""Build script for levenshtein-pa: compiles binding/export.pa into a platform-tagged wheel."""
from __future__ import annotations

import os
import shutil
import subprocess
import sysconfig
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.build_py import build_py as _build_py

PKG_ROOT = Path(__file__).resolve().parent
MOD_NAME = "levenshtein_pa"


def find_pac() -> str:
    env = os.environ.get("PA_PAC")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("pac")
    if found:
        return found
    sibling = PKG_ROOT.parents[2] / "pa" / ".venv" / "bin" / "pac"
    if sibling.is_file():
        return str(sibling)
    raise RuntimeError("`pac` compiler not found (install `pa-compiler` or set PA_PAC)")


class BinaryDistribution(Distribution):
    """Force setuptools/wheel to emit platform- & Python-ABI-specific wheel tags."""

    def has_ext_modules(self) -> bool:
        return True


class BuildPaPackage(_build_py):
    def run(self) -> None:
        super().run()
        pac = find_pac()
        ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
        pkg_build_dir = Path(self.build_lib) / MOD_NAME
        pkg_build_dir.mkdir(parents=True, exist_ok=True)

        # 1. Compile native CPython extension module directly into build_lib
        out_so = pkg_build_dir / f"_native{ext_suffix}"
        subprocess.run(
            [
                pac,
                "build",
                "--shared",
                "--mode",
                "prod",
                "-I",
                str(PKG_ROOT / "pa"),
                str(PKG_ROOT / "binding" / "export.pa"),
                "-o",
                str(out_so),
            ],
            check=True,
        )

        # 2. Bundle pure .pa sources inside wheel for `pa_lang.libs` static imports
        pa_dest = pkg_build_dir / "_pa"
        if pa_dest.exists():
            shutil.rmtree(pa_dest)
        shutil.copytree(PKG_ROOT / "pa", pa_dest)


setup(
    distclass=BinaryDistribution,
    cmdclass={"build_py": BuildPaPackage},
)
