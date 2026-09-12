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
  --count 100000 --queries 32 --backend sqlite-vec
```

Each run creates a separate installation, completes public setup, and calls the
real search HTTP endpoint with normal authentication, authorization, lexical
ranking, local ONNX inference and result materialization. Query vectors are not
precomputed or retained between warm measurement queries. Pass-through timing
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

Physical Pi 5 backfill, ingestion under backfill load, and independent human
query/photo quality acceptance require their own measurements; neither harness
silently substitutes for those checks.
