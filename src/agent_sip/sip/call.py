"""A single phone call, as seen by application code (the CallHandler)."""
import array
import asyncio
import logging
from typing import TYPE_CHECKING

from .rtp import RtpSession

if TYPE_CHECKING:
    from .server import SipServer

log = logging.getLogger(__name__)


class Call:
    """Audio + lifecycle API for one call. Handlers only touch this class.

    The handler coroutine is cancelled when the remote side hangs up.
    """

    def __init__(self, server: "SipServer", *, call_id: str, direction: str,
                 local_hdr: str, remote_hdr: str, remote_target: str,
                 sip_addr: tuple[str, int], rtp: RtpSession, rtp_port: int, number: str = "",
                 phone: str | None = None) -> None:
        self.call_id = call_id
        self.direction = direction            # "incoming" | "outgoing"
        self.number = number                  # dialed number (incoming calls)
        self.phone = phone                    # name of the known phone, if recognised
        self.state = "ringing"                # ringing | active | ended
        self.ended = asyncio.Event()
        # --- SIP dialog state (used by SipServer) ---
        self.local_hdr = local_hdr            # From/To header value with our tag
        self.remote_hdr = remote_hdr
        self.remote_target = remote_target    # request-URI for in-dialog requests
        self.sip_addr = sip_addr
        self.cseq = 1
        self.invite_branch = ""
        self.final_response: bytes | None = None  # last 200 OK, for retransmission
        self.task: asyncio.Task | None = None
        self._server = server
        self._rtp = rtp
        self.rtp_port = rtp_port

    @property
    def active(self) -> bool:
        return self.state == "active"

    # --- audio ---
    async def play(self, pcm: array.array) -> bool:
        """Play 8 kHz mono PCM to the caller. Returns False if the call is over."""
        if not self.active:
            return False
        await self._rtp.send_pcm(pcm)
        return self.active

    async def read_frame(self, timeout: float = 0.1) -> array.array | None:
        """Next 20 ms of incoming audio, or None on timeout."""
        try:
            return await asyncio.wait_for(self._rtp.rx.get(), timeout)
        except TimeoutError:
            return None

    def flush_input(self) -> None:
        self._rtp.flush()

    # --- lifecycle ---
    async def hangup(self) -> None:
        await self._server.hangup(self)

    async def wait_ended(self) -> None:
        await self.ended.wait()
