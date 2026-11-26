"""Offline tests for evidence assembly and all-or-nothing CLI publication."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.seo_audit import __main__ as cli
from scripts.seo_audit import crawler, provenance
from scripts.seo_audit.report import build_evidence, render_json, render_markdown


def sample_sources():
    crawl = {
        "seed": "https://mansaodolago.com", "crawl_host": "mansaodolago.com",
        "pages": [{"requested_url": "https://mansaodolago.com/", "status": 200, "title": "Home",
                   "meta_description": "Uma pousada", "title_absent": False,
                   "title_duplicate": False, "meta_description_absent": False,
                   "meta_description_duplicate": False}],
        "robots": {"url": "https://mansaodolago.com/robots.txt", "status": 200,
                   "parsed": True, "allow": ["/"], "disallow": []},
        "sitemap": {"documents": [{"url": "https://mansaodolago.com/sitemap.xml", "parsed": True}],
                    "references": ["https://mansaodolago.com/"], "not_reached": []},
        "links": {"checks": [], "confirmed_4xx": [], "confirmed_5xx": []},
    }
    search = {"property": "sc-domain:mansaodolago.com", "startDate": "2026-11-01",
              "endDate": "2026-11-20", "dataState": "final",
              "aggregate": {"clicks": 10, "impressions": 200, "ctr": 0.05, "position": 3.2},
              "pages": [{"keys": ["https://mansaodolago.com/"], "clicks": 10,
                         "impressions": 200, "ctr": 0.05, "position": 3.2}],
              "inspections": [{"url": "https://mansaodolago.com/", "classification": "unknown",
                               "unknown": ["coverageState"], "errors": []}]}
    return crawl, search


class ReportTests(unittest.TestCase):
    def test_evidence_is_reproducible_and_does_not_emit_secret_fields(self):
        crawl, search = sample_sources()
        search["credential"] = "SECRET-CANARY"
        search["nested"] = {"private_key": "KEY-CANARY", "client_email": "EMAIL-CANARY"}
        evidence = build_evidence(crawl, search, base_url="https://mansaodolago.com",
            start_date="2026-11-01", end_date="2026-11-20",
            parameters={"maxPages": 200}, commit="abc123",
            generated_at=datetime(2026, 11, 24, tzinfo=timezone.utc))
        encoded = json.dumps(evidence)
        for forbidden in ("SECRET-CANARY", "KEY-CANARY", "EMAIL-CANARY", "private_key", "client_email"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(evidence["generatedAt"], "2026-11-24T00:00:00Z")
        self.assertEqual(evidence["counts"]["indexingUnknown"], 1)
        markdown = render_markdown(evidence)
        self.assertIn("10 | 200 | 0.05 | 3.2", markdown)
        self.assertIn("Estado de indexacao desconhecido", markdown)
        self.assertIn("sitemap.xml", markdown)

    def test_live_run_publishes_complete_pair_only_after_both_sources(self):
        crawl, search = sample_sources()
        with tempfile.TemporaryDirectory() as temp:
            paths = cli.run_audit(base_url="https://mansaodolago.com", start_date="2026-11-01",
                end_date="2026-11-20", output_dir=Path(temp), crawl_fn=lambda *_a, **_k: crawl,
                service_fn=lambda: object(), search_fn=lambda *_a, **_k: search)
            self.assertTrue(paths[0].is_file())
            self.assertTrue(paths[1].is_file())
            self.assertEqual(json.loads(paths[0].read_text(encoding="utf-8"))["ticket"], "MDL-01")
            self.assertEqual(len(list(Path(temp).glob("MDL-01-seo-audit-*"))), 1)

    def test_search_console_failure_leaves_no_final_or_staging_artifact(self):
        crawl, _search = sample_sources()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "secret unavailable"):
                cli.run_audit(base_url="https://mansaodolago.com", start_date="2026-11-01",
                    end_date="2026-11-20", output_dir=Path(temp), crawl_fn=lambda *_a, **_k: crawl,
                    service_fn=lambda: (_ for _ in ()).throw(RuntimeError("secret unavailable")))
            self.assertEqual(list(Path(temp).iterdir()), [])


    def _evidence(self, crawl, search):
        return build_evidence(crawl, search, base_url="https://mansaodolago.com",
            start_date="2026-11-01", end_date="2026-11-20", parameters={}, commit="abc123")

    def test_url_secrets_are_masked_in_json_and_markdown(self):
        crawl, search = sample_sources()
        leaky = ("https://user:PASS-CANARY@mansaodolago.com/?lang=en&access_token=TOKEN-CANARY"
                 "#id_token=FRAGMENT-CANARY")
        nested = "https://mansaodolago.com/r?next=https%3A%2F%2Fx.test%2F%3Fapi_key%3DNESTED-CANARY"
        search["pages"][0]["keys"] = [leaky]
        search["inspections"][0]["url"] = leaky
        crawl["pages"][0]["requested_url"] = "https://mansaodolago.com/"
        crawl["pages"][0]["links"] = [leaky, nested, "relativa?client%5Fsecret=REL-CANARY"]
        crawl["links"]["timeouts"] = [{"url": leaky, "status": None, "attempts": 2}]
        crawl["links"]["confirmed_4xx"] = [{"url": nested, "status": 404, "classification": "confirmed_4xx"}]
        evidence = self._evidence(crawl, search)
        for output in (render_json(evidence), render_markdown(evidence)):
            self.assertNotIn("CANARY", output)
            self.assertIn("access_token=REDACTED", output)
            self.assertIn("lang=en", output)

    def test_markdown_cells_escape_pipes_and_newlines(self):
        crawl, search = sample_sources()
        crawl["pages"][0]["title"] = "Mansao do Lago | Hospedagem\nem Perdizes"
        search["pages"][0]["keys"] = ["https://mansaodolago.com/a|b"]
        markdown = render_markdown(self._evidence(crawl, search))
        self.assertIn("| https://mansaodolago.com/ | Mansao do Lago \\| Hospedagem em Perdizes | Uma pousada |",
                      markdown.splitlines())
        self.assertIn("a\\|b", markdown)
        for line in markdown.splitlines():
            if line.startswith("| https://mansaodolago.com/ | Mansao"):
                self.assertEqual(len(re.findall(r"(?<!\\)\|", line)), 4)

    def test_unconfirmed_checks_and_uncollected_pages_are_explicit(self):
        crawl, search = sample_sources()
        for bucket, name in (("timeouts", "lento"), ("rate_limited", "limite"), ("inconclusive", "talvez")):
            crawl["links"][bucket] = [{"url": f"https://mansaodolago.com/{name}", "status": None, "attempts": 2}]
        crawl["pages"].append({"requested_url": "https://mansaodolago.com/lento", "final_url": "https://mansaodolago.com/lento",
                               "status": None, "attempts": 2, "metadata_collected": False,
                               "title": None, "meta_description": None, "title_absent": False,
                               "meta_description_absent": False})
        evidence = self._evidence(crawl, search)
        markdown = render_markdown(evidence)
        for heading in ("#### Timeout: 1", "#### Rate limited (429): 1", "#### Inconclusivo: 1",
                        "#### Paginas sem metadados coletados: 1"):
            self.assertIn(heading, markdown)
        for name in ("lento", "limite", "talvez"):
            self.assertIn(f"| https://mansaodolago.com/{name} | — | 2 |", markdown)
        self.assertIn("| https://mansaodolago.com/lento | NAO COLETADO | NAO COLETADO |", markdown)
        self.assertNotIn("title ausente", markdown)
        self.assertEqual(evidence["counts"]["timeoutLinks"], 1)
        self.assertEqual(evidence["counts"]["uncollectedPages"], 1)

    def test_total_collection_failure_publishes_nothing_and_skips_search_console(self):
        def timeout(url, *, timeout):
            return crawler.FetchResult(url, url, None, None, b"", "timeout", "timeout")

        def forbidden():
            raise AssertionError("Search Console nao pode ser chamado")

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "pagina inicial, robots.txt, sitemap.xml"):
                cli.run_audit(base_url="https://mansaodolago.com", start_date="2026-11-01",
                    end_date="2026-11-20", output_dir=Path(temp), service_fn=forbidden,
                    crawl_fn=lambda base, **options: crawler.crawl_site(base, fetcher=timeout, **options))
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_each_mandatory_section_blocks_only_on_collection_failure(self):
        for section, status, blocked in (
            ("robots", None, True), ("robots", 302, True), ("robots", 403, True),
            ("robots", 503, True), ("robots", 404, False), ("robots", 410, False),
            ("sitemap", None, True), ("sitemap", 302, True), ("sitemap", 403, True),
            ("sitemap", 429, True), ("sitemap", 404, False), ("sitemap", 410, False),
        ):
            crawl, search = sample_sources()
            broken = {"url": "https://mansaodolago.com/x", "status": status, "parsed": False}
            if section == "robots":
                crawl["robots"] = broken
            else:
                crawl["sitemap"]["documents"] = [broken]
            with self.subTest(section=section, status=status):
                if blocked:
                    with self.assertRaisesRegex(ValueError, section):
                        self._evidence(crawl, search)
                else:
                    self._evidence(crawl, search)

    def test_partial_sitemap_failure_or_empty_documents_fails_closed(self):
        crawl, search = sample_sources()
        crawl["sitemap"]["documents"] = [
            {"url": "https://mansaodolago.com/sitemap.xml", "status": 200, "kind": "index", "parsed": True},
            {"url": "https://mansaodolago.com/sitemap-posts.xml", "status": 200, "kind": "urlset", "parsed": True},
            {"url": "https://mansaodolago.com/sitemap-pages.xml", "status": None, "kind": "urlset", "parsed": False},
        ]
        with self.assertRaisesRegex(ValueError, "sitemap"):
            self._evidence(crawl, search)

        crawl_empty, search_empty = sample_sources()
        crawl_empty["sitemap"]["documents"] = []
        with self.assertRaisesRegex(ValueError, "sitemap"):
            self._evidence(crawl_empty, search_empty)


class ProvenanceTests(unittest.TestCase):
    def test_digest_ignores_line_endings_and_tracks_source_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.py").write_bytes(b"x = 1\ny = 2\n")
            first = provenance.source_digest(root)
            (root / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
            self.assertEqual(provenance.source_digest(root), first)
            (root / "a.py").write_bytes(b"x = 2\n")
            self.assertNotEqual(provenance.source_digest(root)["digest"], first["digest"])

    def test_published_evidence_identifies_the_executed_sources(self):
        crawl, search = sample_sources()
        with tempfile.TemporaryDirectory() as temp:
            json_path, markdown_path = cli.run_audit(base_url="https://mansaodolago.com",
                start_date="2026-11-01", end_date="2026-11-20", output_dir=Path(temp),
                crawl_fn=lambda *_a, **_k: crawl, service_fn=lambda: object(),
                search_fn=lambda *_a, **_k: search)
            source = json.loads(json_path.read_text(encoding="utf-8"))["source"]
            self.assertEqual(source["digest"], provenance.source_digest()["digest"])
            self.assertIn("sanitize.py", source["files"])
            self.assertIn(source["digest"], markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
