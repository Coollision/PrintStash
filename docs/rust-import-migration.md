# Staged native import migration

Implementation starts from `perf/adaptive-rust-import` at
`4b9afeb92d4e7e24298454af38c6c76aeddec437`. The first milestone is
`codex/rust-m00-baseline`. This document records acceptance criteria and evidence;
planned work is not a claim of a completed native import path.

## Architecture and ownership

The destination is an embedded Rust engine for acquisition, durable execution,
archive processing, parsing, Artifact publication, previews, geometric similarity,
and optional enrichment. Python retains HTTP, authentication, and unrelated
capabilities. At final cutover, imports must not execute Python callbacks or
Python workers. SQLite/local storage remains the default; PostgreSQL and existing
remote storage contracts remain supported. No broker or Cloud service is required.

Use framework-independent domain/compute modules, a SQLx persistence adapter,
a Tokio engine, a narrow PyO3 binding, and supervised native STEP/inference helpers.
Keep queue-library types within persistence. Use one Tokio runtime and the existing
bounded Rayon pool. Queue ownership and CPU/memory reservations are distinct.
Foreground work has priority; background work becomes eligible after 60 seconds.
Cloud tenancy, billing, distributed scheduling, and deployment belong outside OSS.

Current ownership at M00 (unchanged by the benchmark):

| Stage | Compute language | Coordinator | Durable-state owner | Existing contract evidence to preserve |
| --- | --- | --- | --- | --- |
| Import acceptance/dispatch | Python | HTTP and `runtime/ingestion` | Python SQLModel transaction, `modules/ingestion/commands.py` | `tests/integration/modules/ingestion/test_commands.py`, `test_command_executor.py` |
| Acquisition/outer archives | Python and existing codecs | Python command executor | Import commands, staging leases and checkpoints | `tests/integration/modules/ingestion/test_acquisition.py`, importer tests |
| Artifact publication | Python | `ingestion.persist_artifact` | One application transaction, reservations and storage receipts | `tests/integration/modules/ingestion/ingestion/test_ingestion_atomicity.py` |
| Mesh preparation/previews | Rust kernels plus Python dispatch/assembly | Python stages using native executor | Python analysis/thumbnail generations | `rust/tests/`, `tests/integration/modules/media/test_mesh_render.py` |
| Resource admission | Existing Rust reservations | Python task selection, native executor | Python durable jobs | `rust/tests/test_orchestration.py`, media resource tests |
| STEP | Native Open CASCADE through Python worker | Python supervision | Python analysis generations | STEP integration fixtures |
| Similarity | Rust proximity plus Python/NumPy work | Python similarity runtime | Python similarity runs/fingerprints | Similarity integration tests and labeled evaluation corpus |
| Optional enrichment | Native inference through Python workers | Python enrichment runtime | Python generation state and validated assets | Existing inference/asset validation tests |

Test paths in this table are relative to `backend/`; these are existing contracts,
not evidence that the migration has passed. Moving a Python callable onto a Rust
thread does not change its compute language or durable ownership.

## Milestones and delivery

Each row receives one branch `codex/rust-mNN-<suffix>` and one PR into the latest
verified `perf/adaptive-rust-import`. Merge only after current-revision checks,
review, performance evidence, and the tested integration result pass. Validate
the resulting integration commit before the next dependent milestone. Accumulate
the final description/evidence in draft PR #173; leave that PR to `main` unmerged.

