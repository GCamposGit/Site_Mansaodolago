"""Crawl publico: metadados, redirects, mesmo host, robots, sitemap e links.

As respostas HTTP sao fixtures em memoria. Nenhum teste fala com a rede.
"""

from __future__ import annotations

import http.client
import inspect
import io
import json
import sys
import unittest
import urllib.error
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from unittest import mock

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import crawler
import models

HOST = "https://audit.test"
SEED = HOST + "/"
CANARY = "CANARY-CRAWL-BODY"


class FakeFetcher:
    def __init__(self, routes: dict[str, crawler.FetchResult | list[crawler.FetchResult]]) -> None:
        self.routes: dict[str, list[crawler.FetchResult]] = {}
        for url, item in routes.items():
            if isinstance(item, crawler.FetchResult):
                self.routes[url] = [item]
            else:
                self.routes[url] = list(item)
        self.calls: list[str] = []

    def __call__(self, url: str, *, timeout: float) -> crawler.FetchResult:
        self.calls.append(url)
        items = self.routes.get(url)
        if not items:
            return crawler.FetchResult(url, url, 599, "text/plain", b"unscripted", None, None)
        current = items[0]
        if len(items) > 1:
            items.pop(0)
        return current


def html_result(
    url: str,
    html: str,
    *,
    status: int = 200,
    final: str | None = None,
    content_type: str = "text/html; charset=utf-8",
) -> crawler.FetchResult:
    return crawler.FetchResult(
        requested_url=url,
        final_url=final or url,
        status=status,
        content_type=content_type,
        body=html.encode("utf-8"),
        error_kind=None,
        error_detail=None,
    )


def text_result(
    url: str,
    body: str,
    *,
    status: int = 200,
    content_type: str = "text/plain; charset=utf-8",
    final: str | None = None,
) -> crawler.FetchResult:
    return crawler.FetchResult(
        requested_url=url,
        final_url=final or url,
        status=status,
        content_type=content_type,
        body=body.encode("utf-8"),
        error_kind=None,
        error_detail=None,
    )


def status_result(
    url: str,
    status: int,
    *,
    body: bytes = b"",
    content_type: str | None = None,
) -> crawler.FetchResult:
    return crawler.FetchResult(url, url, status, content_type, body, None, None)


def error_result(url: str, kind: str) -> crawler.FetchResult:
    return crawler.FetchResult(url, url, None, None, b"", kind, kind)


def crawl(
    routes: dict[str, Any],
    *,
    seed: str = SEED,
    max_attempts: int = 2,
    max_pages: int = 30,
) -> tuple[models.CrawlReport, FakeFetcher]:
    fetcher = FakeFetcher(routes)
    report = crawler.crawl_site(
        seed,
        fetcher=fetcher,
        timeout=1,
        max_attempts=max_attempts,
        max_pages=max_pages,
    )
    return report, fetcher


def _codes(report: models.CrawlReport) -> set[str]:
    return {item.code for item in report.divergences}


def _page(report: models.CrawlReport, url: str) -> models.PageRecord:
    for page in report.pages:
        if page.requested_url == url:
            return page
    raise AssertionError(url)


class NormalizeTests(unittest.TestCase):
    def test_strips_fragment_userinfo_and_default_port(self) -> None:
        self.assertEqual(
            crawler.normalize_url("HTTPS://User:secret@Audit.Test:443/a/../b#frag"),
            "https://audit.test/b",
        )
        self.assertEqual(
            crawler.normalize_url("/abs.html#x", "https://audit.test/dir/a.html"),
            "https://audit.test/abs.html",
        )
        self.assertEqual(
            crawler.normalize_url("sub.html", "https://audit.test/dir/a.html"),
            "https://audit.test/dir/sub.html",
        )
        self.assertEqual(
            crawler.normalize_url("../b.html", "https://audit.test/dir/a.html"),
            "https://audit.test/b.html",
        )
        self.assertEqual(
            crawler.normalize_url("#topo", "https://audit.test/"),
            "https://audit.test/",
        )

    def test_non_http_schemes_are_ignored(self) -> None:
        for href in (
            "mailto:a@audit.test",
            "tel:+5511999999999",
            "javascript:void(0)",
            "data:text/html,hi",
            "ftp://audit.test/x",
        ):
            with self.subTest(href=href):
                self.assertIsNone(crawler.normalize_url(href))
                self.assertIsNone(crawler.normalize_url(href, SEED))

    def test_sitemap_garbage_is_not_joined_onto_the_base(self) -> None:
        self.assertIsNone(crawler.normalize_url("not a url"))
        self.assertIsNone(
            crawler._normalize_reference("not a url", "https://audit.test/sitemap.xml")
        )
        self.assertEqual(
            crawler._normalize_reference("/sitemap.xml", "https://audit.test/robots.txt"),
            "https://audit.test/sitemap.xml",
        )


