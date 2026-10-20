"""Waiting-feedback sounds: a beep when input is received, then a looping melody.

Stdlib only; audio is 8 kHz mono int16 ``array('h')``.
"""
import array
import asyncio
import contextlib
import math
import re
from collections.abc import AsyncIterator, Sequence
from functools import lru_cache

SAMPLE_RATE = 8000
_ATTACK = 0.01   # seconds, linear fade in/out to avoid clicks
_NOTE_RE = re.compile(r"^([A-G])([#b]?)(-?\d+)$")
_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_MIN_FREQ, _MAX_FREQ = 98.0, 3136.0   # G2 .. G7


def _tone(freq: float, dur: float, volume: float) -> array.array:
    n = int(SAMPLE_RATE * dur)
    ramp = max(1, min(int(SAMPLE_RATE * _ATTACK), n // 2))
    amp = 32767 * max(0.0, min(1.0, volume))
    out = array.array("h")
    for i in range(n):
        env = min(1.0, i / ramp, (n - 1 - i) / ramp)
        out.append(int(amp * env * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)))
    return out


@lru_cache(maxsize=32)
def make_beep(freq: float = 800, dur: float = 0.12, volume: float = 0.25) -> array.array:
    """A sine beep with attack/decay envelope. Cached: do not mutate the result."""
    return _tone(freq, dur, volume)


def parse_melody(notes: str | Sequence[str]) -> tuple[float | None, ...]:
    """Parse ``"A4,E5,-"`` (or a list) into frequencies in Hz; ``None`` is a rest."""
    tokens = notes.split(",") if isinstance(notes, str) else list(notes)
    out: list[float | None] = []
    for tok in (str(t).strip() for t in tokens):
        if not tok:
            continue
        if tok in ("-", "r", "R"):
            out.append(None)
            continue
        m = _NOTE_RE.match(tok[0].upper() + tok[1:])
        if not m:
            raise ValueError(f"Invalid melody note {tok!r} (use e.g. A4, F#4, Bb3, or - for a rest)")
        letter, acc, octave = m.groups()
        semis = _SEMITONES[letter] + {"#": 1, "b": -1, "": 0}[acc]
        freq = 440.0 * 2 ** ((semis + 12 * (int(octave) - 4) - 9) / 12)
        if not _MIN_FREQ - 1 <= freq <= _MAX_FREQ + 1:
            raise ValueError(f"Melody note {tok!r} ({freq:.0f} Hz) is outside G2-G7")
        out.append(freq)
    if not out:
        raise ValueError("melody_notes is empty")
    return tuple(out)


@lru_cache(maxsize=8)
def _melody(notes: tuple[float | None, ...], note_dur: float, gap: float,
            volume: float) -> array.array:
    out = array.array("h")
    for f in notes:
        out.extend(array.array("h", bytes(2 * int(SAMPLE_RATE * note_dur))) if f is None
                   else _tone(f, note_dur, volume))
    out.extend(array.array("h", bytes(2 * int(SAMPLE_RATE * gap))))
    return out


def make_melody(notes: str | Sequence[str], note_dur: float = 0.3, gap: float = 2.0,
                volume: float = 0.25) -> array.array:
    """One repetition of the melody followed by ``gap`` seconds of silence."""
    parsed = parse_melody(notes)
    return _melody(parsed, note_dur, gap, volume)


async def _melody_loop(call, cfg) -> None:
    await asyncio.sleep(cfg.melody_delay)
    pcm = make_melody(cfg.melody_notes, cfg.melody_note_duration, cfg.melody_gap,
                      cfg.earcon_volume)
    while call.active:
        await call.play(pcm)   # the trailing silence is the gap


@contextlib.asynccontextmanager
async def thinking(call, cfg, beep: bool = True) -> AsyncIterator[None]:
    """Play a beep, then loop the waiting melody until the block exits.

    The melody task is cancelled *and awaited* on exit so the RTP play lock is free.
    """
    task: asyncio.Task | None = None
    if cfg.earcons:
        if beep and cfg.beep:
            await call.play(make_beep(cfg.beep_freq, cfg.beep_duration, cfg.earcon_volume))
        if cfg.melody:
            task = asyncio.ensure_future(_melody_loop(call, cfg))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
