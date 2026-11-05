import io
import json
import subprocess
import sys
from datetime import date

import pytest

from ccvalidator.cli import main

VISA = "4111111111111111"


def test_valid_number_exits_zero(capsys):
    assert main([VISA]) == 0
    out = capsys.readouterr().out
    assert "VALID" in out and "Visa" in out


def test_invalid_number_exits_one(capsys):
    assert main(["4111111111111112"]) == 1
    out = capsys.readouterr().out
    assert "INVALID" in out and "Luhn" in out


def test_output_never_contains_full_number(capsys):
    main([VISA])
    assert VISA not in capsys.readouterr().out


def test_json_output(capsys):
    assert main([VISA, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["valid"] is True
    assert data["brand"] == "Visa"
    assert data["masked_number"] == "************1111"


def test_cvv_and_expiry(capsys):
    future = f"12/{date.today().year + 2}"
    assert main([VISA, "--cvv", "123", "--expiry", future]) == 0
    assert main([VISA, "--cvv", "12"]) == 1
    assert main([VISA, "--expiry", "01/2020"]) == 1
    capsys.readouterr()


def test_reads_number_from_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(VISA + "\n"))
    assert main([]) == 0
    assert VISA not in capsys.readouterr().out


def test_dash_reads_from_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("3782 822463 10005\n"))
    assert main(["-"]) == 0
    assert "American Express" in capsys.readouterr().out


def test_empty_stdin_is_invalid(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert main([]) == 1
    assert "empty" in capsys.readouterr().out


def test_allow_unknown_brand_flag(capsys):
    assert main(["9000000000000001"]) == 1
    assert main(["9000000000000001", "--allow-unknown-brand"]) == 0
    capsys.readouterr()


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "ccvalidator" in capsys.readouterr().out


def test_python_dash_m_entrypoint():
    proc = subprocess.run(
        [sys.executable, "-m", "ccvalidator", VISA],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "VALID" in proc.stdout
