"""Durable indexing survives stale work, cancellation, poison inputs and restarts."""

from datetime import datetime, timedelta

from printstash_core.search.passages import SearchSubject, SubjectType
from sqlmodel import select

from app.core.time import utcnow
from app.db.models import (
    Document,
    IndexGeneration,
    PassageVector,
    SearchIndexFailure,
    SearchPassage,
)
from app.db.session import get_session_factory
from app.modules.search import generations, indexing
from app.modules.search.passages import sync_subject
from app.schemas.search_generations import GenerationProposal


class TestIndexProcessor:
    def test_indexes_content_added_during_backfill(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_indexing,
        advance_generation,
        make_document,
    ):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        advance_indexing(5)
        added = make_document("Later assembly note", body="Add two screws")

        advance_generation(proposal.id)

        assert set(db_session.exec(select(PassageVector.subject_id)).all()) == set(
            db_session.exec(select(Document.id)).all()
        )
        assert added.id in db_session.exec(select(PassageVector.subject_id)).all()

    def test_indexes_each_public_subject_type(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_generation,
        make_model,
        make_collection,
        make_multipart_model,
    ):
        actor, endpoint = generation_setup
        model = make_model("Assembly bracket")
        collection = make_collection("Assembly collection")
        multipart = make_multipart_model("Assembly kit")
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )

        advance_generation(proposal.id)

        assert set(
            db_session.exec(
                select(PassageVector.subject_type, PassageVector.subject_id)
            ).all()
        ) == {
            ("model", model.id),
            ("collection", collection.id),
            ("multipart_model", multipart.id),
            ("document", db_session.exec(select(Document.id)).one()),
        }

    def test_reports_provider_budget_truncation(
        self,
        db_session,
        generation_setup,
        make_inference_endpoint,
        healthy_embeddings,
        advance_generation,
    ):
        from app.modules.inference.endpoint import EndpointConfig

        actor, _ = generation_setup
        endpoint = make_inference_endpoint(
            config=EndpointConfig(
                base_url="http://inference.test/v1",
                model="test",
                max_input_characters=128,
            )
        )
        document = db_session.exec(select(Document)).one()
        document.body = "Detailed assembly instructions " * 30
        db_session.add(document)
        db_session.commit()
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id,
                index_backend="numpy",
                document_prefix="passage: ",
            ),
        )

        advance_generation(proposal.id)
        db_session.expire_all()

        assert db_session.exec(select(PassageVector.truncated)).all() == [True]
        assert db_session.get(IndexGeneration, proposal.id).truncated_count == 1
        assert (
            max(
                len(value)
                for request in healthy_embeddings.requests
                for value in request["input"]
            )
            == 128
        )
        assert (
            db_session.get(Document, document.id).body
            == "Detailed assembly instructions " * 30
        )

    def test_pauses_backfill_when_ai_is_disabled(
        self, db_session, generation_setup, healthy_embeddings
    ):
        from app.modules.search import configuration
        from app.schemas.inference import SearchSettings

        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        configuration.update(db_session, SearchSettings(enabled=False))

        worked = indexing.IndexProcessor(get_session_factory()).work_one()

        assert worked is False
        assert healthy_embeddings.requests == []
        assert db_session.get(IndexGeneration, proposal.id).state == "building"

    def test_keeps_active_ready_when_the_replacement_probe_fails(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_generation,
        advance_indexing,
    ):
        actor, endpoint = generation_setup
        first = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        advance_generation(first.id)
        second = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id,
                index_backend="numpy",
                query_prefix="Replacement query: ",
            ),
        )
        healthy_embeddings.poison = "Replacement query: "

        advance_indexing(32)
        db_session.expire_all()

        assert db_session.get(IndexGeneration, second.id).phase == "verify_failed"
        assert db_session.get(IndexGeneration, first.id).state == "active"

    def test_refreshes_both_generations_after_an_edit(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_generation,
        advance_indexing,
    ):
        actor, endpoint = generation_setup
        first = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        advance_generation(first.id)
        second = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id,
                index_backend="numpy",
                document_prefix="document: ",
                auto_activate=False,
            ),
        )
        advance_generation(second.id)
        document = db_session.exec(select(Document)).one()
        document.body = "Fit the replacement lid"
        db_session.add(document)
        sync_subject(db_session, SearchSubject(SubjectType.DOCUMENT, document.id))
        db_session.commit()
        healthy_embeddings.requests.clear()

        advance_indexing(30)
        db_session.expire_all()

        passage = db_session.exec(select(SearchPassage)).one()
        vectors = db_session.exec(
            select(PassageVector).order_by(PassageVector.generation_id)
        ).all()
        assert [(v.generation_id, v.input_hash) for v in vectors] == [
            (first.id, passage.content_hash),
            (second.id, passage.content_hash),
        ]
        inputs = [
            value
            for request in healthy_embeddings.requests
            for value in request["input"]
        ]
        assert passage.text in inputs
        assert "document: " + passage.text in inputs

    def test_retries_quarantined_inputs_after_manual_reset(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_indexing,
        advance_generation,
        make_search_index_failure,
    ):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        advance_indexing(4)
        generation = db_session.get(IndexGeneration, proposal.id)
        passage = db_session.exec(select(SearchPassage)).one()
        make_search_index_failure(generation, passage)
        advance_indexing(8)

        generations.retry_quarantine(db_session, proposal.id, proposal.version_token)
        advance_generation(proposal.id)

        assert db_session.exec(select(SearchIndexFailure)).all() == []
        assert (
            db_session.exec(select(PassageVector.input_hash)).one()
            == passage.content_hash
        )

    def test_backfills_current_passages(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
    ):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )

        advance_generation(proposal.id)
        db_session.expire_all()

        vector = db_session.exec(select(PassageVector)).one()
        passage = db_session.get(SearchPassage, vector.passage_id)
        assert (
            vector.subject_type,
            vector.subject_id,
            vector.input_hash,
            vector.native_dimension,
        ) == ("document", passage.subject_id, passage.content_hash, 4)
        assert db_session.get(IndexGeneration, proposal.id).verified_count == 1

    def test_rejects_source_edits_during_inference(
        self, db_session, generation_setup, healthy_embeddings, advance_indexing
    ):
        actor, endpoint = generation_setup
        generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        advance_indexing(4)

        def change_source():
            with get_session_factory().scoped_session() as session:
                document = session.exec(select(Document)).one()
                document.body = "A changed instruction"
                session.add(document)
                sync_subject(session, SearchSubject(SubjectType.DOCUMENT, document.id))
                session.commit()

        healthy_embeddings.before_reply = change_source

        indexing.IndexProcessor(get_session_factory()).work_one()
        db_session.expire_all()

        assert db_session.exec(select(PassageVector)).all() == []
        assert (
            db_session.exec(select(SearchPassage.text))
            .one()
            .endswith("A changed instruction")
        )

    def test_rejects_publication_after_cancellation(
        self, db_session, generation_setup, healthy_embeddings, advance_indexing
    ):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        advance_indexing(4)

        def cancel_work():
            with get_session_factory().scoped_session() as session:
                generations.cancel(session, proposal.id, proposal.version_token)

        healthy_embeddings.before_reply = cancel_work

        indexing.IndexProcessor(get_session_factory()).work_one()
        db_session.expire_all()

        assert db_session.exec(select(PassageVector)).all() == []
        assert db_session.get(IndexGeneration, proposal.id).state == "cancelled"

    def test_quarantines_poison_inputs_without_repeating_healthy_work(
        self,
        db_session,
        generation_setup,
        make_document,
        healthy_embeddings,
        advance_indexing,
    ):
        actor, endpoint = generation_setup
        make_document("Poison instruction", body="invalid provider input")
        healthy_embeddings.poison = "Poison instruction"
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        advance_indexing(5)
        failure = db_session.exec(select(SearchIndexFailure)).one()
        failure.retry_after = datetime(2000, 1, 1)
        db_session.add(failure)
        db_session.commit()
        advance_indexing(1)
        db_session.refresh(failure)
        failure.retry_after = datetime(2000, 1, 1)
        db_session.add(failure)
        db_session.commit()

        advance_indexing(8)
        db_session.expire_all()

        assert (
            db_session.get(SearchIndexFailure, failure.id).attempts,
            db_session.get(SearchIndexFailure, failure.id).state,
        ) == (3, "quarantined")
        assert db_session.exec(select(PassageVector.subject_type)).all() == ["document"]
        assert db_session.get(IndexGeneration, proposal.id).phase == "verify_failed"
        assert db_session.get(IndexGeneration, proposal.id).state == "building"

    def test_copies_same_space_vectors_without_inference(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
    ):
        actor, endpoint = generation_setup
        first = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        advance_generation(first.id)
        generations.activate(db_session, first.id, first.version_token)
        healthy_embeddings.requests.clear()
        second = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="auto", auto_activate=False
            ),
        )

        advance_generation(second.id)
        db_session.expire_all()

        assert healthy_embeddings.requests == []
        assert db_session.get(IndexGeneration, second.id).copied == 1
        assert len(db_session.exec(select(PassageVector)).all()) == 2

    def test_activates_automatically_after_verification(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
    ):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )

        advance_generation(proposal.id)
        db_session.expire_all()

        assert db_session.get(IndexGeneration, proposal.id).state == "active"


class TestClaim:
    def test_reclaims_an_expired_worker_lease(self, db_session, generation_setup):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        first = indexing.claim(db_session)
        row = db_session.get(IndexGeneration, proposal.id)
        row.lease_expires_at = utcnow() - timedelta(seconds=1)
        db_session.add(row)
        db_session.commit()

        second = indexing.claim(db_session)

        assert second[0] == first[0] == proposal.id
        assert second[1] != first[1]

    def test_preserves_a_live_worker_lease(self, db_session, generation_setup):
        actor, endpoint = generation_setup
        generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        first = indexing.claim(db_session)

        second = indexing.claim(db_session)

        assert first is not None
        assert second is None
