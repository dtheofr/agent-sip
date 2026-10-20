"""SIP UAS/UAC over UDP. No application logic lives here: see CallHandler."""
import asyncio
import contextlib
import logging
import socket
import uuid

from ..config import PhoneConfig, SipConfig
from .call import Call
from .handler import CallHandler
from .message import (SipMessage, build_request, build_response, header_tag, header_uri,
                      parse)
from .rtp import RtpSession
from .sdp import build_sdp, parse_rtp_target

log = logging.getLogger(__name__)

T1, T2 = 0.5, 4.0          # RFC 3261 timers: 200 OK retransmit interval start / cap
ACK_TIMEOUT = 64 * T1      # give up (and BYE) if no ACK arrives within 32 s
ACK_GRACE = T1             # start the handler after this long even without an ACK


def _rand(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


def detect_local_ip(towards: str = "8.8.8.8") -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((towards, 9))  # no packet is sent
        return s.getsockname()[0]
    finally:
        s.close()


class _SipProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: "SipServer") -> None:
        self.server = server

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            self.server._on_datagram(data, addr)
        except Exception:
            log.exception("error handling SIP datagram from %s", addr)


class SipServer:
    def __init__(self, config: SipConfig, handler: CallHandler,
                 phones: list[PhoneConfig] | None = None) -> None:
        self.cfg = config
        self.phones = {p.name: p for p in phones or []}
        self.handler = handler
        self.calls: dict[str, Call] = {}
        self.local_ip = config.local_ip or detect_local_ip(
            next((p.ip for p in self.phones.values() if p.ip), "8.8.8.8"))
        self._transport: asyncio.DatagramTransport | None = None
        self._tasks: set[asyncio.Task] = set()
        self._pending: set[str] = set()   # INVITEs being set up

    # ---------------- lifecycle ----------------
    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _SipProtocol(self), local_addr=(self.cfg.bind_host, self.cfg.port))
        log.info("SIP listening on %s:%d (advertising %s)",
                 self.cfg.bind_host, self.cfg.port, self.local_ip)

    async def stop(self) -> None:
        for call in list(self.calls.values()):
            await self.hangup(call)
        for t in list(self._tasks):
            t.cancel()
        if self._transport:
            self._transport.close()

    # ---------------- helpers ----------------
    @property
    def _contact(self) -> str:
        return f"sip:{self.cfg.local_user}@{self.local_ip}:{self.cfg.port}"

    @property
    def _via(self) -> str:
        return f"{self.local_ip}:{self.cfg.port}"

    def _send(self, data: bytes, addr) -> None:
        if self._transport:
            self._transport.sendto(data, addr)

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    async def _open_rtp(self) -> tuple[RtpSession, int]:
        used = {c.rtp_port for c in self.calls.values()}
        for port in range(self.cfg.rtp_port_min, self.cfg.rtp_port_max + 1, 2):
            if port in used:
                continue
            rtp = RtpSession()
            try:
                await rtp.open(self.cfg.bind_host, port)
            except OSError:
                continue
            return rtp, port
        raise RuntimeError("No free RTP port")

    def _in_dialog(self, call: Call, method: str, *, cseq: int | None = None,
                   branch: str | None = None) -> bytes:
        return build_request(
            method, call.remote_target, via=self._via, branch=branch or "z9hG4bK" + _rand(),
            from_=call.local_hdr, to=call.remote_hdr, call_id=call.call_id,
            cseq=cseq if cseq is not None else call.cseq, contact=self._contact)

    # ---------------- dispatch ----------------
    def _on_datagram(self, data: bytes, addr) -> None:
        msg = parse(data)
        if msg.is_response:
            self._on_response(msg, addr)
        else:
            self._on_request(msg, addr)

    def _reply(self, req: SipMessage, code: int, reason: str, addr, **kw) -> bytes:
        data = build_response(req, code, reason, contact=self._contact, **kw)
        self._send(data, addr)
        return data

    # ---------------- incoming requests ----------------
    def _on_request(self, msg: SipMessage, addr) -> None:
        method = msg.method
        call = self.calls.get(msg.call_id)
        if method == "INVITE":
            if call:                                   # retransmission
                if call.final_response:
                    self._send(call.final_response, addr)
                return
            if msg.call_id in self._pending:
                return
            self._spawn(self._handle_invite(msg, addr))
        elif method in ("BYE", "CANCEL"):
            self._reply(msg, 200, "OK", addr)
            if call:
                log.info("[%s] remote %s", call.call_id[:8], method)
                self._end(call)
        elif method == "ACK":
            if call:
                call.acked.set()
        else:
            self._reply(msg, 200, "OK", addr)          # OPTIONS, NOTIFY...

    async def _handle_invite(self, msg: SipMessage, addr) -> None:
        number = header_uri(msg.uri).removeprefix("sip:").split("@")[0]
        remote_rtp = parse_rtp_target(msg.body)
        if not remote_rtp:
            log.warning("INVITE without usable SDP")
            self._reply(msg, 488, "Not Acceptable Here", addr)
            return
        tag = _rand()
        self._pending.add(msg.call_id)
        try:
            rtp, port = await self._open_rtp()
        except RuntimeError:
            self._reply(msg, 503, "Service Unavailable", addr)
            return
        finally:
            self._pending.discard(msg.call_id)
        rtp.remote = remote_rtp
        contact = msg.header("contact")
        call = Call(
            self, call_id=msg.call_id, direction="incoming", number=number,
            local_hdr=msg.header("to") + f";tag={tag}", remote_hdr=msg.header("from"),
            remote_target=header_uri(contact) if contact else header_uri(msg.header("from")),
            sip_addr=addr, rtp=rtp, rtp_port=port,
            phone=next((p.name for p in self.phones.values() if p.ip == addr[0]), None))
        self.calls[call.call_id] = call
        log.info("[%s] incoming call from %s, dialed %r, RTP %s:%d <-> :%d",
                 call.call_id[:8], call.phone or addr[0], number, *remote_rtp, port)
        self._reply(msg, 180, "Ringing", addr, to_tag=tag)
        call.final_response = self._reply(msg, 200, "OK", addr, to_tag=tag,
                                          body=build_sdp(self.local_ip, port))
        call.state = "active"
        self._spawn(self._retransmit_200(call, addr))
        call.task = self._spawn(self._establish(call))

    async def _establish(self, call: Call) -> None:
        """Wait briefly for the ACK so the phone is ready, then run the handler."""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(call.acked.wait(), ACK_GRACE)
        if call.state == "active":
            await self._run_handler(call)

    async def _retransmit_200(self, call: Call, addr) -> None:
        """RFC 3261 13.3.1.4: resend the 200 OK until ACKed; BYE if it never is."""
        delay, elapsed = T1, 0.0
        while not call.acked.is_set() and call.state == "active" and elapsed < ACK_TIMEOUT:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(call.acked.wait(), delay)
            if call.acked.is_set() or call.state != "active":
                return
            log.info("[%s] no ACK yet, retransmitting 200 OK", call.call_id[:8])
            self._send(call.final_response, addr)
            elapsed += delay
            delay = min(delay * 2, T2)
        if not call.acked.is_set() and call.state == "active":
            log.warning("[%s] no ACK received, hanging up", call.call_id[:8])
            await self.hangup(call)

    # ---------------- outgoing calls ----------------
    async def originate(self, phone: str | PhoneConfig | None = None) -> Call:
        """Ring a known phone (by name or config; default: the only/first one).

        The handler starts when the phone is answered.
        """
        if phone is None:
            if not self.phones:
                raise ValueError("No phones configured")
            phone = next(iter(self.phones.values()))
        elif isinstance(phone, str):
            if phone not in self.phones:
                raise KeyError(f"Unknown phone {phone!r}; known: {sorted(self.phones)}")
            phone = self.phones[phone]
        user, host, port = phone.user, phone.ip, phone.port
        rtp, rtp_port = await self._open_rtp()
        call_id = f"{_rand(12)}@{self.local_ip}"
        local = f"<sip:{self.cfg.local_user}@{self.local_ip}>;tag={_rand()}"
        remote = f"<sip:{user}@{host}>"
        call = Call(self, call_id=call_id, direction="outgoing", local_hdr=local,
                    remote_hdr=remote, remote_target=f"sip:{user}@{host}:{port}",
                    sip_addr=(host, port), rtp=rtp, rtp_port=rtp_port, number=user,
                    phone=phone.name)
        call.invite_branch = "z9hG4bK" + _rand()
        self.calls[call_id] = call
        self._send(self._invite(call, build_sdp(self.local_ip, rtp_port)), call.sip_addr)
        log.info("[%s] INVITE sent to %s:%d, the phone should ring", call_id[:8], host, port)
        return call

    def _invite(self, call: Call, sdp: str) -> bytes:
        return build_request(
            "INVITE", call.remote_target, via=self._via, branch=call.invite_branch,
            from_=call.local_hdr, to=call.remote_hdr, call_id=call.call_id, cseq=1,
            contact=self._contact, body=sdp)

    def _on_response(self, msg: SipMessage, addr) -> None:
        call = self.calls.get(msg.call_id)
        if not call or msg.method != "INVITE" or call.direction != "outgoing":
            return
        code = msg.status
        if code < 200:
            log.info("[%s] %s", call.call_id[:8], msg.start_line)
        elif code == 200:
            if call.state == "active":                 # retransmitted 200: re-ACK
                self._send(self._in_dialog(call, "ACK", cseq=1), call.sip_addr)
                return
            call.remote_hdr = msg.header("to")
            contact = msg.header("contact")
            if contact:
                call.remote_target = header_uri(contact)
            remote_rtp = parse_rtp_target(msg.body)
            self._send(self._in_dialog(call, "ACK", cseq=1), call.sip_addr)
            call.cseq = 2
            if not remote_rtp:
                log.warning("200 OK without SDP, hanging up")
                self._spawn(self.hangup(call))
                return
            call._rtp.remote = remote_rtp
            log.info("[%s] answered", call.call_id[:8])
            self._activate(call)
        else:
            to = msg.header("to")
            ack = build_request(
                "ACK", call.remote_target, via=self._via, branch=call.invite_branch,
                from_=call.local_hdr, to=to, call_id=call.call_id, cseq=1, contact=self._contact)
            self._send(ack, call.sip_addr)
            log.info("[%s] call failed: %s", call.call_id[:8], msg.start_line)
            self._end(call)

    # ---------------- call state ----------------
    def _activate(self, call: Call) -> None:
        call.state = "active"
        call.task = self._spawn(self._run_handler(call))

    async def _run_handler(self, call: Call) -> None:
        try:
            await self.handler.on_call(call)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("[%s] handler crashed", call.call_id[:8])
        try:
            if call.active:
                await self.hangup(call)
            await self.handler.on_call_end(call)
        except Exception:
            log.exception("[%s] on_call_end failed", call.call_id[:8])

    async def hangup(self, call: Call) -> None:
        if call.state == "ended":
            return
        if call.state == "active":
            call.cseq += 1
            self._send(self._in_dialog(call, "BYE"), call.sip_addr)
        elif call.direction == "outgoing":             # still ringing: CANCEL
            self._send(self._in_dialog(call, "CANCEL", cseq=1, branch=call.invite_branch),
                       call.sip_addr)
        log.info("[%s] hangup", call.call_id[:8])
        self._end(call)

    def _end(self, call: Call) -> None:
        if call.state == "ended":
            return
        call.state = "ended"
        call.ended.set()
        self.calls.pop(call.call_id, None)
        call._rtp.close()
        if call.task and call.task is not asyncio.current_task():
            call.task.cancel()
