"""Comparacao semanal de SEO. Nao envia e-mail e nao le o cofre.

A janela corrente e a ultima semana civil ja encerrada, de segunda a
domingo, no fuso America/Sao_Paulo. A semana que contem ``now`` nao entra,
inclusive quando ``now`` cai num domingo: esse dia ainda nao terminou.
A comparacao usa os sete dias imediatamente anteriores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SAO_PAULO_TZ_NAME = "America/Sao_Paulo"
INSUFFICIENT_SAMPLE = "amostra insuficiente"
MAX_ACTIONS = 3
_EPS = 1e-9


def sao_paulo_tz() -> timezone:
    try:
        return ZoneInfo(SAO_PAULO_TZ_NAME)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-3), name=SAO_PAULO_TZ_NAME)


class Change(str, Enum):
    MELHOROU = "melhorou"
    PIOROU = "piorou"
    ESTAVEL = "estavel"
    AMOSTRA_INSUFICIENTE = INSUFFICIENT_SAMPLE


@dataclass(frozen=True)
class DateWindow:
    """Intervalo inclusivo de segunda a domingo."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end - self.start != timedelta(days=6):
            raise ValueError("janela deve ter 7 dias")
        if self.start.weekday() != 0 or self.end.weekday() != 6:
            raise ValueError("janela deve ir de segunda a domingo")


@dataclass(frozen=True)
class WeekWindows:
    current: DateWindow
    previous: DateWindow


@dataclass(frozen=True)
class DimensionStat:
    """Uma pagina ou consulta. ``position`` e opcional e nao entra no ranking."""

    key: str
    clicks: float
    impressions: float
    position: float | None = None


@dataclass(frozen=True)
class PeriodStats:
    """Totais de um periodo e as linhas usadas para achar perdas.

    ``clicks`` e ``impressions`` vazios (None) significam amostra ausente.
    Zero e uma medicao real. CTR e posicao sao recalculados: posicao usa o
    valor agregado do periodo, nao a media das paginas.
    """

    clicks: float | None = None
    impressions: float | None = None
    position: float | None = None
    pages: tuple[DimensionStat, ...] = ()
    queries: tuple[DimensionStat, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages or ()))
        object.__setattr__(self, "queries", tuple(self.queries or ()))


@dataclass(frozen=True)
class MetricComparison:
    key: str
    current: float | None
    previous: float | None
    delta: float | None
    change: Change


@dataclass(frozen=True)
class RecommendedAction:
    kind: str
    key: str
    click_loss: float
    impression_loss: float
    message: str


@dataclass(frozen=True)
class WeeklySeoReport:
    current_window: DateWindow
    previous_window: DateWindow
    clicks: MetricComparison
    impressions: MetricComparison
    ctr: MetricComparison
    position: MetricComparison
    actions: tuple[RecommendedAction, ...]
    actions_message: str | None
    sample_message: str | None


class PeriodSource(Protocol):
    def fetch_period(self, start: date, end: date) -> PeriodStats:
        """Devolve as metricas inclusivas de ``start`` ate ``end``."""


def week_windows(now: datetime) -> WeekWindows:
    """Devolve a ultima semana completa e a semana anterior a ela."""

    if not isinstance(now, datetime):
        raise TypeError("now deve ser datetime")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now precisa incluir fuso horario")
    local_day = now.astimezone(sao_paulo_tz()).date()
    this_monday = local_day - timedelta(days=local_day.weekday())
    current_end = this_monday - timedelta(days=1)
    current_start = current_end - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    return WeekWindows(
        current=DateWindow(current_start, current_end),
        previous=DateWindow(previous_start, previous_end),
    )


def build_weekly_report(
    *,
    now: datetime,
    current: PeriodStats | None,
    previous: PeriodStats | None,
) -> WeeklySeoReport:
    """Monta o relatorio. Dados vazios e denominador zero nao levantam excecao."""

    windows = week_windows(now)
    if _is_blank(current) and _is_blank(previous):
        return _blank_report(windows)
    clicks = _count_metric("clicks", current, previous, higher_is_better=True)
    impressions = _count_metric(
        "impressions", current, previous, higher_is_better=True
    )
    ctr = _ctr_metric(current, previous)
    position = _position_metric(current, previous)
    actions, actions_message = _select_actions(current, previous)
    metrics = (clicks, impressions, ctr, position)
    needs_sample = actions_message is not None or any(
        item.change is Change.AMOSTRA_INSUFICIENTE for item in metrics
    )
    return WeeklySeoReport(
        current_window=windows.current,
        previous_window=windows.previous,
        clicks=clicks,
        impressions=impressions,
        ctr=ctr,
        position=position,
        actions=actions,
        actions_message=actions_message,
        sample_message=INSUFFICIENT_SAMPLE if needs_sample else None,
    )


