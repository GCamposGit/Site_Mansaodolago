"""Crawl publico e somente leitura de metadados, robots.txt e sitemap.

Parte de https://mansaodolago.com, acompanha redirects e so enfileira HTML
do mesmo host (o host final do seed). URLs validas do sitemap entram na
fila. Links http unicos sao verificados com timeout e retry limitado.
Fragmentos sao removidos. Esquemas que nao sao http(s) sao ignorados.
A credencial do Search Console nao e lida aqui.
"""

from __future__ import annotations

import heapq
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit, urlunsplit, urljoin
from xml.etree import ElementTree

try:
    from .models import (
        CLASS_CONFIRMED_4XX,
        CLASS_CONFIRMED_5XX,
        CLASS_INCONCLUSIVE,
        CLASS_OK,
        CLASS_RATE_LIMITED,
        CLASS_TIMEOUT,
        DIV_ROBOTS_INVALID_LINE,
        DIV_ROBOTS_UNAVAILABLE,
        DIV_SITEMAP_DUPLICATE_LOC,
        DIV_SITEMAP_EXTERNAL_LOC,
        DIV_SITEMAP_INVALID,
        DIV_SITEMAP_INVALID_LOC,
        DIV_SITEMAP_NESTED_LIMIT,
        DIV_SITEMAP_UNAVAILABLE,
        DIV_SITEMAP_URL_NOT_REACHED,
        DIV_URL_DISALLOWED,
        ERROR_INCONCLUSIVE,
        ERROR_TIMEOUT,
        CrawlReport,
        Divergence,
        DuplicateGroup,
        LinkCheck,
        LinkReport,
        PageRecord,
        RobotsReport,
        SitemapDocument,
        SitemapReport,
    )
    from .sanitize import to_plain
except ImportError:
    from models import (
        CLASS_CONFIRMED_4XX,
        CLASS_CONFIRMED_5XX,
        CLASS_INCONCLUSIVE,
        CLASS_OK,
        CLASS_RATE_LIMITED,
        CLASS_TIMEOUT,
        DIV_ROBOTS_INVALID_LINE,
        DIV_ROBOTS_UNAVAILABLE,
        DIV_SITEMAP_DUPLICATE_LOC,
        DIV_SITEMAP_EXTERNAL_LOC,
        DIV_SITEMAP_INVALID,
        DIV_SITEMAP_INVALID_LOC,
        DIV_SITEMAP_NESTED_LIMIT,
        DIV_SITEMAP_UNAVAILABLE,
        DIV_SITEMAP_URL_NOT_REACHED,
        DIV_URL_DISALLOWED,
        ERROR_INCONCLUSIVE,
        ERROR_TIMEOUT,
        CrawlReport,
        Divergence,
        DuplicateGroup,
        LinkCheck,
        LinkReport,
        PageRecord,
        RobotsReport,
        SitemapDocument,
        SitemapReport,
    )
    from sanitize import to_plain

DEFAULT_SEED = "https://mansaodolago.com"
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_MAX_PAGES = 200
MAX_BODY = 1_048_576
MAX_SITEMAP_DOCS = 20
MAX_SITEMAP_DEPTH = 3
USER_AGENT = "MansaodolagoSEOAudit/1.0 (+https://mansaodolago.com)"

_PAGE_SUFFIXES = {".html", ".htm", ".php", ".asp", ".aspx", ".xhtml"}
_RETRYABLE = {CLASS_TIMEOUT, CLASS_RATE_LIMITED}
_TRANSIENT_STATUS = {502, 503, 504}
_CHARSET_RE = re.compile(r"charset=[\"']?([A-Za-z0-9._-]+)", re.IGNORECASE)


class CrawlError(ValueError):
    """Seed ou limite invalido. A mensagem nao carrega corpo de resposta."""


Fetcher = Callable[..., "FetchResult"]


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int | None
    content_type: str | None
    body: bytes
    error_kind: str | None
    error_detail: str | None


@dataclass(frozen=True)
class AttemptedFetch:
    result: FetchResult
    attempts: int
    classification: str


@dataclass(frozen=True)
class HtmlExtract:
    title: str | None
    title_absent: bool
    title_duplicate: bool
    meta_description: str | None
    meta_description_absent: bool
    meta_description_duplicate: bool
    canonical: str | None
    canonical_absent: bool
    canonical_duplicate: bool
    links: tuple[str, ...]
    duplicate_links: tuple[str, ...]
    ignored_non_http: tuple[str, ...]
    collected: bool = True


@dataclass(frozen=True)
class RobotsParse:
    sitemaps: tuple[str, ...]
    allow: tuple[str, ...]
    disallow: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class SitemapParse:
    kind: str
    page_locs: tuple[str, ...]
    child_locs: tuple[str, ...]
    parse_error: str | None


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({item for item in items if item is not None}))


