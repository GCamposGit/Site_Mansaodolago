"""Adaptador do Search Console: URL e credencial so por injecao."""

from __future__ import annotations

import inspect
import io
import unittest
import urllib.error
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from darkfac_mailer import (
    SearchConsoleAdapter,
    SearchConsoleError,
    collect_weekly_report,
)
from darkfac_mailer.gsc import _bearer_token

SP = ZoneInfo("America/Sao_Paulo")
SITE = "https://example.test/"
TOKEN = "injected-token"
SECRET_KEY = "BEGIN-PRIVATE-SENTINEL"


class InjectionTests(unittest.TestCase):
    def test_site_url_and_credentials_are_required_arguments(self) -> None:
        signature = inspect.signature(SearchConsoleAdapter.__init__)
        self.assertIs(
            signature.parameters["site_url"].default, inspect.Parameter.empty
        )
        self.assertIs(
            signature.parameters["credentials"].default, inspect.Parameter.empty
        )
        with self.assertRaises(SearchConsoleError) as missing_site:
            SearchConsoleAdapter("  ", TOKEN)
        self.assertEqual(missing_site.exception.code, "gsc_site_url_missing")
        self.assertNotIn(TOKEN, str(missing_site.exception))

    def test_missing_token_is_structured_and_hides_secret_material(self) -> None:
        credentials = {
            "private_key": SECRET_KEY,
            "client_email": "svc@example.test",
            "token": "",
        }
        with self.assertRaises(SearchConsoleError) as caught:
            SearchConsoleAdapter(SITE, credentials)
        self.assertEqual(caught.exception.code, "gsc_credentials_invalid")
        self.assertEqual(caught.exception.as_dict()["error"], "gsc_credentials_invalid")
        rendered = str(caught.exception)
        self.assertNotIn(SECRET_KEY, rendered)
        self.assertNotIn("svc@example.test", rendered)
        self.assertIsNone(caught.exception.__cause__)

    def test_private_key_is_not_kept_on_the_adapter(self) -> None:
        adapter = SearchConsoleAdapter(
            SITE, {"access_token": TOKEN, "private_key": SECRET_KEY}
        )
        blob = repr(adapter) + repr(adapter.__dict__)
        self.assertNotIn(SECRET_KEY, blob)
        self.assertNotIn("private_key", blob)
        self.assertNotIn(TOKEN, repr(adapter))

    def test_string_mapping_and_object_tokens_all_authorize(self) -> None:
        class _Creds:
            def __init__(self, token: str) -> None:
                self.token = token

        self.assertEqual(_bearer_token(f"  {TOKEN}  "), TOKEN)
        self.assertEqual(_bearer_token({"token": TOKEN}), TOKEN)
        self.assertEqual(_bearer_token(_Creds(TOKEN)), TOKEN)


