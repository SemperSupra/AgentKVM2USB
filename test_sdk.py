import pytest
import os
import time
import cv2
import numpy as np
import json
import re
from epiphan_firmware import parse_fpga_bitstream, parse_fx3_image
from epiphan_sdk import EpiphanKVM_SDK
from frame_processor import MotionDetector, SRTGenerator, OverlayManager
from hardware_probe import effective_signal, frame_stats, parse_dshow_options

class TestEpiphanKVM_Enhanced:
    """
    Enhanced Test Suite for the AgentKVM2USB SDK.
    Validates: Motion Detection, SRT Generation, Preset Management, Macro DSL, and Config Persistence.
    """

    @pytest.fixture(scope="function")
    def sdk(self):
        """Initializes the SDK for testing and ensures cleanup."""
        _sdk = EpiphanKVM_SDK()
        yield _sdk
        _sdk.close()
        # Cleanup test files
        for f in ["test_user_presets.json", "test_config.json", "test_session.mp4", "test_session.srt"]:
            if os.path.exists(f): os.remove(f)

    # --- 1. FRAME PROCESSOR TESTS ---

    def test_motion_detector_logic(self):
        """Validates that the motion detector identifies significant frame changes."""
        detector = MotionDetector(threshold=10, min_area=100)
        
        # Frame 1: Black
        frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
        is_motion, locs = detector.detect(frame1)
        assert is_motion is False, "First frame should initialize background, not trigger motion."
        
        # Frame 2: Still Black
        is_motion, locs = detector.detect(frame1)
        assert is_motion is False, "Identical frames should not trigger motion."
        
        # Frame 3: White rectangle in center
        frame2 = frame1.copy()
        cv2.rectangle(frame2, (200, 200), (300, 300), (255, 255, 255), -1)
        is_motion, locs = detector.detect(frame2)
        assert is_motion is True, "Significant frame change should trigger motion."
        assert len(locs) > 0

    def test_srt_generator_output(self):
        """Verifies that SRTGenerator creates correctly formatted sidecar files."""
        test_srt = "test_gen.srt"
        if os.path.exists(test_srt): os.remove(test_srt)
        
        srt = SRTGenerator(test_srt)
        srt.add_entry(0.5, 2.5, "Test Motion")
        srt.add_entry(3.0, 5.0, "System Alert")
        
        assert os.path.exists(test_srt)
        with open(test_srt, "r") as f:
            content = f.read()
            assert "1\n00:00:00,500 --> 00:00:02,500\nTest Motion" in content
            assert "2\n00:00:03,000 --> 00:00:05,000\nSystem Alert" in content
        
        os.remove(test_srt)

    def test_overlay_manager_rendering(self):
        """Ensures overlays are actually drawn onto the frames."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        processed = OverlayManager.apply_standard_overlay(frame, status_text="UNIT_TEST", is_motion=True)
        
        # Check if pixels changed (at least the bottom HUD bar and top right motion dot)
        assert not np.array_equal(frame, np.zeros((1080, 1920, 3), dtype=np.uint8))
        # Verify status text area is not black anymore
        assert np.any(processed[1080-20, :]) 

    # --- 2. SEMANTIC AGENT ACTIONS & MACROS ---

    def test_run_macro(self, sdk, mocker):
        """Validates the HID Macro DSL parsing and execution."""
        spy_delay = mocker.spy(time, 'sleep')
        spy_type = mocker.spy(sdk, 'type')
        spy_press = mocker.spy(sdk, 'press')
        spy_hotkey = mocker.spy(sdk, 'hotkey')
        spy_click = mocker.spy(sdk, 'click')

        macro_script = """
        # This is a comment
        DELAY 100
        TYPE hello
        PRESS enter
        HOTKEY ctrl alt delete
        CLICK 0.5 0.5 2
        """

        sdk.run_macro(macro_script)

        assert spy_delay.called
        delay_calls = [call[0][0] for call in spy_delay.call_args_list]
        assert 0.1 in delay_calls  # 100 ms = 0.1 seconds

        assert spy_type.called
        assert spy_type.call_args_list[0][0][0] == "hello"

        # `type` internally calls `press` for each character it can't map
        # But we want to assert that our macro explicitly called press for "enter"
        press_calls = [call[0][0] for call in spy_press.call_args_list]
        assert "enter" in press_calls

        assert spy_hotkey.called
        assert spy_hotkey.call_args_list[0][0] == ("ctrl", "alt", "delete")

        assert spy_click.called
        assert spy_click.call_args_list[0][0] == (0.5, 0.5, 2)

        # Test error handling (should not crash)
        sdk.run_macro("INVALID_CMD")
        sdk.run_macro("CLICK 0.5") # Missing Y

    def test_documented_macro_keys_are_mapped(self):
        """Ensures MACROS.md key names are supported by the SDK key map."""
        expected = {
            *list("abcdefghijklmnopqrstuvwxyz"),
            *list("0123456789"),
            "enter", "esc", "backspace", "tab", "space",
            "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
            "delete", "up", "down", "left", "right",
        }
        assert expected.issubset(EpiphanKVM_SDK.KEY_MAP.keys())

    def test_click_clamps_normalized_coordinates(self, sdk):
        """Protects HID reports from invalid normalized click coordinates."""
        reports = []

        class FakeTouchDevice:
            def write(self, report):
                reports.append(report)

            def close(self):
                pass

        sdk.touch_dev = FakeTouchDevice()
        sdk.click(2.0, -1.0, button=1)

        assert reports[0] == [5, 3, 255, 127, 0, 0, 0]
        assert reports[1] == [5, 2, 255, 127, 0, 0, 0]

    def test_raw_keyboard_uses_vendor_report_id(self):
        """Matches the official KvmApp keyboard HID output report framing."""
        reports = []

        class FakeKeyboardDevice:
            def write(self, report):
                reports.append(report)

        sdk = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
        sdk.kb_dev = FakeKeyboardDevice()

        sdk._raw_kb(0x01, [EpiphanKVM_SDK.KEY_MAP["delete"]])

        assert reports == [[1, 1, 0, 76, 0, 0, 0, 0, 0]]

    def test_feature_reports_use_vendor_report_ids(self, mocker):
        """Covers recovered touch-type and re-enumeration feature reports offline."""
        reports = []

        class FakeSystemDevice:
            def send_feature_report(self, report):
                reports.append(report)
                return len(report)

        sdk = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
        sdk.sys_dev = FakeSystemDevice()
        sdk._log_event = lambda *args: None
        sleep = mocker.patch.object(time, "sleep")

        assert sdk.set_touch_type(1) is True
        sdk.reenumerate_target()

        assert reports == [[6, 1], [7, 0]]
        sleep.assert_called_once_with(2)

    def test_stop_recording_sets_stop_flag(self, sdk):
        """Verifies GUI stop controls have a testable SDK stop signal."""
        sdk._stop_recording = False
        sdk.stop_recording()
        assert sdk._stop_recording is True

    def test_get_input_signal_reads_touch_feature_report(self):
        """Verifies KVM2USB 3.0 live mode parsing from the observed HID report."""
        class FakeTouchDevice:
            def get_feature_report(self, report_id, length):
                assert report_id == 3
                assert length == 8
                return [0x80, 0x07, 0x38, 0x04, 0x01]

        sdk = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
        sdk.touch_dev = FakeTouchDevice()
        sdk.sys_dev = None

        assert sdk.get_input_signal() == {
            "width": 1920,
            "height": 1080,
            "is_active": True,
            "source": "touch_feature_3",
        }
        assert sdk.get_input_resolution() == (1920, 1080)

    def test_get_firmware_version_reads_usb_string_index_3(self):
        """Verifies the vendor app's firmware-version path is exposed read-only."""
        class FakeHidDevice:
            def get_indexed_string(self, index):
                assert index == 3
                return "4.0.0-r39896"

        sdk = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
        sdk.kb_dev = FakeHidDevice()
        sdk.mouse_dev = None
        sdk.touch_dev = None
        sdk.sys_dev = None

        assert sdk.get_firmware_version() == "4.0.0-r39896"

    def test_get_status_includes_firmware_version(self):
        """Keeps machine-consumable status aligned with recovered read-only data."""
        sdk = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
        sdk.get_input_signal = lambda: {
            "width": 1920,
            "height": 1080,
            "is_active": True,
            "source": "touch_feature_3",
        }
        sdk.get_led_status = lambda: {"caps": False, "num": False, "scroll": False}
        sdk.get_firmware_version = lambda: "4.0.0-r39896"

        assert sdk.get_status() == {
            "resolution": "1920x1080",
            "is_signal_active": True,
            "leds": {"caps": False, "num": False, "scroll": False},
            "signal_source": "touch_feature_3",
            "firmware_version": "4.0.0-r39896",
        }

    def test_parse_config_input_status_payload(self):
        """Documents the recovered MI_00 request 0xB2 InputStatusInfo layout."""
        payload = bytearray(29)
        payload[0:4] = b"DVI\x00"
        payload[12:17] = b"VESA\x00"
        payload[20:24] = (59940).to_bytes(4, "little")
        payload[24:26] = (1920).to_bytes(2, "little")
        payload[26:28] = (1080).to_bytes(2, "little")
        payload[28] = 1

        assert EpiphanKVM_SDK.parse_config_input_status(payload) == {
            "source": "DVI",
            "mode_name": "VESA",
            "width": 1920,
            "height": 1080,
            "refresh_hz": 59.94,
            "scan_mode": "p",
            "is_signal_active": True,
            "label": "DVI 1920x1080p@59.94, VESA",
        }

    def test_parse_and_build_config_flags(self):
        """Documents recovered MI_00 requests 0xE2/0xE3 device flag bits."""
        parsed = EpiphanKVM_SDK.parse_config_flags(0x16)

        assert parsed == {
            "raw": 0x16,
            "preserve_aspect_ratio": True,
            "performance_mode": True,
            "audio_selector_multichannel": True,
            "unknown_bits": 0,
        }
        assert EpiphanKVM_SDK.parse_config_flags(0x17)["unknown_bits"] == 0x01
        assert EpiphanKVM_SDK.build_config_flags(
            preserve_aspect_ratio=True,
            performance_mode=False,
            audio_selector_multichannel=True,
        ) == 0x12

    def test_parse_and_build_config_user_mode(self):
        """Documents recovered MI_00 request 0xB3 UserMode records."""
        assert EpiphanKVM_SDK.parse_config_user_mode([0x80, 0x07, 0x38, 0x04, 0x00]) == {
            "width": 1920,
            "height": 1080,
            "enabled": True,
            "disabled_byte": 0,
        }
        assert EpiphanKVM_SDK.parse_config_user_mode([0x80, 0x07, 0x38, 0x04, 0x01])["enabled"] is False
        assert EpiphanKVM_SDK.build_config_user_mode(1920, 1080, enabled=False) == [
            0x80,
            0x07,
            0x38,
            0x04,
            0x01,
        ]
        assert EpiphanKVM_SDK.build_config_user_mode(-1, 70000) == [0, 0, 0xFF, 0xFF, 0]

    def test_parse_fx3_image_records_and_transfer_chunks(self):
        """Documents the recovered Cypress FX3 record/checksum container."""
        record_data = (
            (0x11111111).to_bytes(4, "little")
            + (0x22222222).to_bytes(4, "little")
            + (0x33333333).to_bytes(4, "little")
        )
        checksum = sum(
            int.from_bytes(record_data[i:i + 4], "little")
            for i in range(0, len(record_data), 4)
        )
        image_bytes = (
            b"CY"
            + bytes([0x1C, 0xB0])
            + (3).to_bytes(4, "little")
            + (0x40003000).to_bytes(4, "little")
            + record_data
            + (0).to_bytes(4, "little")
            + (0x40000100).to_bytes(4, "little")
            + checksum.to_bytes(4, "little")
        )

        image = parse_fx3_image(image_bytes)

        assert image.image_control == 0x1C
        assert image.image_type == 0xB0
        assert image.entry_address == 0x40000100
        assert image.checksum_valid is True
        assert image.records[0].word_count == 3
        chunks = list(image.iter_transfer_chunks(max_chunk_size=8))
        assert [(chunk.address, len(chunk.data), chunk.w_value, chunk.w_index) for chunk in chunks] == [
            (0x40003000, 8, 0x3000, 0x4000),
            (0x40003008, 4, 0x3008, 0x4000),
        ]

    def test_parse_fpga_bitstream_sync_word(self):
        """Documents the recovered FPGA bitstream sync-word location."""
        bitstream = parse_fpga_bitstream(b"\xff" * 16 + bytes.fromhex("55 99 aa 66") + b"\x01\x02")

        assert bitstream.has_sync_word is True
        assert bitstream.sync_offset == 16
        assert bitstream.sync_word == bytes.fromhex("55 99 aa 66")
        assert bitstream.preamble == b"\xff" * 16
        assert bitstream.payload.startswith(bytes.fromhex("55 99 aa 66"))

    def test_runtime_session_directory_groups_outputs(self, sdk):
        """Ensures runtime outputs are correlated under a per-session directory."""
        assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", sdk.session_dir.name)
        assert sdk.config_path.parent == sdk.session_dir
        assert sdk.user_presets_path.parent == sdk.session_dir

        sdk.latest_frame = np.zeros((8, 8, 3), dtype=np.uint8)
        screenshot = sdk.get_screen("unit", overlay=False)

        sdk.start_session(enable_logging=True)
        sdk._log_event("TEST", "runtime")
        log_path = sdk.save_log("unit")

        assert str(sdk.session_dir.resolve()) in screenshot
        assert str(sdk.session_dir.resolve()) in log_path
        assert os.path.exists(screenshot)
        assert os.path.exists(log_path)

    # --- 3. PRESET & CONFIG PERSISTENCE ---

    def test_preset_saving_loading(self, sdk):
        """Validates custom user presets are saved and merged correctly."""
        sdk.user_presets_path = "test_user_presets.json"
        test_params = {
            "motion_threshold": 99,
            "motion_min_area": 9999,
            "brightness": 50,
            "contrast": 60,
            "saturation": 70
        }
        
        sdk.save_user_preset("TestCustom", test_params)
        assert os.path.exists(sdk.user_presets_path)
        
        # Reload SDK or re-trigger load
        sdk._load_all_presets()
        assert "TestCustom" in sdk.PRESETS
        assert sdk.PRESETS["TestCustom"]["motion_threshold"] == 99

    def test_config_startup_preset(self, sdk):
        """Verifies that the startup preset choice persists in config.json."""
        sdk.config_path = "test_config.json"
        sdk.config["startup_preset"] = "VGA Legacy"
        sdk.save_config()
        
        assert os.path.exists(sdk.config_path)
        with open(sdk.config_path, "r") as f:
            data = json.load(f)
            assert data["startup_preset"] == "VGA Legacy"

    # --- 4. INTEGRATED SDK TESTS ---

    def test_apply_preset_effect(self, sdk):
        """Verifies that apply_preset correctly updates the internal detector state."""
        sdk.apply_preset("High Sensitivity")
        assert sdk.motion_detector.threshold == 10
        assert sdk.motion_detector.min_area == 100

    def test_get_processed_frame_with_motion(self, sdk):
        """Verifies that the processed frame includes motion indicators when active."""
        sdk.enable_motion_detection = True
        sdk.enable_overlays = True
        
        # Simulate motion
        sdk.latest_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sdk.is_motion_detected = True
        sdk.motion_locs = [(10, 10, 50, 50)]
        
        processed = sdk.get_processed_frame()
        assert processed is not None
        # Should be different from raw zeros because of HUD and MOTION dot
        assert np.any(processed)


