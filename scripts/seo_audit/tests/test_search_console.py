"""Testes offline para o cliente Search Console somente leitura."""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

from scripts.seo_audit import search_console as sc


@dataclass
class Page:
    requested_url: str
    final_url: str
    content_type: str
    status: int | None = 200


@dataclass
class Sitemap:
    references: tuple[str, ...]


@dataclass
class Crawl:
    pages: tuple[Page, ...]
    sitemap: Sitemap


class Request:
    def __init__(self, value):
        self.value = value

    def execute(self, num_retries=0):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class FakeService:
    def __init__(self, sites, analytics, inspections):
        self.site_data = sites
        self.analytics_data = list(analytics)
        self.inspection_data = dict(inspections)
        self.queries = []
        self.inspected = []
        self.site_list_calls = 0

    def sites(self):
        service = self

        class Sites:
            def list(self):
                service.site_list_calls += 1
                return Request(service.site_data)

        return Sites()

    def searchanalytics(self):
        service = self

        class Analytics:
            def query(self, siteUrl, body):
                service.queries.append((siteUrl, dict(body)))
                return Request(service.analytics_data.pop(0))

        return Analytics()

    def urlInspection(self):
        service = self

        class UrlInspection:
            def index(self):
                return self

            def inspect(self, body):
                url = body["inspectionUrl"]
                service.inspected.append(dict(body))
                return Request(service.inspection_data[url])

        return UrlInspection()


def inspection(url, *, verdict="PASS", robots="ALLOWED", indexing="INDEXING_ALLOWED", fetch="SUCCESSFUL", coverage="Submitted and indexed", **extra):
    fields = {
        "verdict": verdict,
        "robotsTxtState": robots,
        "indexingState": indexing,
        "pageFetchState": fetch,
        "coverageState": coverage,
        "lastCrawlTime": "2026-11-20T10:00:00Z",
    }
    fields.update(extra)
    return {"inspectionResult": {"indexStatusResult": fields}}


