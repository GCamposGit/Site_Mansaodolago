"""Run the live MDL-01 audit and publish a complete evidence pair."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import crawler, search_console
from .report import build_evidence, render_json, render_markdown


def _commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=5)
        value = result.stdout.strip()
        return value if value else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run_audit(*, base_url: str, start_date: str, end_date: str,
              output_dir: Path, timeout: float = crawler.DEFAULT_TIMEOUT_S,
              max_pages: int = crawler.DEFAULT_MAX_PAGES,
              crawl_fn: Any = crawler.crawl_site, service_fn: Any = search_console.create_service,
              search_fn: Any = search_console.audit_search_console) -> tuple[Path, Path]:
    """Collect both sources before writing, then publish by one directory rename."""
    output_dir = output_dir.resolve()
    crawl_report = crawl_fn(base_url, timeout=timeout, max_pages=max_pages)
    service = service_fn()
    search_report = search_fn(crawl_report, start_date, end_date, service=service)
    generated = datetime.now(timezone.utc)
    params = {"timeoutSeconds": timeout, "maxPages": max_pages,
              "maxAttempts": crawler.DEFAULT_MAX_ATTEMPTS,
              "userAgent": crawler.USER_AGENT,
              "searchAnalyticsDataState": "final",
              "searchAnalyticsPageSize": search_console.MAX_ANALYTICS_PAGE_SIZE,
              "searchConsoleMaxInspections": search_console.MAX_INSPECTIONS_PER_DAY,
              "searchConsoleMaxAttempts": 3}
    evidence = build_evidence(crawl_report, search_report, base_url=base_url,
        start_date=start_date, end_date=end_date, parameters=params,
        commit=_commit(), generated_at=generated)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    final_dir = output_dir / f"MDL-01-seo-audit-{stamp}"
    if final_dir.exists():
        raise FileExistsError("diretorio de saida ja existe")
    staging = Path(tempfile.mkdtemp(prefix=".MDL-01-seo-audit-staging-", dir=output_dir))
    try:
        json_path = staging / "evidence.json"
        markdown_path = staging / "report.md"
        json_path.write_text(render_json(evidence), encoding="utf-8")
        markdown_path.write_text(render_markdown(evidence), encoding="utf-8")
        # Parse back before publishing to ensure the JSON is complete and valid.
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        if parsed.get("ticket") != "MDL-01" or not markdown_path.read_text(encoding="utf-8").startswith("# Auditoria SEO"):
            raise ValueError("validacao dos artefatos falhou")
        staging.rename(final_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final_dir / "evidence.json", final_dir / "report.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditoria SEO somente leitura MDL-01")
    parser.add_argument("--base-url", default=crawler.DEFAULT_SEED)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "output")
    parser.add_argument("--timeout", type=float, default=crawler.DEFAULT_TIMEOUT_S)
    parser.add_argument("--max-pages", type=int, default=crawler.DEFAULT_MAX_PAGES)
    args = parser.parse_args(argv)
    try:
        json_path, markdown_path = run_audit(base_url=args.base_url,
            start_date=args.start_date, end_date=args.end_date,
            output_dir=args.output_dir, timeout=args.timeout, max_pages=args.max_pages)
    except (crawler.CrawlError, search_console.SearchConsoleError, ValueError, OSError) as exc:
        # Errors raised by secret loading and Google client are sanitized by their modules.
        print(f"auditoria nao publicada: {exc}", file=sys.stderr)
        return 1
    print(f"JSON: {json_path}\nMarkdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
