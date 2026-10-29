import argparse
import asyncio
import logging
import os
import sqlite3

from . import __version__
from .agent import OpenAIChatAgent, ToolRegistry, load_system_prompt, registry, web_tools
from .assistant import AssistantHandler
from .config import Config, load_config
from .db import connect, migrate
from .db.migrations import MIGRATIONS
from .reminders.scheduler import ReminderScheduler
from .reminders.store import ReminderStore
from .reminders.tools import reminder_tools
from .sip import SipServer
from .stt import OpenAITranscriber
from .tts import OpenAISynthesizer


def build_app(
    cfg: Config, prompt: str
) -> tuple[AssistantHandler, ReminderStore | None, sqlite3.Connection | None,
           ReminderScheduler | None]:
    """Wire up the handler and (when enabled) the reminder store + scheduler.

    Returns the handler plus the store, its connection and the scheduler, or
    ``(handler, None, None, None)`` when reminders are disabled. The DB is only opened
    when reminders are enabled, so a disabled feature never creates a file. The agent
    factory builds a fresh registry per call with the reminder tools bound to that
    call's phone; the tools wake the scheduler on create/delete.

    The scheduler needs a :class:`SipServer`, which in turn needs this handler, so the
    server is attached later with :meth:`ReminderScheduler.set_server`.
    """
    base_tools = list(registry._tools.values()) + web_tools(cfg.tools.web)
    conn: sqlite3.Connection | None = None
    store: ReminderStore | None = None
    scheduler: ReminderScheduler | None = None
    if cfg.tools.reminders.enabled:
        conn = connect(cfg.db.path)
        migrate(conn, MIGRATIONS)
        store = ReminderStore(conn)
        scheduler = ReminderScheduler(store, cfg.tools.reminders)

    def make_agent(call):
        tools = list(base_tools)
        if store is not None and scheduler is not None:
            tools += reminder_tools(
                store,
                tz=cfg.tools.reminders.timezone,
                default_phone=cfg.tools.reminders.default_phone,
                phones=cfg.phones,
                call_phone=call.phone,
                on_change=scheduler.wake,
            )
        return OpenAIChatAgent(cfg.llm, prompt, ToolRegistry(tools))

    handler = AssistantHandler(cfg.audio, OpenAITranscriber(cfg.stt), OpenAISynthesizer(cfg.tts),
                               make_agent, cfg.llm.greeting)
    return handler, store, conn, scheduler


async def run(args) -> None:
    cfg = load_config(args.config)
    prompt = load_system_prompt(cfg.llm.system_prompt_file)   # read once at startup
    handler, _store, conn, scheduler = build_app(cfg, prompt)
    server = SipServer(cfg.sip, handler, cfg.phones)
    if scheduler is not None:
        scheduler.set_server(server)
    await server.start()
    if scheduler is not None:
        await scheduler.start()
    print(f"agent-sip {__version__} ready on {server.local_ip}:{cfg.sip.port}. "
          "Lift the handset! (Ctrl+C to quit)")
    try:
        await asyncio.Event().wait()
    finally:
        if scheduler is not None:
            await scheduler.stop()
        await server.stop()
        if conn is not None:
            conn.close()


def main() -> None:
    p = argparse.ArgumentParser(prog="agent-sip", description=__doc__)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config", default="config.toml" if os.path.exists("config.toml") else None,
                   help="TOML config file (default: ./config.toml if present)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
