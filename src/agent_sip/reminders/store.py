"""Async persistence for reminders over a single SQLite connection.

The SQL is synchronous; every public method wraps it in :func:`asyncio.to_thread`
so the event loop is never blocked (AGENTS.md). Because one connection is shared
by the worker threads, all access is serialised with a :class:`threading.Lock`.

The store takes an already-open connection (opened via :func:`agent_sip.db.connect`
and migrated by the caller); it never reads the configured path itself.

State machine
-------------
``pending`` is the only live state. Attempts are recorded with
:meth:`mark_attempt` (before ringing, so a crash cannot loop forever), then the
scheduler settles the occurrence:

* one-shot: :meth:`mark_delivered` -> ``done`` or :meth:`mark_missed` -> ``missed``
* recurring: :meth:`reschedule` -> ``pending`` with a new ``due_at``/``next_try_at``
  and ``attempts`` reset.

Deleting a reminder is a hard ``DELETE``; finished (``done``/``missed``) rows are
kept until :meth:`purge_finished` removes them.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from .models import Reminder

T = TypeVar("T")

_SELECT = "SELECT * FROM reminders"
_DAY = 86_400


class ReminderStore:
    """Async wrapper around the ``reminders`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    # -- sync plumbing -------------------------------------------------------
    def _run(self, operation: Callable[[], T], *, write: bool) -> T:
        """Run ``operation`` under the lock, committing (or rolling back) writes."""
        with self._lock:
            try:
                result = operation()
            except BaseException:
                if write:
                    self._conn.rollback()
                raise
            if write:
                self._conn.commit()
            return result

    def _row(self, reminder_id: int) -> Reminder | None:
        """Fetch one row; the caller must already hold the lock."""
        row = self._conn.execute(f"{_SELECT} WHERE id = ?", (reminder_id,)).fetchone()
        return Reminder.from_row(row) if row is not None else None

    # -- rows -> objects -----------------------------------------------------
    def _add(
        self,
        message: str,
        due_at: int,
        tz: str,
        phone: str,
        repeat: str,
        until: int | None,
        status: str,
        next_try_at: int | None,
        created_at: int | None,
    ) -> Reminder:
        def operation() -> Reminder:
            now = int(time.time()) if created_at is None else int(created_at)
            first_try = int(due_at) if next_try_at is None else int(next_try_at)
            cursor = self._conn.execute(
                "INSERT INTO reminders"
                " (message, due_at, tz, repeat, until, phone, status, attempts,"
                "  next_try_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (message, int(due_at), tz, repeat, until, phone, status, first_try, now),
            )
            row = self._row(cursor.lastrowid)
            assert row is not None  # just inserted
            return row

        return self._run(operation, write=True)

    def _list(self, status: str | None) -> list[Reminder]:
        def operation() -> list[Reminder]:
            if status is None:
                rows = self._conn.execute(f"{_SELECT} ORDER BY id").fetchall()
            else:
                rows = self._conn.execute(
                    f"{_SELECT} WHERE status = ? ORDER BY id", (status,)
                ).fetchall()
            return [Reminder.from_row(row) for row in rows]

        return self._run(operation, write=False)

    def _next_due(self) -> float | None:
        def operation() -> float | None:
            row = self._conn.execute(
                "SELECT MIN(next_try_at) AS due FROM reminders WHERE status = 'pending'"
            ).fetchone()
            return None if row["due"] is None else float(row["due"])

        return self._run(operation, write=False)

    def _claim_due(self, now: float) -> list[Reminder]:
        def operation() -> list[Reminder]:
            rows = self._conn.execute(
                f"{_SELECT} WHERE status = 'pending' AND next_try_at <= ?"
                " ORDER BY next_try_at, id",
                (int(now),),
            ).fetchall()
            return [Reminder.from_row(row) for row in rows]

        return self._run(operation, write=False)

    def _mark_attempt(self, reminder_id: int, next_try_at: int | None) -> Reminder | None:
        def operation() -> Reminder | None:
            if next_try_at is None:
                self._conn.execute(
                    "UPDATE reminders SET attempts = attempts + 1 WHERE id = ?",
                    (reminder_id,),
                )
            else:
                self._conn.execute(
                    "UPDATE reminders SET attempts = attempts + 1, next_try_at = ? WHERE id = ?",
                    (int(next_try_at), reminder_id),
                )
            return self._row(reminder_id)

        return self._run(operation, write=True)

    def _set_next_try(self, reminder_id: int, next_try_at: int) -> Reminder | None:
        def operation() -> Reminder | None:
            self._conn.execute(
                "UPDATE reminders SET next_try_at = ? WHERE id = ?",
                (int(next_try_at), reminder_id),
            )
            return self._row(reminder_id)

        return self._run(operation, write=True)

    def _set_status(self, reminder_id: int, status: str) -> Reminder | None:
        def operation() -> Reminder | None:
            self._conn.execute(
                "UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id)
            )
            return self._row(reminder_id)

        return self._run(operation, write=True)

    def _reschedule(self, reminder_id: int, next_at: int) -> Reminder | None:
        def operation() -> Reminder | None:
            self._conn.execute(
                "UPDATE reminders SET due_at = ?, next_try_at = ?, attempts = 0,"
                " status = 'pending' WHERE id = ?",
                (int(next_at), int(next_at), reminder_id),
            )
            return self._row(reminder_id)

        return self._run(operation, write=True)

    def _purge_finished(self, keep_days: float, now: float | None) -> int:
        def operation() -> int:
            reference = time.time() if now is None else now
            cutoff = int(reference - keep_days * _DAY)
            cursor = self._conn.execute(
                "DELETE FROM reminders WHERE status IN ('done', 'missed') AND next_try_at < ?",
                (cutoff,),
            )
            return cursor.rowcount

        return self._run(operation, write=True)

    # -- async API -----------------------------------------------------------
    async def add(
        self,
        message: str,
        due_at: int,
        *,
        tz: str,
        phone: str,
        repeat: str = "none",
        until: int | None = None,
        status: str = "pending",
        next_try_at: int | None = None,
        created_at: int | None = None,
    ) -> Reminder:
        """Insert a reminder and return it with its assigned ``id``.

        ``next_try_at`` defaults to ``due_at``; ``created_at`` defaults to now.
        Both can be passed explicitly for deterministic tests.
        """
        return await asyncio.to_thread(
            self._add,
            message,
            due_at,
            tz,
            phone,
            repeat,
            until,
            status,
            next_try_at,
            created_at,
        )

    async def list(self, status: str | None = "pending") -> list[Reminder]:
        """Return reminders ordered by id. ``status=None`` returns every status."""
        return await asyncio.to_thread(self._list, status)

    async def get(self, reminder_id: int) -> Reminder | None:
        return await asyncio.to_thread(
            self._run, lambda: self._row(reminder_id), write=False
        )

    async def delete(self, reminder_id: int) -> bool:
        """Hard-delete a reminder. Returns ``False`` if it did not exist."""

        def operation() -> bool:
            cursor = self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            return cursor.rowcount > 0

        return await asyncio.to_thread(self._run, operation, write=True)

    async def next_due(self) -> float | None:
        """Earliest ``next_try_at`` among pending reminders, or ``None`` if none."""
        return await asyncio.to_thread(self._next_due)

    async def claim_due(self, now: float) -> list[Reminder]:
        """Pending reminders whose ``next_try_at <= now``, earliest first.

        This is a read: the scheduler records the attempt with :meth:`mark_attempt`
        before dialling. The single scheduler task is the only claimer, so no
        intermediate "calling" state is needed.
        """
        return await asyncio.to_thread(self._claim_due, now)

    async def mark_attempt(
        self, reminder_id: int, next_try_at: int | None = None
    ) -> Reminder | None:
        """Increment the attempt counter; optionally move ``next_try_at``.

        ``next_try_at=None`` leaves the current schedule in place (used right
        before ringing). Passing a time records the retry delay.
        """
        return await asyncio.to_thread(self._mark_attempt, reminder_id, next_try_at)

    async def set_next_try(self, reminder_id: int, next_try_at: int) -> Reminder | None:
        """Move ``next_try_at`` without touching ``attempts``.

        Used by the scheduler for the "phone busy, try later" postponement and to
        re-plan a retry, so an actual dial is the only thing that increments the
        attempt counter.
        """
        return await asyncio.to_thread(self._set_next_try, reminder_id, next_try_at)

    async def mark_delivered(self, reminder_id: int) -> Reminder | None:
        """Mark a (one-shot) reminder ``done``."""
        return await asyncio.to_thread(self._set_status, reminder_id, "done")

    async def mark_missed(self, reminder_id: int) -> Reminder | None:
        """Mark a reminder ``missed`` after the final failed attempt."""
        return await asyncio.to_thread(self._set_status, reminder_id, "missed")

    async def reschedule(self, reminder_id: int, next_at: int) -> Reminder | None:
        """Advance a recurring reminder to its next occurrence.

        Sets ``due_at`` and ``next_try_at`` to ``next_at``, resets ``attempts``
        and puts the reminder back to ``pending``.
        """
        return await asyncio.to_thread(self._reschedule, reminder_id, next_at)

    async def purge_finished(self, keep_days: float, now: float | None = None) -> int:
        """Delete ``done``/``missed`` rows older than the retention window.

        A row is old when its ``next_try_at`` is before ``now - keep_days``
        (``now`` defaults to the current time, overridable for tests). Pending
        and cancelled reminders are never touched. Returns the number deleted.
        """
        return await asyncio.to_thread(self._purge_finished, keep_days, now)
