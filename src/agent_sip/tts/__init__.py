"""Text-to-speech through any OpenAI-shaped API (POST /v1/audio/speech)."""

from .base import Synthesizer
from .openai import OpenAISynthesizer

__all__ = ["Synthesizer", "OpenAISynthesizer"]
