#!/usr/bin/env python3
"""
Socotel S63 + Linksys: raw SIP endpoint with RTP audio (G.711 u-law).

Flow when you lift the handset:
  1. Linksys sends INVITE -> we answer 200 OK
  2. We play PROMPT_FILE
  3. A beep
  4. We record what you say (stops after a silence, or on timeout)
  5. We play your recording back (optional) and save it to ./recordings/

Usage:
  python3 socotel_voice.py [prompt_file]      # wait for handset pickup
  python3 socotel_voice.py [prompt_file] ring # also lets you ring the phone

Requirements: Python 3.8+, ffmpeg in PATH (for mp3/ogg/any WAV format).
Open UDP 5060 (SIP) and UDP 10000 (RTP) in your firewall.
"""
import array
import math
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid
import wave
from datetime import datetime

# ------------------------- Configuration -------------------------
PC_IP = "192.168.1.22"
LINKSYS_IP = "192.168.1.17"
SIP_PORT = 5060
RTP_PORT = 10000
USER = "socotel"

PROMPT_FILE = "prompt.wav"
RECORD_DIR = "recordings"

SPEECH_THRESHOLD = 500      # RMS (0-32767) above which we consider "speech"
SILENCE_END = 1.5           # seconds of silence after speech => stop recording
NO_SPEECH_TIMEOUT = 8.0     # stop if nothing is said within this time
MAX_RECORD = 20.0           # hard limit in seconds
PLAYBACK_RECORDING = True   # replay what was recorded
# -----------------------------------------------------------------

# ---------------------- G.711 u-law codec ------------------------
BIAS, CLIP = 0x84, 32635


def lin2ulaw(s):
    sign = 0x80 if s < 0 else 0
    s = min(abs(s), CLIP) + BIAS
    exp = max(0, s.bit_length() - 8)
    mant = (s >> (exp + 3)) & 0x0F
    return ~(sign | (exp << 4) | mant) & 0xFF


def _ulaw2lin(u):
    u = ~u & 0xFF
    s = (((u & 0x0F) << 3) + BIAS) << ((u >> 4) & 7)
    s -= BIAS
    return -s if u & 0x80 else s


ULAW_DEC = [_ulaw2lin(i) for i in range(256)]


def encode_pcm(pcm):
    return bytes(lin2ulaw(s) for s in pcm)