class ParseHtmlTests(unittest.TestCase):
    def test_absence_duplicates_relative_links_and_ignored_schemes(self) -> None:
        extract = crawler.parse_html(
            """
            <html><head>
              <base href="https://audit.test/dir/">
              <title>  </title>
              <title>Um</title>
              <title>Dois</title>
              <meta property="og:description" content="nao substitui">
              <meta name="description" content="  ">
              <meta name="Description" content="Primeira">
              <meta name="description" content="Segunda">
              <link rel="stylesheet" href="https://audit.test/css/style.css">
              <link rel="canonical" href="/a">
              <link rel="canonical" href="/b#x">
            </head><body>
              <script>var x = '<a href="https://audit.test/hidden-js.html">';</script>
              <!-- <a href="https://audit.test/hidden-comment.html"> -->
              <a href="sub.html">rel</a>
              <a href="sub.html#frag">dup</a>
              <a href="mailto:a@audit.test">mail</a>
              <a href="javascript:void(0)">js</a>
              <area href="https://external.test/mapa">
            </body></html>
            """,
            "https://audit.test/outra/pagina.html",
        )
        self.assertEqual(extract.title, "Um")
        self.assertFalse(extract.title_absent)
        self.assertTrue(extract.title_duplicate)
        self.assertEqual(extract.meta_description, "Primeira")
        self.assertFalse(extract.meta_description_absent)
        self.assertTrue(extract.meta_description_duplicate)
        self.assertEqual(extract.canonical, "https://audit.test/a")
        self.assertTrue(extract.canonical_duplicate)
        self.assertEqual(
            extract.links,
            (
                "https://audit.test/dir/sub.html",
                "https://external.test/mapa",
            ),
        )
        self.assertEqual(extract.duplicate_links, ("https://audit.test/dir/sub.html",))
        self.assertEqual(
            extract.ignored_non_http,
            ("javascript:void(0)", "mailto:a@audit.test"),
        )
        self.assertNotIn("style.css", "".join(extract.links))
        self.assertNotIn("hidden", "".join(extract.links))

    def test_missing_title_and_meta_are_explicit(self) -> None:
        extract = crawler.parse_html(
            "<html><head><meta property=\"og:description\" content=\"so open graph\">"
            "</head><body><a href=\"/ok.html\">ok</a></body></html>",
            SEED,
        )
        self.assertIsNone(extract.title)
        self.assertTrue(extract.title_absent)
        self.assertFalse(extract.title_duplicate)
        self.assertIsNone(extract.meta_description)
        self.assertTrue(extract.meta_description_absent)
        self.assertIsNone(extract.canonical)
        self.assertTrue(extract.canonical_absent)
        self.assertEqual(extract.links, ("https://audit.test/ok.html",))

    def test_canonical_duplicate_counts_empty_and_missing_href_tags(self) -> None:
        two_empty = crawler.parse_html(
            '<html><head><link rel="canonical" href=""><link rel="canonical"></head></html>',
            SEED,
        )
        self.assertIsNone(two_empty.canonical)
        self.assertTrue(two_empty.canonical_absent)
        self.assertTrue(two_empty.canonical_duplicate)

        mixed = crawler.parse_html(
            '<html><head><link rel="canonical" href=" "><link rel="canonical" href="/a"></head></html>',
            SEED,
        )
        self.assertEqual(mixed.canonical, "https://audit.test/a")
        self.assertFalse(mixed.canonical_absent)
        self.assertTrue(mixed.canonical_duplicate)


class ParseRobotsAndSitemapTests(unittest.TestCase):
    def test_robots_star_group_ignores_other_agents_and_comments(self) -> None:
        parsed = crawler.parse_robots(
            """
            # CANARY-ROBOTS
            User-agent: *
            Disallow: /private
            Allow: /private/ok.html
            Sitemap: https://audit.test/sitemap.xml
            User-agent: OtherBot
            Disallow: /
            Isto nao e diretiva
            """
        )
        self.assertEqual(parsed.disallow, ("/private",))
        self.assertEqual(parsed.allow, ("/private/ok.html",))
        self.assertEqual(parsed.sitemaps, ("https://audit.test/sitemap.xml",))
        self.assertTrue(any("Isto nao e diretiva" in error for error in parsed.errors))
        self.assertNotIn(CANARY, "\n".join(parsed.errors))
        self.assertTrue(crawler.rules_disallow("/private.html", parsed.allow, parsed.disallow))
        self.assertFalse(
            crawler.rules_disallow("/private/ok.html", parsed.allow, parsed.disallow)
        )

    def test_sitemap_urlset_index_and_invalid_xml(self) -> None:
        urlset = crawler.parse_sitemap(
            b"""<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://audit.test/a</loc></url>
            </urlset>
            """
        )
        self.assertEqual(urlset.kind, "urlset")
        self.assertEqual(urlset.page_locs, ("https://audit.test/a",))
        self.assertIsNone(urlset.parse_error)
        index = crawler.parse_sitemap(
            b"""<sitemapindex>
              <sitemap><loc>https://audit.test/child.xml</loc></sitemap>
            </sitemapindex>
            """
        )
        self.assertEqual(index.kind, "index")
        self.assertEqual(index.child_locs, ("https://audit.test/child.xml",))
        broken = crawler.parse_sitemap(b"<<<" + CANARY.encode("ascii"))
        self.assertEqual(broken.parse_error, "XML invalido")
        self.assertNotIn(CANARY, broken.parse_error or "")
        self.assertEqual(broken.page_locs, ())


