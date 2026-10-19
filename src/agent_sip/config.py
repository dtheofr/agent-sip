"""Configuration: defaults < TOML file < environment variables.

Env var for a key is ``AGENT_SIP_<SECTION>_<KEY>`` (e.g. ``AGENT_SIP_SIP_PORT``).
"""
import dataclasses
import json
import os
import typing
import tomllib
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

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
    speech_threshold: float = 500
    silence_end: float = 1.5
    no_speech_timeout: float = 8.0
    max_record: float = 20.0


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
class Config:
    sip: SipConfig = field(default_factory=SipConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    phones: list[PhoneConfig] = field(default_factory=list)  # [[phones]] tables; no env override


def _coerce(raw, typ):
    if typing.get_origin(typ) is dict:
        return raw if isinstance(raw, dict) else json.loads(raw)
    if typ is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return typ(raw)


def load_config(path: str | os.PathLike | None = None, env=None) -> Config:
    env = os.environ if env is None else env
    data: dict = {}
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        data = tomllib.loads(p.read_text())

    cfg = Config()
    for section in dataclasses.fields(cfg):
        if section.name == "phones":
            continue
        obj = getattr(cfg, section.name)
        values = data.get(section.name, {})
        known = {f.name for f in dataclasses.fields(obj)}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"Unknown keys in [{section.name}]: {sorted(unknown)}")
        for f in dataclasses.fields(obj):
            raw = values.get(f.name)
            env_key = f"{ENV_PREFIX}_{section.name}_{f.name}".upper()
            if env_key in env:
                raw = env[env_key]
            if raw is not None:
                setattr(obj, f.name, _coerce(raw, f.type))
    phone_keys = {f.name for f in dataclasses.fields(PhoneConfig)}
    for raw in data.get("phones", []):
        unknown = set(raw) - phone_keys
        if unknown:
            raise ValueError(f"Unknown keys in [[phones]]: {sorted(unknown)}")
        cfg.phones.append(PhoneConfig(**raw))
    names = [p.name for p in cfg.phones]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate phone names in [[phones]]")
    return cfg
