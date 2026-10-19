import array
import asyncio
import unittest

from agent_sip.audio import EnergyVAD, make_vad, play_interruptible, record_until_silence
from agent_sip.config import AudioConfig

LOUD = array.array("h", [3000, -3000] * 80)
QUIET = array.array("h", [0] * 160)


class FakeCall:
    """Feeds a scripted list of frames in (fast) real time; play() takes ``play_time`` seconds."""

    def __init__(self, frames, play_time=1.0):
        self.frames, self.play_time, self.active = list(frames), play_time, True
        self.played = self.cancelled = False

    def flush_input(self):
        pass

    async def read_frame(self, timeout):
        await asyncio.sleep(0.001)
        return self.frames.pop(0) if self.frames else None

    async def play(self, pcm):
        try:
            await asyncio.sleep(self.play_time)
            self.played = True
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return True


class Vad(unittest.IsolatedAsyncioTestCase):
    def test_energy(self):
        v = EnergyVAD(500)
        self.assertTrue(v.is_speech(LOUD))
        self.assertFalse(v.is_speech(QUIET))

    def test_factory(self):
        self.assertIsInstance(make_vad(AudioConfig(vad="energy")), EnergyVAD)
        with self.assertRaises(ValueError):
            make_vad(AudioConfig(vad="nope"))

    async def test_record_ends_on_vad_silence(self):
        call = FakeCall([QUIET] * 3 + [LOUD] * 5 + [QUIET] * 200)
        pcm, heard = await record_until_silence(call, EnergyVAD(), silence_end=0.05)
        self.assertTrue(heard)
        self.assertLess(len(pcm), 160 * 120)

    async def test_record_no_speech(self):
        pcm, heard = await record_until_silence(FakeCall([QUIET] * 5), EnergyVAD(),
                                                no_speech_timeout=0.05)
        self.assertFalse(heard)

    async def test_prefix_counts_as_speech(self):
        pcm, heard = await record_until_silence(FakeCall([QUIET] * 200), EnergyVAD(),
                                                silence_end=0.05, prefix=LOUD)
        self.assertTrue(heard)
        self.assertGreaterEqual(len(pcm), len(LOUD))

    async def test_barge_in_cancels_playback(self):
        call = FakeCall([QUIET] * 5 + [LOUD] * 30)
        captured = await play_interruptible(call, QUIET, EnergyVAD(), min_speech=0.1)
        await asyncio.sleep(0)
        self.assertIsNotNone(captured)
        self.assertTrue(call.cancelled)
        self.assertGreaterEqual(len(captured), 160 * 5)

    async def test_short_noise_does_not_interrupt(self):
        call = FakeCall([QUIET] * 3 + [LOUD] * 2 + [QUIET] * 5, play_time=0.1)
        captured = await play_interruptible(call, QUIET, EnergyVAD(), min_speech=0.1)
        self.assertIsNone(captured)
        self.assertTrue(call.played)


if __name__ == "__main__":
    unittest.main()
