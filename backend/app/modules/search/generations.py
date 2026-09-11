"""Durable proposals, verification and atomic replacement of serving generations."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from pathlib import Path

from printstash_core.inference import EmbeddingError
from printstash_core.inference import EmbeddingSpace as Space
from sqlalchemy import delete, func, text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.errors import ErrorKind, OperationError
from app.core.time import ensure_utc, utcnow
from app.db.models import (
    EmbeddingSpace,
    IndexGeneration,
    InferenceEndpoint,
    PassageVector,
    SearchGenerationLease,
    SearchIndexFailure,
    SearchPassage,
    SearchReconciliationState,
    User,
)
from app.db.session import get_session_factory
from app.db.transactions import begin_write
from app.modules.administration import audit
from app.modules.inference.configuration import load as load_endpoint
from app.modules.search import configuration, vector_index, vector_store
from app.modules.search.access import indexable_passage_ids
from app.modules.search.text_inputs import TextRecipe
from app.modules.storage.capacity import CapacityManager, CapacityResource
from app.runtime.jobs import registry
from app.schemas.search_generations import GenerationProposal, GenerationRead

LEASE_SECONDS = 180
READER_SECONDS = 180  # Greater than the hard 120-second inference deadline.


def contract(session: Session, generation: IndexGeneration) -> Space:
    row = session.get(EmbeddingSpace, generation.space_id)
    if row is None:
        raise EmbeddingError("embedding_space_unavailable")
    return Space(**json.loads(row.config_json))


def eligible(session: Session, space: Space):
    recipe = TextRecipe.for_space(space)
    return select(SearchPassage.id).where(
        SearchPassage.recipe_version == recipe.passage_version,
        SearchPassage.id.in_(indexable_passage_ids(session)),
    )


def current_vectors(session: Session, generation_id: int, space: Space):
    return (
        select(PassageVector.id)
        .join(SearchPassage, SearchPassage.id == PassageVector.passage_id)
        .where(
            PassageVector.generation_id == generation_id,
            PassageVector.unit_kind == "passage",
            PassageVector.input_hash == SearchPassage.content_hash,
            SearchPassage.id.in_(eligible(session, space)),
            PassageVector.native_dimension == space.dimension,
        )
    )


def missing(session: Session, generation_id: int, space: Space):
    present = (
        select(PassageVector.id)
        .where(
            PassageVector.generation_id == generation_id,
            PassageVector.passage_id == SearchPassage.id,
            PassageVector.unit_kind == "passage",
            PassageVector.input_hash == SearchPassage.content_hash,
            PassageVector.native_dimension == space.dimension,
        )
        .exists()
    )
    return eligible(session, space).where(~present)


def counts(session: Session, generation: IndexGeneration) -> tuple[int, int, int]:
    space = contract(session, generation)
    total = session.exec(
        select(func.count()).select_from(eligible(session, space).subquery())
    ).one()
    indexed = session.exec(
        select(func.count()).select_from(
            current_vectors(session, generation.id, space).subquery()
        )
    ).one()
    quarantine = session.exec(
        select(func.count())
        .select_from(SearchIndexFailure)
        .join(SearchPassage, SearchPassage.id == SearchIndexFailure.passage_id)
        .where(
            SearchIndexFailure.generation_id == generation.id,
            SearchIndexFailure.state == "quarantined",
            SearchIndexFailure.input_hash == SearchPassage.content_hash,
        )
    ).one()
    return total, indexed, quarantine


def read(session: Session, generation: IndexGeneration) -> GenerationRead:
    space = contract(session, generation)
    total, indexed, quarantined = counts(session, generation)
    return GenerationRead(
        id=generation.id,
        state=generation.state,
        phase=generation.phase,
        version_token=generation.version_token,
        modality=space.modality,
        profile=space.profile,
        model=space.model_key,
        config_hash=space.config_hash,
        native_dimension=space.dimension,
        index_dimension=generation.index_dimension,
        quantization=generation.quantization,
        index_backend=generation.index_backend,
        index_state=generation.index_state,
        index_error=generation.index_error,
        error_code=generation.error_code,
        processed=generation.processed,
        copied=generation.copied,
        truncated_count=generation.truncated_count,
        eligible=total,
        indexed=indexed,
        quarantined=quarantined,
        estimated_bytes=generation.estimated_bytes,
        job_id=generation.job_id,
        verified_at=ensure_utc(generation.verified_at)
        if generation.verified_at
        else None,
        retain_until=ensure_utc(generation.retain_until)
        if generation.retain_until
        else None,
    )


def list_generations(session: Session) -> list[GenerationRead]:
    rows = session.exec(
        select(IndexGeneration)
        .where(IndexGeneration.version_token.is_not(None))
        .order_by(IndexGeneration.id.desc())
        .limit(100)
    ).all()
    return [read(session, row) for row in rows]


def require(
    session: Session, generation_id: int, version_token: str
) -> IndexGeneration:
    row = session.get(IndexGeneration, generation_id, populate_existing=True)
    if row is None or row.version_token is None:
        raise OperationError("search_generation_not_found", kind=ErrorKind.NOT_FOUND)
    if not secrets.compare_digest(row.version_token, version_token):
        raise OperationError("search_proposal_changed", kind=ErrorKind.CONFLICT)
    return row


def _locked_require(
    session: Session, generation_id: int, version_token: str
) -> IndexGeneration:
    # Acquire a write lock on both supported databases before reading state.
    # A concurrent activation must finish before cancellation/retry is admitted.
    session.exec(
        update(IndexGeneration)
        .where(IndexGeneration.id == generation_id)
        .values(last_activity_at=IndexGeneration.last_activity_at)
    )
    return require(session, generation_id, version_token)


def resources(
    session: Session, space: Space, estimated_bytes: int
) -> list[CapacityResource]:
    # Include existing native floats, row overhead and derived-index allowance.
    occupied = session.exec(
        select(
            func.coalesce(
                func.sum(func.length(PassageVector.vector_blob) * 3 + 1024), 0
            )
        )
    ).one()
    available = max(0, configuration.settings(session).max_index_bytes - occupied)
    result = [
        CapacityResource.for_quota(
            "search-index", estimated_bytes, available, role="search index generations"
        )
    ]
    url = session.get_bind().url
    if url.get_backend_name() == "sqlite" and url.database not in {
        None,
        "",
        ":memory:",
    }:
        result.append(
            CapacityResource.for_path(
                Path(url.database), estimated_bytes, role="search index generations"
            )
        )
    return result


def prepare(
    session: Session, actor: User, proposal: GenerationProposal
) -> GenerationRead:
    actor = session.get(User, actor.id, populate_existing=True)
    if actor is None or not actor.is_active or not actor.is_superuser:
        raise OperationError("admin_required", kind=ErrorKind.FORBIDDEN)
    if not configuration.settings(session).enabled:
        raise OperationError("search_ai_disabled", kind=ErrorKind.CONFLICT)
    endpoint_row = session.get(InferenceEndpoint, proposal.endpoint_id)
    if endpoint_row is None or endpoint_row.kind != "embedding":
        raise OperationError("inference_endpoint_unavailable", kind=ErrorKind.INVALID)
    endpoint = load_endpoint(endpoint_row)
    recipe = TextRecipe(proposal.passage_recipe_version, endpoint.max_input_characters)
    space = Space(
        model_key=endpoint.model,
        model_revision=endpoint.revision,
        dimension=endpoint_row.native_dimension,
        modality="text",
        render_recipe=recipe.encode(),
        provider="openai_compatible",
        profile=proposal.profile,
        query_prefix=proposal.query_prefix,
        document_prefix=proposal.document_prefix,
        provider_config_hash=endpoint.identity,
    )
    if len(space.document_prefix) >= recipe.max_input_characters:
        raise OperationError("search_prefix_exceeds_budget", kind=ErrorKind.INVALID)
    dimension = proposal.index_dimension or space.dimension
    if dimension != space.dimension or proposal.quantization != "float32":
        raise OperationError("search_transform_unavailable", kind=ErrorKind.INVALID)
    backend = proposal.index_backend
    dialect = session.get_bind().dialect.name
    if backend == "auto":
        backend = "sqlite_vec" if dialect == "sqlite" else "pgvector"
    if (backend == "sqlite_vec" and dialect != "sqlite") or (
        backend == "pgvector" and dialect != "postgresql"
    ):
        raise OperationError("search_backend_incompatible", kind=ErrorKind.INVALID)
    key = f"{space.modality}/{space.profile}"
    active = session.exec(
        select(IndexGeneration).where(IndexGeneration.active_profile_key == key)
    ).first()
    total = session.exec(
        select(func.count()).select_from(eligible(session, space).subquery())
    ).one()
    estimate = (total + 128) * (space.dimension * 4 * 3 + 1024) + 1024**2
    version = secrets.token_hex(16)
    reservation_id = "search-generation:" + version
    manager = CapacityManager(get_session_factory())
    reservation = manager.reserve(
        reservation_id, resources(session, space, estimate), durable=True
    )
    try:
        stored_space = vector_store.register_space(session, space)
        generation = IndexGeneration(
            space_id=stored_space.id,
            state="building",
            phase="reconcile",
            building_profile_key=key,
            version_token=version,
            actor_id=actor.id,
            replaces_generation_id=active.id if active else None,
            index_dimension=dimension,
            quantization=proposal.quantization,
            index_backend=backend,
            reservation_id=reservation_id,
            estimated_bytes=estimate,
            last_activity_at=utcnow(),
            auto_activate=proposal.auto_activate,
        )
        session.add(generation)
        session.flush()  # Unique building/profile rejects a competing proposal here.
        generation.job_id = registry.create(actor.id, kind="ai_search", session=session)
        vector_index.prepare(session, generation)
        session.add(generation)
        audit.record(
            session,
            action="search_generation_proposed",
            resource_type="search_generation",
            resource_id=generation.id,
            diff={
                "space": space.config_hash,
                "profile": space.profile,
                "backend": backend,
            },
        )
    except Exception as exc:
        session.rollback()
        reservation.release()
        if isinstance(exc, IntegrityError):
            raise OperationError(
                "search_generation_building", kind=ErrorKind.CONFLICT
            ) from None
        raise
    return read(session, generation)


def _lock_cutover(session: Session) -> None:
    # PostgreSQL table SHARE locks drain in-flight passage/vector writes and
    # prevent new ones until the flip commits. Readers remain unblocked. SQLite
    # takes its ordinary write transaction. No inference happens under this lock.
    begin_write(session)
    if session.get_bind().dialect.name == "postgresql":
        session.exec(text("LOCK TABLE search_passages, passage_vectors IN SHARE MODE"))


def verify_counts(session: Session, generation: IndexGeneration) -> tuple[int, int]:
    total, indexed, quarantined = counts(session, generation)
    if total != indexed or quarantined:
        raise OperationError("search_generation_incomplete", kind=ErrorKind.CONFLICT)
    return total, indexed


def activate(
    session: Session, generation_id: int, version_token: str
) -> GenerationRead:
    candidate = require(session, generation_id, version_token)
    locked_ids = [candidate.id] + (
        [candidate.replaces_generation_id] if candidate.replaces_generation_id else []
    )
    session.exec(
        select(IndexGeneration)
        .where(col(IndexGeneration.id).in_(locked_ids))
        .order_by(IndexGeneration.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    _lock_cutover(session)
    generation = require(session, generation_id, version_token)
    if not configuration.settings(session).enabled:
        raise OperationError("search_ai_disabled", kind=ErrorKind.CONFLICT)
    if (
        generation.state != "building"
        or generation.phase != "ready"
        or generation.verified_at is None
        or generation.cancel_requested
    ):
        raise OperationError("search_generation_not_ready", kind=ErrorKind.CONFLICT)
    if (
        generation.lease_token
        and generation.lease_expires_at
        and ensure_utc(generation.lease_expires_at) > utcnow()
    ):
        raise OperationError("search_generation_busy", kind=ErrorKind.CONFLICT)
    verify_counts(session, generation)
    key = generation.building_profile_key
    active = session.exec(
        select(IndexGeneration).where(IndexGeneration.active_profile_key == key)
    ).first()
    if (active.id if active else None) != generation.replaces_generation_id:
        raise OperationError("search_active_changed", kind=ErrorKind.CONFLICT)
    now = utcnow()
    if active:
        active.state = "retired"
        active.phase = "draining"
        active.active_profile_key = None
        active.retired_at = now
        active.retain_until = now + timedelta(
            hours=configuration.settings(session).rollback_retention_hours
        )
        session.add(active)
        session.flush()
    generation.state = "active"
    generation.phase = "ready"
    generation.building_profile_key = None
    generation.active_profile_key = key
    generation.activated_at = now
    session.add(generation)
    audit.record(
        session,
        action="search_generation_activated",
        resource_type="search_generation",
        resource_id=generation.id,
        diff={"replaced": active.id if active else None},
    )
    if generation.reservation_id:
        CapacityManager(get_session_factory()).release(generation.reservation_id)
    if generation.job_id:
        registry.update(
            generation.job_id,
            state="completed",
            processed=generation.processed,
            progress=100,
            result={"generation_id": generation.id},
        )
    return read(session, generation)


def cancel(session: Session, generation_id: int, version_token: str) -> GenerationRead:
    row = _locked_require(session, generation_id, version_token)
    if row.state != "building":
        raise OperationError("search_generation_not_building", kind=ErrorKind.CONFLICT)
    row.cancel_requested = True
    row.state = "cancelled"
    row.phase = "cancelled"
    row.building_profile_key = None
    row.lease_token = None
    row.lease_expires_at = None
    row.retired_at = utcnow()
    row.retain_until = utcnow() + timedelta(seconds=READER_SECONDS)
    session.add(row)
    audit.record(
        session,
        action="search_generation_cancelled",
        resource_type="search_generation",
        resource_id=row.id,
    )
    if row.job_id:
        registry.update(
            row.job_id,
            state="failed",
            error="search_generation_cancelled",
            retryable=False,
            result={"state": "cancelled", "generation_id": row.id},
        )
    return read(session, row)


def retry_quarantine(
    session: Session, generation_id: int, version_token: str
) -> GenerationRead:
    row = _locked_require(session, generation_id, version_token)
    if row.state not in {"active", "building"}:
        raise OperationError("search_generation_unavailable", kind=ErrorKind.CONFLICT)
    session.exec(
        delete(SearchIndexFailure).where(SearchIndexFailure.generation_id == row.id)
    )
    row.phase = "backfill"
    row.error_code = None
    row.verified_at = None
    session.add(row)
    audit.record(
        session,
        action="search_quarantine_retried",
        resource_type="search_generation",
        resource_id=row.id,
    )
    return read(session, row)


def pin(session: Session, generation_id: int) -> str:
    token = secrets.token_hex(24)
    # Lock the generation row before the lease insert so retirement/prune cannot
    # race a reader admitted to the old active generation.
    result = session.connection().execute(
        update(IndexGeneration)
        .where(IndexGeneration.id == generation_id, IndexGeneration.state == "active")
        .values(last_activity_at=IndexGeneration.last_activity_at)
    )
    if result.rowcount != 1:
        raise EmbeddingError("search_generation_changed")
    session.add(
        SearchGenerationLease(
            token=token,
            generation_id=generation_id,
            expires_at=utcnow() + timedelta(seconds=READER_SECONDS),
        )
    )
    session.commit()
    return token


def unpin(session: Session, token: str) -> None:
    session.exec(
        delete(SearchGenerationLease).where(SearchGenerationLease.token == token)
    )
    session.commit()


def prune_one(session: Session) -> bool:
    now = utcnow()
    session.exec(
        delete(SearchGenerationLease).where(SearchGenerationLease.expires_at <= now)
    )
    row = session.exec(
        select(IndexGeneration)
        .where(
            col(IndexGeneration.state).in_(("retired", "cancelled", "failed")),
            IndexGeneration.version_token.is_not(None),
            IndexGeneration.retain_until <= now,
            ~select(SearchGenerationLease.token)
            .where(
                SearchGenerationLease.generation_id == IndexGeneration.id,
                SearchGenerationLease.expires_at > now,
            )
            .exists(),
        )
        .order_by(IndexGeneration.id)
        .limit(1)
        .with_for_update()
    ).first()
    if row is None:
        session.commit()
        return False
    vector_index.drop(session, row)
    ids = session.exec(
        select(PassageVector.id)
        .where(PassageVector.generation_id == row.id)
        .order_by(PassageVector.id)
        .limit(128)
    ).all()
    if ids:
        session.exec(delete(PassageVector).where(col(PassageVector.id).in_(ids)))
        row.phase = "pruning"
    else:
        row.phase = "pruned"
        row.retain_until = None
        session.exec(
            delete(SearchIndexFailure).where(SearchIndexFailure.generation_id == row.id)
        )
        session.exec(
            delete(SearchReconciliationState).where(
                col(SearchReconciliationState.subject_type).like(f"g{row.id}:%")
            )
        )
    session.add(row)
    session.commit()
    if not ids and row.reservation_id:
        CapacityManager(get_session_factory()).release(row.reservation_id)
    return True
