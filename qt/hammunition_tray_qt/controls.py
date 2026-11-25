# Hammunition Devices - tray for desktops other than Plasma
# Copyright (C) 2026 ChiefGyk3D
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Controls panel's services and radios (helper contract v1), with no Qt.

The helper answers ``hammunition-devctl services state`` and ``radio state``
with one JSON document each, without privilege. A user-scope service and a
radio are changed by running the helper directly; a system-scope service is
changed through ``pkexec``, with the same polkit action as park and wake.
Every sentence and every rule here is restated, word for word, in the Plasma
applet's ``controlslogic.js``; tests/test_controls_parity.py runs both over
the same helper documents and fails on any difference.

Nothing here runs a command. A name that came from the helper's output is
checked against the shape the helper itself accepts before it can reach an
argv, because the Plasma applet builds a shell string from it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime

# The helper contract version this tray speaks (docs/contract.md in the
# helper's branch). A document that says less than this is "update
# hammunition-tray", never an error; one that says more is read as far as
# this tray understands it. Recorded here and in controlslogic.js, and
# nowhere else; test_controls_parity holds the two equal.
CONTRACT_FLOOR = 1

HEADING = "Controls"
GROUP_DEVICES = "Devices"
GROUP_SERVICES = "Services"
GROUP_RADIOS = "Radios"
GROUP_UPLINK = "Uplink"
# What a group says when the installed helper has no such verb, or speaks an
# older contract. One line, not an error on every poll.
UPDATE = "update hammunition-tray"
LOGIN_LABEL = "Start at login"
READING_SERVICES = "Reading services…"
READING_RADIOS = "Reading radios…"
NO_SERVICES = "No services are listed"
NO_RADIOS = "No radios are listed"
SERVICES_READ_ERROR = "Could not read the services list"
SERVICES_PARSE_ERROR = "Could not parse the services list"
RADIOS_READ_ERROR = "Could not read the radios list"
RADIOS_PARSE_ERROR = "Could not parse the radios list"
HELPER_RUN_ERROR = "Could not run the device helper"
NOT_INSTALLED = "%s: not installed"
SERVICE_FAILED = "%s: failed"
SERVICE_STARTING = "%s: starting"
RADIO_UNAVAILABLE = "not available: %s"
RADIO_UNAVAILABLE_NO_TOOL = "not available"
READING_UPLINK = "Reading uplink…"
UPLINK_READ_ERROR = "Could not read the uplink state"
UPLINK_PARSE_ERROR = "Could not parse the uplink state"
UPLINK_UNAVAILABLE = "not available: %s"
UPLINK_UNAVAILABLE_NO_DETAIL = "not available"
UPLINK_AUTO_OWNER = "Auto: using %s"
UPLINK_AUTO_NONE = "Auto: no link has a route"
UPLINK_CELL_UNTIL = "Cell first until %s"
UPLINK_CELL_NO_EXPIRY = "Cell first, no expiry"
UPLINK_SWITCHING = "Switching to %s…"
UPLINK_DURATION_HEADING = "Cell first for"
UPLINK_CONFIRM = "Cell first uses mobile data %s. Turn it on?"
UPLINK_CONFIRM_YES = "Use mobile data"
UPLINK_CONFIRM_NO = "Cancel"

# Every fixed sentence, by name, so the parity test can compare them all.
STRINGS: dict[str, str] = {
    "heading": HEADING,
    "group_devices": GROUP_DEVICES,
    "group_services": GROUP_SERVICES,
    "group_radios": GROUP_RADIOS,
    "group_uplink": GROUP_UPLINK,
    "update": UPDATE,
    "login_label": LOGIN_LABEL,
    "reading_services": READING_SERVICES,
    "reading_radios": READING_RADIOS,
    "no_services": NO_SERVICES,
    "no_radios": NO_RADIOS,
    "services_read_error": SERVICES_READ_ERROR,
    "services_parse_error": SERVICES_PARSE_ERROR,
    "radios_read_error": RADIOS_READ_ERROR,
    "radios_parse_error": RADIOS_PARSE_ERROR,
    "helper_run_error": HELPER_RUN_ERROR,
    "reading_uplink": READING_UPLINK,
    "uplink_read_error": UPLINK_READ_ERROR,
    "uplink_parse_error": UPLINK_PARSE_ERROR,
    "uplink_unavailable_no_detail": UPLINK_UNAVAILABLE_NO_DETAIL,
    "uplink_auto_none": UPLINK_AUTO_NONE,
    "uplink_cell_no_expiry": UPLINK_CELL_NO_EXPIRY,
    "uplink_duration_heading": UPLINK_DURATION_HEADING,
    "uplink_confirm_yes": UPLINK_CONFIRM_YES,
    "uplink_confirm_no": UPLINK_CONFIRM_NO,
}

