"""Capability and backlog reporting obey the same subject visibility as search."""

from printstash_core.search.passages import SearchSubject, SubjectType

from app.db.models import IndexGeneration
from app.modules.search import generations
from app.modules.search.passages import sync_subject
from app.schemas.search_generations import GenerationProposal


class TestStatus:
    def test_reports_only_usable_active_capabilities(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
    ):
        from app.modules.search.status import read

        actor, endpoint = generation_setup
        generation = generations.prepare(
            db_session, actor, GenerationProposal(endpoint_id=endpoint.id)
        )
        assert read(db_session, actor).semantic_ready is False
        advance_generation(generation.id)
        result = read(db_session, actor)
        assert result.semantic_ready is True
        assert result.remote_hosts == ["inference.test"]
        assert result.backlog is False

    def test_hides_backlog_for_inaccessible_subjects(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_generation,
        make_user,
        make_collection,
        make_model,
    ):
        from app.modules.search.status import read

        actor, endpoint = generation_setup
        generation = generations.prepare(
            db_session, actor, GenerationProposal(endpoint_id=endpoint.id)
        )
        advance_generation(generation.id)
        viewer = make_user()
        model = make_model("Confidential", collection=make_collection("Private"))
        sync_subject(db_session, SearchSubject(SubjectType.MODEL, model.id))
        assert read(db_session, viewer).backlog is False

    def test_reports_authorized_backlog(
        self,
        db_session,
        generation_setup,
        healthy_embeddings,
        advance_generation,
        make_document,
    ):
        from app.modules.search.status import read

        actor, endpoint = generation_setup
        generation = generations.prepare(
            db_session, actor, GenerationProposal(endpoint_id=endpoint.id)
        )
        advance_generation(generation.id)
        document = make_document("New guide")
        sync_subject(db_session, SearchSubject(SubjectType.DOCUMENT, document.id))
        assert read(db_session, actor).backlog is True

    def test_reports_a_missing_active_endpoint(
        self, db_session, generation_setup, healthy_embeddings, advance_generation
    ):
        from app.modules.search.status import read

        actor, endpoint = generation_setup
        generation = generations.prepare(
            db_session, actor, GenerationProposal(endpoint_id=endpoint.id)
        )
        advance_generation(generation.id)
        db_session.delete(endpoint)
        db_session.flush()
        result = read(db_session, actor)
        assert result.semantic_ready is False
        assert result.degraded == ["search_semantic_unavailable"]
        assert db_session.get(IndexGeneration, generation.id).state == "active"