class FetchTests(unittest.TestCase):
    def test_requests_use_injected_site_and_bearer_token(self) -> None:
        transport = _ScriptedTransport(
            {
                ("2026-11-16", ()): [_row(10, 100, 4.5)],
                ("2026-11-16", ("page",)): [
                    _keyed(["https://example.test/a"], 6, 60, 3),
                    _keyed(["https://example.test/b"], 4, 40, 6),
                ],
                ("2026-11-16", ("query",)): [
                    _keyed(["casa"], 10, 100, 4.5),
                ],
            }
        )
        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport)
        period = adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))

        self.assertEqual(period.clicks, 10)
        self.assertEqual(period.impressions, 100)
        self.assertAlmostEqual(period.position or 0, 4.5)
        self.assertEqual(
            [row.key for row in period.pages],
            ["https://example.test/a", "https://example.test/b"],
        )
        self.assertEqual(period.queries[0].key, "casa")

        self.assertEqual(len(transport.calls), 3)
        for url, payload, headers in transport.calls:
            self.assertEqual(
                url,
                "https://searchconsole.googleapis.com/webmasters/v3/sites/"
                "https%3A%2F%2Fexample.test%2F/searchAnalytics/query",
            )
            self.assertNotIn(TOKEN, url)
            self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(payload["startDate"], "2026-11-16")
            self.assertEqual(payload["endDate"], "2026-11-22")
            self.assertEqual(payload["dataState"], "all")
            self.assertEqual(payload["type"], "web")
        self.assertNotIn("dimensions", transport.calls[0][1])
        self.assertEqual(transport.calls[1][1]["dimensions"], ["page"])
        self.assertEqual(transport.calls[2][1]["dimensions"], ["query"])

    def test_domain_property_is_encoded_as_given(self) -> None:
        transport = _ScriptedTransport({("2026-11-16", ()): []})
        adapter = SearchConsoleAdapter(
            "sc-domain:example.test", {"token": TOKEN}, transport=transport, page_size=10
        )
        period = adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertEqual(period.clicks, 0)
        self.assertEqual(period.impressions, 0)
        self.assertIsNone(period.position)
        self.assertIn(
            "/sc-domain%3Aexample.test/searchAnalytics/query",
            transport.calls[0][0],
        )
        self.assertNotIn("example.test%2F", transport.calls[0][0])

    def test_empty_rows_are_a_zero_sample_not_an_exception(self) -> None:
        transport = _ScriptedTransport({})
        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport)
        period = adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertEqual(period.clicks, 0)
        self.assertEqual(period.impressions, 0)
        self.assertIsNone(period.position)
        self.assertEqual(period.pages, ())
        self.assertEqual(period.queries, ())

    def test_pagination_combines_dimension_pages(self) -> None:
        pages = [
            [_keyed(["/b"], 2, 5, 4), _keyed(["/a"], 3, 5, 2)],
            [_keyed(["/c"], 4, 5, 6)],
        ]

        def transport(url, payload, headers):
            del url, headers
            dims = tuple(payload.get("dimensions") or [])
            if dims != ("page",):
                return {"rows": [_row(9, 15, 3)]}
            batch = pages.pop(0) if pages else []
            return {"rows": batch}

        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport, page_size=2)
        period = adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertEqual([row.key for row in period.pages], ["/a", "/b", "/c"])
        self.assertEqual(sum(row.clicks for row in period.pages), 9)

    def test_zero_impression_row_does_not_invent_position(self) -> None:
        transport = _ScriptedTransport(
            {
                ("2026-11-16", ()): [_row(0, 0, None)],
                ("2026-11-16", ("page",)): [
                    {"keys": ["/sem-dado"], "clicks": 0, "impressions": 0, "position": 0}
                ],
                ("2026-11-16", ("query",)): [],
            }
        )
        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport)
        period = adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertIsNone(period.position)
        self.assertIsNone(period.pages[0].position)

    def test_weighted_position_across_total_rows(self) -> None:
        transport = _ScriptedTransport(
            {
                ("2026-11-16", ()): [
                    _row(1, 10, 2),
                    _row(1, 30, 6),
                ],
                ("2026-11-16", ("page",)): [],
                ("2026-11-16", ("query",)): [],
            }
        )
        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport, page_size=1)
        period = adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertEqual(period.clicks, 2)
        self.assertEqual(period.impressions, 40)
        self.assertAlmostEqual(period.position or 0, 5.0)

    def test_collect_compares_injected_windows(self) -> None:
        def transport(url, payload, headers):
            del url, headers
            start = payload["startDate"]
            dims = tuple(payload.get("dimensions") or [])
            if dims == ("page",):
                clicks = 4 if start == "2026-11-16" else 10
                return {"rows": [_keyed(["/a"], clicks, 20, 3)]}
            if dims == ("query",):
                return {"rows": []}
            clicks = 4 if start == "2026-11-16" else 10
            position = 3 if start == "2026-11-16" else 7
            return {"rows": [_row(clicks, 20, position)]}

        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport)
        now = datetime(2026, 11, 24, 8, 0, tzinfo=SP)
        report = collect_weekly_report(adapter, now)
        self.assertEqual(report.current_window.start, date(2026, 11, 16))
        self.assertEqual(report.previous_window.start, date(2026, 11, 9))
        self.assertEqual(report.clicks.delta, -6)
        self.assertEqual(report.clicks.change.value, "piorou")
        self.assertEqual(report.position.change.value, "melhorou")
        self.assertEqual(report.actions[0].key, "/a")
        self.assertEqual(report.actions[0].click_loss, 6)


