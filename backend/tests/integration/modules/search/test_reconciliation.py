"""Durable bounded partitions repair edits that bypass content notifications."""

import pytest
from printstash_core.search.passages import SearchSubject, SubjectType
from sqlmodel import delete, select

from app.db.models import Document, SearchPassage, SearchReconciliationState
from app.modules.search.passages import sync_subject
from app.modules.search.reconciliation import reconcile_partition


class TestReconciliation:
    @pytest.mark.parametrize("limit", [0, -1, 1025])
    def test_rejects_an_invalid_repair_limit(self, db_session, limit):
        with pytest.raises(ValueError, match="search_reconciliation_limit"):
            reconcile_partition(db_session, SubjectType.DOCUMENT, limit=limit)
        assert db_session.exec(select(SearchReconciliationState)).all() == []

    def test_repairs_a_body_change_without_a_timestamp(self, db_session, make_document):
        document = make_document("Guide", body="Old instructions")
        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)
        db_session.commit()
        document.body = "New instructions"
        db_session.add(document)
        db_session.commit()

        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)

        assert (
            db_session.exec(select(SearchPassage.text))
            .one()
            .endswith("New instructions")
        )

    def test_persists_the_partition_cursor(self, db_session, make_document):
        documents = [make_document(f"Guide {i}") for i in range(4)]
        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)
        db_session.commit()
        db_session.expire_all()

        state = db_session.exec(select(SearchReconciliationState)).one()

        assert state.partition_after_id == documents[1].id

    def test_removes_a_passage_after_an_unobserved_deletion(
        self, db_session, make_document
    ):
        document = make_document("Guide")
        sync_subject(db_session, SearchSubject(SubjectType.DOCUMENT, document.id))
        db_session.exec(delete(Document).where(Document.id == document.id))
        db_session.commit()

        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)

        assert db_session.exec(select(SearchPassage)).all() == []

    def test_limits_work_to_the_current_partition(self, db_session, make_document):
        documents = [make_document(f"Guide {i}") for i in range(4)]

        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)

        assert set(db_session.exec(select(SearchPassage.subject_id)).all()) == {
            document.id for document in documents[:2]
        }

    def test_reaches_the_next_partition(self, db_session, make_document):
        documents = [make_document(f"Guide {i}") for i in range(4)]
        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)
        db_session.commit()

        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)

        assert set(db_session.exec(select(SearchPassage.subject_id)).all()) == {
            document.id for document in documents
        }

    def test_removes_an_orphan_dependency_without_a_passage(
        self, db_session, make_document
    ):
        from app.db.models import SearchDependency

        document = make_document("Guide")
        sync_subject(db_session, SearchSubject(SubjectType.DOCUMENT, document.id))
        db_session.exec(
            delete(SearchPassage).where(
                SearchPassage.subject_type == "document",
                SearchPassage.subject_id == document.id,
            )
        )
        db_session.exec(delete(Document).where(Document.id == document.id))
        db_session.commit()

        reconcile_partition(db_session, SubjectType.DOCUMENT, limit=2)

        assert db_session.exec(select(SearchDependency)).all() == []
