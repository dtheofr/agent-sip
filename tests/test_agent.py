import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent_sip.agent import OpenAIChatAgent, load_system_prompt
from agent_sip.config import LlmConfig

seen = []


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append((self.path, self.headers.get("Authorization"), body))
        out = json.dumps({"choices": [{"message": {"content": " hi there "}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class AgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat(self):
        srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        cfg = LlmConfig(base_url=f"http://127.0.0.1:{srv.server_port}/api/v1", api_key="k",
                        model="m", extra={"temperature": 0.1})
        with tempfile.NamedTemporaryFile("w", suffix=".md") as f:
            f.write("Be nice.\n")
            f.flush()
            agent = OpenAIChatAgent(cfg, load_system_prompt(f.name))
        self.assertEqual(await agent.respond("hello"), "hi there")
        await agent.respond("again")
        path, auth, body = seen[-1]
        self.assertEqual(path, "/api/v1/chat/completions")
        self.assertEqual(auth, "Bearer k")
        self.assertEqual(body["temperature"], 0.1)
        self.assertEqual([m["role"] for m in body["messages"]],
                         ["system", "user", "assistant", "user"])
        self.assertEqual(body["messages"][0]["content"], "Be nice.")


if __name__ == "__main__":
    unittest.main()
