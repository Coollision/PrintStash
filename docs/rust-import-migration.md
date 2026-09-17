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
Protocol `job-and-library-poll-250ms-v5` records DB backend/version and parsed
metadata, and rejects incompatible comparisons. Older numbers are historical,
not M00 evidence.

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
| 18 | serves search without related packages | Edge | Similarity/families packages absent; live projection worker | All four subject types remain searchable after public writes | E2E | ✅ `tests/e2e/test_search_independence.py::TestSearchIndependence::test_runs_without_related_feature_packages` |
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
| 31 | refuses an existing application database URL | Error | Explicit non-maintenance DB, wrong dialect, URL overrides or SQLite with server configuration | Refused before connection/filesystem writes; credentials absent from error | Integration | ✅ `tests/repo/test_bench_database.py::TestExternalPostgresServer` |
| 32 | isolates databases on a host-managed service | Happy | Real PostgreSQL maintenance connection | Fresh database supports writes; cleanup leaves original database inventory intact | Integration | ✅ `tests/repo/test_bench_database.py::TestExternalPostgresServer::test_uses_only_a_fresh_database_on_the_supplied_server` |
| 33 | imports through a private PostgreSQL service | Happy/Error | Real host-managed PostgreSQL; absent CLI environment or wrong dialect | Complete metadata-preserving import on valid service; invalid CLI rejected | E2E/Unit | ✅ `tests/e2e/test_import_benchmark.py`, `tests/repo/test_bench_import.py::TestBenchmarkArguments` |
| 34 | preserves published search content on rollback | Edge | Committed PostgreSQL projection followed by rolled-back source edit | Original passage remains; no request from the rolled-back transaction survives | Integration | ✅ `tests/integration/postgres/test_search_passages.py::TestSearchPassages::test_batch_rollback_preserves_the_previous_publication` |
| 35 | reproduces identical corpus archives | Happy | Two fresh corpus destinations | Identical archives and source hashes | Repo | ✅ `tests/repo/test_bench_corpus.py::TestBenchmarkCorpus::test_reproduces_identical_archives` |
| 36 | retains real slicer fixtures | Happy | Existing format fixtures | Bytes unchanged; known tetrahedron geometry retained | Repo | ✅ `tests/repo/test_bench_corpus.py::TestBenchmarkCorpus::test_retains_real_slicer_fixtures` |
| 37 | preserves an existing corpus destination | Error | Destination with baseline data | Refuses overwrite; sentinel survives | Repo | ✅ `tests/repo/test_bench_corpus.py::TestBenchmarkCorpus::test_preserves_an_existing_destination` |
| 38 | refuses unbounded corpus work | Error | Counts/subdivision outside documented bounds | Refuses before writing | Repo | ✅ `tests/repo/test_bench_corpus.py::TestBenchmarkCorpus::test_refuses_unbounded_corpus_work` |
| 39 | reports repeatable performance regression | Error | Seven complete pairs with 20% regression | Correct paired change and threshold counts | Repo | ✅ `tests/repo/test_bench_matrix.py::TestPerformanceComparison::test_flags_a_repeatable_regression` |
| 40 | identifies noisy baseline measurements | Edge | Alternating high/low measurements | Marks additional samples necessary | Repo | ✅ `tests/repo/test_bench_matrix.py::TestPerformanceComparison::test_requires_more_samples_when_baseline_is_noisy` |
| 41 | refuses incomplete comparison pairs | Error | Empty or unpaired reports | Fails without reporting comparative evidence | Repo | ✅ `tests/repo/test_bench_matrix.py::TestPerformanceComparison::test_refuses_incomplete_pairs` |
| 42 | refuses ambiguous benchmark revisions | Error | Branch, short hash or option-like input | Fails before running Git/build commands | Repo | ✅ `tests/repo/test_bench_matrix.py::TestBenchmarkRevision::test_refuses_ambiguous_or_option_like_revisions` |
| 43 | requires retained performance evidence | Edge | Opt-in CI benchmark workflow | Dedicated job uses read-only token and required evidence/image artifacts | Repo | ✅ `tests/repo/test_ci_workflows.py::TestControlledImportBenchmark` |
| 44 | completes the intended Model lifecycle | Happy | Unique uploaded bytes; other models may exist in Trash | Correct Model restored and purged | Playwright | ✅ `frontend/tests/e2e-real/models.spec.ts` |
| 45 | applies the selected tag before upload | Edge | Asynchronous tag creation | Selected chip visible before transfer; tag filter retains Model | Playwright | ✅ `frontend/tests/e2e-real/vault.spec.ts` |
| 46 | cancels warmup after consent revocation | Edge | Concurrent real file-backed WAL reader/writer | Loader terminates; provider remains cold | Integration | ✅ `tests/integration/modules/search/test_model_warmup.py` |
| 47 | refuses invalid performance measurements | Error | Null, boolean, string, nonpositive or nonfinite value | Comparison fails without accepting timing evidence | Repo | ✅ `tests/repo/test_bench_matrix.py::TestPerformanceComparison::test_refuses_invalid_measurements` |
| 48 | refuses missing performance measurements | Error | Absent API latency field | Comparison fails with named missing metric | Repo | ✅ `tests/repo/test_bench_matrix.py::TestPerformanceComparison::test_refuses_missing_measurements` |
| 49 | classifies missing embedded preview | Edge | G-code/mesh, expected/unknown failure reason, both databases | Only an identified G-code without an embedded preview is not applicable | Repo | ✅ `tests/repo/test_bench_database.py::TestEnrichmentInspection::test_classifies_missing_embedded_preview` |
| 50 | records G-code without embedded previews | Happy | Existing Orca and BGCODE fixtures, both databases | Complete import, exact preview reason and slicer metadata, no cache permission error | E2E | ✅ `tests/e2e/test_import_benchmark.py::TestImportBenchmark::test_records_gcode_without_embedded_previews` |
| 51 | accepts equal unavailable previews | Edge | Identical source and preview outcome | Comparison accepts equivalent output | Repo | ✅ `tests/repo/test_bench_import.py::TestComparePreviewOutcomes::test_accepts_equal_unavailable_previews` |
| 52 | rejects changed failure reason | Error | Preview failure reason differs | Comparison refuses timing evidence | Repo | ✅ `tests/repo/test_bench_import.py::TestComparePreviewOutcomes::test_rejects_changed_failure_reason` |
| 53 | requires outcome evidence | Error | Absent preview outcome catalog | Comparison refuses timing evidence | Repo | ✅ `tests/repo/test_bench_import.py::TestComparePreviewOutcomes::test_requires_outcome_evidence` |
| 54 | composes independent rankings | Edge | Two sparse lexical rankings in one SQL statement | Both return the authorized passage without CTE name collision | Integration | ✅ `tests/integration/modules/search/test_expansion.py::TestExpansion::test_composes_independent_rankings` |
| 55 | retains coverage after a failed floor | Error | Backend coverage gate fails | JSON/HTML evidence still uploaded; absence fails | Repo | ✅ `tests/repo/test_ci_workflows.py::TestBackendCoverageJob::test_retains_coverage_after_a_failed_floor` |
| 56 | has no preview for empty geometry | Edge | Missing mesh/faces or empty faces | No image is returned | Unit | ✅ `tests/unit/modules/media/test_mesh_render.py::TestRenderMeshThumbnail::test_has_no_preview_for_empty_geometry` |
| 57 | reports native render failure | Error | Native renderer rejects geometry | No image; named failure logged | Unit | ✅ `tests/unit/modules/media/test_mesh_render.py::TestRenderMeshThumbnail::test_reports_native_render_failure` |
| 58 | requires native engine even for empty geometry | Error | Native engine unavailable | Required-capability error propagates | Unit | ✅ `tests/unit/modules/media/test_mesh_render.py::TestRenderMeshThumbnail::test_requires_native_engine_even_for_empty_geometry` |
| 59 | rejects invalid output width | Error | Out-of-range or non-integer width | Stable validation failure | Unit | ✅ `tests/unit/modules/media/test_thumbnail.py::TestWebpNormalization::test_rejects_invalid_output_width` |
| 60 | reports corrupt supported image | Error | Truncated PNG | No unvalidated bytes returned | Unit | ✅ `tests/unit/modules/media/test_thumbnail.py::TestWebpNormalization::test_reports_corrupt_supported_image` |
| 61 | reads bounded native binary geometry | Happy | Ten facets, two-facet budget | Two samples and partial status | Unit | ✅ `tests/unit/modules/media/test_stl_fallback.py::TestSampleStlGeometry::test_reads_bounded_native_binary_geometry` |
| 62 | rejects invalid geometry work budget | Error | Non-integer/out-of-range budget | Refuses before source access | Unit | ✅ `tests/unit/modules/media/test_stl_fallback.py::TestSampleStlGeometry::test_rejects_invalid_geometry_work_budget` |
| 63 | keeps geometry partial after oversized ASCII line | Edge | Valid facet followed by oversized line | Bounded valid geometry remains explicitly partial | Unit | ✅ `tests/unit/modules/media/test_stl_fallback.py::TestSampleStlGeometry::test_keeps_geometry_partial_after_oversized_ascii_line` |
| 64 | records deferred storage failure | Error | Create-only storage write fails | Retry remains pending; source preserved; no preview pointer | Integration | ✅ `tests/integration/modules/media/test_thumbnail_generations.py::TestDeferredPublication::test_records_deferred_storage_failure` |
| 65 | renders from a verified cached preview | Happy | Matching receipt/source/recipe | Expected RGB pixels and view | Integration | ✅ `tests/integration/modules/search/test_visual_index.py::TestCachedThumbnail::test_renders_from_a_verified_cached_preview` |
| 66 | rejects preview larger than its receipt | Error | Actual bytes exceed recorded size | Cached result rejected | Integration | ✅ `tests/integration/modules/search/test_visual_index.py::TestCachedThumbnail::test_rejects_preview_larger_than_its_receipt` |
| 67 | rejects missing cached object | Error | Cache object removed | Cached result rejected | Integration | ✅ `tests/integration/modules/search/test_visual_index.py::TestCachedThumbnail::test_rejects_missing_cached_object` |
| 68 | refuses a budget the parent should never send | Error | Source/candidate/line/address-space budgets exceed caps | Isolated worker exits with invalid-budget status | Unit | ✅ `tests/unit/modules/media/test_stl_preview_worker.py::TestMain::test_refuses_a_budget_the_parent_should_never_send` |
| 69 | renders a binary STL with a manifest beside it | Happy | Actual isolated native worker | Complete image/manifest; subprocess execution instrumented | Unit | ✅ `tests/unit/modules/media/test_stl_preview_worker.py::TestMain::test_renders_a_binary_stl_with_a_manifest_beside_it` |