def _unique_divs(items: Iterable[Divergence]) -> tuple[Divergence, ...]:
    return tuple(sorted(set(items), key=lambda item: (item.code, item.detail)))


def _short(value: str, limit: int = 180) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[:limit]


def _explicit_scheme(value: str) -> str | None:
    text = value.strip()
    if text.startswith("//"):
        return None
    colon = text.find(":")
    if colon <= 0:
        return None
    scheme = text[:colon]
    if not scheme[0].isalpha():
        return None
    if any(not (ch.isalnum() or ch in "+-.") for ch in scheme):
        return None
    return scheme.lower()


def _clean_path(path: str) -> str:
    if path == "":
        return "/"
    trailing = path.endswith("/")
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    cleaned = "/" + "/".join(parts)
    if trailing and cleaned != "/":
        cleaned += "/"
    return cleaned


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Normaliza URL http(s). Devolve None para esquema ignorado ou lixo.

    Fragmento sai. Host fica em minusculas. Porta padrao sai. Userinfo sai.
    """
    raw = url.strip()
    if raw == "" or any(ch in raw for ch in "\r\n\t"):
        return None
    scheme = _explicit_scheme(raw)
    if scheme is not None and scheme not in ("http", "https"):
        return None
    if base is None:
        if scheme not in ("http", "https"):
            return None
        candidate = raw
    elif scheme in ("http", "https"):
        candidate = raw
    else:
        try:
            candidate = urljoin(base, raw)
        except ValueError:
            return None
    if any(ch.isspace() for ch in candidate):
        return None
    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError:
        # Porta ou host malformado invalida so esta referencia.
        return None
    normalized_scheme = parts.scheme.lower()
    if normalized_scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if host == "":
        return None
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if (normalized_scheme == "http" and port == 80) or (
        normalized_scheme == "https" and port == 443
    ):
        port = None
    netloc = host if port is None else f"{host}:{port}"
    path = _clean_path(parts.path)
    return urlunsplit((normalized_scheme, netloc, path, parts.query, ""))


def origin_key(url: str) -> tuple[str, int | None]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    if (parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443):
        port = None
    return host, port


def same_site(url: str, reference: str) -> bool:
    return origin_key(url) == origin_key(reference)


def _same_owner(url: str, seed: str) -> bool:
    """Mesmo host, aceitando a troca entre apex e www."""
    return host_name(url).removeprefix("www.") == host_name(seed).removeprefix("www.")


def host_name(url: str) -> str:
    return origin_key(url)[0]


def _replace_path(url: str, path: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def is_crawl_document(url: str) -> bool:
    """HTML navegavel. Asset com sufixo conhecido fica so na checagem de link."""
    path = urlsplit(url).path
    if path.endswith("/"):
        return True
    leaf = path.rsplit("/", 1)[-1]
    if "." not in leaf:
        return True
    suffix = "." + leaf.rsplit(".", 1)[-1].lower()
    return suffix in _PAGE_SUFFIXES


def _media_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def _is_html_type(content_type: str | None) -> bool:
    return _media_type(content_type) in {"text/html", "application/xhtml+xml"}


def _looks_like_html(body: bytes) -> bool:
    sample = body[:200].lstrip().lower()
    return sample.startswith((b"<!doctype html", b"<html", b"<head", b"<title"))


def _is_html_document(content_type: str | None, body: bytes) -> bool:
    if content_type:
        return _is_html_type(content_type)
    return _looks_like_html(body)


def classify_result(result: FetchResult) -> str:
    """Separa 4xx/5xx confirmados de timeout, 429 e falha sem status."""
    status = result.status
    if status == 429:
        return CLASS_RATE_LIMITED
    if isinstance(status, int) and 400 <= status <= 499:
        return CLASS_CONFIRMED_4XX
    if isinstance(status, int) and 500 <= status <= 599:
        return CLASS_CONFIRMED_5XX
    if result.error_kind == ERROR_TIMEOUT:
        return CLASS_TIMEOUT
    if isinstance(status, int) and 200 <= status <= 299:
        return CLASS_OK
    return CLASS_INCONCLUSIVE


def _should_retry(result: FetchResult, classification: str) -> bool:
    if classification in _RETRYABLE or result.status in _TRANSIENT_STATUS:
        return True
    # 3xx ja e uma resposta. So repetimos falha de transporte, sem status.
    return classification == CLASS_INCONCLUSIVE and result.status is None


def _failure(url: str, kind: str, detail: str) -> FetchResult:
    return FetchResult(url, url, None, None, b"", kind, detail)


def fetch_with_retries(
    url: str,
    fetcher: Fetcher,
    *,
    timeout: float,
    max_attempts: int,
    cache: dict[str, AttemptedFetch] | None = None,
) -> AttemptedFetch:
    store = cache if cache is not None else {}
    cached = store.get(url)
    if cached is not None:
        return cached
    last: AttemptedFetch | None = None
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        try:
            result = fetcher(url, timeout=timeout)
        except Exception:
            result = _failure(url, ERROR_INCONCLUSIVE, "exception")
        if not isinstance(result, FetchResult):
            result = _failure(url, ERROR_INCONCLUSIVE, "invalid")
        classification = classify_result(result)
        last = AttemptedFetch(result, attempts, classification)
        if not _should_retry(result, classification) or attempts == max_attempts:
            break
    if last is None:
        last = AttemptedFetch(_failure(url, ERROR_INCONCLUSIVE, "invalid"), 0, CLASS_INCONCLUSIVE)
    store[url] = last
    return last


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _first_usable(values: list[str]) -> str | None:
    for value in values:
        if value != "":
            return value
    return None


class _HtmlCollector(HTMLParser):
    """Coleta title, description, canonical e href. Ignora script e style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self.descriptions: list[str] = []
        self.canonicals: list[str] = []
        self.hrefs: list[str] = []
        self.base_href: str | None = None
        self._skip_depth = 0
        self._title_open = False
        self._title_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        attr = _attr_map(attrs)
        if name == "base" and self.base_href is None:
            href = attr.get("href", "").strip()
            if href:
                self.base_href = href
            return
        if name == "title":
            self._title_open = True
            self._title_buf = []
            return
        if name == "meta" and attr.get("name", "").lower() == "description":
            self.descriptions.append(attr.get("content", "").strip())
            return
        if name == "link" and "canonical" in attr.get("rel", "").lower().split():
            self.canonicals.append(attr.get("href", "").strip())
            return
        if name in ("a", "area") and "href" in attr:
            self.hrefs.append(attr.get("href", ""))

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if name == "title" and self._title_open:
            self._flush_title()

    def close(self) -> None:
        if self._title_open:
            self._flush_title()
        super().close()

    def _flush_title(self) -> None:
        self.titles.append(_clean_text("".join(self._title_buf)))
        self._title_open = False
        self._title_buf = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._title_open:
            return
        self._title_buf.append(data)


