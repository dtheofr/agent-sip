"""Scheduler + pickup-flow tests (Slice 5).

A fake server records ``originate`` calls and lets tests drive ``answered`` /
``ended``; the clock is injectable and intervals are tiny, so nothing here waits
on wall-clock minutes.
"""
import array
import asyncio
import json
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from agent_sip.agent import OpenAIChatAgent, ToolRegistry
from agent_sip.assistant import AssistantHandler
from agent_sip.config import AudioConfig, LlmConfig, PhoneConfig, RemindersConfig
from agent_sip.db import connect, migrate
from agent_sip.db.migrations import MIGRATIONS
from agent_sip.reminders.recurrence import next_occurrence
from agent_sip.reminders.scheduler import ReminderScheduler
from agent_sip.reminders.store import ReminderStore
from agent_sip.reminders.tools import reminder_tools

NOW = 1_800_000_000.0


class Clock:
    def __init__(self, t: float = NOW) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeCall:
    def __init__(self, phone: str, metadata: dict | None = None) -> None:
        self.phone = phone
        self.metadata = metadata or {}
        self.state = "ringing"
        self.answered = asyncio.Event()
        self.ended = asyncio.Event()
        self.hangups = 0

    async def hangup(self) -> None:
        self.hangups += 1
        self.state = "ended"
        self.ended.set()


class FakeServer:
    def __init__(self) -> None:
        self.calls: dict[int, FakeCall] = {}
        self.originated: list[FakeCall] = []
        self.on_originate = None

    async def originate(self, phone: str, metadata: dict | None = None) -> FakeCall:
        call = FakeCall(phone, metadata)
        self.calls[id(call)] = call
        self.originated.append(call)
        if self.on_originate is not None:
            await self.on_originate(call)
        return call

    def answer(self, call: FakeCall) -> None:
        call.state = "active"
        call.answered.set()

    def end_call(self, call: FakeCall) -> None:
        call.state = "ended"
        call.ended.set()
        self.calls.pop(id(call), None)

    def add_active_call(self, phone: str) -> FakeCall:
        call = FakeCall(phone)
        self.answer(call)
        self.calls[id(call)] = call
        return call


