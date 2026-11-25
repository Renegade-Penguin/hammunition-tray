.pragma library
/*
 * Hammunition Devices - Plasma 6 applet
 * Copyright (C) 2026 ChiefGyk3D
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The Controls panel's Services, Radios and Uplink groups (helper contract v1), with
 * nothing of QML in them. This is qt/hammunition_tray_qt/controls.py
 * restated; the Qt tray runs that one. tests/test_controls_parity.py runs
 * both over the same helper documents and fails on any difference, so every
 * sentence and rule here must match it.
 *
 * Nothing here runs a command, but the applet builds a shell string from
 * what these functions return, so a name that came from the helper's output
 * is checked against the shape the helper itself accepts before it can reach
 * an argv.
 *
 * A library script has no QML context, so it cannot reach i18n itself: every
 * function that words something takes main.qml's `tr`, which is i18n.
 */

// The helper contract version this applet speaks. A document that says less
// is "update hammunition-tray", never an error; one that says more is read
// as far as this applet understands it. Recorded here and in controls.py,
// and nowhere else.
var CONTRACT_FLOOR = 1;

var SERVICE_VERBS = ["start", "stop", "enable", "disable"];
// The only radios the helper switches (`radio on|off wwan|wifi|bluetooth`).
var RADIO_NAMES = ["wwan", "wifi", "bluetooth"];

var ACTIVE = ["active", "inactive", "failed", "activating", "unknown"];
var ENABLED = ["enabled", "disabled", "static", "not-found", "unknown"];
var SCOPES = ["user", "system"];

// The uplink modes the helper accepts (`uplink auto|cell-first`), the closed
// list of durations this applet offers (`--for`; "0" is no expiry) and the one
// it starts on. controls.py has the same tables.
var UPLINK_MODES = ["auto", "cell-first"];
var UPLINK_DURATIONS = [["30m", "30 minutes"], ["1h", "1 hour"], ["2h", "2 hours"],
                        ["4h", "4 hours"], ["8h", "8 hours"], ["0", "No expiry"]];
var UPLINK_DEFAULT_DURATION = "2h";
var UPLINK_OWNERS = ["ethernet", "wifi", "cell", "none"];
// An ISO 8601 stamp with an offset: the only form both languages read alike.
var STAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-](\d{2}):(\d{2}))$/;

// The helper's own shape for a name from its allow-list files.
var NAME = /^[a-z0-9][a-z0-9-]{0,63}$/;

function sameRows(a, b) {
    if (a === b) return true;
    if (a === null || b === null || typeof a !== typeof b) return false;
    if (Array.isArray(a)) {
        if (!Array.isArray(b) || a.length !== b.length) return false;
        for (var i = 0; i < a.length; i++)
            if (!sameRows(a[i], b[i])) return false;
        return true;
    }
    if (typeof a !== "object" || Array.isArray(b)) return false;
    var aKeys = Object.keys(a);
    var bKeys = Object.keys(b);
    if (aKeys.length !== bKeys.length) return false;
    for (var j = 0; j < aKeys.length; j++) {
        var key = aKeys[j];
        if (!Object.prototype.hasOwnProperty.call(b, key) || !sameRows(a[key], b[key]))
            return false;
    }
    return true;
}

// Every fixed sentence, by name; controls.py's STRINGS is the same table.
function strings(tr) {
    return {
        heading: tr("Controls"),
        group_devices: tr("Devices"),
        group_services: tr("Services"),
        group_radios: tr("Radios"),
        group_uplink: tr("Uplink"),
        repair_label: tr("Network Repair"),
        update: tr("update hammunition-tray"),
        login_label: tr("Start at login"),
        reading_services: tr("Reading services…"),
        reading_radios: tr("Reading radios…"),
        no_services: tr("No services are listed"),
        no_radios: tr("No radios are listed"),
        services_read_error: tr("Could not read the services list"),
        services_parse_error: tr("Could not parse the services list"),
        radios_read_error: tr("Could not read the radios list"),
        radios_parse_error: tr("Could not parse the radios list"),
        helper_run_error: tr("Could not run the device helper"),
        reading_uplink: tr("Reading uplink…"),
        uplink_read_error: tr("Could not read the uplink state"),
        uplink_parse_error: tr("Could not parse the uplink state"),
        uplink_unavailable_no_detail: tr("not available"),
        uplink_auto_none: tr("Auto: no link has a route"),
        uplink_cell_no_expiry: tr("Network Repair: cellular first, no expiry"),
        uplink_duration_heading: tr("Network Repair for"),
        uplink_confirm_yes: tr("Use mobile data"),
        uplink_confirm_no: tr("Cancel")
    };
}

function text(row, key) {
    var v = row[key];
    return typeof v === "string" ? v : "";
}

