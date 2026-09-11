"""Reconstructible native indexes; full native float32 remains authoritative."""

from __future__ import annotations

import struct

from printstash_core.inference import EmbeddingError
from sqlalchemy import Integer, Select, column, literal, table, text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import IndexGeneration, PassageVector, SearchReconciliationState
from app.db.transactions import begin_write
from app.db.vector_extensions import load_sqlite_vector_extension


def table_name(generation_id: int, dialect: str) -> str:
    if type(generation_id) is not int or not 1 <= generation_id < 2**63:
        raise EmbeddingError("embedding_generation_invalid")
    return ("vec_gen_" if dialect == "sqlite" else "gen_vectors_") + str(generation_id)


def _fallback(session: Session, generation: IndexGeneration, code: str) -> None:
    generation.index_state = "unavailable"
    generation.index_error = code
    session.add(generation)
    session.flush()


def _native_supported(session: Session, generation: IndexGeneration) -> bool:
    if not settings.search_native_vectors_enabled:
        _fallback(session, generation, "embedding_native_disabled")
        return False
    if generation.quantization != "float32":
        _fallback(session, generation, "embedding_native_transform_unsupported")
        return False
    if session.get_bind().dialect.name == "sqlite":
        # Also covers a connection opened before an operator enables the flag.
        if not load_sqlite_vector_extension(
            session.connection().connection.driver_connection
        ):
            _fallback(session, generation, "embedding_sqlite_vec_unavailable")
            return False
    elif generation.index_dimension > 2000:
        _fallback(session, generation, "embedding_pgvector_dimension_unsupported")
        return False
    return True


def prepare(session: Session, generation: IndexGeneration) -> bool:
    """Probe actual native DDL/types in a savepoint; never fail content startup."""
    begin_write(session)
    if generation.index_backend == "numpy":
        generation.index_state = "ready"
        generation.index_error = None
        session.add(generation)
        session.flush()
        return False
    if not _native_supported(session, generation):
        return False
    name = table_name(generation.id, session.get_bind().dialect.name)
    dimension = generation.index_dimension
    if type(dimension) is not int or not 1 <= dimension <= 4096:
        raise EmbeddingError("embedding_dimension_invalid")
    try:
        with session.begin_nested():
            session.execute(text(f"DROP TABLE IF EXISTS {name}"))
            if session.get_bind().dialect.name == "sqlite":
                session.execute(
                    text(
                        f"CREATE VIRTUAL TABLE {name} USING vec0(embedding float[{dimension}] distance_metric=cosine)"
                    )
                )
                probe = struct.pack(f"<{dimension}f", 1, *([0] * (dimension - 1)))
                session.execute(
                    text(f"INSERT INTO {name}(rowid,embedding) VALUES (0,:v)"),
                    {"v": probe},
                )
                assert (
                    session.execute(
                        text(f"SELECT vec_length(embedding) FROM {name} WHERE rowid=0")
                    ).scalar_one()
                    == dimension
                )
                session.execute(text(f"DELETE FROM {name} WHERE rowid=0"))
            else:
                # Availability alone is insufficient: permission or extension
                # installation can fail. Only this explicit prepare attempts it.
                session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                session.execute(
                    text(
                        f"CREATE TABLE {name} (id INTEGER PRIMARY KEY, embedding vector({dimension}) NOT NULL)"
                    )
                )
                session.execute(
                    text(
                        f"CREATE INDEX {name}_hnsw ON {name} USING hnsw (embedding vector_cosine_ops)"
                    )
                )
                probe = "[1" + ",0" * (dimension - 1) + "]"
                actual = session.execute(
                    text(f"SELECT vector_dims(CAST(:v AS vector({dimension})))"),
                    {"v": probe},
                ).scalar_one()
                if actual != dimension:
                    raise EmbeddingError("embedding_dimension_mismatch")
            generation.vector_table_name = name
            generation.index_state = "building"
            generation.index_error = None
            generation.indexed_after_id = 0
            session.add(generation)
            session.flush()
        return True
    except (DBAPIError, EmbeddingError):
        _fallback(session, generation, "embedding_native_unavailable")
        return False


def replace(session: Session, generation: IndexGeneration, row: PassageVector) -> None:
    """Update one derived unit transactionally; adapter errors preserve floats."""
    if (
        generation.index_state not in {"building", "ready"}
        or generation.index_backend == "numpy"
    ):
        return
    name = table_name(generation.id, session.get_bind().dialect.name)
    if generation.vector_table_name != name:
        _fallback(session, generation, "embedding_native_unavailable")
        return
    try:
        with session.begin_nested():
            if session.get_bind().dialect.name == "sqlite":
                session.execute(
                    text(f"DELETE FROM {name} WHERE rowid=:id"), {"id": row.id}
                )
                session.execute(
                    text(f"INSERT INTO {name}(rowid,embedding) VALUES (:id,:v)"),
                    {"id": row.id, "v": row.vector_blob},
                )
            else:
                values = struct.unpack(f"<{row.native_dimension}f", row.vector_blob)
                encoded = "[" + ",".join(str(value) for value in values) + "]"
                session.execute(
                    text(
                        f"INSERT INTO {name}(id,embedding) VALUES (:id,CAST(:v AS vector)) ON CONFLICT (id) DO UPDATE SET embedding=EXCLUDED.embedding"
                    ),
                    {"id": row.id, "v": encoded},
                )
    except (DBAPIError, struct.error):
        _fallback(session, generation, "embedding_native_unavailable")


