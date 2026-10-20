"""Background scheduler: rings a phone when a reminder becomes due.

One asyncio task owns the loop. It wakes when the soonest ``next_try_at`` is
reached, when a reminder is created/deleted (:meth:`ReminderScheduler.wake`, wired
to the tools' ``on_change``) or after a 60 s safety timeout. Due reminders are
claimed and each gets its own :meth:`deliver` task so a slow call never blocks the
others.

Delivery confirmation comes from the *handler*: the metadata handed to
``server.originate`` carries an ``on_opening_done`` callback that the assistant
invokes once the opening has been played. That callback calls
:meth:`ReminderScheduler.delivered`, which releases the waiting :meth:`deliver`
task. If the call drops before then, the occurrence follows the retry path.

The attempt counter is incremented *before* the phone rings (crash safety: a
restart backs off instead of dialling in a loop). To make that safe we persist an
optimistic retry time in the same update; a failed attempt therefore needs no
second increment. The busy postponement uses
:meth:`~agent_sip.reminders.store.ReminderStore.set_next_try`, which does not
count an attempt.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import RemindersConfig
from .models import Reminder
from .recurrence import next_occurrence
from .store import ReminderStore

log = logging.getLogger(__name__)

_BUSY_POSTPONE = 30.0       # seconds to wait when the target phone is already in a call
_SAFETY_TIMEOUT = 60.0      # cap on how long the loop sleeps, in case a wake is missed
_MAX_ADVANCE = 10_000       # bound on the "skip forward to a future occurrence" loop


class ReminderScheduler:
    """Drive pending reminders to phone calls, one asyncio task per scheduler."""

    def __init__(
        self,
        store: ReminderStore,
        cfg: RemindersConfig,
        server=None,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.cfg = cfg
        self.server = server
        self._now = now
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._in_flight: set[int] = set()
        self._deliveries: set[asyncio.Task] = set()
        self._delivery_events: dict[int, asyncio.Event] = {}

    # -- public API ----------------------------------------------------------
    def set_server(self, server) -> None:
        """Attach the :class:`SipServer` once it has been constructed."""
        self.server = server

    def now(self) -> float:
        return self._now()

    def wake(self) -> None:
        """Ask the loop to re-plan (called after create/delete). Safe from any task."""
        self._wake.set()

    async def start(self) -> None:
        """Start the background loop (must have a server attached)."""
        if self.server is None:
            raise RuntimeError("ReminderScheduler.start() needs a server; call set_server()")
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())
        self._task.add_done_callback(self._on_task_done)

    async def stop(self) -> None:
        """Cancel the loop and any in-flight deliveries, then wait for them."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for task in list(self._deliveries):
            task.cancel()
        if self._deliveries:
            await asyncio.gather(*self._deliveries, return_exceptions=True)
        self._deliveries.clear()
        self._delivery_events.clear()
        self._in_flight.clear()

    async def delivered(self, reminder_id: int) -> None:
        """Confirm that the opening for ``reminder_id`` was played to the caller."""
        event = self._delivery_events.get(reminder_id)
        if event is not None:
            event.set()

    # -- loop ----------------------------------------------------------------
    async def _run(self) -> None:
        await self._recover()
        while True:
            t = await self.store.next_due()
            timeout = _SAFETY_TIMEOUT
            if t is not None:
                timeout = min(_SAFETY_TIMEOUT, max(0.0, t - self.now()))
            if timeout > 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout)
            self._wake.clear()
            for reminder in await self.store.claim_due(self.now()):
                self._spawn(reminder)
            await asyncio.sleep(0)   # let deliveries record their attempt

    def _on_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error("reminder scheduler crashed", exc_info=exc)

    def _spawn(self, reminder: Reminder, *, late: bool = False) -> None:
        if reminder.id in self._in_flight:
            return
        self._in_flight.add(reminder.id)
        task = asyncio.create_task(self._deliver_guarded(reminder, late=late))
        self._deliveries.add(task)
        task.add_done_callback(self._deliveries.discard)

    async def _deliver_guarded(self, reminder: Reminder, *, late: bool) -> None:
        try:
            await self.deliver(reminder, late=late)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("delivery of reminder %s failed", reminder.id)
            self._in_flight.discard(reminder.id)

    async def _recover(self) -> None:
        """Handle reminders that came due while the process was down.

        Within ``max_late`` they fire immediately (with late wording); older ones
        are marked missed (recurring reminders advance to the next future
        occurrence). This is what keeps a long downtime from becoming a call storm.
        """
        now = self.now()
        for reminder in await self.store.claim_due(now):
            late_by = now - reminder.next_try_at
            if late_by <= self.cfg.max_late:
                self._spawn(reminder, late=True)
            else:
                await self._expire(reminder)
        await asyncio.sleep(0)   # let recoveries record their attempt

    # -- one delivery --------------------------------------------------------
    async def deliver(self, reminder: Reminder, *, late: bool = False) -> None:
        """Ring the reminder's phone once and settle the outcome."""
        try:
            if self._phone_busy(reminder.phone):
                await self.store.set_next_try(
                    reminder.id, int(self.now() + _BUSY_POSTPONE)
                )
                log.info("reminder %s postponed: %s is busy", reminder.id, reminder.phone)
                return

            # Persist the attempt *before* ringing. The same update records an
            # optimistic retry time so a crash/restart backs off instead of looping.
            now = self.now()
            updated = await self.store.mark_attempt(
                reminder.id, int(now + self.cfg.retry_interval)
            )
            attempts = updated.attempts if updated is not None else 1

            event = asyncio.Event()
            self._delivery_events[reminder.id] = event
            metadata = self._metadata(reminder, late=late)
            try:
                call = await self.server.originate(reminder.phone, metadata=metadata)
            except Exception:
                log.exception("originate failed for reminder %s", reminder.id)
                await self._settle_failed(reminder, attempts)
                return

            await self._race(call.answered, call.ended, self.cfg.ring_timeout)
            if not call.answered.is_set():
                await call.hangup()
                await self._settle_failed(reminder, attempts)
                return

            await self._race(event, call.ended, None)
            if event.is_set():
                await self._settle_delivered(reminder)
            else:
                log.info("reminder %s call ended before the opening was delivered", reminder.id)
                await self._settle_failed(reminder, attempts)
        finally:
            self._delivery_events.pop(reminder.id, None)
            self._in_flight.discard(reminder.id)

    def _phone_busy(self, phone: str) -> bool:
        if self.server is None:
            return False
        return any(call.phone == phone and call.state != "ended"
                   for call in self.server.calls.values())

    async def _settle_delivered(self, reminder: Reminder) -> None:
        if reminder.repeat == "none":
            await self.store.mark_delivered(reminder.id)
            return
        nxt = self._next_future(reminder)
        if nxt is None:
            await self.store.mark_delivered(reminder.id)  # recurrence series finished
        else:
            await self.store.reschedule(reminder.id, nxt)

    async def _settle_failed(self, reminder: Reminder, attempts: int) -> None:
        # The pre-ring attempt already persisted an optimistic retry time; move it to
        # now + retry_interval without counting another attempt (set_next_try).
        if attempts < self.cfg.retry_attempts:
            await self.store.set_next_try(
                reminder.id, int(self.now() + self.cfg.retry_interval)
            )
            return
        await self._expire(reminder)

    async def _expire(self, reminder: Reminder) -> None:
        """Give up on the current occurrence (mark missed or advance the series)."""
        if reminder.repeat == "none":
            await self.store.mark_missed(reminder.id)
            return
        nxt = self._next_future(reminder)
        if nxt is None:
            await self.store.mark_missed(reminder.id)
        else:
            await self.store.reschedule(reminder.id, nxt)

    def _next_future(self, reminder: Reminder) -> int | None:
        """Next occurrence strictly after now, keeping the local wall-clock time."""
        now = self.now()
        after = reminder.due_at
        nxt = next_occurrence(after, reminder.repeat, reminder.tz, reminder.until)
        for _ in range(_MAX_ADVANCE):
            if nxt is None or nxt > now:
                return nxt
            after = nxt
            nxt = next_occurrence(after, reminder.repeat, reminder.tz, reminder.until)
        return nxt  # pragma: no cover - defensive, same bound as recurrence.py

    # -- metadata / opening --------------------------------------------------
    def _metadata(self, reminder: Reminder, *, late: bool) -> dict:
        async def on_opening_done() -> None:
            await self.delivered(reminder.id)

        return {
            "reminder": reminder,
            "opening": self._opening_text(reminder, late=late),
            "opening_fallback": reminder.message,
            "on_opening_done": on_opening_done,
        }

    def _opening_text(self, reminder: Reminder, *, late: bool) -> str:
        zone = ZoneInfo(reminder.tz) if reminder.tz else None
        due = datetime.fromtimestamp(reminder.due_at, zone).strftime("%H:%M")
        current = datetime.fromtimestamp(self.now(), zone).strftime("%H:%M")
        message = reminder.message.replace("\\", "\\\\").replace('"', '\\"')
        if late:
            timing = (f"It was due at {due} and it is now {current}, so it is late. "
                      "Mention that briefly.")
        else:
            timing = f"Scheduled for {due} (now {current})."
        return (f'[REMINDER] The user asked to be reminded: "{message}". '
                f'{timing} Tell them now, briefly.')

    @staticmethod
    async def _race(first: asyncio.Event, second: asyncio.Event,
                    timeout: float | None) -> None:
        """Wait until either event is set or ``timeout`` elapses."""
        waiters = [asyncio.ensure_future(first.wait()), asyncio.ensure_future(second.wait())]
        try:
            await asyncio.wait(
                waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for waiter in waiters:
                waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
