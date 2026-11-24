# `levenshtein-pa` Custom Batch Loop Template

When calling a single function millions of times from a Python `for` loop, Python interpreter & boundary overhead dominates. This template moves your entire loop into native LLVM code while keeping all zero-copy In/Out buffer wiring pre-built.

## 1. Edit the Loop Body

Open [`custom_batch.pa`](./custom_batch.pa) and edit only the section between:

```python
# === BEGIN USER LOOP BODY ===
...
# === END USER LOOP BODY ===
```

You already have:
- `query: span[u8]` — zero-copy UTF-8 query bytes
- `corpus: span[u8]` & `offsets: span[int]` — flat concatenated corpus + CSR offsets (validated upfront)
- `out_indices: span[int]` & `out_dists: span[int]` — pre-allocated writable output buffers from Python

## 2. Compile to a Direct-Import `.so` Module (One Command)

```bash
pac build --shared --mode prod -I ../pa custom_batch.pa -o custom_batch.so
```

## 3. Import Directly in Python (Zero `ctypes`)

```python
import array
import custom_batch

query = b"kitten"
words = [b"sitting", b"mitten", b"completely_different", b"bitten"]

corpus = b"".join(words)
offsets = array.array("q", [0])
for w in words:
    offsets.append(offsets[-1] + len(w))

out_idx = array.array("q", [0] * len(words))
out_dist = array.array("q", [0] * len(words))

hits = custom_batch.filter_batch(query, corpus, offsets, 2, out_idx, out_dist)
print([(out_idx[i], out_dist[i]) for i in range(hits)])
# [(1, 1), (3, 1)]
```
