"""Mascara segredos em valores de URL antes de qualquer exportacao."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote_plus

REDACTED = "REDACTED"

_SENSITIVE_KEY = re.compile(r"credential|token|private[_-]?key|client[_-]?email|authorization", re.I)
_SENSITIVE_PARAM = re.compile(
    r"token|secret|passw|pwd|credential|authorization|signature|private[_-]?key"
    r"|client[_-]?email|api[_-]?key|session|jwt|^(?:key|auth|sig|code|sid)$",
    re.I,
)
# Parametro em query, fragmento ou matrix param. Vale para URL absoluta ou relativa.
_PARAM = re.compile(r"(?P<sep>&amp;|[?&#;])(?P<name>[^=&#?;\s\"'<>|`]+)=(?P<value>[^&#;\s\"'<>|`]+)")
_USERINFO = re.compile(r"//[^/?#\s\"'<>]*@")
_MAX_DECODE_DEPTH = 3


def sanitize_text(value: str, _depth: int = 0) -> str:
    """Troca por REDACTED o valor de parametros sensiveis e o userinfo de URLs."""

    def mask(match: re.Match[str]) -> str:
        name, raw = match.group("name"), match.group("value")
        hidden = bool(_SENSITIVE_PARAM.search(unquote_plus(name)))
        if not hidden and _depth < _MAX_DECODE_DEPTH:
            # URL aninhada e codificada, como ?next=https%3A%2F%2F...%3Ftoken%3Dx
            decoded = unquote_plus(raw)
            hidden = decoded != raw and sanitize_text(decoded, _depth + 1) != decoded
        if not hidden:
            return match.group(0)
        return f"{match.group('sep')}{name}={REDACTED}"

    value = _USERINFO.sub(f"//{REDACTED}@", value)
    return _PARAM.sub(mask, value)


def to_plain(value: Any) -> Any:
    """Converte para tipos JSON, remove campos sensiveis e limpa todo texto."""
    convert = getattr(value, "to_dict", None)
    if callable(convert):
        return to_plain(convert())
    if isinstance(value, dict):
        return {
            key: to_plain(item)
            for key, item in value.items()
            if not _SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, (tuple, list)):
        return [to_plain(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value
