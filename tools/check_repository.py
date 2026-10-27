"""Check public source candidates and local Markdown links without printing sensitive values.

This is a targeted repository check, not a guarantee of a complete security audit.
Known local credentials are compared against source and reachable Git history.
"""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, encoding="utf-8")


def main() -> None:
    candidates = sorted(
        set(git("ls-files", "--cached", "--others", "--exclude-standard").splitlines())
    )
    failures: list[str] = []
    secrets = [
        value
        for name, value in dotenv_values(ROOT / ".env").items()
        if value
        and len(value) >= 16
        and any(token in name for token in ("PASSWORD", "SECRET", "API_KEY", "ACCESS_TOKEN"))
    ]
    secret_patterns = [
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"sk-(?:proj-)?[A-Za-z0-9_-]{30,}",
        r"gh[pousr]_[A-Za-z0-9]{30,}",
    ]
    for name in candidates:
        path = ROOT / name
        if not path.is_file():
            continue
        if path.suffix in {".parquet", ".xlsx", ".pdf", ".db", ".dump"} and not name.startswith(
            "tests/fixtures/"
        ):
            failures.append(f"Unexpected binary/runtime candidate: {name}")
        if name == ".env" or name.startswith(("runtime/", "private/", "internal/")):
            failures.append(f"Private/runtime source candidate: {name}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(secret in content for secret in secrets) or any(
            re.search(pattern, content) for pattern in secret_patterns
        ):
            failures.append(f"Possible credential in {name}")
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
                target = unquote(target.strip("<> ")).split("#", 1)[0]
                if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                    continue
                if not (path.parent / target).exists():
                    failures.append(f"Missing Markdown link in {name}: {target}")
    history = git("log", "--all", "-p", "--format=fuller")
    if any(secret in history for secret in secrets):
        failures.append("A local credential appears in reachable Git history")
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"PASS: {len(candidates)} source candidates; "
        "known credential/history and Markdown path checks"
    )


if __name__ == "__main__":
    main()