def _attr_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for key, value in attrs:
        name = key.lower()
        if name not in mapped:
            mapped[name] = "" if value is None else value
    return mapped


def _decode_html(body: bytes, content_type: str | None) -> str:
    charset = ""
    if content_type:
        match = _CHARSET_RE.search(content_type)
        if match:
            charset = match.group(1)
    if charset == "":
        head = body[:800].decode("ascii", errors="ignore")
        match = _CHARSET_RE.search(head)
        if match:
            charset = match.group(1)
    if charset == "":
        charset = "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _uncollected_html() -> HtmlExtract:
    """HTML nao analisado: nada se afirma sobre ausencia de metadados."""
    return HtmlExtract(
        title=None,
        title_absent=False,
        title_duplicate=False,
        meta_description=None,
        meta_description_absent=False,
        meta_description_duplicate=False,
        canonical=None,
        canonical_absent=False,
        canonical_duplicate=False,
        links=(),
        duplicate_links=(),
        ignored_non_http=(),
        collected=False,
    )


def parse_html(html: str, base_url: str) -> HtmlExtract:
    collector = _HtmlCollector()
    collector.feed(html)
    collector.close()
    base = base_url
    if collector.base_href:
        resolved = normalize_url(collector.base_href, base_url)
        if resolved:
            base = resolved
    titles = [_clean_text(title) for title in collector.titles]
    descriptions = [_clean_text(item) for item in collector.descriptions]
    canonical_raw = [item.strip() for item in collector.canonicals if item.strip()]
    canonicals = []
    for href in canonical_raw:
        normalized = normalize_url(href, base)
        if normalized:
            canonicals.append(normalized)
    links: list[str] = []
    ignored: list[str] = []
    for href in collector.hrefs:
        text = href.strip()
        if text == "":
            continue
        scheme = _explicit_scheme(text)
        if scheme is not None and scheme not in ("http", "https"):
            ignored.append(text)
            continue
        normalized = normalize_url(text, base)
        if normalized is None:
            continue
        links.append(normalized)
    title = _first_usable(titles)
    description = _first_usable(descriptions)
    canonical = canonicals[0] if canonicals else None
    counts: dict[str, int] = {}
    for link in links:
        counts[link] = counts.get(link, 0) + 1
    duplicate_links = tuple(sorted(link for link, count in counts.items() if count > 1))
    return HtmlExtract(
        title=title,
        title_absent=title is None,
        title_duplicate=len(titles) > 1,
        meta_description=description,
        meta_description_absent=description is None,
        meta_description_duplicate=len(descriptions) > 1,
        canonical=canonical,
        canonical_absent=canonical is None,
        canonical_duplicate=len(canonical_raw) > 1,
        links=_unique(links),
        duplicate_links=duplicate_links,
        ignored_non_http=_unique(ignored),
    )


