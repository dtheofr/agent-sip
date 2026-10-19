"""TTS through any OpenAI-shaped /audio/speech endpoint (stdlib only)."""
import array
import asyncio
import json
import urllib.error
import urllib.request

from ..audio import decode_audio_bytes
from ..config import TtsConfig


class OpenAISynthesizer:
    def __init__(self, cfg: TtsConfig) -> None:
        self.cfg = cfg

    def _request(self, text: str) -> array.array:
        payload = {"model": self.cfg.model, "voice": self.cfg.voice, "input": text,
                   "response_format": self.cfg.response_format}
        payload.update(self.cfg.extra)          # custom params win
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        req = urllib.request.Request(self.cfg.base_url.rstrip("/") + "/audio/speech",
                                     json.dumps(payload).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"TTS HTTP {e.code}: {e.read()[:200]!r}") from e
        return decode_audio_bytes(data, self.cfg.pcm_sample_rate)

    async def synthesize(self, text: str) -> array.array:
        # HTTP + decoding/resampling run in a thread so the SIP/RTP loop is never stalled
        return await asyncio.to_thread(self._request, text)
