"""Entrypoint: destinatarios do cofre, e-mail multipart e SMTP sem vazamento."""

from __future__ import annotations

import ast
import io
import json
import os
import smtplib
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
from html import escape
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from darkfac_mailer.gsc import SearchConsoleError
from darkfac_mailer.main import (
    ENV_RECIPIENTS,
    ENV_SERVICE_ACCOUNT,
    ENV_SITE_URL,
    ENV_SMTP_FROM,
    ENV_SMTP_HOST,
    ENV_SMTP_PASSWORD,
    ENV_SMTP_PORT,
    ENV_SMTP_USERNAME,
    MailerError,
    _connect_smtp,
    _google_access_token,
    build_message,
    deliver,
    load_config,
    main,
    parse_recipients,
    run,
    subject_for,
)
from darkfac_mailer.report import (
    DimensionStat,
    PeriodStats,
    build_weekly_report,
    render_report,
)

SP = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 24, 8, 0, tzinfo=SP)
PERIOD = "2026-11-16/2026-11-22"
PASSWORD = "smtp-password-secret"
PRIVATE_KEY = "PRIVATE KEY\nNOT-A-REAL-KEY-MATERIAL"
RECIPIENTS = ("admin@example.test", "editor@example.test")
ROOT = Path(__file__).resolve().parents[1]


