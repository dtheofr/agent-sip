import array
import io
import json
import math
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent_sip.audio import decode_audio_bytes, resample
from agent_sip.config import TtsConfig, load_config
from agent_sip.tts import OpenAISynthesizer

seen = {}


def wav24k() -> bytes:
    pcm = array.array("h", (int(8000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(24000)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        seen["path"] = self.path
        seen["auth"] = self.headers.get("Authorization")
        seen["json"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = wav24k()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class Tts(unittest.IsolatedAsyncioTestCase):
    def test_resample(self):
        self.assertEqual(len(resample(array.array("h", [0] * 24000), 24000)), 8000)
        self.assertEqual(len(decode_audio_bytes(wav24k())), 8000)

    def test_raw_pcm(self):
        raw = array.array("h", [100] * 2400).tobytes()
        self.assertEqual(len(decode_audio_bytes(raw, 24000)), 800)

    def test_extra_env_json(self):
        cfg = load_config(None, env={"AGENT_SIP_TTS_EXTRA": '{"speed": 1.2}'})
        self.assertEqual(cfg.tts.extra, {"speed": 1.2})

    async def test_synthesize(self):
        srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        cfg = TtsConfig(base_url=f"http://127.0.0.1:{srv.server_port}/v1", api_key="k",
                        voice="v", extra={"speed": 1.5})
        pcm = await OpenAISynthesizer(cfg).synthesize("hello")
        srv.shutdown()
        self.assertEqual(len(pcm), 8000)
        self.assertEqual(seen["path"], "/v1/audio/speech")
        self.assertEqual(seen["auth"], "Bearer k")
        self.assertEqual(seen["json"]["input"], "hello")
        self.assertEqual(seen["json"]["voice"], "v")
        self.assertEqual(seen["json"]["speed"], 1.5)


if __name__ == "__main__":
    unittest.main()
