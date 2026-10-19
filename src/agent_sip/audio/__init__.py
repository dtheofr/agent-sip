"""Audio helpers. Internal format everywhere: 8 kHz mono signed 16-bit (array('h'))."""

from .io import SAMPLE_RATE, decode_audio_bytes, load_audio, make_beep, resample, save_wav
from .recorder import record_until_silence, rms

__all__ = ["SAMPLE_RATE", "decode_audio_bytes", "load_audio", "make_beep", "resample", "save_wav", "record_until_silence", "rms"]
