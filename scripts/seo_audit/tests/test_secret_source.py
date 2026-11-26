"""Fronteira de segredo: so core.line.pilot_secrets, erro fechado e sanitizado."""

from __future__ import annotations

import inspect
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator
from unittest import mock

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import secret_source

CANARY = "CANARY-SECRET-FRAGMENT-9f3c1a"
SECRET_KEY = "MANSAODOLAGO_SEARCH_CONSOLE_CREDENTIALS_JSON"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
FAKE_KEY = "-----BEGIN PRIVATE KEY-----\n" + CANARY + "\n-----END PRIVATE KEY-----\n"


class PilotSecretMissingError(RuntimeError):
    def __init__(self, key: str) -> None:
        super().__init__(CANARY + " ausente " + key)
        self.key = key


def _service_account(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": "service_account",
        "project_id": "mansao-seo",
        "private_key_id": "kid-1",
        "private_key": FAKE_KEY,
        "client_email": "seo-audit@mansao-seo.iam.gserviceaccount.com",
        "client_id": "1234567890",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    data.update(overrides)
    return data


def _pilot_module(require: Any) -> ModuleType:
    module = ModuleType("core.line.pilot_secrets")
    module.MANSAODOLAGO_SEARCH_CONSOLE_KEY = SECRET_KEY
    module.PilotSecretMissingError = PilotSecretMissingError
    module.require_pilot_secret = require
    return module


@contextmanager
def installed_pilot(module: ModuleType | None) -> Iterator[None]:
    """Substitui core.line.pilot_secrets sem tocar no cofre real."""
    names = [name for name in list(sys.modules) if name == "core" or name.startswith("core.")]
    saved = {name: sys.modules.pop(name) for name in names}
    try:
        if module is None:
            sys.modules["core"] = None  # type: ignore[assignment]
        else:
            core = ModuleType("core")
            line = ModuleType("core.line")
            core.__path__ = []  # type: ignore[attr-defined]
            line.__path__ = []  # type: ignore[attr-defined]
            core.line = line  # type: ignore[attr-defined]
            line.pilot_secrets = module  # type: ignore[attr-defined]
            sys.modules["core"] = core
            sys.modules["core.line"] = line
            sys.modules["core.line.pilot_secrets"] = module
        yield
    finally:
        for name in list(sys.modules):
            if name == "core" or name.startswith("core."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class SecretSourceTests(unittest.TestCase):
    def assert_sanitized(self, exc: BaseException, *extra: str) -> None:
        chunks = [
            str(exc),
            repr(exc.args),
            str(exc.__cause__),
            str(exc.__context__),
            *extra,
        ]
        blob = "\n".join(chunks)
        self.assertNotIn(CANARY, blob)
        self.assertIsNone(exc.__cause__)
        self.assertIsNone(exc.__context__)

    def test_signature_has_no_secret_channel(self) -> None:
        signature = inspect.signature(secret_source.load_credentials_json)
        self.assertEqual(list(signature.parameters), [])
        source = Path(secret_source.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "os.environ",
            "getenv",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "dotenv",
            "secrets_vault",
            "open(",
            "Path(",
            "read_text",
            "argparse",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("require_pilot_secret", source)
        self.assertIn("from core.line import pilot_secrets", source)
        scopes = set(
            re.findall(r"https://www\.googleapis\.com/auth/[A-Za-z0-9._-]+", source)
        )
        self.assertEqual(scopes, {SCOPE})
        self.assertEqual(secret_source.SEARCH_CONSOLE_SCOPE, SCOPE)
        self.assertEqual(secret_source.authorized_scopes(), (SCOPE,))

    def test_missing_module_is_closed_and_sanitized(self) -> None:
        with installed_pilot(None):
            with self.assertRaises(secret_source.SecretSourceError) as caught:
                secret_source.load_credentials_json()
        exc = caught.exception
        self.assertNotEqual(exc.exit_code, 0)
        self.assertIn("indisponivel", str(exc))
        self.assert_sanitized(exc)

    def test_incomplete_public_api_is_closed(self) -> None:
        module = ModuleType("core.line.pilot_secrets")
        module.MANSAODOLAGO_SEARCH_CONSOLE_KEY = "OUTRA_CHAVE"
        with installed_pilot(module):
            with self.assertRaises(secret_source.SecretSourceError) as caught:
                secret_source.load_credentials_json()
        self.assertNotEqual(caught.exception.exit_code, 0)
        self.assert_sanitized(caught.exception)

    def test_missing_secret_does_not_fall_back(self) -> None:
        calls: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

        def require_pilot_secret(key: str, *args: Any, **kwargs: Any) -> str:
            calls.append((key, args, kwargs))
            raise PilotSecretMissingError(key)

        env_payload = json.dumps(_service_account(client_email="env-" + CANARY + "@x.test"))
        with tempfile.TemporaryDirectory() as tmp:
            secret_file = Path(tmp) / "credentials.json"
            secret_file.write_text(
                json.dumps(_service_account(client_email="file-" + CANARY + "@x.test")),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    SECRET_KEY: env_payload,
                    "GOOGLE_APPLICATION_CREDENTIALS": str(secret_file),
                },
                clear=False,
            ):
                with installed_pilot(_pilot_module(require_pilot_secret)):
                    with self.assertRaises(secret_source.SecretSourceError) as caught:
                        secret_source.load_credentials_json()
        exc = caught.exception
        self.assertNotEqual(exc.exit_code, 0)
        self.assertIn(SECRET_KEY, str(exc))
        self.assert_sanitized(exc)
        self.assertEqual(calls, [(SECRET_KEY, (), {})])

    def test_unexpected_vault_error_is_sanitized(self) -> None:
        def require_pilot_secret(key: str) -> str:
            raise RuntimeError("vault exploded " + CANARY)

        with installed_pilot(_pilot_module(require_pilot_secret)):
            with self.assertRaises(secret_source.SecretSourceError) as caught:
                secret_source.load_credentials_json()
        exc = caught.exception
        self.assertEqual(str(exc), "falha ao ler o segredo do piloto")
        self.assertNotEqual(exc.exit_code, 0)
        self.assert_sanitized(exc)

    def test_invalid_json_is_sanitized(self) -> None:
        raw = "{nao-json " + CANARY + " -----BEGIN PRIVATE KEY-----"

        def require_pilot_secret(key: str) -> str:
            return raw

        with installed_pilot(_pilot_module(require_pilot_secret)):
            with self.assertRaises(secret_source.SecretSourceError) as caught:
                secret_source.load_credentials_json()
        exc = caught.exception
        self.assertEqual(str(exc), "credencial do Search Console nao e JSON valido")
        self.assertNotEqual(exc.exit_code, 0)
        self.assert_sanitized(exc)

    def test_incompatible_shapes_are_sanitized(self) -> None:
        samples = [
            json.dumps([CANARY]),
            json.dumps("apenas-texto-" + CANARY),
            json.dumps({"type": "authorized_user", "client_id": CANARY}),
            json.dumps(_service_account(private_key="sem-material-" + CANARY)),
            json.dumps(_service_account(client_email=CANARY)),
            json.dumps(
                _service_account(
                    scopes=["https://www.googleapis.com/auth/webmasters", CANARY]
                )
            ),
            json.dumps(
                _service_account(scopes=["https://www.googleapis.com/auth/webmasters"])
            ),
        ]
        for raw in samples:
            with self.subTest(raw=raw[:40]):
                def require_pilot_secret(key: str, payload: str = raw) -> str:
                    return payload

                with installed_pilot(_pilot_module(require_pilot_secret)):
                    with self.assertRaises(secret_source.SecretSourceError) as caught:
                        secret_source.load_credentials_json()
                exc = caught.exception
                self.assertEqual(
                    str(exc), "credencial do Search Console tem estrutura incompativel"
                )
                self.assertNotEqual(exc.exit_code, 0)
                self.assert_sanitized(exc)

    def test_valid_credential_uses_only_readonly_scope(self) -> None:
        payload = _service_account()

        def require_pilot_secret(key: str) -> str:
            self.assertEqual(key, SECRET_KEY)
            return json.dumps(payload)

        with installed_pilot(_pilot_module(require_pilot_secret)):
            loaded = secret_source.load_credentials_json()
        self.assertEqual(loaded["type"], "service_account")
        self.assertEqual(loaded["client_email"], payload["client_email"])
        self.assertEqual(loaded["private_key"], payload["private_key"])
        self.assertNotIn("scopes", loaded)
        self.assertEqual(secret_source.authorized_scopes(), (SCOPE,))

    def test_explicit_readonly_scope_is_accepted(self) -> None:
        for scopes in (SCOPE, [SCOPE]):
            with self.subTest(scopes=scopes):
                payload = _service_account(scopes=scopes)

                def require_pilot_secret(key: str, body: dict[str, Any] = payload) -> str:
                    return json.dumps(body)

                with installed_pilot(_pilot_module(require_pilot_secret)):
                    loaded = secret_source.load_credentials_json()
                self.assertEqual(loaded["scopes"], scopes)

    def test_main_missing_secret_exits_nonzero_without_leak(self) -> None:
        def require_pilot_secret(key: str) -> str:
            raise PilotSecretMissingError(key)

        stderr = io.StringIO()
        with installed_pilot(_pilot_module(require_pilot_secret)):
            with mock.patch("sys.stderr", stderr):
                code = secret_source.main([])
        self.assertNotEqual(code, 0)
        self.assertNotIn(CANARY, stderr.getvalue())
        self.assertIn(SECRET_KEY, stderr.getvalue())

    def test_main_rejects_arguments_without_reading_them(self) -> None:
        def require_pilot_secret(key: str) -> str:
            raise AssertionError("cofre nao deveria ser lido quando ha argumento")

        stderr = io.StringIO()
        with installed_pilot(_pilot_module(require_pilot_secret)):
            with mock.patch("sys.stderr", stderr):
                code = secret_source.main(["--credentials", CANARY])
        self.assertEqual(code, 2)
        self.assertNotIn(CANARY, stderr.getvalue())

    def test_main_success_does_not_print_secret(self) -> None:
        payload = _service_account()

        def require_pilot_secret(key: str) -> str:
            return json.dumps(payload)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with installed_pilot(_pilot_module(require_pilot_secret)):
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                code = secret_source.main([])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "credencial do Search Console carregada\n")
        self.assertNotIn(CANARY, stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("PRIVATE KEY", stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
