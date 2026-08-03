import json
import pytest

import epiphan_sdk
from epiphan_sdk import EpiphanKVM_SDK
from hid_discovery import DeviceProfile, EPIPHAN_KVM2USB3_PROFILE, HidCollectionProfile, UsbIdentity
from keyboard_input import KeyboardCodec, KeyboardProfileError, KeyboardReportProfile, KeyboardState


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


class FailOnceKeyboard(FakeKeyboard):
    def __init__(self):
        super().__init__()
        self.fail_next = False

    def write(self, report):
        if self.fail_next:
            self.fail_next = False
            raise OSError("fixture one-shot keyboard failure")
        return super().write(report)


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


def test_missing_keyboard_metadata_fails_closed():
    collection = HidCollectionProfile("keyboard", 0xFF00, 0x0101, 3)

    with pytest.raises(KeyboardProfileError) as error:
        KeyboardReportProfile.from_collection(collection)

    assert error.value.code == "missing_metadata"
    assert set(error.value.details["missing"]) == {
        "report_id", "report_length", "report_id_prefix", "rollover_limit"
    }


def test_sdk_does_not_open_handles_for_invalid_keyboard_profile(monkeypatch):
    collections = (
        HidCollectionProfile("keyboard", 0xFF00, 0x0101, 3),
        HidCollectionProfile("relative_mouse", 0xFF00, 0x0102, 3),
        HidCollectionProfile("absolute_pointer", 0xFF00, 0x0103, 3),
        HidCollectionProfile("system", 0xFF00, 0x0104, 3),
    )
    invalid_profile = DeviceProfile(
        "invalid-keyboard-fixture",
        (UsbIdentity(0x2B77, 0x3661),),
        collections,
    )
    entries = [
        {
            "path": f"hid://fixture&Col{index:02d}".encode(),
            "vendor_id": 0x2B77,
            "product_id": 0x3661,
            "serial_number": "fixture",
            "release_number": 1,
            "manufacturer_string": "Fixture",
            "product_string": "Fixture KVM",
            "usage_page": 0xFF00,
            "usage": usage,
            "interface_number": 3,
            "bus_type": 1,
        }
        for index, (_, usage) in enumerate((
            ("keyboard", 0x0101), ("relative_mouse", 0x0102),
            ("absolute_pointer", 0x0103), ("system", 0x0104),
        ), 1)
    ]
    monkeypatch.setattr(epiphan_sdk, "EPIPHAN_KVM2USB3_PROFILE", invalid_profile)
    sdk = sdk_with_keyboard()
    sdk.hid_serial = None
    sdk.hid_path = None
    sdk.development_mode = False
    sdk.hid_discovery = None
    sdk.hid_diagnostics = []
    sdk.hid_connection_ready = False
    sdk.kb_dev = sdk.mouse_dev = sdk.touch_dev = sdk.sys_dev = None
    monkeypatch.setattr(epiphan_sdk.hid, "enumerate", lambda: entries)
    monkeypatch.setattr(epiphan_sdk.hid, "device", FakeKeyboard)

    sdk._connect_hid()

    assert sdk.hid_connection_ready is False
    assert any(item.code == "invalid_keyboard_profile" for item in sdk.hid_diagnostics)
    assert sdk.kb_dev is None


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


def test_every_printable_us_ascii_character_has_an_encoding():
    codec = KeyboardCodec()

    assert all(codec.character(chr(code)) is not None for code in range(0x20, 0x7F))
    assert all(codec.character(value) is not None for value in ("\n", "\r", "\t", "\b"))


def test_named_navigation_editing_function_and_modifier_aliases_are_complete():
    codec = KeyboardCodec()
    expected = {
        "enter", "esc", "backspace", "tab", "space", "insert", "home", "end",
        "pageup", "pagedown", "delete", "up", "down", "left", "right",
        *{f"f{number}" for number in range(1, 13)},
    }

    assert expected.issubset(codec.NAMED_KEYS)
    assert all(codec.usage_for_key(key) is not None for key in expected)
    assert all(codec.normalize_modifier(alias) is not None for alias in (
        "ctrl", "control", "shift", "alt", "altgr", "gui", "win", "cmd",
        "leftctrl", "rightctrl", "leftshift", "rightshift", "leftalt", "rightalt",
        "leftgui", "rightgui",
    ))


def test_crlf_normalizes_to_one_enter():
    sdk = sdk_with_keyboard()

    result = sdk.type_text("\r\n")

    assert result.ok
    assert [report[3] for report in sdk.kb_dev.reports] == [0x28, 0]


def test_named_keys_modifiers_and_raw_usage_escape_hatch():
    sdk = sdk_with_keyboard()

    assert sdk.key_down("ctrl").ok
    assert sdk.raw_key_down(0x4C).ok
    assert sdk.raw_key_up(0x4C).ok
    assert sdk.key_up("control").ok
    assert sdk.press("f12").ok
    assert sdk.keyboard_state.active_modifiers == set()
    assert sdk.keyboard_state.pressed_keys == ()


def test_all_modifier_bits_and_raw_modifier_usages_are_exact():
    sdk = sdk_with_keyboard()
    aliases = ["lctrl", "lshift", "lalt", "lgui", "rctrl", "rshift", "ralt", "rgui"]
    expected_bits = [1, 2, 4, 8, 16, 32, 64, 128]

    for alias, bit in zip(aliases, expected_bits):
        assert sdk.key_down(alias).ok
        assert sdk.kb_dev.reports[-1][1] == bit
        assert sdk.key_up(alias).ok

    assert sdk.raw_key_down(0xE6).ok
    assert sdk.kb_dev.reports[-1][1] == 0x40
    assert sdk.raw_key_up(0xE6).ok
    assert sdk.hotkey("altgr", "delete").ok
    assert any(report[1] == 0x40 and report[3] == 0 for report in sdk.kb_dev.reports)
    assert all(
        usage not in report[3:]
        for report in sdk.kb_dev.reports
        for usage in range(0xE0, 0xE8)
    )


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


def test_unsupported_layout_fails_and_clears_state():
    sdk = sdk_with_keyboard()
    sdk.key_down("a")

    result = sdk.type_text("a", layout="de")

    assert not result.ok
    assert result.code == "unsupported_layout"
    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.keyboard_state.active_modifiers == set()


def test_write_failure_clears_logical_state_and_handles_no_stuck_key():
    sdk = sdk_with_keyboard(FakeKeyboard(fail_at=2))

    result = sdk.press("a")

    assert not result.ok
    assert result.code == "write_failed"
    assert sdk.keyboard_state.pressed_keys == ()
    assert sdk.keyboard_state.active_modifiers == set()


def test_failed_key_up_attempts_and_reports_direct_release_recovery():
    keyboard = FailOnceKeyboard()
    sdk = sdk_with_keyboard(keyboard)

    assert sdk.key_down("a").ok
    keyboard.fail_next = True
    result = sdk.key_up("a")

    assert not result.ok
    assert result.code == "write_failed"
    assert result.details["release_all_attempted"] is True
    assert result.details["release_all_succeeded"] is True
    assert keyboard.reports[-1] == (1, 0, 0, 0, 0, 0, 0, 0, 0)
    assert sdk.keyboard_state.pressed_keys == ()


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


def test_macro_propagates_keyboard_action_failure():
    sdk = sdk_with_keyboard()

    result = sdk.run_macro("TYPE €")

    assert not result.ok
    assert result.code == "macro_failed"
    assert result.details["action_code"] == "unsupported_character"
    assert result.details["release_all_succeeded"] is True


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