async def wait_for(predicate, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition was not met in time")
        await asyncio.sleep(0.005)


async def wait_status(store: ReminderStore, reminder_id: int, status: str,
                      timeout: float = 2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        row = await store.get(reminder_id)
        if row is not None and row.status == status:
            return row
        if loop.time() > deadline:
            raise AssertionError(f"reminder {reminder_id} never became {status!r}")
        await asyncio.sleep(0.01)


def iso(epoch: float, tz: str = "UTC") -> str:
    return datetime.fromtimestamp(epoch, ZoneInfo(tz)).strftime("%Y-%m-%dT%H:%M")


class SchedulerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "sched.db")
        migrate(self.conn, MIGRATIONS)
        self.store = ReminderStore(self.conn)
        self.clock = Clock()
        self.server = FakeServer()
        self.cfg = RemindersConfig(ring_timeout=1.0, retry_attempts=3,
                                   retry_interval=5.0, max_late=3600.0, timezone="UTC")
        self.scheduler = ReminderScheduler(self.store, self.cfg, self.server, now=self.clock)

    async def asyncTearDown(self):
        await self.scheduler.stop()
        self.conn.close()
        self._tmp.cleanup()

    async def add(self, **kwargs):
        kwargs.setdefault("message", "call the dentist")
        kwargs.setdefault("due_at", int(self.clock.t))
        kwargs.setdefault("tz", "UTC")
        kwargs.setdefault("phone", "phone")
        return await self.store.add(**kwargs)

    async def drive(self, reminder, action):
        """Run one ``deliver`` and let ``action`` drive the originated call."""
        before = len(self.server.originated)
        task = asyncio.create_task(self.scheduler.deliver(reminder))
        await wait_for(lambda: len(self.server.originated) == before + 1)
        call = self.server.originated[-1]
        await action(call)
        await asyncio.wait_for(task, 2)
        return call

    # -- delivery ------------------------------------------------------------
    async def test_due_reminder_originates_once_with_phone_and_metadata(self):
        reminder = await self.add()
        await self.scheduler.start()
        await wait_for(lambda: len(self.server.originated) == 1)

        call = self.server.originated[0]
        self.assertEqual(call.phone, "phone")
        self.assertEqual(call.metadata["reminder"].id, reminder.id)
        self.assertEqual(call.metadata["opening_fallback"], "call the dentist")
        self.assertIn("call the dentist", call.metadata["opening"])
        self.assertTrue(call.metadata["opening"].startswith("[REMINDER]"))
        self.assertTrue(callable(call.metadata["on_opening_done"]))

        # already in flight: advancing the clock must not dial the same occurrence twice
        self.clock.advance(self.cfg.retry_interval + 1)
        self.scheduler.wake()
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.server.originated), 1)

        self.server.answer(call)
        await self.scheduler.delivered(reminder.id)
        row = await wait_status(self.store, reminder.id, "done")
        self.assertEqual(row.attempts, 1)

    async def test_answered_and_delivered_one_shot_is_done(self):
        reminder = await self.add()
        await self.drive(reminder, self._answer_and_deliver(reminder.id))
        row = await self.store.get(reminder.id)
        self.assertEqual((row.status, row.attempts), ("done", 1))

    async def test_answered_and_delivered_recurring_advances_and_resets(self):
        due = int(self.clock.t)
        reminder = await self.add(repeat="daily", due_at=due, next_try_at=due)
        await self.drive(reminder, self._answer_and_deliver(reminder.id))
        row = await self.store.get(reminder.id)
        self.assertEqual((row.status, row.attempts), ("pending", 0))
        self.assertEqual(row.due_at, next_occurrence(due, "daily", "UTC"))
        self.assertEqual(row.next_try_at, row.due_at)

    async def test_not_answered_retries_then_marks_missed(self):
        reminder = await self.add()
        await self.drive(reminder, self._end_call)
        row = await self.store.get(reminder.id)
        self.assertEqual((row.status, row.attempts), ("pending", 1))
        self.assertEqual(row.next_try_at, int(self.clock.t + self.cfg.retry_interval))

        await self.drive(await self.store.get(reminder.id), self._end_call)
        await self.drive(await self.store.get(reminder.id), self._end_call)
        row = await self.store.get(reminder.id)
        self.assertEqual((row.status, row.attempts), ("missed", 3))

    async def test_not_answered_recurring_advances(self):
        due = int(self.clock.t)
        reminder = await self.add(repeat="daily", due_at=due, next_try_at=due)
        self.cfg.retry_attempts = 2
        await self.drive(reminder, self._end_call)
        await self.drive(await self.store.get(reminder.id), self._end_call)
        row = await self.store.get(reminder.id)
        self.assertEqual((row.status, row.attempts), ("pending", 0))
        self.assertEqual(row.due_at, next_occurrence(due, "daily", "UTC"))

    async def test_ring_timeout_hangs_up_and_counts_attempt(self):
        self.cfg.ring_timeout = 0.05
        reminder = await self.add()
        before = len(self.server.originated)
        task = asyncio.create_task(self.scheduler.deliver(reminder))
        await wait_for(lambda: len(self.server.originated) == before + 1)
        call = self.server.originated[-1]
        await asyncio.wait_for(task, 2)

        self.assertEqual(call.hangups, 1)
        row = await self.store.get(reminder.id)
        self.assertEqual(row.attempts, 1)
        self.assertFalse(call.answered.is_set())

    async def test_dropped_before_opening_is_retried(self):
        reminder = await self.add()

        async def drop(call):
            self.server.answer(call)
            self.server.end_call(call)   # hangs up before on_opening_done

        await self.drive(reminder, drop)
        row = await self.store.get(reminder.id)
        self.assertEqual((row.status, row.attempts), ("pending", 1))
        self.assertEqual(row.next_try_at, int(self.clock.t + self.cfg.retry_interval))

    async def test_phone_busy_postpones_without_counting_attempt(self):
        self.server.add_active_call("phone")
        reminder = await self.add()
        await self.scheduler.deliver(reminder)

        self.assertEqual(self.server.originated, [])
        row = await self.store.get(reminder.id)
        self.assertEqual(row.attempts, 0)
        self.assertEqual(row.next_try_at, int(self.clock.t + 30))

    # -- loop: wake / create / delete ----------------------------------------
    async def test_create_wakes_and_deleted_reminder_never_rings(self):
        tools = reminder_tools(
            self.store, tz="UTC", phones=[PhoneConfig(name="phone")],
            on_change=self.scheduler.wake, now=self.clock,
        )
        registry = ToolRegistry(tools)
        await self.scheduler.start()

        await registry.call("create_reminder", json.dumps(
            {"message": "far away", "when": iso(self.clock.t + 1000)}))
        rows = await self.store.list(None)
        self.assertEqual(len(rows), 1)
        reminder_id = rows[0].id

        # Without the wake this would be stuck in the 60 s safety sleep.
        self.clock.advance(1001)
        self.scheduler.wake()
        await wait_for(lambda: len(self.server.originated) == 1)
        self.server.answer(self.server.originated[0])
        await self.scheduler.delivered(reminder_id)
        await wait_status(self.store, reminder_id, "done")

        # A different reminder deleted before its time is re-planned away.
        await registry.call("create_reminder", json.dumps(
            {"message": "deleted", "when": iso(self.clock.t + 1000)}))
        deleted_id = (await self.store.list(None))[0].id
        await registry.call("delete_reminder", json.dumps({"id": deleted_id}))
        self.clock.advance(1001)
        self.scheduler.wake()
        await asyncio.sleep(0.1)
        self.assertEqual(len(self.server.originated), 1)

    # -- startup recovery ----------------------------------------------------
    async def test_recovery_within_max_late_fires_with_late_wording(self):
        due = int(self.clock.t) - 120
        reminder = await self.add(due_at=due, next_try_at=due)
        await self.scheduler.start()
        await wait_for(lambda: len(self.server.originated) == 1)

        opening = self.server.originated[0].metadata["opening"]
        self.assertIn("late", opening.lower())
        self.assertIn("was due at", opening)

        self.server.answer(self.server.originated[0])
        await self.scheduler.delivered(reminder.id)
        await wait_status(self.store, reminder.id, "done")

    async def test_recovery_beyond_max_late_does_not_call(self):
        due = int(self.clock.t) - 7200
        one_shot = await self.add(message="old one", due_at=due, next_try_at=due)
        recurring = await self.add(message="old daily", due_at=due, next_try_at=due,
                                   repeat="daily")
        await self.scheduler.start()
        await asyncio.sleep(0.15)

        self.assertEqual(self.server.originated, [])
        self.assertEqual((await self.store.get(one_shot.id)).status, "missed")
        row = await self.store.get(recurring.id)
        self.assertEqual(row.status, "pending")
        self.assertGreater(row.due_at, int(self.clock.t))

    async def test_recovery_no_call_storm_for_many_stale_reminders(self):
        due = int(self.clock.t) - 10_000
        for i in range(5):
            await self.add(message=f"stale {i}", due_at=due, next_try_at=due)
        await self.scheduler.start()
        await asyncio.sleep(0.15)
        self.assertEqual(self.server.originated, [])
        self.assertEqual(len([r for r in await self.store.list("missed")]), 5)

    # -- crash safety / stop -------------------------------------------------
    async def test_attempt_is_persisted_before_ringing_and_restart_backs_off(self):
        reminder = await self.add()
        observed: list[int] = []

        async def observe(call):
            row = await self.store.get(reminder.id)
            observed.append(row.attempts)

        self.server.on_originate = observe
        await self.scheduler.start()
        await wait_for(lambda: len(self.server.originated) == 1)
        self.assertEqual(observed, [1])
        await self.scheduler.stop()

        # A fresh scheduler (simulated restart) must not immediately re-dial.
        restarted = FakeServer()
        scheduler2 = ReminderScheduler(self.store, self.cfg, restarted, now=self.clock)
        await scheduler2.start()
        await asyncio.sleep(0.15)
        self.assertEqual(restarted.originated, [])
        await scheduler2.stop()

    async def test_stop_cancels_in_flight_deliveries(self):
        await self.add()
        await self.scheduler.start()
        await wait_for(lambda: len(self.server.originated) == 1)

        await asyncio.wait_for(self.scheduler.stop(), 2)
        self.assertEqual(self.scheduler._in_flight, set())
        self.assertEqual(self.scheduler._deliveries, set())

    # -- helpers -------------------------------------------------------------
    def _answer_and_deliver(self, reminder_id):
        async def action(call):
            self.server.answer(call)
            await self.scheduler.delivered(reminder_id)
        return action

    async def _end_call(self, call):
        self.server.end_call(call)


