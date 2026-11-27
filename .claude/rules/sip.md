---
paths:
  - "src/agent_sip/sip/**"
---
# SIP / RTP layer
- App-agnostic: no import from stt/tts/agent/reminders/assistant. Behaviour goes in a
  `CallHandler`; handlers use the `Call` API only.
- `message.py`, `sdp.py`, `g711.py` stay pure functions (no I/O, no asyncio).
- `server.py` owns dialogs; `rtp.py` is one socket per call.
- UDP: any request or response may be lost or duplicated. A new transaction needs a
  retransmission story (RFC 3261 §17) and a loopback test that drops a packet.
- Match transactions by Via branch + CSeq, dialogs by Call-ID + tags.
- Log with the `[call_id[:8]]` prefix.
