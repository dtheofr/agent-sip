"""Voice activity detection on 8 kHz mono int16 frames (typically 20 ms RTP frames)."""
import array
import functools
import math
from pathlib import Path
from typing import Protocol


class VAD(Protocol):
    """Stateful per-call detector. Feed consecutive frames; get speech / not speech."""

    def is_speech(self, frame: array.array) -> bool: ...
    def reset(self) -> None: ...


def rms(samples) -> float:
    if not len(samples):
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class EnergyVAD:
    """Stdlib-only fallback: frame RMS above a threshold."""

    def __init__(self, threshold: float = 500) -> None:
        self.threshold = threshold

    def is_speech(self, frame) -> bool:
        return rms(frame) > self.threshold

    def reset(self) -> None:
        pass


@functools.lru_cache(maxsize=2)
def _load_silero_session(model_path: str):
    import onnxruntime as ort

    if not Path(model_path).is_file():
        raise RuntimeError(f"Silero model not found at {model_path!r}: run `make install`, "
                           "or set [audio] silero_model / vad = \"energy\"")
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = opts.intra_op_num_threads = 1
    return ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])


class SileroVAD:
    """Silero VAD v5 (ONNX) at 8 kHz. Needs ``pip install agent-sip[vad]``.

    The model works on 256-sample windows (32 ms); incoming frames are buffered and the
    last probability is reused until the next window is complete.
    """

    WINDOW = 256
    CONTEXT = 32

    def __init__(self, threshold: float = 0.5, model_path: str = "") -> None:
        import numpy as np

        self._np = np
        self.threshold = threshold
        self._session = _load_silero_session(model_path)
        self.reset()

    def reset(self) -> None:
        np = self._np
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(self.CONTEXT, dtype=np.float32)
        self._buf = np.zeros(0, dtype=np.float32)
        self.prob = 0.0

    def is_speech(self, frame) -> bool:
        np = self._np
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        self._buf = np.concatenate((self._buf, samples))
        while len(self._buf) >= self.WINDOW:
            chunk, self._buf = self._buf[:self.WINDOW], self._buf[self.WINDOW:]
            x = np.concatenate((self._context, chunk))[None, :]
            out, self._state = self._session.run(
                None, {"input": x, "state": self._state, "sr": np.array(8000, dtype=np.int64)})
            self._context = x[0, -self.CONTEXT:]
            self.prob = float(out[0][0])
        return self.prob >= self.threshold


def make_vad(audio) -> VAD:
    """Build a new VAD from an ``AudioConfig`` (call once per call: VADs are stateful)."""
    kind = audio.vad.lower()
    if kind == "energy":
        return EnergyVAD(audio.speech_threshold)
    if kind == "silero":
        return SileroVAD(audio.vad_threshold, audio.silero_model)
    raise ValueError(f"Unknown vad {audio.vad!r} (use 'energy' or 'silero')")