def collect_weekly_report(source: PeriodSource, now: datetime) -> WeeklySeoReport:
    """Busca as duas janelas em ``source`` e compara."""

    windows = week_windows(now)
    current = source.fetch_period(windows.current.start, windows.current.end)
    previous = source.fetch_period(windows.previous.start, windows.previous.end)
    return build_weekly_report(now=now, current=current, previous=previous)


def render_report(report: WeeklySeoReport) -> str:
    """Texto estavel do relatorio, em portugues, sem destinatario."""

    lines = [
        (
            "Semana atual: "
            f"{report.current_window.start.isoformat()} a "
            f"{report.current_window.end.isoformat()} ({SAO_PAULO_TZ_NAME})"
        ),
        (
            "Semana anterior: "
            f"{report.previous_window.start.isoformat()} a "
            f"{report.previous_window.end.isoformat()}"
        ),
        "",
        _render_metric(report.clicks),
        _render_metric(report.impressions),
        _render_metric(report.ctr),
        _render_metric(report.position),
        "",
        "Ações recomendadas:",
    ]
    if report.actions_message:
        lines.append(report.actions_message)
    elif not report.actions:
        lines.append("Nenhuma queda de cliques em páginas ou consultas.")
    else:
        for index, action in enumerate(report.actions, start=1):
            lines.append(f"{index}. {action.message}")
    if report.sample_message and report.sample_message not in lines:
        lines.append(report.sample_message)
    return "\n".join(lines)


def _blank_report(windows: WeekWindows) -> WeeklySeoReport:
    return WeeklySeoReport(
        current_window=windows.current,
        previous_window=windows.previous,
        clicks=_insufficient("clicks"),
        impressions=_insufficient("impressions"),
        ctr=_insufficient("ctr"),
        position=_insufficient("position"),
        actions=(),
        actions_message=INSUFFICIENT_SAMPLE,
        sample_message=INSUFFICIENT_SAMPLE,
    )


def _is_blank(period: PeriodStats | None) -> bool:
    if period is None:
        return True
    clicks = 0.0 if period.clicks is None else period.clicks
    impressions = 0.0 if period.impressions is None else period.impressions
    return (
        clicks <= 0
        and impressions <= 0
        and period.position is None
        and not period.pages
        and not period.queries
    )


def _insufficient(key: str) -> MetricComparison:
    return MetricComparison(
        key=key,
        current=None,
        previous=None,
        delta=None,
        change=Change.AMOSTRA_INSUFICIENTE,
    )


def _clean(value: float) -> float:
    if abs(value) < _EPS:
        return 0.0
    return float(value)


def _direction(delta: float, *, higher_is_better: bool) -> Change:
    if delta == 0:
        return Change.ESTAVEL
    improved = delta > 0 if higher_is_better else delta < 0
    return Change.MELHOROU if improved else Change.PIOROU


def _measured(period: PeriodStats | None, name: str) -> float | None:
    if period is None:
        return None
    value = getattr(period, name)
    if value is None:
        return None
    return float(value)


def _count_metric(
    key: str,
    current: PeriodStats | None,
    previous: PeriodStats | None,
    *,
    higher_is_better: bool,
) -> MetricComparison:
    current_value = _measured(current, key)
    previous_value = _measured(previous, key)
    if current_value is None or previous_value is None:
        return _insufficient(key)
    delta = _clean(current_value - previous_value)
    return MetricComparison(
        key=key,
        current=current_value,
        previous=previous_value,
        delta=delta,
        change=_direction(delta, higher_is_better=higher_is_better),
    )


def _ctr_percent(period: PeriodStats | None) -> float | None:
    if period is None or period.clicks is None or period.impressions is None:
        return None
    # Impressoes sao o denominador. Zero nao e CTR zero: a razao nao existe.
    if period.impressions <= 0:
        return None
    return (float(period.clicks) / float(period.impressions)) * 100.0


def _ctr_metric(
    current: PeriodStats | None, previous: PeriodStats | None
) -> MetricComparison:
    current_ctr = _ctr_percent(current)
    previous_ctr = _ctr_percent(previous)
    if current_ctr is None or previous_ctr is None:
        return _insufficient("ctr")
    delta = _clean(current_ctr - previous_ctr)
    return MetricComparison(
        key="ctr",
        current=current_ctr,
        previous=previous_ctr,
        delta=delta,
        change=_direction(delta, higher_is_better=True),
    )


def _position_value(period: PeriodStats | None) -> float | None:
    if period is None or period.position is None:
        return None
    if period.impressions is None or period.impressions <= 0:
        return None
    if period.position <= 0:
        return None
    return float(period.position)


