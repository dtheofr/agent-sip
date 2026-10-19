import array
import asyncio
import math
from typing import Protocol

from .io import SAMPLE_RATE


class FrameSource(Protocol):
    """Anything that yields incoming audio frames (e.g. ``sip.Call``)."""

    def flush_input(self) -> None: ...
    async def read_frame(self, timeout: float) -> array.array | None: ...


def rms(samples) -> float:
    if not len(samples):
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


async def record_until_silence(
    source: FrameSource,
    *,
    speech_threshold: float = 500,
    silence_end: float = 1.5,
    no_speech_timeout: float = 8.0,
    max_record: float = 20.0,
) -> tuple[array.array, bool]:
    """Record until the caller stops talking. Returns (pcm, heard_speech)."""
    loop = asyncio.get_running_loop()
    source.flush_input()
    pcm = array.array("h")
    start = last_voice = loop.time()
    heard = False
    while True:
        frame = await source.read_frame(timeout=0.1)
        now = loop.time()
        if frame is not None:
            pcm.extend(frame)
            if rms(frame) > speech_threshold:
                heard, last_voice = True, now
        if heard and now - last_voice > silence_end:
            break
        if not heard and now - start > no_speech_timeout:
            break
        if now - start > max_record:
            break
    return pcm, heard


def duration(pcm) -> float:
    return len(pcm) / SAMPLE_RATE
