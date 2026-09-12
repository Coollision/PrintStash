# AI Search performance acceptance

Run these measurements on an otherwise idle host, after correctness and coverage
checks finish. Keep each output directory and its `result.json`. Record the Git
commit, physical hardware, operating system and available memory alongside the
report. A VM result does not establish physical Raspberry Pi or ARM acceptance.

## Native-vector feasibility

From `backend/`:

```sh
uv run python -m tests.fakes.vector_scale \
  --directory /tmp/ai-vector-scale-500k \
  --count 500000 --dimension 384 --queries 32
```

The destination must be new. The harness reserves capacity for durable floats,
the native derivative and a separate durable-only snapshot. It measures actual
`sqlite-vec` exact KNN against the shipped float scanner, using identical vectors
and both unrestricted and restricted SQL scopes. It records recall@10, p50/p95,
build time, database size and resource use. A fresh SQLite connection then reads
the snapshot without loading any vector extension and verifies its digest and
neighbors. This numeric feasibility result does not measure model quality or
the production backup HTTP workflow; those have separate tests.

## End-to-end query latency

Explicitly preplace the pinned BGE export described in
[the model study](ai-search-model-study.md), including its reviewed manifest.
The harness performs no model acquisition or remote inference.

```sh
uv run python -m tests.fakes.search_scale \
  --directory /tmp/ai-search-scale-100k-numpy \
  --model-directory /absolute/path/to/bge-export \
  --count 100000 --queries 32 --backend numpy

uv run python -m tests.fakes.search_scale \
  --directory /tmp/ai-search-scale-100k-native \
  --model-directory /absolute/path/to/bge-export \
  --count 100000 --queries 32 --backend sqlite_vec
```

Each run creates a separate installation, completes public setup, and calls the
real search HTTP endpoint with normal authentication, authorization, lexical
ranking, local ONNX inference and result materialization. The query-vector cache
is cleared before measuring the distinct frozen queries, so none uses a cached
query vector. Pass-through timing
records embedding, vector retrieval, fusion and Model materialization, as well
as the entire request. The initial request and subsequent warmup are separate;
the normal background warmer may finish during fixture construction, so the
first request is not automatically classified as a cold encoder measurement.

The result retains all timings and exits nonzero if warm p95 exceeds **300 ms**.
Only a 100,000-passage run with the declared hardware satisfies that scale check.
Smaller `--count`/`--queries` settings validate the harness, not the latency gate.

The frozen corpus has **32 distinct engineering texts**, replicated to the
requested cardinality with unique Model identities. Durable document vectors
come from the versioned measured BGE fixture; query vectors come from the real
encoder. Replication preserves realistic passage and authorization structure but
does not supply 100,000 independent semantic labels. The report records the
corpus/query digests and distinct-text count so those claims remain separable.

## Ingestion under backfill

```sh
uv run python -m tests.fakes.search_ingest_load \
  --directory /tmp/ai-search-ingest-load \
  --model-directory /absolute/path/to/bge-export \
  --count 10000 --uploads 20
```

The acceptance limit is declared before measurement: **at most 25% additional
p95 upload-to-completion latency, no failed ingests, and actual inference
backfill running throughout every loaded upload**. Baseline and loaded phases
use fresh installations and the same ordered G-code corpus. Unique comments
prevent duplicate detection from bypassing ingestion; each phase records the
exact file hashes. The seeded library has 32 distinct texts, replicated to
10,000 unembedded passages. Both phases warm the same local model beforehand.

The report contains per-upload completion latency, generation progress before
and after each upload, and sampled RSS/CPU for the application and its worker
processes, including children spawned by executor threads. Sampling accompanies
job polling, so its RSS maximum is labelled as sampled rather than an exact
kernel high-water mark. A run where backfill finishes before the uploads does
not satisfy the overlap requirement. The command preserves phase reports and
exits nonzero when comparison fails.

Physical Pi 5 backfill and independent human query/photo quality acceptance
require separate measurements; these harnesses do not substitute for them.


## Measured 500,000-vector feasibility on x86

Measured on 2026-09-12 at `0364db751861bdecb122679ffa998181417c93d9`:
Linux x86_64, QEMU/KVM, four virtual CPUs, 11,677 MiB RAM, one OpenBLAS thread,
SQLite 3.53.1 and sqlite-vec 0.1.6. Existing user services remained running;
no other test or benchmark was run concurrently. This is a VM measurement,
not the physical ARM result required by S2.

| Eligible vectors | Native p50 / p95 | Float scanner p50 / p95 | Native recall@10 |
|---|---|---|---:|
| 500,000 | 2.247 / 2.281 s | 6.870 / 6.957 s | 1.0 |
| 50,000 (10% SQL scope) | 1.787 / 1.921 s | 1.826 / 1.887 s | 1.0 |

All 32 seeded queries in each scope matched the float top 10 exactly. Building
both tables took 182.22 seconds. The source database occupied 1,808,351,232 bytes;
the durable-only restored database occupied 1,026,580,480 bytes, including
768,000,000 bytes of vector payload. Snapshot copying took 9.60 seconds. The
restored connection had no vector extension loaded; every row was digest-checked
and both scopes returned the same neighbors. Peak process RSS was 68,536 KiB.
The complete run took 621.76 seconds.

The native index improved unrestricted retrieval but did not improve the
restricted-scope p95 in this experiment. It stays opt-in. Neither result meets
or substitutes for the separate 100,000-passage HTTP target: these timings have
no query encoder, application authorization or response materialization.
Raw timings, versions, input digest and source context are retained in
`backend/tests/fixtures/search/sqlite-vec-500k-x86-{vectors,context}.json`.

## Query-path corrections found by the 100k run

The initial portable run was interrupted after repeated 8.3–8.7 second warm
requests exposed a real regression; it is not a completed p95 measurement.
Profiling found repeated worst-candidate sorting, whole-library permission scans
for small result sets, and writer contention during periodic projection repair.
The corrected scorer keeps a bounded competitive cutoff, while SQL preserves
fresh owner/contributor visibility and restricts card/result checks to candidate
identities. Periodic repair processes eight Subjects per stream per transaction;
embedding bursts retain their independent batch budget.

Regression tests compare the scorer against an independent full-sort oracle and
measure SQLite instruction counts before/after adding 1,000 unrelated Models or
Passages. Limited, joined, distinct and empty authorization scopes retain exact
membership. PostgreSQL tests recheck contributor grants and trash state. The
query-deadline regression measures its one-second tolerance from actual provider
admission; cold SQL compilation/authentication belongs to the separate complete
HTTP latency benchmark, whose 300 ms budget remains unchanged.

Before the final vector-store correlation change, a complete 32-query native
run measured p50 **4.059 s**, p95 **4.479 s** and first-request **5.557 s**. That
failed run remains in the task's measurement output.