def _service_account(**overrides: object) -> str:
    payload: dict[str, object] = {
        "type": "service_account",
        "project_id": "example-project",
        "client_email": "report-bot@example.test",
        "private_key": PRIVATE_KEY,
        "token_uri": "https://oauth2.example.test/token",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _env(**overrides: str) -> dict[str, str]:
    env = {
        ENV_RECIPIENTS: "admin@example.test, editor@example.test",
        ENV_SERVICE_ACCOUNT: _service_account(),
        ENV_SITE_URL: "https://example.test/",
        ENV_SMTP_HOST: "smtp.example.test",
        ENV_SMTP_PORT: "587",
        ENV_SMTP_USERNAME: "smtp-user",
        ENV_SMTP_PASSWORD: PASSWORD,
        ENV_SMTP_FROM: "seo@example.test",
    }
    env.update(overrides)
    return env


def _periods() -> tuple[PeriodStats, PeriodStats]:
    current = PeriodStats(
        clicks=50,
        impressions=1000,
        position=4,
        pages=(
            DimensionStat("https://example.test/a", clicks=10, impressions=100),
            DimensionStat("https://example.test/b", clicks=40, impressions=900),
        ),
        queries=(DimensionStat("casa", clicks=5, impressions=50),),
    )
    previous = PeriodStats(
        clicks=30,
        impressions=800,
        position=8,
        pages=(
            DimensionStat("https://example.test/a", clicks=25, impressions=200),
            DimensionStat("https://example.test/b", clicks=5, impressions=600),
        ),
        queries=(DimensionStat("casa", clicks=20, impressions=80),),
    )
    return current, previous


class _Source:
    def __init__(self, current: PeriodStats, previous: PeriodStats) -> None:
        self.current = current
        self.previous = previous
        self.calls: list[tuple[date, date]] = []

    def fetch_period(self, start: date, end: date) -> PeriodStats:
        self.calls.append((start, end))
        if start == date(2026, 11, 16):
            return self.current
        if start == date(2026, 11, 9):
            return self.previous
        raise AssertionError("janela inesperada")


class _Client:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.login_args: tuple[str, str] | None = None
        self.messages: list[object] = []
        self.closed = False

    def login(self, username: str, password: str) -> None:
        self.events.append("login")
        self.login_args = (username, password)

    def send_message(self, message: object) -> None:
        self.events.append("send")
        self.messages.append(message)

    def quit(self) -> None:
        self.events.append("quit")

    def close(self) -> None:
        self.events.append("close")
        self.closed = True


class MailerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch(
            "socket.create_connection", side_effect=AssertionError("rede")
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def invoke(self, env: dict[str, str] | None = None, **kwargs: object):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = run(env if env is not None else _env(), now=NOW, **kwargs)
        return code, out.getvalue(), err.getvalue()

    def payload(self, out: str) -> dict[str, object]:
        self.assertTrue(out.endswith("\n"))
        lines = out.splitlines()
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(
            set(data),
            {"event", "status", "stage", "code", "period", "recipient_count"},
        )
        return data


class RecipientTests(MailerTestCase):
    def test_comma_list_strips_edges_and_empty_slots(self) -> None:
        raw = "  admin@example.test ,  editor@example.test , "
        self.assertEqual(parse_recipients(raw), RECIPIENTS)

    def test_blank_list_is_missing_and_hides_whitespace(self) -> None:
        for raw in (None, "", "   ", ",", " , "):
            with self.subTest(raw=raw):
                with self.assertRaises(MailerError) as caught:
                    parse_recipients(raw)
                self.assertEqual(caught.exception.code, "recipients_missing")
                self.assertEqual(str(caught.exception), "recipients_missing")
                self.assertIsNone(caught.exception.__context__)

    def test_invalid_item_is_rejected_without_the_value(self) -> None:
        sentinel = "leak-target@hidden.example"
        raw = f"admin@example.test, Ops <{sentinel}>"
        with self.assertRaises(MailerError) as caught:
            parse_recipients(raw)
        self.assertEqual(caught.exception.code, "recipients_invalid")
        self.assertEqual(caught.exception.args, ("recipients_invalid",))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        rendered = str(caught.exception) + repr(caught.exception)
        self.assertNotIn(sentinel, rendered)
        self.assertNotIn("Ops", rendered)

    def test_header_injection_is_invalid_and_hidden(self) -> None:
        sentinel = "hidden-bcc@example.test"
        raw = f"admin@example.test\nBcc: {sentinel}"
        with self.assertRaises(MailerError) as caught:
            parse_recipients(raw)
        self.assertEqual(caught.exception.code, "recipients_invalid")
        self.assertNotIn(sentinel, str(caught.exception))
        self.assertNotIn("Bcc", str(caught.exception))


class ConfigTests(MailerTestCase):
    def test_runtime_names_match_the_vault_contract(self) -> None:
        self.assertEqual(ENV_RECIPIENTS, "MANSAODOLAGO_REPORT_RECIPIENTS")
        self.assertEqual(ENV_SERVICE_ACCOUNT, "GOOGLE_SERVICE_ACCOUNT_JSON")
        self.assertEqual(ENV_SITE_URL, "GSC_SITE_URL")
        self.assertEqual(ENV_SMTP_HOST, "SMTP_HOST")
        self.assertEqual(ENV_SMTP_PORT, "SMTP_PORT")
        self.assertEqual(ENV_SMTP_USERNAME, "SMTP_USERNAME")
        self.assertEqual(ENV_SMTP_PASSWORD, "SMTP_PASSWORD")
        self.assertEqual(ENV_SMTP_FROM, "SMTP_FROM")

    def test_password_spaces_are_preserved_and_repr_is_redacted(self) -> None:
        env = _env()
        env[ENV_SMTP_PASSWORD] = " spaced-secret "
        config = load_config(env)
        self.assertEqual(config.smtp_password, " spaced-secret ")
        self.assertEqual(config.recipients, RECIPIENTS)
        self.assertEqual(config.smtp_port, 587)
        blob = repr(config) + str(config)
        self.assertNotIn("spaced-secret", blob)
        self.assertNotIn("admin@example.test", blob)
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", blob)
        self.assertNotIn("report-bot@example.test", blob)
        self.assertIn("recipient_count=2", blob)

    def test_each_missing_variable_has_a_safe_code(self) -> None:
        expected = {
            ENV_RECIPIENTS: "recipients_missing",
            ENV_SERVICE_ACCOUNT: "service_account_missing",
            ENV_SITE_URL: "gsc_site_url_missing",
            ENV_SMTP_HOST: "smtp_host_missing",
            ENV_SMTP_PORT: "smtp_port_missing",
            ENV_SMTP_USERNAME: "smtp_username_missing",
            ENV_SMTP_PASSWORD: "smtp_password_missing",
            ENV_SMTP_FROM: "smtp_from_missing",
        }
        for key, code_name in expected.items():
            with self.subTest(key=key):
                env = _env()
                del env[key]
                status, out, err = self.invoke(env, connect=self._boom)
                self.assertEqual(status, 1)
                self.assertEqual(err, "")
                body = self.payload(out)
                self.assertEqual(body["status"], "failure")
                self.assertEqual(body["stage"], "config")
                self.assertEqual(body["code"], code_name)
                self.assertEqual(body["event"], "weekly_seo_report")
                self.assertEqual(body["period"], PERIOD)
                self.assertEqual(body["recipient_count"], 0)
                self.assertNotIn(PASSWORD, out)
                self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", out)

    def test_invalid_values_are_not_copied_into_the_result(self) -> None:
        account = json.loads(_service_account())
        cases = {
            "recipient": (
                {ENV_RECIPIENTS: "admin@example.test, leak-target@hidden.example\nBcc: x"},
                "recipients_invalid",
                "leak-target@hidden.example",
            ),
            "account": (
                {ENV_SERVICE_ACCOUNT: '{"private_key": "TRUNCATED-SECRET-BODY"'},
                "service_account_invalid",
                "TRUNCATED-SECRET-BODY",
            ),
            "account-email": (
                {
                    ENV_SERVICE_ACCOUNT: _service_account(
                        client_email="not-an-email-secret"
                    )
                },
                "service_account_invalid",
                "not-an-email-secret",
            ),
            "account-key": (
                {
                    ENV_SERVICE_ACCOUNT: _service_account(
                        private_key="LEAKED-KEY-BODY-WITHOUT-MARKER\n"
                    )
                },
                "service_account_invalid",
                "LEAKED-KEY-BODY-WITHOUT-MARKER",
            ),
            "account-uri": (
                {
                    ENV_SERVICE_ACCOUNT: _service_account(
                        token_uri="http://token.secret.example/leak"
                    )
                },
                "service_account_invalid",
                "token.secret.example",
            ),
            "site": (
                {ENV_SITE_URL: "https://secret.example/path\nnext"},
                "gsc_site_url_invalid",
                "secret.example",
            ),
            "host": (
                {ENV_SMTP_HOST: "bad secret-host.example"},
                "smtp_host_invalid",
                "secret-host.example",
            ),
            "port": (
                {ENV_SMTP_PORT: "65536"},
                "smtp_port_invalid",
                "65536",
            ),
            "username": (
                {ENV_SMTP_USERNAME: "smtp-user\nsecret-user-line"},
                "smtp_username_invalid",
                "secret-user-line",
            ),
            "sender": (
                {ENV_SMTP_FROM: "Ops <from-secret@hidden.example>"},
                "smtp_from_invalid",
                "from-secret@hidden.example",
            ),
        }
        for label, (updates, code_name, sentinel) in cases.items():
            with self.subTest(label=label):
                status, out, err = self.invoke(_env(**updates), connect=self._boom)
                self.assertEqual(status, 1)
                self.assertEqual(err, "")
                body = self.payload(out)
                self.assertEqual(body["code"], code_name)
                self.assertEqual(body["stage"], "config")
                self.assertEqual(body["recipient_count"], 0)
                self.assertNotIn(sentinel, out + err)
                self.assertNotIn("Traceback", out + err)
                self.assertNotIn("JSONDecodeError", out + err)
                self.assertNotIn(PASSWORD, out + err)
        self.assertIn("client_email", account)

    def test_non_string_secret_is_not_stringified(self) -> None:
        class Secret:
            def __str__(self) -> str:
                return "STRINGIFIED-SECRET"

        env = _env()
        env[ENV_SMTP_PASSWORD] = Secret()  # type: ignore[assignment]
        with self.assertRaises(MailerError) as caught:
            load_config(env)
        self.assertEqual(caught.exception.code, "smtp_password_missing")
        self.assertNotIn("STRINGIFIED-SECRET", str(caught.exception))
        self.assertIsNone(caught.exception.__context__)

    def _boom(self, host: str, port: int) -> object:
        raise AssertionError(f"smtp {host}:{port}")


class PresentationTests(MailerTestCase):
    def test_multipart_message_names_the_week_and_the_comparison(self) -> None:
        current, previous = _periods()
        report = build_weekly_report(now=NOW, current=current, previous=previous)
        message = build_message(load_config(_env()), report)
        plain, html_body = _bodies(message)

        self.assertEqual(message.get_content_type(), "multipart/alternative")
        self.assertEqual(message["Subject"], subject_for(report))
        self.assertEqual(
            message["Subject"],
            "Relatório SEO semanal 2026-11-16 a 2026-11-22",
        )
        self.assertNotIn("\n", message["Subject"])
        self.assertNotIn("\r", message["Subject"])
        self.assertEqual(message["From"], "seo@example.test")
        self.assertEqual(message["To"], "admin@example.test, editor@example.test")
        self.assertIsNone(message["Cc"])
        self.assertIsNone(message["Bcc"])
        self.assertEqual(plain.strip(), render_report(report).strip())
        self.assertIn("Semana atual: 2026-11-16 a 2026-11-22 (America/Sao_Paulo)", plain)
        self.assertIn("Semana anterior: 2026-11-09 a 2026-11-15", plain)
        self.assertIn("Cliques: atual 50, anterior 30, delta +20, melhorou", plain)
        self.assertIn("Impressões: atual 1000, anterior 800, delta +200, melhorou", plain)
        self.assertIn("CTR: atual 5.00%, anterior 3.75%, delta +1.25 pp, melhorou", plain)
        self.assertIn("Posição média: atual 4.00, anterior 8.00, delta -4.00, melhorou", plain)
        self.assertIn("Revisar página https://example.test/a", plain)
        self.assertIn('Revisar consulta "casa"', plain)
        self.assertRegex(html_body, r"Cliques.+50.+30.+\+20.+melhorou")
        self.assertRegex(html_body, r"Impressões.+1000.+800.+\+200.+melhorou")
        self.assertRegex(html_body, r"CTR.+5\.00%.+3\.75%.+\+1\.25 pp.+melhorou")
        self.assertRegex(html_body, r"Posição média.+4\.00.+8\.00.+-4\.00.+melhorou")
        self.assertIn("2026-11-16", html_body)
        self.assertIn("2026-11-22", html_body)
        self.assertIn("2026-11-09", html_body)
        self.assertIn("2026-11-15", html_body)
        self.assertIn("America/Sao_Paulo", html_body)
        first = escape(report.actions[0].message)
        second = escape(report.actions[1].message)
        self.assertLess(html_body.index(first), html_body.index(second))
        self.assertEqual(report.actions[0].key, "https://example.test/a")
        self.assertEqual(report.actions[1].key, "casa")
        self.assertNotIn(PASSWORD, plain + html_body)
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", plain + html_body)
        self.assertNotIn("admin@example.test", plain + html_body)

    def test_insufficient_sample_is_still_a_complete_message(self) -> None:
        report = build_weekly_report(
            now=NOW,
            current=PeriodStats(clicks=0, impressions=0),
            previous=PeriodStats(clicks=0, impressions=0),
        )
        plain, html_body = _bodies(build_message(load_config(_env()), report))
        self.assertIn("amostra insuficiente", plain)
        self.assertIn("amostra insuficiente", html_body)
        self.assertIn(PERIOD[:10], message_subject(plain, report))


class DeliveryTests(MailerTestCase):
    def test_success_sends_once_over_smtp_and_exits_zero(self) -> None:
        current, previous = _periods()
        source = _Source(current, previous)
        client = _Client()
        targets: list[tuple[str, int]] = []
        token_calls: list[object] = []

        def connect(host: str, port: int) -> _Client:
            targets.append((host, port))
            return client

        def loader(info: object) -> str:
            token_calls.append(info)
            return "nao-deve-rodar"

        code, out, err = self.invoke(source=source, connect=connect, token_loader=loader)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(
            self.payload(out),
            {
                "event": "weekly_seo_report",
                "status": "success",
                "stage": "send",
                "code": "sent",
                "period": PERIOD,
                "recipient_count": 2,
            },
        )
        self.assertEqual(targets, [("smtp.example.test", 587)])
        self.assertEqual(client.events, ["login", "send", "quit"])
        self.assertEqual(client.login_args, ("smtp-user", PASSWORD))
        self.assertEqual(token_calls, [])
        self.assertEqual(
            source.calls,
            [
                (date(2026, 11, 16), date(2026, 11, 22)),
                (date(2026, 11, 9), date(2026, 11, 15)),
            ],
        )
        message = client.messages[0]
        self.assertEqual(message["Subject"], "Relatório SEO semanal 2026-11-16 a 2026-11-22")
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("admin@example.test", out + err)
        self.assertNotIn("editor@example.test", out + err)
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", out + err)
        self.assertNotIn("report-bot@example.test", out + err)
        self.assertNotIn("smtp-user", out + err)

    def test_token_is_sent_only_to_search_console(self) -> None:
        seen: list[str] = []

        def transport(url: str, payload: dict, headers: dict) -> dict:
            del url, payload
            seen.append(headers["Authorization"])
            return {"rows": []}

        def loader(info: dict) -> str:
            self.assertIn("NOT-A-REAL-KEY-MATERIAL", info["private_key"])
            return "injected-access-token"

        client = _Client()
        code, out, err = self.invoke(
            token_loader=loader,
            transport=transport,
            connect=lambda host, port: client,
        )
        self.assertEqual(code, 0)
        self.assertEqual(seen, ["Bearer injected-access-token"] * 6)
        self.assertNotIn("injected-access-token", out + err)
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", out + err)
        self.assertEqual(len(client.messages), 1)

    def test_collect_failure_is_structured_and_skips_smtp(self) -> None:
        class Broken:
            def fetch_period(self, start: date, end: date) -> PeriodStats:
                del start, end
                raise RuntimeError("RAW-COLLECT " + PRIVATE_KEY)

        called: list[tuple[str, int]] = []

        def connect(host: str, port: int) -> _Client:
            called.append((host, port))
            return _Client()

        code, out, err = self.invoke(source=Broken(), connect=connect)
        self.assertEqual(code, 1)
        self.assertEqual(called, [])
        self.assertEqual(err, "")
        body = self.payload(out)
        self.assertEqual(body["status"], "failure")
        self.assertEqual(body["stage"], "collect")
        self.assertEqual(body["code"], "collect_failed")
        self.assertEqual(body["period"], PERIOD)
        self.assertEqual(body["recipient_count"], 2)
        self.assertNotIn("RAW-COLLECT", out + err)
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", out + err)
        self.assertNotIn("Traceback", out + err)
        self.assertNotIn(PASSWORD, out + err)

    def test_search_console_code_is_kept_without_status_text(self) -> None:
        class Coded:
            def fetch_period(self, start: date, end: date) -> PeriodStats:
                del start, end
                raise SearchConsoleError("gsc_request_failed", status=503)

        code, out, err = self.invoke(source=Coded(), connect=lambda host, port: _Client())
        self.assertEqual(code, 1)
        body = self.payload(out)
        self.assertEqual(body["code"], "gsc_request_failed")
        self.assertEqual(body["stage"], "collect")
        self.assertNotIn("status=503", out + err)
        self.assertNotIn("503", out + err)

    def test_token_loader_exception_does_not_reach_the_log(self) -> None:
        def loader(info: dict) -> str:
            raise RuntimeError("RAW-TOKEN " + info["private_key"])

        code, out, err = self.invoke(token_loader=loader, connect=lambda host, port: _Client())
        self.assertEqual(code, 1)
        body = self.payload(out)
        self.assertEqual(body["code"], "gsc_credentials_invalid")
        self.assertEqual(body["stage"], "collect")
        self.assertNotIn("RAW-TOKEN", out + err)
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", out + err)
        self.assertNotIn("Traceback", out + err)

    def test_send_failure_hides_the_server_reply(self) -> None:
        current, previous = _periods()
        client = _Client()

        def login(username: str, password: str) -> None:
            client.events.append("login")
            raise smtplib.SMTPAuthenticationError(
                535, b"AUTH-RAW-BODY " + password.encode("utf-8")
            )

        def quit_client() -> None:
            client.events.append("quit")
            raise RuntimeError("quit raw " + PASSWORD)

        client.login = login  # type: ignore[method-assign]
        client.quit = quit_client  # type: ignore[method-assign]
        code, out, err = self.invoke(
            source=_Source(current, previous),
            connect=lambda host, port: client,
        )
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        body = self.payload(out)
        self.assertEqual(body["status"], "failure")
        self.assertEqual(body["stage"], "send")
        self.assertEqual(body["code"], "smtp_send_failed")
        self.assertEqual(body["recipient_count"], 2)
        self.assertEqual(body["period"], PERIOD)
        self.assertEqual(client.events, ["login", "quit", "close"])
        self.assertNotIn("AUTH-RAW-BODY", out + err)
        self.assertNotIn("quit raw", out + err)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("admin@example.test", out + err)
        self.assertNotIn("SMTPAuthenticationError", out + err)
        self.assertNotIn("Traceback", out + err)

    def test_deliver_exception_has_no_context(self) -> None:
        client = _Client()

        def login(username: str, password: str) -> None:
            raise OSError("socket raw " + password + username)

        client.login = login  # type: ignore[method-assign]
        config = load_config(_env())
        report = build_weekly_report(
            now=NOW,
            current=_periods()[0],
            previous=_periods()[1],
        )
        with self.assertRaises(MailerError) as caught:
            deliver(config, build_message(config, report), connect=lambda host, port: client)
        self.assertEqual(caught.exception.code, "smtp_send_failed")
        self.assertEqual(caught.exception.stage, "send")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(PASSWORD, str(caught.exception) + repr(caught.exception))
        self.assertNotIn("socket raw", str(caught.exception))

    def test_render_exception_is_hidden_and_does_not_send(self) -> None:
        called: list[tuple[str, int]] = []

        def connect(host: str, port: int) -> _Client:
            called.append((host, port))
            return _Client()

        with mock.patch(
            "darkfac_mailer.main._render_html",
            side_effect=RuntimeError("RAW-RENDER secret-template"),
        ):
            code, out, err = self.invoke(source=_Source(*_periods()), connect=connect)
        self.assertEqual(code, 1)
        self.assertEqual(called, [])
        body = self.payload(out)
        self.assertEqual(body["stage"], "render")
        self.assertEqual(body["code"], "render_failed")
        self.assertNotIn("RAW-RENDER", out + err)
        self.assertNotIn("secret-template", out + err)

    def test_submission_port_starts_tls_and_implicit_port_does_not(self) -> None:
        client = mock.Mock()
        with mock.patch("darkfac_mailer.main.smtplib.SMTP", return_value=client) as smtp, \
                mock.patch("darkfac_mailer.main.smtplib.SMTP_SSL") as ssl:
            result = _connect_smtp("smtp.example.test", 587)
        smtp.assert_called_once_with("smtp.example.test", 587, timeout=30)
        self.assertEqual(client.ehlo.call_count, 2)
        client.starttls.assert_called_once_with()
        ssl.assert_not_called()
        self.assertIs(result, client)

        secure = mock.Mock()
        with mock.patch("darkfac_mailer.main.smtplib.SMTP_SSL", return_value=secure) as ssl, \
                mock.patch("darkfac_mailer.main.smtplib.SMTP") as smtp:
            result = _connect_smtp("smtp.example.test", 465)
        ssl.assert_called_once_with("smtp.example.test", 465, timeout=30)
        smtp.assert_not_called()
        secure.starttls.assert_not_called()
        self.assertIs(result, secure)

    def test_main_ignores_argv_and_hides_unexpected_text(self) -> None:
        leak = "argv-only@hidden.example"
        env = _env()
        del env[ENV_RECIPIENTS]
        out = io.StringIO()
        err = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True):
            with redirect_stdout(out), redirect_stderr(err):
                code = main([leak])
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn(leak, out.getvalue())
        self.assertEqual(json.loads(out.getvalue())["code"], "recipients_missing")

        out = io.StringIO()
        err = io.StringIO()
        with mock.patch("darkfac_mailer.main.run", side_effect=RuntimeError("LEAK-MAIN-RAW")):
            with redirect_stdout(out), redirect_stderr(err):
                code = main()
        self.assertEqual(code, 1)
        self.assertNotIn("LEAK-MAIN-RAW", out.getvalue() + err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertEqual(json.loads(out.getvalue())["code"], "unexpected_error")


class TokenLoaderTests(MailerTestCase):
    def test_missing_library_is_a_structured_credential_error(self) -> None:
        blocked = {
            "google": None,
            "google.oauth2": None,
            "google.oauth2.service_account": None,
        }
        with mock.patch.dict(sys.modules, blocked):
            with self.assertRaises(MailerError) as caught:
                _google_access_token(json.loads(_service_account()))
        self.assertEqual(caught.exception.code, "gsc_credentials_invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", str(caught.exception))

    def test_refresh_uses_the_read_only_scope_and_hides_failures(self) -> None:
        info = json.loads(_service_account())
        seen: dict[str, object] = {}

        class Credentials:
            token = "access-token-test"

            @staticmethod
            def from_service_account_info(payload: dict, scopes: list[str] | None = None):
                seen["email"] = payload["client_email"]
                seen["scopes"] = list(scopes or [])
                return Credentials()

            def refresh(self, request: object) -> None:
                seen["request"] = type(request).__name__

        self.assertEqual(self._load(Credentials, info), "access-token-test")
        self.assertEqual(
            seen["scopes"],
            ["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        self.assertEqual(seen["email"], "report-bot@example.test")
        self.assertEqual(seen["request"], "_UrllibAuthRequest")

        class BrokenCredentials:
            @staticmethod
            def from_service_account_info(payload: dict, scopes: list[str] | None = None):
                del scopes
                raise RuntimeError("refresh leaked " + payload["private_key"])

            def refresh(self, request: object) -> None:
                del request

        with self.assertRaises(MailerError) as caught:
            self._load(BrokenCredentials, info)
        self.assertEqual(caught.exception.code, "gsc_credentials_invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn("refresh leaked", str(caught.exception))
        self.assertNotIn("NOT-A-REAL-KEY-MATERIAL", str(caught.exception))

    def _load(self, credentials: type, info: dict) -> str:
        module = types.ModuleType("google.oauth2.service_account")
        module.Credentials = credentials  # type: ignore[attr-defined]
        oauth2 = types.ModuleType("google.oauth2")
        oauth2.service_account = module  # type: ignore[attr-defined]
        google = types.ModuleType("google")
        google.oauth2 = oauth2  # type: ignore[attr-defined]
        with mock.patch.dict(
            sys.modules,
            {
                "google": google,
                "google.oauth2": oauth2,
                "google.oauth2.service_account": module,
            },
        ):
            return _google_access_token(info)


class SourceHygieneTests(MailerTestCase):
    def test_package_has_no_chat_destination_or_import_time_env_lookup(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "weekly_seo.html").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        package = (ROOT / "__init__.py").read_text(encoding="utf-8")
        combined = "\n".join((main_source, template, requirements, package)).lower()
        for needle in ("telegram", "discord", "slack", "webhook", "mansaodolago.com"):
            self.assertNotIn(needle, combined)
        self.assertNotIn("@", template)
        self.assertNotIn("@", requirements)
        self.assertIn("google-auth", requirements)

        tree = ast.parse(main_source)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            self.assertNotIn("environ", ast.dump(node))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotEqual(node.func.id, "print")
        allowed = {
            "__future__",
            "json",
            "os",
            "re",
            "smtplib",
            "sys",
            "warnings",
            "collections.abc",
            "dataclasses",
            "datetime",
            "email.message",
            "html",
            "pathlib",
            "typing",
            "urllib",
            "darkfac_mailer.gsc",
            "darkfac_mailer.report",
            "google.oauth2",
        }
        self.assertTrue(set(imported) <= allowed)

    def test_template_slots_cover_the_report(self) -> None:
        text = (ROOT / "templates" / "weekly_seo.html").read_text(encoding="utf-8")
        for slot in (
            "current_start",
            "current_end",
            "previous_start",
            "previous_end",
            "metric_rows",
            "actions_html",
        ):
            self.assertIn("{{" + slot + "}}", text)


def _bodies(message: object) -> tuple[str, str]:
    plain = ""
    html_body = ""
    for part in message.walk():
        if part.get_content_type() == "text/plain":
            plain = part.get_content()
        elif part.get_content_type() == "text/html":
            html_body = part.get_content()
    return plain, html_body


def message_subject(plain: str, report: object) -> str:
    del plain
    return subject_for(report)


if __name__ == "__main__":
    unittest.main()