def rebuild_partition(
    session: Session, generation: IndexGeneration, *, limit: int = 128
) -> int:
    if not 1 <= limit <= 1024:
        raise EmbeddingError("embedding_rebuild_budget_invalid")
    if generation.index_state not in {"building", "ready"} and not prepare(
        session, generation
    ):
        return 0
    if generation.index_state == "ready":
        return 0
    rows = session.exec(
        select(PassageVector)
        .where(
            PassageVector.generation_id == generation.id,
            PassageVector.id > generation.indexed_after_id,
        )
        .order_by(PassageVector.id)
        .limit(limit)
    ).all()
    for row in rows:
        replace(session, generation, row)
        if generation.index_state == "unavailable":
            return 0
    if rows:
        generation.indexed_after_id = rows[-1].id
    if len(rows) < limit:
        generation.index_state = "ready"
    session.add(generation)
    session.flush()
    return len(rows)


def shortlist(
    session: Session,
    generation: IndexGeneration,
    query: bytes,
    allowed_ids: Select,
    *,
    limit: int,
) -> tuple[int, ...] | None:
    """Authorized native candidates, or None to request bounded NumPy fallback.

    SQLite vec0 applies its rowid IN filter before KNN. PostgreSQL materializes
    the authorized relation before distance ordering; this deliberately trades
    HNSW's unfiltered speed for permission isolation under restrictive access.
    """
    if (
        not settings.search_native_vectors_enabled
        or generation.index_backend == "numpy"
        or generation.index_state != "ready"
    ):
        return None
    if not 1 <= limit <= 2048:
        raise EmbeddingError("embedding_query_budget_invalid")
    dialect = session.get_bind().dialect.name
    name = table_name(generation.id, dialect)
    if generation.vector_table_name != name:
        return None
    try:
        with session.begin_nested():
            if dialect == "sqlite":
                native = table(
                    name,
                    column("rowid", Integer),
                    column("embedding"),
                    column("k", Integer),
                )
                statement = select(native.c.rowid).where(
                    native.c.embedding.op("MATCH")(query),
                    native.c.k == limit,
                    native.c.rowid.in_(allowed_ids),
                )
            else:
                native = table(name, column("id", Integer), column("embedding"))
                authorized = (
                    select(native.c.id, native.c.embedding)
                    .where(native.c.id.in_(allowed_ids))
                    .cte()
                    .prefix_with("MATERIALIZED")
                )
                values = struct.unpack(f"<{len(query) // 4}f", query)
                encoded = "[" + ",".join(str(value) for value in values) + "]"
                distance = authorized.c.embedding.op("<=>")(
                    literal(encoded).cast(_vector_type())
                )
                statement = (
                    select(authorized.c.id)
                    .order_by(distance, authorized.c.id)
                    .limit(limit)
                )
            return tuple(session.execute(statement).scalars())
    except (DBAPIError, struct.error):
        return None


def _vector_type():
    from sqlalchemy.types import UserDefinedType

    class VectorType(UserDefinedType):
        cache_ok = True

        def get_col_spec(self, **kw):
            return "vector"

    return VectorType()


def drop(session: Session, generation: IndexGeneration) -> None:
    """Only a drained retired generation can discard its reconstructible DDL."""
    if generation.state != "retired":
        raise EmbeddingError("embedding_generation_not_retired")
    name = table_name(generation.id, session.get_bind().dialect.name)
    if generation.vector_table_name == name:
        session.execute(text(f"DROP TABLE IF EXISTS {name}"))
    generation.vector_table_name = None
    generation.index_state = "absent"
    session.add(generation)
    session.flush()


def repair_partition(session: Session) -> int:
    """Round-robin one live Generation; startup never waits for a full rebuild."""
    if not settings.search_native_vectors_enabled:
        return 0
    checkpoint = session.exec(select(SearchReconciliationState).where(
        SearchReconciliationState.subject_type == "vector_index")).first()
    if checkpoint is None:
        checkpoint = SearchReconciliationState(subject_type="vector_index")
        session.add(checkpoint)
        session.flush()
    eligible = select(IndexGeneration).where(
        IndexGeneration.state.in_(("active", "building", "ready")),
        IndexGeneration.index_backend != "numpy")
    generation = session.exec(eligible.where(IndexGeneration.id > checkpoint.partition_after_id)
        .order_by(IndexGeneration.id).limit(1)).first()
    if generation is None:
        checkpoint.partition_after_id = 0
        session.add(checkpoint)
        session.flush()
        return 0
    checkpoint.partition_after_id = generation.id
    session.add(checkpoint)
    if generation.index_state == "ready":
        name = table_name(generation.id, session.get_bind().dialect.name)
        try:
            with session.begin_nested():
                session.execute(text(f"SELECT embedding FROM {name} LIMIT 0"))
        except DBAPIError:
            generation.index_state = "absent"
            session.add(generation)
    return rebuild_partition(session, generation)
