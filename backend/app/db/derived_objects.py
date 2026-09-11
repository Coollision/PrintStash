"""Exact registry of reconstructible database objects owned by the application."""

from sqlalchemy import Connection, text

SEARCH_FTS = "search_passages_fts"
SEARCH_FTS_OBJECTS = frozenset(
    {
        SEARCH_FTS,
        *(SEARCH_FTS + suffix for suffix in ("_data", "_idx", "_docsize", "_config")),
    }
)


def managed_names(connection: Connection | None) -> frozenset[str]:
    if connection is None or connection.dialect.name != "sqlite":
        return frozenset()
    ddl = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": SEARCH_FTS},
    ).scalar()
    if (
        not isinstance(ddl, str)
        or "using fts5(" not in ddl.lower()
        or "content='search_passages'" not in ddl.lower()
    ):
        return frozenset()
    return SEARCH_FTS_OBJECTS
