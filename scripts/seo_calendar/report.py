"""Exportação CSV auditável para anexar ao relatório do calendário SEO."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO

from seo_calendar.planner import EditorialCalendar

_COLUMNS = (
    "semana",
    "data_inicio_semana",
    "pauta",
    "consulta_alvo",
    "categoria",
    "cliques",
    "impressoes",
    "ctr",
    "posicao_media",
    "landing_page",
    "justificativa",
)


def write_csv(calendar: EditorialCalendar, destination: str | Path | TextIO) -> None:
    """Escreve CSV UTF-8 com BOM, separador compatível com planilhas e metadados."""

    close_after = not hasattr(destination, "write")
    stream = (
        Path(destination).open("w", encoding="utf-8-sig", newline="")
        if close_after
        else destination
    )
    try:
        writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
        writer.writerow(("metadado", "propriedade", calendar.property_url))
        writer.writerow(
            (
                "metadado",
                "janela_consultada",
                f"{calendar.window_start.isoformat()} a {calendar.window_end.isoformat()}",
            )
        )
        writer.writerow(("metadado", "data_geracao", calendar.generated_on.isoformat()))
        writer.writerow(("metadado", "sha256_conjunto_entrada", calendar.input_digest))
        writer.writerow(_COLUMNS)
        for entry in calendar.entries:
            writer.writerow(
                (
                    entry.week,
                    entry.week_start.isoformat(),
                    entry.topic,
                    entry.target_query,
                    entry.category,
                    entry.clicks,
                    entry.impressions,
                    f"{entry.ctr:.6f}",
                    f"{entry.position:.2f}",
                    entry.landing_page,
                    entry.justification,
                )
            )
    finally:
        if close_after:
            stream.close()
