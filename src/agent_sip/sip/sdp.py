"""Minimal SDP: offer/answer for a single PCMU audio stream."""


def build_sdp(ip: str, rtp_port: int) -> str:
    return (
        "v=0\r\n"
        f"o=agent-sip 1 1 IN IP4 {ip}\r\n"
        "s=-\r\n"
        f"c=IN IP4 {ip}\r\n"
        "t=0 0\r\n"
        f"m=audio {rtp_port} RTP/AVP 0\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
        "a=ptime:20\r\n"
        "a=sendrecv\r\n"
    )


def parse_rtp_target(body: str) -> tuple[str, int] | None:
    """Return the remote (ip, port) for the audio stream, or None."""
    ip = port = None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("c=IN IP4 "):
            ip = line.split()[-1]
        elif line.startswith("m=audio "):
            port = int(line.split()[1])
    return (ip, port) if ip and port else None
