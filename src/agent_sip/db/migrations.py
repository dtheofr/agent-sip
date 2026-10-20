"""Ordered SQLite migrations shared by the application.

Each entry is applied once, in list order, by :func:`agent_sip.db.migrate`. A
database has a single ``PRAGMA user_version``, so there is one global ordered
list: features append their migration strings here (a later feature's migration
is simply a later list entry). Never reorder or edit an already-shipped entry.
"""

MIGRATIONS: list[str] = [
    # Migration 1: reminders table + due index (schema from docs/reminders-plan.md).
    """
CREATE TABLE reminders (
  id           INTEGER PRIMARY KEY,
  message      TEXT NOT NULL,           -- what to remind, as written by the agent
  due_at       INTEGER NOT NULL,        -- UTC epoch seconds of the NEXT occurrence
  tz           TEXT NOT NULL,           -- IANA zone used for recurrence math / speaking times
  repeat       TEXT NOT NULL DEFAULT 'none',
  until        INTEGER,                 -- optional end of recurrence (epoch)
  phone        TEXT NOT NULL,           -- name from [[phones]]
  status       TEXT NOT NULL DEFAULT 'pending',   -- pending | done | missed | cancelled
  attempts     INTEGER NOT NULL DEFAULT 0,        -- attempts for the current occurrence
  next_try_at  INTEGER NOT NULL,        -- scheduler's next action (= due_at, or retry time)
  created_at   INTEGER NOT NULL
);
CREATE INDEX reminders_due ON reminders(status, next_try_at);
""",
]
