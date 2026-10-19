"""Remote STT through any OpenAI-shaped /audio/transcriptions endpoint (stdlib only)."""
import array
import asyncio
import io
import json
import urllib.error
import urllib.request
import uuid
import wave

from ..config import SttConfig


def pcm_to_wav(pcm: array.array, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _multipart(fields: dict[str, str], filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
              f'filename="{filename}"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
    out.write(data + f"\r\n--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


class OpenAITranscriber:
    def __init__(self, cfg: SttConfig) -> None:
        self.cfg = cfg

    def _request(self, wav: bytes) -> str:
        fields = {"model": self.cfg.model, "response_format": "json"}
        if self.cfg.language:
            fields["language"] = self.cfg.language
        for k, v in self.cfg.extra.items():
            fields[k] = (json.dumps(v) if isinstance(v, (dict, list))
                         else str(v).lower() if isinstance(v, bool) else str(v))
        body, ctype = _multipart(fields, "audio.wav", wav)
        headers = {"Content-Type": ctype}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        req = urllib.request.Request(
            self.cfg.base_url.rstrip("/") + "/audio/transcriptions", body, headers)
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                return json.load(resp)["text"].strip()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"STT HTTP {e.code}: {e.read()[:200]!r}") from e

    async def transcribe(self, pcm: array.array, sample_rate: int = 8000) -> str:
        # blocking HTTP runs in a thread so the SIP/RTP loop is never stalled
        return await asyncio.to_thread(self._request, pcm_to_wav(pcm, sample_rate))
