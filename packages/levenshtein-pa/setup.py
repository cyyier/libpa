"""Build script for levenshtein-pa: compiles binding/export.pa into a platform-tagged wheel.

On Python >= 3.11, builds a single `cp311-abi3` wheel per OS/arch using `pac build --shared --abi3`
(`Py_LIMITED_API = 0x030B0000`), which works across Python 3.11, 3.12, 3.13, 3.14, and future 3.x.
On Python 3.10, builds a standard `cp310-cp310` wheel (since `Py_buffer` entered abi3 in 3.11).
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.build_py import build_py as _build_py
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

PKG_ROOT = Path(__file__).resolve().parent
MOD_NAME = "levenshtein_pa"
USE_ABI3 = sys.version_info >= (3, 11)


def find_pac_cmd() -> list[str]:
    env = os.environ.get("PA_PAC")
    if env and os.path.isfile(env):
        return [env]
    if importlib.util.find_spec("pa_lang") is not None:
        return [sys.executable, "-m", "pa_lang.cli"]
    found = shutil.which("pac")
    if found:
        return [found]
    sibling = PKG_ROOT.parents[2] / "pa" / ".venv" / "bin" / "pac"
    if sibling.is_file():
        return [str(sibling)]
    raise RuntimeError("`pac` compiler not found (install `pa-compiler` or set PA_PAC)")


class BinaryDistribution(Distribution):
    """Force setuptools/wheel to emit platform- & Python-ABI-specific wheel tags."""

    def has_ext_modules(self) -> bool:
        return True


class BdistWheelAbi3(_bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()
        if USE_ABI3 and python.startswith("cp"):
            return "cp311", "abi3", plat
        return python, abi, plat


class BuildPaPackage(_build_py):
    def run(self) -> None:
        super().run()
        pac_cmd = find_pac_cmd()
        if USE_ABI3:
            ext_suffix = ".pyd" if sys.platform == "win32" else ".abi3.so"
        else:
            ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or (".pyd" if sys.platform == "win32" else ".so")

        pkg_build_dir = (Path(self.build_lib) / MOD_NAME).resolve()
        pkg_build_dir.mkdir(parents=True, exist_ok=True)

        # 1. Compile native CPython extension module directly into build_lib
        out_so = pkg_build_dir / f"_native{ext_suffix}"
        cmd = [
            *pac_cmd,
            "build",
            "--shared",
            *(["--abi3"] if USE_ABI3 else []),
            "--mode",
            "prod",
            "-I",
            str(PKG_ROOT / "pa"),
            str(PKG_ROOT / "binding" / "export.pa"),
            "-o",
            str(out_so),
        ]
        subprocess.run(cmd, check=True)

        # 2. Bundle pure .pa sources inside wheel for `pa_lang.libs` static imports
        pa_dest = pkg_build_dir / "_pa"
        if pa_dest.exists():
            shutil.rmtree(pa_dest)
        shutil.copytree(PKG_ROOT / "pa", pa_dest)


setup(
    distclass=BinaryDistribution,
    cmdclass={"build_py": BuildPaPackage, "bdist_wheel": BdistWheelAbi3},
)
