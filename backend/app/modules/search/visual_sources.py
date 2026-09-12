"""Current visual units: one stable live mesh Artifact per live Model."""

from __future__ import annotations

from printstash_core.search.visual_inputs import VisualRecipe
from sqlalchemy import String, and_, cast, func, literal, or_
from sqlmodel import Session, col, select

from app.db.models import (
    SENTINEL_MODEL_HASH,
    File,
    FileType,
    Model,
    PassageVector,
    SearchIndexFailure,
    User,
)
from app.db.scopes import live
from app.modules.library.model_views.access import accessible_live_model_ids_stmt

PROFILES = ("thumbnail", "multiview")


def eligible(session: Session, user: User | None = None):
    """Use the oldest live mesh, preserving identity when G-code revisions arrive."""
    statement = (
        select(func.min(File.id))
        .join(Model, Model.id == File.model_id)
        .where(
            live(File),
            live(Model),
            Model.hash != SENTINEL_MODEL_HASH,
            col(File.file_type).in_(
                (FileType.STL, FileType.THREE_MF, FileType.OBJ, FileType.STEP)
            ),
        )
    )
    if user is not None:
        statement = statement.where(
            Model.id.in_(accessible_live_model_ids_stmt(session, user))
        )
    return statement.group_by(File.model_id)


def units_per_file(recipe: VisualRecipe) -> int:
    return (
        1 if recipe.profile == "thumbnail" else 8
    )  # six views, mean and fallback thumbnail


def complete_files(session: Session, generation_id: int, space):
    recipe = VisualRecipe.for_space(space)
    prefix = literal("file:") + cast(File.id, String) + literal(":")
    valid_unit = and_(
        PassageVector.unit_kind == "visual_mean",
        PassageVector.unit_key == prefix + literal("mean"),
    )
    if recipe.profile == "multiview":
        valid_unit = or_(
            valid_unit,
            and_(
                PassageVector.unit_kind == "visual_view",
                PassageVector.unit_key.in_(
                    [prefix + literal(f"view:{index}") for index in range(6)]
                ),
            ),
            and_(
                PassageVector.unit_kind == "visual_thumbnail",
                PassageVector.unit_key == prefix + literal("thumbnail"),
            ),
        )
    return (
        select(PassageVector.file_id)
        .join(File, File.id == PassageVector.file_id)
        .where(
            PassageVector.generation_id == generation_id,
            PassageVector.native_dimension == space.dimension,
            PassageVector.input_hash == File.sha256,
            PassageVector.subject_type == "model",
            PassageVector.subject_id == File.model_id,
            valid_unit,
            PassageVector.unit_kind.in_(
                ("visual_mean",)
                if recipe.profile == "thumbnail"
                else ("visual_mean", "visual_view", "visual_thumbnail")
            ),
            File.id.in_(eligible(session)),
        )
        .group_by(PassageVector.file_id)
        .having(func.count() == units_per_file(recipe))
    )


def current_vectors(
    session: Session, generation_id: int, space, user: User | None = None
):
    recipe = VisualRecipe.for_space(space)
    kind = (
        "visual_view"
        if recipe.profile == "multiview" and recipe.aggregation == "max"
        else "visual_mean"
    )
    prefix = literal("file:") + cast(PassageVector.file_id, String) + literal(":")
    keys = (
        [prefix + literal(f"view:{index}") for index in range(6)]
        if kind == "visual_view"
        else [prefix + literal("mean")]
    )
    statement = select(PassageVector.id).where(
        PassageVector.generation_id == generation_id,
        PassageVector.file_id.in_(complete_files(session, generation_id, space)),
        PassageVector.unit_kind == kind,
        PassageVector.unit_key.in_(keys),
        PassageVector.native_dimension == space.dimension,
    )
    if user is not None:
        statement = statement.where(PassageVector.file_id.in_(eligible(session, user)))
    return statement


def missing(session: Session, generation_id: int, space):
    return select(File.id).where(
        File.id.in_(eligible(session)),
        File.id.not_in(complete_files(session, generation_id, space)),
    )


def counts(session: Session, generation_id: int, space) -> tuple[int, int, int]:
    total = session.exec(
        select(func.count()).select_from(eligible(session).subquery())
    ).one()
    indexed = session.exec(
        select(func.count()).select_from(
            complete_files(session, generation_id, space).subquery()
        )
    ).one()
    quarantined = session.exec(
        select(func.count())
        .select_from(SearchIndexFailure)
        .join(File, File.id == SearchIndexFailure.file_id)
        .where(
            SearchIndexFailure.generation_id == generation_id,
            SearchIndexFailure.state == "quarantined",
            SearchIndexFailure.input_hash == File.sha256,
            File.id.in_(eligible(session)),
        )
    ).one()
    return total, indexed, quarantined
