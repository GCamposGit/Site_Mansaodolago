"""MDL-03 T1: coletor paginado e classificação das consultas do Search Console."""

from __future__ import annotations

import json
import csv
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import seo_calendar.gsc as gsc  # noqa: E402
from seo_calendar.planner import CalendarPlanningError, build_calendar  # noqa: E402
from seo_calendar.report import write_csv  # noqa: E402

SECRET_MARKER = "MDL03-PRIVATE-KEY-MARKER"
_OMIT = object()
TODAY = date(2026, 11, 24)
WINDOW_START = date(2026, 10, 25)
WINDOW_END = date(2026, 11, 21)


def _ignored(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in (0, 1):
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.returncode == 0


def _credential(tmp_path: Path) -> Path:
    path = tmp_path / "vault" / "gsc-service-account.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "client_email": "seo-calendar@mansaodolago.iam.gserviceaccount.com",
                "private_key": (
                    "-----BEGIN PRIVATE KEY-----\n"
                    f"{SECRET_MARKER}\n"
                    "-----END PRIVATE KEY-----\n"
                ),
            }
        ),
        encoding="utf-8",
    )
    return path


def _row(query: str, page: str, impressions: int, position: float, clicks: int = 0) -> dict:
    return {
        "keys": [query, page],
        "impressions": impressions,
        "clicks": clicks,
        "position": position,
    }


def _sitemap(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sitemap.xml"
    path.write_text(body, encoding="utf-8")
    return path


def _versioned_sitemap(*locs: str) -> str:
    items = "\n".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n"
    )


def _page(loc: str, url_text: str = "", title: str = "", h1: str = "") -> gsc.SitemapPage:
    return gsc.SitemapPage(loc=loc, url_text=url_text, title=title, h1=h1)


class FakeClient:
    def __init__(self, rows: list[dict] | None = None, payload: object = _OMIT):
        self.rows = [] if rows is None else rows
        self.payload = payload
        self.calls: list[dict] = []

    def query(self, site_url: str, body):
        recorded = {"site_url": site_url, "body": dict(body)}
        self.calls.append(recorded)
        if self.payload is not _OMIT:
            return self.payload
        start = int(body["startRow"])
        limit = int(body["rowLimit"])
        return {"rows": self.rows[start : start + limit]}


def _collect(tmp_path: Path, client: FakeClient, **overrides):
    sitemap = _sitemap(
        tmp_path,
        _versioned_sitemap("https://www.mansaodolago.com/contato.html"),
    )
    (tmp_path / "contato.html").write_text(
        "<title>Contato</title><h1>Fale conosco</h1>",
        encoding="utf-8",
    )
    params = {
        "sitemap_path": sitemap,
        "site_root": tmp_path,
        "credential_file": _credential(tmp_path),
        "today": TODAY,
        "client": client,
        "row_limit": 2,
    }
    params.update(overrides)
    return gsc.collect(**params)


def _assert_closed(exc_info: pytest.ExceptionInfo) -> None:
    message = str(exc_info.value)
    assert "Nenhuma pauta foi gerada." in message
    assert SECRET_MARKER not in message
    assert "PRIVATE KEY" not in message
    assert not hasattr(exc_info.value, "queries")
    assert exc_info.value.__cause__ is None


def test_seo_calendar_is_tracked_and_generated_artifacts_stay_ignored():
    assert not _ignored("scripts/seo_calendar/gsc.py")
    assert not _ignored("scripts/seo_calendar/__init__.py")
    assert not _ignored("scripts/seo_calendar/requirements.txt")
    assert _ignored("scripts/overhaul_media.py")
    assert _ignored("scripts/seo_calendar/dump.json")
    assert _ignored("scripts/seo_calendar/dump.csv")
    assert _ignored("scripts/seo_calendar/nested/dump.json")
    assert _ignored("scripts/seo_calendar/artifacts/calendario.json")
    assert _ignored("scripts/seo_calendar/artifacts/nota.txt")


