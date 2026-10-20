"""Tests for the reminder tools, per-call wiring and validation (Slice 3)."""
import asyncio
import json
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from agent_sip.__main__ import build_app
from agent_sip.agent import OpenAIChatAgent, ToolRegistry
from agent_sip.config import Config, LlmConfig, PhoneConfig
from agent_sip.db import connect, migrate
from agent_sip.db.migrations import MIGRATIONS
from agent_sip.reminders.store import ReminderStore
from agent_sip.reminders.tools import reminder_tools

# 2027-01-15 08:00:00 UTC - a fixed "now" so the tests never depend on the clock.
NOW = 1_800_000_000


def _iso(epoch: float, tz: str = "UTC") -> str:
    return datetime.fromtimestamp(epoch, ZoneInfo(tz)).strftime("%Y-%m-%dT%H:%M")


def _future(seconds: int = 86_400) -> str:
    """A local-system ISO datetime safely in the future (for real-clock wiring tests)."""
    return (datetime.now().astimezone() + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M")


class FakeCall:
    def __init__(self, phone=None, cid="call-1"):
        self.call_id = cid
        self.phone = phone
        self.active = False
        self.metadata = {}


class ReminderToolsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "tools.db"
        self.conn = connect(self.path)
        migrate(self.conn, MIGRATIONS)
        self.store = ReminderStore(self.conn)

    async def asyncTearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def tools(self, **kwargs):
        kwargs.setdefault("tz", "UTC")
        kwargs.setdefault("now", lambda: float(NOW))
        kwargs.setdefault("phones", [PhoneConfig(name="socotel")])
        return reminder_tools(self.store, **kwargs)

    async def call(self, tools, name, args):
        return await ToolRegistry(tools).call(name, json.dumps(args))

    async def test_create_returns_id_and_spoken_time(self):
        tools = self.tools()
        out = await self.call(tools, "create_reminder",
                              {"message": "call the dentist", "when": "2027-01-16T08:30"})
        self.assertIn("created reminder 1", out)
        self.assertIn("Saturday 2027-01-16 08:30", out)
        rows = await self.store.list(None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].message, "call the dentist")
        self.assertEqual(rows[0].tz, "UTC")
        self.assertEqual(rows[0].repeat, "none")
        expected = int(datetime(2027, 1, 16, 8, 30, tzinfo=UTC).timestamp())
        self.assertEqual(rows[0].due_at, expected)

    async def test_create_recurring_keeps_when_as_first_due(self):
        tools = self.tools()
        await self.call(tools, "create_reminder",
                        {"message": "stand up", "when": "2027-01-16T09:00",
                         "repeat": "daily", "until": "2027-02-01T09:00"})
        row = (await self.store.list(None))[0]
        self.assertEqual(row.repeat, "daily")
        self.assertEqual(row.due_at, row.next_try_at)
        self.assertEqual(row.until, int(datetime(2027, 2, 1, 9, 0, tzinfo=UTC).timestamp()))

    async def test_list_pending_vs_include_past(self):
        tools = self.tools()
        await self.call(tools, "create_reminder",
                        {"message": "pending one", "when": "2027-01-16T08:30"})
        done = await self.store.add("done one", NOW, tz="UTC", phone="socotel")
        await self.store.mark_delivered(done.id)
        missed = await self.store.add("missed one", NOW, tz="UTC", phone="socotel")
        await self.store.mark_missed(missed.id)

        pending = await self.call(tools, "list_reminders", {})
        self.assertIn("pending one", pending)
        self.assertNotIn("done one", pending)
        self.assertNotIn("missed one", pending)
        self.assertIn("[pending]", pending)

        every = await self.call(tools, "list_reminders", {"include_past": True})
        self.assertIn("pending one", every)
        self.assertIn("done one", every)
        self.assertIn("missed one", every)
        self.assertIn("[done]", every)
        self.assertIn("[missed]", every)

    async def test_list_empty(self):
        self.assertEqual(await self.call(self.tools(), "list_reminders", {}), "no reminders")

    async def test_delete_removes_and_unknown_is_error_text(self):
        tools = self.tools()
        await self.call(tools, "create_reminder",
                        {"message": "x", "when": "2027-01-16T08:30"})
        deleted = await self.call(tools, "delete_reminder", {"id": 1})
        self.assertIn("deleted reminder 1", deleted)
        self.assertIsNone(await self.store.get(1))

        unknown = await self.call(tools, "delete_reminder", {"id": 999})
        self.assertTrue(unknown.startswith("error"), unknown)
        self.assertIn("999", unknown)

    async def test_on_change_fires_only_on_success(self):
        events = []
        tools = self.tools(on_change=lambda: events.append(1))
        await self.call(tools, "create_reminder",
                        {"message": "x", "when": "2027-01-16T08:30"})
        self.assertEqual(len(events), 1)
        await self.call(tools, "delete_reminder", {"id": 1})
        self.assertEqual(len(events), 2)
        await self.call(tools, "delete_reminder", {"id": 404})
        await self.call(tools, "create_reminder",
                        {"message": "past", "when": "2027-01-14T08:30"})
        self.assertEqual(len(events), 2)

    async def test_validation_errors(self):
        tools = self.tools()
        future = "2027-01-16T08:30"
        cases = [
            ({"message": "x", "when": "2027-01-14T08:30"}, "past"),
            ({"message": "x", "when": "not-a-date"}, "invalid"),
            ({"message": "x", "when": future, "repeat": "yearly"}, "repeat"),
            ({"message": "x", "when": future, "phone": "ghost"}, "phone"),
            ({"message": "x", "when": future, "until": "2027-01-15T08:00"}, "until"),
        ]
        for args, needle in cases:
            out = await self.call(tools, "create_reminder", args)
            self.assertTrue(out.startswith("error"), out)
            self.assertIn(needle, out.lower())
        self.assertEqual(await self.store.list(None), [])

    async def test_phone_resolution_order(self):
        phones = [PhoneConfig(name="first"), PhoneConfig(name="second")]

        async def made(message, phone=None, **kwargs):
            tools = self.tools(phones=phones, **kwargs)
            args = {"message": message, "when": "2027-01-16T08:30"}
            if phone is not None:
                args["phone"] = phone
            await self.call(tools, "create_reminder", args)
            return (await self.store.list(None))[-1].phone

        # explicit beats current call
        self.assertEqual(await made("1", phone="second", call_phone="first"), "second")
        # current call beats configured default
        self.assertEqual(await made("2", call_phone="second", default_phone="first"), "second")
        # configured default beats first [[phones]]
        self.assertEqual(await made("3", default_phone="second"), "second")
        # first [[phones]] entry is the final fallback
        self.assertEqual(await made("4"), "first")

    async def test_timezone_across_dst(self):
        tools = self.tools(tz="Europe/Berlin", phones=[PhoneConfig(name="p")])
        await self.call(tools, "create_reminder",
                        {"message": "winter", "when": "2027-01-16T08:30"})
        await self.call(tools, "create_reminder",
                        {"message": "summer", "when": "2027-07-16T08:30"})
        by_message = {r.message: r for r in await self.store.list(None)}
        winter = int(datetime(2027, 1, 16, 7, 30, tzinfo=UTC).timestamp())
        summer = int(datetime(2027, 7, 16, 6, 30, tzinfo=UTC).timestamp())
        self.assertEqual(by_message["winter"].due_at, winter)
        self.assertEqual(by_message["summer"].due_at, summer)
        self.assertEqual(by_message["winter"].tz, "Europe/Berlin")
        self.assertEqual(by_message["summer"].tz, "Europe/Berlin")


