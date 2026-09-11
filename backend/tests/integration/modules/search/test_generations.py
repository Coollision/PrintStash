"""Building, verification and cutover preserve the current serving generation."""

from datetime import timedelta

import pytest
from printstash_core.search.passages import SearchSubject, SubjectType
from sqlmodel import select

from app.core.errors import OperationError
from app.core.time import ensure_utc, utcnow
from app.db.models import (
    IndexGeneration,
    PassageVector,
    SearchReconciliationState,
)
from app.modules.search import configuration, generations
from app.modules.search.passages import sync_subject
from app.schemas.inference import SearchSettings
from app.schemas.search_generations import GenerationProposal


@pytest.fixture
def retired_vector_batch(
    db_session,
    make_embedding_space,
    make_index_generation,
    make_passage_vector,
    make_document,
    make_search_passage,
):
    generation = make_index_generation(
        make_embedding_space(),
        active=False,
        version_token="e" * 32,
        retain_until=utcnow() - timedelta(seconds=1),
    )
    for number in range(130):
        document = make_document(f"Retired assembly guide {number}")
        passage = make_search_passage(SearchSubject(SubjectType.DOCUMENT, document.id))
        make_passage_vector(generation, passage=passage)
    return generation


class TestPrepare:
    def test_rejects_capacity_overcommit(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
    ):
        actor, endpoint = generation_setup
        first = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        advance_generation(first.id)
        configuration.update(
            db_session, SearchSettings(enabled=True, max_index_bytes=1024**2)
        )

        with pytest.raises(OperationError) as caught:
            generations.prepare(
                db_session,
                actor,
                GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
            )

        assert caught.value.kind.value == "capacity"
        assert db_session.exec(
            select(IndexGeneration.id).where(IndexGeneration.state == "active")
        ).all() == [first.id]
        assert (
            db_session.exec(
                select(IndexGeneration.id).where(IndexGeneration.state == "building")
            ).all()
            == []
        )

    def test_prepares_a_building_generation(self, db_session, generation_setup):
        actor, endpoint = generation_setup

        result = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )

        assert (
            result.state,
            result.phase,
            result.profile,
            result.native_dimension,
        ) == ("building", "reconcile", "semantic_text", 4)
        assert result.job_id
        assert (
            db_session.exec(
                select(IndexGeneration).where(IndexGeneration.state == "active")
            ).all()
            == []
        )

    def test_refuses_another_build_for_the_profile(self, db_session, generation_setup):
        actor, endpoint = generation_setup
        generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )

        with pytest.raises(OperationError, match="search_generation_building"):
            generations.prepare(
                db_session,
                actor,
                GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
            )

        assert len(db_session.exec(select(IndexGeneration)).all()) == 1

    def test_requires_ai_opt_in(self, db_session, generation_setup):
        actor, endpoint = generation_setup
        configuration.update(db_session, SearchSettings())

        with pytest.raises(OperationError, match="search_ai_disabled"):
            generations.prepare(
                db_session, actor, GenerationProposal(endpoint_id=endpoint.id)
            )


