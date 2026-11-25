"""``uplink`` through the real process runner against a fake of the CLI.

tests/fakes/quectel-usbnet is a stateful stand-in for the manager's CLI
contract. It only writes a small state file under the test's tmp_path, so
this runs a real subprocess without any chance of touching a network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hammunition_devctl.devctl import main
from hammunition_devctl.run import set_runner

FAKES = Path(__file__).resolve().parent / "fakes"


@pytest.fixture(autouse=True)
def _fake_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_runner(None)
    monkeypatch.setenv("PATH", f"{FAKES}:/usr/bin:/bin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FAKE_UPLINK_STATE", str(tmp_path / "state.json"))
    monkeypatch.delenv("FAKE_UPLINK_FAIL", raising=False)


def read(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main(["uplink", "state"]) == 0
    doc: dict[str, object] = json.loads(capsys.readouterr().out)
    return doc


def test_a_round_trip_through_a_real_process(capsys: pytest.CaptureFixture[str]) -> None:
    assert read(capsys)["mode"] == "auto"
    assert main(["uplink", "cell-first", "--for", "1h"]) == 0
    doc = read(capsys)
    assert (doc["mode"], doc["owner"], doc["present"]) == ("cell-first", "cell", True)
    assert isinstance(doc["until"], str)
    assert main(["uplink", "cell-first", "--for", "0"]) == 0
    assert read(capsys)["until"] is None
    assert main(["uplink", "auto"]) == 0
    doc = read(capsys)
    assert (doc["mode"], doc["until"]) == ("auto", None)


def test_a_cli_that_fails_is_a_plain_unavailable_state_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("FAKE_UPLINK_FAIL", "error: NetworkManager is not running")
    doc = read(capsys)
    assert doc["present"] is False and "NetworkManager is not running" in str(doc["detail"])
    assert main(["uplink", "cell-first"]) == 2
    assert not (tmp_path / "state.json").exists()


def test_with_no_cli_at_all_it_is_not_installed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    doc = read(capsys)
    assert doc["present"] is False and "not installed" in str(doc["detail"])
    assert main(["uplink", "auto"]) == 2