def _strip_robot_comment(line: str) -> str:
    if "#" not in line:
        return line
    return line.split("#", 1)[0]


def parse_robots(text: str) -> RobotsParse:
    """Le grupos User-agent. Regras efetivas sao as do agente *."""
    sitemaps: list[str] = []
    errors: list[str] = []
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    seen_rule = False

    def close_group() -> None:
        nonlocal agents, rules, seen_rule
        if agents:
            groups.append((agents, rules))
        agents = []
        rules = []
        seen_rule = False

    for raw_line in text.splitlines():
        line = _strip_robot_comment(raw_line).strip()
        if line == "":
            continue
        if ":" not in line:
            errors.append("linha invalida: " + _short(line, 80))
            continue
        key, value = line.split(":", 1)
        field = key.strip().lower()
        payload = value.strip()
        if field == "sitemap":
            sitemaps.append(payload)
            continue
        if field == "user-agent":
            if seen_rule:
                close_group()
            agents.append(payload.lower())
            continue
        if field in ("allow", "disallow"):
            if not agents:
                errors.append("diretiva fora de grupo: " + _short(line, 80))
                continue
            seen_rule = True
            rules.append((field, payload))
            continue
        errors.append("linha invalida: " + _short(line, 80))
    close_group()

    allow: list[str] = []
    disallow: list[str] = []
    for group_agents, group_rules in groups:
        if "*" not in group_agents:
            continue
        for field, payload in group_rules:
            if field == "allow":
                if payload != "":
                    allow.append(payload)
            elif payload != "":
                disallow.append(payload)
    return RobotsParse(
        sitemaps=_unique(sitemaps),
        allow=_unique(allow),
        disallow=_unique(disallow),
        errors=_unique(errors),
    )


def _rule_match_length(rule: str, path: str) -> int | None:
    if rule == "":
        return None
    anchored = rule.endswith("$")
    body = rule[:-1] if anchored else rule
    pieces = body.split("*")
    expression = "^" + ".*".join(re.escape(piece) for piece in pieces)
    if anchored:
        expression += "$"
    if re.match(expression, path):
        return len(rule)
    return None


def rules_disallow(path: str, allow: Iterable[str], disallow: Iterable[str]) -> bool:
    """Maior regra vence. Empate fica com Allow."""
    best_allow = -1
    best_disallow = -1
    for rule in allow:
        matched = _rule_match_length(rule, path)
        if matched is not None:
            best_allow = max(best_allow, matched)
    for rule in disallow:
        matched = _rule_match_length(rule, path)
        if matched is not None:
            best_disallow = max(best_disallow, matched)
    if best_disallow < 0:
        return False
    return best_disallow > best_allow


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_sitemap(body: bytes) -> SitemapParse:
    payload = body[3:] if body.startswith(b"\xef\xbb\xbf") else body
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return SitemapParse("unknown", (), (), "XML invalido")
    kind = _local_name(root.tag).lower()
    if kind not in ("urlset", "sitemapindex"):
        return SitemapParse("unknown", (), (), "elemento raiz inesperado")
    page_locs: list[str] = []
    child_locs: list[str] = []
    wrapper = "url" if kind == "urlset" else "sitemap"
    target = page_locs if kind == "urlset" else child_locs
    for node in list(root):
        if _local_name(node.tag).lower() != wrapper:
            continue
        for child in list(node):
            if _local_name(child.tag).lower() != "loc" or child.text is None:
                continue
            target.append(child.text.strip())
    mapped = "urlset" if kind == "urlset" else "index"
    return SitemapParse(mapped, tuple(page_locs), tuple(child_locs), None)


def _normalize_reference(value: str, base: str) -> str | None:
    text = value.strip()
    if text == "":
        return None
    scheme = _explicit_scheme(text)
    if scheme in ("http", "https") or text.startswith("/") or text.startswith("//"):
        return normalize_url(text, base)
    return None


