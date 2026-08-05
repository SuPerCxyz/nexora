"""Programmatic Alembic migration entry points."""

import os
from pathlib import Path

from alembic.config import Config

from alembic import command
from nexora.db.database import Database

PROJECT_ROOT = Path(os.environ.get("NEXORA_PROJECT_ROOT", Path(__file__).resolve().parents[3]))


def build_alembic_config() -> Config:
    """Build a location-independent Alembic configuration."""

    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


def upgrade_database(database: Database) -> None:
    """Upgrade the database to the current schema in one connection."""

    config = build_alembic_config()
    with database.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
