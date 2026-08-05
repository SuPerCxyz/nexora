from sqlalchemy import inspect, text

from alembic import command
from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import build_alembic_config, upgrade_database


def test_sqlite_connection_pragmas(settings: Settings) -> None:
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
            busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()
            journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
    finally:
        database.dispose()

    assert 1 == foreign_keys
    assert settings.sqlite_busy_timeout_ms == busy_timeout
    assert "wal" == journal_mode


def test_upgrade_database_reaches_head(settings: Settings) -> None:
    database = Database(settings)
    try:
        upgrade_database(database)
        with database.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        database.dispose()

    assert "20260803_0022" == revision


def test_authentication_schema_is_created(settings: Settings) -> None:
    database = Database(settings)
    try:
        upgrade_database(database)
        table_names = set(inspect(database.engine).get_table_names())
    finally:
        database.dispose()

    assert {
        "administrators",
        "admin_sessions",
        "login_attempts",
        "tasks",
        "task_steps",
        "hosts",
        "host_credentials",
        "host_fingerprints",
        "host_capabilities",
        "remote_command_logs",
        "resource_scans",
        "resource_indexes",
        "resource_documents",
        "host_removal_plans",
        "host_removal_tombstones",
        "resource_locks",
        "vm_change_plans",
        "media_scans",
        "media_items",
        "media_credentials",
        "storage_pool_change_plans",
        "storage_volume_change_plans",
        "vm_creation_plans",
    } <= table_names


def test_database_health_check(settings: Settings) -> None:
    database = Database(settings)
    try:
        database.check_health()
    finally:
        database.dispose()


def test_upgrade_from_p0_preserves_existing_administrator(settings: Settings) -> None:
    database = Database(settings)
    try:
        config = build_alembic_config()
        with database.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "20260728_0003")
            connection.execute(
                text(
                    """
                    INSERT INTO administrators (
                        id, username, password_hash, session_version,
                        session_timeout_minutes, global_monospace, density,
                        language, timezone
                    ) VALUES (
                        1, 'admin', 'hash', 1, 30, 0,
                        'comfortable', 'zh-CN', 'Asia/Shanghai'
                    )
                    """
                )
            )
        upgrade_database(database)
        with database.engine.connect() as connection:
            username = connection.execute(
                text("SELECT username FROM administrators WHERE id = 1")
            ).scalar_one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        database.dispose()

    assert "admin" == username
    assert "20260803_0022" == revision


def test_resource_index_migration_preserves_managed_host(settings: Settings) -> None:
    database = Database(settings)
    try:
        config = build_alembic_config()
        with database.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "20260728_0004")
            connection.execute(
                text(
                    """
                    INSERT INTO hosts (
                        id, name, address, ssh_port, ssh_username,
                        authentication_method, sudo_mode, libvirt_uri, status,
                        labels_json, created_at, updated_at
                    ) VALUES (
                        'host-1', 'node', 'node.example.test', 22, 'root',
                        'private_key', 'none', 'qemu:///system', 'ready',
                        '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        upgrade_database(database)
        with database.engine.connect() as connection:
            host_name = connection.execute(
                text("SELECT name FROM hosts WHERE id = 'host-1'")
            ).scalar_one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        database.dispose()

    assert "node" == host_name
    assert "20260803_0022" == revision