def test_deploy_exclusion_still_covers_scripts_tree():
    workflow = (ROOT / ".github/workflows/deploy-hostinger.yml").read_text(encoding="utf-8")
    htaccess = (ROOT / ".htaccess").read_text(encoding="utf-8")
    assert "**/scripts/**" in workflow
    assert "RewriteRule ^scripts(/|$)" in htaccess


def test_import_does_not_load_google_client_libraries():
    assert "service_account" not in gsc.__dict__
    assert "googleapiclient" not in gsc.__dict__


def test_reporting_window_is_28_complete_days_ending_three_days_ago():
    window = gsc.reporting_window(TODAY)
    assert window.start_date == WINDOW_START
    assert window.end_date == WINDOW_END
    assert window.day_count == gsc.WINDOW_DAYS
    assert window.end_date == TODAY - timedelta(days=gsc.DATA_LAG_DAYS)

    leap = gsc.reporting_window(date(2024, 3, 3))
    assert leap.start_date == date(2024, 2, 2)
    assert leap.end_date == date(2024, 2, 29)
    assert leap.day_count == 28


def test_civil_today_uses_sao_paulo_and_rejects_naive_clock():
    assert gsc.civil_today(datetime(2026, 11, 24, 2, 30, tzinfo=timezone.utc)) == date(2026, 11, 23)
    assert gsc.civil_today(datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)) == date(2026, 11, 24)
    with pytest.raises(gsc.InvalidPeriodError) as exc_info:
        gsc.civil_today(datetime(2026, 11, 24, 12, 0))
    _assert_closed(exc_info)


def test_collector_paginates_until_every_query_page_row_is_consumed(tmp_path: Path):
    rows = [
        _row("alpha um", "https://www.mansaodolago.com/a", 10, 8),
        _row("alpha um", "https://www.mansaodolago.com/b", 5, 12),
        _row("bravo dois", "https://www.mansaodolago.com/c", 4, 6),
        _row("charlie tres", "https://www.mansaodolago.com/d", 3, 30),
        _row("delta quatro", "https://www.mansaodolago.com/e", 2, 5),
    ]
    client = FakeClient(rows)
    result = _collect(tmp_path, client, row_limit=2)

    assert [call["body"]["startRow"] for call in client.calls] == [0, 2, 4]
    assert result.start_date == WINDOW_START
    assert result.end_date == WINDOW_END
    assert result.row_count == 5
    assert [item.query for item in result.queries] == [
        "alpha um",
        "bravo dois",
        "charlie tres",
        "delta quatro",
    ]
    for call in client.calls:
        body = call["body"]
        assert call["site_url"] == gsc.DEFAULT_SITE_URL
        assert body["dimensions"] == ["query", "page"]
        assert body["startDate"] == "2026-10-25"
        assert body["endDate"] == "2026-11-21"
        assert body["dataState"] == "final"
        assert body["type"] == "web"
        assert body["rowLimit"] == 2
        assert SECRET_MARKER not in json.dumps(body)


def test_full_page_requests_the_next_page_before_stopping(tmp_path: Path):
    rows = [
        _row("alpha um", "https://www.mansaodolago.com/a", 10, 8),
        _row("bravo dois", "https://www.mansaodolago.com/b", 10, 9),
    ]
    client = FakeClient(rows)
    result = _collect(tmp_path, client, row_limit=2)
    assert [call["body"]["startRow"] for call in client.calls] == [0, 2]
    assert result.row_count == 2


