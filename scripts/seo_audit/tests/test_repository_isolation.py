"""A auditoria fica versionada fora do site publicado e fora do deploy."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "deploy-hostinger.yml"
GITIGNORE = REPO / ".gitignore"

TRACKED_AUDIT_PATHS = (
    "scripts/seo_audit/__init__.py",
    "scripts/seo_audit/requirements.txt",
    "scripts/seo_audit/secret_source.py",
    "scripts/seo_audit/tests/test_secret_source.py",
    "scripts/seo_audit/tests/test_repository_isolation.py",
)
IGNORED_SCRIPT_PATHS = (
    "scripts/other_tool/run.py",
    "scripts/seo_audit_backup/secret_source.py",
    "scripts/readme.txt",
    "03-scripts/foo.py",
)


def _is_ignored(relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise AssertionError(result.stderr or result.stdout or result.returncode)


class RepositoryIsolationTests(unittest.TestCase):
    def test_gitignore_versions_only_the_seo_audit(self) -> None:
        text = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn("scripts/**", text)
        self.assertIn("!scripts/seo_audit/", text)
        self.assertIn("!scripts/seo_audit/**", text)
        self.assertIn("03-scripts/", text)
        for relative in TRACKED_AUDIT_PATHS:
            with self.subTest(path=relative):
                self.assertTrue((REPO / relative).is_file(), relative)
                self.assertFalse(_is_ignored(relative), relative)
        for relative in IGNORED_SCRIPT_PATHS:
            with self.subTest(path=relative):
                self.assertTrue(_is_ignored(relative), relative)

    def test_deploy_workflow_still_excludes_scripts(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("**/scripts/**", text)
        self.assertNotIn("!scripts/seo_audit", text)
        self.assertNotIn("!**/scripts", text)
        exclude = text.split("exclude:", 1)[1]
        self.assertIn("**/scripts/**", exclude)
        self.assertIn("**/03-scripts/**", exclude)


if __name__ == "__main__":
    unittest.main()
