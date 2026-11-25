"""``uplink``: state and the two modes, with the quectel-usbnet CLI faked by argv.

The real CLI (ChiefGyk3D/quectel-usbnet, its issue 25) is never run, and
nothing here can change a network: ``run`` is replaced by a runner that only
answers the argv it was told about.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from helper_fakes import FakeRunner

from hammunition_devctl import uplink
from hammunition_devctl.devctl import main
from hammunition_devctl.run import Result, set_runner

CLI = "/fake/bin/quectel-usbnet"
STATUS = (CLI, "uplink", "status", "--json")


def status_doc(mode="auto", owner="wifi", until=None, since="2026-11-24T10:00:00Z", **extra):
    doc = {
        "mode": mode,
        "owner": owner,
        "links": {
            "ethernet": {"state": "absent", "healthy": False},
            "wifi": {"state": "up", "healthy": True},
            "cell": {"state": "up", "healthy": True},
        },
        "until": until,
        "since": since,
    }
    doc.update(extra)
    return json.dumps(doc) + "\n"


@pytest.fixture(autouse=True)
def _fake_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uplink, "find_cli", lambda: CLI)


def state(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main(["uplink", "state"]) == 0
    doc: dict[str, object] = json.loads(capsys.readouterr().out)
    return doc


def test_state_is_one_flat_document_with_every_key(capsys: pytest.CaptureFixture[str]) -> None:
    set_runner(FakeRunner({STATUS: Result(0, status_doc())}))
    doc = state(capsys)
    assert doc == {
        "kind": "uplink",
        "version": 1,
        "present": True,
        "mode": "auto",
        "owner": "wifi",
        "until": None,
        "since": "2026-11-24T10:00:00Z",
        "detail": "",
    }


def test_cell_first_carries_its_expiry(capsys: pytest.CaptureFixture[str]) -> None:
    until = "2026-11-24T14:30:00+00:00"
    set_runner(FakeRunner({STATUS: Result(0, status_doc("cell-first", "cell", until))}))
    doc = state(capsys)
    assert (doc["mode"], doc["owner"], doc["until"]) == ("cell-first", "cell", until)


def test_the_links_table_is_not_passed_on(capsys: pytest.CaptureFixture[str]) -> None:
    set_runner(FakeRunner({STATUS: Result(0, status_doc(hostname="somebodys-laptop"))}))
    doc = state(capsys)
    assert "somebodys-laptop" not in json.dumps(doc)
    assert "links" not in doc


def test_a_missing_cli_is_present_false_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(uplink, "find_cli", lambda: None)
    runner = FakeRunner()
    set_runner(runner)
    doc = state(capsys)
    assert doc["present"] is False and doc["mode"] == "" and "not installed" in str(doc["detail"])
    assert runner.calls == []


def test_a_cli_that_vanishes_between_the_lookup_and_the_run_is_the_same(
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_runner(FakeRunner({STATUS: Result(127, "", "command not found")}))
    doc = state(capsys)
    assert doc["present"] is False and "not installed" in str(doc["detail"])


def test_a_failing_cli_says_why_in_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    set_runner(FakeRunner({STATUS: Result(1, "", "error: no state file\nTraceback ...\n")}))
    doc = state(capsys)
    assert doc["present"] is False
    assert "error: no state file" in str(doc["detail"]) and "Traceback" not in str(doc["detail"])


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json",
        "[]",
        "null",
        '{"mode": "turbo", "owner": "wifi", "until": null}',
        '{"owner": "wifi", "until": null}',
        '{"mode": "auto", "owner": "wifi", "until": "tomorrow"}',
        '{"mode": "auto", "owner": "wifi", "until": 5}',
        '{"mode": "cell-first", "owner": 7, "until": null}',
        '{"mode": "auto", "owner": "wifi", "until": NaN}',
    ],
)
def test_an_unreadable_status_is_present_false_never_a_guess(
    stdout: str, capsys: pytest.CaptureFixture[str]
) -> None:
    set_runner(FakeRunner({STATUS: Result(0, stdout)}))
    doc = state(capsys)
    assert doc["present"] is False and doc["mode"] == "" and doc["until"] is None
    assert doc["detail"]


def test_an_owner_this_helper_does_not_know_reads_as_none(capsys: pytest.CaptureFixture[str]) -> None:
    set_runner(FakeRunner({STATUS: Result(0, status_doc(owner="satellite"))}))
    assert state(capsys)["owner"] == "none"


def test_auto_is_one_fixed_argv_and_is_read_back() -> None:
    runner = FakeRunner(
        {
            STATUS: [Result(0, status_doc("cell-first", "cell", "2026-11-24T14:30:00Z")), Result(0, status_doc())],
            (CLI, "uplink", "auto"): Result(0),
        }
    )
    set_runner(runner)
    assert main(["uplink", "auto"]) == 0
    assert runner.calls == [STATUS, (CLI, "uplink", "auto"), STATUS]


def test_cell_first_passes_the_duration_and_is_read_back() -> None:
    until = "2026-11-24T14:30:00Z"
    runner = FakeRunner(
        {
            STATUS: [Result(0, status_doc()), Result(0, status_doc("cell-first", "cell", until))],
            (CLI, "uplink", "cell-first", "--for", "2h"): Result(0),
        }
    )
    set_runner(runner)
    assert main(["uplink", "cell-first", "--for", "2h"]) == 0
    assert (CLI, "uplink", "cell-first", "--for", "2h") in runner.calls


def test_cell_first_defaults_to_two_hours_explicitly() -> None:
    runner = FakeRunner(
        {
            STATUS: [Result(0, status_doc()), Result(0, status_doc("cell-first", "cell", "2026-11-24T14:30:00Z"))],
            (CLI, "uplink", "cell-first", "--for", "2h"): Result(0),
        }
    )
    set_runner(runner)
    assert main(["uplink", "cell-first"]) == 0


def test_no_expiry_is_for_zero_and_reads_back_with_no_until() -> None:
    runner = FakeRunner(
        {
            STATUS: [Result(0, status_doc()), Result(0, status_doc("cell-first", "cell", None))],
            (CLI, "uplink", "cell-first", "--for", "0"): Result(0),
        }
    )
    set_runner(runner)
    assert main(["uplink", "cell-first", "--for", "0"]) == 0


def test_no_expiry_that_reads_back_with_an_expiry_is_unverified(
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_runner(
        FakeRunner(
            {
                STATUS: [Result(0, status_doc()), Result(0, status_doc("cell-first", "cell", "2026-11-24T14:30:00Z"))],
                (CLI, "uplink", "cell-first", "--for", "0"): Result(0),
            }
        )
    )
    assert main(["uplink", "cell-first", "--for", "0"]) == 1
    assert "unverified:" in capsys.readouterr().err


def test_a_timed_cell_first_that_reads_back_with_no_expiry_is_unverified(
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_runner(
        FakeRunner(
            {
                STATUS: [Result(0, status_doc()), Result(0, status_doc("cell-first", "cell", None))],
                (CLI, "uplink", "cell-first", "--for", "1h"): Result(0),
            }
        )
    )
    assert main(["uplink", "cell-first", "--for", "1h"]) == 1
    assert "unverified:" in capsys.readouterr().err


def test_a_mode_that_does_not_read_back_is_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    set_runner(
        FakeRunner(
            {
                STATUS: [Result(0, status_doc("cell-first", "cell", None)), Result(0, status_doc("cell-first", "cell", None))],
                (CLI, "uplink", "auto"): Result(0),
            }
        )
    )
    assert main(["uplink", "auto"]) == 1
    assert "unverified:" in capsys.readouterr().err


def test_a_failing_switch_is_exit_1_with_the_clis_first_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_runner(
        FakeRunner(
            {
                STATUS: Result(0, status_doc()),
                (CLI, "uplink", "cell-first", "--for", "2h"): Result(1, "", "error: modem not connected\nmore\n"),
            }
        )
    )
    assert main(["uplink", "cell-first"]) == 1
    err = capsys.readouterr().err
    assert "error: modem not connected" in err and "more" not in err


def test_a_missing_cli_refuses_a_switch_with_exit_2_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(uplink, "find_cli", lambda: None)
    runner = FakeRunner()
    set_runner(runner)
    assert main(["uplink", "cell-first"]) == 2
    assert "not available" in capsys.readouterr().err
    assert runner.calls == []


def test_a_cli_that_cannot_say_its_state_refuses_a_switch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner({STATUS: Result(1, "", "error: boom")})
    set_runner(runner)
    assert main(["uplink", "auto"]) == 2
    assert runner.calls == [STATUS]


def test_the_switches_refuse_to_run_as_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition_devctl import devctl

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(devctl, "_refuse_or_warn_if_unsafe", lambda: None)
    runner = FakeRunner()
    set_runner(runner)
    for argv in (["uplink", "auto"], ["uplink", "cell-first"]):
        assert main(argv) == 2
        assert "without pkexec" in capsys.readouterr().err
    assert runner.calls == []


@pytest.mark.parametrize(
    "bad",
    ["", "2", "h", "-1h", "01h", "2H", "2 h", "2h;id", "$(id)", "1d", "99999h", "0h", "0m", "1.5h", "2h\n", "inf"],
)
def test_only_a_plain_duration_reaches_the_cli(
    bad: str, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner()
    set_runner(runner)
    assert main(["uplink", "cell-first", f"--for={bad}"]) == 2
    assert "error:" in capsys.readouterr().err
    assert runner.calls == []


@pytest.mark.parametrize("good", ["0", "1m", "30m", "1h", "2h", "8h", "9999h"])
def test_the_plain_durations_are_accepted(good: str) -> None:
    assert uplink.valid_duration(good)


def test_a_bad_mode_is_an_argparse_refusal() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["uplink", "sideways"])
    assert caught.value.code == 2


def test_auto_takes_no_duration() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["uplink", "auto", "--for", "2h"])
    assert caught.value.code == 2


def test_nothing_but_the_status_read_and_one_switch_ever_runs() -> None:
    runner = FakeRunner(
        {
            STATUS: [Result(0, status_doc()), Result(0, status_doc("cell-first", "cell", "2026-11-24T14:30:00Z"))],
            (CLI, "uplink", "cell-first", "--for", "2h"): Result(0),
        }
    )
    set_runner(runner)
    main(["uplink", "cell-first", "--for", "2h"])
    assert {call[:2] for call in runner.calls} == {(CLI, "uplink")}
    assert all("pkexec" not in " ".join(call) and "sudo" not in " ".join(call) for call in runner.calls)


def test_find_cli_looks_on_path_then_in_the_users_local_bin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the autouse fake
    home = tmp_path / "home"
    local = home / ".local" / "bin"
    local.mkdir(parents=True)
    exe = local / "quectel-usbnet"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert uplink.find_cli() == str(exe)
    onpath = tmp_path / "bin"
    onpath.mkdir()
    other = onpath / "quectel-usbnet"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    monkeypatch.setenv("PATH", str(onpath))
    assert uplink.find_cli() == str(other)
    exe.unlink()
    other.unlink()
    assert uplink.find_cli() is None


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_the_cli_path_can_be_named_and_wins_over_the_older_one_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The real laptop: an older quectel-usbnet without `uplink` is on PATH and
    # the manager lives in ~/.local/libexec/quectel-usbnet-uplink.
    monkeypatch.undo()  # the autouse fake
    old = _exe(tmp_path / "bin" / "quectel-usbnet")
    new = _exe(tmp_path / "home" / ".local" / "libexec" / "quectel-usbnet-uplink")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(old.parent))
    monkeypatch.delenv("HAMMUNITION_UPLINK_CLI", raising=False)
    assert uplink.find_cli() == str(old)  # the default is unchanged
    monkeypatch.setenv("HAMMUNITION_UPLINK_CLI", str(new))
    assert uplink.find_cli() == str(new)


@pytest.mark.parametrize("bad", ["", "quectel-usbnet-uplink", "~/x", "../x", "/no/such/cli"])
def test_a_named_path_that_is_not_an_executable_absolute_file_is_not_available_not_a_fallback(
    bad: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()
    on_path = _exe(tmp_path / "bin" / "quectel-usbnet")
    monkeypatch.setenv("PATH", str(on_path.parent))
    monkeypatch.setenv("HAMMUNITION_UPLINK_CLI", bad)
    if bad == "":
        # Unset and empty are the same: the default search.
        assert uplink.find_cli() == str(on_path)
    else:
        assert uplink.find_cli() is None


def test_a_named_path_that_is_a_directory_or_not_executable_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    plain = tmp_path / "plain"
    plain.write_text("x")
    plain.chmod(0o644)
    for bad in (plain, tmp_path):
        monkeypatch.setenv("HAMMUNITION_UPLINK_CLI", str(bad))
        assert uplink.find_cli() is None


def test_a_named_cli_is_what_state_and_the_switch_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.undo()
    new = _exe(tmp_path / "libexec" / "quectel-usbnet-uplink")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setenv("HAMMUNITION_UPLINK_CLI", str(new))
    named = (str(new), "uplink", "status", "--json")
    runner = FakeRunner({named: Result(0, status_doc()), (str(new), "uplink", "auto"): Result(0, "")})
    set_runner(runner)
    assert state(capsys)["present"] is True
    assert main(["uplink", "auto"]) == 0
    assert {call[0] for call in runner.calls} == {str(new)}
