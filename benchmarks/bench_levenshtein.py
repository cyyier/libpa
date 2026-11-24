#!/usr/bin/env python3
"""Isolated 4-way benchmark for levenshtein-pa:
  1. Pure Python (`for` loop)                      — CPython
  2. levenshtein-pa single-call (`levenshtein`)    — CPython + .so
  3. loop-template batch (`filter_batch`)          — CPython + .so
  4. Pure Pa Standalone (`pac build --mode prod`)  — Native (No Python)

Each mode runs in its own isolated child process (3 trials, median) so
wall-clock latency and Peak RSS are measured cleanly without cross-contamination.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "packages" / "levenshtein-pa"
PY_ROOT = PKG_DIR / "python"
SHARED_EXT = ".pyd" if sys.platform == "win32" else ".so"
EXE_EXT = ".exe" if sys.platform == "win32" else ""

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
    from levenshtein_pa import levenshtein

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

PURE_PA_BENCH = f'''from levenshtein import levenshtein_str


def _cand_for(i) -> str_view:
    if i % 10 != 0:
        return "unrelated_record_payload_entry_000001_suffix_data"
    r = i % 9
    if r == 0:
        return "algorithmic_optimisation_pipeline_v0"
    if r == 1:
        return "algorithmic_optimisation_pipeline_v1"
    if r == 2:
        return "algorithmic_optimisation_pipeline_v2"
    if r == 3:
        return "algorithmic_optimisation_pipeline_v3"
    return "algorithmic_optimisation_pipeline_v4"


def _run_filter(query, n, max_dist) -> int:
    qlen = len(query)
    hits = 0
    for i in range(n):
        cand = _cand_for(i)
        diff = qlen - len(cand)
        if diff < 0:
            diff = -diff
        if diff > max_dist:
            continue
        if levenshtein_str(query, cand) <= max_dist:
            hits += 1
    return hits


def main() -> int:
    hits = _run_filter(query="algorithmic_optimization_pipeline_v2", n={N_CANDIDATES}, max_dist={MAX_DIST})
    print(hits)
    return 0
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


def run_py_mode(mode: str, loop_dir: str) -> tuple[float, float, int, list]:
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


def run_pure_pa_binary(bin_path: Path) -> tuple[float, float, int]:
    times: list[float] = []
    rss_vals: list[float] = []
    hits = 0
    has_gnu_time = os.path.isfile("/usr/bin/time") and sys.platform.startswith("linux")
    for _ in range(TRIALS):
        if has_gnu_time:
            t0 = time.perf_counter()
            proc = subprocess.run(
                ["/usr/bin/time", "-v", str(bin_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            hits = int(proc.stdout.strip())
            m = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", proc.stderr)
            rss_mb = int(m.group(1)) / 1024.0 if m else 0.0
        else:
            t0 = time.perf_counter()
            out = subprocess.check_output([str(bin_path)], text=True)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            hits = int(out.strip())
            rss_mb = 0.0
        times.append(elapsed_ms)
        rss_vals.append(rss_mb)
    return statistics.median(times), statistics.median(rss_vals), hits


def main() -> None:
    pac = find_pac()
    if not list((PY_ROOT / "levenshtein_pa").glob(f"_native*{SHARED_EXT}")):
        subprocess.run([sys.executable, str(ROOT / "tools" / "build.py"), "build", "levenshtein-pa"], check=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        loop_so = tmp_path / f"custom_batch{SHARED_EXT}"
        subprocess.run(
            [
                pac, "build", "--shared", "--mode", "prod",
                "-I", str(PKG_DIR / "pa"),
                str(PKG_DIR / "loop-template" / "custom_batch.pa"),
                "-o", str(loop_so),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        pure_src = tmp_path / "bench_pure.pa"
        pure_src.write_text(PURE_PA_BENCH, encoding="utf-8")
        pure_bin = tmp_path / f"bench_pure{EXE_EXT}"
        subprocess.run(
            [
                pac, "build", "--mode", "prod",
                "-I", str(PKG_DIR / "pa"),
                str(pure_src),
                "-o", str(pure_bin),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        py_ms, py_rss, py_hits, py_sample = run_py_mode("python", tmp)
        sg_ms, sg_rss, sg_hits, sg_sample = run_py_mode("single", tmp)
        lt_ms, lt_rss, lt_hits, lt_sample = run_py_mode("loop_template", tmp)
        pa_ms, pa_rss, pa_hits = run_pure_pa_binary(pure_bin)

    assert py_hits == sg_hits == lt_hits == pa_hits, f"hit mismatch: {py_hits}, {sg_hits}, {lt_hits}, {pa_hits}"
    assert py_sample == sg_sample == lt_sample, f"sample mismatch: {py_sample}, {sg_sample}, {lt_sample}"

    pa_rss_str = f"{pa_rss:.1f} MB" if pa_rss > 0 else "n/a"
    print(f"Workload: Fuzzy filter (dist <= {MAX_DIST}) over {N_CANDIDATES:,} strings (~40B each, {py_hits:,} matches)")
    print(f"Methodology: isolated subprocess per mode, {TRIALS}-run median (time.perf_counter + Peak RSS)\n")
    print("| Implementation | Runtime | Median Time | Speedup | Peak RSS |")
    print("|---|---|---:|---:|---:|")
    print(f"| Pure Python (`for` loop) | CPython | {py_ms:.2f} ms | 1.0x | {py_rss:.1f} MB |")
    print(f"| `levenshtein-pa` single-call (`levenshtein_pa.levenshtein`) | CPython + `.so` | {sg_ms:.2f} ms | {py_ms / sg_ms:.1f}x | {sg_rss:.1f} MB |")
    print(f"| `loop-template` batch (`custom_batch.filter_batch`) | CPython + `.so` | {lt_ms:.2f} ms | {py_ms / lt_ms:.1f}x | {lt_rss:.1f} MB |")
    print(f"| Pure Pa Standalone (`pac build --mode prod`) | Native (No Python) | {pa_ms:.2f} ms | {py_ms / pa_ms:.1f}x | {pa_rss_str} |")


if __name__ == "__main__":
    main()
