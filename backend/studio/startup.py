"""Migrate once, seed the local principal, invalidate deployment proof, then serve API."""

import os
import secrets

from alembic import command
from alembic.config import Config

from studio.access import seed_demo
from studio.config import settings
from studio.database import SessionFactory


def main() -> None:
    secret = settings.session_secret.get_secret_value()
    if len(secret) < 32 or secret.startswith("replace-"):
        raise RuntimeError("SESSION_SECRET must be a random secret of at least 32 characters")
    command.upgrade(Config("alembic.ini"), "head")
    with SessionFactory() as db:
        seed_demo(db)
    settings.instance_path.parent.mkdir(parents=True, exist_ok=True)
    settings.instance_path.write_text(secrets.token_urlsafe(32))
    settings.demo_proof_path.unlink(missing_ok=True)
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "studio.api:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-proxy-headers",
            "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
