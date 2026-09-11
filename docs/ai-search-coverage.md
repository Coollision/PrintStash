# AI Search implementation coverage

Work in progress for #166, based on the [owner’s independent plan](https://gist.github.com/xiao-villamor/e4daf5562e6a0819c4b7ce3a915bc19c) and [jorgehermo9’s attachment](https://gist.github.com/jorgehermo9/0b348e4411c0b455be7964a1de5f588c). One branch and one eventual PR. No AI Search availability claim yet.

The branch implements W1–W3 and the remote provider/configuration contracts from W4/W4b. W5 connects generation-aware recipes and vector invalidation next. Local acquisition, hybrid retrieval and the remaining feature stages still need their acceptance evidence.

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| A001 | renders a passage with every configured field in template order | Happy | model with name, description, tags, collection | returned text matches the golden template | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_renders_every_recipe_field_in_stable_order` |
| A002 | chunks a document body at the token cap with overlap | Edge | body above the cap | N passages, contiguous, overlap preserved | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_chunks_a_document_body_at_the_token_cap_with_overlap` |
| A003 | caps the number of chunks for an oversized document | Edge | body far above the cap | chunk count == cap; no error | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_caps_the_number_of_chunks_for_an_oversized_document` |
| A004 | changes the content hash when an indexed field changes | Happy | model description edited | `content_hash` differs; stale vectors deleted | Integration | ❌ missing |
| A005 | leaves the content hash untouched for a non-indexed edit | Edge | `updated_at` bumped, fields equal | hash unchanged; no re-embed enqueued | Integration | ❌ missing |
| A006 | removes passages when a subject is trashed | Edge | model trashed | no passages; no vectors; not returned by search | Integration | ❌ missing |
| A007 | restores passages when a subject is restored | Edge | trashed model restored | passages exist again; searchable | Integration | ❌ missing |
| A008 | re-derives a passage the mutation seam missed | Error | row updated bypassing the seam | watermark sweep repairs it | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_repairs_a_body_change_without_a_timestamp` |
| A009 | ranks an exact title match above a body mention | Happy | two models, FTS5 | ordering asserted | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_ranks_exact_title_above_body` |
| A010 | ranks the controlled BM25 fixture consistently on PostgreSQL | Happy | Mismo tokenizer, corpus y pesos; postgres marker | Orden de referencia BM25, no ts_rank etiquetado como BM25 | Integration | ✅ `integration/postgres/test_search_passages.py::TestSearchPassages::test_ranks_postgres_with_real_bm25` |
| A011 | falls back to ranked LIKE when FTS is unavailable | Error | probe forced to fail | results still returned; capability reports the fallback | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_falls_back_when_fts_is_unavailable` |
| A012 | prepares a generation at its index dimension | Happy | Space nativa 1024; MRL index 128 | Tabla derivada de 128; floats durables de 1024 | Integration | ❌ missing |
| A013 | drops the typed table when a generation is retired | Happy | retired generation | table gone; durable vectors deleted in batches | Integration | ❌ missing |
| A014 | keeps autogenerate empty while a generation is live | Edge | live generation, `alembic revision --autogenerate` | empty diff | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_excludes_registered_vector_objects` |
| A015 | preserves vectors across SQLite→PostgreSQL migration | Happy | seeded generation | same vectors, index rebuilt, no re-embed | Integration | ✅ `integration/modules/administration/test_database_transfer.py::TestDatabaseTransfer::test_copies_sqlite_to_postgres_without_inference` |
| A016 | serves search after a backup restore without a reindex | Happy | backup, wipe, restore | identical results | E2E | ✅ `e2e/test_postgres_backup.py::TestPostgresBackup::test_restores_searchable_documents_through_the_api` |
| A017 | returns brute-force results when the vector extension is missing | Error | extension probe fails | same top-k as the native path | Integration | ✅ `integration/postgres/test_vector_index.py::TestPostgresVectorIndex::test_restores_without_pgvector` |
| A018 | embeds a batch through the remote provider | Happy | contract-enforcing fake endpoint over loopback | returned vectors match inputs and declared dimension; persistence covered separately | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_embeds_ordered_text_batches` |
| A019 | refuses a remote dimension mismatch | Error | endpoint returns 512 for a 384 space | generation fails with a stable code; active untouched | Contract | ❌ missing |
| A020 | degrades to lexical when the endpoint times out | Error | endpoint hangs | 200 with `legs: ["lexical"]`; no 5xx | Integration | ❌ missing |
| A021 | retries a 429 with backoff | Error | endpoint returns 429 then 200 | batch completes; attempt count recorded | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_retries_bounded_rate_limits` |
| A022 | never logs the endpoint API key | Error | provider error path | key absent from job status, logs and response | Integration | ❌ missing |
| A023 | resumes a backfill after a process restart | Edge | killed mid-backfill | resumes from the last committed page | Integration | ❌ missing |
| A024 | cancels a backfill between batches | Happy | cancel requested | terminal state; active generation untouched | Integration | ❌ missing |
| A025 | quarantines a repeatedly failing unit | Error | passage that always throws | quarantined after N attempts; worker continues | Integration | ❌ missing |
| A026 | writes new ingests into a building generation | Edge | model ingested mid-backfill | vector present in the building generation | Integration | ❌ missing |
| A027 | keeps serving the old generation during a backfill | Happy | backfill in progress | results come from the active generation | Integration | ❌ missing |
| A028 | activates atomically | Happy | ready generation | one transaction flips both rows; never two active | Integration | ❌ missing |
| A029 | refuses activation when verification fails | Error | Smoke query inválida | building/verify_failed o failed; active preservada | Integration | ❌ missing |
| A030 | refuses a second concurrent generation for one modality | Edge | two starts | second rejected | Integration | ❌ missing |
| A031 | fuses two legs by weighted RRF | Happy | known rank lists | expected fused order | Unit | ❌ missing |
| A032 | drops results below the similarity floor | Edge | out-of-domain query | empty "no strong matches", not nearest neighbours | Integration | ❌ missing |
| A033 | excludes trashed subjects from fused results | Edge | trashed model with a vector | absent | Integration | ❌ missing |
| A034 | applies visibility through browse authorization | Error | User sin acceso a vecinos principales | Solo resultados autorizados tras refetch bounded; página puede ser corta | Integration | ❌ missing |
| A035 | rejects search from a share-link context | Error | share token | 403; no retrieval performed | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_rejects_share_context_search` |
| A036 | returns per-result match evidence | Happy | hybrid query | each result names its leg and field | Integration | ❌ missing |
| A037 | verifies a downloaded model digest before use | Error | tampered file | discarded; stable error; nothing installed | Contract | ❌ missing |
| A038 | never downloads without the opt-in | Error | download disabled | no egress attempted | Integration | ❌ missing |
| A039 | uses a pre-placed model without network access | Happy | files in the cache dir | loads; no request made | Integration | ❌ missing |
| A040 | refuses to prune a model referenced by a live generation | Edge | delete request | 409; file retained | Integration | ❌ missing |
| A041 | prunes the least recently used model above the cache cap | Edge | cache over cap | unreferenced LRU removed | Integration | ❌ missing |
| A042 | reports the local provider unavailable in lite | Edge | import probe fails | capability false; remote still offered | Integration | ❌ missing |
| A043 | embeds a multiview subject into per-view vectors | Happy | mesh, `multiview` | N vectors at distinct `unit_index` | Integration | ❌ missing |
| A044 | retrieves by max-sim over views | Happy | subject matching one view only | retrieved | Integration | ❌ missing |
| A045 | falls back to the thumbnail profile when rendering is unavailable | Error | render capability off | profile degrades with a visible reason | Integration | ❌ missing |
| A046 | embeds an uploaded query image without storing it | Error | image query | results returned; nothing written to storage | Integration | ❌ missing |
| A047 | rejects an oversized or non-image query upload | Error | 50 MB / a zip | 413/415; no embedding attempted | Integration | ❌ missing |
| A048 | keeps a machine caption out of the user description field | Edge | caption generated | `description` unchanged; caption in its own row | Integration | ❌ missing |
| A049 | stops regenerating a dismissed caption | Edge | caption dismissed | not regenerated on the next pass | Integration | ❌ missing |
| A050 | reaches labelled semantic retrieval quality | Happy | Modelo real preplaced o corpus vectorial real versionado | recall@5 hybrid >=0.9 y lexical >=0.6; critical | Integration | ❌ missing |
| A051 | reaches visual recall on stripped descriptions | Happy | Modelo visual real y corpus held-out description-stripped | recall@10 >=0.7; critical | Integration | ❌ missing |
| A052 | switches the model end to end with no search downtime | Happy | seeded library, model change | search answers throughout; new results after the flip (`critical`) | E2E | ❌ missing |
| A053 | keeps ingestion latency flat under backfill load | Edge | ingest during backfill | latency within budget; no failed ingests | E2E | ❌ missing |
| A054 | exposes exactly one provider seam in the tree | Edge | architecture check | no second ONNX session manager, cache or vector store | Integration | ❌ missing |
| A055 | audit-logs an embedding configuration change | Happy | settings patched | audit row with actor and change | Integration | ❌ missing |
| A056 | shows the remote-egress disclosure whenever a remote modality is on | Happy | remote configured | notice present, names the host | Playwright | ❌ missing |
| A057 | finds a just-uploaded model by name immediately | Happy | upload then search | found by lexical before any embedding | Playwright | ❌ missing |
| A058 | returns schema-valid output from a json_schema endpoint | Happy | fake chat endpoint, schema dialect | parsed object matches the schema | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_returns_a_locally_validated_object` |
| A059 | falls back to parse-and-repair without schema support | Error | probe reports no schema, no tools | usable result; reduced guarantee reported | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_repairs_json_once` |
| A060 | probes the Responses API dialect without assuming it | Edge | endpoint lacking it | detected absent; chat-completions used | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_probes_responses_without_assuming_availability` |
| A061 | never logs the chat API key | Error | chat provider error path | key absent from logs, status and response | Integration | ❌ missing |
| A062 | parses natural language into typed filters | Happy | benchy printed last month under 3 hours | Filtros de fecha/duración/outcome válidos más residual benchy | Integration | ❌ missing |
| A063 | rejects a parsed field outside the filter vocabulary | Error | provider emits an unknown field | discarded; query still runs | Integration | ❌ missing |
| A064 | keeps natural-language parsing off by default | Error | chat endpoint configured, switch untouched | no parse attempted; plain hybrid search | Integration | ❌ missing |
| A065 | runs captions with natural-language parsing disabled | Edge | one generative use on, the other off | Caption generado sin invocar parsing de consultas | Integration | ❌ missing |
| A066 | honours a per-user opt-out of query parsing | Error | user preference off, instance on | no parse for that user; others unaffected | Integration | ❌ missing |
| A067 | retains_all_four_subject_types | Happy | Model/Collection/Multipart/Document | Resultados discriminados y autorizados por owner | Integration | ❌ missing |
| A068 | indexes_every_model_context_field | Happy | Nombre/desc/tags/path/files/Revision/provenance; contexto opcional solo si está registrado | Passage contiene field list completa y autorizada de su receta, sin requerir Family | Integration | ❌ missing |
| A069 | indexes_binary_document_metadata_only | Edge | PDF con body no extraído | Search encuentra nombre/filename, no promete texto completo | Integration | ❌ missing |
| A070 | repairs_ancestor_context_changes | Edge | Rename/move Collection sin tocar Model.updated_at | Passages descendientes corregidos por watermark | Integration | ❌ missing |
| A071 | repairs_deleted_contributor_links | Edge | Borrado de relación sin seam | Sweep elimina contribución obsoleta | Integration | ❌ missing |
| A072 | retains_active_recipe_during_reindex | Edge | Nueva recipe mientras active antigua | Ambas recetas coherentes hasta flip | Integration | ❌ missing |
| A073 | does_not_leak_hidden_contributor_text | Error | Multipart visible con Model Choice oculto; contributor opcional de prueba | Ni ranking ni snippets/vector accesible dependen de texto oculto | Integration | ❌ missing |
| A074 | applies_permission_revocation_immediately | Error | Permiso cambia tras index/cache | Resultado y evidence ocultos en consulta siguiente | Integration | ❌ missing |
| A075 | rolls_back_lexical_projection_with_mutation | Error | Transacción de Model falla | Sin Passage/FTS huérfano | Integration | ❌ missing |
| A076 | keeps_ingest_searchable_when_fts_fails | Error | FTS no disponible en commit | Texto durable encuentra upload vía ranked fallback | Integration | ❌ missing |
| A077 | escapes_lexical_query_syntax | Error | Comillas, operadores, %, _, unicode | Sin SQL/FTS injection ni 500 | Integration | ❌ missing |
| A078 | updates_bm25_corpus_statistics | Edge | Create/edit/delete Passage; ambos motores | Ranking y df/longitudes coherentes | Integration | ❌ missing |
| A079 | uses_native_float_vector_codec | Happy | Vector dimensionado nativo | Bytes LE roundtrip sin pérdida aparte float32 declarado | Unit | ❌ missing |
| A080 | rejects_nonfinite_provider_vectors | Error | NaN/inf/cero no permitido/mala longitud | Código estable, no vector activo corrupto | Contract | ❌ missing |
| A081 | distinguishes_artifact_component_units | Edge | Dos Artifacts del Model con component 0 | Dos unidades durables distintas | Integration | ❌ missing |
| A082 | rejects_cross_space_vector_comparison | Error | Misma dimension pero CLIP/BGE distintos | Comparación denegada, sin ranking inventado | Unit | ❌ missing |
| A083 | truncates_only_registry_approved_mrl_points | Error | Dimensión no soportada o modelo no MRL | Propuesta inválida; active intacta | Integration | ❌ missing |
| A084 | normalizes_mrl_prefix | Happy | Prefix válido de vector nativo | Norma unitaria y dimensión elegida | Unit | ❌ missing |
| A085 | roundtrips_int8_transform_metadata | Happy | Calibración/version fijas | Transformada reproducible al reconstruir índice | Unit | ❌ missing |
| A086 | rescales_quantized_shortlist_with_float_vectors | Happy | Index int8/binary; float source | Top-k dentro de tolerancia medida del baseline | Integration | ❌ missing |
| A087 | retains_native_vectors_after_truncation | Edge | Generación 128 de Space 1024 | Floats de 1024 siguen disponibles para rebuild | Integration | ❌ missing |
| A088 | switches_index_backend_without_embedding | Happy | NumPy↔sqlite-vec o pgvector↔NumPy | Flip continuo; ningún nuevo input recibido por fake provider | E2E | ❌ missing |
| A089 | serves_queries_during_startup_rebuild | Edge | Restart con derivados ausentes | Búsqueda sirve antes de completar rebuild | E2E | ❌ missing |
| A090 | preserves_inflight_generation_readers | Edge | Activate durante query antigua | Query completa con su Space; cleanup espera drain | Integration | ❌ missing |
| A091 | refuses_insufficient_swap_capacity | Error | Cache/disco no admite old+new | 409/resource code; active utilizable | Integration | ❌ missing |
| A092 | rejects_stale_backfill_publication | Edge | Passage cambia durante inference | No vector viejo publicado como current | Integration | ❌ missing |
| A093 | refuses_unexplained_quarantine_at_activation | Error | Fallos de inferencia pendientes al verify | No activa generación incompleta sin explicación | Integration | ❌ missing |
| A094 | detects_unmanaged_schema_drift | Error | Tabla ajena termina en _data | Autogenerate la detecta; no exclusión genérica | Integration | ❌ missing |
| A095 | disables_sqlite_extension_loading_after_connect | Edge | Conexiones sync/async; carga falla | Load_extension deshabilitado al terminar hook | Integration | ✅ `integration/db/test_vector_extensions.py::TestVectorExtensions::test_disables_loading_after_async_connect` |
| A096 | degrades_when_pg_extension_cannot_be_created | Error | Disponible pero usuario sin permiso | NumPy fallback; startup no falla | Integration | ✅ `integration/postgres/test_vector_index.py::TestPostgresVectorIndex::test_degrades_when_pg_extension_cannot_be_created` |
| A097 | restores_without_vector_extension | Edge | Backup nativo restaurado sin extensión | Datos/vector durables consultables; rebuild background | E2E | ❌ missing |
| A098 | probes_chat_tool_calling_fallback | Happy | Endpoint tools sin json_schema | Objeto validado con guarantee reportada | Contract | ❌ missing |
| A099 | rejects_invalid_chat_schema_output | Error | Endpoint devuelve key extra/type erróneo | Nada ejecutado como filtro; fallback limpio | Contract | ❌ missing |
| A100 | bounds_chat_parse_repair | Error | JSON inválido repetido | Se detiene en límite; no loop de llamadas | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_rejects_a_failed_repair` |
| A101 | opens_circuit_after_provider_failures | Error | Endpoint devuelve fallos repetidos | Operaciones se degradan dentro del deadline | Contract | ❌ missing |
| A102 | requires_declared_image_embedding_contract | Error | Endpoint solo compatible texto | Imagen unavailable, no payload adivinado | Contract | ❌ missing |
| A103 | separates_remote_modality_consent | Error | Texto consentido, visual/caption no | No imágenes recibidas por fake host | Contract | ❌ missing |
| A104 | never_sends_raw_geometry_to_provider | Error | Consulta/componente de malla | Recorder contiene solo modalidades permitidas | Contract | ❌ missing |
| A105 | encrypts_sensitive_extra_headers | Error | Header Authorization personalizado | DB/readback/logs no contienen secreto claro | Integration | ❌ missing |
| A106 | hides_private_hosts_from_public_health | Error | Endpoint LAN configurado | Public health sin host privado; admin disclosure presente | Integration | ❌ missing |
| A107 | rejects_download_redirect_outside_policy | Error | HF/mirror redirige a host no permitido | Archivo no instalado y egress denegado | Contract | ❌ missing |
| A108 | caps_actual_download_bytes | Error | Content-Length engañoso | Descarga abortada y temp eliminado | Contract | ❌ missing |
| A109 | installs_model_files_atomically | Edge | Crash entre dos archivos de manifest | Cache no presenta modelo incompleto como usable | Integration | ❌ missing |
| A110 | rejects_model_cache_path_escape | Error | Manifest traversal/symlink | Sin escritura fuera de cache root | Integration | ❌ missing |
| A111 | refuses_custom_onnx_operators | Error | Custom graph necesita operator library | Capability rechazada antes de ejecución | Integration | ❌ missing |
| A112 | pins_cache_during_concurrent_load | Edge | LRU prune corre durante load | Modelo en uso no borrado | Integration | ❌ missing |
| A113 | honours_shared_render_budget | Edge | Thumbnail y multiview concurrentes más consumidor de prueba del mismo permiso | Concurrencia/RSS global dentro del cap sin instalar Similar Models | Integration | ❌ missing |
| A114 | aggregates_normalized_multiview_mean | Happy | Vistas válidas con normas distintas | Vector agregado conforme receta | Unit | ❌ missing |
| A115 | retrieves_printed_part_photo | Happy | Foto real fixture; Space compatible | Source Model en top10 | Integration | ❌ missing |
| A116 | rejects_image_decompression_bomb | Error | Pocos bytes, exceso de píxeles | 413/422 antes de tensor gigante | Integration | ❌ missing |
| A117 | strips_query_image_exif | Edge | Foto con GPS/orientation | Provider recibe imagen orientada sin EXIF | Contract | ❌ missing |
| A118 | avoids_query_upload_disk_spooling | Error | Multipart a través del proxy configurado | Sin archivo temporal persistido del upload | E2E | ❌ missing |
| A119 | degrades_visual_only_to_ready_generation | Error | Pointcloud/multiview capability falla | Siguiente rung listo o texto con motivo real | Integration | ❌ missing |
| A120 | preserves_edited_caption_on_worker_completion | Edge | Usuario edita durante llamada VLM | Caption humana editada no sobrescrita | Integration | ❌ missing |
| A121 | removes_dismissed_caption_from_search | Edge | Dismiss de caption ya indexada | No contribuye a resultados posteriores | Integration | ❌ missing |
| A122 | keeps_caption_disabled_by_default | Error | Chat endpoint configurado | No generación sin switch caption | Integration | ❌ missing |
| A123 | runs_nl_filters_with_caption_disabled | Happy | Solo NL habilitado | Parse funciona sin generar captions | Integration | ❌ missing |
| A124 | filters_one_qualifying_print_job | Edge | Un job cumple fecha; otro duración | Model excluido si ninguno cumple conjunto | Integration | ❌ missing |
| A125 | handles_print_date_timezone_boundaries | Edge | Mes pasado con DST y bordes de medianoche | Límites UTC de calendario correctos | Unit | ❌ missing |
| A126 | does_not_use_estimated_duration_as_actual | Edge | Slicer duration cumple; actual_duration_s null | Filtro de duración real no incluye el Model | Integration | ❌ missing |
| A127 | rejects_unauthorized_parsed_identifiers | Error | Chat emite Collection/printer no visible | Filtro descartado sin disclosure | Integration | ❌ missing |
| A128 | restores_nl_chips_from_canonical_url | Happy | Parse y recarga URL | Filtros y residual restaurados | Playwright | ❌ missing |
| A129 | removes_one_nl_filter_chip | Happy | Quitar duración de parse | Solo esa restricción desaparece; no reparse automático | Playwright | ❌ missing |
| A130 | saves_nl_filters_without_freezing_ranking | Happy | Guardar resultado en Saved View | Typed filters y residual persisten; ranking no | Playwright | ❌ missing |
| A131 | avoids_query_text_in_access_logs | Error | Query normal y error por proxy/ASGI | q/prompt ausentes de logs y jobs | E2E | ❌ missing |
| A132 | disables_all_ai_affordances_with_master | Edge | Master off con generations existentes | Lexical utilizable y UI sin controles AI activos | Playwright | ❌ missing |
| A133 | bounds_query_execution_deadline | Error | ONNX worker ocupado/endpoint lento | Respuesta léxica antes de deadline; event loop responde | Integration | ❌ missing |
| A134 | measures_query_p95_on_100k_passages | Happy | 4-core, Space default, corpus etiquetado | p95 end-to-end <300ms; el gate falla si supera objetivo | E2E | ❌ missing |
| A135 | measures_pi5_default_backfill_budget | Happy | 100k Passages y default real | Backfill <1h; el gate falla si supera objetivo | E2E | ❌ missing |
| A136 | versions_sparse_expansion_independently | Edge | Toggle/model de expansión cambia | Lexical original sigue disponible durante rebuild | Integration | ❌ missing |
| A137 | measures_sparse_expansion_cost | Happy | Corpus con expansión opt-in | Tamaño y recall comparados con lexical base | Integration | ❌ missing |
| A138 | localizes_ai_search_states | Edge | en/es; pending/degraded/empty/caption/NL | Texto traducido, foco y controles accesibles | Frontend unit | ❌ missing |
| A139 | roundtrips_search_schema_with_existing_data | Happy | Upgrade/downgrade/upgrade; SQLite/PostgreSQL poblados | Tablas/config nuevas reversibles; datos previos conservados | Integration | ❌ missing |
| A140 | switches_visual_profile_independently | Happy | Text active mientras se cambia perfil visual | Text Generation intacta; visual flip propio | Integration | ❌ missing |
| A141 | measures_profile_rung_quality_gain | Happy | Mismo held-out corpus y modelo por recipe | Cada rung ofrecido mejora métrica sobre anterior; salida S1 documentada | Integration | ❌ missing |
| A142 | delivers_search_without_related_features | Happy | Main con esta PR; modules similarity y families ausentes | Migración, upload, búsqueda y swap funcionan con los cuatro Subject types propios | E2E | ❌ missing |

