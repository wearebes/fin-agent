"""Run a separate local instance; bind Codex only to an explicitly selected account."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

import uvicorn
from pydantic import SecretStr

from fin_agent.bootstrap.app import create_app
from fin_agent.bootstrap.settings import AppSettings, load_settings
from fin_agent.storage.user_store import SQLAlchemyUserStore


def local_settings(
    data_dir: Path,
    owner: str | None = None,
    database_url: str | None = None,
) -> AppSettings:
    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_path = data_dir / "jwt.secret"
    try:
        descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(secrets.token_urlsafe(48))

    settings = load_settings()
    settings.auth.secret_key = SecretStr(secret_path.read_text(encoding="utf-8").strip())
    settings.database.backend = "sql"
    settings.database.url = database_url or f"sqlite:///{(data_dir / 'fin-agent.db').as_posix()}"
    settings.database.echo = False
    settings.runtime.allow_system_model = False
    settings.codex.enabled = False
    settings.codex.owner_user_id = None
    if owner:
        if settings.runtime.commercial_mode:
            raise ValueError("Commercial mode cannot enable local Codex.")
        users = SQLAlchemyUserStore(settings.database.url)
        try:
            users.create_tables()
            user = users.get_by_username(owner)
        finally:
            users.engine.dispose()
        if not user or not user.is_active:
            raise ValueError("Owner not found. Start without --owner and register locally first.")
        settings.codex.owner_user_id = user.id
        settings.codex.enabled = True
    return settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    owners = parser.add_mutually_exclusive_group()
    owners.add_argument("--owner", help="Existing local Fin-agent username allowed to use Codex")
    owners.add_argument("--owner-file", type=Path, help="Local file containing the owner username")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--data-dir", type=Path, default=Path("var/local-codex"))
    parser.add_argument(
        "--database-url",
        help="Existing local Fin-agent database URL; preserves the selected owner's account.",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    try:
        owner = (
            args.owner_file.read_text(encoding="utf-8").strip() if args.owner_file else args.owner
        )
        settings = local_settings(args.data_dir, owner, args.database_url)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()
