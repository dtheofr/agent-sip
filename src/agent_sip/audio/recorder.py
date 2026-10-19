import array
import asyncio
from typing import Protocol

from .io import SAMPLE_RATE
from .vad import VAD, rms  # noqa: F401  (rms re-exported)

FRAME_SECONDS = 0.02


class FrameSource(Protocol):
    """Anything that yields incoming audio frames (e.g. ``sip.Call``)."""

    def flush_input(self) -> None: ...
    async def read_frame(self, timeout: float) -> array.array | None: ...


class PlaybackSource(FrameSource, Protocol):
    active: bool
    async def play(self, pcm: array.array) -> bool: ...


async def record_until_silence(
    source: FrameSource,
    vad: VAD,
    *,
    silence_end: float = 1.5,
    no_speech_timeout: float = 8.0,
    max_record: float = 20.0,
    prefix: array.array | None = None,
) -> tuple[array.array, bool]:
    """Record until the VAD reports ``silence_end`` seconds without speech.

    ``prefix`` is audio already captured (e.g. by barge-in) that is known to contain speech;
    the input queue is then not flushed. Returns (pcm, heard_speech).
    """
    loop = asyncio.get_running_loop()
    vad.reset()
    pcm = array.array("h")
    heard = False
    if prefix is not None and len(prefix):
        pcm.extend(prefix)
        heard = True
        for i in range(0, len(prefix) - 159, 160):   # warm up VAD state on the prefix
            vad.is_speech(prefix[i:i + 160])
    else:
        source.flush_input()
    start = last_voice = loop.time()
    while True:
        frame = await source.read_frame(timeout=0.1)
        now = loop.time()
        if frame is not None:
            pcm.extend(frame)
            if vad.is_speech(frame):
                heard, last_voice = True, now
        if heard and now - last_voice > silence_end:
            break
        if not heard and now - start > no_speech_timeout:
            break
        if now - start > max_record:
            break
    return pcm, heard


async def play_interruptible(
    call: PlaybackSource,
    pcm: array.array,
    vad: VAD,
    *,
    min_speech: float = 0.3,
    preroll: float = 0.3,
) -> array.array | None:
    """Play ``pcm`` while listening; stop as soon as the caller talks (barge-in).

    Returns None if playback finished (or the call ended), otherwise the audio captured
    since the interruption began (to pass as ``prefix`` to ``record_until_silence``).
    ``min_speech`` seconds of continuous speech are required, to ignore coughs/clicks.
    """
    vad.reset()
    call.flush_input()
    player = asyncio.ensure_future(call.play(pcm))
    need = max(1, round(min_speech / FRAME_SECONDS))
    keep = round(preroll / FRAME_SECONDS)
    history: list[array.array] = []     # recent frames, for pre-roll
    run = 0
    try:
        while not player.done():
            frame = await call.read_frame(timeout=0.05)
            if frame is None:
                continue
            history.append(frame)
            run = run + 1 if vad.is_speech(frame) else 0
            if run >= need:
                player.cancel()
                captured = array.array("h")
                for f in history[-(run + keep):]:
                    captured.extend(f)
                return captured
            if run == 0 and len(history) > keep:
                del history[:-keep]
        await player
        return None
    finally:
        if not player.done():
            player.cancel()


def duration(pcm) -> float:
    return len(pcm) / SAMPLE_RATE
