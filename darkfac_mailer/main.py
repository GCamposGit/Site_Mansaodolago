"""Entrypoint do relatorio semanal de SEO.

A configuracao e lida so quando o processo roda. O unico destino do
relatorio e SMTP. Sucesso e falha escrevem uma linha JSON em stdout e
nao copiam destinatario, senha, conta de servico nem texto de excecao.

Uso: python -m darkfac_mailer.main
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import sys
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any, TextIO
from urllib import error as urllib_error
from urllib import request as urllib_request

from darkfac_mailer.gsc import SearchConsoleAdapter, SearchConsoleError
from darkfac_mailer.report import (
    INSUFFICIENT_SAMPLE,
    Change,
    MetricComparison,
    WeeklySeoReport,
    collect_weekly_report,
    render_report,
    sao_paulo_tz,
    week_windows,
)

ENV_RECIPIENTS = "MANSAODOLAGO_REPORT_RECIPIENTS"
ENV_SERVICE_ACCOUNT = "GOOGLE_SERVICE_ACCOUNT_JSON"
ENV_SITE_URL = "GSC_SITE_URL"
ENV_SMTP_HOST = "SMTP_HOST"
ENV_SMTP_PORT = "SMTP_PORT"
ENV_SMTP_USERNAME = "SMTP_USERNAME"
ENV_SMTP_PASSWORD = "SMTP_PASSWORD"
ENV_SMTP_FROM = "SMTP_FROM"

EVENT_NAME = "weekly_seo_report"
_SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "weekly_seo.html"
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_PERIOD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}$")
_TEMPLATE_TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")
_PRIVATE_KEY_MARKER = "PRIVATE KEY"
_EPS = 1e-9
_SMTP_TIMEOUT = 30

_STAGES = frozenset({"config", "collect", "render", "send"})
_STATUSES = frozenset({"success", "failure"})
_CODES = frozenset(
    {
        "sent",
        "recipients_missing",
        "recipients_invalid",
        "service_account_missing",
        "service_account_invalid",
        "gsc_site_url_missing",
        "gsc_site_url_invalid",
        "smtp_host_missing",
        "smtp_host_invalid",
        "smtp_port_missing",
        "smtp_port_invalid",
        "smtp_username_missing",
        "smtp_username_invalid",
        "smtp_password_missing",
        "smtp_from_missing",
        "smtp_from_invalid",
        "gsc_credentials_invalid",
        "gsc_request_failed",
        "gsc_response_invalid",
        "collect_failed",
        "render_failed",
        "smtp_send_failed",
        "unexpected_error",
    }
)
_GSC_CODES = frozenset(
    {
        "gsc_site_url_missing",
        "gsc_credentials_invalid",
        "gsc_request_failed",
        "gsc_response_invalid",
    }
)
_LABELS = {
    "clicks": "Cliques",
    "impressions": "Impressões",
    "ctr": "CTR",
    "position": "Posição média",
}

TokenLoader = Callable[[Mapping[str, Any]], str]
Connect = Callable[[str, int], Any]
Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class MailerError(Exception):
    """Falha de configuracao, coleta ou envio. A mensagem e so o codigo."""

    def __init__(self, code: str, *, stage: str) -> None:
        self.code = code
        self.stage = stage
        super().__init__(code)

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"MailerError(code={self.code!r}, stage={self.stage!r})"


@dataclass(frozen=True)
class MailerConfig:
    """Configuracao ja validada. ``repr`` nao inclui segredo nem destinatario."""

    recipients: tuple[str, ...]
    site_url: str
    service_account: Mapping[str, Any]
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str

    def __repr__(self) -> str:
        return (
            "MailerConfig("
            f"recipient_count={len(self.recipients)}, smtp_port={self.smtp_port})"
        )


def parse_recipients(raw: str | None) -> tuple[str, ...]:
    """Aceita lista separada por virgula. Nao devolve o texto invalido.

    Espacos nas bordas e segmentos vazios sao descartados. Um segmento
    com texto que nao e e-mail invalida a lista inteira.
    """

    if not isinstance(raw, str) or not raw.strip():
        raise MailerError("recipients_missing", stage="config")
    items: list[str] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if not _is_email(item):
            raise MailerError("recipients_invalid", stage="config")
        items.append(item)
    if not items:
        raise MailerError("recipients_missing", stage="config")
    return tuple(items)


def load_config(env: Mapping[str, str]) -> MailerConfig:
    """Le o mapeamento informado. Nao consulta o ambiente por conta propria."""

    recipients = parse_recipients(_optional_text(env, ENV_RECIPIENTS))
    service_account = _service_account(env)
    site_url = _required_text(
        env,
        ENV_SITE_URL,
        missing="gsc_site_url_missing",
        invalid="gsc_site_url_invalid",
        valid=_valid_site,
    )
    smtp_host = _required_text(
        env,
        ENV_SMTP_HOST,
        missing="smtp_host_missing",
        invalid="smtp_host_invalid",
        valid=_valid_host,
    )
    smtp_port = _smtp_port(env)
    smtp_username = _required_text(
        env,
        ENV_SMTP_USERNAME,
        missing="smtp_username_missing",
        invalid="smtp_username_invalid",
        valid=_valid_username,
    )
    smtp_password = _password(env)
    smtp_from = _required_text(
        env,
        ENV_SMTP_FROM,
        missing="smtp_from_missing",
        invalid="smtp_from_invalid",
        valid=_is_email,
    )
    return MailerConfig(
        recipients=recipients,
        site_url=site_url,
        service_account=service_account,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
    )


def build_message(config: MailerConfig, report: WeeklySeoReport) -> EmailMessage:
    """Monta o e-mail alternativo em texto e HTML. Nao envia."""

    message = EmailMessage()
    message["Subject"] = subject_for(report)
    message["From"] = config.smtp_from
    message["To"] = ", ".join(config.recipients)
    message.set_content(render_report(report))
    message.add_alternative(_render_html(report), subtype="html")
    return message


def subject_for(report: WeeklySeoReport) -> str:
    """O assunto identifica a semana civil corrente do relatorio."""

    start = report.current_window.start.isoformat()
    end = report.current_window.end.isoformat()
    return f"Relatório SEO semanal {start} a {end}"


def deliver(
    config: MailerConfig,
    message: EmailMessage,
    *,
    connect: Connect | None = None,
) -> None:
    """Envia por SMTP. A senha nao entra na fabrica da conexao."""

    opener = connect or _connect_smtp
    client: Any = None
    failure = "smtp_send_failed"
    try:
        client = opener(config.smtp_host, config.smtp_port)
        client.login(config.smtp_username, config.smtp_password)
        client.send_message(message)
        failure = ""
    except MailerError as exc:
        failure = exc.code if exc.code in _CODES else "smtp_send_failed"
    except Exception:
        failure = "smtp_send_failed"
    finally:
        _close_smtp(client)
    if failure:
        raise MailerError(failure, stage="send") from None


def run(
    env: Mapping[str, str] | None = None,
    *,
    now: datetime | None = None,
    token_loader: TokenLoader | None = None,
    transport: Transport | None = None,
    source: Any = None,
    connect: Connect | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Coleta o relatorio e envia. Devolve 0 so quando o SMTP aceita."""

    stream = stdout or sys.stdout
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _execute(
                env if env is not None else os.environ,
                now=now,
                token_loader=token_loader,
                transport=transport,
                source=source,
                connect=connect,
                stdout=stream,
            )
    except Exception:
        _emit(
            stream,
            status="failure",
            stage="config",
            code="unexpected_error",
            period=None,
            recipient_count=0,
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    """Ignora argumentos: destinatario nenhum vem da linha de comando."""

    del argv
    try:
        return run()
    except Exception:
        _emit(
            sys.stdout,
            status="failure",
            stage="config",
            code="unexpected_error",
            period=None,
            recipient_count=0,
        )
        return 1


def _execute(
    env: Mapping[str, str],
    *,
    now: datetime | None,
    token_loader: TokenLoader | None,
    transport: Transport | None,
    source: Any,
    connect: Connect | None,
    stdout: TextIO,
) -> int:
    try:
        moment = now if now is not None else datetime.now(sao_paulo_tz())
        windows = week_windows(moment)
    except Exception:
        return _fail(stdout, stage="config", code="unexpected_error", period=None, count=0)
    period = f"{windows.current.start.isoformat()}/{windows.current.end.isoformat()}"

    try:
        config = load_config(env)
    except MailerError as exc:
        return _fail(stdout, stage="config", code=exc.code, period=period, count=0)
    except Exception:
        return _fail(stdout, stage="config", code="unexpected_error", period=period, count=0)

    count = len(config.recipients)
    try:
        report = _collect(
            config,
            moment,
            token_loader=token_loader,
            transport=transport,
            source=source,
        )
    except SearchConsoleError as exc:
        code = exc.code if exc.code in _GSC_CODES else "collect_failed"
        return _fail(stdout, stage="collect", code=code, period=period, count=count)
    except MailerError as exc:
        stage = exc.stage if exc.stage in _STAGES else "collect"
        return _fail(stdout, stage=stage, code=exc.code, period=period, count=count)
    except Exception:
        return _fail(stdout, stage="collect", code="collect_failed", period=period, count=count)

    try:
        message = build_message(config, report)
    except MailerError as exc:
        return _fail(stdout, stage="render", code=exc.code, period=period, count=count)
    except Exception:
        return _fail(stdout, stage="render", code="render_failed", period=period, count=count)

    try:
        deliver(config, message, connect=connect)
    except MailerError as exc:
        return _fail(stdout, stage="send", code=exc.code, period=period, count=count)
    except Exception:
        return _fail(stdout, stage="send", code="smtp_send_failed", period=period, count=count)

    _emit(
        stdout,
        status="success",
        stage="send",
        code="sent",
        period=period,
        recipient_count=count,
    )
    return 0


def _collect(
    config: MailerConfig,
    now: datetime,
    *,
    token_loader: TokenLoader | None,
    transport: Transport | None,
    source: Any,
) -> WeeklySeoReport:
    if source is None:
        token = _resolve_token(config.service_account, token_loader)
        kwargs: dict[str, Any] = {}
        if transport is not None:
            kwargs["transport"] = transport
        source = SearchConsoleAdapter(config.site_url, token, **kwargs)
    return collect_weekly_report(source, now)


def _resolve_token(info: Mapping[str, Any], loader: TokenLoader | None) -> str:
    reader = loader or _google_access_token
    token: Any = ""
    failure = ""
    try:
        token = reader(info)
    except MailerError as exc:
        failure = exc.code if exc.code in _CODES else "gsc_credentials_invalid"
    except Exception:
        failure = "gsc_credentials_invalid"
    if failure:
        raise MailerError(failure, stage="collect") from None
    if not isinstance(token, str) or not token.strip():
        raise MailerError("gsc_credentials_invalid", stage="collect")
    return token.strip()


def _google_access_token(info: Mapping[str, Any]) -> str:
    """Troca a conta de servico por um bearer token. Falha sem contexto."""

    try:
        from google.oauth2 import service_account
    except Exception:
        imported = None
    else:
        imported = service_account
    if imported is None:
        raise MailerError("gsc_credentials_invalid", stage="collect") from None

    token = ""
    failed = False
    try:
        credentials = imported.Credentials.from_service_account_info(
            dict(info),
            scopes=[_SEARCH_CONSOLE_SCOPE],
        )
        credentials.refresh(_UrllibAuthRequest())
        raw = getattr(credentials, "token", "")
        token = raw if isinstance(raw, str) else ""
    except Exception:
        failed = True
    if failed or not token.strip():
        raise MailerError("gsc_credentials_invalid", stage="collect") from None
    return token.strip()


class _AuthResponse:
    def __init__(self, status: int, headers: Mapping[str, str], data: bytes) -> None:
        self.status = status
        self.headers = dict(headers)
        self.data = data


class _UrllibAuthRequest:
    """Pedido minimo compativel com google.auth, sem cliente HTTP extra."""

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> _AuthResponse:
        del kwargs
        request = urllib_request.Request(
            url,
            data=body,
            headers=dict(headers or {}),
            method=method,
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout or _SMTP_TIMEOUT) as response:
                payload = response.read()
                status = int(response.status)
                header_map = dict(response.headers.items())
        except urllib_error.HTTPError as exc:
            payload = exc.read()
            status = int(exc.code)
            header_map = dict(exc.headers.items()) if exc.headers else {}
        return _AuthResponse(status, header_map, payload)


def _connect_smtp(host: str, port: int) -> Any:
    """465 usa TLS implicito. Os demais exigem STARTTLS antes do login."""

    if port == 465:
        return smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT)
    client = smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT)
    try:
        client.ehlo()
        client.starttls()
        client.ehlo()
    except Exception:
        _close_smtp(client)
        raise
    return client


