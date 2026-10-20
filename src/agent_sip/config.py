"""Configuration: defaults < TOML file < environment variables.

Sections mirror the dataclasses: a dataclass-typed field is a TOML table
(``[tools.web]``) and the env var for a key is ``AGENT_SIP_<PATH>_<KEY>`` with the
dotted path joined by ``_`` (e.g. ``AGENT_SIP_TOOLS_WEB_TAVILY_API_KEY``,
``AGENT_SIP_DB_PATH``).
"""
import dataclasses
import json
import os
import tomllib
import typing
import zoneinfo
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENV_PREFIX = "AGENT_SIP"


@dataclass
class SipConfig:
    local_ip: str = ""
    bind_host: str = "0.0.0.0"
    port: int = 5060
    rtp_port_min: int = 10000
    rtp_port_max: int = 10100
    local_user: str = "agent"


@dataclass
class PhoneConfig:
    """A known phone/ATA. Incoming calls from its IP are tagged with ``name``."""
    name: str = "phone"
    ip: str = ""
    port: int = 5060
    user: str = "phone"      # user part of the phone's SIP URI (used when ringing it)


@dataclass
class AudioConfig:
    vad: str = "silero"             # "silero" (needs the [vad] extra, `make install`) or "energy"
    speech_threshold: float = 500   # energy VAD: RMS above which a frame is speech
    vad_threshold: float = 0.5      # silero VAD: speech probability threshold
    silero_model: str = "models/silero_vad.onnx"  # fetched by `make install`
    barge_in: bool = True           # caller can interrupt the agent while it is speaking
    barge_in_min_speech: float = 0.3  # seconds of continuous speech needed to interrupt
    silence_end: float = 1.5
    no_speech_timeout: float = 8.0
    max_record: float = 20.0
    earcons: bool = True            # waiting-feedback sounds master switch
    earcon_volume: float = 0.25     # 0-1 amplitude scale
    beep: bool = True               # beep when the end of the caller's input is detected
    beep_freq: float = 800
    beep_duration: float = 0.12
    melody: bool = True             # looping pattern while waiting for the reply
    melody_delay: float = 0.4       # wait before the melody starts
    melody_notes: str = "A4,E5"     # comma-separated note names; "-" is a rest
    melody_note_duration: float = 0.3
    melody_gap: float = 2.0         # silence between repetitions


@dataclass
class SttConfig:
    """OpenAI-shaped transcription API (POST {base_url}/audio/transcriptions)."""
    base_url: str = "http://localhost:8000/v1"
    api_key: str = ""
    model: str = "whisper-1"
    language: str = ""       # e.g. "en"; empty = auto-detect
    timeout: float = 30.0
    extra: dict[str, Any] = field(default_factory=dict)  # custom form fields (temperature, prompt...)


@dataclass
class TtsConfig:
    """OpenAI-shaped speech API (POST {base_url}/audio/speech)."""
    base_url: str = "http://localhost:8001/v1"
    api_key: str = ""
    model: str = "tts-1"
    voice: str = "alloy"
    response_format: str = "wav"   # wav (recommended), pcm, or anything ffmpeg can read
    pcm_sample_rate: int = 24000   # only used when the server returns raw pcm
    timeout: float = 60.0
    extra: dict[str, Any] = field(default_factory=dict)  # custom JSON fields (speed, instructions...)


@dataclass
class LlmConfig:
    """OpenAI-shaped chat API (POST {base_url}/chat/completions)."""
    base_url: str = "http://localhost:8002/api/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    system_prompt_file: str = "prompts/system.md"   # external file; empty = no system prompt
    greeting: str = "Hello! How can I help?"        # spoken on pickup; empty = silent
    timeout: float = 60.0
    extra: dict[str, Any] = field(default_factory=dict)  # custom JSON fields (temperature...)


@dataclass
class WebToolsConfig:
    """Web tools for the agent: web_search (Tavily) and fetch_url (local)."""
    tavily_api_key: str = ""          # empty = web_search disabled
    tavily_base_url: str = "https://api.tavily.com"
    search_max_results: int = 3
    search_depth: str = "basic"       # basic | advanced
    fetch_enabled: bool = True
    fetch_max_chars: int = 4000       # truncate text returned to the LLM
    fetch_max_bytes: int = 1000000    # download cap
    timeout: float = 15.0


