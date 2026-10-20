"""Web tools: ``web_search`` (Tavily) and ``fetch_url`` (local, SSRF-guarded). Stdlib only."""
import asyncio
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from ..config import ToolsConfig
from .tools import Tool

UA = "Mozilla/5.0 (compatible; agent-sip/0.1)"
MAX_REDIRECTS = 5
TEXT_TYPES = ("text/", "application/json", "application/xhtml+xml", "application/xml")
SKIP_TAGS = {"script", "style", "head", "nav", "footer", "svg", "noscript", "template"}
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section",
              "article"}


def check_public_url(url: str) -> None:
    """Raise ValueError unless url is http(s) and every resolved address is public."""
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("only http and https URLs are allowed")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"cannot resolve {u.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise ValueError("private or local addresses are not allowed")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    p.close()
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def _fetch(url: str, cfg: ToolsConfig, check=check_public_url) -> str:
    opener = urllib.request.build_opener(_NoRedirect)   # follow redirects manually, re-checking
    for _ in range(MAX_REDIRECTS + 1):
        check(url)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        try:
            resp = opener.open(req, timeout=cfg.timeout)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise RuntimeError(f"HTTP {e.code}") from e
        with resp:
            ctype = resp.headers.get_content_type()
            if not ctype.startswith(TEXT_TYPES):
                raise RuntimeError(f"unsupported content type {ctype}")
            raw = resp.read(cfg.fetch_max_bytes)
            charset = resp.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
        if "html" in ctype:
            text = html_to_text(text)
        if len(text) > cfg.fetch_max_chars:
            text = text[:cfg.fetch_max_chars] + " [truncated]"
        return text or "(empty page)"
    raise RuntimeError("too many redirects")


def _search(query: str, cfg: ToolsConfig) -> str:
    payload = {"query": query, "max_results": cfg.search_max_results,
               "search_depth": cfg.search_depth, "include_answer": True}
    req = urllib.request.Request(
        cfg.tavily_base_url.rstrip("/") + "/search", json.dumps(payload).encode(),
        {"Content-Type": "application/json", "Authorization": f"Bearer {cfg.tavily_api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Tavily HTTP {e.code}: {e.read()[:200]!r}") from e
    lines = []
    if data.get("answer"):
        lines.append(f"Answer: {data['answer']}")
    for r in data.get("results", []):
        snippet = (r.get("content") or "").strip().replace("\n", " ")[:300]
        lines.append(f"- {r.get('title', '')}: {snippet} ({r.get('url', '')})")
    return "\n".join(lines) or "no results"


def web_tools(cfg: ToolsConfig, check=check_public_url) -> list[Tool]:
    """Tools enabled by config. `check` is the URL guard (override only in tests)."""
    tools = []
    if cfg.tavily_api_key:
        async def web_search(query: str) -> str:
            return await asyncio.to_thread(_search, query, cfg)
        tools.append(Tool(
            "web_search", "Search the web for current information. Returns a short answer "
            "and top result snippets.", web_search,
            {"type": "object", "properties": {"query": {"type": "string"}},
             "required": ["query"]}))
    if cfg.fetch_enabled:
        async def fetch_url(url: str) -> str:
            return await asyncio.to_thread(_fetch, url, cfg, check)
        tools.append(Tool(
            "fetch_url", "Fetch a public web page and return its text content.", fetch_url,
            {"type": "object", "properties": {"url": {"type": "string"}},
             "required": ["url"]}))
    return tools
