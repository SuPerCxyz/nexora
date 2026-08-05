import pytest
from lxml import etree

from nexora.storage.volume_contracts import StorageVolumeCreateInput
from nexora.storage.volume_xml import build_volume_xml


def create_input(**changes: object) -> StorageVolumeCreateInput:
    values: dict[str, object] = {
        "host_id": "host-1",
        "pool_resource_id": "pool-1",
        "pool_uuid": "11111111-1111-1111-1111-111111111111",
        "pool_generation": 1,
        "pool_hash": "a" * 64,
        "name": "vm-disk.qcow2",
        "volume_format": "qcow2",
        "capacity_bytes": 10 * 1024**3,
    }
    values.update(changes)
    return StorageVolumeCreateInput(**values)  # type: ignore[arg-type]


def test_volume_input_round_trip_and_xml() -> None:
    create = create_input()

    decoded = StorageVolumeCreateInput.decode(create.encode())
    root = etree.fromstring(build_volume_xml(decoded))

    assert create == decoded
    assert "file" == root.get("type")
    assert "vm-disk.qcow2" == root.findtext("name")
    assert str(10 * 1024**3) == root.findtext("capacity")
    assert "bytes" == root.find("capacity").get("unit")
    assert "0" == root.findtext("allocation")
    assert "qcow2" == root.find("target/format").get("type")
    assert root.find("target/path") is None
    assert root.find("key") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "../disk.qcow2"},
        {"name": "-disk.qcow2"},
        {"volume_format": "vmdk"},
        {"capacity_bytes": 1024},
        {"capacity_bytes": 9 * 1024**5},
        {"pool_uuid": "not-a-uuid"},
        {"pool_hash": "A" * 64},
        {"pool_generation": 0},
    ],
)
def test_invalid_volume_input_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        create_input(**changes).validate()
