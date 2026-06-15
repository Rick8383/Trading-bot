"""Persistence layer.

Phase 2 ships a zero-infra SQLite store (stdlib only) so the journal, decisions,
lessons and metrics survive across runs without standing up PostgreSQL. The
schema mirrors ``migrations/*.sql`` exactly, so moving to Postgres later is a
connection-string change, not a rewrite.
"""

from app.db.store import SQLiteStore

__all__ = ["SQLiteStore"]
