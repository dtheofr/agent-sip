"""G.711 u-law (PCMU) codec, pure Python."""
import array

BIAS, CLIP = 0x84, 32635


def _lin2ulaw(s: int) -> int:
    sign = 0x80 if s < 0 else 0
    s = min(abs(s), CLIP) + BIAS
    exp = max(0, s.bit_length() - 8)
    mant = (s >> (exp + 3)) & 0x0F
    return ~(sign | (exp << 4) | mant) & 0xFF


def _ulaw2lin(u: int) -> int:
    u = ~u & 0xFF
    s = (((u & 0x0F) << 3) + BIAS) << ((u >> 4) & 7)
    s -= BIAS
    return -s if u & 0x80 else s


_DECODE = [_ulaw2lin(i) for i in range(256)]
_ENCODE = bytes(_lin2ulaw(s - 65536 if s >= 32768 else s) for s in range(65536))  # index = s & 0xFFFF
ULAW_SILENCE = 0xFF


def encode(pcm) -> bytes:
    return bytes(_ENCODE[s & 0xFFFF] for s in pcm)


def decode(data: bytes) -> array.array:
    return array.array("h", (_DECODE[b] for b in data))
