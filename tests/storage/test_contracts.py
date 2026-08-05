import pytest

from nexora.storage.contracts import StoragePoolCreateInput, parse_mount_options


def dir_input(**changes: object) -> StoragePoolCreateInput:
    values: dict[str, object] = {
        "host_id": "host-1",
        "name": "images",
        "pool_type": "dir",
        "target_path": "/var/lib/libvirt/images",
    }
    values.update(changes)
    return StoragePoolCreateInput(**values)  # type: ignore[arg-type]


def test_dir_input_round_trip() -> None:
    create = dir_input(start=False, autostart=False)

    create.validate()

    assert create == StoragePoolCreateInput.decode(create.encode())


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "../images"},
        {"target_path": "var/lib/libvirt/images"},
        {"target_path": "/var/../etc"},
        {"target_path": "/etc/nexora"},
        {"pool_type": "rbd"},
        {"source_host": "nfs.example.test"},
    ],
)
def test_invalid_dir_input_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        dir_input(**changes).validate()


def test_netfs_input_accepts_constrained_options() -> None:
    create = dir_input(
        pool_type="netfs",
        source_host="nfs.example.test",
        source_path="/exports/vms",
        nfs_version="4",
        mount_options=("rw", "hard", "timeo=600"),
    )

    create.validate()


@pytest.mark.parametrize(
    "value",
    ["ro,rw", "soft,hard", "suid", "timeo=-1", "vers=4", "rw,rw"],
)
def test_unsafe_mount_options_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        parse_mount_options(value)


def test_decode_rejects_non_boolean_flags() -> None:
    payload = dir_input().encode().replace('"start":true', '"start":"true"')

    with pytest.raises(ValueError):
        StoragePoolCreateInput.decode(payload)
