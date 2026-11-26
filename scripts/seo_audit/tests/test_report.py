"""Offline tests for evidence assembly and all-or-nothing CLI publication."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.seo_audit import __main__ as cli
from scripts.seo_audit.report import build_evidence, render_markdown


def sample_sources():
    crawl = {
        "seed": "https://mansaodolago.com", "crawl_host": "mansaodolago.com",
        "pages": [{"requested_url": "https://mansaodolago.com/", "title": "Home",
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


if __name__ == "__main__":
    unittest.main()
