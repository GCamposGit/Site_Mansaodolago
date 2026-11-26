"""Testes de entrega controlada do calendário (MDL-03 T3)."""

from __future__ import annotations

import json
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_calendar import gsc  # noqa: E402
from seo_calendar.mailer import (  # noqa: E402
    PASSWORD_ENV,
    RECIPIENTS_ENV,
    DeliveryError,
    SmtpConfig,
    build_message,
    load_config,
    send_calendar,
)
from seo_calendar.planner import build_calendar  # noqa: E402
from seo_calendar.report import write_csv  # noqa: E402
from seo_calendar import run  # noqa: E402


def _calendar():
    queries = tuple(
        gsc.QueryClassification(
            query=f"consulta lago tema{index}",
            impressions=100 - index,
            clicks=10 - index,
            position=8 + index,
            category=(gsc.CATEGORY_OUTSIDE if index == 1 else gsc.CATEGORY_OPPORTUNITY),
            without_dedicated_page=index == 1,
            covering_urls=(),
            pages=(f"https://www.mansaodolago.com/pagina-{index}",),
        )
        for index in range(1, 6)
    )
    collected = gsc.CollectionResult(date(2026, 10, 1), date(2026, 10, 28), 5, queries)
    return build_calendar(
        collected,
        property_url=gsc.DEFAULT_SITE_URL,
        generated_on=date(2026, 11, 24),
    )


def _config():
    return SmtpConfig(
        host="smtp.vault.invalid",
        port=587,
        username="vault-user",
        password="vault-password-private",
        sender="sender@example.invalid",
        recipients=("admin1@example.invalid", "admin2@example.invalid"),
    )


def test_vault_config_is_required_and_secrets_are_not_in_repr_or_errors():
    with pytest.raises(DeliveryError) as missing:
        load_config({})
    assert "vault-password-private" not in str(missing.value)
    env = {
        "MDL_SMTP_HOST": "smtp.vault.invalid",
        "MDL_SMTP_PORT": "587",
        "MDL_SMTP_USER": "vault-user",
        PASSWORD_ENV: "vault-password-private",
        "MDL_SMTP_FROM": "sender@example.invalid",
        RECIPIENTS_ENV: "admin1@example.invalid; admin2@example.invalid",
    }
    config = load_config(env)
    assert config.recipients == ("admin1@example.invalid", "admin2@example.invalid")
    assert "vault-password-private" not in repr(config)
    assert "admin1@example.invalid" not in repr(config)


def test_message_summarizes_four_pautas_and_attaches_generated_csv(tmp_path: Path):
    calendar = _calendar()
    csv_path = tmp_path / "calendar.csv"
    write_csv(calendar, csv_path)
    message = build_message(calendar, csv_path, _config())
    body = message.get_body(preferencelist=("plain",)).get_content()
    assert calendar.property_url in body
    assert "2026-10-01 a 2026-10-28" in body
    for entry in calendar.entries:
        assert entry.topic in body
        assert entry.target_query in body
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "calendar.csv"
    assert attachments[0].get_payload(decode=True) == csv_path.read_bytes()
    assert message["Message-ID"]


def test_smtp_delivery_requires_all_recipients_accepted(tmp_path: Path):
    calendar = _calendar()
    csv_path = tmp_path / "calendar.csv"
    write_csv(calendar, csv_path)

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.vault.invalid", 587, 30)
            self.message = None
            self.logged_in = False

        def ehlo(self):
            pass

        def starttls(self, context):
            assert context

        def login(self, user, password):
            self.logged_in = True
            assert password == "vault-password-private"

        def send_message(self, message):
            assert self.logged_in
            self.message = message
            return {}

        def quit(self):
            pass

    fake = FakeSmtp("smtp.vault.invalid", 587, 30)
    message_id = send_calendar(calendar, csv_path, _config(), smtp_factory=lambda *a, **kw: fake)
    assert message_id == fake.message["Message-ID"]
    assert len(list(fake.message.iter_attachments())) == 1

    class PartiallyRefusing(FakeSmtp):
        def send_message(self, message):
            return {"admin2@example.invalid": (550, b"refused")}

    with pytest.raises(DeliveryError, match="recusou") as rejected:
        send_calendar(calendar, csv_path, _config(), smtp_factory=lambda *a, **kw: PartiallyRefusing(*a, **kw))
    assert "admin2@example.invalid" not in str(rejected.value)
    assert "vault-password-private" not in str(rejected.value)


def test_cli_is_dry_run_by_default_and_send_checks_branch_and_digest(tmp_path: Path, monkeypatch, capsys):
    calendar = _calendar()
    monkeypatch.setattr(
        run.gsc,
        "collect",
        lambda **kwargs: gsc.CollectionResult(calendar.window_start, calendar.window_end, 5, ()),
    )
    output = tmp_path / "calendar.csv"
    monkeypatch.setattr(run, "write_csv", lambda value, path: write_csv(value, path))
    monkeypatch.setattr(run, "build_calendar", lambda collection, **kwargs: calendar)
    assert run.main(["--csv", str(output)]) == 0
    assert output.exists()
    assert "Dry-run" in capsys.readouterr().out

    monkeypatch.setattr(run, "current_branch", lambda: "master")
    assert run.main(["--csv", str(output), "--send", "--confirm-digest", calendar.input_digest]) == 2
    assert "branch" in capsys.readouterr().err

    monkeypatch.setattr(run, "current_branch", lambda: "darkfac/m1-seo")
    monkeypatch.setenv("MDL_SMTP_HOST", "should-not-be-read-on-wrong-digest")
    assert run.main(["--csv", str(output), "--send", "--confirm-digest", "0" * 64]) == 2
    assert "digest" in capsys.readouterr().err


def test_delivery_audit_contains_only_timestamp_digest_and_message_id(tmp_path: Path):
    path = tmp_path / "deliveries.jsonl"
    digest = "a" * 64
    run._record_delivery(path, digest, "<id@example.invalid>")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert set(record) == {"timestamp_utc", "digest", "message_id"}
    assert record["digest"] == digest
    assert record["message_id"] == "<id@example.invalid>"
    assert record["timestamp_utc"].endswith("+00:00")
