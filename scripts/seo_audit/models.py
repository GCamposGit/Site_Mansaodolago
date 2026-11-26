"""Contrato do relatorio de crawl publico.

Ausencias, duplicidades e classes de falha ficam em campos proprios.
4xx e 5xx confirmados nao dividem lista com timeout, 429 ou falha inconclusiva.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CLASS_OK = "ok"
CLASS_CONFIRMED_4XX = "confirmed_4xx"
CLASS_CONFIRMED_5XX = "confirmed_5xx"
CLASS_TIMEOUT = "timeout"
CLASS_RATE_LIMITED = "rate_limited"
CLASS_INCONCLUSIVE = "inconclusive"

ERROR_TIMEOUT = "timeout"
ERROR_INCONCLUSIVE = "inconclusive"

DIV_SITEMAP_URL_NOT_REACHED = "sitemap_url_not_reached"
DIV_SITEMAP_INVALID = "sitemap_invalid"
DIV_SITEMAP_UNAVAILABLE = "sitemap_unavailable"
DIV_SITEMAP_INVALID_LOC = "sitemap_invalid_loc"
DIV_SITEMAP_EXTERNAL_LOC = "sitemap_external_loc"
DIV_SITEMAP_DUPLICATE_LOC = "sitemap_duplicate_loc"
DIV_SITEMAP_NESTED_LIMIT = "sitemap_nested_limit"
DIV_ROBOTS_UNAVAILABLE = "robots_unavailable"
DIV_ROBOTS_INVALID_LINE = "robots_invalid_line"
DIV_URL_DISALLOWED = "url_disallowed"

LINK_CLASSIFICATIONS = (
    CLASS_OK,
    CLASS_CONFIRMED_4XX,
    CLASS_CONFIRMED_5XX,
    CLASS_TIMEOUT,
    CLASS_RATE_LIMITED,
    CLASS_INCONCLUSIVE,
)


def _box(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_box(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return value


class ReportModel:
    """Serializa dataclass aninhada sem reordenar campos."""

    def to_dict(self) -> dict[str, Any]:
        fields = getattr(self, "__dataclass_fields__", {})
        return {key: _box(getattr(self, key)) for key in fields}


@dataclass(frozen=True)
class Divergence(ReportModel):
    code: str
    detail: str


@dataclass(frozen=True)
class DuplicateGroup(ReportModel):
    value: str
    urls: tuple[str, ...]


@dataclass(frozen=True)
class PageRecord(ReportModel):
    requested_url: str
    final_url: str
    status: int | None
    content_type: str | None
    title: str | None
    meta_description: str | None
    canonical: str | None
    links: tuple[str, ...]
    duplicate_links: tuple[str, ...]
    ignored_non_http: tuple[str, ...]
    title_absent: bool
    title_duplicate: bool
    meta_description_absent: bool
    meta_description_duplicate: bool
    canonical_absent: bool
    canonical_duplicate: bool
    redirected: bool
    attempts: int
    error_kind: str | None
    metadata_collected: bool = True


@dataclass(frozen=True)
class RobotsReport(ReportModel):
    url: str
    final_url: str
    status: int | None
    content_type: str | None
    parsed: bool
    parse_error: str | None
    references: tuple[str, ...]
    allow: tuple[str, ...]
    disallow: tuple[str, ...]
    divergences: tuple[Divergence, ...]
    attempts: int


@dataclass(frozen=True)
class SitemapDocument(ReportModel):
    url: str
    final_url: str
    status: int | None
    content_type: str | None
    parsed: bool
    parse_error: str | None
    kind: str
    references: tuple[str, ...]
    rejected: tuple[str, ...]
    divergences: tuple[Divergence, ...]
    attempts: int


@dataclass(frozen=True)
class SitemapReport(ReportModel):
    documents: tuple[SitemapDocument, ...]
    references: tuple[str, ...]
    not_reached: tuple[str, ...]
    divergences: tuple[Divergence, ...]


@dataclass(frozen=True)
class LinkCheck(ReportModel):
    url: str
    status: int | None
    classification: str
    attempts: int
    error_kind: str | None


@dataclass(frozen=True)
class LinkReport(ReportModel):
    checks: tuple[LinkCheck, ...]
    ok: tuple[LinkCheck, ...]
    confirmed_4xx: tuple[LinkCheck, ...]
    confirmed_5xx: tuple[LinkCheck, ...]
    timeouts: tuple[LinkCheck, ...]
    rate_limited: tuple[LinkCheck, ...]
    inconclusive: tuple[LinkCheck, ...]


@dataclass(frozen=True)
class CrawlReport(ReportModel):
    seed: str
    crawl_host: str
    pages: tuple[PageRecord, ...]
    robots: RobotsReport
    sitemap: SitemapReport
    links: LinkReport
    duplicate_titles: tuple[DuplicateGroup, ...]
    duplicate_meta_descriptions: tuple[DuplicateGroup, ...]
    duplicate_canonicals: tuple[DuplicateGroup, ...]
    divergences: tuple[Divergence, ...]
