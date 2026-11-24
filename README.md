# libpa

Native LLVM-compiled acceleration libraries for Python hot loops—and zero-dependency static modules for pure [Pa](https://palang.dev) projects.

## Design Principles

- **Single source of truth**: `packages/<pkg>/pa/` holds 100% pure `.pa` kernels (no `@export`, no Python runtime dependency). `packages/<pkg>/binding/` is a thin `@export` layer compiled with `pac build --shared`.
- **Granular PEP 420 packages**: Every domain ships as an independent wheel (`pip install libpa-text`, etc.) sharing the `libpa.*` namespace with no root `__init__.py`.
- **Eliminate Python `for`-loop overhead**: Each sub-package ships a `loop-template/` with pre-wired zero-copy In/Out buffers so you (or your AI agent) can edit only the inner `.pa` loop and compile a custom `.so` in one command.
- **Standardized Origin & Benchmark Card**: Every sub-package `README.md` opens with an **Origin & Attribution** block (stating the inspiring Python library/algorithm, clean-room pure-Pa implementation, and MIT license) followed by a reproducible **Benchmark vs. Original** table (Pure Python vs. single-call `libpa.*` vs. `loop-template` batch, reporting wall-clock median, speedup, and isolated Peak RSS).

## Repository Layout

```text
libpa/
├── packages/
│   ├── libpa-text/               # Fuzzy matching (Levenshtein) & sequence hashing (FNV-1a 64)
│   │   ├── pa/                   # Pure .pa kernels (zero Python dependency)
│   │   ├── binding/              # Thin @export boundary + input validation
│   │   ├── python/libpa/text/    # PEP 420 Python package (__init__.py + .pyi stubs)
│   │   ├── loop-template/        # Customizable zero-copy batch loop template
│   │   ├── tests/                # Pure Pa standalone tests + Python differential tests
│   │   └── pyproject.toml
│   └── (planned: libpa-spatial, libpa-graph, libpa-stats)
├── tools/
│   └── build.py                  # Build, check, and test one or all packages
├── skills/
│   └── libpa-pkg/SKILL.md        # Reusable AI agent skill for scaffolding & verifying new sub-packages
└── benchmarks/
    └── bench_text.py             # Wall-clock & Peak RSS comparison vs Pure Python
```

## Quickstart

### 1. Build & Test All Packages Locally

```bash
python tools/build.py build
python tools/build.py test
```

### 2. Use from Python (Zero `ctypes` Boilerplate)

```python
from libpa.text import levenshtein, levenshtein_bytes, fnv1a_64, levenshtein_batch

dist = levenshtein("kitten", "sitting")          # 3
h = fnv1a_64("hello world")                      # 64-bit FNV-1a hash
dists = levenshtein_batch("kitten", ["sitting", "mitten", "kitchen"])
```

### 3. Static Import in Pure Pa (Zero Python Dependency)

```python
from levenshtein import levenshtein_bytes, fnv1a_64_bytes
```

```bash
pac build --mode prod -I packages/libpa-text/pa main.pa -o app
```

### 4. Customize a High-Frequency Batch Loop (`loop-template/`)

When calling a single function millions of times from a Python `for` loop, move the loop into Pa using the package's `loop-template/`:

```bash
cd packages/libpa-text/loop-template
# Edit the marked loop body in custom_batch.pa, then compile:
pac build --shared --mode prod -I ../pa custom_batch.pa -o custom_batch.so
```

See [packages/libpa-text/loop-template/README.md](packages/libpa-text/loop-template/README.md) for details.
