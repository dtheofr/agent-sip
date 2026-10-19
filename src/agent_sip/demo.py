"""Demo handler ported from poc_sip.py: prompt, beep, record, save, replay."""
import asyncio
import logging
import os
from datetime import datetime

from .audio import load_audio, make_beep, record_until_silence, save_wav
from .audio.recorder import duration
from .config import AudioConfig, DemoConfig
from .sip import Call, CallHandler

log = logging.getLogger(__name__)


class DemoHandler(CallHandler):
    def __init__(self, demo: DemoConfig, audio: AudioConfig) -> None:
        if not os.path.exists(demo.prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {demo.prompt_file}")
        self.demo, self.audio = demo, audio
        self.prompt = load_audio(demo.prompt_file)
        self.beep = make_beep()
        log.info("Prompt loaded: %.1fs", duration(self.prompt))

    async def on_call(self, call: Call) -> None:
        await asyncio.sleep(0.5)  # let the ACK arrive / the audio path settle
        if not await call.play(self.prompt):
            return
        await call.play(self.beep)

        log.info("recording... speak now")
        pcm, heard = await record_until_silence(
            call,
            speech_threshold=self.audio.speech_threshold,
            silence_end=self.audio.silence_end,
            no_speech_timeout=self.audio.no_speech_timeout,
            max_record=self.audio.max_record,
        )
        if not heard:
            log.info("no speech detected")
            return

        os.makedirs(self.demo.record_dir, exist_ok=True)
        path = os.path.join(self.demo.record_dir,
                            datetime.now().strftime("rec_%Y%m%d_%H%M%S.wav"))
        save_wav(path, pcm)
        log.info("saved %s (%.1fs)", path, duration(pcm))

        if self.demo.playback_recording:
            await asyncio.sleep(0.3)
            await call.play(pcm)
