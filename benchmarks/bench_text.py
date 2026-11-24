#!/usr/bin/env python3
"""Isolated 3-way benchmark for libpa-text:
  1. Pure Python DP loop
  2. libpa.text single-call (Python for-loop calling native levenshtein())
  3. loop-template batch (custom_batch.filter_batch in 1 native call)

Each mode runs in its own isolated Python subprocess (3 trials, median) so
wall-clock latency (time.perf_counter) and Peak RSS (resource.getrusage) are
measured cleanly without cross-contamination.
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "packages" / "libpa-text"
PY_ROOT = PKG_DIR / "python"
SHARED_EXT = ".pyd" if sys.platform == "win32" else ".so"

N_CANDIDATES = 10_000
MAX_DIST = 4
TRIALS = 3

WORKER_CODE = r'''
import array, json, sys, time, tracemalloc

try:
    import resource
except ImportError:
    resource = None

if resource is None:
    tracemalloc.start()


def peak_rss_mb() -> float:
    if resource is not None:
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports KiB
        return raw / (1024.0 * 1024.0) if sys.platform == "darwin" else raw / 1024.0
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024.0 * 1024.0)
    except ImportError:
        _, peak = tracemalloc.get_traced_memory()
        return peak / (1024.0 * 1024.0)


mode, py_root, loop_dir, n_cand, max_dist = (
    sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
)

query = "algorithmic_optimization_pipeline_v2"
# 10% close variants (distance 1..4), 90% longer/different strings
corpus_list = []
for i in range(n_cand):
    if i % 10 == 0:
        corpus_list.append(f"algorithmic_optimisation_pipeline_v{i % 9}")
    else:
        corpus_list.append(f"unrelated_record_payload_entry_{i:06d}_suffix_data")


def py_levenshtein(a: str, b: str) -> int:
    ab = a.encode("utf-8")
    bb = b.encode("utf-8")
    n, m = len(ab), len(bb)
    prev = list(range(m + 1))
    curr = [0] * (m + 1)
    for i in range(1, n + 1):
        curr[0] = i
        ai = ab[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ai == bb[j - 1] else 1
            d = prev[j] + 1
            ins = curr[j - 1] + 1
            sub = prev[j - 1] + cost
            best = d if d < ins else ins
            curr[j] = sub if sub < best else best
        prev, curr = curr, prev
    return prev[m]


if mode == "python":
    t0 = time.perf_counter()
    hits = []
    for idx, s in enumerate(corpus_list):
        d = py_levenshtein(query, s)
        if d <= max_dist:
            hits.append((idx, d))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

elif mode == "single":
    sys.path.insert(0, py_root)
    from libpa.text import levenshtein

    t0 = time.perf_counter()
    hits = []
    for idx, s in enumerate(corpus_list):
        d = levenshtein(query, s)
        if d <= max_dist:
            hits.append((idx, d))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

elif mode == "loop_template":
    sys.path.insert(0, loop_dir)
    import custom_batch

    q_bytes = query.encode("utf-8")
    chunks = [s.encode("utf-8") for s in corpus_list]
    corpus_bytes = b"".join(chunks)
    offsets = array.array("q", [0])
    pos = 0
    for b in chunks:
        pos += len(b)
        offsets.append(pos)
    out_idx = array.array("q", [0] * n_cand)
    out_dist = array.array("q", [0] * n_cand)

    t0 = time.perf_counter()
    n_hits = custom_batch.filter_batch(q_bytes, corpus_bytes, offsets, max_dist, out_idx, out_dist)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    hits = [(out_idx[i], out_dist[i]) for i in range(n_hits)]

else:
    raise SystemExit(f"unknown mode: {mode}")

rss_mb = peak_rss_mb()
print(json.dumps({
    "mode": mode,
    "ms": elapsed_ms,
    "rss_mb": rss_mb,
    "hits": len(hits),
    "sample": hits[:5],
}))
'''


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
    raise SystemExit("error: `pac` not found")


def run_mode(mode: str, loop_dir: str) -> tuple[float, float, int, list]:
    times: list[float] = []
    rss_vals: list[float] = []
    hits = 0
    sample: list = []
    for _ in range(TRIALS):
        out = subprocess.check_output(
            [sys.executable, "-c", WORKER_CODE, mode, str(PY_ROOT), loop_dir, str(N_CANDIDATES), str(MAX_DIST)],
            text=True,
        )
        rec = json.loads(out.strip())
        times.append(rec["ms"])
        rss_vals.append(rec["rss_mb"])
        hits = rec["hits"]
        sample = rec["sample"]
    return statistics.median(times), statistics.median(rss_vals), hits, sample


def main() -> None:
    pac = find_pac()
    so_text = PY_ROOT / "libpa" / "text" / f"_text{SHARED_EXT}"
    if not so_text.is_file():
        subprocess.run([sys.executable, str(ROOT / "tools" / "build.py"), "build", "libpa-text"], check=True)

    with tempfile.TemporaryDirectory() as tmp:
        loop_so = Path(tmp) / f"custom_batch{SHARED_EXT}"
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
                str(loop_so),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        py_ms, py_rss, py_hits, py_sample = run_mode("python", tmp)
        sg_ms, sg_rss, sg_hits, sg_sample = run_mode("single", tmp)
        lt_ms, lt_rss, lt_hits, lt_sample = run_mode("loop_template", tmp)

    assert py_hits == sg_hits == lt_hits, f"hit count mismatch: {py_hits}, {sg_hits}, {lt_hits}"
    assert py_sample == sg_sample == lt_sample, f"sample mismatch: {py_sample}, {sg_sample}, {lt_sample}"

    print(f"Workload: Fuzzy filter (dist <= {MAX_DIST}) over {N_CANDIDATES:,} strings (~40B each, {py_hits:,} matches)")
    print(f"Methodology: isolated subprocess per mode, {TRIALS}-run median (time.perf_counter + getrusage RSS)\n")
    print("| Implementation | Median Time | Speedup | Peak RSS |")
    print("|---|---:|---:|---:|")
    print(f"| Pure Python (`for` loop) | {py_ms:.2f} ms | 1.0x | {py_rss:.1f} MB |")
    print(f"| `libpa.text.levenshtein` (single-call loop) | {sg_ms:.2f} ms | {py_ms / sg_ms:.1f}x | {sg_rss:.1f} MB |")
    print(f"| `loop-template` (`custom_batch.filter_batch`) | {lt_ms:.2f} ms | {py_ms / lt_ms:.1f}x | {lt_rss:.1f} MB |")


if __name__ == "__main__":
    main()
