"""levenshtein_pa — Native LLVM-compiled fuzzy text matching and hashing kernels."""
from __future__ import annotations

import array
from collections.abc import Sequence
from pathlib import Path

from . import _native

__all__ = [
    "levenshtein",
    "levenshtein_bytes",
    "levenshtein_batch",
    "fnv1a_64",
]


def _pa_libs_dir() -> str:
    """Entry point for `pa_lang.libs` so pure Pa projects can `from levenshtein import ...` directly."""
    bundled = Path(__file__).resolve().parent / "_pa"
    if bundled.is_dir():
        return str(bundled)
    return str(Path(__file__).resolve().parents[2] / "pa")


def levenshtein(a: str, b: str) -> int:
    """Return the UTF-8 byte Levenshtein edit distance between two strings."""
    if not isinstance(a, str) or not isinstance(b, str):
        raise TypeError("levenshtein() expects two str arguments")
    return _native.levenshtein_str_export(a, b)


def levenshtein_bytes(
    a: bytes | bytearray | memoryview,
    b: bytes | bytearray | memoryview,
) -> int:
    """Return the Levenshtein edit distance between two contiguous byte buffers."""
    return _native.levenshtein_bytes_export(a, b)


def fnv1a_64(data: str | bytes | bytearray | memoryview) -> int:
    """Return the 64-bit unsigned FNV-1a hash of a string or byte buffer."""
    if isinstance(data, str):
        return _native.fnv1a_64_str_export(data)
    return _native.fnv1a_64_bytes_export(data)


def levenshtein_batch(query: str, candidates: Sequence[str]) -> list[int]:
    """Compute Levenshtein distance from `query` to every string in `candidates` in one native call."""
    if not isinstance(query, str):
        raise TypeError("query must be a str")
    n = len(candidates)
    if n == 0:
        return []
    q_bytes = query.encode("utf-8")
    chunks: list[bytes] = []
    offsets = array.array("q", [0])
    pos = 0
    for item in candidates:
        if not isinstance(item, str):
            raise TypeError("all candidates must be str")
        b = item.encode("utf-8")
        chunks.append(b)
        pos += len(b)
        offsets.append(pos)
    corpus = b"".join(chunks)
    out = array.array("q", [0] * n)
    rc = _native.levenshtein_batch_export(q_bytes, corpus, offsets, out)
    if rc < 0:
        raise ValueError("invalid corpus/offsets passed to native batch kernel")
    return out.tolist()
