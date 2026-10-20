"""LLM tools for reminders: create, list and delete by voice.

The tools are *closures over one call's context*, not ``@tool``-registered globals:
``create_reminder`` defaults its target to the phone of the current call. ``__main__``
builds a fresh :class:`~agent_sip.agent.tools.ToolRegistry` per call with these tools
bound to ``call.phone``.

``when`` and ``until`` are absolute *local* ISO 8601 datetimes (the LLM resolves
relative times with ``get_current_datetime`` first). They are interpreted in the
configured timezone (empty = system local) and stored as UTC epoch seconds.

The optional ``on_change`` callback fires after a successful create/delete. It is the
hook Slice 5 uses to wake the scheduler; the tools never touch the scheduler directly.
"""
from __future__ import annotations

import os
import time
import zoneinfo
from collections.abc import Callable, Sequence
from datetime import datetime, tzinfo
from pathlib import Path

from ..agent.tools import Tool
from ..config import PhoneConfig
from .store import ReminderStore

REPEATS = ("none", "daily", "weekdays", "weekly", "monthly")

_CREATE_PARAMS = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "What to remind the user about."},
        "when": {"type": "string",
                 "description": "Absolute local ISO 8601 datetime, e.g. 2025-06-01T08:30."},
        "repeat": {"type": "string", "enum": list(REPEATS),
                   "description": "Recurrence; defaults to none."},
        "until": {"type": "string",
                  "description": "Optional local ISO 8601 end of the recurrence."},
        "phone": {"type": "string",
                  "description": "Target phone name; defaults to the current call's phone."},
    },
    "required": ["message", "when"],
}

_LIST_PARAMS = {
    "type": "object",
    "properties": {"include_past": {
        "type": "boolean",
        "description": "Also show finished (done/missed) reminders, not just pending ones."}},
}

_DELETE_PARAMS = {
    "type": "object",
    "properties": {"id": {"type": "integer", "description": "Reminder id to delete."}},
    "required": ["id"],
}


def _local_iana() -> str:
    """Best-effort IANA name of the system timezone, or ``""`` if unknown."""
    name = os.environ.get("TZ", "")
    if name:
        try:
            zoneinfo.ZoneInfo(name)
            return name
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            pass
    try:
        resolved = Path("/etc/localtime").resolve()
    except OSError:
        return ""
    parts = resolved.parts
    if "zoneinfo" in parts:
        candidate = "/".join(parts[parts.index("zoneinfo") + 1:])
        try:
            zoneinfo.ZoneInfo(candidate)
            return candidate
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            pass
    return ""


def _resolve_tz(tz: str) -> tuple[tzinfo, str]:
    """Return the tzinfo to interpret naive times in and the key to persist."""
    if tz:
        return zoneinfo.ZoneInfo(tz), tz
    key = _local_iana()
    if key:
        return zoneinfo.ZoneInfo(key), key
    return datetime.now().astimezone().tzinfo, ""


def _parse_local(value: str, zone: tzinfo) -> int:
    """Parse a local ISO datetime into a UTC epoch, interpreting naive values in ``zone``."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"invalid datetime {value!r}; use ISO 8601 like 2025-06-01T08:30"
        ) from e
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    return int(moment.timestamp())


def _spoken(epoch: int, tz: str) -> str:
    zone, _ = _resolve_tz(tz)
    return datetime.fromtimestamp(epoch, zone).strftime("%A %Y-%m-%d %H:%M")


def _resolve_phone(
    explicit: str | None,
    call_phone: str | None,
    default_phone: str,
    phones: Sequence[PhoneConfig],
) -> str:
    """explicit > current call > configured default > first ``[[phones]]`` entry."""
    names = [p.name for p in phones]
    for candidate in (explicit, call_phone, default_phone):
        if candidate:
            if candidate not in names:
                known = ", ".join(names) or "none"
                raise ValueError(f"unknown phone {candidate!r}; known phones: {known}")
            return candidate
    if names:
        return names[0]
    raise ValueError("no phone configured; add a [[phones]] entry or set default_phone")


def reminder_tools(
    store: ReminderStore,
    *,
    tz: str = "",
    default_phone: str = "",
    phones: Sequence[PhoneConfig] = (),
    call_phone: str | None = None,
    on_change: Callable[[], None] | None = None,
    now: Callable[[], float] = time.time,
) -> list[Tool]:
    """Build the reminder tools bound to one call.

    ``store`` is the shared :class:`ReminderStore`; ``tz``/``default_phone`` come from
    ``[tools.reminders]``, ``phones`` from ``[[phones]]`` and ``call_phone`` from the
    call being handled. ``on_change`` is called after a successful create/delete (used
    by the scheduler to wake). ``now`` is injectable for deterministic tests.
    """
    zone, stored_tz = _resolve_tz(tz)
    known_phones = list(phones)

    async def create_reminder(
        message: str,
        when: str,
        repeat: str = "none",
        until: str | None = None,
        phone: str | None = None,
    ) -> str:
        repeat = repeat or "none"
        if repeat not in REPEATS:
            raise ValueError(f"unknown repeat {repeat!r}; use one of {', '.join(REPEATS)}")
        target = _resolve_phone(phone, call_phone, default_phone, known_phones)
        current = int(now())
        due_at = _parse_local(when, zone)
        if due_at < current:
            raise ValueError(f"{when!r} is in the past; use a future time")
        until_at = None
        if until:
            until_at = _parse_local(until, zone)
            if until_at < due_at:
                raise ValueError("until is before when")
        reminder = await store.add(
            message,
            due_at,
            tz=stored_tz,
            phone=target,
            repeat=repeat,
            until=until_at,
            next_try_at=due_at,
            created_at=current,
        )
        if on_change is not None:
            on_change()
        return f"created reminder {reminder.id} for {_spoken(due_at, stored_tz)}"

    async def list_reminders(include_past: bool = False) -> str:
        reminders = await store.list(None if include_past else "pending")
        if not reminders:
            return "no reminders"
        return "\n".join(
            f"#{r.id} [{r.status}] {r.message} - {_spoken(r.due_at, r.tz)} ({r.repeat})"
            for r in reminders
        )

    async def delete_reminder(id: int) -> str:
        if not await store.delete(int(id)):
            return f"error: no reminder with id {id}"
        if on_change is not None:
            on_change()
        return f"deleted reminder {id}"

    return [
        Tool(
            "create_reminder",
            "Create a reminder. Times are absolute local ISO 8601; call "
            "get_current_datetime first to resolve relative times.",
            create_reminder,
            _CREATE_PARAMS,
        ),
        Tool(
            "list_reminders",
            "List pending reminders; set include_past to also show done/missed ones.",
            list_reminders,
            _LIST_PARAMS,
        ),
        Tool(
            "delete_reminder",
            "Delete a reminder by id. Safe to call with an unknown id.",
            delete_reminder,
            _DELETE_PARAMS,
        ),
    ]
