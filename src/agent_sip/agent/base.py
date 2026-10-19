from typing import Protocol


class Agent(Protocol):
    """Text in, text out. A CallHandler wires STT -> Agent -> TTS around a Call."""

    async def respond(self, text: str) -> str: ...
