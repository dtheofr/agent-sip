import array
import io
import subprocess
import wave

SAMPLE_RATE = 8000


def load_audio(path: str) -> array.array:
    """Load any audio file as 8 kHz mono 16-bit samples (uses ffmpeg when available)."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ar", str(SAMPLE_RATE), "-ac", "1",
             "-f", "s16le", "-"],
            capture_output=True, check=True).stdout
        pcm = array.array("h")
        pcm.frombytes(out)
        return pcm
    except FileNotFoundError:
        pass  # no ffmpeg: accept only a WAV already in the right format
    with wave.open(path, "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise RuntimeError("Install ffmpeg, or provide a WAV 8000 Hz / mono / 16-bit.")
        pcm = array.array("h")
        pcm.frombytes(w.readframes(w.getnframes()))
        return pcm


def save_wav(path: str, pcm: array.array) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


def resample(pcm: array.array, src: int, dst: int = SAMPLE_RATE) -> array.array:
    """Pure-python resampler: box-filter average when downsampling, linear otherwise."""
    if src == dst or not len(pcm):
        return pcm
    ratio = src / dst
    n = int(len(pcm) / ratio)
    out = array.array("h", bytes(2 * n))
    if ratio > 1:
        for i in range(n):
            a = int(i * ratio)
            b = max(a + 1, int((i + 1) * ratio))
            chunk = pcm[a:b]
            out[i] = sum(chunk) // len(chunk)
    else:
        last = len(pcm) - 1
        for i in range(n):
            pos = i * ratio
            j = int(pos)
            frac = pos - j
            out[i] = int(pcm[j] * (1 - frac) + pcm[min(j + 1, last)] * frac)
    return out


def _ffmpeg_decode(data: bytes) -> array.array:
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", "pipe:0", "-ar", str(SAMPLE_RATE), "-ac", "1",
             "-f", "s16le", "-"], input=data, capture_output=True, check=True).stdout
    except FileNotFoundError:
        raise RuntimeError("Audio format not supported without ffmpeg; "
                           "ask the TTS for response_format=wav or pcm.") from None
    pcm = array.array("h")
    pcm.frombytes(out)
    return pcm


def decode_audio_bytes(data: bytes, pcm_rate: int = 24000) -> array.array:
    """Decode a TTS response (WAV, raw s16le PCM, or anything ffmpeg reads) to 8 kHz mono."""
    if data[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(data), "rb") as w:
                if w.getsampwidth() == 2:
                    pcm = array.array("h")
                    pcm.frombytes(w.readframes(w.getnframes()))
                    ch = w.getnchannels()
                    if ch > 1:
                        pcm = array.array("h", (sum(pcm[i:i + ch]) // ch
                                                for i in range(0, len(pcm) - ch + 1, ch)))
                    return resample(pcm, w.getframerate())
        except (wave.Error, EOFError):
            pass  # e.g. streaming header with unknown length
        return _ffmpeg_decode(data)
    if data[:3] in (b"ID3",) or data[:2] in (b"\xff\xfb", b"\xff\xf3") or data[:4] in (b"OggS", b"fLaC"):
        return _ffmpeg_decode(data)
    # raw signed 16-bit little-endian mono PCM
    pcm = array.array("h")
    pcm.frombytes(data[: len(data) // 2 * 2])
    return resample(pcm, pcm_rate)