@dataclass
class RemindersConfig:
    """Reminder tools + scheduler (see docs/reminders-plan.md)."""
    enabled: bool = True              # register tools + start scheduler
    timezone: str = ""                # IANA name; empty = system local
    default_phone: str = ""           # fallback; empty = first [[phones]] entry
    ring_timeout: float = 30.0        # seconds before cancelling an unanswered call
    retry_attempts: int = 3           # total calls per occurrence
    retry_interval: float = 300.0     # seconds between attempts
    max_late: float = 3600.0          # startup recovery window
    keep_days: int = 7                # retention of done/missed rows


@dataclass
class ToolsConfig:
    """Tool families; one subsection per family."""
    web: WebToolsConfig = field(default_factory=WebToolsConfig)
    reminders: RemindersConfig = field(default_factory=RemindersConfig)


@dataclass
class DbConfig:
    """SQLite file shared by stateful features (reminders, ...)."""
    path: str = "data/agent-sip.db"


@dataclass
class Config:
    sip: SipConfig = field(default_factory=SipConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    db: DbConfig = field(default_factory=DbConfig)
    phones: list[PhoneConfig] = field(default_factory=list)  # [[phones]] tables; no env override


def _coerce(raw, typ):
    if typing.get_origin(typ) is dict:
        return raw if isinstance(raw, dict) else json.loads(raw)
    if typ is str and isinstance(raw, list):
        return ",".join(str(x) for x in raw)
    if typ is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return typ(raw)


def _is_dataclass_type(typ) -> bool:
    return isinstance(typ, type) and dataclasses.is_dataclass(typ)


def _apply_section(obj, values, env, path: list[str]) -> None:
    """Apply a TOML table (plus env overrides) to a dataclass, recursing into
    dataclass-typed fields. ``path`` is the dotted location for error messages."""
    where = ".".join(path)
    if not isinstance(values, dict):
        raise TypeError(f"[{where}] must be a table")
    unknown = set(values) - {f.name for f in dataclasses.fields(obj)}
    if unknown:
        msg = f"Unknown keys in [{where}]: {sorted(unknown)}"
        if path == ["tools"]:
            msg += " (tool settings moved into subsections, e.g. [tools.web])"
        raise ValueError(msg)
    for f in dataclasses.fields(obj):
        field_path = [*path, f.name]
        if _is_dataclass_type(f.type):
            _apply_section(getattr(obj, f.name), values.get(f.name, {}), env, field_path)
            continue
        raw = values.get(f.name)
        env_key = f"{ENV_PREFIX}_{'_'.join(field_path)}".upper()
        if env_key in env:
            raw = env[env_key]
        if raw is not None:
            setattr(obj, f.name, _coerce(raw, f.type))


def load_config(path: str | os.PathLike | None = None, env=None) -> Config:
    env = os.environ if env is None else env
    data: dict = {}
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        data = tomllib.loads(p.read_text())

    cfg = Config()
    unknown = set(data) - {f.name for f in dataclasses.fields(cfg)}
    if unknown:
        raise ValueError(f"Unknown top-level keys: {sorted(unknown)}")
    for f in dataclasses.fields(cfg):
        if f.name == "phones":
            continue
        if _is_dataclass_type(f.type):
            _apply_section(getattr(cfg, f.name), data.get(f.name, {}), env, [f.name])
            continue
        raw = data.get(f.name)
        env_key = f"{ENV_PREFIX}_{f.name}".upper()
        if env_key in env:
            raw = env[env_key]
        if raw is not None:
            setattr(cfg, f.name, _coerce(raw, f.type))

    from .audio.earcons import parse_melody
    try:
        parse_melody(cfg.audio.melody_notes)
    except ValueError as e:
        raise ValueError(f"[audio] melody_notes: {e}") from None
    phone_keys = {f.name for f in dataclasses.fields(PhoneConfig)}
    for raw in data.get("phones", []):
        unknown = set(raw) - phone_keys
        if unknown:
            raise ValueError(f"Unknown keys in [[phones]]: {sorted(unknown)}")
        cfg.phones.append(PhoneConfig(**raw))
    names = [p.name for p in cfg.phones]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate phone names in [[phones]]")

    reminders = cfg.tools.reminders
    tools_table = data.get("tools", {})
    reminders_configured = (isinstance(tools_table, dict) and "reminders" in tools_table) or any(
        k.startswith(f"{ENV_PREFIX}_TOOLS_REMINDERS_") for k in env)
    if reminders_configured and reminders.enabled and not cfg.phones:
        raise ValueError("[tools.reminders] enabled requires at least one [[phones]] entry")
    if reminders.timezone:
        try:
            zoneinfo.ZoneInfo(reminders.timezone)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(
                f"[tools.reminders] timezone: invalid IANA timezone {reminders.timezone!r}"
            ) from e
    return cfg
