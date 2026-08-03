import pytest
import os
import time
import cv2
import numpy as np
import json
import re
from epiphan_sdk import EpiphanKVM_SDK
from frame_processor import MotionDetector, SRTGenerator, OverlayManager

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

        assert reports[0] == [0, 1, 255, 127, 0, 0]
        assert reports[1] == [0, 0, 0, 0, 0, 0]

    def test_stop_recording_sets_stop_flag(self, sdk):
        """Verifies GUI stop controls have a testable SDK stop signal."""
        sdk._stop_recording = False
        sdk.stop_recording()
        assert sdk._stop_recording is True

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

if __name__ == "__main__":
    import pytest
    pytest.main(["-v", __file__])
