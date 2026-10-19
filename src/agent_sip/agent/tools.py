"""Tools the LLM can call. To add one, decorate a function with ``@tool`` (see bottom of file).

The JSON schema is the OpenAI ``parameters`` object. Handlers take keyword args and return
a string (or JSON-serialisable value); they may be sync or async. Sync handlers run inline,
so keep them fast or use ``asyncio.to_thread`` inside an async handler.
"""
import inspect
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

NO_ARGS = {"type": "object", "properties": {}}


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict = None  # JSON schema; defaults to no arguments

    def spec(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters or NO_ARGS}}


class ToolRegistry:
    def __init__(self, tools: list[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools:
            self.add(t)

    def add(self, t: Tool) -> Tool:
        self._tools[t.name] = t
        return t

    def specs(self) -> list[dict]:
        return [t.spec() for t in self._tools.values()]

    def __bool__(self) -> bool:
        return bool(self._tools)

    async def call(self, name: str, arguments: str | dict) -> str:
        """Run a tool; errors are returned as text so the model can recover."""
        t = self._tools.get(name)
        if t is None:
            return f"error: unknown tool {name!r}"
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else arguments
            result = t.handler(**args)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:  # noqa: BLE001 - reported back to the model
            return f"error: {type(e).__name__}: {e}"
        return result if isinstance(result, str) else json.dumps(result)


# Global registry holding every built-in tool; pass a custom ToolRegistry to an agent to override.
registry = ToolRegistry()


def tool(name: str, description: str, parameters: dict = None):
    """Decorator: register a function as a tool in the default registry."""
    def deco(fn):
        registry.add(Tool(name, description, fn, parameters))
        return fn
    return deco


# --- built-in tools -------------------------------------------------------------------------

@tool("get_current_datetime", "Get the current local date, time and weekday.")
def get_current_datetime() -> str:
    now = datetime.now().astimezone()
    return now.strftime("%A, %Y-%m-%d %H:%M:%S %Z (UTC%z)")
