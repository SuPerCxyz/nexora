"""Command-line deployment and recovery operations."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.operations.backup import create_backup
from nexora.operations.constants import ALL_DATA_DIRECTORIES
from nexora.operations.database import verify_database
from nexora.operations.restore import restore_backup


def main() -> None:
    parser = _parser()
    arguments = parser.parse_args()
    settings = Settings()
    try:
        if arguments.command == "init":
            _initialize(settings)
        elif arguments.command == "check":
            verify_database(settings.database_path)
            print("SQLite quick_check: ok")
        elif arguments.command == "backup":
            output = arguments.output or _default_backup_path(settings)
            print(create_backup(settings.data_dir, output))
        elif arguments.command == "restore":
            if not arguments.confirm_stopped:
                parser.error("restore requires --confirm-stopped")
            recovery = restore_backup(
                settings.data_dir,
                arguments.archive,
                replace=arguments.replace_existing_data,
            )
            print(f"Restore complete; previous data: {recovery}")
        else:
            parser.error("unknown operation")
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        _fail(str(exc))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexora-ops")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create data directories and upgrade SQLite")
    commands.add_parser("check", help="run SQLite quick_check")
    backup = commands.add_parser("backup", help="create a consistent data archive")
    backup.add_argument("--output", type=Path)
    restore = commands.add_parser("restore", help="restore a validated data archive")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--confirm-stopped", action="store_true")
    restore.add_argument("--replace-existing-data", action="store_true")
    return parser


def _initialize(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ALL_DATA_DIRECTORIES:
        (settings.data_dir / name).mkdir(mode=0o700, exist_ok=True)
    database = Database(settings)
    try:
        upgrade_database(database)
        database.check_health()
    finally:
        database.dispose()
    print(f"Initialized {settings.data_dir}")


def _default_backup_path(settings: Settings) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return settings.data_dir / "backups" / f"nexora-{stamp}.tar.gz"


def _fail(message: str) -> NoReturn:
    print(f"nexora-ops: {message}", file=sys.stderr)
    raise SystemExit(1)