class UrllibFetcher:
    """GET com redirects do urllib. Nao envia corpo nem credencial."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_S, user_agent: str = USER_AGENT) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def __call__(self, url: str, *, timeout: float | None = None) -> FetchResult:
        effective = self.timeout if timeout is None else timeout
        if normalize_url(url) is None:
            return _failure(url, ERROR_INCONCLUSIVE, "url")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=effective) as response:
                return _from_http(url, response)
        except TimeoutError:
            return _failure(url, ERROR_TIMEOUT, "TimeoutError")
        except urllib.error.HTTPError as exc:
            return _from_http_error(url, exc)
        except urllib.error.URLError as exc:
            return _from_url_error(url, exc)
        except http.client.HTTPException as exc:
            return _failure(url, ERROR_INCONCLUSIVE, type(exc).__name__)
        except OSError as exc:
            if _is_timeout(exc):
                return _failure(url, ERROR_TIMEOUT, "TimeoutError")
            return _failure(url, ERROR_INCONCLUSIVE, type(exc).__name__)


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if "timeout" in type(exc).__name__.lower():
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, BaseException) and reason is not exc:
        return _is_timeout(reason)
    return False


def _header_content_type(headers: Any) -> str | None:
    if headers is None:
        return None
    value = headers.get("Content-Type")
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text == "":
        return None
    if len(text) > 200:
        return text[:200]
    return text


def _read_limited(source: Any) -> bytes:
    """Le ate MAX_BODY. Falha ou corpo truncado sobe para a tentativa."""
    raw = source.read(MAX_BODY + 1) or b""
    remaining = getattr(source, "length", None)
    if len(raw) <= MAX_BODY and isinstance(remaining, int) and remaining > 0:
        raise http.client.IncompleteRead(b"", remaining)
    return raw[:MAX_BODY]


def _read_error_body(source: Any) -> bytes:
    """Em resposta de erro o status ja e a evidencia; o corpo e opcional."""
    try:
        return _read_limited(source)
    except Exception:
        return b""


def _from_http(url: str, response: Any) -> FetchResult:
    status = getattr(response, "status", None)
    if status is None:
        status = response.getcode()
    final_url = response.geturl() or url
    return FetchResult(
        requested_url=url,
        final_url=final_url,
        status=int(status),
        content_type=_header_content_type(response.headers),
        body=_read_limited(response),
        error_kind=None,
        error_detail=None,
    )


def _from_http_error(url: str, exc: urllib.error.HTTPError) -> FetchResult:
    final_url = url
    try:
        final_url = exc.geturl() or url
    except Exception:
        final_url = url
    status = int(exc.code)
    if _is_timeout(exc):
        return _failure(url, ERROR_TIMEOUT, "TimeoutError")
    return FetchResult(
        requested_url=url,
        final_url=final_url,
        status=status,
        content_type=_header_content_type(exc.headers),
        body=_read_error_body(exc),
        error_kind=None,
        error_detail=None,
    )


def _from_url_error(url: str, exc: urllib.error.URLError) -> FetchResult:
    if _is_timeout(exc):
        return _failure(url, ERROR_TIMEOUT, "TimeoutError")
    reason = exc.reason
    detail = type(reason).__name__ if reason is not None else type(exc).__name__
    return _failure(url, ERROR_INCONCLUSIVE, detail)


def _page_from_extract(
    requested: str,
    final: str,
    attempted: AttemptedFetch,
    extract: HtmlExtract,
) -> PageRecord:
    content_type = attempted.result.content_type
    return PageRecord(
        requested_url=requested,
        final_url=final,
        status=attempted.result.status,
        content_type=content_type,
        title=extract.title,
        meta_description=extract.meta_description,
        canonical=extract.canonical,
        links=extract.links,
        duplicate_links=extract.duplicate_links,
        ignored_non_http=extract.ignored_non_http,
        title_absent=extract.title_absent,
        title_duplicate=extract.title_duplicate,
        meta_description_absent=extract.meta_description_absent,
        meta_description_duplicate=extract.meta_description_duplicate,
        canonical_absent=extract.canonical_absent,
        canonical_duplicate=extract.canonical_duplicate,
        redirected=requested != final,
        attempts=attempted.attempts,
        error_kind=attempted.result.error_kind,
        metadata_collected=extract.collected,
    )


def _blank_page(requested: str, final: str, attempted: AttemptedFetch) -> PageRecord:
    return _page_from_extract(requested, final, attempted, _uncollected_html())


def _decode_text(body: bytes) -> str:
    payload = body[3:] if body.startswith(b"\xef\xbb\xbf") else body
    return payload.decode("utf-8", errors="replace")


def _unavailable_robots(url: str, attempted: AttemptedFetch, reason: str) -> RobotsReport:
    return RobotsReport(
        url=url,
        final_url=normalize_url(attempted.result.final_url) or url,
        status=attempted.result.status,
        content_type=attempted.result.content_type,
        parsed=False,
        parse_error=reason,
        references=(),
        allow=(),
        disallow=(),
        divergences=(Divergence(DIV_ROBOTS_UNAVAILABLE, url),),
        attempts=attempted.attempts,
    )


def _load_robots(
    reference: str,
    fetch: Callable[[str], AttemptedFetch],
) -> tuple[RobotsReport, tuple[str, ...]]:
    url = _replace_path(reference, "/robots.txt")
    attempted = fetch(url)
    result = attempted.result
    final = normalize_url(result.final_url) or url
    if attempted.classification != CLASS_OK:
        reason = "timeout" if attempted.classification == CLASS_TIMEOUT else "indisponivel"
        if result.status == 404:
            reason = "ausente"
        return _unavailable_robots(url, attempted, reason), ()
    if not same_site(final, reference) or _is_html_type(result.content_type):
        return _unavailable_robots(url, attempted, "resposta nao e robots.txt"), ()
    parsed = parse_robots(_decode_text(result.body))
    references: list[str] = []
    divergences: list[Divergence] = []
    for line_error in parsed.errors:
        divergences.append(Divergence(DIV_ROBOTS_INVALID_LINE, line_error))
    for raw in parsed.sitemaps:
        normalized = _normalize_reference(raw, final)
        if normalized is None:
            divergences.append(Divergence(DIV_SITEMAP_INVALID_LOC, _short(raw) or "loc vazio"))
            continue
        references.append(normalized)
    report = RobotsReport(
        url=url,
        final_url=final,
        status=result.status,
        content_type=result.content_type,
        parsed=True,
        parse_error=None,
        references=_unique(references),
        allow=parsed.allow,
        disallow=parsed.disallow,
        divergences=_unique_divs(divergences),
        attempts=attempted.attempts,
    )
    return report, report.references


def _document_failure(
    url: str,
    attempted: AttemptedFetch,
    *,
    parsed: bool,
    parse_error: str | None,
    divergence: Divergence,
) -> SitemapDocument:
    final = normalize_url(attempted.result.final_url) or url
    return SitemapDocument(
        url=url,
        final_url=final,
        status=attempted.result.status,
        content_type=attempted.result.content_type,
        parsed=parsed,
        parse_error=parse_error,
        kind="unknown",
        references=(),
        rejected=(),
        divergences=(divergence,),
        attempts=attempted.attempts,
    )


def _classify_locs(
    raw_locs: tuple[str, ...],
    *,
    base: str,
    reference: str,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[Divergence, ...]]:
    counts: dict[str, int] = {}
    rejected: list[str] = []
    divergences: list[Divergence] = []
    for raw in raw_locs:
        if raw.strip() == "":
            divergences.append(Divergence(DIV_SITEMAP_INVALID_LOC, "loc vazio"))
            continue
        normalized = _normalize_reference(raw, base)
        if normalized is None:
            rejected.append(_short(raw) or "loc vazio")
            divergences.append(Divergence(DIV_SITEMAP_INVALID_LOC, _short(raw) or "loc vazio"))
            continue
        if not same_site(normalized, reference):
            rejected.append(normalized)
            divergences.append(Divergence(DIV_SITEMAP_EXTERNAL_LOC, normalized))
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    accepted = tuple(sorted(counts))
    for loc, count in counts.items():
        if count > 1:
            divergences.append(Divergence(DIV_SITEMAP_DUPLICATE_LOC, loc))
    return accepted, _unique(rejected), _unique_divs(divergences)


def _load_sitemap_tree(
    seeds: tuple[str, ...],
    reference: str,
    fetch: Callable[[str], AttemptedFetch],
) -> tuple[list[SitemapDocument], tuple[str, ...], tuple[Divergence, ...]]:
    documents: list[SitemapDocument] = []
    page_urls: list[str] = []
    divergences: list[Divergence] = []
    seen: set[str] = set()

    def load(url: str, depth: int) -> None:
        if url in seen:
            return
        if len(documents) >= MAX_SITEMAP_DOCS or depth > MAX_SITEMAP_DEPTH:
            divergences.append(Divergence(DIV_SITEMAP_NESTED_LIMIT, url))
            return
        seen.add(url)
        attempted = fetch(url)
        result = attempted.result
        final = normalize_url(result.final_url) or url
        if attempted.classification != CLASS_OK or not same_site(final, reference):
            reason = "timeout" if attempted.classification == CLASS_TIMEOUT else "indisponivel"
            if result.status == 404:
                reason = "ausente"
            code = DIV_SITEMAP_UNAVAILABLE
            documents.append(
                _document_failure(
                    url,
                    attempted,
                    parsed=False,
                    parse_error=reason,
                    divergence=Divergence(code, url),
                )
            )
            divergences.append(Divergence(code, url))
            return
        if _is_html_type(result.content_type):
            documents.append(
                _document_failure(
                    url,
                    attempted,
                    parsed=False,
                    parse_error="resposta nao e sitemap.xml",
                    divergence=Divergence(DIV_SITEMAP_INVALID, url),
                )
            )
            divergences.append(Divergence(DIV_SITEMAP_INVALID, url))
            return
        parsed = parse_sitemap(result.body)
        if parsed.parse_error:
            documents.append(
                _document_failure(
                    url,
                    attempted,
                    parsed=False,
                    parse_error=parsed.parse_error,
                    divergence=Divergence(DIV_SITEMAP_INVALID, url),
                )
            )
            divergences.append(Divergence(DIV_SITEMAP_INVALID, url))
            return
        if parsed.kind == "index":
            children, rejected, loc_divs = _classify_locs(
                parsed.child_locs,
                base=final,
                reference=reference,
            )
            documents.append(
                SitemapDocument(
                    url=url,
                    final_url=final,
                    status=result.status,
                    content_type=result.content_type,
                    parsed=True,
                    parse_error=None,
                    kind="index",
                    references=children,
                    rejected=rejected,
                    divergences=loc_divs,
                    attempts=attempted.attempts,
                )
            )
            divergences.extend(loc_divs)
            for child in children:
                load(child, depth + 1)
            return
        pages, rejected, loc_divs = _classify_locs(
            parsed.page_locs,
            base=final,
            reference=reference,
        )
        documents.append(
            SitemapDocument(
                url=url,
                final_url=final,
                status=result.status,
                content_type=result.content_type,
                parsed=True,
                parse_error=None,
                kind="urlset",
                references=pages,
                rejected=rejected,
                divergences=loc_divs,
                attempts=attempted.attempts,
            )
        )
        divergences.extend(loc_divs)
        page_urls.extend(pages)

    for seed in sorted(set(seeds)):
        load(seed, 0)
    return documents, _unique(page_urls), _unique_divs(divergences)


def _shared_values(pages: list[PageRecord], attr: str) -> set[str]:
    buckets: dict[str, set[str]] = {}
    for page in pages:
        value = getattr(page, attr)
        if not value:
            continue
        buckets.setdefault(value, set()).add(page.requested_url)
    return {value for value, urls in buckets.items() if len(urls) > 1}


def _duplicate_groups(pages: list[PageRecord], attr: str) -> tuple[DuplicateGroup, ...]:
    buckets: dict[str, set[str]] = {}
    for page in pages:
        value = getattr(page, attr)
        if not value:
            continue
        buckets.setdefault(value, set()).add(page.requested_url)
    groups = [
        DuplicateGroup(value, tuple(sorted(urls)))
        for value, urls in buckets.items()
        if len(urls) > 1
    ]
    return tuple(sorted(groups, key=lambda group: (group.value, group.urls)))


def _apply_shared(pages: list[PageRecord]) -> list[PageRecord]:
    shared_titles = _shared_values(pages, "title")
    shared_metas = _shared_values(pages, "meta_description")
    shared_canonicals = _shared_values(pages, "canonical")
    updated: list[PageRecord] = []
    for page in pages:
        updated.append(
            replace(
                page,
                title_duplicate=page.title_duplicate or (page.title in shared_titles),
                meta_description_duplicate=(
                    page.meta_description_duplicate or (page.meta_description in shared_metas)
                ),
                canonical_duplicate=(
                    page.canonical_duplicate or (page.canonical in shared_canonicals)
                ),
            )
        )
    return updated


def _link_report(checks: list[LinkCheck]) -> LinkReport:
    ordered = tuple(sorted(checks, key=lambda item: item.url))

    def pick(classification: str) -> tuple[LinkCheck, ...]:
        return tuple(item for item in ordered if item.classification == classification)

    return LinkReport(
        checks=ordered,
        ok=pick(CLASS_OK),
        confirmed_4xx=pick(CLASS_CONFIRMED_4XX),
        confirmed_5xx=pick(CLASS_CONFIRMED_5XX),
        timeouts=pick(CLASS_TIMEOUT),
        rate_limited=pick(CLASS_RATE_LIMITED),
        inconclusive=pick(CLASS_INCONCLUSIVE),
    )


def _check_links(
    pages: Iterable[PageRecord],
    fetch: Callable[[str], AttemptedFetch],
) -> LinkReport:
    urls: set[str] = set()
    for page in pages:
        urls.update(page.links)
    checks: list[LinkCheck] = []
    for url in sorted(urls):
        attempted = fetch(url)
        checks.append(
            LinkCheck(
                url=url,
                status=attempted.result.status,
                classification=attempted.classification,
                attempts=attempted.attempts,
                error_kind=attempted.result.error_kind,
            )
        )
    return _link_report(checks)


def _disallowed_divergences(
    pages: Iterable[PageRecord],
    robots: RobotsReport,
    reference: str,
) -> tuple[Divergence, ...]:
    if not robots.parsed:
        return ()
    found: list[Divergence] = []
    for page in pages:
        for candidate in (page.requested_url, page.final_url):
            if not same_site(candidate, reference):
                continue
            path = urlsplit(candidate).path or "/"
            if rules_disallow(path, robots.allow, robots.disallow):
                found.append(Divergence(DIV_URL_DISALLOWED, page.requested_url))
                break
    return _unique_divs(found)


def crawl_site(
    seed: str = DEFAULT_SEED,
    *,
    fetcher: Fetcher | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> CrawlReport:
    """Crawl publico. Sem fetcher, usa GET via urllib e nao le segredo."""
    if timeout <= 0:
        raise CrawlError("timeout deve ser positivo")
    if max_attempts < 1:
        raise CrawlError("max_attempts deve ser pelo menos 1")
    if max_pages < 1:
        raise CrawlError("max_pages deve ser pelo menos 1")
    normalized_seed = normalize_url(seed)
    if normalized_seed is None:
        raise CrawlError("seed precisa ser uma URL http(s)")
    client = fetcher if fetcher is not None else UrllibFetcher(timeout=timeout)
    cache: dict[str, AttemptedFetch] = {}

    def fetch(url: str) -> AttemptedFetch:
        return fetch_with_retries(
            url,
            client,
            timeout=timeout,
            max_attempts=max_attempts,
            cache=cache,
        )

    seed_attempt = fetch(normalized_seed)
    # O host da navegacao HTML e o destino final do seed, depois dos redirects.
    # Um redirect do seed para outro dominio nao muda o host autorizado.
    seed_final = normalize_url(seed_attempt.result.final_url) or normalized_seed
    reference = seed_final if _same_owner(seed_final, normalized_seed) else normalized_seed

    robots, robot_sitemaps = _load_robots(reference, fetch)
    sitemap_seeds = robot_sitemaps if robot_sitemaps else (_replace_path(reference, "/sitemap.xml"),)
    same_site_sitemaps = tuple(
        url for url in sitemap_seeds if same_site(url, reference)
    )
    external_sitemap_divs = [
        Divergence(DIV_SITEMAP_EXTERNAL_LOC, url)
        for url in sitemap_seeds
        if not same_site(url, reference)
    ]
    if not same_site_sitemaps and not robot_sitemaps:
        same_site_sitemaps = (_replace_path(reference, "/sitemap.xml"),)
    documents, sitemap_urls, sitemap_divs = _load_sitemap_tree(
        same_site_sitemaps,
        reference,
        fetch,
    )
    sitemap_divs = _unique_divs([*sitemap_divs, *external_sitemap_divs])

    pages: list[PageRecord] = []
    visited: set[str] = set()
    queued: set[str] = set()
    pending: list[tuple[int, str]] = []

    def enqueue(url: str, priority: int) -> None:
        if url in visited or url in queued:
            return
        if not same_site(url, reference):
            return
        queued.add(url)
        heapq.heappush(pending, (priority, url))

    def record(requested: str, attempted: AttemptedFetch) -> None:
        final = normalize_url(attempted.result.final_url) or requested
        visited.add(requested)
        visited.add(final)
        # So HTML 2xx entregue pelo host autorizado e analisado e expandido.
        extractable = (
            attempted.classification == CLASS_OK
            and same_site(final, reference)
            and _is_html_document(attempted.result.content_type, attempted.result.body)
        )
        if extractable and attempted.result.body:
            extract = parse_html(_decode_html(attempted.result.body, attempted.result.content_type), final)
            page = _page_from_extract(requested, final, attempted, extract)
        else:
            extract = None
            page = _blank_page(requested, final, attempted)
        pages.append(page)
        if extract is None:
            return
        for link in extract.links:
            if same_site(link, reference) and is_crawl_document(link):
                enqueue(link, 1)

    record(normalized_seed, seed_attempt)
    for url in sitemap_urls:
        enqueue(url, 0)
    while pending and len(pages) < max_pages:
        _priority, url = heapq.heappop(pending)
        if url in visited:
            continue
        record(url, fetch(url))

    pages = _apply_shared(pages)
    reached = {page.requested_url for page in pages} | {page.final_url for page in pages}
    not_reached = tuple(url for url in sitemap_urls if url not in reached)
    not_reached_divs = tuple(
        Divergence(DIV_SITEMAP_URL_NOT_REACHED, url) for url in not_reached
    )
    disallow_divs = _disallowed_divergences(pages, robots, reference)
    sitemap = SitemapReport(
        documents=tuple(sorted(documents, key=lambda item: item.url)),
        references=sitemap_urls,
        not_reached=not_reached,
        divergences=_unique_divs([*sitemap_divs, *not_reached_divs]),
    )
    links = _check_links(pages, fetch)
    divergences = _unique_divs(
        [
            *robots.divergences,
            *sitemap.divergences,
            *disallow_divs,
        ]
    )
    return CrawlReport(
        seed=normalized_seed,
        crawl_host=host_name(reference),
        pages=tuple(sorted(pages, key=lambda page: page.requested_url)),
        robots=robots,
        sitemap=sitemap,
        links=links,
        duplicate_titles=_duplicate_groups(pages, "title"),
        duplicate_meta_descriptions=_duplicate_groups(pages, "meta_description"),
        duplicate_canonicals=_duplicate_groups(pages, "canonical"),
        divergences=divergences,
    )


def main(argv: list[str] | None = None) -> int:
    """Imprime o relatorio em JSON. Nao aceita credencial."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1:
        print("uso: python crawler.py [seed]", file=sys.stderr)
        return 2
    seed = args[0] if args else DEFAULT_SEED
    try:
        report = crawl_site(seed)
    except CrawlError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(to_plain(report), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
