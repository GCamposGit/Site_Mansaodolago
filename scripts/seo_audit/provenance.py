"""Identifica o codigo efetivamente executado: commit base e digest das fontes."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent


def source_files(root: Path = PACKAGE_DIR) -> tuple[Path, ...]:
    """Modulos da ferramenta e requirements.txt. Testes e saidas ficam fora."""
    return tuple(sorted([*root.glob("*.py"), *root.glob("requirements.txt")], key=lambda path: path.name))


def source_digest(root: Path = PACKAGE_DIR) -> dict[str, Any]:
    """SHA-256 de cada fonte (fim de linha normalizado para LF) e do conjunto.

    O digest do conjunto e o SHA-256 das linhas ``<sha256>  <nome>\\n`` em
    ordem de nome, igual em checkout LF ou CRLF.
    """
    files: dict[str, str] = {}
    for path in source_files(root):
        content = path.read_bytes().replace(b"\r\n", b"\n")
        files[path.name] = hashlib.sha256(content).hexdigest()
    manifest = "".join(f"{digest}  {name}\n" for name, digest in sorted(files.items()))
    return {
        "algorithm": "sha256-lf-manifest",
        "root": "scripts/seo_audit",
        "digest": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        "files": files,
    }


def _git(*args: str, root: Path) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def commit(root: Path = PACKAGE_DIR) -> str:
    return _git("rev-parse", "HEAD", root=root) or "unknown"


def collect_source(root: Path = PACKAGE_DIR) -> dict[str, Any]:
    """Digest das fontes e se elas sao identicas as do commit base."""
    source = source_digest(root)
    status = _git("status", "--porcelain", "--untracked-files=all", "--", *source["files"], root=root)
    source["matchesCommit"] = status == "" and commit(root) != "unknown"
    return source
