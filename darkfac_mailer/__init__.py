"""Relatorio semanal de SEO para o administrador do site.

Coleta e comparacao via Search Console. O entrypoint de envio fica em
darkfac_mailer.main e o unico destino final e o e-mail.
"""

from darkfac_mailer.gsc import SearchConsoleAdapter, SearchConsoleError
from darkfac_mailer.report import (
    INSUFFICIENT_SAMPLE,
    MAX_ACTIONS,
    Change,
    DateWindow,
    DimensionStat,
    MetricComparison,
    PeriodStats,
    RecommendedAction,
    WeekWindows,
    WeeklySeoReport,
    build_weekly_report,
    collect_weekly_report,
    render_report,
    week_windows,
)

__all__ = [
    "INSUFFICIENT_SAMPLE",
    "MAX_ACTIONS",
    "Change",
    "DateWindow",
    "DimensionStat",
    "MetricComparison",
    "PeriodStats",
    "RecommendedAction",
    "SearchConsoleAdapter",
    "SearchConsoleError",
    "WeekWindows",
    "WeeklySeoReport",
    "build_weekly_report",
    "collect_weekly_report",
    "render_report",
    "week_windows",
]