function document_(stdout, kind) {
    var doc = JSON.parse(stdout);
    if (doc === null || typeof doc !== "object" || Array.isArray(doc) || doc.kind !== kind)
        throw new Error("not a " + kind + " document");
    return doc;
}

function version(doc) {
    var v = doc.version;
    return typeof v === "number" && Math.floor(v) === v ? v : 0;
}

// Throws on anything but the document the helper always prints.
function parseServices(stdout) {
    var doc = document_(stdout, "services");
    if (!Array.isArray(doc.services)) throw new Error("no services list");
    var rows = doc.services.map(function (row) {
        if (row === null || typeof row !== "object" || Array.isArray(row))
            throw new Error("a row is not an object");
        if (typeof row.name !== "string" || row.name === "" || SCOPES.indexOf(row.scope) === -1)
            throw new Error("a row has no name or a scope this applet does not know");
        var active = text(row, "active");
        var enabled = text(row, "enabled");
        return {
            name: row.name,
            unit: text(row, "unit"),
            scope: row.scope,
            description: text(row, "description"),
            // A state a newer helper might add reads as unknown, which
            // nothing offers a switch for.
            active: ACTIVE.indexOf(active) === -1 ? "unknown" : active,
            enabled: ENABLED.indexOf(enabled) === -1 ? "unknown" : enabled,
            root: row.root === true
        };
    });
    var state = doc.linger !== null && typeof doc.linger === "object" ? doc.linger.state : null;
    return { rows: rows, linger_state: typeof state === "string" ? state : null };
}

function parseRadios(stdout) {
    var doc = document_(stdout, "radios");
    if (!Array.isArray(doc.radios)) throw new Error("no radios list");
    return doc.radios.map(function (row) {
        if (row === null || typeof row !== "object" || Array.isArray(row))
            throw new Error("a row is not an object");
        if (typeof row.name !== "string" || row.name === "") throw new Error("a row has no name");
        return {
            name: row.name,
            present: row.present === true,
            enabled: row.enabled === true,
            method: text(row, "method"),
            detail: text(row, "detail")
        };
    });
}

// A real calendar date and clock time with an offset; JavaScript's own parser
// is more forgiving, so the fields are checked one by one (controls.py's
// _stamp_ok does the same).
function stampOk(text) {
    if (typeof text !== "string") return false;
    var m = STAMP.exec(text);
    if (m === null) return false;
    var year = Number(m[1]), month = Number(m[2]), day = Number(m[3]);
    var hour = Number(m[4]), minute = Number(m[5]), second = Number(m[6]);
    var d = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
    d.setUTCFullYear(year);
    if (d.getUTCFullYear() !== year || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day
        || hour > 23 || minute > 59 || second > 59)
        return false;
    return (m[7] === undefined || Number(m[7]) <= 23) && (m[8] === undefined || Number(m[8]) <= 59);
}

// Throws on anything but the document the helper always prints.
function parseUplink(stdout) {
    var doc = document_(stdout, "uplink");
    if (doc.present !== true)
        return { present: false, mode: "", owner: "", until: null, detail: text(doc, "detail"), switching: false };
    if (UPLINK_MODES.indexOf(doc.mode) === -1) throw new Error("the uplink has no mode this applet knows");
    var until = doc.until === undefined ? null : doc.until;
    if (until !== null && !stampOk(until)) throw new Error("the uplink's expiry is not a stamp");
    return {
        present: true,
        mode: doc.mode,
        owner: typeof doc.owner === "string" && UPLINK_OWNERS.indexOf(doc.owner) !== -1 ? doc.owner : "none",
        until: until,
        detail: text(doc, "detail"),
        switching: false
    };
}

function argparseRefusal(stderr) {
    var low = (stderr || "").toLowerCase();
    return low.indexOf("invalid choice") !== -1 || low.indexOf("usage:") !== -1;
}

// {doc, unsupported, error, keep}: keep means the last good rows stay on
// screen, as the device list does after a failed read. kind is "services",
// "radios" or "uplink".
function pollOutcome(kind, code, stdout, stderr, tr) {
    var s = strings(tr);
    var readError = s[kind + "_read_error"];
    var parseError = s[kind + "_parse_error"];
    // Not there: the device poll says so, and the groups hide with it.
    if (code === 127) return { doc: null, unsupported: false, error: "", keep: false };
    // A helper without this verb: argparse refuses it, exit 2, "invalid
    // choice". Said once, as the group's one line, never as an error on
    // every poll. The helper's own refusals are exit 2 too, and those are
    // errors, not a request to update.
    if (code === 2 && argparseRefusal(stderr)) return { doc: null, unsupported: true, error: "", keep: false };
    if (code !== 0) {
        var err = (stderr || "").trim();
        return { doc: null, unsupported: false, error: err !== "" ? err : readError, keep: true };
    }
    var doc, parsed;
    try {
        var body = (stdout || "").trim();
        doc = kind === "services" ? parseServices(body)
            : kind === "radios" ? parseRadios(body) : parseUplink(body);
        parsed = JSON.parse(body);
    } catch (e) {
        return { doc: null, unsupported: false, error: parseError, keep: true };
    }
    if (version(parsed) < CONTRACT_FLOOR)
        return { doc: null, unsupported: true, error: "", keep: false };
    return { doc: doc, unsupported: false, error: "", keep: false };
}

