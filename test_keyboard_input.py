import json

import epiphan_sdk
from epiphan_sdk import EpiphanKVM_SDK
from hid_discovery import EPIPHAN_KVM2USB3_PROFILE
from keyboard_input import KeyboardCodec, KeyboardReportProfile, KeyboardState


class FakeKeyboard:
    def __init__(self, fail_at=None):
        self.reports = []
        self.fail_at = fail_at

    def write(self, report):
        if self.fail_at is not None and len(self.reports) + 1 == self.fail_at:
            raise OSError("fixture keyboard write failure")
        self.reports.append(tuple(report))
        return len(report)

    def close(self):
        pass


def sdk_with_keyboard(fake=None):
    sdk = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
    sdk.keyboard_codec = KeyboardCodec()
    sdk.keyboard_state = KeyboardState(sdk.keyboard_codec)
    sdk.kb_dev = fake or FakeKeyboard()
    sdk.mouse_dev = sdk.touch_dev = sdk.sys_dev = None
    sdk.cap = None
    sdk._stop_video = False
    sdk.logging_enabled = False
    sdk.last_action_text = ""
    sdk.last_action_expiry = 0
    sdk.session_start_time = None
    sdk._stop_recording = False
    return sdk


def test_profile_defines_keyboard_wire_shape():
    collection = next(
        item for item in EPIPHAN_KVM2USB3_PROFILE.collections
        if item.role == "keyboard"
    )
    profile = KeyboardReportProfile.from_collection(collection)

    assert profile.report_id == 1
    assert profile.report_length == 8
    assert profile.report_id_prefix is True
    assert profile.rollover_limit == 6


def test_exact_key_down_and_up_report_bytes():
    sdk = sdk_with_keyboard()

    result = sdk.press("a")

    assert result.ok
    assert sdk.kb_dev.reports == [
        (1, 0, 0, 4, 0, 0, 0, 0, 0),
        (1, 0, 0, 0, 0, 0, 0, 0, 0),
    ]
    assert sdk.keyboard_state.pressed_keys == ()


def test_us_layout_shifted_text_and_punctuation():
    sdk = sdk_with_keyboard()

    result = sdk.type_text("A!_?")

    assert result.ok
    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.keyboard_state.active_modifiers == set()
    assert sdk.kb_dev.reports[0] == (1, 2, 0, 0, 0, 0, 0, 0, 0)
    assert sdk.kb_dev.reports[1] == (1, 2, 0, 4, 0, 0, 0, 0, 0)
    assert (1, 2, 0, 30, 0, 0, 0, 0, 0) in sdk.kb_dev.reports
    assert (1, 2, 0, 45, 0, 0, 0, 0, 0) in sdk.kb_dev.reports
    assert (1, 2, 0, 56, 0, 0, 0, 0, 0) in sdk.kb_dev.reports
    assert sdk.kb_dev.reports[-1] == (1, 0, 0, 0, 0, 0, 0, 0, 0)


def test_named_keys_modifiers_and_raw_usage_escape_hatch():
    sdk = sdk_with_keyboard()

    assert sdk.key_down("ctrl").ok
    assert sdk.raw_key_down(0x4C).ok
    assert sdk.raw_key_up(0x4C).ok
    assert sdk.key_up("control").ok
    assert sdk.press("f12").ok
    assert sdk.keyboard_state.active_modifiers == set()
    assert sdk.keyboard_state.pressed_keys == ()


def test_hotkey_releases_in_reverse_order():
    sdk = sdk_with_keyboard()

    result = sdk.hotkey("ctrl", "alt", "delete")

    assert result.ok
    assert sdk.keyboard_state.active_modifiers == set()
    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.kb_dev.reports[0][1] == 1
    assert sdk.kb_dev.reports[1][1] == 5
    assert sdk.kb_dev.reports[2][1] == 5
    assert sdk.kb_dev.reports[-1] == (1, 0, 0, 0, 0, 0, 0, 0, 0)


def test_rollover_and_invalid_state_are_structured():
    state = KeyboardState(KeyboardCodec())

    for usage in range(4, 10):
        assert state.key_down_usage(usage)[0].ok
    rollover, _ = state.key_down_usage(10)
    duplicate, _ = state.key_down_usage(4)
    missing, _ = state.key_up_usage(10)

    assert rollover.code == "rollover_limit"
    assert duplicate.code == "already_pressed"
    assert missing.code == "not_pressed"
    state.reset()


def test_unsupported_text_fails_and_clears_state():
    sdk = sdk_with_keyboard()

    result = sdk.type_text("ok €")

    assert not result.ok
    assert result.code == "unsupported_character"
    assert result.details == {"character": "€", "index": 3, "layout": "us"}
    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.keyboard_state.active_modifiers == set()
    assert sdk.kb_dev.reports[-1] == (1, 0, 0, 0, 0, 0, 0, 0, 0)


def test_write_failure_clears_logical_state_and_handles_no_stuck_key():
    sdk = sdk_with_keyboard(FakeKeyboard(fail_at=2))

    result = sdk.press("a")

    assert not result.ok
    assert result.code == "write_failed"
    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.keyboard_state.active_modifiers == set()


def test_macro_finally_releases_keyboard_state(monkeypatch):
    sdk = sdk_with_keyboard()

    def fail_type(_text):
        sdk.keyboard_state.key_down("a")
        raise RuntimeError("fixture cancellation")

    monkeypatch.setattr(sdk, "type", fail_type)
    sdk.run_macro("TYPE abc")

    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.keyboard_state.active_modifiers == set()
    assert sdk.kb_dev.reports[-1] == (1, 0, 0, 0, 0, 0, 0, 0, 0)


def test_close_attempts_release_all_before_closing_keyboard():
    sdk = sdk_with_keyboard()
    sdk.keyboard_state.key_down("shift")

    sdk.close()

    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.keyboard_state.active_modifiers == set()
    assert sdk.kb_dev.reports[-1] == (1, 0, 0, 0, 0, 0, 0, 0, 0)


def test_open_failure_path_is_json_safe(monkeypatch):
    sdk = sdk_with_keyboard(FakeKeyboard())
    sdk.keyboard_state.key_down("a")
    sdk.keyboard_state.reset()
    payload = {
        "reports": [list(report) for report in sdk.kb_dev.reports],
        "state": {
            "modifiers": sorted(sdk.keyboard_state.active_modifiers),
            "keys": sdk.keyboard_state.pressed_keys,
        },
    }

    assert json.dumps(payload)
