"""Bounded local projection repair, coordinated with database maintenance."""

from __future__ import annotations

import asyncio
from itertools import cycle

from printstash_core.inference import EmbeddingError
from printstash_core.search.passages import SubjectType

from app.core.errors import OperationError
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.modules.inference import model_cache
from app.modules.inference.worker_pool import pool as model_workers
from app.modules.search.generations import ensure_caption_recipe
from app.modules.search.indexing import IndexProcessor
from app.modules.search.lexical_index import rebuild_partition
from app.modules.search.reconciliation import reconcile_partition
from app.modules.search.vector_index import repair_partition as repair_vectors
from app.runtime import maintenance

logger = get_logger(__name__)


def process_one(kind: SubjectType) -> int:
    if not maintenance.begin_mutating_operation():
        return 0
    try:
        with get_session_factory().scoped_session() as session:
            model_workers.prune_idle(
                tuple(
                    model.directory
                    for model in model_cache.inventory()
                    if model_cache.referenced(session, model)
                )
            )
            changed = reconcile_partition(session, kind)
            rebuild_partition(session)
            repair_vectors(session)
            session.commit()
        with get_session_factory().scoped_session() as session:
            try:
                ensure_caption_recipe(session)
            except (OperationError, EmbeddingError):
                session.rollback()
                logger.debug("Caption recipe proposal deferred")
        IndexProcessor(get_session_factory()).work_one()
        return changed
    finally:
        maintenance.end_mutating_operation()


async def run_search() -> None:
    for kind in cycle(SubjectType):
        unit = asyncio.create_task(asyncio.to_thread(process_one, kind))
        try:
            await asyncio.shield(unit)
        except asyncio.CancelledError:
            await unit
            raise
        except Exception:
            logger.warning("Search indexing paused; retrying a bounded repair unit")
        await asyncio.sleep(1)
