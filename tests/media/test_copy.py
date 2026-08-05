import pytest

from media.copy_support import Executor, Transfer, runtime, service
from nexora.config import Settings
from nexora.media.copy_errors import MediaCopyError


def test_copy_streams_verifies_and_publishes_without_partial(
    settings: Settings,
) -> None:
    database, copy_input, source = runtime(settings)
    remote_files: dict[str, bytes] = {}
    executor = Executor(remote_files)
    transfer = Transfer(remote_files)
    copy_service = service(database, settings, executor, transfer)

    result = copy_service.execute(copy_input, task_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    final = "/pool/base.raw"
    assert "image copied" in result
    assert source == remote_files[final]
    assert not any(path.endswith(".partial") for path in remote_files)
    assert any(argv[0] == "ln" for argv in executor.commands)
    assert 1 == transfer.calls
    database.dispose()


def test_copy_blocks_out_of_band_pool_change_before_transfer(settings: Settings) -> None:
    database, copy_input, _source = runtime(settings)
    remote_files: dict[str, bytes] = {}
    transfer = Transfer(remote_files)
    copy_service = service(
        database,
        settings,
        Executor(remote_files),
        transfer,
        authoritative_pool_hash="c" * 64,
    )

    with pytest.raises(MediaCopyError, match="status blocks writes"):
        copy_service.execute(copy_input, task_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert 0 == transfer.calls
    database.dispose()


def test_copy_never_overwrites_existing_target(settings: Settings) -> None:
    database, copy_input, _source = runtime(settings)
    remote_files = {"/pool/base.raw": b"existing"}
    transfer = Transfer(remote_files)
    copy_service = service(database, settings, Executor(remote_files), transfer)

    with pytest.raises(MediaCopyError, match="collision"):
        copy_service.execute(copy_input, task_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert b"existing" == remote_files["/pool/base.raw"]
    assert 0 == transfer.calls
    database.dispose()


def test_recovery_accepts_already_published_matching_image(settings: Settings) -> None:
    database, copy_input, source = runtime(settings)
    remote_files = {"/pool/base.raw": source}
    transfer = Transfer(remote_files)
    copy_service = service(database, settings, Executor(remote_files), transfer)

    result = copy_service.execute(
        copy_input,
        task_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )

    assert "already published" in result
    assert 0 == transfer.calls
    database.dispose()


def test_recovery_removes_only_its_partial_before_retry(settings: Settings) -> None:
    database, copy_input, source = runtime(settings)
    task_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    partial = f"/pool/.base.raw.nexora-{task_id}.partial"
    remote_files = {partial: b"interrupted", "/pool/unrelated.raw": b"keep"}
    transfer = Transfer(remote_files)
    copy_service = service(database, settings, Executor(remote_files), transfer)

    copy_service.execute(copy_input, task_id=task_id)

    assert source == remote_files["/pool/base.raw"]
    assert b"keep" == remote_files["/pool/unrelated.raw"]
    assert partial not in remote_files
    assert 1 == transfer.calls
    database.dispose()


def test_hash_failure_only_cleans_task_partial(settings: Settings) -> None:
    database, copy_input, _source = runtime(settings)
    remote_files = {"/pool/unrelated.raw": b"keep"}
    copy_service = service(
        database,
        settings,
        Executor(remote_files),
        Transfer(remote_files, corrupt=True),
    )

    with pytest.raises(MediaCopyError, match="SHA-256"):
        copy_service.execute(copy_input, task_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert {"/pool/unrelated.raw": b"keep"} == remote_files
    database.dispose()
