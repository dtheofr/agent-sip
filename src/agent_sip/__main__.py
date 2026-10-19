import argparse
import asyncio
import logging
import os

from .config import load_config
from .echo import EchoHandler
from .sip import SipServer
from .stt import OpenAITranscriber
from .tts import OpenAISynthesizer


async def run(args) -> None:
    cfg = load_config(args.config)
    server = SipServer(cfg.sip, EchoHandler(cfg.audio, OpenAITranscriber(cfg.stt),
                                       OpenAISynthesizer(cfg.tts)), cfg.phones)
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
