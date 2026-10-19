"""Echo handler: listen, transcribe, repeat with TTS, until the caller hangs up."""
import logging

from .audio import make_vad, play_interruptible, record_until_silence
from .config import AudioConfig
from .sip import Call, CallHandler
from .stt import Transcriber
from .tts import Synthesizer

log = logging.getLogger(__name__)


class EchoHandler(CallHandler):
    def __init__(self, audio: AudioConfig, stt: Transcriber, tts: Synthesizer) -> None:
        self.audio, self.stt, self.tts = audio, stt, tts

    async def on_call(self, call: Call) -> None:
        tag = call.call_id[:8]
        log.info("[%s] echo session started", tag)
        vad = make_vad(self.audio)
        barged = None
        while call.active:
            pcm, heard = await record_until_silence(
                call, vad,
                prefix=barged,
                silence_end=self.audio.silence_end,
                no_speech_timeout=self.audio.no_speech_timeout,
                max_record=self.audio.max_record,
            )
            barged = None
            if not heard:
                continue                      # keep waiting for the caller
            try:
                text = await self.stt.transcribe(pcm)
                log.info("[%s] caller said: %r", tag, text)
                if not text:
                    continue
                speech = await self.tts.synthesize(text)
            except Exception:
                log.exception("[%s] STT/TTS failed", tag)
                continue
            if self.audio.barge_in:
                barged = await play_interruptible(
                    call, speech, vad, min_speech=self.audio.barge_in_min_speech)
            else:
                await call.play(speech)
