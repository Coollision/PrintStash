"""Durable passage refresh is idempotent and belongs to the content transaction.

Old recipes survive live refreshes; absence removes every recipe. No inference
or user-facing retrieval is implied by these internal persistence contracts.
"""

from datetime import datetime

from printstash_core.search.passages import RECIPE_VERSION, SearchSubject, SubjectType
from sqlmodel import select

from app.db.models.search import SearchPassage
from app.modules.search.passages import PassageChanges, sync_subject


class TestSyncSubject:
    def test_persists_model_text(self, db_session, make_model):
        model = make_model("Dragon", description="No supports")

        changes = sync_subject(db_session, SearchSubject(SubjectType.MODEL, model.id))
        db_session.commit()
        row = db_session.exec(select(SearchPassage)).one()

        assert changes == PassageChanges(inserted=1)
        assert row.text == "Title: Dragon\nDescription: No supports"
        assert row.access_dependencies_json == "[]"

    def test_preserves_idempotent_passage_identity(self, db_session, make_model):
        model = make_model("Dragon")
        subject = SearchSubject(SubjectType.MODEL, model.id)
        sync_subject(db_session, subject)
        db_session.commit()
        row = db_session.exec(select(SearchPassage)).one()
        before = (row.id, row.content_hash, row.updated_at)

        changes = sync_subject(db_session, subject)
        db_session.commit()
        db_session.refresh(row)

        assert changes == PassageChanges()
        assert (row.id, row.content_hash, row.updated_at) == before

    def test_ignores_nonindexed_edits_for_content_freshness(
        self, db_session, make_model
    ):
        model = make_model("Dragon")
        subject = SearchSubject(SubjectType.MODEL, model.id)
        sync_subject(db_session, subject)
        row = db_session.exec(select(SearchPassage)).one()
        before = (row.id, row.content_hash, row.updated_at)
        model.updated_at = datetime(2026, 9, 12)
        model.thumbnail_path = "new-thumbnail.webp"
        db_session.add(model)

        changes = sync_subject(db_session, subject)
        db_session.commit()

        assert changes == PassageChanges()
        assert (row.id, row.content_hash, row.updated_at) == before

    def test_replaces_changed_passage_content(self, db_session, make_model):
        model = make_model("Dragon")
        subject = SearchSubject(SubjectType.MODEL, model.id)
        sync_subject(db_session, subject)
        row = db_session.exec(select(SearchPassage)).one()
        original_id, original_hash = row.id, row.content_hash
        model.description = "Prints without supports"
        db_session.add(model)

        changes = sync_subject(db_session, subject)
        db_session.commit()

        assert changes == PassageChanges(updated=1)
        assert row.id == original_id
        assert row.content_hash != original_hash
        assert row.text.endswith("Description: Prints without supports")

    def test_removes_obsolete_passage_windows(self, db_session, make_document):
        document = make_document(body="word " * 500)
        subject = SearchSubject(SubjectType.DOCUMENT, document.id)
        sync_subject(db_session, subject)
        document.body = "Short guide"
        db_session.add(document)

        changes = sync_subject(db_session, subject)

        assert changes == PassageChanges(updated=1, removed=1)
        assert db_session.exec(select(SearchPassage.text)).all() == [
            "Title: manual\nBody: Short guide"
        ]

    def test_preserves_other_live_recipes(
        self, db_session, make_model, make_search_passage
    ):
        model = make_model("Dragon")
        subject = SearchSubject(SubjectType.MODEL, model.id)
        old = make_search_passage(
            subject, recipe_version=RECIPE_VERSION + 1, text="Other recipe"
        )

        sync_subject(db_session, subject)
        db_session.commit()

        assert db_session.get(SearchPassage, old.id).text == "Other recipe"
        assert len(db_session.exec(select(SearchPassage)).all()) == 2

    def test_removes_every_recipe_for_a_trashed_subject(
        self, db_session, make_model, make_search_passage
    ):
        model = make_model("Dragon", trashed=True)
        subject = SearchSubject(SubjectType.MODEL, model.id)
        make_search_passage(subject)
        make_search_passage(subject, recipe_version=RECIPE_VERSION + 1)

        changes = sync_subject(db_session, subject)

        assert changes == PassageChanges(removed=2)
        assert db_session.exec(select(SearchPassage)).all() == []

    def test_removes_passages_for_a_purged_subject(
        self, db_session, make_model, make_search_passage
    ):
        model = make_model("Dragon")
        subject = SearchSubject(SubjectType.MODEL, model.id)
        make_search_passage(subject)
        db_session.delete(model)
        db_session.commit()

        changes = sync_subject(db_session, subject)

        assert changes == PassageChanges(removed=1)
        assert db_session.exec(select(SearchPassage)).all() == []

    def test_restores_passages_for_a_restored_subject(self, db_session, make_model):
        model = make_model("Dragon", trashed=True)
        subject = SearchSubject(SubjectType.MODEL, model.id)
        sync_subject(db_session, subject)
        model.deleted_at = None
        db_session.add(model)

        changes = sync_subject(db_session, subject)

        assert changes == PassageChanges(inserted=1)
        assert db_session.exec(select(SearchPassage.text)).one() == "Title: Dragon"

    def test_rolls_projection_back_with_content(self, db_session, make_model):
        model = make_model("Dragon")
        subject = SearchSubject(SubjectType.MODEL, model.id)
        sync_subject(db_session, subject)
        db_session.commit()
        model.description = "Uncommitted description"
        db_session.add(model)
        sync_subject(db_session, subject)

        db_session.rollback()
        db_session.refresh(model)

        assert model.description is None
        assert db_session.exec(select(SearchPassage.text)).one() == "Title: Dragon"

    def test_does_not_create_rows_for_a_missing_subject(self, db_session):
        changes = sync_subject(db_session, SearchSubject(SubjectType.MODEL, 123456))

        assert changes == PassageChanges()
        assert db_session.exec(select(SearchPassage)).all() == []
