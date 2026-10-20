"""The ``Reminder`` dataclass, mirroring the migration-1 schema."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Reminder:
    """A stored reminder.

    Times are UTC epoch seconds. ``tz`` is the IANA zone the user scheduled in;
    it is kept per reminder so recurrence math and speaking times survive the
    server running in a different zone. ``next_try_at`` is when the scheduler
    should next act: normally ``due_at``, or a later retry time.
    """

    message: str
    due_at: int
    tz: str
    phone: str
    repeat: str = "none"
    until: int | None = None
    status: str = "pending"
    attempts: int = 0
    next_try_at: int = 0
    created_at: int = 0
    id: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Reminder:
        return cls(
            id=row["id"],
            message=row["message"],
            due_at=row["due_at"],
            tz=row["tz"],
            repeat=row["repeat"],
            until=row["until"],
            phone=row["phone"],
            status=row["status"],
            attempts=row["attempts"],
            next_try_at=row["next_try_at"],
            created_at=row["created_at"],
        )
