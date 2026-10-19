import array
from typing import Protocol


class Transcriber(Protocol):
    """Turns 8 kHz mono PCM into text. Implementations (e.g. faster-whisper) go here."""

    async def transcribe(self, pcm: array.array, sample_rate: int = 8000) -> str: ...
