# SPDX-FileCopyrightText: Copyright (C) 2026 ChiefGyk3D
# SPDX-License-Identifier: GPL-3.0-or-later

"""Uplink: which link owns the default routes. docs/contract.md.

A thin, fixed-argv client of the link-priority manager's CLI
(ChiefGyk3D/quectel-usbnet, ``quectel-usbnet uplink ...``). The manager runs
as the calling user, so none of this is privileged and none of it goes through
pkexec or sudo. The helper never changes a route itself: it asks the manager
for ``auto`` or ``cell-first`` and reads the answer back.

The CLI's answer is checked field by field before any of it is passed on, and
anything that does not fit is "not available" with a one-line reason, never a
guess. The CLI's ``links`` table is not passed on.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

from hammunition_devctl.run import run

__all__ = ["CLI_ENV", "DEFAULT_DURATION", "MODES", "find_cli", "read_uplink", "switch", "valid_duration"]

MODES = ("auto", "cell-first")
OWNERS = ("ethernet", "wifi", "cell", "none")
CLI_NAME = "quectel-usbnet"
DEFAULT_DURATION = "2h"
"""Sent explicitly with ``cell-first``, so the helper's default does not
depend on the manager's."""

_DURATION = re.compile(r"(0|[1-9][0-9]{0,3}[mh])")
"""``0`` is no expiry; otherwise minutes or hours, at most four digits."""
_STAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})"
)
_TOOL_MISSING = 127


def valid_duration(text: str) -> bool:
    return _DURATION.fullmatch(text) is not None


CLI_ENV = "HAMMUNITION_UPLINK_CLI"
"""Names the CLI by absolute path, for a machine where the manager is not
``quectel-usbnet`` on ``PATH`` (an older one there has no ``uplink``). Unset
or empty: the search below, unchanged. Set: that file or nothing, never a
fallback to another one, so a typo cannot quietly run something else."""


def find_cli() -> str | None:
    """The absolute path of the CLI, or None. ``HAMMUNITION_UPLINK_CLI`` if it
    is set; else ``PATH``, then the account's ``~/.local/bin``: a panel or a
    service manager often starts a tray without it on ``PATH``."""
    named = os.environ.get(CLI_ENV, "")
    if named:
        ok = os.path.isabs(named) and os.path.isfile(named) and os.access(named, os.X_OK)
        return named if ok else None
    found = shutil.which(CLI_NAME)
    if found:
        return found
    return shutil.which(CLI_NAME, path=os.path.expanduser("~/.local/bin"))


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:120]
    return ""


def _no_constant(name: str) -> object:
    raise ValueError(f"{name} is not JSON")


def _doc(present: bool, detail: str, mode: str = "", owner: str = "", until: str | None = None,
         since: str | None = None) -> dict[str, Any]:
    return {
        "kind": "uplink",
        "version": 1,
        "present": present,
        "mode": mode,
        "owner": owner,
        "until": until,
        "since": since,
        "detail": detail,
    }


def _stamp(value: object) -> str | None:
    """The stamp when it is one, else None."""
    if isinstance(value, str) and _STAMP.fullmatch(value):
        return value
    return None


def _parse(stdout: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(stdout, parse_constant=_no_constant)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    mode, owner = raw.get("mode"), raw.get("owner")
    if mode not in MODES or not isinstance(owner, str):
        return None
    until = _stamp(raw.get("until"))
    if raw.get("until") is not None and until is None:
        return None
    return _doc(
        True,
        "",
        mode=mode,
        owner=owner if owner in OWNERS else "none",
        until=until,
        since=_stamp(raw.get("since")),
    )


def read_uplink() -> dict[str, Any]:
    """The ``uplink`` document. Always the same keys; ``present`` is false,
    with a reason in ``detail``, when the CLI is absent, fails or answers
    with something this helper does not recognize."""
    cli = find_cli()
    if cli is None:
        return _doc(False, f"{CLI_NAME} is not installed")
    shown = run((cli, "uplink", "status", "--json"))
    if shown.returncode == _TOOL_MISSING:
        return _doc(False, f"{CLI_NAME} is not installed")
    if not shown.ok:
        why = _first_line(shown.stderr) or f"exit {shown.returncode}"
        return _doc(False, f"{CLI_NAME} could not read the uplink: {why}")
    parsed = _parse(shown.stdout.strip())
    if parsed is None:
        return _doc(False, f"{CLI_NAME} printed an uplink status this helper does not recognize")
    return parsed


def switch(mode: str, duration: str) -> tuple[int, list[str]]:
    """Ask the manager for ``mode``. Returns ``(exit_code, problems)``.

    Exit 2 when the manager cannot be reached (nothing is run), 1 for a
    change that failed or did not read back, 0 for one that did.
    """
    cli = find_cli()
    before = read_uplink()
    if cli is None or not before["present"]:
        return 2, [f"the uplink switch is not available: {before['detail']}"]
    argv: tuple[str, ...] = (cli, "uplink", "auto")
    if mode == "cell-first":
        argv = (cli, "uplink", "cell-first", "--for", duration)
    result = run(argv)
    if not result.ok:
        why = _first_line(result.stderr) or f"exit {result.returncode}"
        return 1, [f"{CLI_NAME} uplink {mode} failed: {why}"]
    after = read_uplink()
    if not after["present"] or after["mode"] != mode:
        seen = after["mode"] or "unreadable"
        return 1, [f"the uplink was asked to be {mode} and reads {seen} afterwards"]
    if mode == "cell-first" and (after["until"] is None) != (duration == "0"):
        return 1, [f"the uplink is cell-first, but its expiry does not match the {duration} that was asked for"]
    return 0, []