# ---------------------------------------------------------------------------
# Pickup flow: AssistantHandler opening
# ---------------------------------------------------------------------------

class FakeTranscriber:
    def __init__(self, texts=()) -> None:
        self.texts = list(texts)

    async def transcribe(self, pcm, sample_rate: int = 8000) -> str:
        return self.texts.pop(0) if self.texts else ""


class FakeSynth:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> array.array:
        self.texts.append(text)
        return array.array("h", [1000] * 160)


class FakeAgent:
    def __init__(self, replies=(), fail: bool = False) -> None:
        self.replies = list(replies)
        self.fail = fail
        self.calls: list[str] = []

    async def respond(self, text: str) -> str:
        self.calls.append(text)
        if self.fail:
            raise RuntimeError("llm down")
        return self.replies.pop(0) if self.replies else ""


class HandlerCall:
    def __init__(self, metadata=None, frames=(), end_after_plays=None) -> None:
        self.call_id = "call-abcd1234"
        self.phone = "phone"
        self.metadata = dict(metadata or {})
        self.active = True
        self.state = "active"
        self.played: list[array.array] = []
        self._frames = list(frames)
        self.end_after_plays = end_after_plays

    async def play(self, pcm: array.array) -> bool:
        self.played.append(pcm)
        if self.end_after_plays is not None and len(self.played) >= self.end_after_plays:
            self.active = False
        return self.active

    def flush_input(self) -> None:
        pass

    async def read_frame(self, timeout: float = 0.1):
        if self._frames:
            return self._frames.pop(0)
        await asyncio.sleep(min(timeout, 0.01))
        return None