SERVICE_VERBS = ("start", "stop", "enable", "disable")
# The only radios the helper switches (`radio on|off wwan|wifi|bluetooth`).
RADIO_NAMES = ("wwan", "wifi", "bluetooth")
RADIO_LABELS = {
    "wwan": "Mobile broadband (WWAN)",
    "wifi": "Wi-Fi",
    "bluetooth": "Bluetooth",
}

# The uplink modes the helper accepts (`uplink auto|cell-first`), the closed
# list of durations this tray offers (`--for`; "0" is no expiry), and the one
# it starts on.
UPLINK_MODES = ("auto", "cell-first")
UPLINK_MODE_LABELS = {"auto": "Auto", "cell-first": "Cell first"}
UPLINK_DURATIONS = (
    ("30m", "30 minutes"),
    ("1h", "1 hour"),
    ("2h", "2 hours"),
    ("4h", "4 hours"),
    ("8h", "8 hours"),
    ("0", "No expiry"),
)
UPLINK_DEFAULT_DURATION = "2h"
_UPLINK_OWNERS = ("ethernet", "wifi", "cell", "none")
_UPLINK_OWNER_LABELS = {"ethernet": "Ethernet", "wifi": "Wi-Fi", "cell": "cellular"}
# An ISO 8601 stamp with an offset: the only form both languages read alike.
_STAMP = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?"
    r"(?:Z|[+-]([0-9]{2}):([0-9]{2}))"
)

_ACTIVE = ("active", "inactive", "failed", "activating", "unknown")
_ENABLED = ("enabled", "disabled", "static", "not-found", "unknown")
_SCOPES = ("user", "system")
# The helper's own shape for a name from its allow-list files.
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class ControlsError(ValueError):
    """The helper's output is not the document it always prints."""


@dataclass(frozen=True)
class ServiceRow:
    name: str
    unit: str
    scope: str
    description: str
    active: str
    enabled: str
    root: bool


@dataclass(frozen=True)
class ServicesDoc:
    rows: tuple[ServiceRow, ...]
    linger_state: str | None = None


@dataclass(frozen=True)
class RadioRow:
    name: str
    present: bool
    enabled: bool
    method: str
    detail: str


@dataclass(frozen=True)
class UplinkRow:
    """``uplink state``. ``switching`` is only ever true on a row from
    :func:`effective_uplink`: the operator asked for ``mode`` and no poll has
    confirmed it."""

    present: bool
    mode: str
    owner: str
    until: str | None
    detail: str
    switching: bool = False


# -- parsing ---------------------------------------------------------------


def _text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


def _no_constant(name: str) -> object:
    # Python reads NaN and Infinity where JSON, and JavaScript's parser, do not.
    raise ValueError(f"{name} is not JSON")


def _document(stdout: str, kind: str) -> dict[str, object]:
    try:
        doc = json.loads(stdout, parse_constant=_no_constant)
    except ValueError as exc:
        raise ControlsError(str(exc)) from exc
    if not isinstance(doc, dict) or doc.get("kind") != kind:
        raise ControlsError(f"not a {kind} document")
    return doc


def _version(doc: dict[str, object]) -> int:
    v = doc.get("version")
    # JSON has one number type: 1.0 is version 1, as JavaScript reads it.
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
        return 0
    return int(v)


def parse_services(stdout: str) -> ServicesDoc:
    doc = _document(stdout, "services")
    rows = doc.get("services")
    if not isinstance(rows, list):
        raise ControlsError("no services list")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ControlsError("a row is not an object")
        name, scope = row.get("name"), row.get("scope")
        if not isinstance(name, str) or not name or scope not in _SCOPES:
            raise ControlsError("a row has no name or a scope this tray does not know")
        active, enabled = _text(row, "active"), _text(row, "enabled")
        out.append(
            ServiceRow(
                name=name,
                unit=_text(row, "unit"),
                scope=scope,
                description=_text(row, "description"),
                # A state a newer helper might add reads as unknown, which
                # nothing offers a switch for.
                active=active if active in _ACTIVE else "unknown",
                enabled=enabled if enabled in _ENABLED else "unknown",
                root=row.get("root") is True,
            )
        )
    linger = doc.get("linger")
    state = linger.get("state") if isinstance(linger, dict) else None
    return ServicesDoc(rows=tuple(out), linger_state=state if isinstance(state, str) else None)


