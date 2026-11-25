"""Network Repair: the owner's one-click name for the uplink's ``cell-first``.

The CLI and helper contract keep ``cell-first`` (other code depends on it);
only what the owner sees is renamed. Runs in a fixed time zone, because the
expiry is shown in the operator's local time. The applet's JavaScript is held
to these rules by test_controls_parity; the Plasma files by
test_applet_package; the real Tray by test_qt_smoke.
"""

import json
import os
import re
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qt"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from controls_fixtures import UPLINK_NOW, UPLINKS  # noqa: E402
from hammunition_tray_qt import controls, logic  # noqa: E402
from hammunition_tray_qt.logic import ProcResult, TrayState  # noqa: E402

HELPER = "/usr/local/libexec/hammunition-devctl"


def ok(stdout="", code=0, stderr=""):
    return ProcResult(started=True, crashed=False, code=code, stdout=stdout, stderr=stderr)


def uplink(name):
    return controls.parse_uplink(json.dumps(UPLINKS[name]))


def with_uplink(name="auto-wifi"):
    return logic.apply_uplink_poll(TrayState(devices=()), ok(json.dumps(UPLINKS[name])))


class InUtc(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._old
        time.tzset()


class Label(unittest.TestCase):
    def test_the_label_is_network_repair(self):
        self.assertEqual(controls.REPAIR_LABEL, "Network Repair")
        self.assertEqual(controls.STRINGS["repair_label"], "Network Repair")
        self.assertEqual(controls.uplink_mode_label("cell-first"), "Network Repair")

    def test_the_underlying_mode_and_argv_are_unchanged(self):
        self.assertEqual(controls.UPLINK_MODES, ("auto", "cell-first"))
        self.assertEqual(
            controls.uplink_argv(HELPER, "cell-first", "2h"), (HELPER, ["uplink", "cell-first", "--for", "2h"])
        )
        self.assertEqual(controls.uplink_argv(HELPER, "auto", "2h"), (HELPER, ["uplink", "auto"]))
        self.assertEqual(controls.uplink_poll_argv(HELPER), (HELPER, ["uplink", "state"]))

    def test_the_old_name_is_nowhere_the_owner_can_read_it(self):
        # Guards the guard: it must find something to read at all.
        files = [
            ROOT / "qt/hammunition_tray_qt/controls.py",
            ROOT / "qt/hammunition_tray_qt/logic.py",
            ROOT / "qt/hammunition_tray_qt/tray.py",
            ROOT / "plasmoid/package/contents/ui/controlslogic.js",
            ROOT / "plasmoid/package/contents/ui/main.qml",
            ROOT / "plasmoid/package/contents/ui/FullRepresentation.qml",
            ROOT / "plasmoid/package/contents/ui/CompactRepresentation.qml",
            ROOT / "README.md",
            ROOT / "docs/contract.md",
            ROOT / "CHANGELOG.md",
        ]
        self.assertTrue(all(f.is_file() for f in files))
        for f in files:
            text = f.read_text()
            if f.name in ("controls.py", "controlslogic.js", "README.md", "contract.md"):
                self.assertIn("Network Repair", text, f.name)
            self.assertIsNone(re.search(r"cell first", text, re.I), f"{f.name} still says Cell first")


class Rules(InUtc):
    def test_active_only_for_a_present_cell_first(self):
        want = {
            "auto-wifi": False, "auto-ethernet": False, "auto-cell": False, "auto-none": False,
            "cell-first": True, "cell-first-offset": True, "cell-first-no-expiry": True,
            "missing": False, "failed": False, "no-detail": False,
        }
        for name, active in want.items():
            with self.subTest(doc=name):
                self.assertIs(controls.repair_active(uplink(name)), active)

    def test_the_intent_counts_at_once_and_a_return_to_auto_ends_it(self):
        on = controls.effective_uplink(uplink("auto-wifi"), (controls.uplink_pending("cell-first"),))
        self.assertTrue(controls.repair_active(on))
        off = controls.effective_uplink(uplink("cell-first"), (controls.uplink_pending("auto"),))
        self.assertFalse(controls.repair_active(off))

    def test_one_click_flips_between_the_two_modes(self):
        self.assertEqual(controls.repair_next_mode(uplink("auto-wifi")), "cell-first")
        self.assertEqual(controls.repair_next_mode(uplink("cell-first")), "auto")
        self.assertEqual(controls.repair_next_mode(uplink("cell-first-no-expiry")), "auto")

    def test_enabled_unless_acting_or_unavailable(self):
        self.assertTrue(controls.repair_enabled(uplink("auto-wifi"), False))
        self.assertFalse(controls.repair_enabled(uplink("auto-wifi"), True))
        self.assertFalse(controls.repair_enabled(uplink("missing"), False))

    def test_only_turning_it_on_asks(self):
        self.assertTrue(controls.uplink_needs_confirm(controls.repair_next_mode(uplink("auto-wifi"))))
        self.assertFalse(controls.uplink_needs_confirm(controls.repair_next_mode(uplink("cell-first"))))

    def test_the_tooltip_line(self):
        t = lambda n: controls.repair_tooltip(uplink(n), UPLINK_NOW)  # noqa: E731
        self.assertEqual(t("cell-first"), "Network Repair: cellular first, until 14:30")
        self.assertEqual(t("cell-first-no-expiry"), "Network Repair: cellular first, no expiry")
        self.assertEqual(t("cell-first-next-day"), "Network Repair: cellular first, until 2026-11-25 01:05")
        for name in ("auto-wifi", "auto-cell", "missing"):
            self.assertEqual(t(name), "", name)

    def test_the_confirmation_says_what_it_does_in_plain_words(self):
        for duration in ("30m", "2h", "0"):
            text = controls.uplink_confirm_text(duration)
            with self.subTest(duration=duration):
                self.assertTrue(text.startswith("Network Repair makes cellular the main connection"))
                self.assertIn("takes Wi-Fi and Ethernet out of the default route", text)
                self.assertIn("until you turn it off", text)
                self.assertIn("The VPN will reconnect over cellular.", text)
                self.assertIn("Cellular data is metered.", text)
                self.assertTrue(text.endswith("Turn it on?"))
        self.assertIn("or it expires in 30 minutes", controls.uplink_confirm_text("30m"))
        self.assertNotIn("expires", controls.uplink_confirm_text("0"))

    def test_no_em_dash_and_no_emoji_in_any_sentence(self):
        texts = [*controls.STRINGS.values(), controls.uplink_confirm_text("2h"),
                 controls.repair_tooltip(uplink("cell-first"), UPLINK_NOW)]
        for text in texts:
            self.assertNotIn("—", text)
            self.assertTrue(text.isascii() or "…" in text, text)


class Icon(InUtc):
    def test_the_icon_is_its_own_name_distinct_from_the_other_two(self):
        self.assertEqual(logic.ICON_REPAIR, "hammunition-tray-qt-repair")
        self.assertEqual(len({logic.ICON_AWAKE, logic.ICON_PARKED, logic.ICON_REPAIR}), 3)

    def test_the_icon_state_follows_the_uplink(self):
        self.assertEqual(logic.icon_name(TrayState()), logic.ICON_AWAKE)
        self.assertEqual(logic.icon_name(with_uplink("auto-wifi")), logic.ICON_AWAKE)
        self.assertEqual(logic.icon_name(with_uplink("cell-first")), logic.ICON_REPAIR)
        self.assertEqual(logic.icon_name(with_uplink("cell-first-no-expiry")), logic.ICON_REPAIR)
        self.assertEqual(logic.icon_name(with_uplink("missing")), logic.ICON_AWAKE)

    def test_the_icon_shows_the_intent_at_once_and_drops_it_when_asked_for_auto(self):
        s = with_uplink("auto-wifi")
        [e] = [e for e in logic.menu_model(s, now=UPLINK_NOW) if e.kind == "repair"]
        self.assertEqual(logic.icon_name(logic.begin_control(s, e)), logic.ICON_REPAIR)
        s = with_uplink("cell-first")
        [e] = [e for e in logic.menu_model(s, now=UPLINK_NOW) if e.kind == "repair"]
        self.assertEqual(logic.icon_name(logic.begin_control(s, e)), logic.ICON_AWAKE)

    def test_a_missing_helper_is_still_the_warning(self):
        s = TrayState(helper_missing=True, uplink=uplink("cell-first"))
        self.assertEqual(logic.icon_name(s), logic.ICON_MISSING)
        self.assertNotIn("Network Repair", logic.tooltip(s))

    def test_the_tooltip_says_when_it_ends(self):
        tip = logic.tooltip(with_uplink("cell-first"), now=UPLINK_NOW)
        self.assertEqual(
            tip.splitlines()[-1], "Network Repair: cellular first, until 14:30"
        )
        self.assertEqual(
            logic.tooltip(with_uplink("cell-first-no-expiry"), now=UPLINK_NOW).splitlines()[-1],
            "Network Repair: cellular first, no expiry",
        )

    def test_the_tooltip_is_unchanged_when_it_is_off(self):
        self.assertEqual(
            logic.tooltip(with_uplink("auto-wifi"), now=UPLINK_NOW),
            "Hammunition Devices\nNo parkable device is attached",
        )


class Entry(InUtc):
    def entry(self, state):
        model = logic.menu_model(state, now=UPLINK_NOW)
        self.assertEqual(model[0].kind, "repair", "the action is the first thing in the menu")
        self.assertEqual([e.kind for e in model].count("repair"), 1)
        return model[0]

    def test_off_it_offers_to_turn_it_on_with_the_chosen_duration(self):
        e = self.entry(with_uplink("auto-wifi"))
        self.assertEqual((e.text, e.checked, e.enabled, e.verb, e.duration), ("Network Repair", False, True, "cell-first", "2h"))
        s = logic.set_uplink_duration(with_uplink("auto-wifi"), "4h")
        self.assertEqual(self.entry(s).duration, "4h")
        self.assertEqual(logic.control_argv(self.entry(s)), (HELPER, ["uplink", "cell-first", "--for", "4h"]))

    def test_on_it_offers_to_turn_it_off_back_to_auto(self):
        e = self.entry(with_uplink("cell-first"))
        self.assertEqual((e.text, e.checked, e.enabled, e.verb), ("Network Repair", True, True, "auto"))
        self.assertEqual(logic.control_argv(e), (HELPER, ["uplink", "auto"]))

    def test_it_is_direct_never_pkexec_or_sudo(self):
        for name in ("auto-wifi", "cell-first"):
            program, args = logic.control_argv(self.entry(with_uplink(name)))
            self.assertEqual(program, HELPER)
            self.assertFalse({"pkexec", "sudo"} & set(args))

    def test_unavailable_or_unread_it_is_there_and_disabled(self):
        for state in (with_uplink("missing"), TrayState(devices=()),
                      logic.apply_uplink_poll(TrayState(devices=()), ok(code=1, stderr="error: boom"))):
            e = self.entry(state)
            self.assertEqual((e.text, e.enabled, e.verb), ("Network Repair", False, None))

    def test_while_acting_it_is_disabled(self):
        self.assertFalse(self.entry(logic.begin_action(with_uplink("cell-first"))).enabled)

    def test_a_poll_that_follows_a_click_confirms_it(self):
        s = with_uplink("auto-wifi")
        e = self.entry(s)
        s = logic.begin_control(s, e)
        self.assertEqual(s.pending, (("uplink:mode", "cell-first"),))
        self.assertTrue(self.entry(s).checked)
        s = logic.apply_control(s, e, ProcResult(started=True, code=1, stderr="error: no modem\n"))
        self.assertEqual((s.pending, s.action_error), ((), "error: no modem"))
        self.assertFalse(self.entry(s).checked)

    def test_a_missing_helper_hides_it_as_well(self):
        s = logic.apply_poll(TrayState(), ProcResult(started=False))[0]
        e = logic.menu_model(s, now=UPLINK_NOW)[0]
        self.assertNotEqual(e.kind, "repair")


if __name__ == "__main__":
    unittest.main()
