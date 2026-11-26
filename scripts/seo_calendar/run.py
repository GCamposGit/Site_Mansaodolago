"""CLI para gerar e enviar (com confirmação) o calendário SEO ao administrador."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from seo_calendar import gsc
from seo_calendar.mailer import DeliveryError, load_config, send_calendar
from seo_calendar.planner import build_calendar
from seo_calendar.report import write_csv

SEND_BRANCH = "darkfac/m1-seo"
AUDIT_ENV = "MDL_DELIVERY_AUDIT_FILE"


def current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise DeliveryError("Não foi possível confirmar a branch Git; envio recusado.") from None
    return result.stdout.strip()


def _record_delivery(path: Path, digest: str, message_id: str) -> None:
    """Acrescenta apenas os três campos operacionais fora do histórico Git."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "digest": digest,
            "message_id": message_id,
        }
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        raise DeliveryError("Não foi possível gravar o registro local da entrega.") from None


def _audit_destination() -> Path:
    """Resolve o log e recusa arquivo versionável dentro do repositório."""

    raw = os.environ.get(
        AUDIT_ENV,
        "scripts/seo_calendar/artifacts/deliveries.jsonl",
    )
    path = Path(raw).expanduser().resolve()
    try:
        root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        root = Path(root_result.stdout.strip()).resolve()
        path.relative_to(root)
    except ValueError:
        return path
    except (OSError, subprocess.SubprocessError):
        raise DeliveryError("Não foi possível validar o destino do registro operacional.") from None
    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(path)],
            cwd=root,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise DeliveryError("Não foi possível validar o destino do registro operacional.") from None
    if ignored.returncode != 0:
        raise DeliveryError("Envio recusado: o registro operacional não está fora do Git.")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise DeliveryError("Não foi possível preparar o destino do registro operacional.") from None
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sitemap", type=Path, default=Path("sitemap.xml"))
    parser.add_argument("--site-root", type=Path, default=Path("."))
    parser.add_argument("--property", default=gsc.DEFAULT_SITE_URL, dest="property_url")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("scripts/seo_calendar/artifacts/calendario-seo.csv"),
        dest="csv_path",
    )
    parser.add_argument("--send", action="store_true", help="envia após validar branch e digest")
    parser.add_argument("--confirm-digest", help="digest SHA-256 exibido na execução dry-run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        collection = gsc.collect(
            sitemap_path=args.sitemap,
            site_root=args.site_root,
            site_url=args.property_url,
        )
        calendar = build_calendar(collection, property_url=args.property_url)
        args.csv_path.parent.mkdir(parents=True, exist_ok=True)
        write_csv(calendar, args.csv_path)
        print(f"Calendário preparado: {len(calendar.entries)} pautas; CSV: {args.csv_path}")
        print(f"Propriedade: {calendar.property_url}")
        print(f"Período: {calendar.window_start.isoformat()} a {calendar.window_end.isoformat()}")
        for item in calendar.entries:
            print(f"Semana {item.week}: {item.topic} | consulta: {item.target_query}")
        print(f"Digest SHA-256: {calendar.input_digest}")

        if not args.send:
            print("Dry-run: nenhum e-mail enviado e nenhuma página publicada.")
            return 0

        branch = current_branch()
        if branch == "master" or branch != SEND_BRANCH:
            raise DeliveryError("Envio recusado: a branch atual não é darkfac/m1-seo.")
        if args.confirm_digest != calendar.input_digest:
            raise DeliveryError("Envio recusado: confirme exatamente o digest SHA-256 exibido.")
        audit_path = _audit_destination()
        config = load_config()
        message_id = send_calendar(calendar, args.csv_path, config)
        _record_delivery(audit_path, calendar.input_digest, message_id)
        print(f"Entrega aceita pelo SMTP para todos os destinatários. Message-ID: {message_id}")
        print(f"Registro operacional gravado em {audit_path}.")
        return 0
    except (gsc.SeoCalendarError, DeliveryError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("Falha inesperada na execução; detalhes omitidos por segurança.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
