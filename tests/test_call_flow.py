"""End-to-end on loopback: a fake phone calls the server, which echoes audio."""
import array
import asyncio
import socket
import struct
import tempfile
import time
import unittest
from pathlib import Path

from agent_sip.assistant import AssistantHandler
from agent_sip.config import AudioConfig, PhoneConfig, RemindersConfig, SipConfig
from agent_sip.db import connect, migrate
from agent_sip.db.migrations import MIGRATIONS
from agent_sip.reminders.scheduler import ReminderScheduler
from agent_sip.reminders.store import ReminderStore
from agent_sip.sip import Call, CallHandler, SipServer, g711
from agent_sip.sip.message import SipMessage, build_response, parse
from agent_sip.sip.sdp import build_sdp, parse_rtp_target


class Echo(CallHandler):
    def __init__(self):
        self.ended = asyncio.Event()

    async def on_call(self, call: Call) -> None:
        await call.play(array.array("h", [1000] * 800))   # 100 ms

    async def on_call_end(self, call: Call) -> None:
        self.ended.set()


class Flow(unittest.IsolatedAsyncioTestCase):
    async def test_incoming_call(self):
        cfg = SipConfig(local_ip="127.0.0.1", bind_host="127.0.0.1", port=55060,
                        rtp_port_min=55100, rtp_port_max=55120)
        handler = Echo()
        server = SipServer(cfg, handler)
        await server.start()
        phone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        phone.bind(("127.0.0.1", 0))
        phone.setblocking(False)
        loop = asyncio.get_running_loop()
        rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtp.bind(("127.0.0.1", 0))
        rtp.setblocking(False)
        sdp = ("v=0\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\n"
               f"m=audio {rtp.getsockname()[1]} RTP/AVP 0\r\n")
        port = phone.getsockname()[1]
        invite = (f"INVITE sip:100@127.0.0.1 SIP/2.0\r\nVia: SIP/2.0/UDP 127.0.0.1:{port};branch=z9hG4bKx\r\n"
                  f"From: <sip:p@127.0.0.1>;tag=a\r\nTo: <sip:100@127.0.0.1>\r\nCall-ID: c1\r\n"
                  f"CSeq: 1 INVITE\r\nContact: <sip:p@127.0.0.1:{port}>\r\n"
                  f"Content-Length: {len(sdp)}\r\n\r\n{sdp}")
        phone.sendto(invite.encode(), ("127.0.0.1", 55060))

        codes, ok = [], None
        while ok is None:
            data = await asyncio.wait_for(loop.sock_recv(phone, 4096), 2)
            m = parse(data)
            codes.append(m.status)
            if m.status == 200:
                ok = m
        self.assertEqual(codes, [180, 200])
        remote = parse_rtp_target(ok.body)

        # send some RTP, expect RTP back
        rtp.sendto(struct.pack("!BBHII", 0x80, 0, 1, 0, 1) + g711.encode([0] * 160), remote)
        pkt = await asyncio.wait_for(loop.sock_recv(rtp, 4096), 2)
        self.assertEqual(len(pkt), 12 + 160)

        # handler finishes -> server sends BYE
        while True:
            data = await asyncio.wait_for(loop.sock_recv(phone, 4096), 2)
            m = parse(data)
            if not m.is_response and m.method == "BYE":
                break
        await asyncio.wait_for(handler.ended.wait(), 2)
        self.assertEqual(server.calls, {})
        await server.stop()
        phone.close()
        rtp.close()


class Recording(CallHandler):
    """Records whether/when ``on_call`` ran and what the call looked like."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.ended = asyncio.Event()
        self.seen: list[dict] = []
        self.hold = asyncio.Event()

    async def on_call(self, call: Call) -> None:
        self.seen.append({
            "call": call,
            "metadata": dict(call.metadata),
            "answered": call.answered.is_set(),
            "active": call.active,
        })
        self.started.set()
        await self.hold.wait()

    async def on_call_end(self, call: Call) -> None:
        self.ended.set()


class FakePhone:
    """Minimal SIP UAS used to drive outgoing calls.

    Runs its own receive loop and queues parsed requests; tests call ``expect``
    to pull the message they care about and ``answer``/``reject``/``silent`` to
    control the dialog.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]
        self.rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp.bind(("127.0.0.1", 0))
        self.rtp.setblocking(False)
        self.rtp_port = self.rtp.getsockname()[1]
        self.server_addr: tuple[str, int] = ()
        self.rx: asyncio.Queue[SipMessage] = asyncio.Queue()
        self._task = loop.create_task(self._read())

    @property
    def contact(self) -> str:
        return f"sip:phone@127.0.0.1:{self.port}"

    async def _read(self) -> None:
        try:
            while True:
                data = await self.loop.sock_recv(self.sock, 4096)
                await self.rx.put(parse(data))
        except (OSError, asyncio.CancelledError):
            pass

    async def expect(self, method: str, timeout: float = 2.0) -> SipMessage:
        while True:
            msg = await asyncio.wait_for(self.rx.get(), timeout)
            if not msg.is_response and msg.method == method:
                return msg

    def answer(self, invite: SipMessage) -> None:
        body = build_sdp("127.0.0.1", self.rtp_port)
        self.sock.sendto(build_response(invite, 200, "OK", contact=self.contact,
                                        to_tag="ph", body=body), self.server_addr)

    def reject(self, invite: SipMessage, code: int) -> None:
        reason = {486: "Busy Here", 603: "Decline"}.get(code, "Decline")
        self.sock.sendto(build_response(invite, code, reason, contact=self.contact,
                                        to_tag="ph"), self.server_addr)

    def close(self) -> None:
        self._task.cancel()
        self.sock.close()
        self.rtp.close()


