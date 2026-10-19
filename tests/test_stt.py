import array
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent_sip.config import SttConfig
from agent_sip.stt import OpenAITranscriber

seen = {}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        seen.update(path=self.path, auth=self.headers.get("Authorization"), body=body)
        out = json.dumps({"text": " hello world "}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class Stt(unittest.IsolatedAsyncioTestCase):
    async def test_transcribe(self):
        srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        cfg = SttConfig(base_url=f"http://127.0.0.1:{srv.server_port}/v1", api_key="k", language="en")
        text = await OpenAITranscriber(cfg).transcribe(array.array("h", [0] * 800))
        srv.shutdown()
        self.assertEqual(text, "hello world")
        self.assertEqual(seen["path"], "/v1/audio/transcriptions")
        self.assertEqual(seen["auth"], "Bearer k")
        self.assertIn(b'name="language"', seen["body"])
        self.assertIn(b"RIFF", seen["body"])


if __name__ == "__main__":
    unittest.main()
