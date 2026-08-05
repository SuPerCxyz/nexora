import asyncssh

from nexora.hosts.connection import ManagedHostConnectionResolver
from nexora.hosts.contracts import CredentialPayload, HostCreate
from nexora.hosts.models import AuthenticationMethod
from nexora.hosts.onboarding import candidate_digest

from .conftest import HostRuntime


def _resolver(runtime: HostRuntime) -> ManagedHostConnectionResolver:
    return ManagedHostConnectionResolver(
        runtime.database,
        runtime.credentials,
        runtime.store,
    )


def test_resolver_returns_password_only_after_host_key_confirmation(
    host_runtime: HostRuntime,
) -> None:
    pending = host_runtime.onboarding.begin(
        HostCreate(
            name="password-node",
            address="kvm.example.test",
            ssh_port=22,
            ssh_username="root",
            authentication_method=AuthenticationMethod.PASSWORD,
            credential=CredentialPayload(password="test-password"),
        )
    )
    host_runtime.onboarding.confirm(
        pending.id,
        candidate_digest(host_runtime.scanner_values),
    )

    profile = _resolver(host_runtime).resolve(pending.id)

    assert "test-password" == profile.password
    assert profile.private_key is None


def test_resolver_returns_encrypted_private_key_and_passphrase(
    host_runtime: HostRuntime,
) -> None:
    key = asyncssh.generate_private_key("ssh-ed25519")
    private_key = key.export_private_key("openssh", passphrase="key-passphrase").decode()
    pending = host_runtime.onboarding.begin(
        HostCreate(
            name="key-node",
            address="kvm.example.test",
            ssh_port=22,
            ssh_username="operator",
            authentication_method=AuthenticationMethod.PRIVATE_KEY,
            credential=CredentialPayload(
                private_key=private_key,
                private_key_passphrase="key-passphrase",
            ),
        )
    )
    host_runtime.onboarding.confirm(
        pending.id,
        candidate_digest(host_runtime.scanner_values),
    )

    profile = _resolver(host_runtime).resolve(pending.id)

    assert private_key == profile.private_key
    assert "key-passphrase" == profile.private_key_passphrase
    assert profile.password is None
