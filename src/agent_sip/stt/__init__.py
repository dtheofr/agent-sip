"""Speech-to-text. Remote OpenAI-shaped API now; local faster-whisper possible later."""

from .base import Transcriber
from .openai import OpenAITranscriber

__all__ = ["Transcriber", "OpenAITranscriber"]
