---
name: libpa-pkg
description: Scaffold, build, differentially test, and benchmark a new granular libpa sub-package (pure .pa core, thin @export binding, PEP 420 Python package with .pyi stubs, loop-template, Origin & Benchmark Card, and isolated 3-way benchmark). Use when creating, updating, or verifying any packages/libpa-* sub-package in the libpa monorepo.
---

# libpa-pkg

End-to-end procedure for creating, verifying, and benchmarking a granular `libpa` sub-package (`packages/libpa-<domain>/`).

> **Prerequisites**: This skill builds on Pa's bundled `pa-coder` language skill. Install `pa-lang` and load the base skills first so your agent has the full Pa syntax and compiler gate rules:
> ```bash
> pip install pa-lang
> pac skill --install claude   # or: cursor | codex | copilot | antigravity
> ```

## 1. Required Sub-Package Layout

Create `packages/libpa-<domain>/` with module name `<mod> = <domain>.replace("-", "_")`:

```text
packages/libpa-<domain>/
├── pa/
│   └── <core>.pa              # 100% pure .pa (NO @export, NO Python runtime deps)
├── binding/
│   └── export.pa              # Thin @export boundary + input/bounds validation
├── python/
│   └── libpa/                 # STRICT PEP 420: NEVER create __init__.py here
│       └── <mod>/
│           ├── __init__.py    # Pythonic wrappers, docstrings, TypeError/ValueError checks
│           ├── __init__.pyi   # Complete PEP 484 type stubs
│           └── py.typed       # Empty PEP 561 marker
├── loop-template/
│   ├── custom_batch.pa        # Pre-wired zero-copy In/Out + marked user loop body
│   ├── pyproject.toml         # Standalone template package metadata
│   └── README.md              # 3-step edit -> pac build --shared -> import guide
├── tests/
│   ├── test_<core>_pure.pa    # Pure Pa standalone test binary (zero Python runtime)
│   └── test_<mod>.py          # Pytest differential suite + PEP 420 + loop-template E2E
├── pyproject.toml             # PEP 621 config (readme = "README.md", PEP 420 find)
└── README.md                  # Origin & Attribution + Benchmark vs. Original table
```

## 2. Hard Engineering Rules

1. **Pure Core (`pa/<core>.pa`)**
   - Zero `@export` and zero Python imports — must compile as a standalone binary with `pac build -I packages/libpa-<domain>/pa`.
   - Follow `pa-coder` compiler gates: declare `-> ReturnType` on every function; keep parameters unannotated; functions ≤ 40 lines, cyclomatic complexity ≤ 8 (`PA_E061`), nesting ≤ 3; calls with > 2 args require keyword arguments (`PA_E051`); no negative indexing (`0 <= i < len`).
   - Keep container layouts monomorphic per helper (do not pass `str_view` at one call site and `span[u8]` at another; provide distinct `*_str` / `*_bytes` helpers when needed).
2. **Thin Binding (`binding/export.pa`)**
   - Import pure kernels via `from <core> import ...` (resolved with `-I packages/libpa-<domain>/pa`).
   - Use only types supported by `pac build --shared` direct CPython `PyInit_<mod>` wrappers:
     - Parameters: scalars (`int`, `uint`, `int32`, `uint8`, `uint32`, `float`, `float32`, `bool`), `str_view`, or `span[<scalar>]` (writable in-place for pre-allocated Python buffers like `array.array` / `bytearray` / NumPy `ndarray`).
     - Returns: any scalar, `void`, or `str_view`.
   - Validate all buffer lengths and offset bounds before slicing (`span(buf, start, length)`); return `-1` on invalid input so Python raises `ValueError` instead of segfaulting.
3. **PEP 420 Python Package (`python/libpa/<mod>/`)**
   - Never place `__init__.py` inside `python/libpa/`.
   - Import the compiled extension as `from . import _<mod>` (built to `python/libpa/<mod>/_<mod>.so` or `.pyd`).
   - Provide complete `__init__.pyi` stubs and `py.typed`.
   - In `pyproject.toml`, set `readme = "README.md"`, `[tool.setuptools.packages.find] where = ["python"], include = ["libpa*"]`, and `package-data` for `*.so`, `*.pyd`, `*.pyi`, `py.typed`.
4. **Custom Batch Loop Template (`loop-template/custom_batch.pa`)**
   - Pre-wire zero-copy inputs (`span[...]`), upfront offset/length validation, and pre-allocated writable output `span[...]` buffers.
   - Clearly delimit the editable region with:
     ```python
     # === BEGIN USER LOOP BODY (edit filter / scoring logic freely) ===
     ...
     # === END USER LOOP BODY ===
     ```
   - Must compile cleanly with `pac build --shared --mode prod -I ../pa custom_batch.pa -o custom_batch.so` and be directly importable in Python with zero `ctypes`.

## 3. Build & Test Workflow

Run all checks, builds, standalone `.pa` tests, `loop-template` compilation, and Python differential tests via the monorepo tool:

```bash
# Static check all .pa files in the package
python tools/build.py check libpa-<domain>

# Build _<mod>.so in prod mode
python tools/build.py build libpa-<domain> --mode prod

# Full E2E test suite (pure .pa binary + loop-template .so + pytest differential tests)
python tools/build.py test libpa-<domain>
```

If `pac` is in a virtualenv not on `PATH`, set `PA_PAC=/path/to/pac` (or use that venv's `python`).

## 4. Isolated 3-Way Benchmark & Sub-Package README

1. Add `benchmarks/bench_<mod>.py` following `benchmarks/bench_text.py`:
   - Compare **Pure Python (`for` loop)** vs **`libpa.<mod>` single-call** vs **`loop-template` batch**.
   - Run each mode in its own **isolated subprocess** (3 trials, median) measuring wall-clock time (`time.perf_counter()`) and Peak RSS:
     - **Cross-platform RSS helper**: use `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` on Unix (KiB on Linux -> `/ 1024.0`; bytes on macOS -> `/ (1024.0 * 1024.0)`), and fall back to `psutil.Process().memory_info().rss` or `tracemalloc.get_traced_memory()[1]` on Windows where `import resource` is unavailable.
   - Assert 100% output parity across all three modes before printing the Markdown table.
2. Run `python benchmarks/bench_<mod>.py` and record the **actual measured numbers** (never fabricate data) in `packages/libpa-<domain>/README.md` using the standard header:
   - **Origin & Attribution** blockquote (inspiring Python library/algorithm, clean-room pure-Pa reimplementation, zero GC / deterministic layout, MIT license).
   - **Benchmark vs. Original** 3-row table (workload size, environment, median time, speedup, Peak RSS, and reproduce command).
   - Concise usage snippets for Python, Pure Pa (`-I`), and `loop-template/`.

## 5. Definition of Done

- [ ] `python tools/build.py check libpa-<domain>` exits 0 (zero errors/warnings).
- [ ] `python tools/build.py test libpa-<domain>` passes pure `.pa` binary test, `loop-template` `.so` E2E test, and all `pytest` differential tests.
- [ ] `python/libpa/__init__.py` does **not** exist (`getattr(libpa, "__file__", None) is None`).
- [ ] `python benchmarks/bench_<mod>.py` runs cleanly with parity verified and real numbers written into `packages/libpa-<domain>/README.md`.