class TestKvmAppGUI:
    @pytest.fixture
    def app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        yield app

    @pytest.fixture
    def window(self, app, mocker):
        class FakeSdk:
            def __init__(self):
                self.cap = None
                self.latest_frame = None
                self.is_motion_detected = False
                self.enable_motion_detection = False
                self.enable_overlays = True
                self.show_motion_boxes = False

            def start_session(self, enable_logging=True):
                self.logging_enabled = enable_logging

            def list_available_cameras(self):
                return []

            def get_status(self):
                return {
                    "resolution": "0x0",
                    "is_signal_active": False,
                    "leds": {"caps": False, "num": False, "scroll": False},
                }

            def get_processed_frame(self):
                return None

            def reenumerate_target(self):
                pass

            def hotkey(self, *args):
                pass

            def stop_recording(self):
                self.stop_called = True

            def record_session(self, *args):
                pass

            def save_log(self, prefix="session"):
                return None

            def close(self):
                pass

        import kvmapp_gui

        fake_sdk = FakeSdk()
        mocker.patch.object(kvmapp_gui, "EpiphanKVM_SDK", return_value=fake_sdk)
        win = kvmapp_gui.KvmAppGUI()
        win.timer.stop()
        win.status_timer.stop()
        yield win
        win.close()

    def test_main_menus_are_created_at_startup(self, window):
        titles = [action.text() for action in window.menuBar().actions()]
        assert titles == ["&File", "&View", "&Devices", "&Tools", "&Options"]

    def test_toolbar_uses_plain_system_text(self, window):
        from PySide6.QtGui import QAction

        texts = [action.text() for action in window.findChildren(QAction) if action.text()]
        assert "Capture" in texts
        assert "Copy" in texts
        assert "Sensitivity: Medium" in texts
        assert all("📸" not in text and "🔒" not in text and "⚡" not in text for text in texts)

    def test_toggle_recording_requests_sdk_stop(self, window):
        window.toggle_recording()
        assert window.is_recording is True
        window.toggle_recording()
        assert window.is_recording is False
        assert window.sdk.stop_called is True

    def test_cursor_toggle_updates_state(self, window):
        window.toggle_cursor_vis(False)
        assert window.show_host_cursor is False
        window.toggle_cursor_vis(True)
        assert window.show_host_cursor is True


