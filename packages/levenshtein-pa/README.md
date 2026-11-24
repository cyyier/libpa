# `levenshtein-pa`

> **Origin & Attribution**
> - **Algorithm**: Classic Wagner–Fischer two-row Levenshtein edit distance (1965) & public-domain 64-bit FNV-1a hash specification.
> - **Implementation**: 100% clean-room implementation from scratch in pure **Pa** (`.pa`) — zero C/C++ boilerplate, zero garbage collection, deterministic stack/RAII memory layout, compiled via LLVM `-O2`.
> - **License**: MIT

## Benchmark vs. Original

**Workload**: Fuzzy match filter (`dist <= 4`) of a 36-byte query against **10,000 candidate strings** (~40 bytes each, 1,000 matches), verified for 100% identical `(index, distance)` output across all three runs.  
**Environment**: Linux x86-64 · CPython 3.12 · `pac 0.1.0 --mode prod` · isolated subprocess per mode, 3-run median (`time.perf_counter` + `resource.getrusage` Peak RSS).

| Implementation | Runtime | Median Time | Speedup | Peak RSS |
|---|---|---:|---:|---:|
| Pure Python (`for` loop) | CPython | 2,532.66 ms | 1.0x | 17.7 MB |
| `levenshtein-pa` single-call (`levenshtein_pa.levenshtein`) | CPython + `.so` | 62.60 ms | **40.5x** | 17.7 MB |
| `loop-template` batch (`custom_batch.filter_batch`) | CPython + `.so` | **4.78 ms** | **530.0x** | 19.1 MB |
| Pure Pa Standalone (`pac build --mode prod`) | Native (No Python) | **7.52 ms** | **336.8x** | **1.7 MB** |

> *Note: CPython rows include the ~17 MB interpreter baseline; the +1.4 MB in `loop-template` mode comes from the contiguous UTF-8 corpus buffer, CSR offsets, and pre-allocated zero-copy output arrays (zero per-item `PyObject*` allocations inside the native loop). The Pure Pa Standalone row includes full OS process startup (`fork`/`exec`) and drops Peak RSS to **1.7 MB** with zero Python runtime.*

Reproduce locally:

```bash
python benchmarks/bench_levenshtein.py
```

---

## Quick Usage

### 1. Python (Pre-compiled `.so` / `.pyd`, Zero `ctypes`)

```bash
pip install levenshtein-pa
```

```python
import levenshtein_pa

levenshtein_pa.levenshtein("kitten", "sitting")                            # 3
levenshtein_pa.levenshtein_bytes(b"kitten", b"sitting")                    # 3
levenshtein_pa.fnv1a_64("foobar")                                          # 0x85944171f73967e8
levenshtein_pa.levenshtein_batch("kitten", ["sitting", "mitten", "bitten"])  # [3, 1, 1]
```

### 2. Pure Pa Standalone (Zero Python Runtime)

After `pip install levenshtein-pa` (via the `pa_lang.libs` entry point) or with `-I packages/levenshtein-pa/pa`:

```python
from levenshtein import levenshtein_str, fnv1a_64_str
```

```bash
pac build --mode prod main.pa -o app
```

### 3. Custom Batch Loop (`loop-template/`)

To eliminate Python `for`-loop overhead on custom filtering/scoring workloads, edit only the marked loop body in [`loop-template/custom_batch.pa`](./loop-template/custom_batch.pa) and compile directly to an importable `.so`:

```bash
cd packages/levenshtein-pa/loop-template
pac build --shared --mode prod -I ../pa custom_batch.pa -o custom_batch.so
```
