"""Audio helpers. Internal format everywhere: 8 kHz mono signed 16-bit (array('h'))."""

from .io import SAMPLE_RATE, load_audio, make_beep, save_wav
from .recorder import record_until_silence, rms

__all__ = ["SAMPLE_RATE", "load_audio", "make_beep", "save_wav", "record_until_silence", "rms"]
