"""Persistence layer — storage-agnostic.

Two interchangeable backends with an identical method surface:
  * SQLiteStore   — zero-infra, default; the journal/decisions/lessons/metrics
    survive across runs without standing up a server.
  * PostgresStore — production; same schema as ``migrations/*.sql``.

Use :func:`make_store` to pick a backend from a URL/path so the rest of the code
never cares which one is in play.
"""

from __future__ import annotations

from app.db.store import SQLiteStore

__all__ = ["SQLiteStore", "make_store"]


def make_store(url: str | None = None):
    """Build a store from a URL/path.

    * ``postgresql://...`` / ``postgres://...``  -> PostgresStore
    * ``sqlite:///path`` or a bare filesystem path -> SQLiteStore (default)
    """
    if not url:
        return SQLiteStore()
    low = url.lower()
    if low.startswith(("postgresql://", "postgres://")):
        from app.db.postgres_store import PostgresStore

        return PostgresStore(url)
    if low.startswith("sqlite:///"):
        return SQLiteStore(url[len("sqlite:///"):])
    return SQLiteStore(url)