`critical-capabilities.json` gains `ai-search-model-swap-no-downtime` (row 52), `ai-search-retrieval-quality` (rows 50–51) and `ai-search-disabled-degradation` (rows 11 and 20). Coverage floors are raised for both new modules in the same PR, per the two-sided floor rule.

## W1 subcontracts verified in this increment

The original acceptance rows above retain their full outcomes: rows requiring
automatic synchronization, vectors or retrieval remain missing even where the
internal persistence subcontracts below now pass. `core/` paths refer to
`backend/packages/printstash-core/tests/`; other paths refer to `backend/tests/`.

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| P001 | accepts each supported subject | Happy | Each registered Subject type, id=1 | Typed Subject identity retained | Unit | ✅ `core/search/test_passages.py::TestSearchSubject::test_accepts_each_supported_subject` |
| P002 | rejects invalid subject ids | Error | Zero, negative, overflow, boolean, float or string ID | ValueError identifies invalid Subject ID | Unit | ✅ `core/search/test_passages.py::TestSearchSubject::test_rejects_invalid_subject_ids` |
| P003 | rejects an unsupported subject type | Error | Artifact used as Subject type | ValueError rejects unsupported type | Unit | ✅ `core/search/test_passages.py::TestSearchSubject::test_rejects_an_unsupported_subject_type` |
| P004 | canonicalizes conjunctive access dependencies | Happy | Repeated and reordered contributor Subjects | Canonical conjunctive JSON and identical segment digest | Unit | ✅ `core/search/test_passages.py::TestAccessIdentity::test_canonicalizes_conjunctive_access_dependencies` |
| P005 | distinguishes subject types with equal ids | Edge | Model and Collection share numeric ID | Different access segment identities | Unit | ✅ `core/search/test_passages.py::TestAccessIdentity::test_distinguishes_subject_types_with_equal_ids` |
| P006 | represents a subject only segment | Edge | No additional contributors | Empty dependency array; Subject access still required | Unit | ✅ `core/search/test_passages.py::TestAccessIdentity::test_represents_a_subject_only_segment` |
| P007 | renders every recipe field in stable order | Happy | Every recipe-v1 field populated | Exact labelled text in fixed field order | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_renders_every_recipe_field_in_stable_order` |
| P008 | preserves unicode text | Edge | Accents, CJK, control characters and Markdown | NFC text and whitespace retained without NUL | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_preserves_unicode_text` |
| P009 | omits empty fields | Edge | Title with absent optional metadata | No empty labels | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_omits_empty_fields` |
| P010 | deduplicates repeated list values | Edge | Duplicate and blank tag values | Stable distinct nonempty values | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_deduplicates_repeated_list_values` |
| P011 | chunks a document body at the token cap with overlap | Edge | 500-word Markdown body | Two windows with 40 recipe-token overlap and retained endpoints | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_chunks_a_document_body_at_the_token_cap_with_overlap` |
| P012 | keeps a body at the token boundary in one passage | Edge | Exactly 400 recipe tokens including body label | One complete passage without truncation | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_keeps_a_body_at_the_token_boundary_in_one_passage` |
| P013 | caps the number of chunks for an oversized document | Edge | Body exceeding 16 passage windows | Exactly 16 passages, all marked truncated | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_caps_the_number_of_chunks_for_an_oversized_document` |
| P014 | reports bounded truncation | Edge | Oversized title, list, body, list entry or indivisible token | Explicit truncation and 16,384-character passage cap | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_reports_bounded_truncation` |
| P015 | reserves body space when metadata fills its budget | Edge | Metadata exceeds half the passage budget | Body text survives; truncation reported | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_reserves_body_space_when_metadata_fills_its_budget` |
| P016 | changes the hash when text changes | Happy | Title changes | Different deterministic content hash | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_changes_the_hash_when_text_changes` |
| P017 | keeps identical text hashes stable | Edge | Equivalent normalized title text | Identical passages and hashes | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_keeps_identical_text_hashes_stable` |
| P018 | accepts empty content | Edge | All fields empty | One empty, nontruncated passage | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_accepts_empty_content` |
| P019 | persists model text | Happy | Model with description | Durable labelled text with Subject-only access segment | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_persists_model_text` |
| P020 | preserves idempotent passage identity | Edge | Repeated identical projection | Same IDs, hashes and content watermark; no changes | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_preserves_idempotent_passage_identity` |
| P021 | ignores nonindexed edits for content freshness | Edge | Only thumbnail and source timestamp change | Content identity unchanged; no content update | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_ignores_nonindexed_edits_for_content_freshness` |
| P022 | replaces changed passage content | Happy | Model description edited | Stable ID with new text and content hash | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_replaces_changed_passage_content` |
| P023 | removes obsolete passage windows | Edge | Long Document shortened | Surplus passage removed; first window replaced | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_removes_obsolete_passage_windows` |
| P024 | preserves other live recipes | Edge | A different recipe remains live | Other recipe text preserved | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_preserves_other_live_recipes` |
| P025 | removes every recipe for a trashed subject | Edge | Trashed Model with two stored recipes | Every recipe removed | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_removes_every_recipe_for_a_trashed_subject` |
| P026 | removes passages for a purged subject | Edge | Model physically deleted | Orphan passage removed | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_removes_passages_for_a_purged_subject` |
| P027 | restores passages for a restored subject | Edge | Trashed Model restored | Current recipe recreated | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_restores_passages_for_a_restored_subject` |
| P028 | rolls projection back with content | Error | Content edit and projection followed by rollback | Neither edit survives | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_rolls_projection_back_with_content` |
| P029 | does not create rows for a missing subject | Edge | Missing Model ID | No passage created | Integration | ✅ `integration/modules/search/test_passages.py::TestSyncSubject::test_does_not_create_rows_for_a_missing_subject` |
| P030 | projects model fields | Happy | Model with Collection and G-code Revision | Name, description, path, filename, Revision label and notes projected | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_projects_model_fields` |
| P031 | uses effective tags | Happy | Direct, ancestor and Artifact tags; duplicate association | Sorted distinct effective tags | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_uses_effective_tags` |
| P032 | excludes trashed artifact text | Edge | Trashed Artifact carries filename and notes | No Artifact text projected | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_excludes_trashed_artifact_text` |
| P033 | ignores nonrevision notes | Edge | STL with legacy Revision notes | Non-Revision notes excluded | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_ignores_nonrevision_notes` |
| P034 | honors provenance overrides | Happy | User overrides source title and description | Effective title, summary and source tags projected | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_honors_provenance_overrides` |
| P035 | honors cleared provenance text | Edge | User clears captured title to null | Suppressed captured title excluded | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_honors_cleared_provenance_text` |
| P036 | reports excess source tags | Edge | Source tag list exceeds recipe cap | Extraction truncation reported | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_reports_excess_source_tags` |
| P037 | ignores nontext provenance tags | Error | Mixed-type tag list or non-list JSON | Only textual tags retained | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_ignores_nontext_provenance_tags` |
| P038 | projects collection fields | Happy | Collection with Markdown readme | Name, path and description projected | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_projects_collection_fields` |
| P039 | projects multipart parts | Happy | Multipart Model with named Multipart Part | Grouping metadata and Part name projected | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_projects_multipart_parts` |
| P040 | segments multipart member context | Happy | Grouping references member in another Collection | Member name and label only in a Model-dependent segment | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_segments_multipart_member_context` |
| P041 | projects markdown body | Happy | Markdown Document | Body retained; binary filename not projected | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_projects_markdown_body` |
| P042 | indexes only binary document metadata | Edge | PDF or other binary with stray body field | Only name and filename projected; no body extraction | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_indexes_only_binary_document_metadata` |
| P043 | excludes trashed subjects | Edge | Trashed Model, Collection or Document | No Subject projection | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_excludes_trashed_subjects` |
| P044 | omits missing subjects | Edge | Missing Subject in each registered type | No Subject projection | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_omits_missing_subjects` |
| P045 | excludes the external print sentinel | Edge | External-print sentinel Model | Sentinel excluded | Integration | ✅ `integration/modules/search/test_sources.py::TestProjectSubject::test_excludes_the_external_print_sentinel` |
| P046 | upgrades without losing library content | Happy | Previous SQLite schema with a real Model | Additive table upgrade retains library content | Integration | ✅ `integration/db/migrations/test_search_passages_migration.py::TestSearchPassagesMigration::test_upgrades_without_losing_library_content` |
| P047 | downgrades without losing library content | Happy | SQLite schema downgrade with a real Model | Only passage table removed | Integration | ✅ `integration/db/migrations/test_search_passages_migration.py::TestSearchPassagesMigration::test_downgrades_without_losing_library_content` |
| P048 | emits portable offline schema | Happy | SQLite and PostgreSQL offline DDL | Passage table and constraints rendered | Integration | ✅ `integration/db/migrations/test_search_passages_migration.py::TestSearchPassagesMigration::test_emits_portable_offline_schema` |
| P049 | projects existing models after upgrade | Happy | Existing PostgreSQL Model upgraded to passage schema | Durable Unicode passage after projection | Integration | ✅ `integration/postgres/test_search_passages.py::TestSearchPassages::test_projects_existing_models_after_upgrade` |
| P050 | rejects duplicate passage identity | Error | Duplicate identity on PostgreSQL | Unique constraint rejects duplicate; original retained | Integration | ✅ `integration/postgres/test_search_passages.py::TestSearchPassages::test_rejects_duplicate_passage_identity` |
| P051 | indexes a new document before commit returns | Happy | Document created through the real HTTP API | Current passage visible in a fresh database session without explicit indexing | E2E | ✅ `e2e/test_search_passages.py::TestSearchPassageLifecycle::test_indexes_a_new_document_before_commit_returns` |
| P052 | search passage builder preserves subject identity | Happy | Factory receives a real Model Subject | Persisted owner, access requirements and default text match | Integration | ✅ `repo/test_factories.py::TestGeneratedIdentities::test_search_passage_builder_preserves_subject_identity` |

## W1 transaction and reconciliation checks

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| P053 | projects an authorized model edit | Happy | Authorized Model rename | Passage updated before operation returns | Integration | ✅ `integration/modules/search/test_projection.py::TestContentProjection::test_projects_an_authorized_model_edit` |
| P054 | refreshes descendants after an ancestor tag change | Edge | Ancestor tag assignment | Descendant Model passage gains effective tag | Integration | ✅ `integration/modules/search/test_projection.py::TestContentProjection::test_refreshes_descendants_after_an_ancestor_tag_change` |
| P055 | refreshes removed relationships | Edge | Direct tag link removed | Stale tag removed from passage | Integration | ✅ `integration/modules/search/test_projection.py::TestContentProjection::test_refreshes_removed_relationships` |
| P056 | rolls back a content notification | Error | Content notification then rollback | Source projection restored atomically | Integration | ✅ `integration/modules/search/test_projection.py::TestContentProjection::test_rolls_back_a_content_notification` |
| P057 | leaves content usable without a projection | Edge | Optional projection unbound | Content commit succeeds without passages | Integration | ✅ `integration/modules/search/test_projection.py::TestContentProjection::test_leaves_content_usable_without_a_projection` |
| P058 | repairs a body change without a timestamp | Edge | Document changed outside mutation port | Partition sweep corrects text | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_repairs_a_body_change_without_a_timestamp` |
| P059 | persists the partition cursor | Happy | First bounded page commits | Durable cursor names last visited Subject | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_persists_the_partition_cursor` |
| P060 | removes a passage after an unobserved deletion | Edge | Subject removed without notification | Orphan passage removed | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_removes_a_passage_after_an_unobserved_deletion` |
| P061 | limits work to the current partition | Edge | Four Subjects and page limit two | Only current two Subjects projected | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_limits_work_to_the_current_partition` |
| P062 | reaches the next partition | Happy | Two successive bounded pages | All four Subjects eventually projected | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_reaches_the_next_partition` |

