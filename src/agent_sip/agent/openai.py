"""Agent backed by any OpenAI-shaped POST {base_url}/chat/completions endpoint (stdlib only)."""
import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..config import LlmConfig
from .tools import ToolRegistry, registry

log = logging.getLogger(__name__)


def _short(x, n=80) -> str:
    x = str(x).replace("\n", " ")
    return x if len(x) <= n else x[:n] + "…"


def load_system_prompt(path: str) -> str:
    return Path(path).read_text().strip() if path else ""


class OpenAIChatAgent:
    """One instance = one conversation (keeps history). Create one per call."""

    MAX_TOOL_ROUNDS = 5

    def __init__(self, cfg: LlmConfig, system_prompt: str = "",
                 tools: ToolRegistry | None = None) -> None:
        self.cfg = cfg
        self.tools = registry if tools is None else tools
        self.messages: list[dict] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def _request(self, messages: list[dict]) -> dict:
        payload = {"model": self.cfg.model, "messages": messages}
        if self.tools:
            payload["tools"] = self.tools.specs()
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
        return data["choices"][0]["message"]

    async def respond(self, text: str) -> str:
        messages = self.messages + [{"role": "user", "content": text}]
        for _ in range(self.MAX_TOOL_ROUNDS + 1):
            msg = await asyncio.to_thread(self._request, messages)
            calls = msg.get("tool_calls")
            if not calls:
                break
            messages.append({"role": "assistant", "content": msg.get("content"),
                             "tool_calls": calls})
            for c in calls:
                fn = c["function"]
                t0 = time.monotonic()
                result = await self.tools.call(fn["name"], fn.get("arguments"))
                log.info("tool %s(%s) in %.0f ms -> %s", fn["name"],
                         _short(fn.get("arguments") or ""), (time.monotonic() - t0) * 1000,
                         _short(result))
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
        else:
            raise RuntimeError("too many tool-call rounds")
        reply = (msg.get("content") or "").strip()
        # only commit the turn once it succeeded, so a failure leaves history consistent
        self.messages = messages + [{"role": "assistant", "content": reply}]
        return reply