def test_pagination_that_repeats_rows_or_never_ends_is_incomplete(tmp_path: Path, monkeypatch):
    class StickyClient:
        def __init__(self):
            self.calls = []

        def query(self, site_url, body):
            self.calls.append(body["startRow"])
            return {
                "rows": [
                    _row("casa lago", "https://www.mansaodolago.com/a", 10, 8),
                    _row("casa lago", "https://www.mansaodolago.com/b", 10, 12),
                ]
            }

    sticky = StickyClient()
    with pytest.raises(gsc.IncompleteResponseError) as repeated:
        _collect(tmp_path, sticky, row_limit=2)
    _assert_closed(repeated)
    assert sticky.calls == [0, 2]

    monkeypatch.setattr(gsc, "MAX_PAGES", 1)

    class EndlessClient:
        def query(self, site_url, body):
            return {"rows": [_row("casa lago", f"https://www.mansaodolago.com/{body['startRow']}", 3, 9)]}

    with pytest.raises(gsc.IncompleteResponseError) as endless:
        _collect(tmp_path, EndlessClient(), row_limit=1)
    _assert_closed(endless)


def test_position_is_weighted_by_impressions_not_by_clicks_or_simple_mean():
    pages = (_page("https://www.mansaodolago.com/contato.html", "contato", "Contato", "Fale"),)
    weighted_in = gsc.classify_search_console_rows(
        [
            _row("media simples fora", "https://www.mansaodolago.com/a", 1, 40, clicks=0),
            _row("media simples fora", "https://www.mansaodolago.com/b", 3, 10, clicks=0),
        ],
        pages,
    )
    assert weighted_in[0].position == pytest.approx(17.5)
    assert weighted_in[0].is_opportunity is True
    assert weighted_in[0].category == gsc.CATEGORY_OPPORTUNITY

    weighted_out = gsc.classify_search_console_rows(
        [
            _row("ponderada fora", "https://www.mansaodolago.com/a", 100, 4, clicks=0),
            _row("ponderada fora", "https://www.mansaodolago.com/b", 1, 30, clicks=50),
        ],
        pages,
    )
    assert weighted_out[0].position == pytest.approx(430 / 101)
    assert weighted_out[0].is_opportunity is False
    assert weighted_out[0].category == gsc.CATEGORY_OUTSIDE

    clicks_ignored = gsc.classify_search_console_rows(
        [
            _row("cliques nao pesam", "https://www.mansaodolago.com/a", 10, 4, clicks=0),
            _row("cliques nao pesam", "https://www.mansaodolago.com/b", 10, 30, clicks=100),
        ],
        pages,
    )
    assert clicks_ignored[0].position == pytest.approx(17)
    assert clicks_ignored[0].clicks == 100
    assert clicks_ignored[0].impressions == 20
    assert clicks_ignored[0].is_opportunity is True
    assert clicks_ignored[0].pages == (
        "https://www.mansaodolago.com/a",
        "https://www.mansaodolago.com/b",
    )


def test_opportunity_band_includes_5_and_20_and_excludes_the_outside():
    pages = (_page("https://www.mansaodolago.com/contato.html", "contato", "Contato", "Fale"),)
    rows = [
        _row("borda inferior", "https://www.mansaodolago.com/a", 8, 5),
        _row("borda superior", "https://www.mansaodolago.com/a", 8, 20),
        _row("abaixo", "https://www.mansaodolago.com/a", 8, 4.99),
        _row("acima", "https://www.mansaodolago.com/a", 8, 20.01),
        _row("topo", "https://www.mansaodolago.com/a", 8, 1),
    ]
    classified = gsc.classify_search_console_rows(rows, pages)
    by_query = {item.query: item for item in classified}
    assert [item.query for item in classified] == sorted(by_query)
    assert by_query["borda inferior"].is_opportunity is True
    assert by_query["borda superior"].is_opportunity is True
    assert by_query["abaixo"].category == gsc.CATEGORY_OUTSIDE
    assert by_query["acima"].category == gsc.CATEGORY_OUTSIDE
    assert by_query["topo"].is_opportunity is False
    opportunities = tuple(item for item in classified if item.is_opportunity)
    assert {item.query for item in opportunities} == {"borda inferior", "borda superior"}


