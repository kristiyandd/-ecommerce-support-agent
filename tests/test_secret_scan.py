from pathlib import Path

from scripts.secret_scan import (
    KNOWN_FAKE_VALUES,
    PROJECT_ROOT,
    credential_findings,
    credential_scan_files,
    files_to_scan,
)


def test_scan_covers_source_config_and_docs_but_not_the_virtualenv() -> None:
    scanned = {path.relative_to(PROJECT_ROOT).parts[0] for path in files_to_scan()}

    assert {"src", "config", "docs", "tests"} <= scanned
    assert ".venv" not in scanned


def test_an_unquoted_provider_key_is_found(tmp_path: Path) -> None:
    leaked = tmp_path / "notes.txt"
    planted_key = "-".join(("sk", "ant", "api03", "x" * 32))
    leaked.write_text(f"ANTHROPIC_API_KEY={planted_key}\n", encoding="utf-8")

    assert credential_findings([leaked])


def test_documented_fake_keys_are_not_findings(tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text(" ".join(sorted(KNOWN_FAKE_VALUES)), encoding="utf-8")

    assert credential_findings([sample]) == []


def test_transcripts_are_scanned_for_credentials() -> None:
    assert any("claude-transcripts" in path.parts for path in credential_scan_files())