| Milestone | Branch suffix | Acceptance and comparison |
| --- | --- | --- |
| M00 | baseline | Record contracts, fixtures, ownership and failures; both-DB benchmark; native coverage; repeated unchanged baseline/noise |
| M01 | queue-qualification | Apalis/Azums executable qualification on both DBs; atomicity, crashes, stale owners, waiting, priority, shutdown/restore; idle/claim/recovery/contention costs |
| M02 | dependencies | Latest compatible stable versions, exact lockfiles/features/licenses/MSRV/native dependencies and exceptions; dependency-only comparison |
| M03 | persistence | Native repositories and import-owned transactions; schema/pragmas/version allocation/maintenance parity; transaction latency/contention |
| M04 | durable-queue | Qualified adapter, preserved job IDs/checkpoints, safe pending-job upgrade and single owner; enqueue/recovery/database growth |
| M05 | import-runtime | Rust dispatch/heartbeats/waiting/admission/drain; explicit temporary bridge; foreground/background fairness and API latency |
| M06 | publication | Native idempotency/reservations/receipts/reconciliation/cleanup for every caller; source-saved/publication latency |
| M07 | storage | Supported native local/remote adapters preserving identities, create-only writes and read-only sources; streaming/memory/request counts |
| M08 | gcode | Bounded text metadata and established libbgcode codec; slicer compatibility, parsing/bytes read/memory |
| M09 | archives | Bounded inspection/extraction and path safety; many-small and large-entry workloads |
| M10 | mesh-previews | Native preparation/buffer flow and renderer orchestration; geometry and pixel parity, allocations/memory |
| M11 | step | Supervised native Open CASCADE helper; units/settings/work limits; cold/warm complex assemblies |
| M12 | similarity | Remaining voxelization/descriptors/alignment/verification; labeled quality and work bounds; indexing/verification latency |
| M13 | acquisition | Rust URL/provider/inbox/source acquisition, credentials/checkpoints; safe destinations and resumed bytes |
| M14 | native-enrichment | Native inference/tokenization with optional installation and asset validation; canaries/cold/warm/batching/memory |
| M15 | complete-cutover | Remove every Python import executor/bridge; all entry points/upgrades/packaging; original and immediate-parent corpus comparison |

M03–M07 require a qualified queue. If neither candidate qualifies, retain the
current queue and stop that cutover; independent M08–M14 can continue through
existing execution paths. M15 requires every previous milestone. Preserve public
HTTP contracts and job identity. Rust acceptance owns its complete transaction;
never pass a SQLAlchemy session into SQLx. Use additive transitions and verify
rollback; disable the old consumer before enabling its replacement.

Application migrations remain new autogenerated Alembic revisions. Do not edit
merged migrations. Queue-internal migrations have one documented owner and run
only during controlled startup/upgrade. Validate upgrades with real existing data,
pending work, retries, staged files and completed Artifacts.

## Queue and dependency gate

Recheck stable releases at implementation. Qualify Apalis, compare Azums, and
prefer Apalis if both pass. Azums is eligible only if Apalis fails and Azums passes
all gates. Effectum lacks PostgreSQL support. Fang is excluded unless a stable
release fixes its documented interrupted-job recovery limitation. No maintained
fork or replacement custom queue is an implicit fallback.

The Apalis 0.7.4 PostgreSQL acknowledgment ownership concern is **unresolved**
until reproduced against real PostgreSQL. A source-level concern is not a failed
runtime test. Qualification also needs supported atomic enqueue, crash recovery,
stale acknowledgment/publication protection, replay idempotency, checkpoints,
bounded failures, dependency waiting without attempt consumption, existing
priority, maintenance, backups and restore on both databases. Integration must
not duplicate library leasing/retry machinery. Record exact versions/features,
licenses, security findings, toolchains, native dependencies, integration code,
rejected alternatives and maintenance costs.

Prefer SQLx, Tokio, Rayon, the existing ZIP/XML/compression/image stack, reqwest,
OpenDAL where provider contracts permit, Prusa libbgcode, Open CASCADE, and the
native ONNX Runtime API with compatible tokenization. Retain application-specific
policy. Do not introduce an ORM, database engine, custom thread pool or codec.

## Measurement and gates