def parse_radios(stdout: str) -> tuple[RadioRow, ...]:
    doc = _document(stdout, "radios")
    rows = doc.get("radios")
    if not isinstance(rows, list):
        raise ControlsError("no radios list")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ControlsError("a row is not an object")
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise ControlsError("a row has no name")
        out.append(
            RadioRow(
                name=name,
                present=row.get("present") is True,
                enabled=row.get("enabled") is True,
                method=_text(row, "method"),
                detail=_text(row, "detail"),
            )
        )
    return tuple(out)


def _stamp_ok(text: object) -> bool:
    """A real calendar date and clock time with an offset. Restated, field by
    field, in controlslogic.js: JavaScript's own parser is more forgiving."""
    if not isinstance(text, str):
        return False
    found = _STAMP.fullmatch(text)
    if found is None:
        return False
    year, month, day, hour, minute, second, off_h, off_m = found.groups()
    try:
        datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
    except ValueError:
        return False
    return (off_h is None or int(off_h) <= 23) and (off_m is None or int(off_m) <= 59)


def parse_uplink(stdout: str) -> UplinkRow:
    doc = _document(stdout, "uplink")
    present = doc.get("present") is True
    if not present:
        return UplinkRow(False, "", "", None, _text(doc, "detail"))
    mode = doc.get("mode")
    if mode not in UPLINK_MODES:
        raise ControlsError("the uplink has no mode this tray knows")
    until = doc.get("until")
    if until is not None and not _stamp_ok(until):
        raise ControlsError("the uplink's expiry is not a stamp")
    owner = doc.get("owner")
    return UplinkRow(
        True,
        str(mode),
        owner if isinstance(owner, str) and owner in _UPLINK_OWNERS else "none",
        until,
        _text(doc, "detail"),
    )


@dataclass(frozen=True)
class GroupOutcome:
    """What one poll means. ``doc`` is a ServicesDoc, a tuple of RadioRow, an
    UplinkRow, or None. ``keep`` is true when the last good rows should stay on screen
    (a failed read, as the device list does)."""

    doc: ServicesDoc | tuple[RadioRow, ...] | UplinkRow | None = None
    unsupported: bool = False
    error: str = ""
    keep: bool = False


def _argparse_refusal(stderr: str) -> bool:
    low = stderr.lower()
    return "invalid choice" in low or "usage:" in low


def poll_outcome(
    kind: str, started: bool, crashed: bool, code: int, stdout: str, stderr: str
) -> GroupOutcome:
    if kind not in ("services", "radios", "uplink"):
        raise ValueError(f"no such group {kind!r}")
    read_error, parse_error = {
        "services": (SERVICES_READ_ERROR, SERVICES_PARSE_ERROR),
        "radios": (RADIOS_READ_ERROR, RADIOS_PARSE_ERROR),
        "uplink": (UPLINK_READ_ERROR, UPLINK_PARSE_ERROR),
    }[kind]
    # Not there at all: the device poll says so in its own words, and the
    # groups are hidden with it.
    if not started or (not crashed and code == 127):
        return GroupOutcome()
    # A helper without this verb: argparse refuses it, exit 2, "invalid
    # choice". Said once, as the group's one line; the poll keeps asking, so
    # updating the helper brings the group in without a new login. The
    # helper's own refusals are exit 2 too (contract: "error: ..."), and
    # those are errors, not a request to update.
    if not crashed and code == 2 and _argparse_refusal(stderr):
        return GroupOutcome(unsupported=True)
    if crashed or code != 0:
        return GroupOutcome(error=stderr.strip() or read_error, keep=True)
    try:
        doc: ServicesDoc | tuple[RadioRow, ...] | UplinkRow
        if kind == "services":
            doc = parse_services(stdout.strip())
        elif kind == "radios":
            doc = parse_radios(stdout.strip())
        else:
            doc = parse_uplink(stdout.strip())
        # Parsed once already, so this cannot fail.
        version = _version(json.loads(stdout.strip(), parse_constant=_no_constant))
    except ControlsError:
        # A document with no version cannot say it speaks this contract, but
        # an unreadable one is a parse error before it is anything else.
        return GroupOutcome(error=parse_error, keep=True)
    if version < CONTRACT_FLOOR:
        return GroupOutcome(unsupported=True)
    return GroupOutcome(doc=doc)