class FailureTests(unittest.TestCase):
    def test_transport_error_drops_context_and_secret(self) -> None:
        def transport(url, payload, headers):
            del url, payload, headers
            raise RuntimeError(f"boom {TOKEN} {SECRET_KEY}")

        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport)
        with self.assertRaises(SearchConsoleError) as caught:
            adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertEqual(caught.exception.code, "gsc_request_failed")
        self.assertIsNone(caught.exception.status)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertNotIn(SECRET_KEY, str(caught.exception))
        self.assertNotIn(TOKEN, repr(caught.exception.as_dict()))

    def test_http_error_keeps_status_and_hides_header(self) -> None:
        adapter = SearchConsoleAdapter(SITE, TOKEN)

        def boom(request, timeout=0):
            del timeout
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "forbidden " + request.get_header("Authorization"),
                hdrs=None,
                fp=io.BytesIO(TOKEN.encode("utf-8")),
            )

        with mock.patch("urllib.request.urlopen", boom):
            with self.assertRaises(SearchConsoleError) as caught:
                adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertEqual(caught.exception.code, "gsc_request_failed")
        self.assertEqual(caught.exception.status, 403)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertEqual(
            caught.exception.as_dict(), {"error": "gsc_request_failed", "status": 403}
        )

    def test_error_payload_is_not_copied_into_the_exception(self) -> None:
        def transport(url, payload, headers):
            del url, payload, headers
            return {"error": {"message": TOKEN, "private_key": SECRET_KEY}}

        adapter = SearchConsoleAdapter(SITE, TOKEN, transport=transport)
        with self.assertRaises(SearchConsoleError) as caught:
            adapter.fetch_period(date(2026, 11, 16), date(2026, 11, 22))
        self.assertEqual(caught.exception.code, "gsc_response_invalid")
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertNotIn(SECRET_KEY, str(caught.exception))

    def test_production_modules_have_no_real_secret_or_env_lookup(self) -> None:
        root = Path(__file__).resolve().parents[1]
        banned = (
            "mansaodolago",
            "begin private key",
            "mansaodolago_report",
            "os.environ",
            "smtplib",
            "telegram",
            "ya29.",
            SECRET_KEY.lower(),
            TOKEN,
        )
        for name in ("gsc.py", "report.py", "__init__.py"):
            text = (root / name).read_text(encoding="utf-8").lower()
            for needle in banned:
                self.assertNotIn(needle, text, f"{needle} em {name}")


class _ScriptedTransport:
    def __init__(self, rows_by_key: dict[tuple[str, tuple[str, ...]], list[dict]]) -> None:
        self._rows = rows_by_key
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url, payload, headers):
        self.calls.append((url, payload, headers))
        key = (payload["startDate"], tuple(payload.get("dimensions") or []))
        rows = self._rows.get(key, [])
        start = int(payload.get("startRow") or 0)
        limit = int(payload.get("rowLimit") or len(rows))
        return {"rows": rows[start : start + limit]}


def _row(clicks: float, impressions: float, position: float | None) -> dict:
    row = {"clicks": clicks, "impressions": impressions}
    if position is not None:
        row["position"] = position
    return row


def _keyed(keys: list[str], clicks: float, impressions: float, position: float) -> dict:
    row = _row(clicks, impressions, position)
    row["keys"] = keys
    return row


if __name__ == "__main__":
    unittest.main()
