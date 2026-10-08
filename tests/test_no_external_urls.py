"""Fail if any runtime file mentions a URL outside the internal allowlist.

The stack must never call out. Service hostnames on the internal Docker network
and loopback are allowed; everything else is a finding. README, LICENSE and the
lockfile are documentation or package metadata and are not runtime code.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = re.compile(r"https?://([A-Za-z0-9._-]+)", re.IGNORECASE)
ALLOWED_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "0.0.0.0", "ollama", "qdrant", "vllm", "rag-api", "edge"}
)
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "bundle",
        "node_modules",
    }
)
SKIP_FILES = frozenset({"README.md", "LICENSE", "uv.lock", "test_no_external_urls.py"})
SKIP_SUFFIXES = frozenset({".png", ".jpg", ".ico", ".pdf", ".docx", ".tar", ".gz"})


def _runtime_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
        and path.name not in SKIP_FILES
        and path.suffix not in SKIP_SUFFIXES
    ]


def _findings(files: list[Path], root: Path = ROOT) -> list[str]:
    found: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for match in URL.finditer(line):
                if match.group(1).lower() not in ALLOWED_HOSTS:
                    found.append(f"{path.relative_to(root)}:{number}: {match.group(0)}")
    return found


def test_runtime_code_references_no_external_urls() -> None:
    assert _findings(_runtime_files()) == []


def test_the_scan_actually_finds_external_urls(tmp_path: Path) -> None:
    bad = tmp_path / "x.py"
    bad.write_text('requests.get("https://api.example.com/v1")\nok = "http://ollama:11434"\n')
    assert _findings([bad], tmp_path) == ["x.py:1: https://api.example.com"]