Every accepted comparison comes from committed release builds, against both the
immediate parent and original baseline, with identical corpus hashes, output
requirements, settings and DB versions. Run 2 CPU/2 GiB and 4 CPU/4 GiB profiles
sequentially without builds/tests alongside them: one warm-up and seven alternating
before/after pairs, extended to fourteen if noise masks the result. Require source
hashes, Artifact counts, metadata, geometry, previews and similarity correctness
before accepting timings. Record source-saved/full latency, API p50/p95/max, CPU,
memory, throughput and stage costs; queue changes add idle/claim/recovery/growth.
Sampled RSS can miss peaks and double-count shared pages; record container peaks
where available. Repeated regressions above 5% elapsed/API p95 or 10% CPU/memory
block merge absent explicit acceptance. Shared CI timing is not a controlled gate.

Run focused tests, backend fast then coverage (including full), lint, CI-scoped
formatting, types, independent core coverage, Rust format/Clippy/tests/bindings and
native coverage. Preserve existing branch-coverage ratchets. Run frontend checks,
coverage, mock/real Playwright and affected capture/storage flows, native amd64/arm64
and full/lite image smoke tests. Review each production milestone's exact diff for
security. Missing services/assets/checks are blockers, never successful skips.
Each PR includes its concrete coverage matrix, dependency/ownership decisions,
benchmark table/raw sanitized evidence, migration/rollback and limitations.

## M00 evidence

In progress. The benchmark now selects `--database sqlite|postgres`. PostgreSQL
uses the repository test-container owner and a fresh per-run database, never an
existing vault URL. Both paths use the supported `app.db.migrate` bootstrap.
Protocol `job-and-library-poll-250ms-v3` records DB backend/version and rejects
incompatible comparisons. Existing v2 numbers are historical, not M00 evidence.

Native coverage uses `scripts/native-coverage.sh`, cargo-llvm-cov 0.9.1 and the
existing production compiler 1.91.0 plus llvm-tools-preview. It instruments a
separate extension, asserts Python loaded that extension, and runs Rust/binding
and application preview tests. Stable compiler reports provide line/region/function
coverage; they **do not establish branch coverage**. Any future nightly branch
instrumentation must be pinned and recorded separately from production.

No queue candidate is selected. No import stage has changed ownership. No
controlled baseline performance comparison or complete migration is claimed.

### M00 coverage matrix

