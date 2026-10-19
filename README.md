# agent-sip

Talk to one or many AI agents from a phone (e.g. an analog phone behind a Linksys/ATA) through SIP.

Pipeline (target): `phone ⇄ SIP/RTP ⇄ STT → Agent → TTS ⇄ phone`

| Package            | Status  | Role |
|--------------------|---------|------|
| `agent_sip.sip`    | working | SIP signalling + RTP (G.711 µ-law), multi-call, no app logic |
| `agent_sip.audio`  | working | 8 kHz PCM helpers: load/save, beep, silence-based recorder |
| `agent_sip.stt`    | working | `Transcriber` protocol + remote OpenAI-shaped client (`[stt]` config); local faster-whisper possible later |
| `agent_sip.tts`    | working | `Synthesizer` protocol + OpenAI-shaped `/audio/speech` client (`[tts]` config) |
| `agent_sip.agent`  | working | `Agent` protocol + OpenAI-shaped `/chat/completions` client (`[llm]`, system prompt in `prompts/system.md`) |
| `agent_sip.assistant` | working | Main handler: listen → STT → agent → TTS, history per call |
| `agent_sip.echo`   | working | Demo handler: listen → STT → TTS → repeat until hangup |

Pure standard library (Python ≥ 3.11). `ffmpeg` is only needed if the TTS returns something other than wav/pcm.

## Quick start

```sh
# edit config.toml: [[phones]], [stt], [tts] (needs reachable STT and TTS servers)
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
`[stt]` and `[tts]` accept an `extra` table of custom parameters merged into the request
(form fields for STT, JSON body for TTS), e.g. `extra = { speed = 1.1 }`; via env, pass JSON:
`AGENT_SIP_TTS_EXTRA='{"speed":1.1}'`.
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