class RetryClassificationTests(unittest.TestCase):
    def test_confirmed_http_errors_are_not_retried(self) -> None:
        url = HOST + "/item"
        fetcher = FakeFetcher(
            {
                url: [
                    status_result(url, 404),
                    html_result(url, "<title>nao devia</title>"),
                    status_result(url, 500),
                ]
            }
        )
        attempted = crawler.fetch_with_retries(
            url, fetcher, timeout=1, max_attempts=3
        )
        self.assertEqual(attempted.attempts, 1)
        self.assertEqual(attempted.classification, models.CLASS_CONFIRMED_4XX)
        self.assertEqual(attempted.result.status, 404)
        server = HOST + "/server"
        fetcher.routes[server] = [
            status_result(server, 500),
            html_result(server, "<title>depois</title>"),
        ]
        attempted_5xx = crawler.fetch_with_retries(
            server, fetcher, timeout=1, max_attempts=3
        )
        self.assertEqual(attempted_5xx.attempts, 1)
        self.assertEqual(attempted_5xx.classification, models.CLASS_CONFIRMED_5XX)
        self.assertEqual(attempted_5xx.result.status, 500)

    def test_timeout_429_and_inconclusive_retry_until_the_limit(self) -> None:
        cases = (
            (HOST + "/t", error_result(HOST + "/t", models.ERROR_TIMEOUT), models.CLASS_TIMEOUT),
            (HOST + "/r", status_result(HOST + "/r", 429), models.CLASS_RATE_LIMITED),
            (
                HOST + "/i",
                error_result(HOST + "/i", models.ERROR_INCONCLUSIVE),
                models.CLASS_INCONCLUSIVE,
            ),
        )
        for url, result, classification in cases:
            with self.subTest(url=url):
                fetcher = FakeFetcher({url: [result, result, html_result(url, "<title>x</title>")]})
                attempted = crawler.fetch_with_retries(
                    url, fetcher, timeout=1, max_attempts=2
                )
                self.assertEqual(attempted.attempts, 2)
                self.assertEqual(attempted.classification, classification)
                self.assertNotEqual(attempted.classification, models.CLASS_CONFIRMED_4XX)
                self.assertNotEqual(attempted.classification, models.CLASS_CONFIRMED_5XX)

    def test_timeout_then_success_uses_the_recovered_response(self) -> None:
        url = HOST + "/recover"
        fetcher = FakeFetcher(
            {url: [error_result(url, models.ERROR_TIMEOUT), html_result(url, "<title>Voltou</title>")]}
        )
        attempted = crawler.fetch_with_retries(url, fetcher, timeout=1, max_attempts=2)
        self.assertEqual(attempted.attempts, 2)
        self.assertEqual(attempted.classification, models.CLASS_OK)
        self.assertEqual(attempted.result.status, 200)

    def test_unfollowed_redirect_is_inconclusive_and_not_retried(self) -> None:
        url = HOST + "/old"
        fetcher = FakeFetcher({url: [status_result(url, 301), html_result(url, "<title>x</title>")]})
        attempted = crawler.fetch_with_retries(url, fetcher, timeout=1, max_attempts=3)
        self.assertEqual(attempted.attempts, 1)
        self.assertEqual(attempted.result.status, 301)
        self.assertEqual(attempted.classification, models.CLASS_INCONCLUSIVE)

    def test_fetcher_exception_is_sanitized(self) -> None:
        url = HOST + "/boom"

        def explode(target: str, *, timeout: float) -> crawler.FetchResult:
            raise RuntimeError("vault " + CANARY)

        attempted = crawler.fetch_with_retries(url, explode, timeout=1, max_attempts=2)
        self.assertEqual(attempted.attempts, 2)
        self.assertEqual(attempted.classification, models.CLASS_INCONCLUSIVE)
        self.assertNotIn(CANARY, attempted.result.error_detail or "")
        self.assertEqual(attempted.result.body, b"")


class ResilienceTests(unittest.TestCase):
    def test_transient_gateway_errors_are_retried_before_confirmation(self) -> None:
        for status in (502, 503, 504):
            url = HOST + "/gateway"
            with self.subTest(status=status):
                recovered = crawler.fetch_with_retries(
                    url,
                    FakeFetcher({url: [status_result(url, status), html_result(url, "<title>Ok</title>")]}),
                    timeout=1,
                    max_attempts=2,
                )
                self.assertEqual((recovered.attempts, recovered.classification), (2, models.CLASS_OK))
                persistent = crawler.fetch_with_retries(
                    url, FakeFetcher({url: status_result(url, status)}), timeout=1, max_attempts=2
                )
                self.assertEqual(
                    (persistent.attempts, persistent.classification), (2, models.CLASS_CONFIRMED_5XX)
                )

    def test_body_read_failure_is_retried_and_never_classified_ok(self) -> None:
        for failure, classification in (
            (TimeoutError("lento"), models.CLASS_TIMEOUT),
            (ConnectionResetError("caiu"), models.CLASS_INCONCLUSIVE),
            (http.client.IncompleteRead(b""), models.CLASS_INCONCLUSIVE),
            (None, models.CLASS_INCONCLUSIVE),
        ):

            class Response:
                status = 200
                headers = {"Content-Type": "text/html"}
                # failure None simula corpo truncado: Content-Length nao cumprido.
                length = 10 if failure is None else None

                def geturl(self) -> str:
                    return SEED

                def read(self, size: int) -> bytes:
                    if failure is not None:
                        raise failure
                    return b"<html>"

                def __enter__(self) -> "Response":
                    return self

                def __exit__(self, *args: object) -> bool:
                    return False

            with self.subTest(failure=failure), mock.patch.object(
                crawler.urllib.request, "urlopen", lambda *_a, **_k: Response()
            ):
                attempted = crawler.fetch_with_retries(
                    SEED, crawler.UrllibFetcher(), timeout=1, max_attempts=2
                )
                self.assertEqual((attempted.attempts, attempted.classification), (2, classification))
                self.assertIsNotNone(attempted.result.error_kind)
                self.assertIsNone(attempted.result.status)

    def test_error_pages_and_external_redirects_are_not_mined(self) -> None:
        link = '<title>X</title><a href="https://audit.test/{}">l</a>'
        routes = {
            SEED: html_result(SEED, '<title>Home</title><a href="/sumiu">s</a><a href="/fora">f</a>'),
            HOST + "/sumiu": html_result(HOST + "/sumiu", link.format("do-404"), status=404),
            HOST + "/fora": html_result(
                HOST + "/fora", link.format("do-externo"), final="https://external.test/x"
            ),
        }
        report, fetcher = crawl(routes)
        self.assertNotIn(HOST + "/do-404", fetcher.calls)
        self.assertNotIn(HOST + "/do-externo", fetcher.calls)
        for url, status, final in (
            (HOST + "/sumiu", 404, HOST + "/sumiu"),
            (HOST + "/fora", 200, "https://external.test/x"),
        ):
            page = _page(report, url)
            self.assertEqual((page.status, page.final_url), (status, final))
            self.assertFalse(page.metadata_collected)
            self.assertFalse(page.title_absent)
            self.assertIsNone(page.title)
            self.assertEqual(page.links, ())

    def test_seed_redirect_to_another_domain_does_not_move_the_scope(self) -> None:
        routes = {
            SEED: html_result(
                SEED, '<title>Fora</title><a href="/dentro">d</a>', final="https://external.test/"
            ),
        }
        report, fetcher = crawl(routes)
        self.assertEqual(report.crawl_host, "audit.test")
        self.assertFalse(_page(report, SEED).metadata_collected)
        self.assertFalse(any(call.startswith("https://external.test") for call in fetcher.calls))

    def test_invalid_port_rejects_only_that_reference(self) -> None:
        self.assertIsNone(crawler.normalize_url("https://example.test:invalid/"))
        self.assertIsNone(crawler.normalize_url("https://example.test:99999/"))
        self.assertIsNone(crawler.normalize_url("//[quebrado/", SEED))
        extract = crawler.parse_html(
            '<a href="https://example.test:invalid/">x</a><a href="//[y">y</a><a href="/ok">ok</a>', SEED
        )
        self.assertEqual(extract.links, (HOST + "/ok",))


