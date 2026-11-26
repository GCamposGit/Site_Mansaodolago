"""Adaptador do Google Search Console.

``GSC_SITE_URL`` e a credencial entram so por injecao. Este modulo nao le
ambiente, nao tem propriedade padrao e nao coloca segredo em erro ou repr.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import Any, Callable
from urllib.parse import quote

from darkfac_mailer.report import DimensionStat, PeriodStats

_ENDPOINT = (
    "https://searchconsole.googleapis.com/webmasters/v3/sites/"
    "{site}/searchAnalytics/query"
)
_MAX_PAGE_SIZE = 25000
_MAX_PAGES = 20
Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class SearchConsoleError(Exception):
    """Falha estruturada. ``code`` e ``status`` nunca carregam segredo."""

    def __init__(self, code: str, *, status: int | None = None) -> None:
        self.code = code
        self.status = status
        super().__init__(code)

    def __str__(self) -> str:
        if self.status is None:
            return self.code
        return f"{self.code} status={self.status}"

    def as_dict(self) -> dict[str, str | int | None]:
        return {"error": self.code, "status": self.status}


class SearchConsoleAdapter:
    """Cliente da Search Analytics API para uma propriedade ja autorizada."""

    def __init__(
        self,
        site_url: str,
        credentials: Any,
        *,
        transport: Transport | None = None,
        page_size: int = _MAX_PAGE_SIZE,
    ) -> None:
        if not isinstance(site_url, str) or not site_url.strip():
            raise SearchConsoleError("gsc_site_url_missing")
        if not isinstance(page_size, int) or isinstance(page_size, bool):
            raise ValueError("page_size invalido")
        if page_size < 1 or page_size > _MAX_PAGE_SIZE:
            raise ValueError("page_size invalido")
        self._site_url = site_url.strip()
        # Guarda so o token. O mapping original pode ter chave privada.
        self._access_token = _bearer_token(credentials)
        self._transport = transport or _urllib_transport
        self._page_size = page_size

    def __repr__(self) -> str:
        return f"SearchConsoleAdapter(site_url={self._site_url!r})"

    def fetch_period(self, start: date, end: date) -> PeriodStats:
        """Agrega o periodo inclusivo. Lista vazia vira zeros, sem excecao."""

        if not isinstance(start, date) or not isinstance(end, date):
            raise TypeError("start e end devem ser date")
        if start > end:
            raise ValueError("intervalo invalido")
        totals = _aggregate(self._query(start, end, None))
        pages = _dimension_stats(self._query(start, end, ["page"]))
        queries = _dimension_stats(self._query(start, end, ["query"]))
        return PeriodStats(
            clicks=totals[0],
            impressions=totals[1],
            position=totals[2],
            pages=pages,
            queries=queries,
        )

    def _query(
        self, start: date, end: date, dimensions: list[str] | None
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        start_row = 0
        for _ in range(_MAX_PAGES):
            payload: dict[str, Any] = {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "rowLimit": self._page_size,
                "startRow": start_row,
                # A semana civil recem-encerrada ainda nao esta finalizada
                # no Search Console na manha de segunda. "all" inclui esse dado.
                "dataState": "all",
                "type": "web",
            }
            if dimensions:
                payload["dimensions"] = list(dimensions)
            body = self._request(payload)
            if "error" in body and not body.get("rows"):
                raise SearchConsoleError("gsc_response_invalid")
            batch = body.get("rows") or []
            if not isinstance(batch, list):
                raise SearchConsoleError("gsc_response_invalid")
            for row in batch:
                if not isinstance(row, dict):
                    raise SearchConsoleError("gsc_response_invalid")
                collected.append(row)
            if len(batch) < self._page_size:
                return collected
            start_row += self._page_size
        raise SearchConsoleError("gsc_response_invalid")

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = _ENDPOINT.format(site=quote(self._site_url, safe=""))
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # A excecao estruturada nasce fora do except para nao herdar contexto
        # que possa citar o token ou o corpo da resposta.
        failed = False
        try:
            body = self._transport(url, payload, headers)
        except SearchConsoleError:
            raise
        except Exception:
            failed = True
        if failed:
            raise SearchConsoleError("gsc_request_failed")
        if not isinstance(body, dict):
            raise SearchConsoleError("gsc_response_invalid")
        return body


def _bearer_token(credentials: Any) -> str:
    token = ""
    if isinstance(credentials, str):
        token = credentials.strip()
    elif isinstance(credentials, Mapping):
        raw = credentials.get("access_token", credentials.get("token", ""))
        token = str(raw or "").strip()
        if token.lower() in {"none", "null"}:
            token = ""
    else:
        raw_attr = getattr(credentials, "token", None)
        if isinstance(raw_attr, str):
            token = raw_attr.strip()
    if not token:
        raise SearchConsoleError("gsc_credentials_invalid")
    return token


def _num(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise SearchConsoleError("gsc_response_invalid") from None


def _aggregate(rows: list[dict[str, Any]]) -> tuple[float, float, float | None]:
    clicks = 0.0
    impressions = 0.0
    weighted_position = 0.0
    saw_position = False
    for row in rows:
        row_clicks = _num(row.get("clicks"))
        row_impressions = _num(row.get("impressions"))
        clicks += row_clicks
        impressions += row_impressions
        if row.get("position") is not None and row_impressions > 0:
            weighted_position += _num(row.get("position")) * row_impressions
            saw_position = True
    position = (
        weighted_position / impressions if saw_position and impressions > 0 else None
    )
    return clicks, impressions, position


def _dimension_stats(rows: list[dict[str, Any]]) -> tuple[DimensionStat, ...]:
    stats: list[DimensionStat] = []
    for row in rows:
        keys = row.get("keys") or []
        if not isinstance(keys, list) or not keys or not str(keys[0]).strip():
            continue
        impressions = _num(row.get("impressions"))
        position = None
        if row.get("position") is not None and impressions > 0:
            position = _num(row.get("position"))
        stats.append(
            DimensionStat(
                key=str(keys[0]),
                clicks=_num(row.get("clicks")),
                impressions=impressions,
                position=position,
            )
        )
    stats.sort(key=lambda item: item.key)
    return tuple(stats)


def _urllib_transport(
    url: str, payload: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    status: int | None = None
    failed = False
    raw = b""
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        failed = True
    except urllib.error.URLError:
        failed = True
    if failed:
        raise SearchConsoleError("gsc_request_failed", status=status)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SearchConsoleError("gsc_response_invalid") from None
    if not isinstance(parsed, dict):
        raise SearchConsoleError("gsc_response_invalid")
    return parsed