class WiringTest(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_creates_no_db_and_no_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config()
            cfg.tools.reminders.enabled = False
            cfg.db.path = str(Path(tmp) / "reminders.db")
            handler, store, conn, scheduler = build_app(cfg, "")
            self.assertIsNone(store)
            self.assertIsNone(conn)
            self.assertIsNone(scheduler)
            self.assertFalse(Path(cfg.db.path).exists())

            agent = handler.agent_factory(FakeCall(phone=None))
            out = await agent.tools.call("create_reminder", "{}")
            self.assertTrue(out.startswith("error: unknown tool"), out)
            self.assertTrue((await agent.tools.call("list_reminders", "{}")).startswith("error"))

    async def test_enabled_opens_db_and_registers_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config()
            cfg.audio.vad = "energy"
            cfg.db.path = str(Path(tmp) / "reminders.db")
            cfg.phones = [PhoneConfig(name="p")]
            handler, store, conn, scheduler = build_app(cfg, "")
            self.addCleanup(conn.close)
            self.assertIsNotNone(scheduler)
            self.assertTrue(Path(cfg.db.path).exists())

            agent = handler.agent_factory(FakeCall(phone="p"))
            out = await agent.tools.call(
                "create_reminder", json.dumps({"message": "m", "when": _future()}))
            self.assertIn("created reminder", out)
            self.assertEqual((await store.list(None))[0].phone, "p")

    async def test_factory_receives_call_and_calls_get_independent_registries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config()
            cfg.audio.vad = "energy"
            cfg.llm.greeting = ""
            cfg.db.path = str(Path(tmp) / "reminders.db")
            cfg.phones = [PhoneConfig(name="a"), PhoneConfig(name="b")]
            handler, store, conn, _scheduler = build_app(cfg, "")
            self.addCleanup(conn.close)

            seen = []
            original = handler.agent_factory

            def recording(call):
                seen.append(call)
                return original(call)

            handler.agent_factory = recording
            call_a, call_b = FakeCall(phone="a", cid="aaaaaaaa"), FakeCall(phone="b", cid="bbbbbbbb")
            await asyncio.gather(handler.on_call(call_a), handler.on_call(call_b))
            self.assertEqual(seen, [call_a, call_b])

            agent_a, agent_b = original(call_a), original(call_b)
            self.assertIsNot(agent_a.tools, agent_b.tools)
            when = _future()
            await agent_a.tools.call(
                "create_reminder", json.dumps({"message": "x", "when": when}))
            self.assertEqual((await store.list(None))[0].phone, "a")


class LLMToolCallTest(unittest.IsolatedAsyncioTestCase):
    async def test_scripted_tool_call_creates_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "llm.db")
            migrate(conn, MIGRATIONS)
            store = ReminderStore(conn)
            tools = reminder_tools(store, tz="UTC", phones=[PhoneConfig(name="p")])
            when = _iso(NOW + 86_400)
            replies = [
                {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
                    "name": "create_reminder",
                    "arguments": json.dumps({"message": "dentist", "when": when})}}]},
                {"content": "ok"},
            ]

            class FakeLLM(BaseHTTPRequestHandler):
                def do_POST(self):
                    self.rfile.read(int(self.headers["Content-Length"]))
                    msg = replies.pop(0)
                    out = json.dumps({"choices": [{"message": msg}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    self.wfile.write(out)

                def log_message(self, *a):
                    pass

            srv = HTTPServer(("127.0.0.1", 0), FakeLLM)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.shutdown)
            self.addCleanup(conn.close)
            agent = OpenAIChatAgent(
                LlmConfig(base_url=f"http://127.0.0.1:{srv.server_port}"),
                tools=ToolRegistry(tools))
            self.assertEqual(await agent.respond("remind me to call the dentist"), "ok")
            rows = await store.list(None)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].message, "dentist")
            self.assertEqual(rows[0].phone, "p")
            self.assertEqual(rows[0].due_at, NOW + 86_400)


if __name__ == "__main__":
    unittest.main()
