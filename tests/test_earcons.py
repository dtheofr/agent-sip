import asyncio
import os
import tempfile
import unittest

from agent_sip.audio.earcons import make_beep, make_melody, parse_melody, thinking
from agent_sip.config import AudioConfig, load_config


class FakeCall:
    active = True

    def __init__(self):
        self.played = []
        self.cancelled = 0
        self.busy = False

    async def play(self, pcm):
        assert not self.busy, "play lock still held"
        self.busy = True
        self.played.append(len(pcm))
        try:
            await asyncio.sleep(len(pcm) / 8000)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.busy = False
        return True


class Parse(unittest.TestCase):
    def test_notes(self):
        f = parse_melody("A4, a5,C4,F#4,Bb3,-,r")
        self.assertAlmostEqual(f[0], 440)
        self.assertAlmostEqual(f[1], 880)
        self.assertAlmostEqual(f[2], 261.63, places=1)
        self.assertAlmostEqual(f[3], 369.99, places=1)
        self.assertAlmostEqual(f[4], 233.08, places=1)
        self.assertEqual(f[5:], (None, None))
        self.assertEqual(parse_melody(["A4", "-"]), (440.0, None))

    def test_invalid(self):
        for bad in ("H4", "A4,x", "C1", "C8", ""):
            with self.assertRaises(ValueError):
                parse_melody(bad)


class Generators(unittest.TestCase):
    def test_beep(self):
        b = make_beep(800, 0.12, 0.25)
        self.assertEqual(len(b), 960)
        self.assertLessEqual(max(map(abs, b)), 0.25 * 32767)
        self.assertLess(abs(b[0]), 50)
        self.assertLess(abs(b[-1]), 500)

    def test_melody(self):
        m = make_melody("A4,-,E5", 0.1, 0.5, 0.25)
        self.assertEqual(len(m), 8000 * (0.3 + 0.5))
        self.assertLessEqual(max(map(abs, m)), 0.25 * 32767)
        self.assertEqual(m[0], 0)


class Thinking(unittest.IsolatedAsyncioTestCase):
    def cfg(self, **kw):
        return AudioConfig(melody_delay=0.1, melody_note_duration=0.05, melody_gap=0.05, **kw)

    async def test_beep_then_melody_and_stop(self):
        call = FakeCall()
        async with thinking(call, self.cfg()):
            self.assertEqual(call.played, [960])
            await asyncio.sleep(0.3)
        self.assertGreater(len(call.played), 1)
        self.assertFalse(call.busy)
        n = len(call.played)
        await asyncio.sleep(0.2)
        self.assertEqual(len(call.played), n)

    async def test_fast_reply_no_melody(self):
        call = FakeCall()
        async with thinking(call, self.cfg()):
            pass
        await asyncio.sleep(0.2)
        self.assertEqual(call.played, [960])

    async def test_exception(self):
        call = FakeCall()
        with self.assertRaises(RuntimeError):
            async with thinking(call, self.cfg()):
                await asyncio.sleep(0.2)
                raise RuntimeError
        self.assertFalse(call.busy)

    async def test_disabled_and_no_beep(self):
        call = FakeCall()
        async with thinking(call, self.cfg(earcons=False)):
            await asyncio.sleep(0.2)
        self.assertEqual(call.played, [])
        async with thinking(call, self.cfg(), beep=False):
            await asyncio.sleep(0.05)
        self.assertEqual(call.played, [])


class Config(unittest.TestCase):
    def test_toml_and_env(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[audio]\nmelody_notes = ["A4", "C5"]\nbeep_freq = 900\n')
        try:
            c = load_config(f.name, env={"AGENT_SIP_AUDIO_MELODY_GAP": "3", "AGENT_SIP_AUDIO_BEEP": "false"})
            self.assertEqual(c.audio.melody_notes, "A4,C5")
            self.assertEqual(c.audio.beep_freq, 900)
            self.assertEqual(c.audio.melody_gap, 3.0)
            self.assertFalse(c.audio.beep)
            with self.assertRaises(ValueError):
                load_config(f.name, env={"AGENT_SIP_AUDIO_MELODY_NOTES": "H4"})
        finally:
            os.unlink(f.name)
