"""A real active generation supplies bounded semantic results with fresh authorization."""

from urllib.parse import parse_qs, urlsplit

import pytest
from printstash_core.search.passages import SubjectType
from sqlmodel import select

from app.core.errors import OperationError
from app.db.models import Document, PassageVector, SearchGenerationLease
from app.modules.inference.query import close_queries
from app.modules.search import configuration, generations
from app.modules.search.retrieval import search
from app.schemas.inference import SearchSettings
from app.schemas.search_generations import GenerationProposal


@pytest.fixture(autouse=True)
def projection():
    from app.db.projections import bind_content_projection
    from app.modules.search.projection import LibraryProjection

    previous = bind_content_projection(LibraryProjection())
    yield
    bind_content_projection(previous)


@pytest.fixture
def hybrid_library(
    db_session, generation_setup, healthy_embeddings, advance_generation, make_model
):
    close_queries()
    actor, endpoint = generation_setup
    model = make_model("Benchy boat")
    proposal = generations.prepare(
        db_session,
        actor,
        GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
    )
    advance_generation(proposal.id)
    document = db_session.exec(select(Document)).one()
    healthy_embeddings.requests.clear()
    yield actor, endpoint, proposal, document, model
    close_queries()


class TestSearch:
    def test_reauthorizes_cached_query_vectors(
        self, db_session, hybrid_library, healthy_embeddings
    ):
        actor, *_ = hybrid_library
        assert search(db_session, actor, "assembly instructions").items
        assert len(healthy_embeddings.requests) == 1
        actor.is_superuser = False
        db_session.add(actor)
        db_session.commit()

        result = search(db_session, actor, "assembly instructions")

        assert result.items == []
        assert len(healthy_embeddings.requests) == 1

    def test_expires_cursors_after_ranking_changes(self, db_session, hybrid_library):
        actor, *_ = hybrid_library
        first = search(db_session, actor, "assembly instructions", limit=1)
        assert first.next_cursor
        configuration.update(
            db_session, SearchSettings(enabled=True, semantic_weight=2)
        )
        db_session.commit()

        with pytest.raises(OperationError, match="search_cursor_invalid"):
            search(
                db_session,
                actor,
                "assembly instructions",
                cursor=first.next_cursor,
                limit=1,
            )

    def test_retries_admission_after_concurrent_cutover(
        self, db_session, hybrid_library, advance_generation
    ):
        from sqlalchemy import event

        from app.db.session import get_session_factory

        actor, endpoint, _, _, _ = hybrid_library
        replacement = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id,
                quantization="int8",
                index_backend="numpy",
                auto_activate=False,
            ),
        )
        advance_generation(replacement.id)
        activated = []

        def cutover(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ):
            if (
                not activated
                and "FROM index_generations JOIN embedding_spaces" in statement
                and "embedding_spaces.profile" in statement
            ):
                activated.append(True)
                with get_session_factory().scoped_session() as session:
                    generations.activate(
                        session, replacement.id, replacement.version_token
                    )

        engine = db_session.get_bind()
        event.listen(engine, "after_cursor_execute", cutover)
        try:
            result = search(db_session, actor, "assembly instructions")
        finally:
            event.remove(engine, "after_cursor_execute", cutover)

        assert activated == [True]
        assert result.generations == [replacement.id]
        assert len(result.items) == 2
        assert result.semantic_ready
        assert result.degraded == []

    def test_reports_bounded_candidate_coverage(
        self, db_session, hybrid_library, make_document, advance_indexing
    ):
        from app.db.projections import content_changed

        actor, *_ = hybrid_library
        documents = [make_document(f"Workshop note {number}") for number in range(101)]
        content_changed(db_session, "document", [document.id for document in documents])
        db_session.commit()
        advance_indexing(40)

        result = search(
            db_session,
            actor,
            "semantic-only-query",
            types=(SubjectType.DOCUMENT,),
            limit=100,
        )

        assert len(result.items) == 100
        assert result.truncated
        assert result.next_cursor is None

    def test_selects_the_declared_space_floor(self, db_session, hybrid_library):
        from app.modules.search import semantic

        actor, _, proposal, _, _ = hybrid_library
        configuration.update(
            db_session,
            SearchSettings(
                enabled=True,
                semantic_floor=-1,
                semantic_floors={proposal.config_hash: 0.9},
            ),
        )
        db_session.commit()

        assert (
            semantic.registry(db_session, configuration.settings(db_session))[0].floor
            == 0.9
        )

    def test_refuses_inference_without_visible_vectors(
        self, db_session, hybrid_library, healthy_embeddings, make_user
    ):
        reader = make_user()

        result = search(db_session, reader, "assembly instructions")

        assert result.items == []
        assert healthy_embeddings.requests == []
        assert result.outcome == "no_results"

    def test_expires_cursors_after_permission_changes(
        self, db_session, hybrid_library, healthy_embeddings
    ):
        actor, *_ = hybrid_library
        first = search(db_session, actor, "assembly instructions", limit=1)
        assert first.next_cursor
        actor.is_superuser = False
        db_session.add(actor)
        db_session.commit()
        healthy_embeddings.requests.clear()

        with pytest.raises(OperationError, match="search_cursor_invalid"):
            search(
                db_session,
                actor,
                "assembly instructions",
                cursor=first.next_cursor,
                limit=1,
            )

        assert healthy_embeddings.requests == []

    def test_returns_lexical_results_by_query_deadline(
        self, db_session, hybrid_library, healthy_embeddings
    ):
        from threading import Event
        from time import monotonic

        actor, _, _, _, model = hybrid_library
        configuration.update(
            db_session, SearchSettings(enabled=True, query_timeout_seconds=0.05)
        )
        db_session.commit()
        release = Event()
        healthy_embeddings.before_reply = lambda: release.wait(2)
        started = monotonic()
        try:
            result = search(db_session, actor, "Benchy")
            assert not release.is_set()
            assert monotonic() - started < 1
            assert [item.subject_id for item in result.items] == [model.id]
            assert result.degraded == ["search_semantic_unavailable"]
        finally:
            release.set()

    def test_preserves_an_inflight_generation(
        self, db_session, hybrid_library, healthy_embeddings, advance_generation
    ):
        actor, endpoint, first, _, _ = hybrid_library
        replacement = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id,
                quantization="int8",
                index_backend="numpy",
                auto_activate=False,
            ),
        )
        advance_generation(replacement.id)
        activation_errors = []

        def activate():
            assert len(db_session.exec(select(SearchGenerationLease)).all()) == 1
            try:
                generations.activate(
                    db_session, replacement.id, replacement.version_token
                )
            except Exception as exc:
                activation_errors.append(exc)
                raise

        healthy_embeddings.before_reply = activate
        result = search(db_session, actor, "assembly instructions")

        assert activation_errors == []
        assert len(result.items) == 2
        assert result.generations == [first.id]
        assert result.semantic_ready
        assert db_session.exec(select(SearchGenerationLease)).all() == []

    def test_excludes_trashed_subjects(self, db_session, hybrid_library):
        from app.modules.library.trash import soft_delete_model

        actor, _, _, document, model = hybrid_library
        soft_delete_model(db_session, model)

        result = search(db_session, actor, "assembly instructions")

        assert [(item.subject_type, item.subject_id) for item in result.items] == [
            (SubjectType.DOCUMENT, document.id)
        ]

    def test_retrieves_semantic_matches(
        self, db_session, hybrid_library, healthy_embeddings
    ):
        actor, _, proposal, document, model = hybrid_library

        result = search(db_session, actor, "instructions to assemble the part")

        assert {(item.subject_type, item.subject_id) for item in result.items} == {
            (SubjectType.DOCUMENT, document.id),
            (SubjectType.MODEL, model.id),
        }
        assert all(item.evidence[0].leg == "semantic_text" for item in result.items)
        assert result.semantic_ready
        assert result.generations == [proposal.id]
        assert result.outcome == "results"
        assert len(healthy_embeddings.requests) == 1

    def test_rejects_weak_dense_neighbors(
        self, db_session, hybrid_library, healthy_embeddings
    ):
        actor, *_ = hybrid_library
        healthy_embeddings.vector = [-1, 0, 0, 0]

        result = search(db_session, actor, "unrelated astronomy")

        assert result.items == []
        assert result.outcome == "no_strong_matches"
        assert result.semantic_ready

    @pytest.mark.parametrize(
        "options",
        [{"mode": "lexical"}, {"instant": True}, {"legs": ("lexical",)}],
        ids=["mode", "instant", "leg-selection"],
    )
    def test_disables_query_inference_for_lexical_mode(
        self, db_session, hybrid_library, healthy_embeddings, options
    ):
        actor, _, _, _, model = hybrid_library

        result = search(db_session, actor, "Benchy", **options)

        assert [item.subject_id for item in result.items] == [model.id]
        assert result.legs == ["lexical"]
        assert not result.semantic_ready
        assert healthy_embeddings.requests == []

    def test_filters_subject_types_before_ranking(self, db_session, hybrid_library):
        actor, _, _, document, _ = hybrid_library

        result = search(
            db_session, actor, "assembly instructions", types=(SubjectType.DOCUMENT,)
        )

        assert [(item.subject_type, item.subject_id) for item in result.items] == [
            (SubjectType.DOCUMENT, document.id)
        ]

    def test_rechecks_permissions_after_inference(
        self, db_session, hybrid_library, healthy_embeddings
    ):
        actor, *_ = hybrid_library

        def revoke():
            actor.is_superuser = False
            db_session.add(actor)
            db_session.commit()

        healthy_embeddings.before_reply = revoke
        result = search(db_session, actor, "assembly instructions")

        assert result.items == []
        assert db_session.exec(select(SearchGenerationLease)).all() == []

    def test_keeps_disabled_ai_lexical(
        self, db_session, hybrid_library, healthy_embeddings
    ):
        actor, _, _, _, model = hybrid_library
        configuration.update(db_session, SearchSettings(enabled=False))
        db_session.commit()

        result = search(db_session, actor, "Benchy")

        assert [item.subject_id for item in result.items] == [model.id]
        assert result.legs == ["lexical"]
        assert healthy_embeddings.requests == []

    def test_expires_cursors_after_generation_switch(
        self, db_session, hybrid_library, advance_generation
    ):
        actor, endpoint, _, _, _ = hybrid_library
        first = search(db_session, actor, "assembly instructions", limit=1)
        assert first.next_cursor
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, quantization="int8", index_backend="numpy"
            ),
        )
        advance_generation(proposal.id)

        with pytest.raises(OperationError, match="search_cursor_expired"):
            search(
                db_session,
                actor,
                "assembly instructions",
                limit=1,
                cursor=first.next_cursor,
            )

    def test_excludes_stale_vectors(self, db_session, hybrid_library):
        actor, *_ = hybrid_library
        for row in db_session.exec(select(PassageVector)).all():
            row.input_hash = "0" * 64
            db_session.add(row)
        db_session.commit()

        assert search(db_session, actor, "assembly instructions").items == []

    def test_degrades_after_active_vector_corruption(self, db_session, hybrid_library):
        actor, _, _, _, model = hybrid_library
        for row in db_session.exec(select(PassageVector)).all():
            row.vector_blob = b"bad"
            db_session.add(row)
        db_session.commit()

        result = search(db_session, actor, "Benchy")

        assert [item.subject_id for item in result.items] == [model.id]
        assert result.degraded == ["search_semantic_unavailable"]

    def test_encodes_collection_links(self, db_session, make_collection, make_user):
        from app.db.projections import content_changed

        actor = make_user(superuser=True)
        collection = make_collection("Bracket & assembly")
        content_changed(db_session, "collection", [collection.id])
        db_session.commit()

        result = search(db_session, actor, "Bracket")

        assert parse_qs(urlsplit(result.items[0].href).query)["c"] == [
            collection.path
        ]
