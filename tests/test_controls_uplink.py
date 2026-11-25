"""The Uplink control's rules (helper contract v1, ``uplink``), without a display.

controls.py holds the rules and wording both front ends share; logic.py holds
the state they act on. controlslogic.js is held to controls.py by
test_controls_parity; test_qt_smoke drives the real Tray with a fake runner.
Everything here runs in a fixed time zone, because the expiry is shown in the
operator's local time.
"""

import json
import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qt"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from controls_fixtures import UPLINK_NOW, UPLINK_POLLS, UPLINKS  # noqa: E402
from hammunition_tray_qt import controls, logic  # noqa: E402
from hammunition_tray_qt.logic import ProcResult, TrayState  # noqa: E402

HELPER = "/usr/local/libexec/hammunition-devctl"


def ok(stdout="", code=0, stderr=""):
    return ProcResult(started=True, crashed=False, code=code, stdout=stdout, stderr=stderr)


def uplink(name):
    return controls.parse_uplink(json.dumps(UPLINKS[name]))


def with_uplink(name="auto-wifi", state=None):
    return logic.apply_uplink_poll(state or TrayState(devices=()), ok(json.dumps(UPLINKS[name])))


def entries(state, kind):
    return [e for e in logic.menu_model(state, now=UPLINK_NOW) if e.kind == kind]


class InZone(unittest.TestCase):
    zone = "UTC"

    def setUp(self):
        self._old = os.environ.get("TZ")
        os.environ["TZ"] = self.zone
        time.tzset()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._old
        time.tzset()


class Parse(unittest.TestCase):
    def test_every_fixture_reads(self):
        for name in UPLINKS:
            with self.subTest(name):
                self.assertIsInstance(uplink(name), controls.UplinkRow)

    def test_cell_first_with_an_expiry(self):
        r = uplink("cell-first")
        self.assertEqual((r.present, r.mode, r.owner, r.until), (True, "cell-first", "cell", "2026-11-24T14:30:00Z"))

    def test_an_owner_this_tray_does_not_know_reads_as_none(self):
        self.assertEqual(uplink("auto-unknown-owner").owner, "none")

    def test_an_unavailable_uplink_has_no_mode_whatever_the_document_says(self):
        raw = dict(UPLINKS["missing"], mode="cell-first", owner="cell", until="2026-11-24T14:30:00Z")
        r = controls.parse_uplink(json.dumps(raw))
        self.assertEqual((r.present, r.mode, r.owner, r.until), (False, "", "", None))

    def test_refusals(self):
        for stdout in (
            "",
            "[]",
            "null",
            json.dumps(UPLINKS["auto-wifi"] | {"kind": "radios"}),
            json.dumps(UPLINKS["auto-wifi"] | {"mode": "turbo"}),
            json.dumps(UPLINKS["auto-wifi"] | {"mode": ""}),
            json.dumps(UPLINKS["auto-wifi"] | {"mode": "cell-first", "until": "tomorrow"}),
            json.dumps(UPLINKS["auto-wifi"] | {"mode": "cell-first", "until": 5}),
            json.dumps(UPLINKS["auto-wifi"] | {"mode": "cell-first", "until": "2026-11-24T14:30:00"}),
            '{"kind": "uplink", "version": 1, "present": true, "mode": "auto", "until": NaN}',
        ):
            with self.subTest(stdout[:60]):
                with self.assertRaises(controls.ControlsError):
                    controls.parse_uplink(stdout)