class CrawlFixtureTests(unittest.TestCase):
    def _routes(self) -> dict[str, Any]:
        home = html_result(
            SEED,
            """
            <html><head>
              <title>Home</title>
              <meta name="description" content="Desc home">
              <link rel="canonical" href="https://audit.test/">
              <link rel="stylesheet" href="https://audit.test/css/style.css">
            </head><body>
              <script>var x = '<a href="https://audit.test/hidden-js.html">';</script>
              <a href="#topo">topo</a>
              <a href="/#topo">topo de novo</a>
              <a href="/sem-meta">sem</a>
              <a href="/sem-meta#x">dup</a>
              <a href="https://audit.test/sem-meta">abs</a>
              <a href="relativa.html">rel</a>
              <a href="mailto:a@audit.test">mail</a>
              <a href="tel:+5511">tel</a>
              <a href="javascript:void(0)">js</a>
              <a href="https://external.test/out.html">ext</a>
              <a href="/quebrado.html">quebrado</a>
              <a href="/foto.jpg">foto</a>
              <a href="/igual">igual</a>
              <a href="/timeout">timeout</a>
              <a href="/limite">limite</a>
              <a href="/instavel">instavel</a>
              <a href="/erro-servidor">erro</a>
            </body></html>
            """,
        )
        leaf = (
            "<html><head><title>{title}</title>"
            "<meta name=\"description\" content=\"{meta}\">"
            "<link rel=\"canonical\" href=\"{canonical}\"></head>"
            "<body>ok</body></html>"
        )
        robots = text_result(
            HOST + "/robots.txt",
            """
            # CANARY-ROBOTS
            User-agent: *
            Disallow: /private
            Allow: /private/ok.html
            Sitemap: https://audit.test/sitemap.xml
            User-agent: OtherBot
            Disallow: /
            Isto nao e diretiva
            """,
        )
        sitemap = text_result(
            HOST + "/sitemap.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://audit.test/</loc></url>
              <url><loc>https://audit.test/igual-b</loc></url>
              <url><loc>https://audit.test/igual-b</loc></url>
              <url><loc>https://audit.test/private.html</loc></url>
              <url><loc>https://audit.test/private/ok.html</loc></url>
              <url><loc>https://audit.test/so-no-mapa</loc></url>
              <url><loc>https://audit.test/so-no-mapa#frag</loc></url>
              <url><loc>https://external.test/fora</loc></url>
              <url><loc>not a url</loc></url>
              <url><loc>ftp://audit.test/x</loc></url>
            </urlset>
            """,
            content_type="application/xml",
        )
        routes: dict[str, Any] = {
            SEED: home,
            HOST + "/robots.txt": robots,
            HOST + "/sitemap.xml": sitemap,
            HOST + "/sem-meta": html_result(
                HOST + "/sem-meta",
                "<html><head><meta property=\"og:description\" content=\"nao substitui\">"
                "</head><body>sem</body></html>",
            ),
            HOST + "/relativa.html": html_result(
                HOST + "/relativa.html",
                leaf.format(
                    title="Relativa",
                    meta="Pagina relativa",
                    canonical="https://audit.test/relativa.html",
                ),
            ),
            HOST + "/igual": html_result(
                HOST + "/igual",
                leaf.format(
                    title="Repetido",
                    meta="mesma",
                    canonical="https://audit.test/canon",
                ),
            ),
            HOST + "/igual-b": html_result(
                HOST + "/igual-b",
                leaf.format(
                    title="Repetido",
                    meta="mesma",
                    canonical="https://audit.test/canon",
                ),
            ),
            HOST + "/so-no-mapa": html_result(
                HOST + "/so-no-mapa",
                leaf.format(
                    title="So no mapa",
                    meta="Mapa",
                    canonical="https://audit.test/so-no-mapa",
                ),
            ),
            HOST + "/private.html": html_result(
                HOST + "/private.html",
                leaf.format(
                    title="Privada",
                    meta="Privada",
                    canonical="https://audit.test/private.html",
                ),
            ),
            HOST + "/private/ok.html": html_result(
                HOST + "/private/ok.html",
                leaf.format(
                    title="Ok privada",
                    meta="Ok",
                    canonical="https://audit.test/private/ok.html",
                ),
            ),
            HOST + "/quebrado.html": html_result(
                HOST + "/quebrado.html",
                "<title>Quebrado</title>",
                status=404,
            ),
            HOST + "/foto.jpg": status_result(HOST + "/foto.jpg", 404, content_type="image/jpeg"),
            HOST + "/erro-servidor": [
                html_result(HOST + "/erro-servidor", "<title>Erro</title>", status=500),
                html_result(HOST + "/erro-servidor", "<title>nao devia</title>"),
            ],
            HOST + "/timeout": [
                error_result(HOST + "/timeout", models.ERROR_TIMEOUT),
                error_result(HOST + "/timeout", models.ERROR_TIMEOUT),
            ],
            HOST + "/limite": [
                status_result(HOST + "/limite", 429),
                status_result(HOST + "/limite", 429),
            ],
            HOST + "/instavel": [
                error_result(HOST + "/instavel", models.ERROR_INCONCLUSIVE),
                error_result(HOST + "/instavel", models.ERROR_INCONCLUSIVE),
            ],
            "https://external.test/out.html": html_result(
                "https://external.test/out.html",
                "<html><head><title>Fora</title></head>"
                "<body><a href=\"https://audit.test/hidden.html\">h</a></body></html>",
            ),
        }
        return routes

    def test_crawl_records_pages_links_robots_and_sitemap(self) -> None:
        report, fetcher = crawl(self._routes())
        self.assertEqual(report.seed, SEED)
        self.assertEqual(report.crawl_host, "audit.test")
        self.assertEqual(
            [page.requested_url for page in report.pages],
            sorted(page.requested_url for page in report.pages),
        )
        self.assertEqual(
            {page.requested_url for page in report.pages},
            {
                SEED,
                HOST + "/erro-servidor",
                HOST + "/igual",
                HOST + "/igual-b",
                HOST + "/instavel",
                HOST + "/limite",
                HOST + "/private.html",
                HOST + "/private/ok.html",
                HOST + "/quebrado.html",
                HOST + "/relativa.html",
                HOST + "/sem-meta",
                HOST + "/so-no-mapa",
                HOST + "/timeout",
            },
        )
        self.assertNotIn(HOST + "/foto.jpg", {page.requested_url for page in report.pages})
        self.assertNotIn("https://external.test/out.html", {page.requested_url for page in report.pages})
        self.assertNotIn(HOST + "/hidden.html", fetcher.calls)
        self.assertNotIn(HOST + "/hidden-js.html", fetcher.calls)
        self.assertNotIn(HOST + "/css/style.css", fetcher.calls)
        self.assertNotIn("https://external.test/fora", fetcher.calls)

        home = _page(report, SEED)
        self.assertEqual(home.final_url, SEED)
        self.assertEqual(home.status, 200)
        self.assertEqual(home.content_type, "text/html; charset=utf-8")
        self.assertEqual(home.title, "Home")
        self.assertFalse(home.title_absent)
        self.assertFalse(home.title_duplicate)
        self.assertEqual(home.meta_description, "Desc home")
        self.assertEqual(home.canonical, SEED)
        self.assertFalse(home.redirected)
        self.assertEqual(
            home.links,
            (
                SEED,
                HOST + "/erro-servidor",
                HOST + "/foto.jpg",
                HOST + "/igual",
                HOST + "/instavel",
                HOST + "/limite",
                HOST + "/quebrado.html",
                HOST + "/relativa.html",
                HOST + "/sem-meta",
                HOST + "/timeout",
                "https://external.test/out.html",
            ),
        )
        self.assertEqual(home.duplicate_links, (SEED, HOST + "/sem-meta"))
        self.assertEqual(
            home.ignored_non_http,
            ("javascript:void(0)", "mailto:a@audit.test", "tel:+5511"),
        )
        self.assertFalse(any("#" in link for link in home.links))

        bare = _page(report, HOST + "/sem-meta")
        self.assertTrue(bare.title_absent)
        self.assertIsNone(bare.title)
        self.assertTrue(bare.meta_description_absent)
        self.assertIsNone(bare.meta_description)
        self.assertTrue(bare.canonical_absent)
        self.assertNotEqual(bare.meta_description, "nao substitui")

        self.assertEqual(
            report.duplicate_titles,
            (models.DuplicateGroup("Repetido", (HOST + "/igual", HOST + "/igual-b")),),
        )
        self.assertEqual(
            report.duplicate_meta_descriptions,
            (models.DuplicateGroup("mesma", (HOST + "/igual", HOST + "/igual-b")),),
        )
        self.assertEqual(
            report.duplicate_canonicals,
            (
                models.DuplicateGroup(
                    "https://audit.test/canon",
                    (HOST + "/igual", HOST + "/igual-b"),
                ),
            ),
        )
        self.assertTrue(_page(report, HOST + "/igual").title_duplicate)
        self.assertTrue(_page(report, HOST + "/igual-b").meta_description_duplicate)
        self.assertTrue(_page(report, HOST + "/igual").canonical_duplicate)

        self.assertEqual(report.robots.status, 200)
        self.assertTrue(report.robots.parsed)
        self.assertIsNone(report.robots.parse_error)
        self.assertEqual(report.robots.references, (HOST + "/sitemap.xml",))
        self.assertEqual(report.robots.disallow, ("/private",))
        self.assertEqual(report.robots.allow, ("/private/ok.html",))
        self.assertIn(models.DIV_ROBOTS_INVALID_LINE, {item.code for item in report.robots.divergences})
        self.assertNotIn(CANARY, json.dumps(report.robots.to_dict()))

        self.assertEqual(len(report.sitemap.documents), 1)
        document = report.sitemap.documents[0]
        self.assertEqual(document.status, 200)
        self.assertTrue(document.parsed)
        self.assertEqual(document.kind, "urlset")
        self.assertIn(HOST + "/so-no-mapa", document.references)
        self.assertIn(HOST + "/so-no-mapa", {page.requested_url for page in report.pages})
        self.assertEqual(report.sitemap.not_reached, ())
        self.assertIn("https://external.test/fora", document.rejected)
        self.assertIn("not a url", document.rejected)
        self.assertTrue(any(item.startswith("ftp://") for item in document.rejected))
        sitemap_codes = {item.code for item in document.divergences}
        self.assertIn(models.DIV_SITEMAP_EXTERNAL_LOC, sitemap_codes)
        self.assertIn(models.DIV_SITEMAP_INVALID_LOC, sitemap_codes)
        self.assertIn(models.DIV_SITEMAP_DUPLICATE_LOC, sitemap_codes)
        self.assertIn(models.DIV_URL_DISALLOWED, _codes(report))
        self.assertIn(
            HOST + "/private.html",
            {item.detail for item in report.divergences if item.code == models.DIV_URL_DISALLOWED},
        )
        self.assertNotIn(
            HOST + "/private/ok.html",
            {item.detail for item in report.divergences if item.code == models.DIV_URL_DISALLOWED},
        )

        self.assertEqual(
            [item.url for item in report.links.checks],
            sorted(item.url for item in report.links.checks),
        )
        buckets = (
            report.links.ok,
            report.links.confirmed_4xx,
            report.links.confirmed_5xx,
            report.links.timeouts,
            report.links.rate_limited,
            report.links.inconclusive,
        )
        flat = [item.url for bucket in buckets for item in bucket]
        self.assertEqual(sorted(flat), [item.url for item in report.links.checks])
        self.assertEqual(len(flat), len(set(flat)))
        by_url = {item.url: item for item in report.links.checks}
        self.assertEqual(by_url[HOST + "/quebrado.html"].classification, models.CLASS_CONFIRMED_4XX)
        self.assertEqual(by_url[HOST + "/quebrado.html"].status, 404)
        self.assertEqual(by_url[HOST + "/quebrado.html"].attempts, 1)
        self.assertEqual(by_url[HOST + "/foto.jpg"].classification, models.CLASS_CONFIRMED_4XX)
        self.assertEqual(by_url[HOST + "/foto.jpg"].attempts, 1)
        self.assertEqual(by_url[HOST + "/erro-servidor"].classification, models.CLASS_CONFIRMED_5XX)
        self.assertEqual(by_url[HOST + "/erro-servidor"].status, 500)
        self.assertEqual(by_url[HOST + "/erro-servidor"].attempts, 1)
        self.assertEqual(fetcher.calls.count(HOST + "/erro-servidor"), 1)
        self.assertEqual(by_url[HOST + "/timeout"].classification, models.CLASS_TIMEOUT)
        self.assertEqual(by_url[HOST + "/timeout"].attempts, 2)
        self.assertIsNone(by_url[HOST + "/timeout"].status)
        self.assertEqual(by_url[HOST + "/limite"].classification, models.CLASS_RATE_LIMITED)
        self.assertEqual(by_url[HOST + "/limite"].status, 429)
        self.assertEqual(by_url[HOST + "/limite"].attempts, 2)
        self.assertEqual(by_url[HOST + "/instavel"].classification, models.CLASS_INCONCLUSIVE)
        self.assertEqual(by_url[HOST + "/instavel"].attempts, 2)
        self.assertNotIn(HOST + "/limite", {item.url for item in report.links.confirmed_4xx})
        self.assertNotIn(HOST + "/timeout", {item.url for item in report.links.confirmed_5xx})
        self.assertNotIn(HOST + "/instavel", {item.url for item in report.links.confirmed_4xx})
        self.assertEqual(fetcher.calls.count("https://external.test/out.html"), 1)
        self.assertEqual(
            {item.url for item in report.links.checks},
            set(home.links),
        )
        blob = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True)
        self.assertNotIn(CANARY, blob)
        self.assertNotIn("mailto:", "".join(home.links))
        self.assertFalse(any(call.startswith("mailto:") for call in fetcher.calls))

    def test_results_are_deterministic(self) -> None:
        first, _fetcher = crawl(self._routes())
        second, _fetcher = crawl(self._routes())
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first.to_dict(), sort_keys=True),
            json.dumps(second.to_dict(), sort_keys=True),
        )

    def test_redirect_limits_html_navigation_to_the_final_host(self) -> None:
        apex = "https://apex.test/"
        final = "https://www.apex.test/"
        routes = {
            apex: html_result(
                apex,
                """
                <html><head>
                  <title>Inicio</title>
                  <meta name="description" content="Bem-vindo">
                  <link rel="canonical" href="https://www.apex.test/">
                </head><body>
                  <a href="/on-www.html">www</a>
                  <a href="https://apex.test/only-apex.html">apex</a>
                  <a href="https://external.test/out">fora</a>
                </body></html>
                """,
                final=final,
            ),
            "https://www.apex.test/robots.txt": text_result(
                "https://www.apex.test/robots.txt",
                "User-agent: *\nSitemap: https://www.apex.test/sitemap.xml\n",
            ),
            "https://www.apex.test/sitemap.xml": text_result(
                "https://www.apex.test/sitemap.xml",
                """<urlset>
                  <url><loc>https://www.apex.test/from-map.html</loc></url>
                  <url><loc>https://apex.test/apex-map.html</loc></url>
                </urlset>""",
                content_type="application/xml",
            ),
            "https://www.apex.test/on-www.html": html_result(
                "https://www.apex.test/on-www.html",
                "<title>No www</title><meta name=\"description\" content=\"Www\">",
            ),
            "https://www.apex.test/from-map.html": html_result(
                "https://www.apex.test/from-map.html",
                "<title>Mapa</title><meta name=\"description\" content=\"Mapa\">",
            ),
            "https://apex.test/only-apex.html": html_result(
                "https://apex.test/only-apex.html",
                "<title>Apex</title><a href=\"https://www.apex.test/hidden-from-apex.html\">h</a>",
            ),
            "https://external.test/out": html_result(
                "https://external.test/out",
                "<a href=\"https://www.apex.test/hidden-from-external.html\">h</a>",
            ),
        }
        report, fetcher = crawl(routes, seed="https://apex.test")
        self.assertEqual(report.crawl_host, "www.apex.test")
        home = _page(report, apex)
        self.assertEqual(home.final_url, final)
        self.assertTrue(home.redirected)
        self.assertEqual(home.status, 200)
        self.assertEqual(home.title, "Inicio")
        self.assertEqual(home.canonical, final)
        pages = {page.requested_url for page in report.pages}
        self.assertIn("https://www.apex.test/on-www.html", pages)
        self.assertIn("https://www.apex.test/from-map.html", pages)
        self.assertNotIn("https://apex.test/only-apex.html", pages)
        self.assertNotIn("https://apex.test/apex-map.html", pages)
        self.assertNotIn("https://www.apex.test/hidden-from-apex.html", fetcher.calls)
        self.assertNotIn("https://www.apex.test/hidden-from-external.html", fetcher.calls)
        self.assertNotIn("https://apex.test/robots.txt", fetcher.calls)
        self.assertIn("https://www.apex.test/robots.txt", fetcher.calls)
        self.assertEqual(report.robots.url, "https://www.apex.test/robots.txt")
        self.assertTrue(report.robots.parsed)
        self.assertIn(models.DIV_SITEMAP_EXTERNAL_LOC, _codes(report))
        self.assertIn("https://apex.test/only-apex.html", {item.url for item in report.links.checks})
        self.assertIn("https://external.test/out", {item.url for item in report.links.checks})

    def test_sitemap_urls_not_reached_when_the_page_budget_ends(self) -> None:
        routes = {
            SEED: html_result(SEED, "<title>Home</title><a href=\"/aaa.html\">a</a>"),
            HOST + "/robots.txt": text_result(
                HOST + "/robots.txt",
                "User-agent: *\nSitemap: /sitemap.xml\n",
            ),
            HOST + "/sitemap.xml": text_result(
                HOST + "/sitemap.xml",
                "<urlset><url><loc>https://audit.test/zzz</loc></url></urlset>",
                content_type="application/xml",
            ),
            HOST + "/zzz": html_result(HOST + "/zzz", "<title>Zed</title>"),
            HOST + "/aaa.html": html_result(HOST + "/aaa.html", "<title>Aaa</title>"),
        }
        report, fetcher = crawl(routes, max_pages=1)
        self.assertEqual([page.requested_url for page in report.pages], [SEED])
        self.assertEqual(report.sitemap.not_reached, (HOST + "/zzz",))
        self.assertIn(
            models.Divergence(models.DIV_SITEMAP_URL_NOT_REACHED, HOST + "/zzz"),
            report.divergences,
        )
        self.assertNotIn(HOST + "/zzz", fetcher.calls)
        self.assertNotIn(HOST + "/aaa.html", {page.requested_url for page in report.pages})
        self.assertIn(HOST + "/aaa.html", {item.url for item in report.links.checks})
        self.assertEqual(report.robots.references, (HOST + "/sitemap.xml",))

    def test_valid_sitemap_urls_are_crawled_before_extra_links(self) -> None:
        routes = {
            SEED: html_result(SEED, "<title>Home</title><a href=\"/aaa.html\">a</a>"),
            HOST + "/robots.txt": text_result(HOST + "/robots.txt", "User-agent: *\nAllow: /\n"),
            HOST + "/sitemap.xml": text_result(
                HOST + "/sitemap.xml",
                "<urlset><url><loc>https://audit.test/zzz</loc></url></urlset>",
                content_type="application/xml",
            ),
            HOST + "/zzz": html_result(HOST + "/zzz", "<title>Zed</title>"),
            HOST + "/aaa.html": html_result(HOST + "/aaa.html", "<title>Aaa</title>"),
        }
        report, fetcher = crawl(routes, max_pages=2)
        self.assertEqual(
            {page.requested_url for page in report.pages},
            {SEED, HOST + "/zzz"},
        )
        self.assertLess(fetcher.calls.index(HOST + "/zzz"), fetcher.calls.index(HOST + "/aaa.html"))
        self.assertEqual(report.sitemap.not_reached, ())

    def test_invalid_sitemap_does_not_abort_the_crawl(self) -> None:
        routes = {
            SEED: html_result(SEED, "<title>Home</title><a href=\"/ok.html\">ok</a>"),
            HOST + "/robots.txt": status_result(HOST + "/robots.txt", 404),
            HOST + "/sitemap.xml": text_result(
                HOST + "/sitemap.xml",
                "<<<" + CANARY,
                content_type="application/xml",
            ),
            HOST + "/ok.html": html_result(HOST + "/ok.html", "<title>Ok</title>"),
        }
        report, fetcher = crawl(routes)
        self.assertIn(HOST + "/ok.html", {page.requested_url for page in report.pages})
        self.assertEqual(report.robots.status, 404)
        self.assertFalse(report.robots.parsed)
        self.assertEqual(report.robots.parse_error, "ausente")
        document = report.sitemap.documents[0]
        self.assertEqual(document.status, 200)
        self.assertFalse(document.parsed)
        self.assertEqual(document.parse_error, "XML invalido")
        self.assertIn(models.DIV_SITEMAP_INVALID, _codes(report))
        self.assertIn(models.DIV_ROBOTS_UNAVAILABLE, _codes(report))
        self.assertNotIn(CANARY, json.dumps(report.to_dict()))
        self.assertIn(HOST + "/sitemap.xml", fetcher.calls)

    def test_relative_sitemap_and_index_are_followed_on_the_same_host(self) -> None:
        routes = {
            SEED: html_result(SEED, "<title>Home</title>"),
            HOST + "/robots.txt": text_result(
                HOST + "/robots.txt",
                "User-agent: *\nSitemap: /sitemap.xml\n",
            ),
            HOST + "/sitemap.xml": text_result(
                HOST + "/sitemap.xml",
                "<sitemapindex><sitemap><loc>https://audit.test/child.xml</loc></sitemap>"
                "</sitemapindex>",
                content_type="application/xml",
            ),
            HOST + "/child.xml": text_result(
                HOST + "/child.xml",
                "<urlset><url><loc>https://audit.test/from-child.html</loc></url></urlset>",
                content_type="application/xml",
            ),
            HOST + "/from-child.html": html_result(
                HOST + "/from-child.html",
                "<title>Filha</title>",
            ),
        }
        report, fetcher = crawl(routes)
        self.assertEqual(report.robots.references, (HOST + "/sitemap.xml",))
        kinds = {document.url: document.kind for document in report.sitemap.documents}
        self.assertEqual(kinds[HOST + "/sitemap.xml"], "index")
        self.assertEqual(kinds[HOST + "/child.xml"], "urlset")
        self.assertIn(HOST + "/from-child.html", {page.requested_url for page in report.pages})
        self.assertIn(HOST + "/from-child.html", report.sitemap.references)
        self.assertIn(HOST + "/child.xml", fetcher.calls)

    def test_external_sitemap_reference_is_not_fetched(self) -> None:
        routes = {
            SEED: html_result(SEED, "<title>Home</title>"),
            HOST + "/robots.txt": text_result(
                HOST + "/robots.txt",
                "User-agent: *\nSitemap: https://external.test/sitemap.xml\n",
            ),
            HOST + "/sitemap.xml": text_result(
                HOST + "/sitemap.xml",
                "<urlset><url><loc>https://audit.test/nao.html</loc></url></urlset>",
                content_type="application/xml",
            ),
        }
        report, fetcher = crawl(routes)
        self.assertEqual(report.robots.references, ("https://external.test/sitemap.xml",))
        self.assertNotIn("https://external.test/sitemap.xml", fetcher.calls)
        self.assertNotIn(HOST + "/sitemap.xml", fetcher.calls)
        self.assertNotIn(HOST + "/nao.html", fetcher.calls)
        self.assertIn(models.DIV_SITEMAP_EXTERNAL_LOC, _codes(report))
        self.assertEqual([page.requested_url for page in report.pages], [SEED])


class UrllibFetcherTests(unittest.TestCase):
    def test_success_carries_final_url_user_agent_and_body_limit(self) -> None:
        captured: dict[str, Any] = {}

        class Response:
            status = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def geturl(self) -> str:
                return "https://www.audit.test/"

            def read(self, size: int) -> bytes:
                captured["read"] = size
                return b"x" * (size + 10)

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> bool:
                return False

        def urlopen(request: Any, timeout: float | None = None) -> Response:
            captured["timeout"] = timeout
            captured["method"] = request.get_method()
            captured["ua"] = request.get_header("User-agent")
            return Response()

        with mock.patch.object(crawler.urllib.request, "urlopen", urlopen):
            with mock.patch.object(crawler, "MAX_BODY", 4):
                result = crawler.UrllibFetcher(timeout=3)(SEED, timeout=3)
        self.assertEqual(result.status, 200)
        self.assertEqual(result.final_url, "https://www.audit.test/")
        self.assertEqual(result.body, b"xxxx")
        self.assertEqual(captured["read"], 5)
        self.assertEqual(captured["timeout"], 3)
        self.assertEqual(captured["method"], "GET")
        self.assertIn("MansaodolagoSEOAudit/1.0", captured["ua"])
        self.assertIsNone(result.error_kind)

    def test_http_error_timeout_and_network_failure_stay_sanitized(self) -> None:
        headers = EmailMessage()
        headers["Content-Type"] = "text/html; charset=utf-8"
        http_error = urllib.error.HTTPError(
            HOST + "/missing",
            404,
            "missing " + CANARY,
            headers,
            io.BytesIO(b"<title>Sumiu</title>"),
        )

        def missing(request: Any, timeout: float | None = None) -> Any:
            raise http_error

        with mock.patch.object(crawler.urllib.request, "urlopen", missing):
            result = crawler.UrllibFetcher()(HOST + "/missing", timeout=1)
        self.assertEqual(result.status, 404)
        self.assertEqual(result.body, b"<title>Sumiu</title>")
        self.assertIsNone(result.error_kind)
        self.assertNotIn(CANARY, result.error_detail or "")

        def timed_out(request: Any, timeout: float | None = None) -> Any:
            raise urllib.error.URLError(TimeoutError("timed out " + CANARY))

        with mock.patch.object(crawler.urllib.request, "urlopen", timed_out):
            result = crawler.UrllibFetcher()(SEED, timeout=1)
        self.assertEqual(result.error_kind, models.ERROR_TIMEOUT)
        self.assertIsNone(result.status)
        self.assertNotIn(CANARY, result.error_detail or "")

        def exploded(request: Any, timeout: float | None = None) -> Any:
            raise urllib.error.URLError(OSError("dns " + CANARY))

        with mock.patch.object(crawler.urllib.request, "urlopen", exploded):
            result = crawler.UrllibFetcher()(SEED, timeout=1)
        self.assertEqual(result.error_kind, models.ERROR_INCONCLUSIVE)
        self.assertEqual(result.error_detail, "OSError")
        self.assertNotIn(CANARY, result.error_detail or "")
        self.assertEqual(result.body, b"")


class PublicContractTests(unittest.TestCase):
    def test_default_seed_and_no_secret_channel(self) -> None:
        signature = inspect.signature(crawler.crawl_site)
        self.assertEqual(signature.parameters["seed"].default, "https://mansaodolago.com")
        self.assertEqual(crawler.DEFAULT_SEED, "https://mansaodolago.com")
        self.assertEqual(crawler.normalize_url(crawler.DEFAULT_SEED), "https://mansaodolago.com/")
        names = " ".join(signature.parameters)
        self.assertNotIn("credential", names)
        self.assertNotIn("secret", names)
        source = Path(crawler.__file__).read_text(encoding="utf-8")
        self.assertNotIn("pilot_secrets", source)
        self.assertNotIn("MANSAODOLAGO_SEARCH_CONSOLE", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", source)

    def test_invalid_seed_and_limits_fail_closed(self) -> None:
        with self.assertRaises(crawler.CrawlError):
            crawler.crawl_site("ftp://audit.test/")
        with self.assertRaises(crawler.CrawlError):
            crawler.crawl_site(SEED, timeout=0, fetcher=FakeFetcher({}))
        with self.assertRaises(crawler.CrawlError):
            crawler.crawl_site(SEED, max_attempts=0, fetcher=FakeFetcher({}))
        with self.assertRaises(crawler.CrawlError):
            crawler.crawl_site(SEED, max_pages=0, fetcher=FakeFetcher({}))

    def test_documents_are_html_like_and_assets_are_not(self) -> None:
        self.assertTrue(crawler.is_crawl_document(HOST + "/hospedagem.html"))
        self.assertTrue(crawler.is_crawl_document(HOST + "/blog/"))
        self.assertTrue(crawler.is_crawl_document(HOST + "/sem-extensao"))
        self.assertFalse(crawler.is_crawl_document(HOST + "/foto.jpg"))
        self.assertFalse(crawler.is_crawl_document(HOST + "/css/style.css?v=1"))
        self.assertFalse(crawler.is_crawl_document(HOST + "/sitemap.xml"))


if __name__ == "__main__":
    unittest.main()
