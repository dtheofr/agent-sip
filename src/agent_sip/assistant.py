"""Assistant handler: listen -> STT -> agent (LLM) -> TTS, one conversation per call."""
import array
import logging
from collections.abc import Callable

from .agent import Agent
from .audio import make_vad, play_interruptible, record_until_silence
from .config import AudioConfig
from .sip import Call, CallHandler
from .stt import Transcriber
from .tts import Synthesizer

log = logging.getLogger(__name__)


class AssistantHandler(CallHandler):
    def __init__(self, audio: AudioConfig, stt: Transcriber, tts: Synthesizer,
                 agent_factory: Callable[[], Agent], greeting: str = "") -> None:
        self.audio, self.stt, self.tts = audio, stt, tts
        self.agent_factory, self.greeting = agent_factory, greeting

    async def on_call(self, call: Call) -> None:
        tag = call.call_id[:8]
        agent = self.agent_factory()          # fresh history for every call
        vad = make_vad(self.audio)            # stateful: one per call
        log.info("[%s] assistant session started", tag)
        barged = None                         # caller audio captured by a barge-in
        if self.greeting:
            barged = await self._say(call, vad, self.greeting, tag)
        while call.active:
            pcm, heard = await record_until_silence(
                call, vad,
                silence_end=self.audio.silence_end,
                no_speech_timeout=self.audio.no_speech_timeout,
                max_record=self.audio.max_record,
                prefix=barged,
            )
            barged = None
            if not heard:
                continue
            try:
                text = await self.stt.transcribe(pcm)
                log.info("[%s] caller: %r", tag, text)
                if not text:
                    continue
                reply = await agent.respond(text)
                log.info("[%s] agent: %r", tag, reply)
            except Exception:
                log.exception("[%s] STT/agent failed", tag)
                continue
            if reply:
                barged = await self._say(call, vad, reply, tag)

    async def _say(self, call: Call, vad, text: str, tag: str) -> array.array | None:
        """Speak ``text``. Returns the caller's audio if they interrupted, else None."""
        try:
            pcm = await self.tts.synthesize(text)
            if not self.audio.barge_in:
                await call.play(pcm)
                return None
            captured = await play_interruptible(
                call, pcm, vad, min_speech=self.audio.barge_in_min_speech)
            if captured is not None:
                log.info("[%s] caller interrupted the agent", tag)
            return captured
        except Exception:
            log.exception("[%s] TTS failed", tag)
            return None
