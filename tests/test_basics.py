import array
import os
import tempfile
import unittest

from agent_sip.config import load_config
from agent_sip.sip import g711
from agent_sip.sip.message import header_tag, header_uri, parse
from agent_sip.sip.sdp import build_sdp, parse_rtp_target


class G711(unittest.TestCase):
    def test_roundtrip(self):
        for s in (0, 100, -100, 1000, -5000, 20000, -32000):
            out = g711.decode(g711.encode([s]))[0]
            self.assertLess(abs(out - s), max(64, abs(s) // 16))

    def test_silence_byte(self):
        self.assertEqual(g711.encode([0]), bytes([g711.ULAW_SILENCE]))


class Sip(unittest.TestCase):
    def test_parse(self):
        m = parse(b"INVITE sip:42@h SIP/2.0\r\nVia: a\r\nVia: b\r\nCall-ID: x\r\n"
                  b"From: <sip:a@b>;tag=t1\r\n\r\nbody")
        self.assertEqual((m.method, m.call_id, m.body), ("INVITE", "x", "body"))
        self.assertEqual(m.headers["via"], ["a", "b"])
        self.assertEqual(header_tag(m.header("from")), "t1")
        self.assertEqual(header_uri(m.header("from")), "sip:a@b")

    def test_sdp(self):
        self.assertEqual(parse_rtp_target(build_sdp("1.2.3.4", 10000)), ("1.2.3.4", 10000))


class Config(unittest.TestCase):
    def test_toml_and_env(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("[sip]\nport = 5070\n[demo]\nplayback_recording = false\n"
                    '[[phones]]\nname = "a"\nip = "1.1.1.1"\n[[phones]]\nname = "b"\nip = "2.2.2.2"\n')
        try:
            cfg = load_config(f.name, env={"AGENT_SIP_SIP_LOCAL_IP": "9.9.9.9"})
        finally:
            os.unlink(f.name)
        self.assertEqual(cfg.sip.port, 5070)
        self.assertEqual(cfg.sip.local_ip, "9.9.9.9")
        self.assertEqual([(p.name, p.ip) for p in cfg.phones], [("a", "1.1.1.1"), ("b", "2.2.2.2")])
        self.assertFalse(cfg.demo.playback_recording)


if __name__ == "__main__":
    unittest.main()