| 70 | successor completes after a rejected stale callback | Error | Expired worker attempts completion before its successor; no intervening status refresh | Durable job reaches the successor's completed state | Integration | ✅ `tests/integration/modules/ingestion/test_commands.py::TestCommandsContract::test_successor_completes_after_a_rejected_stale_callback` |
| 71 | recovers a terminated worker without losing jobs | Error | Real process killed after claim; production lease; SQLite/PostgreSQL | Same job recovers once, stale callback rejected, successor completes | E2E | ✅ `tests/e2e/test_queue_benchmark.py::TestQueueBenchmark::test_recovers_a_terminated_worker_without_losing_jobs` |
| 72 | refuses unbounded work before creating output | Error | Invalid count or idle duration | No benchmark output/database created | Repo | ✅ `tests/repo/test_bench_queue.py::TestQueueBenchmarkBounds::test_refuses_unbounded_work_before_creating_output` |
| 73 | refuses internal execution without a disposable owner | Error | Internal CLI used without supervisor | Refuses before loading application database | Repo | ✅ `tests/repo/test_bench_queue.py::TestQueueBenchmarkOwnership::test_refuses_internal_execution_without_a_disposable_owner` |
| 74 | refuses a changed database | Error | Supervisor receipt belongs to another database | Refuses application database access | Repo | ✅ `tests/repo/test_bench_queue.py::TestQueueBenchmarkOwnership::test_refuses_a_changed_database` |
| 75 | distinguishes latency from resource regressions | Edge | Repeatable 6% latency/CPU changes | Flags latency at 5%; CPU remains below 10% threshold | Repo | ✅ `tests/repo/test_bench_matrix.py::TestQueueComparison::test_distinguishes_latency_from_resource_regressions` |
| 76 | rejects non-equivalent queue outcomes | Error | Missing/different completion count | No timing comparison accepted | Repo | ✅ `tests/repo/test_bench_matrix.py::TestQueueComparison::test_rejects_non_equivalent_queue_outcomes` |