class Outgoing(unittest.IsolatedAsyncioTestCase):
    """Outgoing-call primitives: answered/metadata and ring-timeout handling."""

    async def _setup(self, sip_port: int):
        loop = asyncio.get_running_loop()
        phone = FakePhone(loop)
        cfg = SipConfig(local_ip="127.0.0.1", bind_host="127.0.0.1", port=sip_port,
                        rtp_port_min=sip_port + 100, rtp_port_max=sip_port + 120)
        handler = Recording()
        server = SipServer(cfg, handler, phones=[
            PhoneConfig(name="phone", ip="127.0.0.1", port=phone.port, user="phone")])
        await server.start()
        phone.server_addr = ("127.0.0.1", sip_port)

        async def cleanup():
            await server.stop()
            phone.close()

        self.addAsyncCleanup(cleanup)
        return server, handler, phone

    async def test_outgoing_answered_sets_answered_and_metadata(self):
        server, handler, phone = await self._setup(55200)
        call = await server.originate("phone", metadata={"reminder": {"id": 7}})
        invite = await phone.expect("INVITE")
        self.assertFalse(call.answered.is_set())
        self.assertEqual(call.metadata, {"reminder": {"id": 7}})

        phone.answer(invite)
        await asyncio.wait_for(call.answered.wait(), 2)
        await asyncio.wait_for(handler.started.wait(), 2)

        self.assertTrue(call.active)
        rec = handler.seen[0]
        self.assertTrue(rec["answered"])
        self.assertTrue(rec["active"])
        self.assertEqual(rec["metadata"], {"reminder": {"id": 7}})
        # handler received the very same call object
        self.assertIs(rec["call"], call)

    async def test_phone_rejects_releases_rtp_and_never_answers(self):
        for i, code in enumerate((486, 603)):
            with self.subTest(code=code):
                server, handler, phone = await self._setup(55220 + i * 20)
                call = await server.originate("phone")
                invite = await phone.expect("INVITE")
                phone.reject(invite, code)
                await asyncio.wait_for(call.ended.wait(), 2)

                self.assertFalse(call.answered.is_set())
                self.assertFalse(handler.started.is_set())
                self.assertEqual(server.calls, {})

                # the RTP port was released: a new call can reuse it
                await asyncio.sleep(0.05)          # let the transport finish closing
                call2 = await server.originate("phone")
                await phone.expect("INVITE")
                self.assertEqual(call2.rtp_port, call.rtp_port)
                await call2.hangup()

    async def test_hangup_while_ringing_sends_cancel_and_releases_rtp(self):
        server, _handler, phone = await self._setup(55260)
        call = await server.originate("phone")
        await phone.expect("INVITE")

        await call.hangup()
        await phone.expect("CANCEL")
        await asyncio.wait_for(call.ended.wait(), 2)
        self.assertFalse(call.answered.is_set())
        self.assertEqual(server.calls, {})

        await asyncio.sleep(0.05)                  # let the transport finish closing
        call2 = await server.originate("phone")
        await phone.expect("INVITE")
        self.assertEqual(call2.rtp_port, call.rtp_port)
        await call2.hangup()

    async def test_late_answer_after_cancel_starts_no_handler(self):
        server, handler, phone = await self._setup(55280)
        call = await server.originate("phone")
        invite = await phone.expect("INVITE")
        await call.hangup()
        await phone.expect("CANCEL")

        phone.answer(invite)                  # 200 OK arrives after our CANCEL
        await asyncio.sleep(0.2)
        self.assertFalse(handler.started.is_set())
        self.assertEqual(server.calls, {})
        self.assertFalse(call.answered.is_set())


