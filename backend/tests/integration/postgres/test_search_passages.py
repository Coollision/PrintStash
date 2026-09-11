"""Supported PostgreSQL preserves the same durable passage invariants as SQLite."""

from uuid import uuid4

import pytest
from alembic.config import Config
from printstash_core.search.passages import SearchSubject, SubjectType
from sqlalchemy import make_url
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from alembic import command
from app.db.models.search import SearchPassage
from app.db.url import normalize_database_url
from app.modules.search.passages import sync_subject
from tests.containers import postgres_url
from tests.factories import build_model, build_search_passage
from tests.paths import ALEMBIC_INI


@pytest.fixture
def passage_engine():
    schema = "search_passages_" + uuid4().hex
    base_url = make_url(normalize_database_url(postgres_url()))
    base = create_engine(base_url)
    with base.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    url = base_url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(url)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    try:
        SQLModel.metadata.create_all(
            engine,
            tables=[
                table
                for name, table in SQLModel.metadata.tables.items()
                if name != "search_passages"
            ],
        )
        command.stamp(config, "0118bda3e719")
        yield engine, config
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        base.dispose()


class TestSearchPassages:
    def test_projects_existing_models_after_upgrade(self, passage_engine):
        engine, config = passage_engine
        with Session(engine) as session:
            model = build_model(session, "Dragón", description="Print without supports")
            subject = SearchSubject(SubjectType.MODEL, model.id)

        command.upgrade(config, "bf435683b126")
        with Session(engine) as session:
            sync_subject(session, subject)
            session.commit()

        with Session(engine) as session:
            assert (
                session.exec(select(SearchPassage.text)).one()
                == "Title: Dragón\nDescription: Print without supports"
            )

    def test_rejects_duplicate_passage_identity(self, passage_engine):
        engine, config = passage_engine
        command.upgrade(config, "bf435683b126")
        with Session(engine) as session:
            model = build_model(session)
            subject = SearchSubject(SubjectType.MODEL, model.id)
            build_search_passage(session, subject)

            with pytest.raises(IntegrityError, match="uq_search_passage_identity"):
                build_search_passage(session, subject)
            session.rollback()

            assert len(session.exec(select(SearchPassage)).all()) == 1