class PollOutcome(unittest.TestCase):
    def outcome(self, name):
        code, out, err = UPLINK_POLLS[name]
        return controls.poll_outcome("uplink", True, False, code, out, err)

    def test_a_good_document(self):
        o = self.outcome("ok")
        self.assertEqual((o.doc.mode, o.unsupported, o.error, o.keep), ("cell-first", False, "", False))

    def test_a_helper_without_the_verb_says_update_once_and_no_error(self):
        o = self.outcome("old-helper")
        self.assertEqual((o.doc, o.unsupported, o.error), (None, True, ""))

    def test_a_document_below_the_floor_is_unsupported_too(self):
        self.assertTrue(self.outcome("version-0").unsupported)

    def test_a_newer_version_and_a_float_one_are_read(self):
        for name in ("newer-version", "version-float"):
            self.assertIsNotNone(self.outcome(name).doc, name)

    def test_no_helper_is_silent_the_device_poll_says_it(self):
        self.assertEqual(self.outcome("missing"), controls.GroupOutcome())

    def test_a_refusal_that_is_not_a_missing_verb_is_an_error(self):
        o = self.outcome("refused")
        self.assertEqual((o.unsupported, o.error, o.keep), (False, "error: refused", True))

    def test_other_failures_keep_the_last_state_and_say_why(self):
        self.assertEqual(self.outcome("failed-with-stderr").error, "error: boom")
        self.assertEqual(self.outcome("failed-silently").error, controls.UPLINK_READ_ERROR)
        self.assertTrue(self.outcome("failed-silently").keep)

    def test_unreadable_output_is_a_parse_error_that_keeps_the_state(self):
        for name in ("not-json", "an-array", "null", "wrong-kind", "no-mode", "bad-mode", "bad-until",
                     "until-not-a-string", "until-no-offset", "nan", "until-feb-30", "until-hour-24",
                     "until-second-60", "until-offset-99", "until-trailing-newline"):
            with self.subTest(name):
                o = self.outcome(name)
                self.assertEqual((o.doc, o.error, o.keep), (None, controls.UPLINK_PARSE_ERROR, True))

    def test_a_leap_day_is_a_real_date(self):
        self.assertIsNotNone(self.outcome("until-leap-day").doc)

    def test_an_unavailable_uplink_is_a_document_not_an_error(self):
        o = self.outcome("unavailable")
        self.assertFalse(o.doc.present)
        self.assertEqual(o.error, "")


class Words(InZone):
    def text(self, name, now=UPLINK_NOW):
        return controls.uplink_indicator(uplink(name), now)

    def test_auto_names_the_owner(self):
        self.assertEqual(self.text("auto-wifi"), "Auto: using Wi-Fi")
        self.assertEqual(self.text("auto-ethernet"), "Auto: using Ethernet")
        self.assertEqual(self.text("auto-cell"), "Auto: using cellular")
        self.assertEqual(self.text("auto-none"), "Auto: no link has a route")

    def test_cell_first_says_when_it_ends_today_as_a_time(self):
        self.assertEqual(self.text("cell-first"), "Cell first until 14:30")

    def test_cell_first_says_the_date_when_it_ends_on_another_day(self):
        self.assertEqual(self.text("cell-first-next-day"), "Cell first until 2026-11-25 01:05")

    def test_an_offset_stamp_is_shown_in_local_time(self):
        self.assertEqual(self.text("cell-first-offset"), "Cell first until 12:30")

    def test_no_expiry_says_so(self):
        self.assertEqual(self.text("cell-first-no-expiry"), "Cell first, no expiry")

    def test_unavailable_names_the_reason(self):
        self.assertEqual(self.text("missing"), "not available: quectel-usbnet is not installed")
        self.assertEqual(self.text("no-detail"), "not available")

    def test_the_mode_names(self):
        self.assertEqual(controls.uplink_mode_label("auto"), "Auto")
        self.assertEqual(controls.uplink_mode_label("cell-first"), "Cell first")

    def test_the_durations_default_to_two_hours_and_include_no_expiry(self):
        self.assertEqual(controls.UPLINK_DEFAULT_DURATION, "2h")
        self.assertEqual([d for d, _ in controls.UPLINK_DURATIONS], ["30m", "1h", "2h", "4h", "8h", "0"])
        self.assertEqual(controls.uplink_duration_label("2h"), "2 hours")
        self.assertEqual(controls.uplink_duration_label("0"), "No expiry")

    def test_the_confirmation_says_mobile_data_and_for_how_long(self):
        self.assertEqual(
            controls.uplink_confirm_text("2h"), "Cell first uses mobile data for 2 hours. Turn it on?"
        )
        self.assertEqual(
            controls.uplink_confirm_text("0"),
            "Cell first uses mobile data until you switch back to Auto. Turn it on?",
        )

    def test_only_cell_first_asks(self):
        self.assertTrue(controls.uplink_needs_confirm("cell-first"))
        self.assertFalse(controls.uplink_needs_confirm("auto"))

    def test_no_em_dash_in_any_sentence(self):
        for text in controls.STRINGS.values():
            self.assertNotIn("\u2014", text)


