"""Carrega a credencial do Search Console somente pelo cofre do piloto.

A unica fonte e ``core.line.pilot_secrets.require_pilot_secret``. Nao ha
leitura de ambiente, arquivo local nem argumento. O escopo autorizado e
exclusivamente ``https://www.googleapis.com/auth/webmasters.readonly``.
"""

from __future__ import annotations

import json
import sys
from typing import Any

SECRET_KEY = "MANSAODOLAGO_SEARCH_CONSOLE_CREDENTIALS_JSON"
SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

_REQUIRED_FIELDS = (
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "client_id",
    "token_uri",
)
_INVALID = object()


class SecretSourceError(RuntimeError):
    """Falha fechada. A mensagem nunca contem material do segredo."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        if exit_code == 0:
            exit_code = 1
        super().__init__(message)
        self.exit_code = exit_code


def authorized_scopes() -> tuple[str, ...]:
    """Unico escopo Google que esta ferramenta pode pedir."""
    return (SEARCH_CONSOLE_SCOPE,)


def load_credentials_json() -> dict[str, Any]:
    """Devolve o JSON da credencial ja validado.

    Nao aceita caminho, texto nem variavel: o valor sai so do cofre.
    """
    module = _import_pilot_secrets()
    raw = _read_secret(module)
    return _parse_credentials(raw)


def main(argv: list[str] | None = None) -> int:
    """Confirma que a credencial carrega. Nao imprime o segredo."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(
            "argumentos nao sao aceitos; a credencial vem somente do cofre do piloto",
            file=sys.stderr,
        )
        return 2
    try:
        load_credentials_json()
    except SecretSourceError as exc:
        print(str(exc), file=sys.stderr)
        code = exc.exit_code
        return code if code else 1
    print("credencial do Search Console carregada")
    return 0


def _import_pilot_secrets() -> Any:
    module: Any = _INVALID
    try:
        # Import lazy: modulo ausente vira erro sanitizado, nao traceback de boot.
        from core.line import pilot_secrets as module
    except ImportError:
        module = _INVALID
    if module is _INVALID:
        raise SecretSourceError("modulo de segredos do piloto indisponivel")
    key = getattr(module, "MANSAODOLAGO_SEARCH_CONSOLE_KEY", None)
    require = getattr(module, "require_pilot_secret", None)
    missing_error = getattr(module, "PilotSecretMissingError", None)
    api_ok = (
        key == SECRET_KEY
        and callable(require)
        and isinstance(missing_error, type)
        and issubclass(missing_error, BaseException)
    )
    if not api_ok:
        raise SecretSourceError("modulo de segredos do piloto indisponivel")
    return module


def _read_secret(module: Any) -> str:
    raw: Any = _INVALID
    missing = False
    failed = False
    try:
        raw = module.require_pilot_secret(module.MANSAODOLAGO_SEARCH_CONSOLE_KEY)
    except module.PilotSecretMissingError:
        missing = True
    except Exception:
        failed = True
    if missing:
        raise SecretSourceError("segredo do piloto ausente no cofre: " + SECRET_KEY)
    if failed or raw is _INVALID:
        raise SecretSourceError("falha ao ler o segredo do piloto")
    if isinstance(raw, bytes):
        text: Any = _INVALID
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = _INVALID
        if text is _INVALID:
            raise SecretSourceError("credencial do Search Console nao e JSON valido")
        raw = text
    if isinstance(raw, str) and raw.strip() == "":
        raise SecretSourceError("segredo do piloto ausente no cofre: " + SECRET_KEY)
    if not isinstance(raw, str):
        raise SecretSourceError("credencial do Search Console tem estrutura incompativel")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    return raw


def _parse_credentials(raw: str) -> dict[str, Any]:
    data: Any = _INVALID
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = _INVALID
    if data is _INVALID:
        raise SecretSourceError("credencial do Search Console nao e JSON valido")
    if not isinstance(data, dict):
        raise SecretSourceError("credencial do Search Console tem estrutura incompativel")
    if data.get("type") != "service_account":
        raise SecretSourceError("credencial do Search Console tem estrutura incompativel")
    for field in _REQUIRED_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or value.strip() == "":
            raise SecretSourceError("credencial do Search Console tem estrutura incompativel")
    email = data["client_email"].strip()
    if email.count("@") != 1 or email.startswith("@") or email.endswith("@"):
        raise SecretSourceError("credencial do Search Console tem estrutura incompativel")
    if "PRIVATE KEY" not in data["private_key"]:
        raise SecretSourceError("credencial do Search Console tem estrutura incompativel")
    if not _scopes_are_authorized(data):
        raise SecretSourceError("credencial do Search Console tem estrutura incompativel")
    return dict(data)


def _scopes_are_authorized(data: dict[str, Any]) -> bool:
    if "scopes" not in data:
        return True
    scopes = data["scopes"]
    only = SEARCH_CONSOLE_SCOPE
    if isinstance(scopes, str):
        return scopes == only
    if isinstance(scopes, list) and len(scopes) == 1 and scopes[0] == only:
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
