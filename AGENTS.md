# AGENTS.md

Guidance for coding agents working on agent-sip.

## Layout
- `src/agent_sip/sip/` — SIP/RTP transport. **Must stay app-agnostic**: behaviour goes in a
  `CallHandler` (`handler.py`); handlers only use the `Call` API (`call.py`).
  `message.py`/`sdp.py`/`g711.py` are pure functions; `server.py` owns dialogs; `rtp.py` one socket per call.
- `src/agent_sip/audio/` — shared helpers. Internal audio format is always **8 kHz mono int16 `array('h')`**.
- `stt/`, `tts/`, `agent/` — each exposes a small `Protocol` in `base.py`; implementations are added alongside.
  TTS must work with any OpenAI-shaped API (configurable base_url/api_key/model/voice).
- `echo.py` — reference handler (STT → TTS echo); `__main__.py` — CLI wiring only.
- `config.py` — dataclasses; TOML < env (`AGENT_SIP_<SECTION>_<KEY>`). Add new keys to
  the dataclass **and** `config.example.toml`.
- `examples/poc_sip.py` — original single-file proof of concept, kept for reference only.

## Conventions
- asyncio everywhere; no blocking calls in handlers (use `asyncio.to_thread` for CPU-bound STT).
- Core stays stdlib-only; heavy deps go in optional extras in `pyproject.toml`.
- Python ≥ 3.11, ruff line length 100.

## Versioning
- SemVer. `__version__` in `src/agent_sip/__init__.py` is the single source of truth;
  `pyproject.toml` reads it dynamically. Never edit a version in two places.
- Add user-visible changes to `CHANGELOG.md` under `[Unreleased]`.
- Release: move the changelog section to the new version, bump `__version__`, commit, then
  publish a GitHub Release tagged `vX.Y.Z`. The release workflow verifies the tag, attaches
  the build and then deploys that tag to the server.

## Commands
- `make test` — unittest suite (includes a loopback SIP call). Run before finishing.
- `make lint`, `make run`.
