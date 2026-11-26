"""CLI por subprocesso: crawl via servidor HTTP local, cofre e Google simulados.

O servidor local atua como proxy HTTP, entao o ``UrllibFetcher`` real pede
``http://mansaodolago.com`` sem sair da maquina.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SITE = "http://www.mansaodolago.com"


def _html(title: str, body: str = "") -> str:
    return (f"<!doctype html><html><head><title>{title}</title>"
            f'<meta name="description" content="Descricao {title}"></head>'
            f"<body>{body}</body></html>")


ROUTES = {
    f"{SITE}/": (200, "text/html", _html("Home", '<a href="/quebrado.html">x</a>')),
    f"{SITE}/en/": (200, "text/html", _html("English")),
    f"{SITE}/robots.txt": (200, "text/plain", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n"),
    f"{SITE}/sitemap.xml": (200, "application/xml",
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{SITE}/</loc></url><url><loc>{SITE}/en/</loc></url></urlset>"),
}


class _Proxy(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "http://mansaodolago.com/":
            self.send_response(301)
            self.send_header("Location", f"{SITE}/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        status, content_type, body = ROUTES.get(self.path, (404, "text/html", _html("404")))
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: object) -> None:
        pass


FAKE_VAULT = '''
import json

MANSAODOLAGO_SEARCH_CONSOLE_KEY = "MANSAODOLAGO_SEARCH_CONSOLE_CREDENTIALS_JSON"


class PilotSecretMissingError(RuntimeError):
    pass


def require_pilot_secret(key):
    return json.dumps({"type": "service_account", "project_id": "p", "private_key_id": "k",
        "private_key": "PRIVATE KEY CANARY", "client_email": "canary@example.test",
        "client_id": "1", "token_uri": "https://example.test/token"})
'''

FAKE_CREDENTIALS = '''
class Credentials:
    @classmethod
    def from_service_account_info(cls, info, scopes):
        return cls()
'''

FAKE_DISCOVERY = '''
import os


class _Request:
    def __init__(self, value):
        self.value = value

    def execute(self, num_retries=0):
        return self.value


class _Service:
    def sites(self):
        return self

    def list(self):
        if os.environ.get("FAKE_NO_PROPERTY"):
            return _Request({"siteEntry": []})
        return _Request({"siteEntry": [{"siteUrl": "sc-domain:mansaodolago.com"}]})

    def searchanalytics(self):
        return self

    def query(self, siteUrl, body):
        row = {"clicks": 7, "impressions": 70, "ctr": 0.1, "position": 2.0}
        if body.get("dimensions"):
            row["keys"] = ["http://www.mansaodolago.com/"]
        return _Request({"rows": [row]})

    def urlInspection(self):
        return self

    def index(self):
        return self

    def inspect(self, body):
        failed = body["inspectionUrl"].endswith("/en/")
        return _Request({"inspectionResult": {"indexStatusResult": {
            "verdict": "FAIL" if failed else "PASS", "robotsTxtState": "ALLOWED",
            "indexingState": "INDEXING_ALLOWED", "pageFetchState": "SUCCESSFUL",
            "coverageState": "estado", "lastCrawlTime": "2026-11-20T10:00:00Z"}}})


def build(*args, **kwargs):
    return _Service()
'''


class CliEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fakes = self.root / "fakes"
        for relative, source in (
            ("core/__init__.py", ""),
            ("core/line/__init__.py", ""),
            ("core/line/pilot_secrets.py", FAKE_VAULT),
            ("google/__init__.py", ""),
            ("google/oauth2/__init__.py", ""),
            ("google/oauth2/service_account.py", FAKE_CREDENTIALS),
            ("googleapiclient/__init__.py", ""),
            ("googleapiclient/discovery.py", FAKE_DISCOVERY),
        ):
            target = fakes / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Proxy)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        proxy = f"http://127.0.0.1:{server.server_address[1]}"
        self.env = {key: value for key, value in os.environ.items() if not key.lower().endswith("_proxy")}
        self.env.update({"http_proxy": proxy, "https_proxy": proxy, "PYTHONPATH": str(fakes),
                         "PYTHONDONTWRITEBYTECODE": "1"})

    def run_cli(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "scripts.seo_audit", "--base-url", "http://mansaodolago.com",
             "--start-date", "2026-11-01", "--end-date", "2026-11-20",
             "--output-dir", str(self.root / "output")],
            cwd=REPO, env={**self.env, **extra}, capture_output=True, text=True, timeout=60, check=False,
        )

    def test_publishes_evidence_and_structured_markdown(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        (final,) = (self.root / "output").iterdir()
        raw = (final / "evidence.json").read_text(encoding="utf-8")
        markdown = (final / "report.md").read_text(encoding="utf-8")
        evidence = json.loads(raw)
        self.assertEqual({row["url"] for row in evidence["searchConsole"]["inspections"]},
                         {"http://mansaodolago.com/", f"{SITE}/", f"{SITE}/en/"})
        self.assertEqual(evidence["counts"]["indexingErrors"], 1)
        self.assertEqual(evidence["counts"]["brokenLinks"], 1)
        headings = [line for line in markdown.splitlines() if line.startswith(("# ", "## ", "### "))
                    and not line.startswith("### P")]
        self.assertEqual(headings, [
            "# Auditoria SEO — MDL-01", "## Search Console", "### Desempenho por pagina",
            "### Indexacao", "## Crawl", "### Titles e meta descriptions", "### Links quebrados",
            "### Verificacoes inconclusivas", "### robots.txt", "### sitemap.xml", "## Achados priorizados", "## Cobertura e limitacoes",
        ])
        self.assertIn(f"| {SITE}/quebrado.html | 404 | confirmed_4xx |", markdown)
        self.assertIn("Link quebrado confirmado", markdown)
        self.assertIn("Erro de indexacao", markdown)
        self.assertIn(f"| {SITE}/en/ | error | FAIL |", markdown)
        for output in (raw, markdown, result.stdout, result.stderr):
            self.assertNotIn("CANARY", output)
            self.assertNotIn("canary@example.test", output)

    def test_unreachable_site_exits_nonzero_without_artifacts(self) -> None:
        # Proxy apontando para uma porta fechada: toda a coleta falha.
        result = self.run_cli(http_proxy="http://127.0.0.1:9", https_proxy="http://127.0.0.1:9")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("crawl incompleto", result.stderr)
        self.assertFalse((self.root / "output").exists())

    def test_missing_property_exits_nonzero_without_artifacts(self) -> None:
        result = self.run_cli(FAKE_NO_PROPERTY="1")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("auditoria nao publicada", result.stderr)
        self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main()
