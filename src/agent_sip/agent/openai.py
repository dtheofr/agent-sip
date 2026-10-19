"""Agent backed by any OpenAI-shaped POST {base_url}/chat/completions endpoint (stdlib only)."""
import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path

from ..config import LlmConfig


def load_system_prompt(path: str) -> str:
    return Path(path).read_text().strip() if path else ""


class OpenAIChatAgent:
    """One instance = one conversation (keeps history). Create one per call."""

    def __init__(self, cfg: LlmConfig, system_prompt: str = "") -> None:
        self.cfg = cfg
        self.messages: list[dict] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def _request(self, messages: list[dict]) -> str:
        payload = {"model": self.cfg.model, "messages": messages}
        payload.update(self.cfg.extra)          # custom params win
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        req = urllib.request.Request(self.cfg.base_url.rstrip("/") + "/chat/completions",
                                     json.dumps(payload).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"LLM HTTP {e.code}: {e.read()[:200]!r}") from e
        return (data["choices"][0]["message"].get("content") or "").strip()

    async def respond(self, text: str) -> str:
        messages = self.messages + [{"role": "user", "content": text}]
        reply = await asyncio.to_thread(self._request, messages)
        # only commit the turn once it succeeded, so a failure leaves history consistent
        self.messages = messages + [{"role": "assistant", "content": reply}]
        return reply