def opening_metadata(message: str = "call the dentist", on_done=None) -> dict:
    return {
        "opening": f'[REMINDER] The user asked to be reminded: "{message}". '
                   "Scheduled for 08:30 (now 08:31). Tell them now, briefly.",
        "opening_fallback": message,
        "on_opening_done": on_done,
    }


class OpeningHandlerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.audio = AudioConfig(vad="energy", barge_in=False, earcons=False,
                                 no_speech_timeout=0.05, silence_end=0.05, max_record=0.2)
        self.synth = FakeSynth()

    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "handler.db")
        migrate(self.conn, MIGRATIONS)
        self.store = ReminderStore(self.conn)

    async def asyncTearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def handler(self, agent, transcriber=None):
        return AssistantHandler(self.audio, transcriber or FakeTranscriber(), self.synth,
                                lambda call: agent, greeting="STATIC GREETING")

    async def test_opening_skips_static_greeting(self):
        delivered = asyncio.Event()

        async def on_done():
            delivered.set()

        agent = FakeAgent(replies=["On it."])
        call = HandlerCall(metadata=opening_metadata(on_done=on_done), end_after_plays=1)
        await asyncio.wait_for(self.handler(agent).on_call(call), 2)

        self.assertEqual(agent.calls[0], call.metadata["opening"])
        self.assertEqual(self.synth.texts, ["On it."])
        self.assertNotIn("STATIC GREETING", self.synth.texts)
        self.assertTrue(delivered.is_set())
        self.assertEqual(len(call.played), 1)

    async def test_opening_is_sent_to_llm_as_tagged_user_message(self):
        seen: list[dict] = []

        class LLM(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append(body)
                out = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), LLM)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        agent = OpenAIChatAgent(LlmConfig(base_url=f"http://127.0.0.1:{srv.server_port}"),
                                system_prompt="sys")
        call = HandlerCall(metadata=opening_metadata(), end_after_plays=1)
        await asyncio.wait_for(self.handler(agent).on_call(call), 3)

        opening = call.metadata["opening"]
        self.assertEqual(seen[-1]["messages"][-1], {"role": "user", "content": opening})
        self.assertEqual(seen[-1]["messages"][0], {"role": "system", "content": "sys"})

    async def test_llm_failure_falls_back_to_raw_reminder(self):
        delivered = asyncio.Event()

        def on_done():   # sync callback: must still work
            delivered.set()

        agent = FakeAgent(fail=True)
        call = HandlerCall(metadata=opening_metadata(on_done=on_done), end_after_plays=1)
        await asyncio.wait_for(self.handler(agent).on_call(call), 2)

        self.assertEqual(self.synth.texts, ["call the dentist"])
        self.assertTrue(delivered.is_set())

    async def test_opening_done_errors_do_not_break_the_call(self):
        def on_done():
            raise RuntimeError("callback boom")

        agent = FakeAgent(replies=["ok"])
        call = HandlerCall(metadata=opening_metadata(on_done=on_done), end_after_plays=1)
        await asyncio.wait_for(self.handler(agent).on_call(call), 2)
        self.assertEqual(self.synth.texts, ["ok"])

    async def test_conversation_continues_and_reminder_tools_stay_available(self):
        tools = reminder_tools(self.store, tz="UTC", phones=[PhoneConfig(name="phone")],
                               call_phone="phone")
        agent = FakeAgent(replies=["Opening reply", "Second reply"])
        agent.tools = ToolRegistry(tools)
        frames = [array.array("h", [20000] * 160) for _ in range(3)]
        call = HandlerCall(metadata=opening_metadata(), frames=frames, end_after_plays=2)
        handler = self.handler(agent, FakeTranscriber(["thanks"]))
        await asyncio.wait_for(handler.on_call(call), 2)

        self.assertEqual(agent.calls, [call.metadata["opening"], "thanks"])
        self.assertEqual(self.synth.texts, ["Opening reply", "Second reply"])

        # The per-call tools remain usable after the opening.
        self.assertEqual(await agent.tools.call("list_reminders", "{}"), "no reminders")
        created = await agent.tools.call("create_reminder", json.dumps(
            {"message": "again", "when": iso(NOW + 86_400)}))
        self.assertIn("created reminder", created)
        self.assertEqual(len(await self.store.list(None)), 1)


if __name__ == "__main__":
    unittest.main()
