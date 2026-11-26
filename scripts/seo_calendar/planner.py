"""Planejamento determinístico do calendário editorial a partir do GSC."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from seo_calendar import gsc


class CalendarPlanningError(gsc.SeoCalendarError):
    """Não há dados elegíveis suficientes para produzir quatro pautas."""


@dataclass(frozen=True)
class CalendarEntry:
    week: int
    week_start: date
    topic: str
    target_query: str
    category: str
    clicks: int
    impressions: int
    ctr: float
    position: float
    landing_page: str
    justification: str


@dataclass(frozen=True)
class EditorialCalendar:
    property_url: str
    window_start: date
    window_end: date
    generated_on: date
    input_digest: str
    entries: tuple[CalendarEntry, ...]


def _fail(message: str) -> CalendarPlanningError:
    return CalendarPlanningError(f"{message} Nenhuma pauta foi gerada.")


def _normalized_intent(query: str) -> tuple[str, ...]:
    return gsc.intent_tokens(query)


def _input_digest(collection: gsc.CollectionResult, property_url: str) -> str:
    payload = {
        "property": property_url,
        "window": [collection.start_date.isoformat(), collection.end_date.isoformat()],
        "row_count": collection.row_count,
        "queries": [
            {
                "query": item.query,
                "clicks": item.clicks,
                "impressions": item.impressions,
                "position": item.position,
                "category": item.category,
                "without_dedicated_page": item.without_dedicated_page,
                "pages": list(item.pages),
                "covering_urls": list(item.covering_urls),
            }
            for item in sorted(collection.queries, key=lambda row: row.query)
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _take_distinct(
    source: Iterable[gsc.QueryClassification],
    selected: list[tuple[gsc.QueryClassification, str]],
    seen_intents: set[tuple[str, ...]],
    category: str,
) -> None:
    for item in sorted(source, key=lambda row: (-row.impressions, -row.clicks, row.query.casefold())):
        intent = _normalized_intent(item.query)
        if not intent or intent in seen_intents:
            continue
        seen_intents.add(intent)
        selected.append((item, category))
        return


def _topic(query: str) -> str:
    return f"Guia prático: {query.strip().rstrip('?.!')}"


def build_calendar(
    collection: gsc.CollectionResult,
    *,
    property_url: str,
    generated_on: date | None = None,
) -> EditorialCalendar:
    """Cria quatro pautas distintas, começando na próxima segunda-feira."""

    if not isinstance(property_url, str) or not property_url.strip():
        raise _fail("A propriedade do Search Console é obrigatória.")
    if not isinstance(collection, gsc.CollectionResult):
        raise _fail("O resultado da coleta do Search Console é inválido.")
    created = generated_on or gsc.civil_today()
    if not isinstance(created, date) or isinstance(created, datetime):
        raise _fail("A data de geração é inválida.")

    candidates = [item for item in collection.queries if item.impressions > 0]
    opportunity = [item for item in candidates if item.is_opportunity]
    missing_page = [item for item in candidates if item.without_dedicated_page]
    selected: list[tuple[gsc.QueryClassification, str]] = []
    seen_intents: set[tuple[str, ...]] = set()

    # Reserve separate intents for each class when both opportunity types exist.
    if opportunity and missing_page:
        _take_distinct(opportunity, selected, seen_intents, gsc.CATEGORY_OPPORTUNITY)
        _take_distinct(
            missing_page,
            selected,
            seen_intents,
            "sem_pagina_dedicada",
        )
        if len(selected) < 2:
            raise _fail("Não há intenções distintas entre oportunidades e consultas sem página dedicada.")
    elif opportunity:
        _take_distinct(opportunity, selected, seen_intents, gsc.CATEGORY_OPPORTUNITY)
    elif missing_page:
        _take_distinct(missing_page, selected, seen_intents, "sem_pagina_dedicada")

    # Fill remaining slots while alternating source preference and never repeating intent.
    pools = (opportunity, missing_page)
    pool_index = 0
    while len(selected) < 4:
        before = len(selected)
        for offset in range(len(pools)):
            index = (pool_index + offset) % len(pools)
            category = (
                gsc.CATEGORY_OPPORTUNITY
                if pools[index] is opportunity
                else "sem_pagina_dedicada"
            )
            _take_distinct(pools[index], selected, seen_intents, category)
            if len(selected) == 4:
                break
        pool_index = (pool_index + 1) % len(pools)
        if len(selected) == before:
            raise _fail("São necessárias quatro consultas com intenções distintas e elegíveis.")

    days_until_monday = (7 - created.weekday()) % 7 or 7
    first_monday = created + timedelta(days=days_until_monday)
    entries: list[CalendarEntry] = []
    for week, (item, category) in enumerate(selected, start=1):
        ctr = item.clicks / item.impressions if item.impressions else 0.0
        page = item.pages[0] if item.pages else ""
        justification = (
            f"Na janela {collection.start_date.isoformat()} a {collection.end_date.isoformat()}, "
            f'a consulta teve {item.clicks} cliques, {item.impressions} impressões, '
            f"CTR de {ctr:.2%} e posição média {item.position:.2f}; categoria: {category}."
        )
        entries.append(
            CalendarEntry(
                week=week,
                week_start=first_monday + timedelta(weeks=week - 1),
                topic=_topic(item.query),
                target_query=item.query,
                category=category,
                clicks=item.clicks,
                impressions=item.impressions,
                ctr=ctr,
                position=item.position,
                landing_page=page,
                justification=justification,
            )
        )

    return EditorialCalendar(
        property_url=property_url.strip(),
        window_start=collection.start_date,
        window_end=collection.end_date,
        generated_on=created,
        input_digest=_input_digest(collection, property_url.strip()),
        entries=tuple(entries),
    )
