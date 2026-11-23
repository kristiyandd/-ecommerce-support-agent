import zipfile
from pathlib import Path

import pytest

from scripts.package import build_archive, files_to_archive, is_excluded, write_index


@pytest.mark.parametrize(
    "relative",
    [
        ".venv/Lib/x.py",
        "src/pkg/__pycache__/a.pyc",
        "src/ecommerce_support_agent.egg-info/PKG-INFO",
        ".env",
        ".coverage",
        ".claude/settings.local.json",
        "dist/old.zip",
    ],
)
def test_build_artifacts_secrets_and_caches_are_excluded(relative: str) -> None:
    assert is_excluded(Path(relative))


def _project(root: Path) -> Path:
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "module.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "pkg" / "__pycache__").mkdir()
    (root / "src" / "pkg" / "__pycache__" / "module.pyc").write_bytes(b"\0")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    return root


def test_archive_has_the_project_folder_as_root_and_no_excluded_files(tmp_path: Path) -> None:
    root = _project(tmp_path / "shop-project")
    archive = tmp_path / "dist" / "out.zip"

    build_archive(archive, root)

    with zipfile.ZipFile(archive) as bundle:
        assert sorted(bundle.namelist()) == ["shop-project/README.md", "shop-project/src/pkg/module.py"]
    assert [path.name for path in files_to_archive(root)] == ["module.py", "README.md"]


def test_index_lists_every_session_file_with_its_size(tmp_path: Path) -> None:
    (tmp_path / "abc.jsonl").write_bytes(b"{}\n")
    (tmp_path / "abc" / "subagents").mkdir(parents=True)
    (tmp_path / "abc" / "subagents" / "agent-1.jsonl").write_bytes(b"{}\n")

    listed = write_index(tmp_path)

    index = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert listed == 2
    assert "| abc | abc.jsonl | 3 |" in index
    assert "| abc | abc/subagents/agent-1.jsonl | 3 |" in index
