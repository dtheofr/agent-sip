"""SIP message parsing and building."""
from dataclasses import dataclass, field


@dataclass
class SipMessage:
    start_line: str
    headers: dict[str, list[str]] = field(default_factory=dict)  # lower-case names
    body: str = ""

    @property
    def is_response(self) -> bool:
        return self.start_line.startswith("SIP/2.0")

    @property
    def method(self) -> str:
        """Request method (requests) or CSeq method (responses)."""
        if self.is_response:
            return self.header("cseq").split()[1]
        return self.start_line.split()[0]

    @property
    def uri(self) -> str:
        return self.start_line.split()[1]

    @property
    def status(self) -> int:
        return int(self.start_line.split()[1])

    def header(self, name: str, default: str = "") -> str:
        vals = self.headers.get(name.lower())
        return vals[0] if vals else default

    @property
    def call_id(self) -> str:
        return self.header("call-id")


def parse(data: bytes) -> SipMessage:
    text = data.decode(errors="replace")
    head, _, body = text.partition("\r\n\r\n")
    lines = head.split("\r\n")
    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers.setdefault(k.strip().lower(), []).append(v.strip())
    return SipMessage(lines[0], headers, body)


def header_uri(value: str) -> str:
    """'"Name" <sip:a@b>;tag=x' -> 'sip:a@b'."""
    if "<" in value and ">" in value:
        return value[value.index("<") + 1:value.index(">")]
    return value.split(";")[0].strip()


def header_tag(value: str) -> str | None:
    if "tag=" not in value:
        return None
    return value.split("tag=", 1)[1].split(";")[0].strip()


def _finish(lines: list[str], body: str) -> bytes:
    if body:
        lines.append("Content-Type: application/sdp")
    body_b = body.encode()
    lines += [f"Content-Length: {len(body_b)}", "", ""]
    return "\r\n".join(lines).encode() + body_b


def build_response(req: SipMessage, code: int, reason: str, *, contact: str,
                   to_tag: str | None = None, body: str = "") -> bytes:
    to = req.header("to")
    if to_tag and "tag=" not in to:
        to += f";tag={to_tag}"
    lines = [f"SIP/2.0 {code} {reason}"]
    lines += [f"Via: {v}" for v in req.headers.get("via", [])]
    lines += [
        f"From: {req.header('from')}",
        f"To: {to}",
        f"Call-ID: {req.call_id}",
        f"CSeq: {req.header('cseq')}",
        f"Contact: <{contact}>",
    ]
    return _finish(lines, body)


def build_request(method: str, uri: str, *, via: str, branch: str, from_: str, to: str,
                  call_id: str, cseq: int, contact: str, body: str = "") -> bytes:
    lines = [
        f"{method} {uri} SIP/2.0",
        f"Via: SIP/2.0/UDP {via};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: {from_}",
        f"To: {to}",
        f"Call-ID: {call_id}",
        f"CSeq: {cseq} {method}",
        f"Contact: <{contact}>",
    ]
    return _finish(lines, body)
