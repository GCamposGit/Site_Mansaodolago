"""Build reproducible JSON evidence and an actionable Markdown audit."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .sanitize import to_plain

_UNCHECKED_BUCKETS = (("timeouts", "Timeout"), ("rate_limited", "Rate limited (429)"),
                      ("inconclusive", "Inconclusivo"))


class IncompleteCrawlError(ValueError):
    """Uma secao obrigatoria do crawl nao foi coletada."""


_ACCEPTED_ABSENCE_STATUSES = frozenset({404, 410})


def _collection_failed(item: dict[str, Any]) -> bool:
    """Falha em transporte, 3xx, 400/401/403/429 ou 5xx. Aceita 2xx e ausencia 404/410."""
    status = item.get("status")
    if not isinstance(status, int):
        return True
    return not (200 <= status <= 299 or status in _ACCEPTED_ABSENCE_STATUSES)


def require_complete_crawl(crawl: Any) -> None:
    """Impede publicar quando seed, robots.txt ou sitemap nao foram coletados."""
    data = to_plain(crawl)
    if not isinstance(data, dict):
        raise IncompleteCrawlError("crawl nao serializavel")
    seed = str(data.get("seed", "")).rstrip("/")
    failed: list[str] = []
    if not any(
        str(page.get("requested_url", "")).rstrip("/") == seed
        and isinstance(page.get("status"), int) and 200 <= page["status"] <= 299
        and page.get("metadata_collected", True)
        for page in data.get("pages", [])
    ):
        failed.append("pagina inicial")
    robots = data.get("robots", {})
    if not robots.get("parsed") and _collection_failed(robots):
        failed.append("robots.txt")
    documents = data.get("sitemap", {}).get("documents", [])
    if not documents or any((not doc.get("parsed") and _collection_failed(doc)) for doc in documents):
        failed.append("sitemap.xml")
    if failed:
        raise IncompleteCrawlError("crawl incompleto; falha de coleta em: " + ", ".join(failed))


def build_evidence(crawl: Any, search: Any, *, base_url: str, start_date: str,
                   end_date: str, parameters: dict[str, Any], commit: str,
                   source: dict[str, Any] | None = None,
                   generated_at: datetime | None = None) -> dict[str, Any]:
    """Return the normalized source data plus reproducibility metadata."""
    require_complete_crawl(crawl)
    crawl_data, search_data = to_plain(crawl), to_plain(search)
    if not isinstance(crawl_data, dict) or not isinstance(search_data, dict):
        raise ValueError("fontes de auditoria nao serializaveis")
    if not search_data.get("property") or search_data.get("dataState") != "final":
        raise ValueError("Search Console sem propriedade ou dados finais")
    stamp = generated_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError("timestamp precisa de fuso horario")
    return {
        "schemaVersion": 1,
        "ticket": "MDL-01",
        "generatedAt": stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "commit": commit,
        "source": dict(source or {}),
        "input": {"baseUrl": to_plain(base_url), "property": search_data["property"],
                  "startDate": start_date, "endDate": end_date, "parameters": to_plain(parameters)},
        "searchConsole": search_data,
        "crawl": crawl_data,
        "counts": {
            "crawledPages": len(crawl_data.get("pages", [])),
            "checkedLinks": len(crawl_data.get("links", {}).get("checks", [])),
            "brokenLinks": len(crawl_data.get("links", {}).get("confirmed_4xx", [])) + len(crawl_data.get("links", {}).get("confirmed_5xx", [])),
            "timeoutLinks": len(crawl_data.get("links", {}).get("timeouts", [])),
            "rateLimitedLinks": len(crawl_data.get("links", {}).get("rate_limited", [])),
            "inconclusiveLinks": len(crawl_data.get("links", {}).get("inconclusive", [])),
            "uncollectedPages": len(_uncollected_pages(crawl_data)),
            "indexedUrlsInspected": len(search_data.get("inspections", [])),
            "indexingErrors": sum(row.get("classification") == "error" for row in search_data.get("inspections", [])),
            "indexingUnknown": sum(row.get("classification") == "unknown" for row in search_data.get("inspections", [])),
        },
    }


def _uncollected_pages(crawl: dict[str, Any]) -> list[dict[str, Any]]:
    return [page for page in crawl.get("pages", []) if page.get("metadata_collected") is False]


def _line(value: Any) -> str:
    """Texto externo em uma unica linha."""
    return " ".join(str(value).splitlines())


def _cell(value: Any) -> str:
    """Celula de tabela: sem quebra de linha e com pipe escapado."""
    return _line(value).replace("\\", "\\\\").replace("|", "\\|")


def _row(*values: Any) -> str:
    return "| " + " | ".join(_cell(value) for value in values) + " |"


def _finding(severity: str, title: str, url: str, evidence: str, impact: str,
             recommendation: str, priority: int) -> dict[str, Any]:
    return {"priority": priority, "severity": severity, "title": title, "url": url,
            "evidence": evidence, "impact": impact, "recommendation": recommendation}


def findings(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    crawl = evidence["crawl"]
    search = evidence["searchConsole"]
    found: list[dict[str, Any]] = []
    for item in search.get("inspections", []):
        if item.get("classification") == "error":
            found.append(_finding("alta", "Erro de indexacao", item["url"],
                ", ".join(item.get("errors", [])) or "estado de indexacao reportado como erro",
                "A URL pode nao aparecer nos resultados de busca.",
                "Investigar o estado indicado no Search Console e corrigir a causa antes de solicitar nova indexacao.", 1))
        elif item.get("classification") == "unknown":
            found.append(_finding("media", "Estado de indexacao desconhecido", item["url"],
                ", ".join(item.get("unknown", [])) or "resposta de inspecao incompleta",
                "Nao e possivel confirmar a indexabilidade desta URL com a resposta disponivel.",
                "Verificar a URL no Search Console; a API nao fornece detalhe suficiente nesta resposta.", 3))
    for link in crawl.get("links", {}).get("confirmed_4xx", []) + crawl.get("links", {}).get("confirmed_5xx", []):
        found.append(_finding("alta" if link.get("classification") == "confirmed_4xx" else "media",
            "Link quebrado confirmado", link["url"], f"HTTP {link.get('status')}",
            "Visitantes e rastreadores encontram um destino indisponivel.",
            "Corrigir o destino, substituir o link ou remover a referencia na pagina de origem.", 2))
    for page in crawl.get("pages", []):
        status = page.get("status")
        if isinstance(status, int) and status >= 400 and status != 429:
            found.append(_finding("alta" if status < 500 else "media", "Pagina com resposta de erro",
                page.get("requested_url", ""), f"HTTP {status}",
                "A pagina nao foi entregue com sucesso a visitantes ou rastreadores.",
                "Restaurar a pagina ou configurar um redirecionamento permanente para a alternativa relevante.", 1))
    for page in crawl.get("pages", []):
        for absent, duplicate, label, recommendation in (
            ("title_absent", "title_duplicate", "title", "Adicionar title unico, descritivo e especifico para a pagina."),
            ("meta_description_absent", "meta_description_duplicate", "meta description", "Escrever meta description unica que resuma o conteudo e motive o clique."),
        ):
            if page.get("metadata_collected", True) and (page.get(absent) or page.get(duplicate)):
                issue = "ausente" if page.get(absent) else "duplicado"
                found.append(_finding("media", f"{label} {issue}", page["requested_url"],
                    f"{label} {issue}", "Trechos de busca podem ficar ausentes ou repetidos entre paginas.", recommendation, 4 if label == "title" else 5))
    robots = crawl.get("robots", {})
    if not robots.get("parsed"):
        found.append(_finding("alta", "robots.txt inconclusivo", robots.get("url", ""),
            robots.get("parse_error") or f"HTTP {robots.get('status')}",
            "As diretivas de rastreamento nao puderam ser confirmadas.",
            "Validar robots.txt e garantir que paginas importantes nao estejam bloqueadas.", 1))
    sitemap = crawl.get("sitemap", {})
    if not sitemap.get("documents") or any(not doc.get("parsed") for doc in sitemap.get("documents", [])):
        found.append(_finding("media", "Sitemap incompleto ou indisponivel", sitemap.get("documents", [{}])[0].get("url", "") if sitemap.get("documents") else "",
            f"documentos={len(sitemap.get('documents', []))}; referencias={len(sitemap.get('references', []))}",
            "A descoberta de URLs pelo sitemap pode estar limitada.",
            "Publicar sitemap XML valido e referenciar somente URLs canonicas e indexaveis.", 3))
    return sorted(found, key=lambda row: (row["priority"], row["url"], row["title"]))


def render_markdown(evidence: dict[str, Any]) -> str:
    search, crawl = evidence["searchConsole"], evidence["crawl"]
    metrics = search.get("aggregate", {})
    source = evidence.get("source", {})
    lines = ["# Auditoria SEO — MDL-01", "", f"Gerado: {evidence['generatedAt']} · Commit base: `{evidence['commit']}`"]
    if source.get("digest"):
        lines.append(f"Fontes executadas ({source.get('algorithm')}, `{source.get('root')}`): `{source['digest']}` · "
                     f"identicas ao commit base: {'sim' if source.get('matchesCommit') else 'nao'}")
    totals = (_row(*(metrics.get(field) for field in ("clicks", "impressions", "ctr", "position")))
              if metrics else _row("Nenhuma linha retornada pela API", "—", "—", "—"))
    lines.extend([
        f"Propriedade: `{search['property']}` · Periodo: {search['startDate']} a {search['endDate']}",
        f"URL-base: {_line(evidence['input']['baseUrl'])}", "", "## Search Console", "",
        "| Cliques | Impressoes | CTR | Posicao media |", "|---:|---:|---:|---:|", totals, "",
        "### Desempenho por pagina", "", "| Pagina | Cliques | Impressoes | CTR | Posicao |", "|---|---:|---:|---:|---:|"])
    for row in search.get("pages", []):
        keys = row.get("keys", [])
        lines.append(_row(keys[0] if keys else "(sem URL)", row.get("clicks"), row.get("impressions"),
                          row.get("ctr"), row.get("position")))
    if not search.get("pages"):
        lines.append("| Nenhuma linha retornada pela API | — | — | — | — |")
    lines.extend(["", "### Indexacao", "", "| URL | Classificacao | Veredito | Cobertura | Evidencia |", "|---|---|---|---|---|"])
    for row in search.get("inspections", []):
        detail = f"erros: {', '.join(row.get('errors', []))}; desconhecidos: {', '.join(row.get('unknown', []))}"
        lines.append(_row(row["url"], row.get("classification"), row.get("verdict"), row.get("coverageState"), detail))
    if not search.get("inspections"):
        lines.append("| Nenhuma URL inspecionada | unknown | — | — | Cobertura de inspecao vazia |")
    lines.extend(["", "## Crawl", "", f"Paginas: {len(crawl.get('pages', []))}; links verificados: {len(crawl.get('links', {}).get('checks', []))}; quebrados confirmados: {evidence['counts']['brokenLinks']}",
        "", "### Titles e meta descriptions", "", "| URL | Title | Meta description |", "|---|---|---|"])
    for page in crawl.get("pages", []):
        missing = "AUSENTE" if page.get("metadata_collected", True) else "NAO COLETADO"
        lines.append(_row(page["requested_url"], page.get("title") or missing, page.get("meta_description") or missing))
    lines.extend(["", "### Links quebrados", "", "| URL | HTTP | Classificacao |", "|---|---:|---|"])
    broken = crawl.get("links", {}).get("confirmed_4xx", []) + crawl.get("links", {}).get("confirmed_5xx", [])
    lines.extend(_row(row["url"], row.get("status"), row.get("classification")) for row in broken)
    if not broken:
        lines.append("| Nenhum link quebrado confirmado | — | — |")
    lines.extend(["", "### Verificacoes inconclusivas", "",
        "Os destinos abaixo nao foram confirmados como integros nem como quebrados."])
    for bucket, label in _UNCHECKED_BUCKETS:
        checks = crawl.get("links", {}).get(bucket, [])
        lines.extend(["", f"#### {label}: {len(checks)}"])
        if checks:
            lines.extend(["", "| URL | HTTP | Tentativas |", "|---|---:|---:|"])
            lines.extend(_row(row["url"], row.get("status") or "—", row.get("attempts")) for row in checks)
    uncollected = _uncollected_pages(crawl)
    lines.extend(["", f"#### Paginas sem metadados coletados: {len(uncollected)}"])
    if uncollected:
        lines.extend(["", "| URL | URL final | HTTP | Tentativas |", "|---|---|---:|---:|"])
        lines.extend(_row(page["requested_url"], page.get("final_url"), page.get("status") or "—",
                          page.get("attempts")) for page in uncollected)
    robots = crawl.get("robots", {})
    lines.extend(["", "### robots.txt", "", f"URL: {robots.get('url')} · HTTP {robots.get('status')} · parseado: {robots.get('parsed')} · allow: {len(robots.get('allow', []))} · disallow: {len(robots.get('disallow', []))}"])
    lines.extend(f"- Allow: `{_line(rule)}`" for rule in robots.get("allow", []))
    lines.extend(f"- Disallow: `{_line(rule)}`" for rule in robots.get("disallow", []))
    sitemap = crawl.get("sitemap", {})
    lines.extend(["", "### sitemap.xml", "", f"Documentos: {len(sitemap.get('documents', []))} · URLs declaradas: {len(sitemap.get('references', []))} · nao alcancadas: {len(sitemap.get('not_reached', []))}"])
    lines.extend(f"- `{doc.get('url')}` · HTTP {doc.get('status')} · parseado: {doc.get('parsed')} · tipo: {doc.get('kind')} · URLs: {len(doc.get('references', []))}" for doc in sitemap.get("documents", []))
    lines.extend([
        "", "## Achados priorizados", ""])
    items = findings(evidence)
    if not items:
        lines.append("Nenhum achado acionavel identificado nas verificacoes concluidas.")
    for item in items:
        lines.extend([f"### P{item['priority']} · {item['severity']} · {item['title']}",
            f"- URL/evidencia: `{_line(item['url'])}` — {_line(item['evidence'])}", f"- Impacto: {item['impact']}", f"- Recomendacao: {item['recommendation']}", ""])
    lines.extend(["## Cobertura e limitacoes", "",
        f"Crawl limitado a {evidence['input']['parameters'].get('maxPages')} paginas e a URLs publicamente alcancaveis/encontradas no sitemap.",
        "Search Analytics retorna as linhas disponibilizadas pela API para as consultas paginadas; dados agregados podem nao coincidir com a soma das linhas por pagina devido a limites/privacidade da API.",
        f"URL Inspection: {len(search.get('inspections', []))} URLs inspecionadas; estados unknown permanecem inconclusivos e nao foram interpretados como erro.",
        "Confirme achados inconclusivos diretamente no Search Console antes de aplicar correcoes.", ""])
    return "\n".join(lines)


def render_json(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