class NewYork(Words):
    zone = "America/New_York"

    def test_the_same_stamp_is_the_operators_local_time(self):
        self.assertEqual(self.text("cell-first"), "Cell first until 09:30")

    # the cases of Words that assume UTC
    def test_cell_first_says_when_it_ends_today_as_a_time(self):
        self.assertEqual(self.text("cell-first"), "Cell first until 09:30")

    def test_cell_first_says_the_date_when_it_ends_on_another_day(self):
        # 20:05 local on the 24th is still the same local day as "now" (07:00)
        self.assertEqual(self.text("cell-first-next-day"), "Cell first until 20:05")

    def test_an_offset_stamp_is_shown_in_local_time(self):
        self.assertEqual(self.text("cell-first-offset"), "Cell first until 07:30")


class Rules(unittest.TestCase):
    def test_checked_follows_the_mode(self):
        r = uplink("cell-first")
        self.assertTrue(controls.uplink_checked(r, "cell-first"))
        self.assertFalse(controls.uplink_checked(r, "auto"))

    def test_enabled_unless_acting_or_unavailable(self):
        self.assertTrue(controls.uplink_enabled(uplink("auto-wifi"), False))
        self.assertFalse(controls.uplink_enabled(uplink("auto-wifi"), True))
        self.assertFalse(controls.uplink_enabled(uplink("missing"), False))

    def test_the_duration_choice_follows_the_same_rule(self):
        self.assertTrue(controls.uplink_duration_enabled(uplink("auto-wifi"), False))
        self.assertFalse(controls.uplink_duration_enabled(uplink("missing"), False))
        self.assertFalse(controls.uplink_duration_enabled(uplink("auto-wifi"), True))


class Argv(unittest.TestCase):
    def test_auto_is_direct_and_has_no_duration(self):
        self.assertEqual(controls.uplink_argv(HELPER, "auto", "2h"), (HELPER, ["uplink", "auto"]))

    def test_cell_first_carries_its_duration(self):
        for d, _ in controls.UPLINK_DURATIONS:
            self.assertEqual(
                controls.uplink_argv(HELPER, "cell-first", d), (HELPER, ["uplink", "cell-first", "--for", d])
            )

    def test_nothing_else_reaches_a_command(self):
        for mode, d in (
            ("turbo", "2h"), ("", "2h"), ("auto;id", "2h"), ("cell-first", ""), ("cell-first", "3h"),
            ("cell-first", "2h;id"), ("cell-first", "0h"), ("cell-first", "$(id)"), ("cell-first", "2h "),
        ):
            with self.subTest(mode=mode, duration=d):
                with self.assertRaises(ValueError):
                    controls.uplink_argv(HELPER, mode, d)

    def test_the_poll_has_no_pkexec(self):
        self.assertEqual(controls.uplink_poll_argv(HELPER), (HELPER, ["uplink", "state"]))
        self.assertEqual(logic.uplink_poll_argv(), (HELPER, ["uplink", "state"]))

    def test_neither_a_poll_nor_a_switch_can_name_pkexec_or_sudo(self):
        words = controls.uplink_poll_argv(HELPER)[1] + controls.uplink_argv(HELPER, "cell-first", "2h")[1]
        self.assertFalse({"pkexec", "sudo", "/usr/bin/pkexec"} & set(words))


class Pending(unittest.TestCase):
    def test_the_key_is_the_mode(self):
        self.assertEqual(controls.uplink_pending("cell-first"), ("uplink:mode", "cell-first"))

    def test_effective_shows_the_intent_as_switching(self):
        r = controls.effective_uplink(uplink("auto-wifi"), (controls.uplink_pending("cell-first"),))
        self.assertEqual((r.mode, r.switching, r.until), ("cell-first", True, None))
        self.assertEqual(controls.uplink_indicator(r, UPLINK_NOW), "Switching to Cell first…")
        back = controls.effective_uplink(uplink("cell-first"), (controls.uplink_pending("auto"),))
        self.assertEqual(controls.uplink_indicator(back, UPLINK_NOW), "Switching to Auto…")

    def test_a_request_the_row_already_matches_is_not_switching(self):
        r = controls.effective_uplink(uplink("auto-wifi"), (controls.uplink_pending("auto"),))
        self.assertFalse(r.switching)
        self.assertEqual(r, uplink("auto-wifi"))

    def test_no_pending_and_an_unavailable_row_are_left_alone(self):
        self.assertEqual(controls.effective_uplink(uplink("auto-wifi"), ()), uplink("auto-wifi"))
        self.assertEqual(
            controls.effective_uplink(uplink("missing"), (controls.uplink_pending("auto"),)), uplink("missing")
        )


