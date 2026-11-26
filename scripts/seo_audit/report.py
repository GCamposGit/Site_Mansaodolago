"""Build reproducible JSON evidence and an actionable Markdown audit."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


_SENSITIVE = re.compile(r"credential|token|private[_-]?key|client[_-]?email|authorization", re.I)


def _plain(value: Any) -> Any:
    convert = getattr(value, "to_dict", None)
    if callable(convert):
        return _plain(convert())
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items() if not _SENSITIVE.search(str(key))}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def build_evidence(crawl: Any, search: Any, *, base_url: str, start_date: str,
                   end_date: str, parameters: dict[str, Any], commit: str,
                   generated_at: datetime | None = None) -> dict[str, Any]:
    """Return the normalized source data plus reproducibility metadata."""
    crawl_data, search_data = _plain(crawl), _plain(search)
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
        "input": {"baseUrl": base_url, "property": search_data["property"],
                  "startDate": start_date, "endDate": end_date, "parameters": _plain(parameters)},
        "searchConsole": search_data,
        "crawl": crawl_data,
        "counts": {
            "crawledPages": len(crawl_data.get("pages", [])),
            "checkedLinks": len(crawl_data.get("links", {}).get("checks", [])),
            "brokenLinks": len(crawl_data.get("links", {}).get("confirmed_4xx", [])) + len(crawl_data.get("links", {}).get("confirmed_5xx", [])),
            "indexedUrlsInspected": len(search_data.get("inspections", [])),
            "indexingErrors": sum(row.get("classification") == "error" for row in search_data.get("inspections", [])),
            "indexingUnknown": sum(row.get("classification") == "unknown" for row in search_data.get("inspections", [])),
        },
    }


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
        if isinstance(status, int) and status >= 400:
            found.append(_finding("alta" if status < 500 else "media", "Pagina com resposta de erro",
                page.get("requested_url", ""), f"HTTP {status}",
                "A pagina nao foi entregue com sucesso a visitantes ou rastreadores.",
                "Restaurar a pagina ou configurar um redirecionamento permanente para a alternativa relevante.", 1))
    for page in crawl.get("pages", []):
        for absent, duplicate, label, recommendation in (
            ("title_absent", "title_duplicate", "title", "Adicionar title unico, descritivo e especifico para a pagina."),
            ("meta_description_absent", "meta_description_duplicate", "meta description", "Escrever meta description unica que resuma o conteudo e motive o clique."),
        ):
            if page.get(absent) or page.get(duplicate):
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
    lines = ["# Auditoria SEO — MDL-01", "", f"Gerado: {evidence['generatedAt']} · Commit: `{evidence['commit']}`",
        f"Propriedade: `{search['property']}` · Periodo: {search['startDate']} a {search['endDate']}",
        f"URL-base: {evidence['input']['baseUrl']}", "", "## Search Console", "",
        "| Cliques | Impressoes | CTR | Posicao media |", "|---:|---:|---:|---:|",
        f"| {metrics.get('clicks')} | {metrics.get('impressions')} | {metrics.get('ctr')} | {metrics.get('position')} |", "",
        "### Desempenho por pagina", "", "| Pagina | Cliques | Impressoes | CTR | Posicao |", "|---|---:|---:|---:|---:|"]
    for row in search.get("pages", []):
        keys = row.get("keys", [])
        lines.append(f"| {keys[0] if keys else '(sem URL)'} | {row.get('clicks')} | {row.get('impressions')} | {row.get('ctr')} | {row.get('position')} |")
    if not search.get("pages"):
        lines.append("| Nenhuma linha retornada pela API | — | — | — | — |")
    lines.extend(["", "### Indexacao", "", "| URL | Classificacao | Veredito | Cobertura | Evidencia |", "|---|---|---|---|---|"])
    for row in search.get("inspections", []):
        lines.append(f"| {row['url']} | {row.get('classification')} | {row.get('verdict')} | {row.get('coverageState')} | erros: {', '.join(row.get('errors', []))}; desconhecidos: {', '.join(row.get('unknown', []))} |")
    if not search.get("inspections"):
        lines.append("| Nenhuma URL inspecionada | unknown | — | — | Cobertura de inspecao vazia |")
    lines.extend(["", "## Crawl", "", f"Paginas: {len(crawl.get('pages', []))}; links verificados: {len(crawl.get('links', {}).get('checks', []))}; quebrados confirmados: {evidence['counts']['brokenLinks']}",
        "", "### Titles e meta descriptions", "", "| URL | Title | Meta description |", "|---|---|---|"])
    for page in crawl.get("pages", []):
        lines.append(f"| {page['requested_url']} | {page.get('title') or 'AUSENTE'} | {page.get('meta_description') or 'AUSENTE'} |")
    lines.extend(["", "### Links quebrados", "", "| URL | HTTP | Classificacao |", "|---|---:|---|"])
    broken = crawl.get("links", {}).get("confirmed_4xx", []) + crawl.get("links", {}).get("confirmed_5xx", [])
    lines.extend(f"| {row['url']} | {row.get('status')} | {row.get('classification')} |" for row in broken)
    if not broken:
        lines.append("| Nenhum link quebrado confirmado | — | — |")
    robots = crawl.get("robots", {})
    lines.extend(["", "### robots.txt", "", f"URL: {robots.get('url')} · HTTP {robots.get('status')} · parseado: {robots.get('parsed')} · allow: {len(robots.get('allow', []))} · disallow: {len(robots.get('disallow', []))}"])
    lines.extend(f"- Allow: `{rule}`" for rule in robots.get("allow", []))
    lines.extend(f"- Disallow: `{rule}`" for rule in robots.get("disallow", []))
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
            f"- URL/evidencia: `{item['url']}` — {item['evidence']}", f"- Impacto: {item['impact']}", f"- Recomendacao: {item['recommendation']}", ""])
    lines.extend(["## Cobertura e limitacoes", "",
        f"Crawl limitado a {evidence['input']['parameters'].get('maxPages')} paginas e a URLs publicamente alcancaveis/encontradas no sitemap.",
        "Search Analytics retorna as linhas disponibilizadas pela API para as consultas paginadas; dados agregados podem nao coincidir com a soma das linhas por pagina devido a limites/privacidade da API.",
        f"URL Inspection: {len(search.get('inspections', []))} URLs inspecionadas; estados unknown permanecem inconclusivos e nao foram interpretados como erro.",
        "Confirme achados inconclusivos diretamente no Search Console antes de aplicar correcoes.", ""])
    return "\n".join(lines)


def render_json(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
