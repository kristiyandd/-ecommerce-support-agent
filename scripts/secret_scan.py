"""Secret scan over source, tests, config, data, docs and transcripts; works without git (explicit file list).

Two layers: detect-secrets (entropy and known formats) on project files, and credential patterns on project
files plus the raw transcripts, which ship in the archive but are too noisy for entropy checks.
"""

import logging
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from detect_secrets.pre_commit_hook import main as detect_secrets_hook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRECTORIES = ("src", "tests", "scripts", "mock_env", "config", "data", "docs")
TRANSCRIPTS_DIRECTORY = "claude-transcripts"
SCANNED_ROOT_FILES = (
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    ".env.example",
    ".pre-commit-config.yaml",
)
SCANNED_SUFFIXES = frozenset({".py", ".json", ".jsonl", ".md", ".toml", ".txt", ".yaml", ".yml", ".example"})
SKIPPED_PARTS = frozenset({"__pycache__", ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache"})
CREDENTIAL_PATTERN = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{20,}|sk-(?:proj-)?[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}"
    r"|xox[abp]-[A-Za-z0-9-]{10,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
KNOWN_FAKE_VALUES = frozenset(
    {
        "AKIAIOSFODNN7EXAMPLE",  # pragma: allowlist secret
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH",  # pragma: allowlist secret
        "sk-ant-api03-Zq8xR2mT5vLw9KpN3bYc7HdF1gJs4QeUa6",  # pragma: allowlist secret
        "sk-ant-api03-abcdefABCDEF0123456789abcdefABCDEF0123456789",  # pragma: allowlist secret
        "AKIASIAIAFBASAAKAIAE",  # pragma: allowlist secret
        "AKIASIAIANBASAAKAIAE",  # pragma: allowlist secret
        "AKIAUUEQCAIRAAAAAAAA",  # pragma: allowlist secret
    }
)
"""Public documentation example, fake keys typed in this session to prove the scan works, and byte patterns
from binary files under .venv that an earlier scan printed into the session transcript."""

logger = logging.getLogger("secret_scan")


def _project_files(root: Path, directories: Iterable[str]) -> Iterator[Path]:
    for directory in directories:
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in SCANNED_SUFFIXES and not SKIPPED_PARTS & set(path.parts):
                yield path


def files_to_scan(root: Path = PROJECT_ROOT) -> Iterator[Path]:
    yield from _project_files(root, SCANNED_DIRECTORIES)
    yield from (root / name for name in SCANNED_ROOT_FILES if (root / name).is_file())


def credential_scan_files(root: Path = PROJECT_ROOT) -> Iterator[Path]:
    yield from files_to_scan(root)
    yield from _project_files(root, (TRANSCRIPTS_DIRECTORY,))


def credential_findings(paths: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        found = {match.group(0) for match in CREDENTIAL_PATTERN.finditer(text)} - KNOWN_FAKE_VALUES
        findings += [f"{path}: credential-like value {value[:12]}..." for value in sorted(found)]
    return findings


def main() -> int:
    """Exit non-zero when detect-secrets or the credential patterns find a potential secret."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    hook_result = detect_secrets_hook([str(path.relative_to(PROJECT_ROOT)) for path in files_to_scan()])
    findings = credential_findings(credential_scan_files())
    for finding in findings:
        logger.error(finding)
    return 1 if hook_result or findings else 0


if __name__ == "__main__":
    sys.exit(main())