def test_without_dedicated_page_only_when_no_versioned_url_covers_intent():
    covered = "https://www.mansaodolago.com/blog/casa-com-lago.html"
    other = "https://www.mansaodolago.com/contato.html"
    pages = (
        _page(other, "contato", "Telefone dos anfitrioes", "Horario de visita"),
        _page(covered, "blog casa com lago", "Mapa do sitio", "Endereco postal"),
    )
    rows = [
        _row("casa com lago", "https://www.mansaodolago.com/", 12, 9),
        _row("transfer heliponto zeppelin", "https://www.mansaodolago.com/blog/casa-com-lago.html", 9, 11),
        _row("de do da", "https://www.mansaodolago.com/", 7, 12),
        _row("sem impressao real", "https://www.mansaodolago.com/", 0, 12),
    ]
    classified = gsc.classify_search_console_rows(rows, pages)
    by_query = {item.query: item for item in classified}

    assert "sem impressao real" not in by_query
    assert by_query["casa com lago"].without_dedicated_page is False
    assert by_query["casa com lago"].covering_urls == (covered,)
    assert by_query["transfer heliponto zeppelin"].without_dedicated_page is True
    assert by_query["transfer heliponto zeppelin"].covering_urls == ()
    assert by_query["transfer heliponto zeppelin"].is_opportunity is True
    assert by_query["de do da"].without_dedicated_page is False
    assert gsc.intent_tokens("de do da") == ()
    assert gsc.intent_tokens("suíte privativa") == ("suite", "privativa")


def test_coverage_is_per_field_and_uses_the_documented_three_fifths_minimum():
    tokens = ("alpha", "bravo", "charlie", "delta", "echo")
    assert len(tokens) == 5
    query = " ".join(tokens)
    page = "https://www.mansaodolago.com/blog/pauta.html"

    def classify(url_text: str, title: str, h1: str) -> gsc.QueryClassification:
        found = gsc.classify_search_console_rows(
            [_row(query, "https://www.mansaodolago.com/", 6, 7)],
            (_page(page, url_text, title, h1),),
        )
        return found[0]

    split = classify("alpha bravo", "charlie delta", "echo foxtrot")
    assert split.without_dedicated_page is True

    exact = classify("telefone", "alpha bravo charlie", "horario")
    assert exact.without_dedicated_page is False
    assert exact.covering_urls == (page,)

    title_only = classify("contato", "alpha bravo charlie", "horario")
    h1_only = classify("contato", "horario comercial", "alpha bravo charlie")
    url_only = classify("alpha bravo charlie", "horario comercial", "telefone fixo")
    assert title_only.without_dedicated_page is False
    assert h1_only.without_dedicated_page is False
    assert url_only.without_dedicated_page is False

    below = classify("alpha bravo", "zzzz yyyy", "qqqq")
    assert below.without_dedicated_page is True


def test_non_versioned_sitemap_urls_do_not_count_as_dedicated_pages(tmp_path: Path):
    sitemap = _sitemap(
        tmp_path,
        _versioned_sitemap(
            "https://www.mansaodolago.com/contato.html",
            "https://www.mansaodolago.com/blog/casa-com-lago.html?v=9",
            "https://mansaodolago.com/blog/casa-com-lago.html",
            "http://www.mansaodolago.com/blog/casa-com-lago.html",
            "https://www.mansaodolago.com/blog/casa-com-lago.html#topo",
        ),
    )
    (tmp_path / "contato.html").write_text(
        "<title>Contato</title><h1>Fale conosco</h1>",
        encoding="utf-8",
    )
    blog = tmp_path / "blog"
    blog.mkdir()
    (blog / "casa-com-lago.html").write_text(
        "<title>Casa com lago</title><h1>Lago</h1>",
        encoding="utf-8",
    )
    pages = gsc.load_versioned_pages(sitemap, tmp_path)
    assert [page.loc for page in pages] == ["https://www.mansaodolago.com/contato.html"]

    classified = gsc.classify_search_console_rows(
        [_row("casa com lago", "https://www.mansaodolago.com/blog/casa-com-lago.html", 5, 6)],
        pages,
    )
    assert classified[0].without_dedicated_page is True


