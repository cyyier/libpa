# libpa

Monorepo of native LLVM-compiled `*-pa` acceleration packages for Python hot loops—and zero-dependency static modules for pure [Pa](https://palang.dev) projects.

## Design Principles

- **Zero syntax sugar, zero implicit magic**: Every kernel is flat, deterministic, and auditable with standard `ast.parse`.
- **Single source of truth**: `packages/<name>-pa/pa/` holds 100% pure `.pa` kernels (no `@export`, no Python runtime dependency). `packages/<name>-pa/binding/` is a thin `@export` layer compiled with `pac build --shared`.
- **1:1 intuitive PyPI naming**: `pip install <name>-pa` → `import <name>_pa` (e.g., `pip install levenshtein-pa` → `import levenshtein_pa`). Each package ships pre-compiled platform wheels so end users need neither `pa-lang` nor LLVM, while also registering a `pa_lang.libs` entry point for zero-config static imports in pure Pa projects.
- **Eliminate Python `for`-loop overhead**: Each sub-package ships a `loop-template/` with pre-wired zero-copy In/Out buffers so you (or your AI agent) can edit only the inner `.pa` loop and compile a custom `.so` in one command.
- **Standardized Origin & Benchmark Card**: Every sub-package `README.md` opens with an **Origin & Attribution** block followed by a reproducible 4-row **Benchmark vs. Original** table (Pure Python vs. single-call `<name>_pa` vs. `loop-template` batch vs. Pure Pa Standalone native binary, reporting runtime, wall-clock median, speedup, and isolated Peak RSS).

## Repository Layout

```text
libpa/
├── .github/workflows/
│   └── release.yml                # Tag-triggered cibuildwheel + PyPI Trusted Publishing
├── packages/
│   ├── levenshtein-pa/            # `pip install levenshtein-pa` -> `import levenshtein_pa`
│   │   ├── pa/                    # Pure .pa kernels (zero Python dependency)
│   │   ├── binding/               # Thin @export boundary + input validation
│   │   ├── python/levenshtein_pa/ # 1:1 Python package (__init__.py + .pyi stubs)
│   │   ├── loop-template/         # Customizable zero-copy batch loop template
│   │   ├── tests/                 # Pure Pa standalone tests + Python differential tests
│   │   ├── setup.py               # Platform-tagged wheel builder via `pac build --shared`
│   │   └── pyproject.toml
│   └── (planned: utm-pa, kdtree-pa, bm25-pa)
├── tools/
│   └── build.py                   # Check, build, test, and wheel one or all packages
├── skills/
│   └── libpa-pkg/SKILL.md         # Reusable AI agent skill for scaffolding & verifying new packages
└── benchmarks/
    └── bench_levenshtein.py       # Isolated 3-way wall-clock & Peak RSS benchmark
```

## Quickstart

### 1. Build & Test All Packages Locally

```bash
python tools/build.py build
python tools/build.py test
python tools/build.py wheel levenshtein-pa
```

### 2. Use from Python (Zero `ctypes` Boilerplate)

```bash
pip install levenshtein-pa
```

```python
import levenshtein_pa

dist = levenshtein_pa.levenshtein("kitten", "sitting")            # 3
h = levenshtein_pa.fnv1a_64("hello world")                        # 64-bit FNV-1a hash
dists = levenshtein_pa.levenshtein_batch("kitten", ["sitting", "mitten", "kitchen"])
```

### 3. Static Import in Pure Pa (Zero Python Dependency)

After `pip install levenshtein-pa` (auto-discovered via `pa_lang.libs`) or with `-I packages/levenshtein-pa/pa`:

```python
from levenshtein import levenshtein_bytes, fnv1a_64_bytes
```

```bash
pac build --mode prod main.pa -o app
```

### 4. Customize a High-Frequency Batch Loop (`loop-template/`)

```bash
cd packages/levenshtein-pa/loop-template
# Edit the marked loop body in custom_batch.pa, then compile:
pac build --shared --mode prod -I ../pa custom_batch.pa -o custom_batch.so
```

See [packages/levenshtein-pa/loop-template/README.md](packages/levenshtein-pa/loop-template/README.md) for details.