Paths below are relative to `backend/`. Database-sensitive cases are parametrized
against real file-backed SQLite and PostgreSQL. No database transactions are mocked.

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | counts only background analysis | Edge | Pending background, active foreground and failed analysis rows | Pending/failure totals include only background policy | Integration | ✅ `tests/repo/test_bench_database.py::TestEnrichmentInspection::test_counts_only_background_analysis` |
| 2 | includes similarity only when requested | Edge | Pending similarity run, feature off/on | Pending totals follow benchmark workload selection | Integration | ✅ `tests/repo/test_bench_database.py::TestEnrichmentInspection::test_includes_similarity_only_when_requested` |
| 3 | counts projection requests without a state | Happy | Two durable projection requests | Pending count is two | Integration | ✅ `tests/repo/test_bench_database.py::TestEnrichmentInspection::test_counts_projection_requests_without_a_state` |
| 4 | records database version without connection details | Happy | Live SQLite/PostgreSQL connection | Backend/version present; no connection URL/credentials | Integration | ✅ `tests/repo/test_bench_database.py::TestEnrichmentInspection::test_records_database_version_without_connection_details` |
| 5 | isolates each run | Edge | Concurrent benchmark databases; sentinel in first | Second is fresh, first survives second cleanup | Integration | ✅ `tests/repo/test_bench_database.py::TestDisposableDatabase::test_isolates_each_run` |
| 6 | refuses an existing SQLite file | Error | Destination contains existing bytes | Refused before modification; bytes unchanged | Integration | ✅ `tests/repo/test_bench_database.py::TestDisposableDatabase::test_refuses_an_existing_sqlite_file` |
| 7 | removes its PostgreSQL database after failure | Error | Benchmark body raises | Owned database absent from PostgreSQL catalog | Integration | ✅ `tests/repo/test_bench_database.py::TestDisposableDatabase::test_removes_its_postgres_database_after_failure` |
| 8 | rejects an unsupported database | Error | Unknown dialect | Error before database creation | Integration | ✅ `tests/repo/test_bench_database.py::TestDisposableDatabase::test_rejects_an_unsupported_database` |
| 9 | supports the documented script entry point | Happy | Direct CLI invocation without PYTHONPATH | Successful help includes database choices | Integration | ✅ `tests/repo/test_bench_import.py::TestBenchmarkArguments::test_supports_the_documented_script_entry_point` |
| 10 | accepts matching database versions | Happy | Identical database evidence | Comparison accepted | Unit | ✅ `tests/repo/test_bench_import.py::TestCompareDatabases::test_accepts_matching_database_versions` |
| 11 | refuses incompatible database evidence | Error | Changed dialect/version or missing result evidence | Comparison refused | Unit | ✅ `tests/repo/test_bench_import.py::TestCompareDatabases::test_refuses_incompatible_database_evidence` |
| 12 | requires reference database evidence | Error | Missing reference metadata | Comparison refused | Unit | ✅ `tests/repo/test_bench_import.py::TestCompareDatabases::test_requires_reference_database_evidence` |
| 13 | benchmarks a complete import | Happy | ZIP with known tetrahedron, fresh real app on each DB | Completed job, exact source digest/size, four triangles, ready preview, serialized DB evidence | E2E | ✅ `tests/e2e/test_import_benchmark.py::TestImportBenchmark::test_benchmarks_a_complete_import` |
| 14 | measures actual native execution | Happy | Isolated instrumented extension and existing Rust/binding/preview suites | Loaded module is instrumented; executed source coverage exists for bindings and render core | Integration | ✅ `scripts/native-coverage.sh`; instrumented tests and combined workspace report verified locally |
| 15 | rejects the former public test password | Error | Real PostgreSQL benchmark; known former password | Authentication fails; session-specific credentials still support the benchmark | Integration | ✅ `tests/repo/test_bench_database.py::TestDisposableDatabase::test_rejects_public_test_password` |
| 16 | removes registered native indexes during test reset | Edge | Float, int8 and binary index roots with generation ownership | Root and shadow tables disappear before ownership rows are cleared | Integration | ✅ `tests/repo/test_db_parity.py::TestTestDatabase::test_reset_removes_registered_native_index_tables` |
| 17 | serves independent thumbnail fallback | Error | Native multiview unavailable; distinct thumbnail rendering recipe | Thumbnail generation serves the expected Model without copying incompatible vectors | Integration | ✅ `tests/integration/modules/search/test_visual_index.py::TestVisualIndex::test_prepares_an_independent_thumbnail_fallback` |
| 18 | serves search without related packages | Edge | Similarity/families packages absent; live projection worker | All four subject types remain searchable after public writes | E2E | ❌ rerun pending: `tests/e2e/test_search_independence.py::TestSearchIndependence::test_runs_without_related_feature_packages` |
| 19 | preserves MinIO migration contents | Happy | Official mirror, identical pinned image digest; ordinary/Unicode/multipart objects | Two migrations preserve all three objects and source volume | Contract | ✅ `scripts/test_minio_migration.sh` |
| 20 | focuses localized library search | Happy | Spanish locale and slash shortcut | Current accessible searchbox receives focus | Playwright | ✅ `frontend/tests/e2e/i18n.spec.ts` |
| 21 | preserves import browser workflows | Happy | Current search-status/caption response contracts | Existing upload/capture/detail flows complete without unexpected HTTP errors | Playwright | ✅ `frontend/tests/e2e/{uploads,pending-imports,inbox,model-detail}.spec.ts` |
| 22 | preserves storage through restart | Edge | WebDAV setup followed by real backend restart | Active provider, stored credentials and safe GC workflow remain usable | Playwright | ✅ `frontend/tests/e2e-real/storage/storage-provider.spec.ts` |
| 23 | persists print-tracking toggle | Happy | Toggle mutation response before React repaint | New value appears and survives reload | Playwright | ✅ `frontend/tests/e2e-real/settings.spec.ts` |
| 24 | requires confirmation before staging cleanup | Edge | Real expired ownership receipt in disposable browser vault | File survives preview; confirmation removes it | Playwright | ✅ `frontend/tests/e2e-real/settings.spec.ts` |
| 25 | filters library with current search control | Happy | Uploaded Model; search query then list/grid selection | Matching Model remains visible in both views | Playwright | ✅ `frontend/tests/e2e-real/vault.spec.ts` |
| 26 | shows an empty library search | Edge | Query with no matching Model | Model links disappear after query is applied | Playwright | ✅ `frontend/tests/e2e-real/vault.spec.ts` |