# --------------------------- Audio I/O ---------------------------
def load_audio(path):
    """Return array('h') of 8 kHz mono 16-bit samples."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ar", "8000", "-ac", "1",
             "-f", "s16le", "-"],
            capture_output=True, check=True).stdout
        pcm = array.array("h")
        pcm.frombytes(out)
        return pcm
    except FileNotFoundError:
        pass  # no ffmpeg: fall back to a WAV that is already 8 kHz mono 16-bit
    with wave.open(path, "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (8000, 1, 2):
            raise SystemExit("Install ffmpeg, or provide a WAV 8000 Hz / mono / 16-bit.")
        pcm = array.array("h")
        pcm.frombytes(w.readframes(w.getnframes()))
        return pcm


def make_beep(freq=1000, dur=0.25, amp=8000):
    n = int(8000 * dur)
    return array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / 8000))
                             for i in range(n)))


def save_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(pcm.tobytes())


# ----------------------------- RTP -------------------------------
rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rtp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rtp_sock.bind(("0.0.0.0", RTP_PORT))

rtp_state = {"seq": 0, "ts": 0, "ssrc": uuid.uuid4().int & 0xFFFFFFFF}
rec = {"on": False, "pcm": array.array("h")}
stop_event = threading.Event()


def rtp_receiver():
    while True:
        data, _ = rtp_sock.recvfrom(2048)
        if not rec["on"] or len(data) < 12:
            continue
        off = 12 + 4 * (data[0] & 0x0F)               # skip CSRC list
        if data[0] & 0x10 and len(data) >= off + 4:    # skip header extension
            off += 4 + 4 * struct.unpack("!H", data[off + 2:off + 4])[0]
        if (data[1] & 0x7F) != 0:                      # only PCMU
            continue
        rec["pcm"].extend(ULAW_DEC[b] for b in data[off:])


def send_audio(pcm, remote):
    """Send PCM samples as 20 ms RTP packets (real-time paced)."""
    payload = encode_pcm(pcm)
    t0 = time.perf_counter()
    for n, i in enumerate(range(0, len(payload), 160)):
        if stop_event.is_set():
            return False
        chunk = payload[i:i + 160].ljust(160, b"\xff")  # 0xFF = u-law silence
        header = struct.pack("!BBHII", 0x80, 0, rtp_state["seq"] & 0xFFFF,
                             rtp_state["ts"] & 0xFFFFFFFF, rtp_state["ssrc"])
        rtp_sock.sendto(header + chunk, remote)
        rtp_state["seq"] += 1
        rtp_state["ts"] += 160
        delay = t0 + (n + 1) * 0.02 - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
    return True


def record_until_silence():
    rec["pcm"] = array.array("h")
    rec["on"] = True
    start = time.time()
    idx = 0
    heard_speech = False
    last_voice = start
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
            chunk = rec["pcm"][idx:]
            idx += len(chunk)
            now = time.time()
            if chunk:
                rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
                if rms > SPEECH_THRESHOLD:
                    heard_speech = True
                    last_voice = now
            if heard_speech and now - last_voice > SILENCE_END:
                break
            if not heard_speech and now - start > NO_SPEECH_TIMEOUT:
                break
            if now - start > MAX_RECORD:
                break
    finally:
        rec["on"] = False
    return rec["pcm"], heard_speech


def run_session(remote, prompt, beep):
    """Executed in a thread once the call is established."""
    stop_event.clear()
    time.sleep(0.5)  # let the ACK arrive / the audio path settle
    print(f"[audio] RTP -> {remote[0]}:{remote[1]}")

    if not send_audio(prompt, remote):
        return
    send_audio(beep, remote)

    print("[audio] recording... speak now")
    pcm, heard = record_until_silence()
    if stop_event.is_set():
        print("[audio] call ended during recording")
    if not heard:
        print("[audio] no speech detected")
        return

    os.makedirs(RECORD_DIR, exist_ok=True)
    path = os.path.join(RECORD_DIR, datetime.now().strftime("rec_%Y%m%d_%H%M%S.wav"))
    save_wav(path, pcm)
    print(f"[audio] saved {path} ({len(pcm) / 8000:.1f}s)")

    # >>> process the recording here (speech-to-text, command, etc.) <<<

    if PLAYBACK_RECORDING and not stop_event.is_set():
        time.sleep(0.3)
        send_audio(pcm, remote)


# ----------------------------- SIP -------------------------------
sip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sip_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sip_sock.bind(("0.0.0.0", SIP_PORT))

SDP = (
    "v=0\r\n"
    f"o=python 1 1 IN IP4 {PC_IP}\r\n"
    "s=-\r\n"
    f"c=IN IP4 {PC_IP}\r\n"
    "t=0 0\r\n"
    f"m=audio {RTP_PORT} RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n"
    "a=ptime:20\r\n"
    "a=sendrecv\r\n"
)

call = {}       # outgoing call state (we ring the phone)
incoming = {}   # incoming call state (handset lifted)
assets = {}     # prompt + beep samples


def rand(n=8):
    return uuid.uuid4().hex[:n]


def send(msg, addr):
    sip_sock.sendto(msg.encode(), addr)


def parse(data):
    text = data.decode(errors="replace")
    head, _, body = text.partition("\r\n\r\n")
    lines = head.split("\r\n")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers.setdefault(k.strip().lower(), []).append(v.strip())
    return lines[0], headers, body


def rtp_target_from_sdp(body):
    """Extract (ip, port) of the remote RTP endpoint from an SDP body."""
    ip = port = None
    for line in body.splitlines():
        if line.startswith("c=IN IP4 "):
            ip = line.split()[-1]
        elif line.startswith("m=audio "):
            port = int(line.split()[1])
    return (ip, port) if ip and port else None


def reply(h, code, reason, addr, to_tag=None, body=""):
    to = h["to"][0]
    if to_tag and "tag=" not in to:
        to += f";tag={to_tag}"
    lines = [f"SIP/2.0 {code} {reason}"]
    lines += [f"Via: {v}" for v in h["via"]]
    lines += [
        f"From: {h['from'][0]}",
        f"To: {to}",
        f"Call-ID: {h['call-id'][0]}",
        f"CSeq: {h['cseq'][0]}",
        f"Contact: <sip:python@{PC_IP}:{SIP_PORT}>",
    ]
    if body:
        lines.append("Content-Type: application/sdp")
    lines += [f"Content-Length: {len(body)}", "", body]
    send("\r\n".join(lines), addr)


def request(method, branch, cseq, to_tag=None, body=""):
    to = f"<sip:{USER}@{LINKSYS_IP}>" + (f";tag={to_tag}" if to_tag else "")
    lines = [
        f"{method} sip:{USER}@{LINKSYS_IP}:5060 SIP/2.0",
        f"Via: SIP/2.0/UDP {PC_IP}:{SIP_PORT};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:python@{PC_IP}>;tag={call['from_tag']}",
        f"To: {to}",
        f"Call-ID: {call['call_id']}",
        f"CSeq: {cseq} {method}",
        f"Contact: <sip:python@{PC_IP}:{SIP_PORT}>",
    ]
    if body:
        lines.append("Content-Type: application/sdp")
    lines += [f"Content-Length: {len(body)}", "", body]
    send("\r\n".join(lines), (LINKSYS_IP, 5060))


def start_session(remote):
    threading.Thread(target=run_session,
                     args=(remote, assets["prompt"], assets["beep"]),
                     daemon=True).start()


def ring():
    call.clear()
    call.update(call_id=f"{rand(12)}@{PC_IP}", from_tag=rand(),
                branch="z9hG4bK" + rand(), to_tag=None, answered=False)
    request("INVITE", call["branch"], 1, body=SDP)
    print("-> INVITE sent, the phone should ring")


def hangup():
    if not call:
        return
    stop_event.set()
    if call["answered"]:
        request("BYE", "z9hG4bK" + rand(), 2, to_tag=call["to_tag"])
    else:
        request("CANCEL", call["branch"], 1)
    print("-> hangup / cancel sent")


def on_response(start, h, body):
    code = int(start.split()[1])
    if h["cseq"][0].split()[1] != "INVITE" or not call:
        return
    if code in (180, 183):
        print("   ringing...")
    elif code == 200:
        if call["answered"]:
            return  # retransmission
        to_tag = h["to"][0].split("tag=")[-1]
        call.update(answered=True, to_tag=to_tag)
        request("ACK", "z9hG4bK" + rand(), 1, to_tag=to_tag)
        print("   HANDSET PICKED UP (outgoing call)")
        remote = rtp_target_from_sdp(body)
        if remote:
            start_session(remote)
    elif code >= 300:
        tag = h["to"][0].split("tag=")[-1] if "tag=" in h["to"][0] else None
        request("ACK", call["branch"], 1, to_tag=tag)
        print(f"   call failed: {start}")


def on_request(start, h, body, addr):
    method = start.split()[0]
    if method == "INVITE":
        call_id = h["call-id"][0]
        if incoming.get("call_id") == call_id:      # retransmitted INVITE
            reply(h, 200, "OK", addr, to_tag=incoming["tag"], body=SDP)
            return
        number = start.split()[1].removeprefix("sip:").split("@")[0]
        print(f"<- Handset lifted, dialed: '{number}'")
        incoming.update(call_id=call_id, tag=rand())
        reply(h, 180, "Ringing", addr, to_tag=incoming["tag"])
        reply(h, 200, "OK", addr, to_tag=incoming["tag"], body=SDP)
        remote = rtp_target_from_sdp(body)
        if remote:
            start_session(remote)
        else:
            print("!! No RTP address in the INVITE's SDP")
    elif method == "BYE":
        reply(h, 200, "OK", addr)
        stop_event.set()
        incoming.clear()
        print("<- Handset hung up")
    elif method == "CANCEL":
        reply(h, 200, "OK", addr)
        stop_event.set()
        incoming.clear()
    elif method != "ACK":
        reply(h, 200, "OK", addr)  # OPTIONS, NOTIFY...


def sip_listener():
    while True:
        data, addr = sip_sock.recvfrom(65535)
        try:
            start, h, body = parse(data)
            if start.startswith("SIP/2.0"):
                on_response(start, h, body)
            else:
                on_request(start, h, body, addr)
        except Exception as e:
            print("parse error:", e)


# ----------------------------- Main ------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]
    prompt_path = args[0] if args and args[0] != "ring" else PROMPT_FILE

    if not os.path.exists(prompt_path):
        raise SystemExit(f"Prompt file not found: {prompt_path}")

    assets["prompt"] = load_audio(prompt_path)
    assets["beep"] = make_beep()
    print(f"Prompt loaded: {len(assets['prompt']) / 8000:.1f}s")

    threading.Thread(target=rtp_receiver, daemon=True).start()
    threading.Thread(target=sip_listener, daemon=True).start()
    print(f"SIP {PC_IP}:{SIP_PORT} / RTP {RTP_PORT} ready. Lift the handset!")

    try:
        if "ring" in args:
            input("ENTER to ring the Socotel...\n")
            ring()
            input("ENTER to hang up...\n")
            hangup()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBye.")