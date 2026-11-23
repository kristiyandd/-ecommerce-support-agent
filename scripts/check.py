"""Run the full quality gate: lint, format, layer contracts, types, tests, coverage, secret scan, dependency audit."""

import logging
import subprocess
import sys

COVERAGE_THRESHOLD = 85
GATED_PACKAGES = (
    "src/support_agent/domain/*",
    "src/support_agent/policy/*",
    "src/support_agent/application/*",
)
LINT_IMPORTS = "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())"

logger = logging.getLogger("check")

Step = tuple[str, tuple[str, ...]]

STEPS: tuple[Step, ...] = (
    ("ruff check", ("-m", "ruff", "check", ".")),
    ("ruff format", ("-m", "ruff", "format", "--check", ".")),
    ("import contracts", ("-c", LINT_IMPORTS)),
    ("mypy", ("-m", "mypy")),
    ("pytest", ("-m", "pytest", "--cov", "--cov-report=term-missing")),
    (
        "coverage gate",
        ("-m", "coverage", "report", f"--include={','.join(GATED_PACKAGES)}", f"--fail-under={COVERAGE_THRESHOLD}"),
    ),
    ("secret scan", ("-m", "scripts.secret_scan")),
    ("dependency audit", ("-m", "pip_audit", "--skip-editable", "--progress-spinner", "off")),
)


def run_step(name: str, args: tuple[str, ...]) -> int:
    logger.info("run %s", name)
    return subprocess.run([sys.executable, *args], check=False).returncode  # noqa: S603 -- fixed argument tuples, no user input


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    for name, args in STEPS:
        code = run_step(name, args)
        if code != 0:
            logger.error("FAILED: %s (exit %d)", name, code)
            return code
    logger.info("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
