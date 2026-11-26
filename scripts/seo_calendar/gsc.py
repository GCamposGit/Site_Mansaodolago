"""Coleta e classifica consultas reais do Google Search Console.

Contrato (MDL-03 T1). Nada aqui publica página nem inventa pauta.

Janela
    28 dias civis completos, encerrados três dias antes do dia de referência.
    O dia civil é America/Sao_Paulo (UTC−3, sem horário de verão desde 2019).
    A consulta pede ``dataState=final`` e ``type=web``.

Credencial
    Só entra por referência de arquivo. O cofre injeta o caminho em
    ``MDL_GSC_CREDENTIAL_FILE`` ou o chamador passa ``credential_file``.
    O segredo não vai para o pedido, para o resultado nem para a mensagem
    de erro.

Posição
    Por consulta, a posição é a média ponderada pelas impressões:
    soma(posição × impressões) / soma(impressões).
    A categoria ``oportunidade`` inclui a posição 5 e a posição 20.
    Valores fora desse intervalo ficam em ``fora_da_faixa``.

Página dedicada
    Uma URL é versionada quando está no sitemap, em
    ``https://www.mansaodolago.com``, sem query string e sem fragmento.
    A cobertura mínima da intenção é a fração 3/5 (0,6), calculada à parte
    em cada fonte: caminho da URL, ``<title>`` ou primeiro ``<h1>``.
    Uma fonte basta. Tokens de intenção: sem acento, minúsculos, distintos,
    comprimento >= 3, fora da lista de stopwords.
    Consulta com impressões reais é marcada sem página dedicada somente
    quando nenhuma URL versionada alcança essa fração. Sem tokens de
    intenção, a consulta não recebe essa marca.

Falha fechada
    Entrada vazia, resposta incompleta, período inválido, credencial
    ausente, sitemap sem URL versionada ou volume abaixo do mínimo
    configurado interrompem com erro. O coletor não devolve pauta
    substituta.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Mapping, Protocol, Sequence
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

WINDOW_DAYS = 28
DATA_LAG_DAYS = 3
OPPORTUNITY_POSITION_MIN = 5
OPPORTUNITY_POSITION_MAX = 20
CATEGORY_OPPORTUNITY = "oportunidade"
CATEGORY_OUTSIDE = "fora_da_faixa"

# Cobertura mínima documentada: 3/5 dos tokens de intenção numa única fonte.
COVERAGE_NUMERATOR = 3
COVERAGE_DENOMINATOR = 5
MIN_INTENT_COVERAGE = COVERAGE_NUMERATOR / COVERAGE_DENOMINATOR
MIN_TOKEN_LENGTH = 3

CREDENTIAL_ENV = "MDL_GSC_CREDENTIAL_FILE"
DEFAULT_SITE_URL = "https://www.mansaodolago.com/"
CANONICAL_ORIGIN = "https://www.mansaodolago.com"
CANONICAL_HOST = "www.mansaodolago.com"
SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
MAX_ROW_LIMIT = 25000
MAX_PAGES = 10000
SAO_PAULO = timezone(timedelta(hours=-3))
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

STOPWORDS = frozenset(
    {
        "a",
        "o",
        "os",
        "as",
        "um",
        "uma",
        "uns",
        "umas",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "para",
        "pra",
        "com",
        "sem",
        "e",
        "ou",
        "que",
        "se",
        "ao",
        "aos",
        "num",
        "numa",
        "nao",
        "lhe",
        "eles",
        "elas",
        "ele",
        "ela",
        "seu",
        "sua",
        "seus",
        "suas",
        "the",
        "of",
        "in",
        "on",
        "for",
        "and",
        "or",
        "to",
        "an",
        "el",
        "la",
        "los",
        "las",
        "del",
        "con",
        "un",
        "una",
        "y",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


class SeoCalendarError(Exception):
    """Falha do coletor. A mensagem não contém segredo nem pauta."""


class MissingCredentialError(SeoCalendarError):
    """O cofre não entregou um arquivo de credencial utilizável."""


class InvalidPeriodError(SeoCalendarError):
    """A janela não é a dos 28 dias completos encerrados há três dias."""


class IncompleteResponseError(SeoCalendarError):
    """A resposta do Search Console veio cortada ou malformada."""


class EmptyInputError(SeoCalendarError):
    """Não há linhas query/página com impressões."""


class InsufficientDataError(SeoCalendarError):
    """O volume real ficou abaixo do mínimo configurado."""


class MissingSitemapError(SeoCalendarError):
    """Não há URL versionada para avaliar página dedicada."""


def _closed(exc_type: type[SeoCalendarError], message: str) -> SeoCalendarError:
    text = message.rstrip()
    suffix = "Nenhuma pauta foi gerada."
    if not text.endswith(suffix):
        text = f"{text} {suffix}"
    return exc_type(text)


class SearchAnalyticsClient(Protocol):
    """Cliente mínimo da Search Analytics API. Recebe o corpo, não o segredo."""

    def query(self, site_url: str, body: Mapping[str, object]) -> Mapping[str, object]:
        """Executa searchAnalytics.query e devolve o JSON já decodificado."""


@dataclass(frozen=True)
class ReportingWindow:
    start_date: date
    end_date: date

    @property
    def day_count(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True)
class SitemapPage:
    """Página versionada: URL canônica do sitemap mais title e H1 locais."""

    loc: str
    url_text: str
    title: str
    h1: str


@dataclass(frozen=True)
class ParsedRow:
    query: str
    page: str
    impressions: int
    clicks: int
    position: float


@dataclass(frozen=True)
class QueryClassification:
    query: str
    impressions: int
    clicks: int
    position: float
    category: str
    without_dedicated_page: bool
    covering_urls: tuple[str, ...]
    pages: tuple[str, ...]

    @property
    def is_opportunity(self) -> bool:
        return self.category == CATEGORY_OPPORTUNITY


@dataclass(frozen=True)
class CollectionResult:
    start_date: date
    end_date: date
    row_count: int
    queries: tuple[QueryClassification, ...]

    @property
    def opportunities(self) -> tuple[QueryClassification, ...]:
        return tuple(item for item in self.queries if item.is_opportunity)


def civil_today(now: datetime | None = None) -> date:
    """Dia civil em São Paulo. Instantes sem fuso são período inválido."""

    if now is None:
        moment = datetime.now(SAO_PAULO)
    elif not isinstance(now, datetime) or now.tzinfo is None:
        raise _closed(
            InvalidPeriodError,
            "Período inválido: o instante de referência precisa ter fuso.",
        )
    else:
        moment = now.astimezone(SAO_PAULO)
    return moment.date()


def reporting_window(today: date) -> ReportingWindow:
    """28 dias inclusivos cujo último dia é ``today`` menos três dias."""

    civil = _civil_day(today, "a data de referência")
    end = civil - timedelta(days=DATA_LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    window = ReportingWindow(start, end)
    if window.day_count != WINDOW_DAYS or window.end_date != civil - timedelta(days=DATA_LAG_DAYS):
        raise _closed(
            InvalidPeriodError,
            "Período inválido: a janela calculada não tem 28 dias encerrados há três dias.",
        )
    return window


def resolve_credential_file(credential_file: str | Path | None = None) -> Path:
    """Resolve a referência de arquivo. Não devolve o conteúdo do segredo."""

    if credential_file is not None:
        return _existing_credential(credential_file)
    injected = os.environ.get(CREDENTIAL_ENV, "").strip()
    if not injected:
        raise _closed(
            MissingCredentialError,
            "Credencial ausente: o cofre precisa injetar o caminho do arquivo "
            f"em {CREDENTIAL_ENV}.",
        )
    return _existing_credential(injected)


def load_versioned_pages(sitemap_path: Path, site_root: Path) -> tuple[SitemapPage, ...]:
    """Lê o sitemap e o HTML local das URLs versionadas, em ordem estável."""

    path = _as_path(sitemap_path)
    root = _as_path(site_root)
    try:
        exists = path.is_file()
    except OSError:
        exists = False
    if not exists:
        raise _closed(
            MissingSitemapError,
            "Sitemap ausente: não é possível classificar página dedicada.",
        )
    try:
        document = ElementTree.parse(path)
    except (ElementTree.ParseError, OSError):
        raise _closed(
            MissingSitemapError,
            "Sitemap ilegível: não é possível classificar página dedicada.",
        ) from None

    locs = _sitemap_locs(document.getroot())
    pages: list[SitemapPage] = []
    seen: set[str] = set()
    for loc in locs:
        if loc in seen or not _is_versioned_loc(loc):
            continue
        seen.add(loc)
        url_text = _url_path_text(loc)
        title, h1 = _read_title_h1(loc, root)
        pages.append(SitemapPage(loc=loc, url_text=url_text, title=title, h1=h1))
    pages.sort(key=lambda item: item.loc)
    if not pages:
        raise _closed(
            MissingSitemapError,
            "Sitemap sem URL versionada: não é possível classificar página dedicada.",
        )
    return tuple(pages)


def classify_search_console_rows(
    rows: Sequence[Mapping[str, object]],
    pages: Sequence[SitemapPage],
) -> tuple[QueryClassification, ...]:
    """Classifica linhas já obtidas. Entrada vazia devolve tupla vazia."""

    parsed = _parse_rows(rows)
    return _classify_parsed(parsed, pages)


def collect(
    *,
    sitemap_path: str | Path,
    site_root: str | Path,
    credential_file: str | Path | None = None,
    site_url: str = DEFAULT_SITE_URL,
    today: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    client: SearchAnalyticsClient | None = None,
    min_rows: int = 1,
    min_queries: int = 1,
    row_limit: int = MAX_ROW_LIMIT,
) -> CollectionResult:
    """Coleta todas as linhas query/página da janela e classifica as consultas."""

    credential_path = resolve_credential_file(credential_file)
    minimum_rows = _configured_minimum(min_rows, "min_rows")
    minimum_queries = _configured_minimum(min_queries, "min_queries")
    page_size = _row_limit(row_limit)
    if not isinstance(site_url, str) or not site_url.strip():
        raise _closed(
            SeoCalendarError,
            "Propriedade do Search Console ausente.",
        )
    reference = civil_today() if today is None else today
    window = _validated_window(reference, start_date, end_date)
    pages = load_versioned_pages(sitemap_path, site_root)
    analytics = client if client is not None else build_search_console_client(credential_path)
    parsed = _fetch_all_rows(analytics, site_url.strip(), window, page_size)
    usable = [row for row in parsed if row.impressions > 0]
    if not usable:
        raise _closed(
            EmptyInputError,
            "Entrada vazia: o Search Console não devolveu linhas query/página com impressões.",
        )
    if len(usable) < minimum_rows:
        raise _closed(
            InsufficientDataError,
            "Dados insuficientes: "
            f"{len(usable)} linhas com impressões; o mínimo configurado é {minimum_rows}.",
        )
    classified = _classify_parsed(usable, pages)
    if len(classified) < minimum_queries:
        raise _closed(
            InsufficientDataError,
            "Dados insuficientes: "
            f"{len(classified)} consultas com impressões; o mínimo configurado é {minimum_queries}.",
        )
    return CollectionResult(
        start_date=window.start_date,
        end_date=window.end_date,
        row_count=len(usable),
        queries=classified,
    )


def build_search_console_client(credential_file: Path) -> SearchAnalyticsClient:
    """Abre o cliente oficial a partir do arquivo. Import tardio, só leitura."""

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise _closed(
            SeoCalendarError,
            "Dependência ausente: instale scripts/seo_calendar/requirements.txt.",
        ) from None

    credentials = service_account.Credentials.from_service_account_file(
        str(credential_file),
        scopes=[SEARCH_CONSOLE_SCOPE],
    )
    service = build(
        "searchconsole",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    class GoogleSearchConsoleClient:
        def query(self, site_url: str, body: Mapping[str, object]) -> Mapping[str, object]:
            try:
                response = (
                    service.searchanalytics()
                    .query(siteUrl=site_url, body=dict(body))
                    .execute()
                )
            except Exception:
                raise _closed(
                    IncompleteResponseError,
                    "Resposta incompleta: a consulta ao Search Console falhou.",
                ) from None
            if not isinstance(response, dict):
                raise _closed(
                    IncompleteResponseError,
                    "Resposta incompleta: o Search Console não devolveu um objeto.",
                )
            return response

    return GoogleSearchConsoleClient()


def _validated_window(
    today: date,
    start_date: date | None,
    end_date: date | None,
) -> ReportingWindow:
    expected = reporting_window(today)
    if start_date is None and end_date is None:
        return expected
    if start_date is None or end_date is None:
        raise _closed(
            InvalidPeriodError,
            "Período inválido: informe início e fim juntos, ou nenhum dos dois.",
        )
    start = _civil_day(start_date, "a data inicial")
    end = _civil_day(end_date, "a data final")
    if start > end:
        raise _closed(
            InvalidPeriodError,
            "Período inválido: a data inicial é posterior à final.",
        )
    if start != expected.start_date or end != expected.end_date:
        raise _closed(
            InvalidPeriodError,
            "Período inválido: use 28 dias completos encerrados há três dias "
            f"({expected.start_date.isoformat()} a {expected.end_date.isoformat()}).",
        )
    return expected


def _civil_day(value: date, label: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise _closed(InvalidPeriodError, f"Período inválido: {label} precisa ser um dia civil.")
    return value


def _existing_credential(raw: str | Path) -> Path:
    try:
        path = Path(raw)
        exists = path.is_file()
    except (TypeError, ValueError, OSError):
        raise _closed(
            MissingCredentialError,
            "Credencial ausente: a referência de arquivo indicada pelo cofre é inválida.",
        ) from None
    if not exists:
        raise _closed(
            MissingCredentialError,
            "Credencial ausente: o cofre não apontou para um arquivo de credencial.",
        )
    _validate_credential_file(path)
    return path


def _validate_credential_file(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise _closed(
            MissingCredentialError,
            "Credencial ausente: o arquivo de credencial é ilegível.",
        ) from None
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise _closed(
            MissingCredentialError,
            "Credencial ausente: o arquivo não é uma conta de serviço.",
        )
    email = data.get("client_email")
    key = data.get("private_key")
    if not isinstance(email, str) or "@" not in email:
        raise _closed(
            MissingCredentialError,
            "Credencial ausente: a conta de serviço não traz client_email.",
        )
    if not isinstance(key, str) or "PRIVATE KEY" not in key:
        raise _closed(
            MissingCredentialError,
            "Credencial ausente: a conta de serviço não traz private_key.",
        )


def _configured_minimum(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _closed(SeoCalendarError, f"Mínimo configurado inválido ({label}).")
    return value


def _row_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_ROW_LIMIT:
        raise _closed(
            SeoCalendarError,
            f"Limite de página inválido: use um inteiro entre 1 e {MAX_ROW_LIMIT}.",
        )
    return value


def _as_path(value: str | Path) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError):
        raise _closed(MissingSitemapError, "Sitemap ausente: caminho inválido.") from None


def _sitemap_locs(root: ElementTree.Element) -> list[str]:
    found = [node.text for node in root.findall("sm:url/sm:loc", SITEMAP_NS)]
    if not found:
        found = [node.text for node in root.findall("url/loc")]
    return [text.strip() for text in found if isinstance(text, str) and text.strip()]


def _is_versioned_loc(loc: str) -> bool:
    parts = urlsplit(loc.strip())
    path = unquote(parts.path)
    return (
        parts.scheme == "https"
        and parts.netloc == CANONICAL_HOST
        and not parts.query
        and not parts.fragment
        and bool(path)
        and ".." not in path.split("/")
    )


def _url_path_text(loc: str) -> str:
    path = unquote(urlsplit(loc).path)
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    elif path.endswith(".html"):
        path = path[: -len(".html")]
    return path.replace("/", " ").replace("-", " ").replace("_", " ")


def _read_title_h1(loc: str, site_root: Path) -> tuple[str, str]:
    relative = _loc_to_relative(loc)
    if relative is None:
        return "", ""
    try:
        candidate = (site_root / relative).resolve()
        root = site_root.resolve()
        candidate.relative_to(root)
        html = candidate.read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeError):
        return "", ""
    return _extract_title(html), _extract_h1(html)


def _loc_to_relative(loc: str) -> Path | None:
    path = unquote(urlsplit(loc).path)
    if path.endswith("/"):
        relative = Path(path.lstrip("/")) / "index.html"
    else:
        relative = Path(path.lstrip("/"))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return relative


def _extract_title(html: str) -> str:
    match = _TITLE_RE.search(html)
    if match is None:
        return ""
    return _visible_text(match.group(1))


def _extract_h1(html: str) -> str:
    match = _H1_RE.search(html)
    if match is None:
        return ""
    return _visible_text(match.group(1))


def _visible_text(fragment: str) -> str:
    without_comments = _COMMENT_RE.sub(" ", fragment)
    without_tags = _TAG_RE.sub(" ", without_comments)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def intent_tokens(text: str) -> tuple[str, ...]:
    """Tokens de intenção, estáveis e sem stopword."""

    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    found: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(folded.lower()):
        if len(token) < MIN_TOKEN_LENGTH or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        found.append(token)
    return tuple(found)


def _covers(query_tokens: Sequence[str], field_text: str) -> bool:
    if not query_tokens:
        return False
    field_tokens = set(intent_tokens(field_text))
    hits = sum(1 for token in query_tokens if token in field_tokens)
    return hits * COVERAGE_DENOMINATOR >= len(query_tokens) * COVERAGE_NUMERATOR


def _covering_urls(query: str, pages: Sequence[SitemapPage]) -> tuple[str, ...]:
    tokens = intent_tokens(query)
    if not tokens:
        return ()
    matched = [
        page.loc
        for page in pages
        if _covers(tokens, page.url_text)
        or _covers(tokens, page.title)
        or _covers(tokens, page.h1)
    ]
    return tuple(sorted(set(matched)))


def _fetch_all_rows(
    client: SearchAnalyticsClient,
    site_url: str,
    window: ReportingWindow,
    row_limit: int,
) -> tuple[ParsedRow, ...]:
    collected: list[ParsedRow] = []
    seen: set[tuple[str, str]] = set()
    start_row = 0
    for _ in range(MAX_PAGES):
        body = {
            "startDate": window.start_date.isoformat(),
            "endDate": window.end_date.isoformat(),
            "dimensions": ["query", "page"],
            "rowLimit": row_limit,
            "startRow": start_row,
            "dataState": "final",
            "type": "web",
        }
        try:
            payload = client.query(site_url, body)
        except SeoCalendarError:
            raise
        except Exception:
            raise _closed(
                IncompleteResponseError,
                "Resposta incompleta: a consulta ao Search Console falhou.",
            ) from None
        page_rows = _page_rows(payload)
        for raw in page_rows:
            parsed = _parse_row(raw)
            identity = (parsed.query, parsed.page)
            if identity in seen:
                raise _closed(
                    IncompleteResponseError,
                    "Resposta incompleta: linha query/página repetida.",
                )
            seen.add(identity)
            collected.append(parsed)
        if len(page_rows) < row_limit:
            return tuple(collected)
        start_row += len(page_rows)
    raise _closed(
        IncompleteResponseError,
        "Resposta incompleta: a paginação não consumiu todas as linhas query/página.",
    )


def _page_rows(payload: object) -> list:
    if not isinstance(payload, Mapping):
        raise _closed(
            IncompleteResponseError,
            "Resposta incompleta: a página não é um objeto.",
        )
    if "rows" not in payload:
        return []
    rows = payload["rows"]
    if not isinstance(rows, list):
        raise _closed(
            IncompleteResponseError,
            "Resposta incompleta: a lista de linhas query/página não veio.",
        )
    return rows


def _parse_rows(rows: Sequence[object]) -> tuple[ParsedRow, ...]:
    parsed: list[ParsedRow] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        item = _parse_row(raw)
        identity = (item.query, item.page)
        if identity in seen:
            raise _closed(
                IncompleteResponseError,
                "Resposta incompleta: linha query/página repetida.",
            )
        seen.add(identity)
        parsed.append(item)
    return tuple(parsed)


def _parse_row(raw: object) -> ParsedRow:
    if not isinstance(raw, Mapping):
        raise _closed(IncompleteResponseError, "Resposta incompleta: linha sem campos.")
    keys = raw.get("keys")
    if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes)) or len(keys) != 2:
        raise _closed(
            IncompleteResponseError,
            "Resposta incompleta: linha sem as dimensões query e page.",
        )
    query, page = keys[0], keys[1]
    if not isinstance(query, str) or not query.strip():
        raise _closed(IncompleteResponseError, "Resposta incompleta: consulta vazia.")
    if not isinstance(page, str) or not page.strip():
        raise _closed(IncompleteResponseError, "Resposta incompleta: página vazia.")
    return ParsedRow(
        query=query,
        page=page,
        impressions=_count(raw.get("impressions"), "impressões"),
        clicks=_count(raw.get("clicks"), "cliques"),
        position=_position(raw.get("position")),
    )


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _closed(IncompleteResponseError, f"Resposta incompleta: {label} ausentes.")
    if isinstance(value, float) and not value.is_integer():
        raise _closed(IncompleteResponseError, f"Resposta incompleta: {label} inválidas.")
    if value < 0:
        raise _closed(IncompleteResponseError, f"Resposta incompleta: {label} negativas.")
    return int(value)


def _position(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _closed(IncompleteResponseError, "Resposta incompleta: posição ausente.")
    if isinstance(value, float) and not math.isfinite(value):
        raise _closed(IncompleteResponseError, "Resposta incompleta: posição inválida.")
    if value <= 0:
        raise _closed(IncompleteResponseError, "Resposta incompleta: posição inválida.")
    return float(value)


def _classify_parsed(
    rows: Sequence[ParsedRow],
    pages: Sequence[SitemapPage],
) -> tuple[QueryClassification, ...]:
    grouped: dict[str, list[ParsedRow]] = defaultdict(list)
    for row in rows:
        if row.impressions > 0:
            grouped[row.query].append(row)
    classified: list[QueryClassification] = []
    for query in sorted(grouped):
        items = grouped[query]
        impressions = sum(item.impressions for item in items)
        clicks = sum(item.clicks for item in items)
        weighted = sum(item.position * item.impressions for item in items) / impressions
        tokens = intent_tokens(query)
        covering = _covering_urls(query, pages) if tokens else ()
        # Sem token de intenção não há como documentar a lacuna: não marca.
        without_page = bool(tokens) and not covering
        category = CATEGORY_OPPORTUNITY if _in_band(weighted) else CATEGORY_OUTSIDE
        classified.append(
            QueryClassification(
                query=query,
                impressions=impressions,
                clicks=clicks,
                position=weighted,
                category=category,
                without_dedicated_page=without_page,
                covering_urls=covering,
                pages=tuple(sorted({item.page for item in items})),
            )
        )
    return tuple(classified)


def _in_band(position: float) -> bool:
    return OPPORTUNITY_POSITION_MIN <= position <= OPPORTUNITY_POSITION_MAX
