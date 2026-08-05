"""Alembic migration environment."""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from alembic import context
from nexora.audit.models import RemoteCommandLog
from nexora.auth.models import Administrator
from nexora.consoles.models import ConsoleSession
from nexora.db.base import Base
from nexora.hosts.models import Host
from nexora.hosts.removal_models import HostRemovalPlan
from nexora.media.models import MediaItem
from nexora.resources.models import ResourceIndex
from nexora.storage.models import StoragePoolChangePlan
from nexora.storage.volume_models import StorageVolumeChangePlan
from nexora.tasks.locks import ResourceLock
from nexora.tasks.models import Task
from nexora.vms.change_models import VmChangePlan
from nexora.vms.clone_models import VmClonePlan
from nexora.vms.creation_models import VmCreationPlan
from nexora.vms.media_creation_models import VmMediaCreationPlan
from nexora.vms.snapshot_models import SnapshotChangePlan

config = context.config
_loaded_model_types = (
    Administrator,
    ConsoleSession,
    Host,
    HostRemovalPlan,
    MediaItem,
    RemoteCommandLog,
    ResourceIndex,
    ResourceLock,
    StoragePoolChangePlan,
    StorageVolumeChangePlan,
    Task,
    VmChangePlan,
    VmClonePlan,
    VmCreationPlan,
    VmMediaCreationPlan,
    SnapshotChangePlan,
)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_with_connection(connection: Connection) -> None:
    """Run migrations through an existing connection."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a shared or configured connection."""

    shared_connection = config.attributes.get("connection")
    if shared_connection is not None:
        run_with_connection(shared_connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        run_with_connection(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
