# agent-sip

Talk to one or many AI agents from a phone (e.g. an analog phone behind a Linksys/ATA) through SIP.

Pipeline (target): `phone ⇄ SIP/RTP ⇄ STT → Agent → TTS ⇄ phone`

| Package            | Status  | Role |
|--------------------|---------|------|
| `agent_sip.sip`    | working | SIP signalling + RTP (G.711 µ-law), multi-call, no app logic |
| `agent_sip.audio`  | working | 8 kHz PCM helpers: load/save, beep, silence-based recorder |
| `agent_sip.stt`    | working | `Transcriber` protocol + remote OpenAI-shaped client (`[stt]` config); local faster-whisper possible later |
| `agent_sip.tts`    | stub    | `Synthesizer` protocol (any OpenAI-shaped `/v1/audio/speech`) |
| `agent_sip.agent`  | stub    | `Agent` protocol |
| `agent_sip.demo`   | working | Port of `examples/poc_sip.py`: prompt → beep → record → replay |

Pure standard library for now (Python ≥ 3.11, `ffmpeg` optional for loading non-8 kHz audio).

## Quick start

```sh
cp assets/your_prompt.wav assets/prompt.wav   # any format if ffmpeg is installed
make run          # creates .venv, config.toml (from config.example.toml), starts the server
make test         # unit + loopback call-flow tests
make help
```

Open UDP 5060 (SIP) and the RTP range (default 10000–10100) in your firewall, and point
the phone/ATA's SIP proxy/dial plan at this machine.

## Configuration

`config.toml` (see `config.example.toml`), overridden by env vars
`AGENT_SIP_<SECTION>_<KEY>`, e.g. `AGENT_SIP_SIP_PORT=5080`.
`sip.local_ip` is auto-detected when empty.
Phones are declared as repeated `[[phones]]` tables (name, ip, port, user); these are TOML-only.

## Writing your own behaviour

The SIP layer never needs changes: subclass `CallHandler`.

```python
from agent_sip.sip import Call, CallHandler, SipServer

class MyHandler(CallHandler):
    async def on_call(self, call: Call):
        await call.play(pcm)                      # 8 kHz mono int16 array('h')
        pcm_in, heard = await record_until_silence(call)
        ...
```

`on_call` runs per call, concurrently; it is cancelled on remote hangup and the call is
hung up when it returns. `SipServer.originate("name")` rings a phone declared in `[[phones]]` (not exposed in the CLI).
Incoming calls from a declared phone's IP get `call.phone = "name"`.

Limitations: UDP only, no auth/registration, PCMU only, no 200-OK retransmission timers.