| 27 | preserves parsed metadata in performance comparisons | Happy/Error | Real Prusa G-code plus mesh on both DBs; changed or missing comparison facts | Exact slicer time/layer/material/tool color recorded without transient IDs; lossy comparisons refused | E2E/Unit | ✅ `tests/e2e/test_import_benchmark.py`, `tests/repo/test_bench_import.py::TestCompareMetadata` |
| 28 | edits a linked Nextcloud connection | Edge | Current verified-migration provider form; existing linked target | Credentials remain private; compatible edits succeed and root change is rejected | Playwright | ✅ `frontend/tests/e2e-real/critical/remote-backup.spec.ts` |
| 29 | resumes verified migration after restart | Edge | Baseline and online delta Artifacts; API restart | Both contents survive cutover; full audit succeeds | Playwright | ✅ `frontend/tests/e2e-real/migration/vault-migration.spec.ts` |
| 30 | re-enrolls an external root before write-back | Edge | Test-owned root with missing proof | Explicit enrollment succeeds; upload bytes reach that root | Playwright | ✅ `frontend/tests/e2e-real/external-libraries.spec.ts` |

The browser paths above are relative to the repository root. Verification so far:
corrected both-database benchmark suite **31 passed**; additional comparison/CLI
suite **21 passed**; database authentication/isolation and container startup suite
**18 passed**. Native instrumentation executed **289 binding, 401 core mesh,
12 application tests and 11 Rust tests**. The combined owned-source report measures
**96.19% lines, 95.44% regions and 92.98% functions**; branch coverage is unmeasured.
The corrected fallback, test grouping and both-database import E2Es also pass (**4 tests**).
Rust formatting and Clippy pass. These establish functional behavior, not speedups.

Initial draft PR #177 CI exposed an omitted renderer coverage package, an obsolete
MinIO registry, outdated browser contracts/selectors, a distinct-recipe fallback
expectation, and native test-index cleanup leakage. The first exact-diff security
review also found that benchmark PostgreSQL inherited a known test password; a
real authentication regression test now verifies session-specific credentials.
Corrections require fresh CI and a new exact-diff review before merge. The local
fast run stopped after its known fallback failure (**1 failed, 4,831 passed**).
Broader gates and controlled benchmark comparisons remain incomplete.

The MinIO registry correction intentionally retains the historical migration
source release and digest; it is not a dependency upgrade. Application execution
ownership, schema and installed release versions remain unchanged in M00.

CI revision `927d81a5` passed frontend lint/format/types/coverage/mock Playwright,
native source coverage, both architecture native jobs, all eight image builds/scans,
the core matrix, SQLite async extra, extension and MinIO migration. Its main real
browser lane passed 86 tests with one external-root test skipped for missing fixture
configuration; upload/onboarding follow-on suites passed two tests each. The skip
is not acceptance evidence. CI now supplies an explicit disposable external root.
Two later browser tests exposed the collapsed migration form: local corrected
Nextcloud editing and full Vault migration/restart tests both pass. Backend CI and
new-revision CI remain required. M00 protocol v4 adds exact parsed metadata and
per-tool requirements to comparison acceptance (24 comparison/CLI tests and two
real-database import tests pass). No performance comparison is accepted yet.

The external-root browser contract now passes locally with the explicit fixture;
it distinguishes missing proof from legacy unbound state. Updated benchmark
code passes Ruff and Pyright.
