"""SQLite plumbing shared by stateful features.

The core stays stdlib-only: everything here is built on :mod:`sqlite3`.

The API is synchronous on purpose. Handlers and the scheduler run on the asyncio
event loop, so they must call these helpers through :func:`asyncio.to_thread`
(see :class:`agent_sip.reminders.store.ReminderStore`).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def connect(path: str | os.PathLike[str]) -> sqlite3.Connection:
    """Open (and create) a SQLite database with the settings features expect.

    Missing parent directories are created. WAL allows readers while a writer is
    active, foreign keys are enforced, and ``check_same_thread=False`` lets the
    single connection be used from ``asyncio.to_thread`` worker threads (callers
    must still serialise access, e.g. with a lock).
    """
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def split_statements(script: str) -> list[str]:
    """Split a SQL script into individual statements.

    :func:`sqlite3.complete_statement` is used rather than ``str.split(';')`` so
    semicolons inside string literals, comments or triggers do not break the
    script. Needed because ``Connection.executescript`` commits before running,
    which would defeat per-migration transactions.
    """
    statements: list[str] = []
    buffer = ""
    for char in script:
        buffer += char
        if char == ";" and sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    tail = buffer.strip()
    if tail:
        statements.append(tail)
    return statements


def migrate(conn: sqlite3.Connection, migrations: list[str]) -> int:
    """Apply ``migrations`` that are newer than the database, in order.

    Version ``n`` is the 1-based index into ``migrations``; it is stored in
    ``PRAGMA user_version``. Every migration runs inside its own transaction and
    is rolled back completely if any statement fails, so ``user_version`` only
    advances for fully applied migrations. Calling this again with the same list
    is a no-op (idempotent).

    Returns the number of migrations applied.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    applied = 0
    for version, script in enumerate(migrations, start=1):
        if version <= current:
            continue
        conn.execute("BEGIN")
        try:
            for statement in split_statements(script):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()
        applied += 1
    return applied