def services_poll_argv(helper: str) -> tuple[str, list[str]]:
    # No pkexec: asking systemd for a unit's state needs no privilege.
    return helper, ["services", "state"]


def radios_poll_argv(helper: str) -> tuple[str, list[str]]:
    return helper, ["radio", "state"]


def uplink_poll_argv(helper: str) -> tuple[str, list[str]]:
    # No pkexec, no sudo: the link-priority manager runs as the user.
    return helper, ["uplink", "state"]


# -- the rules, and the words ------------------------------------------------


def _installed(row: ServiceRow) -> bool:
    return row.enabled != "not-found"


def run_checked(row: ServiceRow) -> bool:
    return row.active in ("active", "activating")


def run_verb(row: ServiceRow) -> str:
    return "stop" if run_checked(row) else "start"


def run_enabled(row: ServiceRow, acting: bool) -> bool:
    return not acting and _installed(row) and row.active != "unknown"


def login_checked(row: ServiceRow) -> bool:
    return row.enabled == "enabled"


def login_verb(row: ServiceRow) -> str:
    return "disable" if login_checked(row) else "enable"


def login_enabled(row: ServiceRow, acting: bool) -> bool:
    # `static` units have no [Install] section: there is nothing to enable.
    return not acting and row.enabled in ("enabled", "disabled")


def service_label(row: ServiceRow) -> str:
    return row.name


def service_detail(row: ServiceRow) -> str:
    if not _installed(row):
        return NOT_INSTALLED % row.description
    if row.active == "failed":
        return SERVICE_FAILED % row.description
    if row.active == "activating":
        return SERVICE_STARTING % row.description
    return row.description


def radio_label(row: RadioRow) -> str:
    return RADIO_LABELS.get(row.name, row.name)


def radio_detail(row: RadioRow) -> str:
    if not row.present:
        return RADIO_UNAVAILABLE % row.detail if row.detail else RADIO_UNAVAILABLE_NO_TOOL
    return row.detail


def radio_verb(row: RadioRow) -> str:
    return "off" if row.enabled else "on"


def radio_enabled(row: RadioRow, acting: bool) -> bool:
    return not acting and row.present and row.name in RADIO_NAMES


def uplink_mode_label(mode: str) -> str:
    return UPLINK_MODE_LABELS.get(mode, mode)


def uplink_duration_label(duration: str) -> str:
    for value, label in UPLINK_DURATIONS:
        if value == duration:
            return label
    return duration


def uplink_checked(row: UplinkRow, mode: str) -> bool:
    return row.present and row.mode == mode


def uplink_enabled(row: UplinkRow, acting: bool) -> bool:
    return not acting and row.present


def uplink_duration_enabled(row: UplinkRow, acting: bool) -> bool:
    return not acting and row.present


def uplink_needs_confirm(mode: str) -> bool:
    """Cell first uses mobile data and asks first; going back to Auto never does."""
    return mode == "cell-first"


def uplink_confirm_text(duration: str) -> str:
    when = "until you switch back to Auto" if duration == "0" else "for " + uplink_duration_label(duration)
    return UPLINK_CONFIRM % when


def until_text(until: str, now: float) -> str:
    """When cell first ends, in the operator's local time: ``HH:MM`` if that is
    today, else ``YYYY-MM-DD HH:MM``. ``now`` is epoch seconds; the stamp has
    been checked by :func:`_stamp_ok` already."""
    when = datetime.fromisoformat(until).astimezone()
    if when.date() == datetime.fromtimestamp(now).date():
        return when.strftime("%H:%M")
    return when.strftime("%Y-%m-%d %H:%M")


def uplink_indicator(row: UplinkRow, now: float) -> str:
    """The one line that says where the default routes are and, for cell
    first, when that ends."""
    if not row.present:
        return UPLINK_UNAVAILABLE % row.detail if row.detail else UPLINK_UNAVAILABLE_NO_DETAIL
    if row.switching:
        return UPLINK_SWITCHING % uplink_mode_label(row.mode)
    if row.mode == "cell-first":
        return UPLINK_CELL_UNTIL % until_text(row.until, now) if row.until else UPLINK_CELL_NO_EXPIRY
    if row.owner in _UPLINK_OWNER_LABELS:
        return UPLINK_AUTO_OWNER % _UPLINK_OWNER_LABELS[row.owner]
    return UPLINK_AUTO_NONE


# -- argv, and only the argv the helper accepts -------------------------------


