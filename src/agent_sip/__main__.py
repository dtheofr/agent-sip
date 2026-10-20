import argparse
import asyncio
import logging
import os

from .agent import OpenAIChatAgent, ToolRegistry, load_system_prompt, registry, web_tools
from .assistant import AssistantHandler
from .config import load_config
from .sip import SipServer
from .stt import OpenAITranscriber
from .tts import OpenAISynthesizer


async def run(args) -> None:
    cfg = load_config(args.config)
    prompt = load_system_prompt(cfg.llm.system_prompt_file)   # read once at startup
    tools = ToolRegistry(list(registry._tools.values()) + web_tools(cfg.tools))
    handler = AssistantHandler(cfg.audio, OpenAITranscriber(cfg.stt), OpenAISynthesizer(cfg.tts),
                               lambda: OpenAIChatAgent(cfg.llm, prompt, tools), cfg.llm.greeting)
    server = SipServer(cfg.sip, handler, cfg.phones)
    await server.start()
    print(f"Ready on {server.local_ip}:{cfg.sip.port}. Lift the handset! (Ctrl+C to quit)")
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main() -> None:
    p = argparse.ArgumentParser(prog="agent-sip", description=__doc__)
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