class Transitions(unittest.TestCase):
    def entry(self, state, mode):
        [e] = [e for e in entries(state, "uplink-mode") if e.verb == mode]
        return e

    def test_a_poll_fills_the_group(self):
        s = with_uplink("cell-first")
        self.assertEqual(s.uplink.mode, "cell-first")
        self.assertEqual((s.uplink_unsupported, s.uplink_error), (False, ""))

    def test_the_duration_defaults_to_two_hours_and_can_be_chosen(self):
        s = TrayState()
        self.assertEqual(s.uplink_duration, "2h")
        self.assertEqual(logic.set_uplink_duration(s, "0").uplink_duration, "0")
        with self.assertRaises(ValueError):
            logic.set_uplink_duration(s, "3h")

    def test_a_switch_is_optimistic_at_once_and_runs_direct(self):
        s = with_uplink("auto-wifi")
        e = self.entry(s, "cell-first")
        self.assertEqual(logic.control_argv(e), (HELPER, ["uplink", "cell-first", "--for", "2h"]))
        s = logic.begin_control(s, e)
        self.assertTrue(s.acting)
        self.assertEqual(s.pending, (("uplink:mode", "cell-first"),))
        [info] = entries(s, "info")[-1:]  # the indicator is the last info line of the group
        self.assertEqual(info.text, "Switching to Cell first…")

    def test_the_chosen_duration_goes_on_the_command(self):
        s = logic.set_uplink_duration(with_uplink("auto-wifi"), "30m")
        self.assertEqual(
            logic.control_argv(self.entry(s, "cell-first")), (HELPER, ["uplink", "cell-first", "--for", "30m"])
        )

    def test_success_keeps_the_intent_until_the_next_poll_confirms(self):
        s = with_uplink("auto-wifi")
        e = self.entry(s, "cell-first")
        s = logic.begin_control(s, e)
        s = logic.apply_control(s, e, ok())
        self.assertEqual((s.acting, s.action_error, s.inflight), (False, "", ()))
        self.assertEqual(s.pending, (("uplink:mode", "cell-first"),))
        s = logic.apply_uplink_poll(s, ok(json.dumps(UPLINKS["cell-first"])), s.epoch)
        self.assertEqual((s.pending, s.uplink.mode), ((), "cell-first"))

    def test_a_failed_verb_reverts_and_shows_the_one_line_error(self):
        s = with_uplink("auto-wifi")
        e = self.entry(s, "cell-first")
        s = logic.begin_control(s, e)
        s = logic.apply_control(s, e, ok(code=1, stderr="error: modem not connected\nmore\n"))
        self.assertEqual((s.pending, s.action_error), ((), "error: modem not connected"))
        self.assertEqual(s.uplink.mode, "auto")

    def test_a_helper_that_cannot_run_is_one_line(self):
        s = with_uplink("auto-wifi")
        e = self.entry(s, "auto")
        s = logic.apply_control(logic.begin_control(s, e), e, ProcResult(started=False))
        self.assertEqual(s.action_error, controls.HELPER_RUN_ERROR)

    def test_a_poll_that_started_before_the_verb_leaves_the_intent_on_screen(self):
        s = with_uplink("auto-wifi")
        e = self.entry(s, "cell-first")
        before = s.epoch
        s = logic.begin_control(s, e)
        s = logic.apply_control(s, e, ok())
        s = logic.apply_uplink_poll(s, ok(json.dumps(UPLINKS["auto-wifi"])), before)
        self.assertEqual(s.pending, (("uplink:mode", "cell-first"),))

    def test_one_group_poll_never_clears_the_others_intent(self):
        s = with_uplink("auto-wifi")
        e = self.entry(s, "cell-first")
        s = logic.apply_control(logic.begin_control(s, e), e, ok())
        s = logic.apply_radios_poll(s, ok(json.dumps({"kind": "radios", "version": 1, "radios": []})), s.epoch)
        self.assertEqual(s.pending, (("uplink:mode", "cell-first"),))

    def test_unsupported_missing_and_failing_polls(self):
        s = logic.apply_uplink_poll(TrayState(devices=()), ok(code=2, stderr=UPLINK_POLLS["old-helper"][2]))
        self.assertEqual((s.uplink, s.uplink_unsupported), (None, True))
        s = logic.apply_uplink_poll(with_uplink("auto-wifi"), ok(code=1, stderr="error: boom"))
        self.assertEqual((s.uplink.mode, s.uplink_error), ("auto", "error: boom"))
        s = logic.apply_uplink_poll(s, ProcResult(started=True, code=127))
        self.assertEqual((s.uplink.mode, s.uplink_error), ("auto", ""))
        s = logic.apply_uplink_poll(s, ok(json.dumps(UPLINKS["auto-wifi"])))
        self.assertFalse(s.uplink_unsupported)