### Verification and remaining gates

No stage changes compute language, coordinator, or durable-state owner in M00.
No queue candidate is selected, no migration milestone is merged, and no controlled
performance comparison is accepted. The browser paths in the matrix are relative
to the repository root; other test paths are relative to `backend/`.

The completed CI run at `ed0a8a4d` passes **13,061 non-service tests** and
**294 service-backed tests**, then fails the 90% module floor for `mesh_render`
(79.17%), `stl_fallback` (88.06%), `stl_preview_worker` (88.18%), `thumbnail`
(87.27%), `thumbnail_generations` (89.51%), and `visual_index` (89.24%). Focused
coverage audit: **180 focused tests pass**. Their combined line/branch coverage is
100% for `mesh_render`, 93.23% for `stl_fallback`, 95.45% for `stl_preview_worker`,
and 91.14% for `visual_index`. The focused subset measures 81.21% for `thumbnail`
and 87.47% for `thumbnail_generations`; coverage from the rest of the suite must
still be measured by the complete current-revision gate.
No floor is lowered or new debt entry added. CI now retains its JSON/HTML report
when the coverage gate fails.

The baseline fixes preserve real contracts: file-backed WAL replaces an unsuitable
shared-memory concurrency fixture; browser fixtures wait for upload/tag completion
and target the intended Trash item; empty search uses a unique single token rather
than a phrase whose words match existing Models. Model lifecycle/tag selection pass
three browser repetitions each with retries disabled (**6 passed**); empty-search
checks pass three repetitions and an explicit empty-state assertion. The full real
browser lane requires a new revision because its prior result was **86 passed,
one failed**. One image scanner also requires a fresh result after its vulnerability
database download was interrupted by a network reset; that scan was incomplete.

