import pytest

from nexora.vms.clone_contracts import CloneFile, VmCloneManifest


def _manifest() -> VmCloneManifest:
    return VmCloneManifest(
        source_host_id="source",
        source_vm_uuid="11111111-1111-1111-1111-111111111111",
        source_generation=1,
        source_hash="a" * 64,
        target_host_id="target",
        target_pool_id="pool",
        target_pool_uuid="22222222-2222-2222-2222-222222222222",
        target_pool_generation=2,
        target_pool_hash="b" * 64,
        target_vm_uuid="33333333-3333-3333-3333-333333333333",
        target_name="safe-clone",
        mac_addresses=("52:54:00:aa:bb:cc",),
        files=(
            CloneFile(
                "/source/a.qcow2",
                "/target/a.qcow2",
                "/target/.a.partial",
                1024,
                "disk",
            ),
        ),
    )


def test_clone_manifest_round_trip() -> None:
    manifest = _manifest()
    assert manifest == VmCloneManifest.decode(manifest.encode())


def test_clone_manifest_rejects_path_traversal() -> None:
    manifest = _manifest()
    invalid = VmCloneManifest(
        **{
            **vars(manifest),
            "files": (CloneFile("/source/a", "/target/../escape", "/tmp/p", 1, "disk"),),
        }
    )
    with pytest.raises(ValueError, match="path"):
        invalid.validate()


def test_migration_manifest_requires_matching_uuid() -> None:
    manifest = _manifest()
    migration = VmCloneManifest(
        **{
            **vars(manifest),
            "preserve_identity": True,
            "target_vm_uuid": manifest.source_vm_uuid,
        }
    )
    assert migration.validate() is None
    with pytest.raises(ValueError, match="UUID"):
        VmCloneManifest(
            **{
                **vars(manifest),
                "preserve_identity": True,
                "target_vm_uuid": "44444444-4444-4444-4444-444444444444",
            }
        ).validate()


def test_migration_manifest_round_trip() -> None:
    manifest = _manifest()
    migration = VmCloneManifest(
        **{
            **vars(manifest),
            "preserve_identity": True,
            "target_vm_uuid": manifest.source_vm_uuid,
        }
    )
    assert migration == VmCloneManifest.decode(migration.encode())
    decoded = VmCloneManifest.decode(migration.encode())
    assert decoded.preserve_identity
