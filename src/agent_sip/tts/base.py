import array
from typing import Protocol


class Synthesizer(Protocol):
    """Turns text into 8 kHz mono PCM, ready for ``Call.play``.

    The OpenAI-compatible HTTP implementation (base_url, api_key, model, voice)
    will live next to this file; resampling to 8 kHz happens there.
    """

    async def synthesize(self, text: str) -> array.array: ...