def service_argv(pkexec: str, helper: str, row: ServiceRow, verb: str) -> tuple[str, list[str]]:
    """User scope runs the helper directly; system scope goes through pkexec
    by its path. The name must have the helper's own shape."""
    if verb not in SERVICE_VERBS:
        raise ValueError(f"refusing service verb {verb!r}")
    if not _NAME.fullmatch(row.name):
        raise ValueError(f"refusing service name {row.name!r}: not an allow-list name")
    if row.scope == "user":
        return helper, ["services", verb, row.name]
    if row.scope == "system":
        return pkexec, [helper, "services", verb, row.name]
    raise ValueError(f"refusing service scope {row.scope!r}")


def uses_pkexec(row: ServiceRow) -> bool:
    return row.scope == "system"


def radio_argv(helper: str, row: RadioRow, on: bool) -> tuple[str, list[str]]:
    if row.name not in RADIO_NAMES:
        raise ValueError(f"refusing radio {row.name!r}")
    return helper, ["radio", "on" if on else "off", row.name]


def uplink_argv(helper: str, mode: str, duration: str) -> tuple[str, list[str]]:
    """The helper directly, never pkexec. The duration must be one this tray
    offers, so nothing else reaches the CLI's ``--for``."""
    if mode not in UPLINK_MODES:
        raise ValueError(f"refusing uplink mode {mode!r}")
    if duration not in dict(UPLINK_DURATIONS):
        raise ValueError(f"refusing uplink duration {duration!r}")
    if mode == "auto":
        return helper, ["uplink", "auto"]
    return helper, ["uplink", "cell-first", "--for", duration]


def direct_error(started: bool, crashed: bool, code: int, stderr: str) -> str:
    """The one line for a verb run without pkexec that did not succeed, or
    "" when it did. The helper's first non-empty stderr line is its reason;
    a pkexec verb has its own rules (logic.apply_action)."""
    if not started or crashed:
        return HELPER_RUN_ERROR
    if code == 0:
        return ""
    # Split on newline only, as controlslogic.js does.
    for line in stderr.split("\n"):
        if line.strip():
            return line.strip()
    return f"Action failed (exit {code})"


# -- what the operator just asked for, until a poll says otherwise -----------

Pending = tuple[tuple[str, "str | bool"], ...]

_EXPECTED = {
    "start": ("active", "active"),
    "stop": ("active", "inactive"),
    "enable": ("enabled", "enabled"),
    "disable": ("enabled", "disabled"),
}


def service_pending(verb: str, name: str) -> tuple[str, str]:
    field, value = _EXPECTED[verb]
    return f"service:{name}:{field}", value


def radio_pending(name: str, on: bool) -> tuple[str, bool]:
    return f"radio:{name}:enabled", on


def uplink_pending(mode: str) -> tuple[str, str]:
    return "uplink:mode", mode


def pending_fresh(started_epoch: int | None, epoch: int, acting: bool) -> bool:
    """May a poll that has just landed end the operator's pending requests?
    Only one that started after the last verb finished: one that was already
    running when a verb began describes a world from before it, and one that
    lands while a verb is running has not seen its effect. ``None`` is a
    caller with no epoch to give, which is "now"."""
    return not acting and (started_epoch is None or started_epoch == epoch)


def effective_services(rows: tuple[ServiceRow, ...], pending: Pending) -> tuple[ServiceRow, ...]:
    """The rows as the operator would see them if every pending request had
    worked. The real rows are never changed."""
    want = dict(pending)
    out = []
    for row in rows:
        active = want.get(f"service:{row.name}:active")
        enabled = want.get(f"service:{row.name}:enabled")
        out.append(
            replace(
                row,
                active=active if isinstance(active, str) else row.active,
                enabled=enabled if isinstance(enabled, str) else row.enabled,
            )
        )
    return tuple(out)


def effective_radios(rows: tuple[RadioRow, ...], pending: Pending) -> tuple[RadioRow, ...]:
    want = dict(pending)
    out = []
    for row in rows:
        on = want.get(f"radio:{row.name}:enabled")
        out.append(replace(row, enabled=on if isinstance(on, bool) else row.enabled))
    return tuple(out)


def effective_uplink(row: UplinkRow, pending: Pending) -> UplinkRow:
    """The row as the operator would see it if their request had worked: the
    mode they asked for, marked as switching (its expiry is not known yet)."""
    want = dict(pending).get("uplink:mode")
    if not row.present or not isinstance(want, str) or want == row.mode:
        return row
    return replace(row, mode=want, until=None, switching=True)
