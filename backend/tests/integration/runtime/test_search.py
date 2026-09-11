"""Projection repair participates in the same maintenance admission as writes."""

import asyncio
import threading

import pytest
from printstash_core.search.passages import SubjectType
from sqlmodel import select

from app.db.models import SearchPassage, SearchReconciliationState
from app.db.session import get_session_factory
from app.runtime import maintenance, search


class TestSearchRuntime:
    def test_defers_projection_repair_during_restore(self, db_session):
        maintenance.hold_restore_maintenance()
        try:
            assert search.process_one(SubjectType.DOCUMENT) == 0
            assert db_session.exec(select(SearchReconciliationState)).all() == []
        finally:
            maintenance.end_restore_maintenance()

    def test_commits_a_projection_repair_partition(self, db_session, make_document):
        document = make_document("Assembly", body="Press the latch")
        assert search.process_one(SubjectType.DOCUMENT) == 1
        with get_session_factory().scoped_session() as session:
            assert (
                session.exec(
                    select(SearchPassage.text).where(
                        SearchPassage.subject_type == "document",
                        SearchPassage.subject_id == document.id,
                    )
                ).one()
                == "Title: Assembly\nBody: Press the latch"
            )

    @pytest.mark.asyncio
    async def test_cancellation_waits_for_projection_repair(self, monkeypatch):
        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def bounded(_kind):
            entered.set()
            assert release.wait(timeout=5)
            finished.set()
            return 1

        monkeypatch.setattr(search, "process_one", bounded)
        task = asyncio.create_task(search.run_search())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
            assert finished.is_set()
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