class SearchConsoleTests(unittest.TestCase):
    def make_crawl(self):
        return Crawl(
            pages=(
                Page("https://mansaodolago.com/a", "https://mansaodolago.com/a", "text/html"),
                Page("https://mansaodolago.com/not-html.html", "https://mansaodolago.com/not-html.html", "image/jpeg"),
                Page("https://www.mansaodolago.com/x", "https://www.mansaodolago.com/x", "text/html"),
                Page("https://mansaodolago.com/old", "https://mansaodolago.com/a", "text/html"),
                Page("https://mansaodolago.com/gone", "https://mansaodolago.com/gone", "text/html", 404),
                Page("https://mansaodolago.com/boom", "https://mansaodolago.com/boom", "text/html", 500),
                Page("https://notmansaodolago.com/", "https://notmansaodolago.com/", "text/html"),
            ),
            sitemap=Sitemap((
                "https://mansaodolago.com/from-map.html",
                "https://mansaodolago.com/photo.jpg",
                "https://other.test/out.html",
            )),
        )

    def valid_service(self, *, sites=None, analytics=None, inspections=None):
        page_urls = (
            "https://mansaodolago.com/a",
            "https://mansaodolago.com/from-map.html",
            "https://www.mansaodolago.com/x",
        )
        return FakeService(
            sites if sites is not None else {"siteEntry": [{"siteUrl": "sc-domain:mansaodolago.com"}]},
            analytics if analytics is not None else [
                {"rows": [{"clicks": 12, "impressions": 300, "ctr": 0.04, "position": 7.5}]},
                {"rows": [{"keys": ["https://mansaodolago.com/a"], "clicks": 9, "impressions": 200, "ctr": 0.045, "position": 6.0}]},
            ],
            inspections if inspections is not None else {url: inspection(url) for url in page_urls},
        )

    def test_uses_exact_property_explicit_final_queries_and_inspects_crawl_and_sitemap(self):
        service = self.valid_service(sites={"siteEntry": [
            {"siteUrl": "https://notmansaodolago.com/"},
            {"siteUrl": "sc-domain:mansaodolago.com"},
        ]})
        report = sc.audit_search_console(self.make_crawl(), "2026-11-01", "2026-11-20", service=service)
        self.assertEqual(report.property_url, "sc-domain:mansaodolago.com")
        self.assertEqual(report.data_state, "final")
        self.assertEqual(report.aggregate, {"clicks": 12, "impressions": 300, "ctr": 0.04, "position": 7.5})
        self.assertEqual(len(report.pages), 1)
        self.assertEqual({row["inspectionUrl"] for row in service.inspected}, {
            "https://mansaodolago.com/a", "https://mansaodolago.com/from-map.html",
            "https://www.mansaodolago.com/x",
        })
        self.assertEqual(len(service.queries), 2)
        for _, query in service.queries:
            self.assertEqual(query["startDate"], "2026-11-01")
            self.assertEqual(query["endDate"], "2026-11-20")
            self.assertEqual(query["dataState"], "final")
        self.assertNotIn("dimensions", service.queries[0][1])
        self.assertEqual(service.queries[1][1]["dimensions"], ["page"])

    def test_analytics_pages_are_fetched_until_short_page(self):
        service = self.valid_service(analytics=[
            {"rows": []},
            {"rows": [{"keys": ["a"]}, {"keys": ["b"]}]},
            {"rows": [{"keys": ["c"]}]},
        ])
        report = sc.audit_search_console(self.make_crawl(), "2026-11-01", "2026-11-20", service=service, page_size=2)
        pages_queries = [body for _, body in service.queries if body.get("dimensions") == ["page"]]
        self.assertEqual([body["startRow"] for body in pages_queries], [0, 2])
        self.assertEqual([row["keys"][0] for row in report.pages], ["a", "b", "c"])

    def test_url_prefix_www_property_scopes_inspections_to_its_scheme_and_host(self):
        for prop, expected in (
            ("https://www.mansaodolago.com/", {"https://www.mansaodolago.com/x"}),
            ("http://www.mansaodolago.com/", set()),
        ):
            service = self.valid_service(sites={"siteEntry": [{"siteUrl": prop}]})
            with self.subTest(prop=prop):
                report = sc.audit_search_console(self.make_crawl(), "2026-11-01", "2026-11-20", service=service)
                self.assertEqual(report.property_url, prop)
                self.assertEqual({row["inspectionUrl"] for row in service.inspected}, expected)
                self.assertLessEqual({row["siteUrl"] for row in service.inspected}, {prop})

    def test_domain_property_wins_over_url_prefixes(self):
        service = self.valid_service(sites={"siteEntry": [
            {"siteUrl": "https://www.mansaodolago.com/"},
            {"siteUrl": "sc-domain:mansaodolago.com"},
            {"siteUrl": "https://mansaodolago.com/"},
        ]})
        self.assertEqual(sc._resolve_property(service, 1, lambda _s: None), "sc-domain:mansaodolago.com")

    def test_domain_scope_covers_subdomains_but_not_lookalikes(self):
        prop = "sc-domain:mansaodolago.com"
        self.assertTrue(sc._url_belongs("http://blog.mansaodolago.com/a", prop))
        self.assertFalse(sc._url_belongs("https://notmansaodolago.com/", prop))
        self.assertFalse(sc._url_belongs("https://mansaodolago.com.evil.test/", prop))

    def test_ambiguous_or_missing_property_fails_before_queries(self):
        for sites in ({"siteEntry": []}, {"siteEntry": [
            {"siteUrl": "https://blog.mansaodolago.com/"},
            {"siteUrl": "https://www.mansaodolago.com/blog/"},
        ]}, {"siteEntry": [
            {"siteUrl": "https://www.mansaodolago.com/"},
            {"siteUrl": "https://mansaodolago.com/"},
        ]}):
            service = self.valid_service(sites=sites)
            with self.subTest(sites=sites), self.assertRaisesRegex(sc.SearchConsoleError, "propriedade"):
                sc.audit_search_console(self.make_crawl(), "2026-11-01", "2026-11-20", service=service)
            self.assertEqual(service.queries, [])

    def test_inspection_classifies_errors_and_unknowns_separately(self):
        urls = ["https://mansaodolago.com/a", "https://mansaodolago.com/from-map.html"]
        service = self.valid_service(inspections={
            urls[0]: inspection(urls[0], verdict="FAIL", robots="DISALLOWED"),
            urls[1]: {"inspectionResult": {"indexStatusResult": {"verdict": "VERDICT_UNSPECIFIED"}}},
            "https://www.mansaodolago.com/x": inspection("https://www.mansaodolago.com/x"),
        })
        result = sc.audit_search_console(self.make_crawl(), "2026-11-01", "2026-11-20", service=service).inspections
        bad, unknown, healthy = result
        self.assertEqual(healthy.classification, "ok")
        self.assertEqual(bad.classification, "error")
        self.assertEqual(bad.errors, ("verdict", "robotsTxtState"))
        self.assertEqual(unknown.classification, "unknown")
        self.assertIn("indexingState", unknown.unknown)
        self.assertIn("coverageState", unknown.unknown)
        self.assertIn("lastCrawlTime", unknown.unknown)
        self.assertIsNone(unknown.coverage_state)
        self.assertEqual(unknown.to_dict()["coverageState"], None)

    def test_quota_prevents_partial_inspection_report(self):
        service = self.valid_service()
        with self.assertRaisesRegex(sc.SearchConsoleError, "quota"):
            sc.audit_search_console(self.make_crawl(), "2026-11-01", "2026-11-20", service=service, max_inspections=1)
        self.assertEqual(service.queries, [])
        self.assertEqual(service.inspected, [])

    def test_invalid_interval_fails_closed(self):
        with self.assertRaisesRegex(sc.SearchConsoleError, "intervalo"):
            sc.audit_search_console(self.make_crawl(), "2026-11-21", "2026-11-20", service=self.valid_service())

    def test_retries_429_and_5xx_but_not_auth_errors_and_sanitizes(self):
        class HttpError(Exception):
            def __init__(self, status, content=b""):
                self.resp = SimpleNamespace(status=status)
                self.content = content
                super().__init__("private error detail")

        waits = []
        outcomes = [HttpError(429), HttpError(503), {"siteEntry": [{"siteUrl": "sc-domain:mansaodolago.com"}]}]

        class RetryService:
            def sites(self):
                class Sites:
                    calls = 0

                    def list(inner):
                        inner.calls += 1
                        return Request(outcomes.pop(0))
                self.resource = Sites()
                return self.resource

        resolved = sc._resolve_property(RetryService(), 3, waits.append)
        self.assertEqual(resolved, "sc-domain:mansaodolago.com")
        self.assertEqual(waits, [1, 2])
        quota = HttpError(403, json.dumps({"error": {"errors": [{"reason": "quotaExceeded"}]}}).encode())
        with self.assertRaisesRegex(sc.SearchConsoleError, "quota") as caught:
            sc._execute(lambda: Request(quota), 2, waits.append)
        self.assertNotIn("quotaExceeded", str(caught.exception))
        with self.assertRaisesRegex(sc.SearchConsoleError, "autenticacao"):
            sc._execute(lambda: Request(HttpError(401)), 3, waits.append)

    def test_client_uses_only_vault_credentials_and_readonly_scope(self):
        captured = {}

        def credential_factory(info, scopes):
            captured["info"] = info
            captured["scopes"] = scopes
            return "credential"

        def service_factory(*args, **kwargs):
            captured["service_args"] = args
            captured["service_kwargs"] = kwargs
            return "service"

        with mock.patch.object(sc, "load_credentials_json", return_value={"type": "service_account"}) as read:
            value = sc.create_service(credentials_factory=credential_factory, service_factory=service_factory)
        read.assert_called_once_with()
        self.assertEqual(captured["scopes"], ["https://www.googleapis.com/auth/webmasters.readonly"])
        self.assertEqual(captured["service_args"], ("searchconsole", "v1"))
        self.assertFalse(captured["service_kwargs"]["cache_discovery"])
        self.assertEqual(value, "service")

    def test_missing_vault_secret_stops_without_building_client(self):
        with mock.patch.object(sc, "load_credentials_json", side_effect=sc.SecretSourceError("secret canary")):
            with self.assertRaises(sc.SearchConsoleError) as caught:
                sc.create_service(credentials_factory=lambda *_args, **_kwargs: None, service_factory=lambda *_args, **_kwargs: None)
        self.assertNotIn("secret canary", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