function installed(row) {
    return row.enabled !== "not-found";
}

function runChecked(row) {
    return row.active === "active" || row.active === "activating";
}

function runVerb(row) {
    return runChecked(row) ? "stop" : "start";
}

function runEnabled(row, acting) {
    return !acting && installed(row) && row.active !== "unknown";
}

function loginChecked(row) {
    return row.enabled === "enabled";
}

function loginVerb(row) {
    return loginChecked(row) ? "disable" : "enable";
}

// `static` units have no [Install] section: there is nothing to enable.
function loginEnabled(row, acting) {
    return !acting && (row.enabled === "enabled" || row.enabled === "disabled");
}

function serviceLabel(row) {
    return row.name;
}

function serviceDetail(row, tr) {
    if (!installed(row)) return tr("%1: not installed", row.description);
    if (row.active === "failed") return tr("%1: failed", row.description);
    if (row.active === "activating") return tr("%1: starting", row.description);
    return row.description;
}

function radioLabel(row, tr) {
    switch (row.name) {
    case "wwan": return tr("Mobile broadband (WWAN)");
    case "wifi": return tr("Wi-Fi");
    case "bluetooth": return tr("Bluetooth");
    }
    return row.name;
}

function radioDetail(row, tr) {
    if (!row.present)
        return row.detail !== "" ? tr("not available: %1", row.detail) : tr("not available");
    return row.detail;
}

function radioVerb(row) {
    return row.enabled ? "off" : "on";
}

function radioEnabled(row, acting) {
    return !acting && row.present && RADIO_NAMES.indexOf(row.name) !== -1;
}

function uplinkModeLabel(mode, tr) {
    switch (mode) {
    case "auto": return tr("Auto");
    case "cell-first": return tr("Network Repair");
    }
    return mode;
}

function uplinkDurationLabel(duration, tr) {
    switch (duration) {
    case "30m": return tr("30 minutes");
    case "1h": return tr("1 hour");
    case "2h": return tr("2 hours");
    case "4h": return tr("4 hours");
    case "8h": return tr("8 hours");
    case "0": return tr("No expiry");
    }
    return duration;
}

function uplinkChecked(row, mode) {
    return row.present && row.mode === mode;
}

function uplinkEnabled(row, acting) {
    return !acting && row.present;
}

function uplinkDurationEnabled(row, acting) {
    return !acting && row.present;
}

// One click on Network Repair, the owner's name for the CLI's cell-first:
// whether it is on, what a click asks for, and the tooltip line while it is on.
function repairActive(row) {
    return row.present && row.mode === "cell-first";
}

function repairNextMode(row) {
    return repairActive(row) ? "auto" : "cell-first";
}

function repairEnabled(row, acting) {
    return !acting && row.present;
}

function repairTooltip(row, now, tr) {
    return repairActive(row) ? uplinkIndicator(row, now, tr) : "";
}

// Network Repair uses mobile data and asks first; going back to Auto never does.
function uplinkNeedsConfirm(mode) {
    return mode === "cell-first";
}

function uplinkConfirmText(duration, tr) {
    var when = duration === "0" ? tr("until you turn it off")
        : tr("until you turn it off or it expires in %1", uplinkDurationLabel(duration, tr));
    return tr("Network Repair makes cellular the main connection and takes Wi-Fi and Ethernet "
        + "out of the default route %1. The VPN will reconnect over cellular. "
        + "Cellular data is metered. Turn it on?", when);
}

function pad2(n) {
    return n < 10 ? "0" + n : String(n);
}

// When Network Repair ends, in the operator's local time: HH:MM if that is today,
// else YYYY-MM-DD HH:MM. `now` is epoch seconds.
function untilText(until, now) {
    var when = new Date(until);
    var today = new Date(now * 1000);
    var clock = pad2(when.getHours()) + ":" + pad2(when.getMinutes());
    if (when.getFullYear() === today.getFullYear() && when.getMonth() === today.getMonth()
        && when.getDate() === today.getDate())
        return clock;
    return when.getFullYear() + "-" + pad2(when.getMonth() + 1) + "-" + pad2(when.getDate()) + " " + clock;
}