class TestActivate:
    def test_refuses_content_added_after_verification(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_generation,
        make_document,
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
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        advance_generation(second.id)
        added = make_document("New instruction")
        sync_subject(db_session, SearchSubject(SubjectType.DOCUMENT, added.id))
        db_session.commit()

        with pytest.raises(OperationError, match="search_generation_incomplete"):
            generations.activate(db_session, second.id, second.version_token)

        assert db_session.exec(
            select(IndexGeneration.id).where(IndexGeneration.state == "active")
        ).all() == [first.id]

    def test_activates_a_verified_generation(
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

        result = generations.activate(db_session, proposal.id, proposal.version_token)

        assert result.state == "active"
        assert result.indexed == result.eligible == 1
        assert db_session.exec(select(PassageVector.input_hash)).one()

    def test_replaces_the_old_active_atomically(
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
        second = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id,
                index_backend="numpy",
                document_prefix="passage: ",
                auto_activate=False,
            ),
        )
        advance_generation(second.id)

        generations.activate(db_session, second.id, second.version_token)
        db_session.expire_all()

        assert db_session.exec(
            select(IndexGeneration.id).where(IndexGeneration.state == "active")
        ).all() == [second.id]
        assert db_session.get(IndexGeneration, first.id).state == "retired"
        assert (
            ensure_utc(db_session.get(IndexGeneration, first.id).retain_until)
            > utcnow()
        )

    def test_refuses_unverified_generations(self, db_session, generation_setup):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, auto_activate=False),
        )

        with pytest.raises(OperationError, match="search_generation_not_ready"):
            generations.activate(db_session, proposal.id, proposal.version_token)

    def test_rejects_stale_proposal_versions(self, db_session, generation_setup):
        actor, endpoint = generation_setup
        proposal = generations.prepare(
            db_session, actor, GenerationProposal(endpoint_id=endpoint.id)
        )

        with pytest.raises(OperationError, match="search_proposal_changed"):
            generations.activate(db_session, proposal.id, "f" * 32)


class TestCancel:
    def test_cancels_durable_work(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
    ):
        actor, endpoint = generation_setup
        old = generations.prepare(
            db_session,
            actor,
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        advance_generation(old.id)
        proposal = generations.prepare(
            db_session, actor, GenerationProposal(endpoint_id=endpoint.id)
        )

        result = generations.cancel(db_session, proposal.id, proposal.version_token)

        assert (result.state, result.phase) == ("cancelled", "cancelled")
        assert db_session.get(IndexGeneration, old.id).state == "active"
        assert db_session.get(IndexGeneration, proposal.id).building_profile_key is None


class TestPruneOne:
    def test_prunes_vectors_in_bounded_batches(self, db_session, retired_vector_batch):
        generation = retired_vector_batch

        pruned = generations.prune_one(db_session)

        assert pruned is True
        assert (
            len(
                db_session.exec(
                    select(PassageVector.id).where(
                        PassageVector.generation_id == generation.id
                    )
                ).all()
            )
            == 2
        )
        assert db_session.get(IndexGeneration, generation.id).phase == "pruning"

    def test_preserves_rollback_retention_after_readers_finish(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
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
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        advance_generation(second.id)

        assert generations.prune_one(db_session) is False
        assert db_session.exec(select(PassageVector.generation_id)).all() == [
            first.id,
            second.id,
        ]

    def test_prunes_expired_generations_with_their_checkpoints(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
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
            GenerationProposal(endpoint_id=endpoint.id, index_backend="numpy"),
        )
        advance_generation(second.id)
        old = db_session.get(IndexGeneration, first.id)
        old.retain_until = utcnow() - timedelta(seconds=1)
        db_session.add(old)
        db_session.commit()

        assert generations.prune_one(db_session) is True
        assert generations.prune_one(db_session) is True

        assert db_session.exec(select(PassageVector.generation_id)).all() == [second.id]
        assert db_session.get(IndexGeneration, first.id).phase == "pruned"
        assert (
            db_session.exec(
                select(SearchReconciliationState.subject_type).where(
                    SearchReconciliationState.subject_type.like(f"g{first.id}:%")
                )
            ).all()
            == []
        )

    def test_retains_old_vectors_while_a_reader_is_pinned(
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
        pin = generations.pin(db_session, first.id)
        second = generations.prepare(
            db_session,
            actor,
            GenerationProposal(
                endpoint_id=endpoint.id, index_backend="numpy", auto_activate=False
            ),
        )
        advance_generation(second.id)
        generations.activate(db_session, second.id, second.version_token)
        old = db_session.get(IndexGeneration, first.id)
        old.retain_until = utcnow() - timedelta(seconds=1)
        db_session.add(old)
        db_session.commit()

        pruned = generations.prune_one(db_session)

        assert pruned is False
        assert db_session.exec(
            select(PassageVector.id).where(PassageVector.generation_id == first.id)
        ).all()
        generations.unpin(db_session, pin)