def _close_smtp(client: Any) -> None:
    if client is None:
        return
    try:
        client.quit()
    except Exception:
        try:
            client.close()
        except Exception:
            return


def _render_html(report: WeeklySeoReport) -> str:
    template = ""
    failed = False
    try:
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    except Exception:
        failed = True
    if failed:
        raise MailerError("render_failed", stage="render") from None
    values = {
        "current_start": escape(report.current_window.start.isoformat()),
        "current_end": escape(report.current_window.end.isoformat()),
        "previous_start": escape(report.previous_window.start.isoformat()),
        "previous_end": escape(report.previous_window.end.isoformat()),
        "metric_rows": _metric_rows(report),
        "actions_html": _actions_html(report),
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(key)
        return values[key]

    rendered = ""
    failed = False
    try:
        rendered = _TEMPLATE_TOKEN.sub(replace, template)
    except Exception:
        failed = True
    if failed:
        raise MailerError("render_failed", stage="render") from None
    return rendered


def _metric_rows(report: WeeklySeoReport) -> str:
    rows: list[str] = []
    for metric in (report.clicks, report.impressions, report.ctr, report.position):
        label, current, previous, delta, change = _metric_cells(metric)
        rows.append(
            "<tr>"
            f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0e9dc;\">{escape(label)}</td>"
            f"<td align=\"right\" style=\"padding:8px 6px;border-bottom:1px solid #f0e9dc;\">{escape(current)}</td>"
            f"<td align=\"right\" style=\"padding:8px 6px;border-bottom:1px solid #f0e9dc;\">{escape(previous)}</td>"
            f"<td align=\"right\" style=\"padding:8px 6px;border-bottom:1px solid #f0e9dc;\">{escape(delta)}</td>"
            f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0e9dc;\">{escape(change)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _metric_cells(metric: MetricComparison) -> tuple[str, str, str, str, str]:
    label = _LABELS[metric.key]
    if metric.change is Change.AMOSTRA_INSUFICIENTE:
        missing = INSUFFICIENT_SAMPLE
        return label, missing, missing, missing, missing
    return (
        label,
        _format_value(metric.key, metric.current),
        _format_value(metric.key, metric.previous),
        _format_delta(metric.key, metric.delta),
        metric.change.value,
    )


def _actions_html(report: WeeklySeoReport) -> str:
    if report.actions_message:
        body = f"<p>{escape(report.actions_message)}</p>"
    elif not report.actions:
        body = "<p>Nenhuma queda de cliques em páginas ou consultas.</p>"
    else:
        items = "".join(f"<li>{escape(action.message)}</li>" for action in report.actions)
        body = f"<ol>{items}</ol>"
    if report.sample_message and report.sample_message != report.actions_message:
        body += f"<p>{escape(report.sample_message)}</p>"
    return body


def _format_count(value: float) -> str:
    if abs(value - round(value)) < _EPS:
        return str(int(round(value)))
    return f"{value:.1f}"


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


def _optional_text(env: Mapping[str, str], key: str) -> str | None:
    if key not in env:
        return None
    value = env[key]
    if not isinstance(value, str):
        return None
    return value


def _required_text(
    env: Mapping[str, str],
    key: str,
    *,
    missing: str,
    invalid: str,
    valid: Callable[[str], bool],
) -> str:
    raw = _optional_text(env, key)
    if raw is None or not raw.strip():
        raise MailerError(missing, stage="config")
    value = raw.strip()
    if not valid(value):
        raise MailerError(invalid, stage="config")
    return value


def _password(env: Mapping[str, str]) -> str:
    # A senha nao e aparada: espaco faz parte do segredo.
    raw = _optional_text(env, ENV_SMTP_PASSWORD)
    if raw is None or raw == "":
        raise MailerError("smtp_password_missing", stage="config")
    return raw


def _smtp_port(env: Mapping[str, str]) -> int:
    raw = _optional_text(env, ENV_SMTP_PORT)
    if raw is None or not raw.strip():
        raise MailerError("smtp_port_missing", stage="config")
    text = raw.strip()
    if not text.isdecimal():
        raise MailerError("smtp_port_invalid", stage="config")
    port = int(text)
    if port < 1 or port > 65535:
        raise MailerError("smtp_port_invalid", stage="config")
    return port


def _service_account(env: Mapping[str, str]) -> Mapping[str, Any]:
    raw = _optional_text(env, ENV_SERVICE_ACCOUNT)
    if raw is None or not raw.strip():
        raise MailerError("service_account_missing", stage="config")
    parsed: Any = None
    failed = False
    try:
        parsed = json.loads(raw)
    except Exception:
        failed = True
    if failed:
        raise MailerError("service_account_invalid", stage="config") from None
    if not isinstance(parsed, dict):
        raise MailerError("service_account_invalid", stage="config")
    if parsed.get("type") != "service_account":
        raise MailerError("service_account_invalid", stage="config")
    email = parsed.get("client_email")
    private_key = parsed.get("private_key")
    token_uri = parsed.get("token_uri")
    if not isinstance(email, str) or not _is_email(email):
        raise MailerError("service_account_invalid", stage="config")
    if not isinstance(private_key, str) or not _valid_private_key(private_key):
        raise MailerError("service_account_invalid", stage="config")
    if not isinstance(token_uri, str) or not _valid_token_uri(token_uri):
        raise MailerError("service_account_invalid", stage="config")
    return parsed


def _valid_private_key(value: str) -> bool:
    if len(value) < 32 or _PRIVATE_KEY_MARKER not in value:
        return False
    if "\x00" in value:
        return False
    return "\n" in value or "\r" in value


def _valid_token_uri(value: str) -> bool:
    if not value.startswith("https://") or len(value) > 300:
        return False
    return not any(character.isspace() or ord(character) < 32 for character in value)


def _is_email(value: str) -> bool:
    if len(value) > 254 or not _EMAIL_RE.fullmatch(value):
        return False
    if ".." in value:
        return False
    local, domain = value.rsplit("@", 1)
    if not local or len(local) > 64:
        return False
    if local.startswith(".") or local.endswith("."):
        return False
    if domain.startswith(".") or domain.endswith(".") or domain.startswith("-"):
        return False
    labels = domain.split(".")
    for label in labels:
        if not label or label.startswith("-") or label.endswith("-") or len(label) > 63:
            return False
    return True


def _valid_host(value: str) -> bool:
    if _IPV4_RE.fullmatch(value):
        return all(0 <= int(part) <= 255 for part in value.split("."))
    return _HOST_RE.fullmatch(value) is not None


def _valid_site(value: str) -> bool:
    if not value or len(value) > 2048:
        return False
    return not any(character.isspace() or ord(character) < 32 for character in value)


def _valid_username(value: str) -> bool:
    if not value or len(value) > 320:
        return False
    return not any(ord(character) < 32 for character in value)


def _fail(
    stdout: TextIO,
    *,
    stage: str,
    code: str,
    period: str | None,
    count: int,
) -> int:
    _emit(
        stdout,
        status="failure",
        stage=stage,
        code=code,
        period=period,
        recipient_count=count,
    )
    return 1


def _emit(
    stdout: TextIO,
    *,
    status: str,
    stage: str,
    code: str,
    period: str | None,
    recipient_count: int,
) -> None:
    safe_period = period if isinstance(period, str) and _PERIOD_RE.fullmatch(period) else None
    if isinstance(recipient_count, bool) or not isinstance(recipient_count, int):
        safe_count = 0
    elif recipient_count < 0:
        safe_count = 0
    else:
        safe_count = recipient_count
    payload = {
        "event": EVENT_NAME,
        "status": status if status in _STATUSES else "failure",
        "stage": stage if stage in _STAGES else "config",
        "code": code if code in _CODES else "unexpected_error",
        "period": safe_period,
        "recipient_count": safe_count,
    }
    stdout.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
    try:
        stdout.flush()
    except Exception:
        return


if __name__ == "__main__":
    sys.exit(main())