def test_versioned_url_can_be_covered_by_slug_title_or_h1_from_disk(tmp_path: Path):
    sitemap = _sitemap(
        tmp_path,
        _versioned_sitemap(
            "https://www.mansaodolago.com/blog/casa-com-lago.html",
            "https://www.mansaodolago.com/blog/",
        ),
    )
    blog = tmp_path / "blog"
    blog.mkdir()
    (blog / "casa-com-lago.html").write_text(
        "<html><head><title>Mapa</title></head><body><h1>Endereço</h1></body></html>",
        encoding="utf-8",
    )
    (blog / "index.html").write_text(
        "<title>Cadernos</title><h1 class=\"heading\">Suíte privativa em Perdizes</h1>",
        encoding="utf-8",
    )
    pages = gsc.load_versioned_pages(sitemap, tmp_path)
    by_loc = {page.loc: page for page in pages}
    slug = by_loc["https://www.mansaodolago.com/blog/casa-com-lago.html"]
    assert "casa" in slug.url_text and "lago" in slug.url_text
    hub = by_loc["https://www.mansaodolago.com/blog/"]
    assert hub.h1 == "Suíte privativa em Perdizes"

    classified = gsc.classify_search_console_rows(
        [
            _row("casa com lago", "https://www.mansaodolago.com/", 4, 15),
            _row("suíte privativa perdizes", "https://www.mansaodolago.com/", 4, 18),
        ],
        pages,
    )
    by_query = {item.query: item for item in classified}
    assert by_query["casa com lago"].without_dedicated_page is False
    assert by_query["suíte privativa perdizes"].without_dedicated_page is False
    assert by_query["suíte privativa perdizes"].covering_urls == (
        "https://www.mansaodolago.com/blog/",
    )


def test_missing_html_still_counts_url_coverage_and_leaves_title_empty(tmp_path: Path):
    sitemap = _sitemap(
        tmp_path,
        _versioned_sitemap("https://www.mansaodolago.com/blog/casa-com-lago.html"),
    )
    pages = gsc.load_versioned_pages(sitemap, tmp_path)
    assert pages[0].title == ""
    assert pages[0].h1 == ""
    classified = gsc.classify_search_console_rows(
        [_row("casa com lago", "https://www.mansaodolago.com/", 3, 10)],
        pages,
    )
    assert classified[0].without_dedicated_page is False


def test_real_sitemap_exposes_title_h1_and_covers_the_allianz_post():
    pages = gsc.load_versioned_pages(ROOT / "sitemap.xml", ROOT)
    assert pages
    assert [page.loc for page in pages] == sorted(page.loc for page in pages)
    for page in pages:
        assert page.title
        assert page.h1
        assert gsc._is_versioned_loc(page.loc)
    post = next(
        page
        for page in pages
        if page.loc.endswith("/blog/onde-ficar-perto-allianz-parque-perdizes.html")
    )
    assert "Allianz" in post.title
    assert "ficar" in post.h1.lower()
    classified = gsc.classify_search_console_rows(
        [_row("onde ficar allianz parque", "https://www.mansaodolago.com/", 15, 8)],
        pages,
    )
    assert classified[0].without_dedicated_page is False
    assert post.loc in classified[0].covering_urls


