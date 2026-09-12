"""Scale replicas remain ordinary searchable Models through a real refresh."""

from printstash_core.search.passages import SearchSubject, SubjectType
from sqlalchemy import func
from sqlmodel import select

from app.db.models import Model, PassageVector, SearchPassage
from app.db.models.search import (
    SearchLexicalPosting,
    SearchLexicalState,
    SearchLexicalTerm,
)
from app.modules.search import lexical_index
from app.modules.search.passages import sync_subject
from app.modules.search.retrieval import search
from tests.factories.search_scale import replicate_models


def test_replicas_survive_refresh_and_rebuild_with_consistent_statistics(
    db_session,
    make_model,
    make_user,
    make_embedding_space,
    make_index_generation,
    make_passage_vector,
):
    actor = make_user(superuser=True)
    generation = make_index_generation(make_embedding_space())
    seeds = [
        make_model("Boat", description="Calibration boat"),
        make_model("Bracket", description="Shelf support"),
    ]
    for model in seeds:
        sync_subject(db_session, SearchSubject(SubjectType.MODEL, model.id))
        passage = db_session.exec(
            select(SearchPassage).where(SearchPassage.subject_id == model.id)
        ).one()
        make_passage_vector(generation, passage=passage)
    result = replicate_models(db_session, seeds, generation, count=10)
    db_session.commit()
    replica_id = result["first_replica_id"]
    replica = db_session.get(Model, replica_id)
    assert replica.name == seeds[0].name
    assert replica.hash != seeds[0].hash
    passage = db_session.exec(
        select(SearchPassage).where(SearchPassage.subject_id == replica_id)
    ).one()
    vector = db_session.exec(
        select(PassageVector).where(PassageVector.passage_id == passage.id)
    ).one()
    before = (passage.content_hash, vector.id, vector.vector_blob)
    sync_subject(db_session, SearchSubject(SubjectType.MODEL, replica_id))
    db_session.commit()
    db_session.expire_all()
    vector = db_session.exec(
        select(PassageVector).where(PassageVector.passage_id == passage.id)
    ).one()
    assert (passage.content_hash, vector.id, vector.vector_blob) == before
    while lexical_index.rebuild_partition(db_session, limit=3):
        db_session.commit()
    db_session.commit()
    state = db_session.get(SearchLexicalState, 1)
    assert state.document_count == 10
    assert (
        state.total_length
        == db_session.exec(select(func.sum(SearchPassage.token_count))).one()
    )
    assert state.native_phase == "ready"
    assert dict(
        db_session.exec(
            select(SearchLexicalTerm.term, SearchLexicalTerm.document_frequency)
        ).all()
    ) == dict(
        db_session.exec(
            select(SearchLexicalPosting.term, func.count()).group_by(
                SearchLexicalPosting.term
            )
        ).all()
    )
    found = search(db_session, actor, "boat", mode="lexical")
    assert found.lexical_backend == "fts5"
    assert {row.subject_id for row in found.items} == {
        seeds[0].id,
        replica_id,
        replica_id + 2,
        replica_id + 4,
        replica_id + 6,
    }
