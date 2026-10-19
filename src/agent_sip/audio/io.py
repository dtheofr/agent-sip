import array
import math
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


def make_beep(freq: float = 1000, dur: float = 0.25, amp: int = 8000) -> array.array:
    n = int(SAMPLE_RATE * dur)
    return array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
                             for i in range(n)))


def save_wav(path: str, pcm: array.array) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
