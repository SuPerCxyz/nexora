"""Resolve trusted managed hosts into strict SSH connection profiles."""

from nexora.db import Database
from nexora.hosts.credentials import HostCredentialService
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile


class HostConnectionUnavailable(RuntimeError):
    """Host is missing, untrusted, or has no usable credential."""


class ManagedHostConnectionResolver:
    def __init__(
        self,
        database: Database,
        credentials: HostCredentialService,
        host_key_store: HostKeyStore,
    ) -> None:
        self.database = database
        self.credentials = credentials
        self.host_key_store = host_key_store

    def resolve(self, host_id: str) -> SSHConnectionProfile:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None or host.status not in {
                HostStatus.READY,
                HostStatus.SCANNING,
                HostStatus.DEGRADED,
                HostStatus.REMOVAL_PENDING,
            }:
                raise HostConnectionUnavailable("host is not trusted and ready")
            connection = SSHConnection(
                host.address,
                host.ssh_port,
                host.ssh_username,
                self.host_key_store.path_for(host.id).absolute(),
            )
            authentication_method = AuthenticationMethod(host.authentication_method)
        payload = self.credentials.load(host_id)
        if authentication_method == AuthenticationMethod.PASSWORD:
            return SSHConnectionProfile(connection, password=payload.password)
        return SSHConnectionProfile(
            connection,
            private_key=payload.private_key,
            private_key_passphrase=payload.private_key_passphrase,
        )