class TestHardwareProbeHelpers:
    def test_frame_stats_identifies_nonblank_frame(self):
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        frame[2:5, 2:5] = 255

        stats = frame_stats(frame)

        assert stats["shape"] == [10, 10, 3]
        assert stats["max"] == 255
        assert stats["nonBlackRatio"] == 0.09

    def test_effective_signal_prefers_hid_but_accepts_visible_frame(self):
        status = {"is_signal_active": False}
        stats = {"nonBlackRatio": 0.09, "max": 255}

        assert effective_signal(status, stats) == {
            "active": True,
            "hidActive": False,
            "framePresent": True,
            "frameNonBlank": True,
            "reason": "frame_content",
        }

    def test_effective_signal_accepts_sparse_firmware_text(self):
        status = {"is_signal_active": False}
        stats = {"nonBlackRatio": 0.000869, "max": 255}

        assert effective_signal(status, stats)["active"] is True
        assert effective_signal(status, stats)["reason"] == "frame_content"

    def test_effective_signal_reports_blank_frame(self):
        status = {"is_signal_active": False}
        stats = {"nonBlackRatio": 0.0, "max": 0}

        assert effective_signal(status, stats) == {
            "active": False,
            "hidActive": False,
            "framePresent": True,
            "frameNonBlank": False,
            "reason": "blank_frame",
        }

    def test_parse_dshow_options_deduplicates_modes(self):
        text = """
        pixel_format=yuyv422  min s=1920x1080 fps=15 max s=1920x1080 fps=60.0002
        pixel_format=yuyv422  min s=1920x1080 fps=15 max s=1920x1080 fps=60.0002 (tv, bt709/bt709/unknown, topleft)
        pixel_format=yuyv422  min s=640x480 fps=15 max s=640x480 fps=60.0002
        """

        assert parse_dshow_options(text) == [
            {
                "pixelFormat": "yuyv422",
                "width": 1920,
                "height": 1080,
                "minFps": 15.0,
                "maxFps": 60.0002,
            },
            {
                "pixelFormat": "yuyv422",
                "width": 640,
                "height": 480,
                "minFps": 15.0,
                "maxFps": 60.0002,
            },
        ]

if __name__ == "__main__":
    import pytest
    pytest.main(["-v", __file__])
