# AI Search implementation coverage

Work in progress for #166, based on the [owner’s independent plan](https://gist.github.com/xiao-villamor/e4daf5562e6a0819c4b7ce3a915bc19c) and [jorgehermo9’s attachment](https://gist.github.com/jorgehermo9/0b348e4411c0b455be7964a1de5f588c). One branch and one eventual PR. No AI Search availability claim yet.

The first increment implements the W1 passage recipe, source extraction and transactional persistence. Mutation-port wiring, dependency reconciliation and every later stage remain unfinished. Existing Similar Models inference will be adopted at W3/W12 rather than duplicated.

| # | Behaviour (test name) | Category | Precondition / input | Observable outcome asserted | Tier | Status |
|---|---|---|---|---|---|---|
| A001 | renders a passage with every configured field in template order | Happy | model with name, description, tags, collection | returned text matches the golden template | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_renders_every_recipe_field_in_stable_order` |
| A002 | chunks a document body at the token cap with overlap | Edge | body above the cap | N passages, contiguous, overlap preserved | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_chunks_a_document_body_at_the_token_cap_with_overlap` |
| A003 | caps the number of chunks for an oversized document | Edge | body far above the cap | chunk count == cap; no error | Unit | ✅ `core/search/test_passages.py::TestRenderPassages::test_caps_the_number_of_chunks_for_an_oversized_document` |
| A004 | changes the content hash when an indexed field changes | Happy | model description edited | `content_hash` differs; stale vectors deleted | Integration | ❌ missing |
| A005 | leaves the content hash untouched for a non-indexed edit | Edge | `updated_at` bumped, fields equal | hash unchanged; no re-embed enqueued | Integration | ❌ missing |
| A006 | removes passages when a subject is trashed | Edge | model trashed | no passages; no vectors; not returned by search | Integration | ❌ missing |
| A007 | restores passages when a subject is restored | Edge | trashed model restored | passages exist again; searchable | Integration | ❌ missing |
| A008 | re-derives a passage the mutation seam missed | Error | row updated bypassing the seam | watermark sweep repairs it | Integration | ❌ missing |
| A009 | ranks an exact title match above a body mention | Happy | two models, FTS5 | ordering asserted | Integration | ❌ missing |
| A010 | ranks the controlled BM25 fixture consistently on PostgreSQL | Happy | Mismo tokenizer, corpus y pesos; postgres marker | Orden de referencia BM25, no ts_rank etiquetado como BM25 | Integration | ❌ missing |
| A011 | falls back to ranked LIKE when FTS is unavailable | Error | probe forced to fail | results still returned; capability reports the fallback | Integration | ❌ missing |
| A012 | prepares a generation at its index dimension | Happy | Space nativa 1024; MRL index 128 | Tabla derivada de 128; floats durables de 1024 | Integration | ❌ missing |
| A013 | drops the typed table when a generation is retired | Happy | retired generation | table gone; durable vectors deleted in batches | Integration | ❌ missing |
| A014 | keeps autogenerate empty while a generation is live | Edge | live generation, `alembic revision --autogenerate` | empty diff | Integration | ❌ missing |
| A015 | preserves vectors across SQLite→PostgreSQL migration | Happy | seeded generation | same vectors, index rebuilt, no re-embed | Integration | ❌ missing |
| A016 | serves search after a backup restore without a reindex | Happy | backup, wipe, restore | identical results | E2E | ❌ missing |
| A017 | returns brute-force results when the vector extension is missing | Error | extension probe fails | same top-k as the native path | Integration | ❌ missing |
| A018 | embeds a batch through the remote provider | Happy | contract-enforcing fake endpoint over loopback | returned vectors match inputs and declared dimension; persistence covered separately | Contract | ❌ missing |
| A019 | refuses a remote dimension mismatch | Error | endpoint returns 512 for a 384 space | generation fails with a stable code; active untouched | Contract | ❌ missing |
| A020 | degrades to lexical when the endpoint times out | Error | endpoint hangs | 200 with `legs: ["lexical"]`; no 5xx | Integration | ❌ missing |
| A021 | retries a 429 with backoff | Error | endpoint returns 429 then 200 | batch completes; attempt count recorded | Contract | ❌ missing |
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
| A035 | rejects search from a share-link context | Error | share token | 403; no retrieval performed | Integration | ❌ missing |
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
| A058 | returns schema-valid output from a json_schema endpoint | Happy | fake chat endpoint, schema dialect | parsed object matches the schema | Contract | ❌ missing |
| A059 | falls back to parse-and-repair without schema support | Error | probe reports no schema, no tools | usable result; reduced guarantee reported | Contract | ❌ missing |
| A060 | probes the Responses API dialect without assuming it | Edge | endpoint lacking it | detected absent; chat-completions used | Contract | ❌ missing |
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
| A095 | disables_sqlite_extension_loading_after_connect | Edge | Conexiones sync/async; carga falla | Load_extension deshabilitado al terminar hook | Integration | ❌ missing |
| A096 | degrades_when_pg_extension_cannot_be_created | Error | Disponible pero usuario sin permiso | NumPy fallback; startup no falla | Integration | ❌ missing |
| A097 | restores_without_vector_extension | Edge | Backup nativo restaurado sin extensión | Datos/vector durables consultables; rebuild background | E2E | ❌ missing |
| A098 | probes_chat_tool_calling_fallback | Happy | Endpoint tools sin json_schema | Objeto validado con guarantee reportada | Contract | ❌ missing |
| A099 | rejects_invalid_chat_schema_output | Error | Endpoint devuelve key extra/type erróneo | Nada ejecutado como filtro; fallback limpio | Contract | ❌ missing |
| A100 | bounds_chat_parse_repair | Error | JSON inválido repetido | Se detiene en límite; no loop de llamadas | Contract | ❌ missing |
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
| P051 | materializes a document created through the api | Happy | Document created through real HTTP API; explicit projection operation | Text readable from a new database session | E2E | ✅ `e2e/test_search_passages.py::TestSearchPassageLifecycle::test_materializes_a_document_created_through_the_api` |
| P052 | search passage builder preserves subject identity | Happy | Factory receives a real Model Subject | Persisted owner, access requirements and default text match | Integration | ✅ `repo/test_factories.py::TestGeneratedIdentities::test_search_passage_builder_preserves_subject_identity` |
