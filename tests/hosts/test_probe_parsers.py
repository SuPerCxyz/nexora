import pytest

from nexora.hosts.probe_parsers import parse_lscpu


def test_parse_lscpu_selects_bounded_hardware_fields() -> None:
    result = parse_lscpu(
        b'{"lscpu":['
        b'{"field":"Architecture:","data":"x86_64"},'
        b'{"field":"CPU(s):","data":"32"},'
        b'{"field":"Model name:","data":"Example CPU"},'
        b'{"field":"Socket(s):","data":"2"},'
        b'{"field":"Unknown:","data":"ignored"}'
        b"]}"
    )

    assert {
        "architecture": "x86_64",
        "logical_cpus": 32,
        "model_name": "Example CPU",
        "sockets": 2,
    } == result


def test_parse_lscpu_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="lscpu"):
        parse_lscpu(b"not-json")
