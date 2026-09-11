"""Optional native indexes preserve authorized portable vector retrieval."""

import json
import sqlite3

import pytest
from printstash_core.inference import EmbeddingError
from printstash_core.inference import EmbeddingSpace as SpaceContract
from printstash_core.inference.transforms import IndexTransform
from printstash_core.inference.vectors import normalize
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

from app.core.config import _overlay
from app.db.derived_objects import managed_names
from app.db.models import PassageVector
from app.modules.search import vector_index, vector_store


@pytest.fixture(
    params=[("int8", 8), ("binary", 8), ("float32", 4)],
    ids=["int8", "binary", "mrl-prefix"],
)
def compressed_native_units(
    request,
    db_session,
    monkeypatch,
    make_embedding_space,
    make_index_generation,
    make_passage_vector,
    make_model,
    make_file,
):
    monkeypatch.setitem(_overlay, "search_native_vectors_enabled", True)
    quantization, dimension = request.param
    space = make_embedding_space(native_dimension=8)
    transform = IndexTransform.approved(8, dimension, quantization, mrl_dimensions=(4,))
    generation = make_index_generation(
        space,
        index_backend="sqlite_vec",
        index_dimension=dimension,
        quantization=quantization,
        transform_json=transform.metadata(),
    )
    first = make_passage_vector(
        generation,
        make_file(make_model()),
        vector_blob=normalize((1, 2, 3, 4, 5, 6, 7, 8), 8),
    )
    second = make_passage_vector(generation, make_file(make_model()))
    contract = SpaceContract(**json.loads(space.config_json))
    assert vector_index.prepare(db_session, generation)
    assert vector_index.rebuild_partition(db_session, generation) == 2
    db_session.commit()
    yield generation, contract, first, second, transform
    db_session.rollback()
    db_session.execute(
        text(f"DROP TABLE IF EXISTS {vector_index.table_name(generation.id, 'sqlite')}")
    )
    db_session.commit()


@pytest.fixture
def native_units(
    db_session,
    monkeypatch,
    make_embedding_space,
    make_index_generation,
    make_passage_vector,
    make_model,
    make_file,
):
    monkeypatch.setitem(_overlay, "search_native_vectors_enabled", True)
    space = make_embedding_space()
    generation = make_index_generation(space, index_backend="sqlite_vec")
    first = make_passage_vector(generation, make_file(make_model()))
    second = make_passage_vector(generation, make_file(make_model()))
    contract = SpaceContract(**json.loads(space.config_json))
    assert vector_index.prepare(db_session, generation)
    assert vector_index.rebuild_partition(db_session, generation) == 2
    db_session.commit()
    return generation, contract, first, second


