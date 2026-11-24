# `libpa-text`

> **Origin & Attribution**
> - **Inspired by**: [`python-Levenshtein`](https://github.com/rapidfuzz/python-Levenshtein) & Python's [`difflib`](https://docs.python.org/3/library/difflib.html) (edit-distance API) + standard 64-bit FNV-1a specification.
> - **Implementation**: 100% clean-room reimplementation from scratch in pure **Pa** (`.pa`) — zero C/C++ boilerplate, zero garbage collection, deterministic stack/RAII memory layout, compiled via LLVM `-O2`.
> - **License**: MIT

## Benchmark vs. Original

**Workload**: Fuzzy match filter (`dist <= 4`) of a 36-byte query against **10,000 candidate strings** (~40 bytes each, 1,000 matches), verified for 100% identical `(index, distance)` output across all three runs.  
**Environment**: Linux x86-64 · CPython 3.12 · `pac 0.1.0 --mode prod` · isolated subprocess per mode, 3-run median (`time.perf_counter` + `resource.getrusage` Peak RSS).

| Implementation | Median Time | Speedup | Peak RSS |
|---|---:|---:|---:|
| Pure Python (`for` loop) | 2,536.15 ms | 1.0x | 17.6 MB |
| `libpa-text` single-call (`libpa.text.levenshtein`) | 62.46 ms | **40.6x** | 17.6 MB |
| `loop-template` batch (`custom_batch.filter_batch`) | **4.79 ms** | **529.6x** | 18.5 MB |

Reproduce locally:

```bash
python benchmarks/bench_text.py
```

---

## Quick Usage

### 1. Python (Pre-compiled `.so`, Zero `ctypes`)

```python
from libpa.text import fnv1a_64, levenshtein, levenshtein_batch, levenshtein_bytes

levenshtein("kitten", "sitting")                            # 3
levenshtein_bytes(b"kitten", b"sitting")                    # 3
fnv1a_64("foobar")                                          # 0x85944171f73967e8
levenshtein_batch("kitten", ["sitting", "mitten", "bitten"])  # [3, 1, 1]
```

### 2. Pure Pa Standalone (Zero Python Runtime)

```python
from levenshtein import levenshtein_str, fnv1a_64_str
```

```bash
pac build --mode prod -I packages/libpa-text/pa main.pa -o app
```

### 3. Custom Batch Loop (`loop-template/`)

To eliminate Python `for`-loop overhead on custom filtering/scoring workloads, edit only the marked loop body in [`loop-template/custom_batch.pa`](./loop-template/custom_batch.pa) and compile directly to an importable `.so`:

```bash
cd packages/libpa-text/loop-template
pac build --shared --mode prod -I ../pa custom_batch.pa -o custom_batch.so
```