def _position_metric(
    current: PeriodStats | None, previous: PeriodStats | None
) -> MetricComparison:
    current_position = _position_value(current)
    previous_position = _position_value(previous)
    if current_position is None or previous_position is None:
        return _insufficient("position")
    delta = _clean(current_position - previous_position)
    # Posicao menor e melhor: cair de 8 para 4 e melhora, delta negativo.
    return MetricComparison(
        key="position",
        current=current_position,
        previous=previous_position,
        delta=delta,
        change=_direction(delta, higher_is_better=False),
    )


def _index_rows(rows: tuple[DimensionStat, ...]) -> dict[str, tuple[float, float]]:
    indexed: dict[str, list[float]] = {}
    for row in rows:
        key = str(row.key).strip()
        if not key:
            continue
        bucket = indexed.setdefault(key, [0.0, 0.0])
        bucket[0] += float(row.clicks)
        bucket[1] += float(row.impressions)
    return {key: (values[0], values[1]) for key, values in indexed.items()}


def _select_actions(
    current: PeriodStats | None, previous: PeriodStats | None
) -> tuple[tuple[RecommendedAction, ...], str | None]:
    current_pages = () if current is None else current.pages
    current_queries = () if current is None else current.queries
    previous_pages = () if previous is None else previous.pages
    previous_queries = () if previous is None else previous.queries
    available = (
        current_pages + current_queries + previous_pages + previous_queries
    )
    if not available or all(
        row.impressions <= 0 and row.clicks <= 0 for row in available
    ):
        return (), INSUFFICIENT_SAMPLE
    ranked = _rank_losses(
        current_pages, previous_pages, current_queries, previous_queries
    )
    if not ranked:
        return (), None
    return tuple(ranked[:MAX_ACTIONS]), None


def _rank_losses(
    current_pages: tuple[DimensionStat, ...],
    previous_pages: tuple[DimensionStat, ...],
    current_queries: tuple[DimensionStat, ...],
    previous_queries: tuple[DimensionStat, ...],
) -> list[RecommendedAction]:
    grouped = (
        ("page", current_pages, previous_pages),
        ("query", current_queries, previous_queries),
    )
    actions: list[RecommendedAction] = []
    for kind, current_rows, previous_rows in grouped:
        current_index = _index_rows(current_rows)
        previous_index = _index_rows(previous_rows)
        for key in set(current_index) | set(previous_index):
            current_clicks, current_impressions = current_index.get(key, (0.0, 0.0))
            previous_clicks, previous_impressions = previous_index.get(
                key, (0.0, 0.0)
            )
            click_loss = _clean(previous_clicks - current_clicks)
            impression_loss = _clean(previous_impressions - current_impressions)
            if click_loss <= 0:
                continue
            actions.append(
                RecommendedAction(
                    kind=kind,
                    key=key,
                    click_loss=click_loss,
                    impression_loss=impression_loss,
                    message=_action_message(
                        kind, key, click_loss, previous_clicks, current_clicks
                    ),
                )
            )
    actions.sort(
        key=lambda action: (
            -action.click_loss,
            -action.impression_loss,
            0 if action.kind == "page" else 1,
            action.key,
        )
    )
    return actions


def _action_message(
    kind: str,
    key: str,
    click_loss: float,
    previous_clicks: float,
    current_clicks: float,
) -> str:
    label = "página" if kind == "page" else "consulta"
    shown = f'"{key}"' if kind == "query" else key
    return (
        f"Revisar {label} {shown}: queda de {_format_count(click_loss)} cliques "
        f"({_format_count(previous_clicks)} para {_format_count(current_clicks)})."
    )


def _format_count(value: float) -> str:
    if abs(value - round(value)) < _EPS:
        return str(int(round(value)))
    return f"{value:.1f}"


_LABELS = {
    "clicks": "Cliques",
    "impressions": "Impressões",
    "ctr": "CTR",
    "position": "Posição média",
}


def _render_metric(metric: MetricComparison) -> str:
    label = _LABELS[metric.key]
    if metric.change is Change.AMOSTRA_INSUFICIENTE:
        return f"{label}: {INSUFFICIENT_SAMPLE}"
    return (
        f"{label}: atual {_format_value(metric.key, metric.current)}, "
        f"anterior {_format_value(metric.key, metric.previous)}, "
        f"delta {_format_delta(metric.key, metric.delta)}, "
        f"{metric.change.value}"
    )


def _format_value(key: str, value: float | None) -> str:
    if value is None:
        return INSUFFICIENT_SAMPLE
    if key == "ctr":
        return f"{value:.2f}%"
    if key == "position":
        return f"{value:.2f}"
    return _format_count(value)


def _format_delta(key: str, delta: float | None) -> str:
    if delta is None:
        return INSUFFICIENT_SAMPLE
    if key == "ctr":
        return f"{delta:+.2f} pp"
    if key == "position":
        return f"{delta:+.2f}"
    if abs(delta - round(delta)) < _EPS:
        return f"{int(round(delta)):+d}"
    return f"{delta:+.1f}"
