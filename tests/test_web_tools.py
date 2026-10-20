import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent_sip.agent import ToolRegistry, web_tools
from agent_sip.agent.web_tools import html_to_text
from agent_sip.config import ToolsConfig

seen = []
HTML = b"<html><head><title>x</title></head><body><script>bad()</script><p>Hello</p><p>World</p></body></html>"


class Fake(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append((self.path, self.headers.get("Authorization"), body))
        self._send(200, json.dumps({"answer": "42", "results": [
            {"title": "T", "content": "snippet", "url": "http://u"}]}).encode())

    def do_GET(self):
        if self.path == "/redir":
            self._send(302, b"", extra={"Location": "http://192.168.1.1/"})
        elif self.path == "/bin":
            self._send(200, b"\x00", "application/octet-stream")
        else:
            self._send(200, HTML, "text/html")

    def log_message(self, *a):
        pass


class WebToolsTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_registration(self):
        names = [t.name for t in web_tools(ToolsConfig())]
        self.assertEqual(names, ["fetch_url"])
        names = [t.name for t in web_tools(ToolsConfig(tavily_api_key="k", fetch_enabled=False))]
        self.assertEqual(names, ["web_search"])

    def test_html_to_text(self):
        self.assertEqual(html_to_text(HTML.decode()), "Hello\nWorld")

    async def test_search(self):
        cfg = ToolsConfig(tavily_api_key="k", tavily_base_url=self.base)
        reg = ToolRegistry(web_tools(cfg))
        out = await reg.call("web_search", '{"query": "life"}')
        self.assertIn("Answer: 42", out)
        self.assertIn("- T: snippet (http://u)", out)
        self.assertEqual(seen[-1][:2], ("/search", "Bearer k"))
        self.assertEqual(seen[-1][2]["query"], "life")

    async def test_fetch(self):
        # guard disabled so the loopback fake server is reachable
        cfg = ToolsConfig(fetch_max_chars=8)
        reg = ToolRegistry(web_tools(cfg, check=lambda u: None))
        self.assertEqual(await reg.call("fetch_url", {"url": self.base + "/"}),
                         "Hello\nWo [truncated]")
        self.assertIn("unsupported", await reg.call("fetch_url", {"url": self.base + "/bin"}))

    async def test_ssrf_guard(self):
        reg = ToolRegistry(web_tools(ToolsConfig()))
        for url in (self.base + "/", "http://192.168.1.1/", "file:///etc/passwd",
                    "http://localhost/"):
            self.assertTrue((await reg.call("fetch_url", {"url": url})).startswith("error:"), url)

    async def test_redirect_rechecked(self):
        def check(u):
            if "192.168" in u:
                raise ValueError("private")
        reg = ToolRegistry(web_tools(ToolsConfig(), check=check))
        out = await reg.call("fetch_url", {"url": self.base + "/redir"})
        self.assertIn("private", out)


if __name__ == "__main__":
    unittest.main()
