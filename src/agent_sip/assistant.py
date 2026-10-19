"""Assistant handler: listen -> STT -> agent (LLM) -> TTS, one conversation per call."""
import logging
from collections.abc import Callable

from .agent import Agent
from .audio import record_until_silence
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
        log.info("[%s] assistant session started", tag)
        if self.greeting:
            await self._say(call, self.greeting, tag)
        while call.active:
            pcm, heard = await record_until_silence(
                call,
                speech_threshold=self.audio.speech_threshold,
                silence_end=self.audio.silence_end,
                no_speech_timeout=self.audio.no_speech_timeout,
                max_record=self.audio.max_record,
            )
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
                await self._say(call, reply, tag)

    async def _say(self, call: Call, text: str, tag: str) -> None:
        try:
            await call.play(await self.tts.synthesize(text))
        except Exception:
            log.exception("[%s] TTS failed", tag)
