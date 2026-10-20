"""Audio helpers. Internal format everywhere: 8 kHz mono signed 16-bit (array('h'))."""

from .earcons import make_beep, make_melody, parse_melody, thinking
from .io import SAMPLE_RATE, decode_audio_bytes, load_audio, resample, save_wav
from .recorder import play_interruptible, record_until_silence
from .vad import VAD, EnergyVAD, SileroVAD, make_vad, rms

__all__ = ["SAMPLE_RATE", "decode_audio_bytes", "load_audio", "make_beep", "make_melody",
           "parse_melody", "thinking", "resample", "save_wav", "record_until_silence",
           "play_interruptible", "rms", "VAD", "EnergyVAD", "SileroVAD", "make_vad"]