## W1 content-owner lifecycle validation

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| P063 | indexes_a_new_document_before_commit_returns | Happy | create Markdown through the API | durable title and body passage | E2E | ⏭️ N/A — same headline lifecycle now covered by P051 |
| P064 | replaces_a_document_body_after_edit | Happy | edit a projected Markdown body | only current body remains | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestDocumentProjection::test_replaces_a_document_body_after_edit` |
| P065 | removes_a_trashed_document | Happy | trash a projected Document | no passage remains | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestDocumentProjection::test_removes_a_trashed_document` |
| P066 | reindexes_a_restored_document | Happy | restore a trashed Document | current passage returns | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestDocumentProjection::test_reindexes_a_restored_document` |
| P067 | removes_a_purged_document | Happy | permanently delete a projected Document | passages and dependencies removed | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestDocumentProjection::test_removes_a_purged_document` |
| P068 | indexes_an_uploaded_markdown_document | Happy | upload Markdown bytes | body searchable in durable passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestDocumentProjection::test_indexes_an_uploaded_markdown_document` |
| P069 | indexes_an_uploaded_binary_filename | Happy | upload PDF bytes | filename metadata indexed without binary content | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestDocumentProjection::test_indexes_an_uploaded_binary_filename` |
| P070 | refreshes_models_after_collection_rename | Happy | rename an ancestor Collection | descendant Model passage contains new path | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestTaxonomyProjection::test_refreshes_models_after_collection_rename` |
| P071 | replaces_collection_readme | Happy | edit Collection landing text | current README passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestTaxonomyProjection::test_replaces_collection_readme` |
| P072 | refreshes_models_after_collection_tags | Happy | replace inherited tags through API | Model passage contains replacement tag | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestTaxonomyProjection::test_refreshes_models_after_collection_tags` |
| P073 | removes_deleted_tag_text | Edge | delete a tag after projection | dependent Model omits deleted tag | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestTaxonomyProjection::test_removes_deleted_tag_text` |
| P074 | indexes_a_new_multipart_model | Happy | create a multipart aggregate through API | shared title passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestMultipartProjection::test_indexes_a_new_multipart_model` |
| P075 | refreshes_multipart_metadata | Happy | rename aggregate | current shared title passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestMultipartProjection::test_refreshes_multipart_metadata` |
| P076 | removes_a_deleted_multipart_model | Happy | delete aggregate | no aggregate passages | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestMultipartProjection::test_removes_a_deleted_multipart_model` |
| P077 | refreshes_batch_model_moves | Happy | move selected Models | current collection path | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_refreshes_batch_model_moves` |
| P078 | refreshes_batch_model_tags | Happy | replace selected Model tags | current effective tag text | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_refreshes_batch_model_tags` |
| P079 | removes_a_trashed_model | Happy | trash a projected Model | no Model passages | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_removes_a_trashed_model` |
| P080 | reindexes_a_restored_model | Happy | restore Model | current Model passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_reindexes_a_restored_model` |
| P081 | refreshes_revision_notes | Happy | edit Revision notes | current Revision text in Model passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_refreshes_revision_notes` |
| P082 | removes_a_trashed_revision_filename | Happy | trash a Revision | removed filename absent from Model passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_removes_a_trashed_revision_filename` |
| P083 | refreshes_artifact_tags | Happy | replace Artifact tags | Model effective tag text updated | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_refreshes_artifact_tags` |
| P084 | refreshes_provenance_override | Happy | edit captured title override | effective override appears in Model passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_refreshes_provenance_override` |
| P085 | indexes_ingested_artifact_metadata | Happy | persist a new Artifact | filename in durable Model passage | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_indexes_ingested_artifact_metadata` |
| P086 | omits_derived_passages_from_audit | Edge | content projection while audit installed | no duplicate text in audit derivative rows | Integration | ✅ `integration/modules/search/projection/test_content_lifecycle.py::TestModelProjection::test_omits_derived_passages_from_audit` |
| P087 | defers_projection_repair_during_restore | Edge | restore maintenance active | no repair checkpoint created | Integration | ✅ `integration/runtime/test_search.py::TestSearchRuntime::test_defers_projection_repair_during_restore` |
| P088 | commits_a_projection_repair_partition | Happy | repair existing Document in worker | fresh session sees passage | Integration | ✅ `integration/runtime/test_search.py::TestSearchRuntime::test_commits_a_projection_repair_partition` |
| P089 | cancellation_waits_for_projection_repair | Edge | cancel scheduler during admitted unit | unit finishes before cancellation completes | Integration | ✅ `integration/runtime/test_search.py::TestSearchRuntime::test_cancellation_waits_for_projection_repair` |
| P090 | preserves_content_when_projection_fails | Error | projection raises during Model edit | source edit and projection roll back | Integration | ✅ `integration/modules/search/test_projection.py::TestContentProjection::test_preserves_content_when_projection_fails` |
| P091 | rejects_an_invalid_repair_limit | Error | limit zero or above maximum | ValueError before writes | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_rejects_an_invalid_repair_limit` |
| P092 | upgrades_projection_checkpoints_with_content | Happy | existing library at passage migration | upgrade preserves content and supports checkpoints | Integration | ✅ `integration/db/migrations/test_search_checkpoints_migration.py::TestSearchCheckpointsMigration::test_upgrades_projection_checkpoints_with_content` |
| P093 | downgrades_projection_checkpoints_with_content | Happy | library at checkpoint migration | downgrade preserves library and passage rows | Integration | ✅ `integration/db/migrations/test_search_checkpoints_migration.py::TestSearchCheckpointsMigration::test_downgrades_projection_checkpoints_with_content` |

## W2 lexical ranking and failure handling

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| L001 | tokenizes_unicode_query_without_operators | Edge | punctuation, accents, FTS operators | bounded literal tokens | Unit | ✅ `core/search/test_lexical.py::TestLexical::test_tokenizes_unicode_query_without_operators` |
| L002 | computes_reference_bm25 | Happy | fixed corpus counts and field frequencies | numeric BM25 reference | Unit | ✅ `core/search/test_lexical.py::TestLexical::test_computes_reference_bm25` |
| L003 | ranks_exact_title_above_body | Happy | identical word in title versus description | title Subject first | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_ranks_exact_title_above_body` |
| L004 | searches_current_content_after_edit | Happy | already indexed Model renamed | new query matches; old does not | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_searches_current_content_after_edit` |
| L005 | removes_deleted_content_from_native_index | Edge | indexed Subject trashed | old query returns no result | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_removes_deleted_content_from_native_index` |
| L006 | rolls_back_lexical_edits | Error | source transaction rolled back | original matches preserved | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_rolls_back_lexical_edits` |
| L007 | falls_back_when_fts_is_unavailable | Error | native capability absent | weighted LIKE returns result with fallback status | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_falls_back_when_fts_is_unavailable` |
| L008 | preserves_content_when_native_update_fails | Error | FTS update fails | source and durable passage commit; LIKE finds new name | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_preserves_content_when_native_update_fails` |
| L009 | repairs_native_index_in_bounded_pages | Edge | missing index over existing passages | cursor advances; queries work after rebuild | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_repairs_native_index_in_bounded_pages` |
| L010 | ranks_postgres_with_real_bm25 | Happy | controlled corpus on PostgreSQL | reference ranking using term statistics | Integration | ✅ `integration/postgres/test_search_passages.py::TestSearchPassages::test_ranks_postgres_with_real_bm25` |
| L011 | maintains_postgres_statistics_after_delete | Edge | indexed passage deleted | df, corpus length and document count updated | Integration | ✅ `integration/postgres/test_search_passages.py::TestSearchPassages::test_maintains_postgres_statistics_after_delete` |
| L012 | searches_all_public_subject_types | Happy | Model, Collection, Multipart Model, Document | discriminated authorized results | E2E | ✅ `e2e/test_search_passages.py::TestSearchPassageLifecycle::test_searches_all_public_subject_types` |
| L013 | rejects_unauthenticated_search | Error | no credentials | 401 before retrieval | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_rejects_unauthenticated_search` |
| L014 | rejects_share_context_search | Error | share token | denied before retrieval | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_rejects_share_context_search` |
| L015 | hides_unauthorized_member_segments | Error | aggregate readable; member private | private member terms yield no aggregate result | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_hides_unauthorized_member_segments` |
| L016 | applies_permission_revocation_immediately | Edge | access revoked after indexing | no restricted result or highlight | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_applies_permission_revocation_immediately` |
| L017 | escapes_like_wildcards | Edge | literal percent and underscore query | no wildcard widening | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_escapes_like_wildcards` |
| L018 | returns_bounded_plain_text_evidence | Edge | hostile HTML in indexed content | escaped-by-consumer text plus match ranges; no raw HTML | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_returns_bounded_plain_text_evidence` |
| L019 | ranks_library_browse_through_read_port | Happy | exact title and body matches | Model browse order agrees with lexical relevance | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_ranks_library_browse_through_read_port` |
| L020 | detects_unmanaged_schema_drift | Error | unrelated table resembling a shadow | autogenerate reports it | Integration | ✅ `integration/db/derived_objects/test_search_fts.py::TestSearchDerivedObjects::test_detects_unmanaged_schema_drift` |
| L021 | excludes_only_registered_fts_objects_from_autogenerate | Edge | populated native FTS index | no derivative drift | Integration | ✅ `integration/db/derived_objects/test_search_fts.py::TestSearchDerivedObjects::test_excludes_only_registered_fts_objects_from_autogenerate` |

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| P094 | removes_an_orphan_dependency_without_a_passage | Edge | source and passage removed outside owner | dependency inventory removed by bounded repair | Integration | ✅ `integration/modules/search/test_reconciliation.py::TestReconciliation::test_removes_an_orphan_dependency_without_a_passage` |
| L022 | hides_private_member_context_on_postgres | Error | readable aggregate with unreadable member on PostgreSQL | no private term match | Integration | ✅ `integration/postgres/test_search_passages.py::TestSearchPassages::test_hides_private_member_context_on_postgres` |
| L023 | paginates_ranked_library_browse | Happy | multiple ranked Model matches | no repeats, exact total, terminal cursor | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_paginates_ranked_library_browse` |
| L024 | rejects_a_cursor_from_another_query | Error | signed cursor reused with different query | stable invalid-cursor error | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_rejects_a_cursor_from_another_query` |
| L025 | paginates_without_repeating_a_subject | Happy | more Subjects than page size | each Subject once across pages | Integration | ✅ `integration/api/v1/test_search.py::TestSearch::test_paginates_without_repeating_a_subject` |
| L026 | browse_falls_back_after_native_table_loss | Error | native FTS table removed after initialization | ranked browse still returns current Model | Integration | ✅ `integration/modules/search/test_lexical_query.py::TestLexicalQuery::test_browse_falls_back_after_native_table_loss` |

## Shared vector platform

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| V001 | preserves_legacy_space_hash | Edge | persisted v1 CLIP contract | identical identity after adoption | Core | ✅ `core/inference/test_embedding.py::TestEmbeddingSpace::test_preserves_legacy_space_hash` |
| V002 | isolates_inference_identity | Error | equal dimensions, different aligned model/config | distinct immutable Space | Core | ✅ `core/inference/test_embedding.py::TestEmbeddingSpace::test_isolates_inference_identity` |
| V003 | keeps_subject_types_distinct | Edge | Model and Document share integer ID | two separate neighbors | Core | ✅ `core/inference/test_vectors.py::TestCosineNeighbors::test_keeps_subject_types_distinct` |
| V004 | publishes_a_document_without_similarity | Happy | plain Space, generation and Document passage | source-fenced native vector and authorized neighbor | Integration | ✅ `integration/modules/search/test_vector_store.py::TestVectorStore::test_publishes_a_document_without_similarity` |
| V005 | refuses_stale_source_publication | Edge | passage changes while embedding | old hash cannot publish | Integration | ✅ `integration/modules/search/test_vector_store.py::TestVectorStore::test_refuses_stale_source_publication` |
| V006 | preserves_legacy_vectors_on_upgrade | Edge | seeded pre-166 native blobs and unit keys | same bytes/IDs, typed Model mapping | Integration | ✅ `integration/db/migrations/test_search_vectors_migration.py::TestSearchVectorsMigration::test_preserves_legacy_vectors_on_upgrade` |
| V007 | excludes_registered_vector_objects | Edge | live native generation and unrelated similarly named table | only exact registered derivatives excluded | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_excludes_registered_vector_objects` |
| V008 | restores_native_vectors_without_extension | Error | native database backup, extension absent on restore | portable full-float neighbors, no embedding call | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_restores_native_vectors_without_extension` |
| V009 | copies_sqlite_to_postgres_without_inference | Happy | seeded current SQLite with library/vector data | same durable counts/hashes/IDs on empty PostgreSQL | Integration | ✅ `integration/modules/administration/test_database_transfer.py::TestDatabaseTransfer::test_copies_sqlite_to_postgres_without_inference` |
| V010 | refuses_nonempty_migration_target | Error | target already contains user data | refuses before any mutation | Integration | ✅ `integration/modules/administration/test_database_transfer.py::TestDatabaseTransfer::test_refuses_nonempty_migration_target` |
| V011 | previews_database_migration | Edge | dry-run against empty target | validated copy plan, target stays empty | Integration | ✅ `integration/modules/administration/test_database_transfer.py::TestDatabaseTransfer::test_previews_database_migration` |
| V012 | stages_vectors_without_committing_source | Edge | authorized CTE publication then rollback | no vector survives outside caller transaction | Integration | ✅ `integration/modules/search/test_vector_store.py::TestVectorStore::test_stages_vectors_without_committing_source` |
| V013 | queries_only_authorized_native_units | Error | hidden higher-rank native unit | only authorized vector enters result | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_queries_only_authorized_native_units` |
| V014 | falls_back_after_native_table_loss | Error | native table removed after ready | bounded NumPy neighbors from durable floats | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_falls_back_after_native_table_loss` |
| V015 | retirement_preserves_full_float_rows | Edge | active then retired generation | active drop rejected; retirement keeps durable bytes | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_retirement_preserves_full_float_rows` |
| V016 | rolls_back_native_preparation | Error | rebuild starts then transaction rolls back | previous native data and readiness survive | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_rolls_back_native_preparation` |
| V017 | refuses_untrusted_generation_identifiers | Error | invalid/bool/SQL-like generation IDs | rejected before constructing DDL | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_refuses_untrusted_generation_identifiers` |
| V018 | repairs_native_tables_without_inference | Edge | restored native table absent | worker restores native neighbors from floats | Integration | ✅ `integration/modules/search/test_vector_index.py::TestVectorIndex::test_repairs_native_tables_without_inference` |
| V019 | disables_sqlite_extension_loading_after_connect | Error | installed wheel loaded | SQL extension loading is then unauthorized | Integration | ✅ `integration/db/test_vector_extensions.py::TestVectorExtensions::test_disables_sqlite_extension_loading_after_connect` |
| V020 | disables_loading_after_failure | Error | wheel loader raises | loading gate closed; normal SQL usable | Integration | ✅ `integration/db/test_vector_extensions.py::TestVectorExtensions::test_disables_loading_after_failure` |
| V021 | disables_loading_after_async_connect | Edge | async SQLite pool opens connection | native functions available, loading disabled | Integration | ✅ `integration/db/test_vector_extensions.py::TestVectorExtensions::test_disables_loading_after_async_connect` |
| V022 | queries_authorized_native_vectors | Error | actual pgvector/HNSW with restricted SQL set | authorized full-float rescore; no schema drift | Integration | ✅ `integration/postgres/test_vector_index.py::TestPostgresVectorIndex::test_queries_authorized_native_vectors` |
| V023 | degrades_when_pg_extension_cannot_be_created | Error | PostgreSQL role lacks extension permission | NumPy fallback without breaking transaction | Integration | ✅ `integration/postgres/test_vector_index.py::TestPostgresVectorIndex::test_degrades_when_pg_extension_cannot_be_created` |
| V024 | restores_without_pgvector | Edge | native PostgreSQL snapshot copied with extension disabled | same portable neighbors without inference | Integration | ✅ `integration/postgres/test_vector_index.py::TestPostgresVectorIndex::test_restores_without_pgvector` |
| V025 | rolls_back_a_failed_transfer | Error | copy verification fails | destination schema/data rolled back | Integration | ✅ `integration/modules/administration/test_database_transfer.py::TestDatabaseTransfer::test_rolls_back_a_failed_transfer` |
| V026 | restores_native_floats_from_portable_backup | Happy | PostgreSQL backup then data loss | restore replaces data atomically and preserves vectors | Integration | ✅ `integration/modules/backups/backup/test_snapshot.py::TestPostgresSnapshot::test_restores_native_floats_from_portable_backup` |
| V027 | restores_searchable_documents_through_the_api | Happy | PostgreSQL HTTP backup then data loss | restored Document and search result through real HTTP API | E2E | ✅ `e2e/test_postgres_backup.py::TestPostgresBackup::test_restores_searchable_documents_through_the_api` |
| V028 | preserves_encoded_database_urls | Edge | encoded credentials and PostgreSQL options | Alembic receives exact URL | Unit | ✅ `unit/db/test_migrate.py::TestMigrationConfig::test_preserves_encoded_database_urls` |
| V029 | supports_search_modalities | Happy | text and point-cloud contract identities | valid immutable Space values | Core | ✅ `core/inference/test_embedding.py::TestEmbeddingSpace::test_supports_search_modalities` |

