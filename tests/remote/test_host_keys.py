import base64
import stat
import subprocess
from pathlib import Path

import pytest

from nexora.remote.host_key_scanner import HostKeyScanError, scan_host_keys
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.host_keys import (
    HostKeyCandidate,
    HostKeyStatus,
    compare_host_keys,
)
from nexora.remote.validation import validate_host


def _candidate(data: bytes = b"public-key") -> HostKeyCandidate:
    return HostKeyCandidate(
        "kvm.example.test",
        10022,
        "ssh-ed25519",
        base64.b64encode(data).decode(),
    )


def test_candidate_exposes_fingerprint_and_strict_line() -> None:
    candidate = _candidate()

    assert candidate.fingerprint.startswith("SHA256:")
    assert (
        f"[kvm.example.test]:10022 ssh-ed25519 {candidate.key_data}" == candidate.known_hosts_line
    )


def test_comparison_detects_new_match_and_changed() -> None:
    candidate = _candidate()

    assert HostKeyStatus.NEW == compare_host_keys([candidate], [])
    assert HostKeyStatus.MATCH == compare_host_keys([candidate], [candidate])
    assert HostKeyStatus.CHANGED == compare_host_keys([_candidate(b"new")], [candidate])


def test_store_is_atomic_private_and_rejects_path_escape(tmp_path: Path) -> None:
    store = HostKeyStore(tmp_path / "hostkeys")
    candidate = _candidate()

    path = store.save("host-1", [candidate])

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [candidate] == store.load("host-1", host=candidate.host, port=candidate.port)
    with pytest.raises(ValueError):
        store.save("../escape", [candidate])


def test_scanner_uses_argv_and_parses_supported_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()
    output = f"[kvm.example.test]:10022 {candidate.key_type} {candidate.key_data}\n"

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert [
            "ssh-keyscan",
            "-T",
            "10",
            "-p",
            "10022",
            "kvm.example.test",
        ] == command
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert [candidate] == scan_host_keys("KVM.EXAMPLE.TEST", 10022)


def test_scanner_rejects_injection_and_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError):
        scan_host_keys("-oProxyCommand=evil", 22)

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "failed"),
    )
    with pytest.raises(HostKeyScanError):
        scan_host_keys("kvm.example.test", 22)


@pytest.mark.parametrize("host", ["192.0.2.1", "2001:db8::1", "KVM.EXAMPLE.TEST"])
def test_host_validation_accepts_ip_and_dns(host: str) -> None:
    assert validate_host(host)