class Menu(InZone):
    def group(self, state):
        model = logic.menu_model(state, now=UPLINK_NOW)
        start = next(i for i, e in enumerate(model) if e.kind == "heading" and e.text == "Uplink")
        end = next(i for i in range(start + 1, len(model)) if model[i].kind == "separator")
        return model[start + 1 : end]

    def test_the_group_sits_between_radios_and_time(self):
        headings = [e.text for e in logic.menu_model(with_uplink(), now=UPLINK_NOW) if e.kind == "heading"]
        self.assertEqual(headings, ["Controls", "Devices", "Services", "Radios", "Uplink", "Time"])

    def test_auto_state(self):
        g = self.group(with_uplink("auto-wifi"))
        self.assertEqual([(e.kind, e.text) for e in g if e.kind == "info"], [("info", "Auto: using Wi-Fi")])
        modes = [e for e in g if e.kind == "uplink-mode"]
        self.assertEqual([(e.text, e.checked, e.enabled, e.verb) for e in modes],
                         [("Auto", True, True, "auto"), ("Cell first", False, True, "cell-first")])

    def test_cell_first_state_has_its_expiry_and_the_duration_choice(self):
        g = self.group(with_uplink("cell-first"))
        self.assertIn(("info", "Cell first until 14:30"), [(e.kind, e.text) for e in g])
        self.assertIn(("note", controls.UPLINK_DURATION_HEADING), [(e.kind, e.text) for e in g])
        durs = [e for e in g if e.kind == "uplink-duration"]
        self.assertEqual([e.duration for e in durs], ["30m", "1h", "2h", "4h", "8h", "0"])
        self.assertEqual([e.checked for e in durs], [False, False, True, False, False, False])
        self.assertEqual(durs[-1].text, "No expiry")

    def test_the_chosen_duration_is_the_one_checked(self):
        g = self.group(logic.set_uplink_duration(with_uplink(), "0"))
        self.assertEqual([e.duration for e in g if e.kind == "uplink-duration" and e.checked], ["0"])

    def test_unavailable_says_why_and_offers_nothing(self):
        g = self.group(with_uplink("missing"))
        kinds = [e.kind for e in g]
        self.assertEqual(kinds, ["info"])
        self.assertEqual(g[0].text, "not available: quectel-usbnet is not installed")

    def test_a_cli_that_fails_to_read_is_a_plain_error_line_and_changes_nothing(self):
        s = logic.apply_uplink_poll(TrayState(devices=()), ok(code=1, stderr="error: boom"))
        g = self.group(s)
        self.assertEqual([(e.kind, e.text) for e in g], [("error", "error: boom")])

    def test_before_the_first_poll_and_when_unsupported(self):
        g = self.group(TrayState(devices=()))
        self.assertEqual([(e.kind, e.text) for e in g], [("info", "Reading uplink…")])
        s = logic.apply_uplink_poll(TrayState(devices=()), ok(code=2, stderr=UPLINK_POLLS["old-helper"][2]))
        self.assertEqual([(e.kind, e.text) for e in self.group(s)], [("info", "update hammunition-tray")])

    def test_while_acting_every_control_is_disabled(self):
        s = logic.begin_action(with_uplink("cell-first"))
        g = self.group(s)
        self.assertTrue(all(not e.enabled for e in g if e.kind in ("uplink-mode", "uplink-duration")))

    def test_a_missing_helper_hides_the_group(self):
        s = logic.apply_poll(TrayState(), ProcResult(started=False))[0]
        self.assertNotIn("Uplink", [e.text for e in logic.menu_model(s, now=UPLINK_NOW) if e.kind == "heading"])


if __name__ == "__main__":
    unittest.main()