// The one line that says where the default routes are and, for Network Repair,
// when that ends.
function uplinkIndicator(row, now, tr) {
    if (!row.present)
        return row.detail !== "" ? tr("not available: %1", row.detail) : tr("not available");
    if (row.switching) return tr("Switching to %1…", uplinkModeLabel(row.mode, tr));
    if (row.mode === "cell-first")
        return row.until !== null ? tr("Network Repair: cellular first, until %1", untilText(row.until, now))
            : tr("Network Repair: cellular first, no expiry");
    switch (row.owner) {
    case "ethernet": return tr("Auto: using %1", tr("Ethernet"));
    case "wifi": return tr("Auto: using %1", tr("Wi-Fi"));
    case "cell": return tr("Auto: using %1", tr("cellular"));
    }
    return tr("Auto: no link has a route");
}

function usesPkexec(row) {
    return row.scope === "system";
}

// The argv words, program first. User scope runs the helper directly, system
// scope goes through pkexec by its path; anything the helper would not
// accept throws, so nothing odd reaches the shell string main.qml builds.
function serviceArgv(pkexec, helper, row, verb) {
    if (SERVICE_VERBS.indexOf(verb) === -1) throw new Error("refusing service verb");
    if (!NAME.test(row.name)) throw new Error("refusing service name");
    if (row.scope === "user") return [helper, "services", verb, row.name];
    if (row.scope === "system") return [pkexec, helper, "services", verb, row.name];
    throw new Error("refusing service scope");
}

function radioArgv(helper, row, on) {
    if (RADIO_NAMES.indexOf(row.name) === -1) throw new Error("refusing radio");
    return [helper, "radio", on ? "on" : "off", row.name];
}

function uplinkPollArgv(helper) {
    return [helper, "uplink", "state"];
}

// The helper directly, never pkexec or sudo. The duration must be one this
// applet offers, so nothing else reaches the CLI's --for.
function uplinkArgv(helper, mode, duration) {
    if (UPLINK_MODES.indexOf(mode) === -1) throw new Error("refusing uplink mode");
    var known = UPLINK_DURATIONS.some(function (d) { return d[0] === duration; });
    if (!known) throw new Error("refusing uplink duration");
    if (mode === "auto") return [helper, "uplink", "auto"];
    return [helper, "uplink", "cell-first", "--for", duration];
}

// The one line for a verb run without pkexec that did not succeed, or "".
// The helper's first non-empty stderr line is its reason.
// May a poll that has just landed end the operator's pending requests? Only
// one that started after the last verb finished (see controls.py).
function pendingFresh(startedEpoch, epoch, acting) {
    return !acting && (startedEpoch === null || startedEpoch === epoch);
}

function directError(code, stderr, tr) {
    if (code === 0) return "";
    var lines = (stderr || "").split("\n");
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (line !== "") return line;
    }
    return tr("Action failed (exit %1)", code);
}

// What the operator just asked for, until a poll says otherwise: a map from
// "service:NAME:active" | "service:NAME:enabled" | "radio:NAME:enabled" to
// the value that request expects.
function servicePending(verb, name) {
    switch (verb) {
    case "start": return ["service:" + name + ":active", "active"];
    case "stop": return ["service:" + name + ":active", "inactive"];
    case "enable": return ["service:" + name + ":enabled", "enabled"];
    case "disable": return ["service:" + name + ":enabled", "disabled"];
    }
    throw new Error("refusing service verb");
}

function radioPending(name, on) {
    return ["radio:" + name + ":enabled", on];
}

function uplinkPending(mode) {
    return ["uplink:mode", mode];
}

function copy(row) {
    var out = {};
    for (var k in row) out[k] = row[k];
    return out;
}

// The rows as the operator would see them if every pending request had
// worked. The real rows are never changed.
function effectiveServices(rows, pending) {
    return rows.map(function (row) {
        var out = copy(row);
        var active = pending["service:" + row.name + ":active"];
        var enabled = pending["service:" + row.name + ":enabled"];
        if (typeof active === "string") out.active = active;
        if (typeof enabled === "string") out.enabled = enabled;
        return out;
    });
}

function effectiveRadios(rows, pending) {
    return rows.map(function (row) {
        var out = copy(row);
        var on = pending["radio:" + row.name + ":enabled"];
        if (typeof on === "boolean") out.enabled = on;
        return out;
    });
}

// The row as the operator would see it if their request had worked: the mode
// they asked for, marked as switching (its expiry is not known yet).
function effectiveUplink(row, pending) {
    var want = pending["uplink:mode"];
    if (!row.present || typeof want !== "string" || want === row.mode) return row;
    var out = copy(row);
    out.mode = want;
    out.until = null;
    out.switching = true;
    return out;
}