class Incoming(unittest.IsolatedAsyncioTestCase):
    async def test_incoming_metadata_empty_and_answered_set(self):
        cfg = SipConfig(local_ip="127.0.0.1", bind_host="127.0.0.1", port=55300,
                        rtp_port_min=55320, rtp_port_max=55340)
        handler = Recording()
        server = SipServer(cfg, handler)
        await server.start()
        phone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        phone.bind(("127.0.0.1", 0))
        phone.setblocking(False)
        rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtp.bind(("127.0.0.1", 0))
        rtp.setblocking(False)

        async def cleanup():
            await server.stop()
            phone.close()
            rtp.close()

        self.addAsyncCleanup(cleanup)

        loop = asyncio.get_running_loop()
        sdp = build_sdp("127.0.0.1", rtp.getsockname()[1])
        port = phone.getsockname()[1]
        invite = (f"INVITE sip:100@127.0.0.1 SIP/2.0\r\n"
                  f"Via: SIP/2.0/UDP 127.0.0.1:{port};branch=z9hG4bKx\r\n"
                  f"From: <sip:p@127.0.0.1>;tag=a\r\nTo: <sip:100@127.0.0.1>\r\n"
                  f"Call-ID: c-inc\r\nCSeq: 1 INVITE\r\n"
                  f"Contact: <sip:p@127.0.0.1:{port}>\r\n"
                  f"Content-Length: {len(sdp)}\r\n\r\n{sdp}")
        phone.sendto(invite.encode(), ("127.0.0.1", 55300))

        while True:
            data = await asyncio.wait_for(loop.sock_recv(phone, 4096), 2)
            if parse(data).status == 200:
                break
        await asyncio.wait_for(handler.started.wait(), 2)

        rec = handler.seen[0]
        self.assertEqual(rec["metadata"], {})
        self.assertTrue(rec["answered"])
        self.assertTrue(rec["call"].answered.is_set())


class _FakeTranscriber:
    async def transcribe(self, pcm, sample_rate: int = 8000) -> str:
        return ""


class _FakeSynth:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> array.array:
        self.texts.append(text)
        return array.array("h", [1000] * 160)


class _FakeAgent:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def respond(self, text: str) -> str:
        self.calls.append(text)
        return "Reminder: call the dentist"


class ReminderIntegration(unittest.IsolatedAsyncioTestCase):
    """Real SIP server + fake phone UA + fake LLM/TTS, driven by the scheduler."""

    async def test_due_reminder_rings_answers_and_ends_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "integration.db")
            migrate(conn, MIGRATIONS)
            store = ReminderStore(conn)
            loop = asyncio.get_running_loop()
            phone = FakePhone(loop)
            sip_port = 55400
            cfg = SipConfig(local_ip="127.0.0.1", bind_host="127.0.0.1", port=sip_port,
                            rtp_port_min=55420, rtp_port_max=55460)
            audio = AudioConfig(vad="energy", barge_in=False, earcons=False,
                                no_speech_timeout=0.2, silence_end=0.1, max_record=1.0)
            synth = _FakeSynth()
            agent = _FakeAgent()
            handler = AssistantHandler(audio, _FakeTranscriber(), synth, lambda call: agent)
            server = SipServer(cfg, handler, phones=[
                PhoneConfig(name="phone", ip="127.0.0.1", port=phone.port, user="phone")])
            scheduler = ReminderScheduler(
                store,
                RemindersConfig(ring_timeout=2.0, retry_attempts=2,
                                retry_interval=60.0, max_late=3600.0, timezone="UTC"),
                server,
            )
            await server.start()
            phone.server_addr = ("127.0.0.1", sip_port)

            async def cleanup():
                await scheduler.stop()
                await server.stop()
                phone.close()
                conn.close()

            self.addAsyncCleanup(cleanup)

            now = int(time.time())
            reminder = await store.add("call the dentist", now, tz="UTC", phone="phone",
                                       next_try_at=now, created_at=now)
            await scheduler.start()

            invite = await phone.expect("INVITE", timeout=5)
            phone.answer(invite)
            await asyncio.sleep(0.05)
            active = next(iter(server.calls.values()))
            self.assertEqual(active.metadata["reminder"].id, reminder.id)

            deadline = time.monotonic() + 5
            row = None
            while time.monotonic() < deadline:
                row = await store.get(reminder.id)
                if row is not None and row.status == "done":
                    break
                await asyncio.sleep(0.02)
            self.assertIsNotNone(row)
            self.assertEqual(row.status, "done")
            self.assertEqual(synth.texts, ["Reminder: call the dentist"])
            self.assertTrue(agent.calls[0].startswith("[REMINDER]"))
            self.assertIn("call the dentist", agent.calls[0])


if __name__ == "__main__":
    unittest.main()
