import pytest

from nexora.hosts.contracts import CredentialPayload, HostCreate
from nexora.hosts.models import AuthenticationMethod


def test_password_authentication_rejects_mixed_secrets() -> None:
    create = HostCreate(
        name="node",
        address="192.0.2.10",
        ssh_port=22,
        ssh_username="root",
        authentication_method=AuthenticationMethod.PASSWORD,
        credential=CredentialPayload(password="secret", private_key="-----BEGIN KEY-----"),
    )

    with pytest.raises(ValueError, match="only a password"):
        create.validate()


def test_private_key_authentication_rejects_unknown_format() -> None:
    create = HostCreate(
        name="node",
        address="192.0.2.10",
        ssh_port=22,
        ssh_username="root",
        authentication_method=AuthenticationMethod.PRIVATE_KEY,
        credential=CredentialPayload(private_key="not-a-key"),
    )

    with pytest.raises(ValueError, match="not recognized"):
        create.validate()


def test_onboarding_allows_only_system_libvirt_uri() -> None:
    create = HostCreate(
        name="node",
        address="192.0.2.10",
        ssh_port=22,
        ssh_username="root",
        authentication_method=AuthenticationMethod.PASSWORD,
        credential=CredentialPayload(password="secret"),
        libvirt_uri="qemu+tcp://unsafe/system",
    )

    with pytest.raises(ValueError, match="libvirt URI"):
        create.validate()
