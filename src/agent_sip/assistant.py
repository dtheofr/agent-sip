"""Assistant handler: listen -> STT -> agent (LLM) -> TTS, one conversation per call."""
import array
import logging
from collections.abc import Callable

from .agent import Agent
from .audio import make_vad, play_interruptible, record_until_silence, thinking
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
            async with thinking(call, self.audio, beep=False):
                pcm = await self._synth(self.greeting, tag)
            barged = await self._play(call, vad, pcm, tag)
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
            reply_pcm = None
            async with thinking(call, self.audio):
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
                    reply_pcm = await self._synth(reply, tag)
            if reply_pcm is not None:
                barged = await self._play(call, vad, reply_pcm, tag)

    async def _synth(self, text: str, tag: str) -> array.array | None:
        try:
            return await self.tts.synthesize(text)
        except Exception:
            log.exception("[%s] TTS failed", tag)
            return None

    async def _play(self, call: Call, vad, pcm: array.array | None,
                    tag: str) -> array.array | None:
        """Play ``pcm``. Returns the caller's audio if they interrupted, else None."""
        if pcm is None:
            return None
        try:
            if not self.audio.barge_in:
                await call.play(pcm)
                return None
            captured = await play_interruptible(
                call, pcm, vad, min_speech=self.audio.barge_in_min_speech)
            if captured is not None:
                log.info("[%s] caller interrupted the agent", tag)
            return captured
        except Exception:
            log.exception("[%s] playback failed", tag)
            return None
