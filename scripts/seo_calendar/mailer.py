"""Entrega SMTP do calendário SEO usando configuração injetada pelo cofre."""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Mapping, Protocol

from seo_calendar.planner import EditorialCalendar

HOST_ENV = "MDL_SMTP_HOST"
PORT_ENV = "MDL_SMTP_PORT"
USER_ENV = "MDL_SMTP_USER"
PASSWORD_ENV = "MDL_SMTP_PASSWORD"
SENDER_ENV = "MDL_SMTP_FROM"
RECIPIENTS_ENV = "MDL_SMTP_RECIPIENTS"


class DeliveryError(Exception):
    """Erro seguro de entrega. Nunca carrega mensagem do provedor SMTP."""


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str = field(repr=False)
    password: str = field(repr=False)
    sender: str = field(repr=False)
    recipients: tuple[str, ...] = field(repr=False)


class SmtpConnection(Protocol):
    def ehlo(self) -> object: ...
    def starttls(self, context: ssl.SSLContext) -> object: ...
    def login(self, user: str, password: str) -> object: ...
    def send_message(self, message: EmailMessage) -> Mapping[str, object]: ...
    def quit(self) -> object: ...


def load_config(environ: Mapping[str, str] | None = None) -> SmtpConfig:
    """Lê apenas valores injetados no ambiente; não usa defaults administrativos."""

    source = os.environ if environ is None else environ
    names = (HOST_ENV, PORT_ENV, USER_ENV, PASSWORD_ENV, SENDER_ENV, RECIPIENTS_ENV)
    values = {name: source.get(name, "").strip() for name in names}
    if any(not value for value in values.values()):
        raise DeliveryError("Configuração do cofre incompleta para entrega SMTP.")
    try:
        port = int(values[PORT_ENV])
    except ValueError:
        raise DeliveryError("Porta SMTP inválida na configuração do cofre.") from None
    if not 1 <= port <= 65535:
        raise DeliveryError("Porta SMTP inválida na configuração do cofre.")
    recipients = tuple(dict.fromkeys(part.strip() for part in values[RECIPIENTS_ENV].replace(";", ",").split(",") if part.strip()))
    if not recipients or any("@" not in address for address in (values[SENDER_ENV], *recipients)):
        raise DeliveryError("Remetente ou destinatários inválidos na configuração do cofre.")
    return SmtpConfig(
        host=values[HOST_ENV],
        port=port,
        username=values[USER_ENV],
        password=values[PASSWORD_ENV],
        sender=values[SENDER_ENV],
        recipients=recipients,
    )


def build_message(calendar: EditorialCalendar, attachment: str | Path, config: SmtpConfig) -> EmailMessage:
    """Monta e-mail com resumo e anexo CSV, sem revelar config em cabeçalhos/logs."""

    path = Path(attachment)
    try:
        payload = path.read_bytes()
    except OSError:
        raise DeliveryError("Não foi possível ler o CSV do calendário para anexar.") from None
    message = EmailMessage()
    message["Subject"] = f"Calendário SEO de conteúdo — {calendar.property_url}"
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message["Message-ID"] = make_msgid()
    message.set_content(_body(calendar))
    message.add_attachment(
        payload,
        maintype="text",
        subtype="csv",
        filename=path.name,
    )
    return message


def send_calendar(
    calendar: EditorialCalendar,
    attachment: str | Path,
    config: SmtpConfig,
    *,
    smtp_factory=smtplib.SMTP,
) -> str:
    """Envia via STARTTLS e exige aceitação SMTP de cada destinatário."""

    message = build_message(calendar, attachment, config)
    connection: SmtpConnection | None = None
    try:
        connection = smtp_factory(config.host, config.port, timeout=30)
        connection.ehlo()
        connection.starttls(context=ssl.create_default_context())
        connection.ehlo()
        connection.login(config.username, config.password)
        refused = connection.send_message(message)
        if refused:
            raise DeliveryError("O servidor SMTP recusou um ou mais destinatários do cofre.")
        message_id = message.get("Message-ID")
        if not message_id:
            raise DeliveryError("O servidor não confirmou um Message-ID para a entrega.")
        return message_id
    except DeliveryError:
        raise
    except Exception:
        raise DeliveryError("Falha SMTP durante a entrega; detalhes omitidos por segurança.") from None
    finally:
        if connection is not None:
            try:
                connection.quit()
            except Exception:
                pass


def _body(calendar: EditorialCalendar) -> str:
    lines = [
        "Calendário editorial proposto a partir de dados reais do Google Search Console.",
        f"Propriedade: {calendar.property_url}",
        f"Período consultado: {calendar.window_start.isoformat()} a {calendar.window_end.isoformat()}",
        f"Digest SHA-256 dos dados: {calendar.input_digest}",
        "",
        "Quatro pautas propostas (aguardam aceite do owner; nada foi publicado):",
    ]
    for entry in calendar.entries:
        lines.append(
            f"Semana {entry.week} ({entry.week_start.isoformat()}): {entry.topic} "
            f"— consulta alvo: {entry.target_query} — {entry.impressions} impressões, "
            f"posição média {entry.position:.2f}."
        )
    lines.extend(("", "O CSV anexo contém justificativas, métricas e landing pages por pauta."))
    return "\n".join(lines)