## Remote inference

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| R001 | embeds_ordered_text_batches | Happy | loopback endpoint returns vectors out of order | output matches each input index with native normalization | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_embeds_ordered_text_batches` |
| R002 | rejects_invalid_embedding_outputs | Error | missing/duplicate indexes, wrong dimension, nonfinite/zero vector | stable failure, no partial batch | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_rejects_invalid_embedding_outputs` |
| R003 | bounds_remote_response_bytes | Error | oversized or compressed response | rejected inside response budget | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_bounds_remote_response_bytes` |
| R004 | retries_bounded_rate_limits | Error | 429 then success | bounded retry and successful batch | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_retries_bounded_rate_limits` |
| R005 | refuses_redirected_embeddings | Error | endpoint redirects to another origin | no redirected request or credential forwarding | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_refuses_redirected_embeddings` |
| R006 | opens_a_failed_endpoint_circuit | Error | repeated retryable failures | subsequent call rejected without a socket request | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_opens_a_failed_endpoint_circuit` |
| R007 | cancels_remote_inference | Edge | operation cancelled before/during wait | bounded cancellation; no publication | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_cancels_remote_inference` |
| R008 | keeps_inference_credentials_encrypted | Error | endpoint saved with key and secret headers | raw DB lacks plaintext and read API redacts secrets | Integration | ✅ `integration/api/v1/test_inference.py::TestCreateEndpoint::test_keeps_inference_credentials_encrypted` |
| R009 | requires_admin_endpoint_configuration | Error | ordinary user submits endpoint | rejected before probe or mutation | Integration | ✅ `integration/api/v1/test_inference.py::TestCreateEndpoint::test_requires_admin_endpoint_configuration` |
| R010 | isolates_endpoint_configuration_versions | Edge | endpoint/model/credential version changes | new immutable provider identity; old Space retained | Integration | ✅ `integration/api/v1/test_inference.py::TestCreateEndpoint::test_isolates_endpoint_configuration_versions` |
| R011 | bounds_the_whole_operation | Error | stalled and trickling server | single deadline, one request | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_bounds_the_whole_operation` |
| R012 | keeps_inference_wire_data_out_of_debug_logs | Error | DEBUG logging with private text and response header | query/key/upstream header/URL absent | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_keeps_inference_wire_data_out_of_debug_logs` |
| R013 | does_not_retry_rejected_credentials | Error | 401 endpoint | one request and stable code | Contract | ✅ `contract/modules/inference/test_remote.py::TestRemoteEmbeddingProvider::test_does_not_retry_rejected_credentials` |
| R014 | redacts_invalid_configuration_input | Error | invalid secret header | 422 omits submitted credentials | Integration | ✅ `integration/api/v1/test_inference.py::TestCreateEndpoint::test_redacts_invalid_configuration_input` |
| R015 | omits_credentials_from_audit | Happy | saved endpoint | audit has only kind/host/model | Integration | ✅ `integration/api/v1/test_inference.py::TestCreateEndpoint::test_omits_credentials_from_audit` |
| R016 | defaults_to_independent_opt_ins | Happy | fresh settings | all AI uses and outbound images off | Integration | ✅ `integration/api/v1/test_inference.py::TestReadSettings::test_defaults_to_independent_opt_ins` |
| R017 | requires_a_capable_chat_endpoint | Error | generative opt-in without endpoint | rejected, settings remain off | Integration | ✅ `integration/api/v1/test_inference.py::TestUpdateSettings::test_requires_a_capable_chat_endpoint` |
| R018 | configures_a_probed_embedding_endpoint | Happy | admin HTTP setup plus real socket canary | stored capability and secret-free readback | E2E | ✅ `e2e/test_remote_inference.py::TestRemoteInferenceSetup::test_configures_a_probed_embedding_endpoint` |
| R019 | preserves_existing_settings_on_upgrade | Happy | existing library and config at W3 revision | content retained, new opt-ins absent | Integration | ✅ `integration/db/migrations/test_inference_endpoints_migration.py::TestInferenceEndpointsMigration::test_preserves_existing_settings_on_upgrade` |
| R020 | downgrades_without_losing_existing_settings | Edge | current schema | old settings survive downgrade | Integration | ✅ `integration/db/migrations/test_inference_endpoints_migration.py::TestInferenceEndpointsMigration::test_downgrades_without_losing_existing_settings` |
| C001 | returns_a_locally_validated_object | Happy | Ollama-schema/vLLM-tool/llama.cpp-JSON contract variants | typed result and honest guarantee | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_returns_a_locally_validated_object` |
| C002 | reuses_a_probed_dialect | Edge | previous structured unsupported responses | one subsequent completion request | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_reuses_a_probed_dialect` |
| C003 | repairs_json_once | Error | strict JSON output malformed once | validated repaired result | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_repairs_json_once` |
| C004 | rejects_a_failed_repair | Error | two invalid JSON outputs | stable error, bounded calls | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_rejects_a_failed_repair` |
| C005 | rejects_unsupported_fields_locally | Error | endpoint ignores supplied schema | no extra field accepted | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_rejects_unsupported_fields_locally` |
| C006 | never_changes_dialect_after_timeout | Error | ambiguous timeout | one dialect, one request | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_never_changes_dialect_after_timeout` |
| C007 | never_changes_dialect_after_server_failure | Error | 500 responses | bounded retry of original dialect | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_never_changes_dialect_after_server_failure` |
| C008 | rejects_external_schema_references_before_egress | Error | schema URL reference | rejected without HTTP | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_rejects_external_schema_references_before_egress` |
| C009 | probes_responses_without_assuming_availability | Edge | optional Responses API absent | falls back to chat-completions | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_probes_responses_without_assuming_availability` |
| C010 | uses_a_confirmed_responses_endpoint | Happy | Responses API responds to canary | validated schema result with store=false | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_uses_a_confirmed_responses_endpoint` |
| C011 | does_not_fall_back_after_a_responses_timeout | Error | ambiguous Responses timeout | no second paid dialect request | Contract | ✅ `contract/modules/inference/test_chat.py::TestRemoteChatProvider::test_does_not_fall_back_after_a_responses_timeout` |
| C012 | configures_chat_with_reported_json_guarantees | Happy | admin HTTP setup, JSON-only real fake | reduced guarantee persisted and independent switch | E2E | ✅ `e2e/test_remote_inference.py::TestRemoteInferenceSetup::test_configures_chat_with_reported_json_guarantees` |

## Durable generation lifecycle — planned

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| G001 | prepares_without_mutating_active | Happy | configured endpoint, old generation | immutable building proposal; old still serves | Integration | ❌ missing |
| G002 | fences_concurrent_proposals | Error | same modality/profile | at most one building | PostgreSQL | ❌ missing |
| G003 | backfills_current_passages | Happy | seeded four-type library | native vectors at current content hash | Integration | ❌ missing |
| G004 | rejects_late_publication | Error | content edit or cancellation during inference | no stale vector committed | Integration | ❌ missing |
| G005 | resumes_expired_leases | Edge | interrupted worker | committed work retained, expired unit reclaimed | Integration | ❌ missing |
| G006 | quarantines_poison_units | Error | repeat inference failure | bounded attempts; other units progress; verify refuses incomplete | Integration | ❌ missing |
| G007 | activates_verified_generation_atomically | Happy | ready proposal and correct version | one active, old retired, no serving gap | Integration | ❌ missing |
| G008 | preserves_active_when_verification_fails | Error | smoke failure or unreconciled edits | old active unchanged | Integration | ❌ missing |
| G009 | maintains_active_and_building_recipes | Edge | edits during rebuild | both serving/building hashes current | Integration | ❌ missing |
| G010 | drains_readers_before_pruning | Edge | query pinned during flip | old vectors retained until expiry and rollback retention | Integration | ❌ missing |
| G011 | rejects_capacity_overcommit | Error | old+new exceed storage budget | proposal rejected; old retained | Integration | ❌ missing |
| G012 | switches_index_without_reembedding | Happy | same Space, new backend/transform | durable floats reused, no embedding request | E2E | ❌ missing |
