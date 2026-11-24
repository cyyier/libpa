---
name: libpa-pkg
description: Scaffold, build, differentially test, benchmark, and package a new `<name>-pa` sub-package in the libpa monorepo (pure .pa core, thin @export binding, 1:1 `<name>_pa` Python package with .pyi stubs, platform wheel setup.py, loop-template, Origin & Benchmark Card, and isolated 4-way benchmark). Use when creating, updating, or verifying any `packages/*-pa` sub-package.
---

# libpa-pkg

End-to-end procedure for creating, verifying, benchmarking, and packaging a granular `<name>-pa` sub-package (`packages/<name>-pa/`).

> **Prerequisites**: This skill builds on Pa's bundled `pa-coder` language skill. Install `pa-compiler` and load the base skills first so your agent has the full Pa syntax and compiler gate rules:
> ```bash
> pip install pa-compiler
> pac skill --install claude   # or: cursor | codex | copilot | antigravity
> ```

## 1. Required Sub-Package Layout (1:1 `<name>-pa` → `import <name>_pa`)

Choose a clean, generic algorithm or protocol name (`levenshtein-pa`, `utm-pa`, `kdtree-pa`, `bm25-pa` — avoid third-party trademarks). Let `<mod> = <name>_pa`:

```text
packages/<name>-pa/
├── pa/
│   └── <core>.pa              # 100% pure .pa (NO @export, NO Python runtime deps)
├── binding/
│   └── export.pa              # Thin @export boundary + input/bounds validation
├── python/
│   └── <mod>/                 # 1:1 Python import name matching PyPI distribution
│       ├── __init__.py        # Pythonic wrappers, _pa_libs_dir(), TypeError/ValueError
│       ├── __init__.pyi       # Complete PEP 484 type stubs
│       └── py.typed           # Empty PEP 561 marker
├── loop-template/
│   ├── custom_batch.pa        # Pre-wired zero-copy In/Out + marked user loop body
│   ├── pyproject.toml         # Standalone template package metadata
│   └── README.md              # 3-step edit -> pac build --shared -> import guide
├── tests/
│   ├── test_<core>_pure.pa    # Pure Pa standalone test binary (zero Python runtime)
│   └── test_<mod>.py          # Pytest differential suite + loop-template E2E
├── setup.py                   # Compiles `_native<EXT_SUFFIX>` + bundles `_pa/*.pa` into wheel
├── pyproject.toml             # PEP 621 config (`name = "<name>-pa"`, `pa_lang.libs` entry point)
└── README.md                  # Origin & Attribution + Benchmark vs. Original table
```

## 2. Hard Engineering Rules

1. **Pure Core (`pa/<core>.pa`)**
   - Zero `@export` and zero Python imports — must compile as a standalone binary with `pac build -I packages/<name>-pa/pa`.
   - Follow `pa-coder` compiler gates: declare `-> ReturnType` on every function; keep parameters unannotated; functions ≤ 40 lines, cyclomatic complexity ≤ 8 (`PA_E061`), nesting ≤ 3; calls with > 2 args require keyword arguments (`PA_E051`); no negative indexing (`0 <= i < len`).
   - Keep container layouts monomorphic per helper (do not pass `str_view` at one call site and `span[u8]` at another; provide distinct `*_str` / `*_bytes` helpers when needed).
2. **Thin Binding (`binding/export.pa`)**
   - Import pure kernels via `from <core> import ...` (resolved with `-I packages/<name>-pa/pa`).
   - Use only types supported by `pac build --shared` direct CPython `PyInit__native` wrappers:
     - Parameters: scalars (`int`, `uint`, `int32`, `uint8`, `uint32`, `float`, `float32`, `bool`), `str_view`, or `span[<scalar>]` (writable in-place for pre-allocated Python buffers like `array.array` / `bytearray` / NumPy `ndarray`).
     - Returns: any scalar, `void`, or `str_view`.
   - Validate all buffer lengths and offset bounds before slicing (`span(buf, start, length)`); return `-1` on invalid input so Python raises `ValueError` instead of segfaulting.
3. **1:1 Python Package & Platform Wheel (`python/<mod>/` + `setup.py`)**
   - Import the compiled extension as `from . import _native` (compiled to `python/<mod>/_native<EXT_SUFFIX>`).
   - Provide complete `__init__.pyi` stubs, `py.typed`, and `_pa_libs_dir()` registered under `[project.entry-points."pa_lang.libs"]` so `pip install <name>-pa` works for both Python `import <mod>` and pure Pa static imports.
   - `setup.py` overrides `Distribution.has_ext_modules = lambda self: True` so wheels get exact `cp3XX-<platform>` tags (never `py3-none-any`), and copies `pa/` into `<mod>/_pa/` inside the wheel.
4. **Custom Batch Loop Template (`loop-template/custom_batch.pa`)**
   - Pre-wire zero-copy inputs (`span[...]`), upfront offset/length validation, and pre-allocated writable output `span[...]` buffers.
   - Clearly delimit the editable region with:
     ```python
     # === BEGIN USER LOOP BODY (edit filter / scoring logic freely) ===
     ...
     # === END USER LOOP BODY ===
     ```
   - Must compile cleanly with `pac build --shared --mode prod -I ../pa custom_batch.pa -o custom_batch.so` and be directly importable in Python with zero `ctypes`.

## 3. Build, Test & Wheel Workflow

```bash
# Static check all .pa files in the package
python tools/build.py check <name>-pa

# Build _native<EXT_SUFFIX> in prod mode
python tools/build.py build <name>-pa --mode prod

# Full E2E test suite (pure .pa binary + loop-template .so + pytest differential tests)
python tools/build.py test <name>-pa

# Build a platform-tagged PyPI wheel locally
python tools/build.py wheel <name>-pa
```

If `pac` is in a virtualenv not on `PATH`, set `PA_PAC=/path/to/pac`.

## 4. Isolated 4-Way Benchmark & Sub-Package README

1. Add `benchmarks/bench_<name>.py` following `benchmarks/bench_levenshtein.py`:
   - Compare all **4 runtime tiers** on the exact same workload:
     1. **Pure Python (`for` loop)** — `CPython`
     2. **`<name>-pa` single-call** — `CPython + .so`
     3. **`loop-template` batch** — `CPython + .so`
     4. **Pure Pa Standalone (`pac build --mode prod`)** — `Native (No Python)`
   - Run each mode in its own **isolated subprocess** (3 trials, median) measuring wall-clock time (`time.perf_counter()`) and Peak RSS:
     - **Cross-platform RSS helper**: for Python modes, use `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` on Unix (KiB on Linux -> `/ 1024.0`; bytes on macOS -> `/ (1024.0 * 1024.0)`), falling back to `psutil.Process().memory_info().rss` or `tracemalloc.get_traced_memory()[1]` on Windows; for the Pure Pa Standalone binary, measure with `/usr/bin/time -v` on Linux (falling back to wall-clock only if unavailable).
   - Assert 100% output parity across all four modes before printing the Markdown table.
2. Run `python benchmarks/bench_<name>.py` and record the **actual measured numbers** (never fabricate data) in `packages/<name>-pa/README.md` using the standard header:
   - **Origin & Attribution** blockquote (inspiring Python library/algorithm, clean-room pure-Pa reimplementation, zero GC / deterministic layout, MIT license).
   - **Benchmark vs. Original** 4-row table (`Implementation | Runtime | Median Time | Speedup | Peak RSS`, plus a brief RSS footnote noting the CPython interpreter baseline, pre-allocated batch buffers, and pure-Pa zero-Python footprint, and the reproduce command).
   - Concise usage snippets for Python (`pip install <name>-pa` / `import <mod>`), Pure Pa, and `loop-template/`.

## 5. Definition of Done

- [ ] `python tools/build.py check <name>-pa` exits 0 (zero errors/warnings).
- [ ] `python tools/build.py test <name>-pa` passes pure `.pa` binary test, `loop-template` `.so` E2E test, and all `pytest` differential tests.
- [ ] `python tools/build.py wheel <name>-pa` produces a platform- & ABI-tagged wheel (`cp3XX-...`, not `py3-none-any`) containing `_native*` and `_pa/*.pa`.
- [ ] `python benchmarks/bench_<name>.py` runs cleanly with parity verified and real numbers written into `packages/<name>-pa/README.md`.