def test_credential_is_a_file_reference_injected_by_the_vault(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(gsc.CREDENTIAL_ENV, raising=False)
    client = FakeClient([_row("casa com lago", "https://www.mansaodolago.com/", 2, 9)])
    with pytest.raises(gsc.MissingCredentialError) as missing:
        _collect(tmp_path, client, credential_file=None)
    _assert_closed(missing)
    assert client.calls == []
    assert gsc.CREDENTIAL_ENV in str(missing.value)

    monkeypatch.chdir(tmp_path)
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")
    with pytest.raises(gsc.MissingCredentialError):
        _collect(tmp_path, client, credential_file=None)

    secret_path = tmp_path / f"{SECRET_MARKER}.json"
    monkeypatch.setenv(gsc.CREDENTIAL_ENV, str(secret_path))
    with pytest.raises(gsc.MissingCredentialError) as absent:
        _collect(tmp_path, client, credential_file=None)
    _assert_closed(absent)

    vault_file = _credential(tmp_path)
    monkeypatch.setenv(gsc.CREDENTIAL_ENV, str(vault_file))
    result = _collect(tmp_path, client, credential_file=None, row_limit=10)
    assert result.row_count == 1
    assert SECRET_MARKER not in repr(result)
    assert client.calls

    with pytest.raises(gsc.MissingCredentialError) as leaked:
        _collect(tmp_path, client, credential_file=f"-----BEGIN PRIVATE KEY-----\n{SECRET_MARKER}\n")
    _assert_closed(leaked)


def test_unreadable_credential_does_not_echo_the_secret(tmp_path: Path):
    path = tmp_path / "vault.json"
    path.write_text('{"private_key": "' + SECRET_MARKER + '"}', encoding="utf-8")
    with pytest.raises(gsc.MissingCredentialError) as exc_info:
        gsc.resolve_credential_file(path)
    _assert_closed(exc_info)

    path.write_text(SECRET_MARKER, encoding="utf-8")
    with pytest.raises(gsc.MissingCredentialError) as broken:
        gsc.resolve_credential_file(path)
    _assert_closed(broken)


def test_invalid_period_stops_before_the_api(tmp_path: Path):
    client = FakeClient([_row("casa com lago", "https://www.mansaodolago.com/", 2, 9)])
    with pytest.raises(gsc.InvalidPeriodError) as too_fresh:
        _collect(
            tmp_path,
            client,
            start_date=WINDOW_END - timedelta(days=27),
            end_date=TODAY - timedelta(days=2),
        )
    _assert_closed(too_fresh)
    assert "Período inválido" in str(too_fresh.value)
    assert client.calls == []

    with pytest.raises(gsc.InvalidPeriodError) as reversed_window:
        _collect(tmp_path, client, start_date=WINDOW_END, end_date=WINDOW_START)
    _assert_closed(reversed_window)

    with pytest.raises(gsc.InvalidPeriodError) as not_a_day:
        _collect(tmp_path, client, today=datetime(2026, 11, 24, 15, 0))
    _assert_closed(not_a_day)

    with pytest.raises(gsc.InvalidPeriodError) as half:
        _collect(tmp_path, client, start_date=WINDOW_START, end_date=None)
    _assert_closed(half)


def test_empty_or_incomplete_response_does_not_fabricate_a_calendar(tmp_path: Path):
    empty_payloads = [{}, {"rows": []}]
    for payload in empty_payloads:
        client = FakeClient(payload=payload)
        with pytest.raises(gsc.EmptyInputError) as exc_info:
            _collect(tmp_path, client, row_limit=10)
        _assert_closed(exc_info)
        assert "Entrada vazia" in str(exc_info.value)

    zero = FakeClient([_row("casa com lago", "https://www.mansaodolago.com/", 0, 8)])
    with pytest.raises(gsc.EmptyInputError) as no_impressions:
        _collect(tmp_path, zero, row_limit=10)
    _assert_closed(no_impressions)

    incomplete = [
        None,
        {"rows": None},
        {"rows": {}},
        {"rows": [_row("casa", "https://www.mansaodolago.com/", 4, 8) | {"position": None}]},
        {"rows": [{"keys": ["casa"], "impressions": 4, "clicks": 1, "position": 8}]},
        {"rows": [{"keys": ["casa", "https://www.mansaodolago.com/"], "clicks": 1, "position": 8}]},
    ]
    for payload in incomplete:
        client = FakeClient(payload=payload)
        with pytest.raises(gsc.IncompleteResponseError) as exc_info:
            _collect(tmp_path, client, row_limit=10)
        _assert_closed(exc_info)
        assert "Resposta incompleta" in str(exc_info.value)

    class Boom:
        def query(self, site_url, body):
            raise RuntimeError(SECRET_MARKER)

    with pytest.raises(gsc.IncompleteResponseError) as boom:
        _collect(tmp_path, Boom(), row_limit=10)
    _assert_closed(boom)
    assert gsc.classify_search_console_rows([], ()) == ()


def test_below_configured_minimum_stops_without_a_partial_calendar(tmp_path: Path):
    rows = [
        _row("casa com lago", "https://www.mansaodolago.com/a", 5, 8),
        _row("casa com lago", "https://www.mansaodolago.com/b", 5, 9),
        _row("somente esta", "https://www.mansaodolago.com/c", 0, 7),
    ]
    client = FakeClient(rows)
    with pytest.raises(gsc.InsufficientDataError) as too_few_rows:
        _collect(tmp_path, client, min_rows=3, row_limit=10)
    _assert_closed(too_few_rows)
    assert "mínimo configurado" in str(too_few_rows.value)

    client = FakeClient(rows)
    with pytest.raises(gsc.InsufficientDataError) as too_few_queries:
        _collect(tmp_path, client, min_queries=2, row_limit=10)
    _assert_closed(too_few_queries)
    assert client.calls
    assert "consultas" in str(too_few_queries.value)

    idle = FakeClient(rows)
    with pytest.raises(gsc.SeoCalendarError):
        _collect(tmp_path, idle, min_rows=0)
    assert idle.calls == []


def test_collect_matches_classifier_and_writes_no_artifact(tmp_path: Path):
    package = ROOT / "scripts" / "seo_calendar"
    before = sorted(path.relative_to(package) for path in package.rglob("*") if path.is_file())
    rows = [
        _row("bravo", "https://www.mansaodolago.com/b", 3, 19),
        _row("alpha", "https://www.mansaodolago.com/a", 4, 6),
    ]
    client = FakeClient(rows)
    result = _collect(tmp_path, client, row_limit=10)
    direct = gsc.classify_search_console_rows(
        rows,
        gsc.load_versioned_pages(tmp_path / "sitemap.xml", tmp_path),
    )
    assert result.queries == direct
    assert [item.query for item in result.queries] == ["alpha", "bravo"]
    assert result.opportunities[0].query == "alpha"
    after = sorted(path.relative_to(package) for path in package.rglob("*") if path.is_file())
    assert before == after


def test_default_clock_is_civil_today(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gsc, "civil_today", lambda: TODAY)
    client = FakeClient([_row("casa com lago", "https://www.mansaodolago.com/", 2, 9)])
    result = _collect(tmp_path, client, today=None, row_limit=10)
    assert result.start_date == WINDOW_START
    assert result.end_date == WINDOW_END
    assert client.calls[0]["body"]["endDate"] == "2026-11-21"


def test_missing_sitemap_stops_before_the_api(tmp_path: Path):
    client = FakeClient([_row("casa com lago", "https://www.mansaodolago.com/", 2, 9)])
    with pytest.raises(gsc.MissingSitemapError) as exc_info:
        gsc.collect(
            sitemap_path=tmp_path / "ausente.xml",
            site_root=tmp_path,
            credential_file=_credential(tmp_path),
            today=TODAY,
            client=client,
        )
    _assert_closed(exc_info)
    assert client.calls == []


def _calendar_input() -> gsc.CollectionResult:
    queries = (
        gsc.QueryClassification("suite privativa", 100, 12, 8.5, gsc.CATEGORY_OPPORTUNITY, False, (), ("https://www.mansaodolago.com/suites.html",)),
        gsc.QueryClassification("casa para eventos", 80, 8, 11.0, gsc.CATEGORY_OPPORTUNITY, True, (), ()),
        gsc.QueryClassification("hospedagem perdizes", 60, 6, 6.0, gsc.CATEGORY_OPPORTUNITY, False, (), ("https://www.mansaodolago.com/hospedagem.html",)),
        gsc.QueryClassification("ensaio fotografico", 40, 3, 22.0, gsc.CATEGORY_OUTSIDE, True, (), ()),
        gsc.QueryClassification("casamento no lago", 20, 1, 25.0, gsc.CATEGORY_OUTSIDE, True, (), ()),
    )
    return gsc.CollectionResult(WINDOW_START, WINDOW_END, 9, queries)


def test_calendar_has_four_distinct_intents_and_reserves_both_opportunity_types():
    result = build_calendar(
        _calendar_input(),
        property_url=gsc.DEFAULT_SITE_URL,
        generated_on=date(2026, 11, 24),
    )
    assert len(result.entries) == 4
    assert [entry.week for entry in result.entries] == [1, 2, 3, 4]
    assert [entry.week_start for entry in result.entries] == [
        date(2026, 11, 30), date(2026, 12, 7), date(2026, 12, 14), date(2026, 12, 21)
    ]
    intents = [gsc.intent_tokens(entry.target_query) for entry in result.entries]
    assert len(set(intents)) == 4
    assert any(entry.category == gsc.CATEGORY_OPPORTUNITY for entry in result.entries)
    assert any(entry.category == "sem_pagina_dedicada" for entry in result.entries)
    assert result.entries[0].landing_page.endswith("suites.html")
    assert result.entries[0].ctr == pytest.approx(0.12)
    assert "2026-10-25 a 2026-11-21" in result.entries[0].justification
    assert "12 cliques" in result.entries[0].justification
    assert "100 impressões" in result.entries[0].justification
    assert "8.50" in result.entries[0].justification
    assert len(result.input_digest) == 64


def test_calendar_starts_next_monday_even_when_generated_on_monday():
    collection = _calendar_input()
    result = build_calendar(collection, property_url="site", generated_on=date(2026, 11, 30))
    assert result.entries[0].week_start == date(2026, 12, 7)


def test_calendar_blocks_when_four_distinct_eligible_intents_are_unavailable():
    collection = _calendar_input()
    too_few = gsc.CollectionResult(
        collection.start_date,
        collection.end_date,
        collection.row_count,
        collection.queries[:3],
    )
    with pytest.raises(CalendarPlanningError, match="Nenhuma pauta foi gerada"):
        build_calendar(too_few, property_url="site", generated_on=TODAY)

    duplicated = gsc.CollectionResult(
        collection.start_date,
        collection.end_date,
        collection.row_count,
        (
            gsc.QueryClassification("suite privativa", 10, 1, 8, gsc.CATEGORY_OPPORTUNITY, False, (), ()),
            gsc.QueryClassification("SUÍTE privativa", 9, 1, 9, gsc.CATEGORY_OPPORTUNITY, False, (), ()),
        ),
    )
    with pytest.raises(CalendarPlanningError):
        build_calendar(duplicated, property_url="site", generated_on=TODAY)


def test_calendar_csv_is_utf8_spreadsheet_friendly_and_contains_audit_metadata(tmp_path: Path):
    calendar = build_calendar(
        _calendar_input(),
        property_url=gsc.DEFAULT_SITE_URL,
        generated_on=TODAY,
    )
    path = tmp_path / "calendario.csv"
    write_csv(calendar, path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    decoded = raw.decode("utf-8-sig")
    assert ";" in decoded
    assert "propriedade;https://www.mansaodolago.com/" in decoded
    assert "2026-10-25 a 2026-11-21" in decoded
    assert "data_geracao;2026-11-24" in decoded
    assert f"sha256_conjunto_entrada;{calendar.input_digest}" in decoded
    rows = list(csv.reader(decoded.splitlines(), delimiter=";"))
    assert len([row for row in rows if len(row) == 11 and row[0].isdigit()]) == 4
    assert rows[4][0] == "semana"
