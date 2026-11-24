"""Differential & integration tests for libpa.text and its loop-template."""
from __future__ import annotations

import array
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import libpa
from libpa.text import fnv1a_64, levenshtein, levenshtein_batch, levenshtein_bytes

PKG_DIR = Path(__file__).resolve().parent.parent
SHARED_EXT = ".pyd" if sys.platform == "win32" else ".so"


def ref_levenshtein_bytes(a: bytes, b: bytes) -> int:
    n, m = len(a), len(b)
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m]


def ref_fnv1a_64(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for b in data:
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def test_pep420_namespace_package():
    # PEP 420: libpa has no __init__.py (so __file__ is None)
    assert getattr(libpa, "__file__", None) is None
    assert not (PKG_DIR / "python" / "libpa" / "__init__.py").exists()


@pytest.mark.parametrize(
    "a,b",
    [
        ("", ""),
        ("", "abc"),
        ("abc", ""),
        ("same", "same"),
        ("kitten", "sitting"),
        ("flaw", "lawn"),
        ("saturday", "sunday"),
        ("你好世界", "你好中国"),
        ("emoji🚀test", "emoji🔥test"),
    ],
)
def test_levenshtein_parity(a: str, b: str):
    expected = ref_levenshtein_bytes(a.encode("utf-8"), b.encode("utf-8"))
    assert levenshtein(a, b) == expected
    assert levenshtein_bytes(a.encode("utf-8"), b.encode("utf-8")) == expected


@pytest.mark.parametrize("s", ["", "a", "foobar", "hello world", "pa-lang-0.1.0", "中文UTF8"])
def test_fnv1a_64_parity(s: str):
    raw = s.encode("utf-8")
    expected = ref_fnv1a_64(raw)
    assert fnv1a_64(s) == expected
    assert fnv1a_64(raw) == expected
    assert fnv1a_64(memoryview(raw)) == expected


def test_levenshtein_batch_parity():
    query = "kitten"
    candidates = ["sitting", "mitten", "", "kitten", "bitten", "completely_different"]
    expected = [ref_levenshtein_bytes(query.encode(), c.encode()) for c in candidates]
    assert levenshtein_batch(query, candidates) == expected
    assert levenshtein_batch(query, []) == []


def test_input_validation_errors():
    with pytest.raises(TypeError):
        levenshtein(123, "abc")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        levenshtein_batch("a", ["ok", 42])  # type: ignore[list-item]


def test_loop_template_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pac = os.environ.get("PA_PAC") or str(PKG_DIR.parent.parent.parent / "pa" / ".venv" / "bin" / "pac")
    so_path = tmp_path / f"custom_batch{SHARED_EXT}"
    subprocess.run(
        [
            pac,
            "build",
            "--shared",
            "--mode",
            "prod",
            "-I",
            str(PKG_DIR / "pa"),
            str(PKG_DIR / "loop-template" / "custom_batch.pa"),
            "-o",
            str(so_path),
        ],
        check=True,
    )
    assert so_path.is_file()

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    mod = importlib.import_module("custom_batch")

    words = [b"sitting", b"mitten", b"completely_different", b"bitten"]
    corpus = b"".join(words)
    offsets = array.array("q", [0])
    for w in words:
        offsets.append(offsets[-1] + len(w))
    out_idx = array.array("q", [0] * len(words))
    out_dist = array.array("q", [0] * len(words))

    hits = mod.filter_batch(b"kitten", corpus, offsets, 2, out_idx, out_dist)
    assert hits == 2
    assert [(out_idx[i], out_dist[i]) for i in range(hits)] == [(1, 1), (3, 1)]

    # Invalid offsets length must return -1 safely (no segfault)
    bad_offsets = array.array("q", [0, 1])
    assert mod.filter_batch(b"kitten", corpus, bad_offsets, 2, out_idx, out_dist) == -1