Both Python 3.13 CI runs expose an anonymous CTE identity collision in sparse
retrieval. A bounded minimal SQLAlchemy reproduction fails on its sixth construction:
`prefix_with()` clones an anonymous CTE, discards its original object, and a later
CTE reuses that object's identity-based name. Scoped named CTEs preserve query
composition. **41 focused Python 3.13 tests pass** with the locked full dependency
set. The first isolated environment lacked the optional tokenizer and was stopped;
it supplies no acceptance evidence. Configured Pyright and benchmark-script
Pyright pass. Direct Pyright on the two search SQL modules reports 31 SQLModel
column-typing errors outside the configured include list; no suppression or scope
exclusion was added. No production dependency was upgraded for this fix.

Benchmark protocol v5 records exact preview source/type/state/failure-reason
outcomes as well as parsed metadata, material requirements, geometry, source bytes,
and preview pixels. Only an identified G-code source's `no_embedded_thumbnail`
outcome is not applicable; unexpected failures remain fatal. The Artifact cache
is isolated under each temporary vault. The initial regression failed before the
fix; **61 focused tests pass**, including real SQLite/PostgreSQL and existing
Orca/BGCODE imports. The two additional stale-source cases and three strengthened Prusa-preview
checks pass. All seven corpus cases pass on SQLite and PostgreSQL (14 total). These local runs are functional checks, not controlled
performance comparisons.

Native instrumentation executed **289 binding, 401 core mesh, 12 application and
11 Rust tests**. The owned-source report measures **96.19% lines, 95.44% regions,
92.98% functions**; native branch coverage is unmeasured. Rust formatting/Clippy
passed. Python's separate subprocess coverage configuration now uses coverage.py's
supported `patch = subprocess`: the same 19 isolated worker tests measure 86.36%
instead of 31.82%, including the actual image-publication path. This configuration
does not establish Rust coverage. See [coverage.py process guidance](https://coverage.readthedocs.io/en/latest/subprocess.html).

The first controlled CI comparison built committed release images and the corpus,
then stopped before measurements because the unprivileged instrumentation layer
could not inspect copied core source directories. The benchmark-only layer now
makes those source directories readable. The existing MinIO migration-source
release remains pinned to its historical digest; its official registry mirror
changed, not its version. Disposable PostgreSQL supports an isolated maintenance
service without Docker socket access or host networking, and uses private generated
credentials. Exact-diff security review through `ed0a8a4d` completed with no findings;
it does not cover subsequent edits. A current review, controlled comparisons,
queue-recovery baseline evidence, and all current CI gates remain open.

The new queue diagnostic found a baseline correctness failure: after a rejected
stale completion, a tentative terminal state remained cached and suppressed the
valid successor's update. A regression reproduces the pending durable row before
the fix. Failed persistence now invalidates that cache entry so the next update
reloads authoritative state. **33 focused command/registry tests pass**. The
SQLite/PostgreSQL process-kill cases both pass. The probe uses the real 120-second lease, bounded
polling, and private migrated databases. It measures repository execution, not
payload processing or queue-library qualification. The original revision's failed
recovery sequence cannot supply an accepted timing comparison; no speedup is
claimed for it. Queue comparison/CI contract checks: **38 tests pass**.

The first successful recovery run exposed a benchmark transport error: application
logs shared stdout with the JSON result. Measurement startup now redirects those
logs to the supervisor log, preserving one structured result on stdout. Both real
database E2Es assert the persisted JSON as well as recovered job outcomes.