class TestVectorIndex:
    def test_rebuilds_compressed_derivatives_without_inference(
        self, db_session, compressed_native_units
    ):
        generation, contract, first, second, _ = compressed_native_units
        db_session.execute(text(f"DROP TABLE {generation.vector_table_name}"))

        fallback = vector_store.query(
            db_session,
            generation_id=generation.id,
            space=contract,
            vector=(1, 2, 3, 4, 5, 6, 7, 8),
            allowed_ids=select(PassageVector.id),
        )
        assert fallback.backend == "numpy"
        assert fallback.items[0].unit_id == first.id
        assert vector_index.repair_partition(db_session) == 2
        db_session.commit()
        rebuilt = vector_store.query(
            db_session,
            generation_id=generation.id,
            space=contract,
            vector=(1, 2, 3, 4, 5, 6, 7, 8),
            allowed_ids=select(PassageVector.id),
        )
        assert rebuilt.backend == "sqlite_vec"
        assert rebuilt.items == fallback.items
        assert len(first.vector_blob) == len(second.vector_blob) == 32

    def test_restores_compressed_generations_without_extension(
        self, db_session, compressed_native_units, tmp_path
    ):
        generation, contract, first, _, _ = compressed_native_units
        snapshot = tmp_path / "compressed.sqlite"
        with sqlite3.connect(snapshot) as destination:
            db_session.connection().connection.driver_connection.backup(destination)
        engine = create_engine(f"sqlite:///{snapshot}")
        try:
            with Session(engine) as restored:
                result = vector_store.query(
                    restored,
                    generation_id=generation.id,
                    space=contract,
                    vector=(1, 2, 3, 4, 5, 6, 7, 8),
                    allowed_ids=select(PassageVector.id),
                )
                assert result.backend == "numpy"
                assert result.items[0].unit_id == first.id
                assert (
                    restored.get(PassageVector, first.id).vector_blob
                    == first.vector_blob
                )
        finally:
            engine.dispose()

    def test_rescores_compressed_native_candidates(
        self, db_session, compressed_native_units
    ):
        generation, contract, first, _, transform = compressed_native_units

        result = vector_store.query(
            db_session,
            generation_id=generation.id,
            space=contract,
            vector=(1, 2, 3, 4, 5, 6, 7, 8),
            allowed_ids=select(PassageVector.id),
            limit=1,
        )

        assert result.backend == "sqlite_vec"
        assert result.items[0].unit_id == first.id
        assert result.items[0].score == pytest.approx(1)
        assert len(first.vector_blob) == 32
        assert (
            db_session.execute(
                text(
                    f"SELECT vec_length(embedding) FROM {generation.vector_table_name} WHERE rowid=:id"
                ),
                {"id": first.id},
            ).scalar_one()
            == transform.storage_dimension
        )

    def test_queries_only_authorized_native_units(self, db_session, native_units):
        generation, contract, first, second = native_units
        result = vector_store.query(
            db_session,
            generation_id=generation.id,
            space=contract,
            vector=[1, 0, 0],
            allowed_ids=select(PassageVector.id).where(PassageVector.id == second.id),
        )
        assert result.backend == "sqlite_vec"
        assert [row.unit_id for row in result.items] == [second.id]
        assert result.scanned == 1

    def test_excludes_registered_vector_objects(self, db_session, native_units):
        generation, *_ = native_units
        db_session.execute(text("CREATE TABLE unrelated_data(id INTEGER)"))
        names = managed_names(db_session.connection())
        assert generation.vector_table_name in names
        assert generation.vector_table_name + "_vector_chunks00" in names
        assert "unrelated_data" not in names
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from sqlmodel import SQLModel

        context = MigrationContext.configure(
            db_session.connection(),
            opts={
                "include_name": lambda name, kind, parents: (
                    not (kind == "table" and name in names)
                ),
                "compare_server_default": True,
            },
        )
        changes = compare_metadata(context, SQLModel.metadata)
        assert len(changes) == 1
        assert changes[0][0] == "remove_table"
        assert changes[0][1].name == "unrelated_data"
        db_session.execute(text("DROP TABLE unrelated_data"))
        assert compare_metadata(context, SQLModel.metadata) == []

    def test_restores_native_vectors_without_extension(
        self, db_session, native_units, tmp_path
    ):
        generation, contract, first, second = native_units
        snapshot = tmp_path / "restored.sqlite"
        with sqlite3.connect(snapshot) as destination:
            db_session.connection().connection.driver_connection.backup(destination)
        engine = create_engine(f"sqlite:///{snapshot}")
        try:
            with Session(engine) as restored:
                # This fresh connection never loads sqlite-vec, while the file
                # still contains the native virtual table and all its shadows.
                result = vector_store.query(
                    restored,
                    generation_id=generation.id,
                    space=contract,
                    vector=[1, 0, 0],
                    allowed_ids=select(PassageVector.id),
                )
                assert result.backend == "numpy"
                assert {row.unit_id for row in result.items} == {first.id, second.id}
                assert (
                    restored.get(PassageVector, first.id).vector_blob
                    == first.vector_blob
                )
        finally:
            engine.dispose()

    def test_falls_back_after_native_table_loss(self, db_session, native_units):
        generation, contract, *_ = native_units
        db_session.execute(text(f"DROP TABLE {generation.vector_table_name}"))
        result = vector_store.query(
            db_session,
            generation_id=generation.id,
            space=contract,
            vector=[1, 0, 0],
            allowed_ids=select(PassageVector.id),
        )
        assert result.backend == "numpy"
        assert len(result.items) == 2

    def test_repairs_native_tables_without_inference(self, db_session, native_units):
        generation, contract, *_ = native_units
        db_session.execute(text(f"DROP TABLE {generation.vector_table_name}"))
        assert vector_index.repair_partition(db_session) == 2
        db_session.commit()
        result = vector_store.query(
            db_session,
            generation_id=generation.id,
            space=contract,
            vector=[1, 0, 0],
            allowed_ids=select(PassageVector.id),
        )
        assert result.backend == "sqlite_vec"
        assert len(result.items) == 2

    def test_retirement_preserves_full_float_rows(self, db_session, native_units):
        generation, _, first, _ = native_units
        with pytest.raises(EmbeddingError, match="not_retired"):
            vector_index.drop(db_session, generation)
        generation.state = "retired"
        generation.active_profile_key = None
        vector_index.drop(db_session, generation)
        assert db_session.get(PassageVector, first.id).vector_blob == first.vector_blob
        assert generation.vector_table_name is None

    def test_rolls_back_native_preparation(self, db_session, native_units):
        generation, *_ = native_units
        original = generation.vector_table_name
        generation.index_state = "absent"
        vector_index.prepare(db_session, generation)
        db_session.rollback()
        assert generation.index_state == "ready"
        assert (
            db_session.execute(text(f"SELECT count(*) FROM {original}")).scalar_one()
            == 2
        )

    @pytest.mark.parametrize("id", [0, -1, True, "1; DROP TABLE models", 2**63])
    def test_refuses_untrusted_generation_identifiers(self, id):
        with pytest.raises(EmbeddingError, match="generation_invalid"):
            vector_index.table_name(id, "sqlite")
