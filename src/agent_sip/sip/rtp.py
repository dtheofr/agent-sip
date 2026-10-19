"""RTP session: one UDP socket per call, G.711 u-law, 20 ms packets."""
import array
import asyncio
import logging
import struct
import uuid

from . import g711

log = logging.getLogger(__name__)

FRAME_SAMPLES = 160  # 20 ms @ 8 kHz
FRAME_SECONDS = 0.02


class RtpSession(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.remote: tuple[str, int] | None = None
        self.rx: asyncio.Queue[array.array] = asyncio.Queue(maxsize=500)
        self._seq = 0
        self._ts = 0
        self._ssrc = uuid.uuid4().int & 0xFFFFFFFF
        self._play_lock = asyncio.Lock()

    async def open(self, host: str, port: int) -> None:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: self, local_addr=(host, port))

    def close(self) -> None:
        if self.transport:
            self.transport.close()
            self.transport = None

    # --- asyncio protocol ---
    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if len(data) < 12:
            return
        off = 12 + 4 * (data[0] & 0x0F)                 # skip CSRC list
        if data[0] & 0x10 and len(data) >= off + 4:     # skip header extension
            off += 4 + 4 * struct.unpack("!H", data[off + 2:off + 4])[0]
        if (data[1] & 0x7F) != 0:                       # PCMU only
            return
        pcm = g711.decode(data[off:])
        if self.rx.full():
            self.rx.get_nowait()                        # drop oldest
        self.rx.put_nowait(pcm)

    # --- API ---
    def flush(self) -> None:
        while not self.rx.empty():
            self.rx.get_nowait()

    async def send_pcm(self, pcm) -> None:
        """Send samples as real-time paced 20 ms packets. Cancel the task to stop."""
        if not self.transport or not self.remote:
            return
        payload = g711.encode(pcm)
        loop = asyncio.get_running_loop()
        async with self._play_lock:
            t0 = loop.time()
            for n, i in enumerate(range(0, len(payload), FRAME_SAMPLES)):
                chunk = payload[i:i + FRAME_SAMPLES].ljust(FRAME_SAMPLES, bytes([g711.ULAW_SILENCE]))
                header = struct.pack("!BBHII", 0x80, 0, self._seq & 0xFFFF,
                                     self._ts & 0xFFFFFFFF, self._ssrc)
                if self.transport is None:
                    return
                self.transport.sendto(header + chunk, self.remote)
                self._seq += 1
                self._ts += FRAME_SAMPLES
                delay = t0 + (n + 1) * FRAME_SECONDS - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
