"""Cliente somente leitura para desempenho e inspecao do Search Console."""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable
from urllib.parse import urlsplit

from . import crawler
from .secret_source import SEARCH_CONSOLE_SCOPE, SecretSourceError, load_credentials_json

PROPERTY_DOMAIN = "mansaodolago.com"
MAX_INSPECTIONS_PER_DAY = 2_000
MAX_ANALYTICS_PAGE_SIZE = 25_000
DEFAULT_MAX_ATTEMPTS = 3
_METRIC_FIELDS = ("clicks", "impressions", "ctr", "position")
_PROPERTY_SCHEME = re.compile(r"^https?://", re.IGNORECASE)


class SearchConsoleError(RuntimeError):
    """Erro sanitizado; respostas ou credenciais da Google nunca sao exibidas."""


@dataclass(frozen=True)
class Inspection:
    url: str
    verdict: str | None
    coverage_state: str | None
    robots_txt_state: str | None
    indexing_state: str | None
    page_fetch_state: str | None
    last_crawl_time: str | None
    classification: str
    errors: tuple[str, ...]
    unknown: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "verdict": self.verdict,
            "coverageState": self.coverage_state,
            "robotsTxtState": self.robots_txt_state,
            "indexingState": self.indexing_state,
            "pageFetchState": self.page_fetch_state,
            "lastCrawlTime": self.last_crawl_time,
            "classification": self.classification,
            "errors": list(self.errors),
            "unknown": list(self.unknown),
        }


@dataclass(frozen=True)
class SearchConsoleReport:
    property_url: str
    start_date: str
    end_date: str
    data_state: str
    aggregate: dict[str, Any]
    pages: tuple[dict[str, Any], ...]
    inspections: tuple[Inspection, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "property": self.property_url,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "dataState": self.data_state,
            "aggregate": dict(self.aggregate),
            "pages": [dict(row) for row in self.pages],
            "inspections": [record.to_dict() for record in self.inspections],
        }


def create_service(
    *, credentials_factory: Callable[..., Any] | None = None,
    service_factory: Callable[..., Any] | None = None,
) -> Any:
    """Cria cliente Google usando exclusivamente o segredo do cofre do piloto."""
    try:
        info = load_credentials_json()
    except SecretSourceError:
        raise SearchConsoleError("falha ao ler credencial do Search Console no cofre do piloto") from None
    except Exception:
        raise SearchConsoleError("falha ao ler credencial do Search Console no cofre do piloto") from None
    try:
        if credentials_factory is None:
            from google.oauth2.service_account import Credentials

            credentials_factory = Credentials.from_service_account_info
        if service_factory is None:
            from googleapiclient.discovery import build

            service_factory = build
        credentials = credentials_factory(info, scopes=[SEARCH_CONSOLE_SCOPE])
        return service_factory("searchconsole", "v1", credentials=credentials, cache_discovery=False)
    except SearchConsoleError:
        raise
    except Exception:
        raise SearchConsoleError("cliente Search Console indisponivel") from None


