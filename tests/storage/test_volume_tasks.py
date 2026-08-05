import pytest

from nexora.storage.volume_tasks import StorageVolumeTaskInput

POOL_UUID = "11111111-1111-1111-1111-111111111111"


def test_mutation_task_input_binds_volume_resource_identity() -> None:
    value = StorageVolumeTaskInput(
        "plan-1",
        "host-1",
        POOL_UUID,
        "resize",
        '["pool","/images/vm.qcow2"]',
    )

    decoded = StorageVolumeTaskInput.decode(value.encode())

    assert value == decoded


def test_mutation_task_input_rejects_missing_volume_identity() -> None:
    value = StorageVolumeTaskInput("plan-1", "host-1", POOL_UUID, "delete")

    with pytest.raises(ValueError, match="invalid"):
        StorageVolumeTaskInput.decode(value.encode())