def audit_search_console(
    crawl_report: Any,
    start_date: str,
    end_date: str,
    *,
    service: Any | None = None,
    max_inspections: int = MAX_INSPECTIONS_PER_DAY,
    page_size: int = MAX_ANALYTICS_PAGE_SIZE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> SearchConsoleReport:
    """Consulta dados finais e inspeciona cada URL HTML descoberta, sem escrita."""
    _validate_interval(start_date, end_date)
    if not isinstance(max_inspections, int) or isinstance(max_inspections, bool) or not 1 <= max_inspections <= MAX_INSPECTIONS_PER_DAY:
        raise SearchConsoleError("limite de inspecao invalido")
    if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= MAX_ANALYTICS_PAGE_SIZE:
        raise SearchConsoleError("tamanho de pagina Search Analytics invalido")
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 5:
        raise SearchConsoleError("limite de tentativas invalido")
    if service is None:
        service = create_service()

    property_url = _resolve_property(service, max_attempts, sleep)
    urls = _crawl_urls(crawl_report, property_url)
    if len(urls) > max_inspections:
        raise SearchConsoleError("quota diaria de URL Inspection insuficiente para o conjunto descoberto")

    aggregate_rows = _query(service, property_url, start_date, end_date, "final", page_size, max_attempts, sleep)
    if len(aggregate_rows) > 1:
        raise SearchConsoleError("resposta Search Analytics inconclusiva")
    # Sem linhas a API nao informou totais: o agregado fica vazio.
    aggregate = {field: aggregate_rows[0][field] for field in _METRIC_FIELDS} if aggregate_rows else {}
    page_rows = _query(service, property_url, start_date, end_date, "final", page_size, max_attempts, sleep, dimensions=["page"])
    inspections = tuple(
        _inspect(service, property_url, url, max_attempts, sleep) for url in urls
    )
    return SearchConsoleReport(property_url, start_date, end_date, "final", aggregate, tuple(page_rows), inspections)


def _validate_interval(start_date: str, end_date: str) -> None:
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if start.isoformat() != start_date or end.isoformat() != end_date or end < start:
            raise ValueError
    except (TypeError, ValueError):
        raise SearchConsoleError("intervalo de datas invalido") from None


def _resolve_property(service: Any, attempts: int, sleep: Callable[[float], None]) -> str:
    response = _execute(lambda: service.sites().list(), attempts, sleep)
    sites = response.get("siteEntry", []) if isinstance(response, dict) else []
    matches = [site.get("siteUrl") for site in sites if isinstance(site, dict) and _property_matches(site.get("siteUrl"))]
    # Mais de uma correspondencia nunca e desempatada: a escolha seria silenciosa.
    if len(matches) != 1:
        raise SearchConsoleError("propriedade mansaodolago.com ausente ou ambigua no Search Console")
    return matches[0]


def _property_matches(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if _is_domain_property(value):
        return True
    if not _PROPERTY_SCHEME.match(value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.hostname is not None
            and parsed.hostname.lower() in (PROPERTY_DOMAIN, "www." + PROPERTY_DOMAIN)
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def _is_domain_property(value: str) -> bool:
    return value.lower() == "sc-domain:" + PROPERTY_DOMAIN


def _crawl_urls(report: Any, property_url: str) -> tuple[str, ...]:
    """URLs finais de paginas HTML 2xx, mais os documentos HTML do sitemap."""
    urls: set[str] = set()
    for page in getattr(report, "pages", ()):
        status = getattr(page, "status", None)
        url = getattr(page, "final_url", None)
        if not isinstance(status, int) or not 200 <= status <= 299 or not isinstance(url, str):
            continue
        content_type = (getattr(page, "content_type", None) or "").lower()
        if content_type:
            is_html = "text/html" in content_type or "application/xhtml+xml" in content_type
        else:
            is_html = crawler.is_crawl_document(url)
        if is_html and _url_belongs(url, property_url):
            urls.add(url)
    sitemap = getattr(report, "sitemap", None)
    for url in getattr(sitemap, "references", ()):
        if isinstance(url, str) and crawler.is_crawl_document(url) and _url_belongs(url, property_url):
            urls.add(url)
    return tuple(sorted(urls))


def _url_belongs(url: str, property_url: str) -> bool:
    """Dominio: o host e seus subdominios. URL-prefix: esquema, host, porta e caminho."""
    try:
        candidate = urlsplit(url)
        host = (candidate.hostname or "").lower()
        if candidate.scheme not in ("http", "https") or not host:
            return False
        if _is_domain_property(property_url):
            return host == PROPERTY_DOMAIN or host.endswith("." + PROPERTY_DOMAIN)
        prop = urlsplit(property_url)
        default_port = 443 if prop.scheme.lower() == "https" else 80
        return (
            candidate.scheme == prop.scheme.lower()
            and host == (prop.hostname or "").lower()
            and (candidate.port or default_port) == (prop.port or default_port)
            and (candidate.path or "/").startswith(prop.path or "/")
        )
    except ValueError:
        return False


def _query(service: Any, property_url: str, start: str, end: str, state: str, page_size: int, attempts: int, sleep: Callable[[float], None], *, dimensions: list[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start_row = 0
    while True:
        body: dict[str, Any] = {"startDate": start, "endDate": end, "dataState": state, "rowLimit": page_size, "startRow": start_row}
        if dimensions:
            body["dimensions"] = dimensions
        response = _execute(lambda body=body: service.searchanalytics().query(siteUrl=property_url, body=body), attempts, sleep)
        if not isinstance(response, dict):
            raise SearchConsoleError("resposta Search Analytics inconclusiva")
        batch = response.get("rows", [])
        if not isinstance(batch, list) or any(not _valid_row(row, len(dimensions or ())) for row in batch):
            raise SearchConsoleError("resposta Search Analytics inconclusiva")
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        start_row += len(batch)


def _valid_row(row: Any, dimension_count: int) -> bool:
    """Linha completa: quatro metricas finitas e uma chave por dimensao pedida."""
    if not isinstance(row, dict):
        return False
    for field in _METRIC_FIELDS:
        value = row.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not math.isfinite(value) or value < 0:
            return False
    if dimension_count == 0:
        return True
    keys = row.get("keys")
    return (
        isinstance(keys, list)
        and len(keys) == dimension_count
        and all(isinstance(key, str) and key for key in keys)
    )


def _inspect(service: Any, property_url: str, url: str, attempts: int, sleep: Callable[[float], None]) -> Inspection:
    response = _execute(
        lambda: service.urlInspection().index().inspect(
            body={"inspectionUrl": url, "siteUrl": property_url, "languageCode": "pt-BR"}
        ),
        attempts,
        sleep,
    )
    result = response.get("inspectionResult") if isinstance(response, dict) else None
    index = result.get("indexStatusResult") if isinstance(result, dict) else None
    index = index if isinstance(index, dict) else {}
    fields = {
        "verdict": index.get("verdict"),
        "coverageState": index.get("coverageState"),
        "robotsTxtState": index.get("robotsTxtState"),
        "indexingState": index.get("indexingState"),
        "pageFetchState": index.get("pageFetchState"),
        "lastCrawlTime": index.get("lastCrawlTime"),
    }
    errors: list[str] = []
    unknown: list[str] = []
    _classify_state(fields, "verdict", lambda v: v == "PASS", errors, unknown)
    _classify_state(fields, "robotsTxtState", lambda v: v == "ALLOWED", errors, unknown)
    _classify_state(fields, "indexingState", lambda v: v == "INDEXING_ALLOWED", errors, unknown)
    _classify_state(fields, "pageFetchState", lambda v: v == "SUCCESSFUL", errors, unknown)
    _mark_unknown(fields, "coverageState", unknown)
    _mark_unknown(fields, "lastCrawlTime", unknown)
    classification = "error" if errors else ("unknown" if unknown else "ok")
    return Inspection(url, fields["verdict"], fields["coverageState"], fields["robotsTxtState"], fields["indexingState"], fields["pageFetchState"], fields["lastCrawlTime"], classification, tuple(errors), tuple(unknown))


def _classify_state(fields: dict[str, Any], name: str, healthy: Callable[[str], bool], errors: list[str], unknown: list[str]) -> None:
    value = fields.get(name)
    if not isinstance(value, str) or not value or value.endswith("_UNSPECIFIED"):
        unknown.append(name)
    elif not healthy(value):
        errors.append(name)


def _mark_unknown(fields: dict[str, Any], name: str, unknown: list[str]) -> None:
    value = fields.get(name)
    if not isinstance(value, str) or not value or value.endswith("_UNSPECIFIED"):
        unknown.append(name)


def _execute(request_factory: Callable[[], Any], attempts: int, sleep: Callable[[float], None]) -> Any:
    for attempt in range(attempts):
        try:
            return request_factory().execute(num_retries=0)
        except Exception as exc:
            status, quota = _api_error(exc)
            if status == 429 or (status is not None and 500 <= status <= 599):
                if attempt + 1 < attempts:
                    sleep(min(2 ** attempt, 8))
                    continue
                raise SearchConsoleError("Search Console temporariamente indisponivel apos novas tentativas") from None
            if quota:
                raise SearchConsoleError("quota Search Console esgotada") from None
            if status in (401, 403):
                raise SearchConsoleError("autenticacao ou autorizacao Search Console recusada") from None
            if status in (400, 404):
                raise SearchConsoleError("propriedade ou consulta Search Console invalida") from None
            raise SearchConsoleError("falha na consulta Search Console") from None
    raise SearchConsoleError("falha na consulta Search Console")


def _api_error(exc: Exception) -> tuple[int | None, bool]:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if not isinstance(status, int):
        status = None
    quota = False
    content = getattr(exc, "content", b"")
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="ignore")
    if isinstance(content, str):
        try:
            data = json.loads(content)
            message = json.dumps(data, ensure_ascii=True).lower()
            quota = any(term in message for term in ("quotaexceeded", "dailylimitexceeded", "userratelimitexceeded", "ratelimitexceeded"))
        except (ValueError, TypeError):
            pass
    return status, quota
