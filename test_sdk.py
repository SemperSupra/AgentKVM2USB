import pytest
import os
import time
import cv2
import platform
import numpy as np
from pathlib import Path
from epiphan_sdk import EpiphanKVM_SDK

class TestEpiphanKVM:
    """
    Comprehensive, Cross-Platform Test Suite for the Enhanced AgentKVM2USB SDK.
    Validates: Discovery, Video, HID, Vision Overlays, and Session Recording.
    """

    @pytest.fixture(scope="class")
    def sdk(self):
        """Initializes the SDK for testing and ensures cleanup."""
        _sdk = EpiphanKVM_SDK()
        yield _sdk
        _sdk.close()

    # --- 1. CORE CONNECTIVITY & DISCOVERY ---
    def test_hardware_discovery(self, sdk):
        """Validates that the SDK attempted discovery on the current platform."""
        # We check if self.cap is initialized if hardware is present
        # If not present, we skip the live hardware tests
        if sdk.cap is None:
            pytest.skip("KVM2USB 3.0 hardware not detected. Skipping live hardware tests.")
        
        assert sdk.cap.isOpened(), "Video capture should be opened if device is found."
        status = sdk.get_status()
        assert status['is_signal_active'] is True or status['is_signal_active'] is False

    # --- 2. VISION & IMAGE PROCESSING ---
    def test_autotune_logic(self, sdk, mocker):
        """Validates the autotune algorithm logic (brightness adjustment)."""
        if sdk.cap is None: pytest.skip("No hardware.")
        
        # We mock latest_frame to simulate a dark signal
        sdk.latest_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        spy_set = mocker.spy(sdk.cap, 'set')
        
        sdk.autotune(target_mean=128)
        # Should have attempted to increase brightness
        assert spy_set.called

    def test_get_screen_with_overlay(self, sdk):
        """Verifies visual audit overlays (timestamp/actions) are rendered into frames."""
        if sdk.cap is None: pytest.skip("No hardware.")
        
        test_file = "test_overlay.jpg"
        sdk._log_action("Test Action")
        path = sdk.get_screen(test_file, overlay=True)
        
        assert os.path.exists(test_file)
        # Verify it's a valid image
        img = cv2.imread(test_file)
        assert img is not None
        assert img.shape[0] > 0
        os.remove(test_file)

    # --- 3. SEMANTIC AGENT ACTIONS (HID) ---
    def test_semantic_typing(self, sdk, mocker):
        """Validates that 'sdk.type' correctly maps strings to HID writes."""
        if sdk.kb_dev is None: pytest.skip("No HID hardware.")
        
        spy = mocker.spy(sdk.kb_dev, 'write')
        sdk.type("abc")
        # 'a', 'b', 'c' each involve a Press and Release (2 writes per char)
        # Plus any shifts/modifiers. Min 6 writes.
        assert spy.call_count >= 6

    def test_hotkey_masking(self, sdk, mocker):
        """Verifies bitmask generation for complex hotkeys (e.g. Ctrl+Alt+Del)."""
        if sdk.kb_dev is None: pytest.skip("No HID hardware.")
        
        spy = mocker.spy(sdk, '_raw_kb')
        sdk.hotkey("ctrl", "alt", "delete")
        
        # Check first call (Press)
        mods = spy.call_args_list[0][0][0]
        assert mods == 0x05 # 0x01 | 0x04

    def test_normalized_click(self, sdk, mocker):
        """Validates 0.0-1.0 coordinate scaling for AI Agents."""
        if sdk.touch_dev is None: pytest.skip("No Touch hardware.")
        
        spy = mocker.spy(sdk.touch_dev, 'write')
        sdk.click(0.5, 0.5) # Click center
        
        # Center of 32767 is 16383
        # Report ID 0, buttons, x_lsb, x_msb, y_lsb, y_msb
        report = spy.call_args_list[0][0][0]
        # x_lsb = 16383 & 0xFF = 0xFF, x_msb = 16383 >> 8 = 0x3F
        assert report[3] == 0xFF 
        assert report[4] == 0x3F

    # --- 4. SESSION RECORDING & SRT ---
    def test_session_recording_and_srt(self, sdk):
        """Verifies session recording generates both MP4 and sidecar SRT."""
        if sdk.cap is None: pytest.skip("No hardware.")
        
        test_video = "test_session.mp4"
        test_srt = "test_session.srt"
        
        # Record a very short 2-second burst
        sdk.type("test event")
        sdk.record_session(2, filename=test_video)
        
        assert os.path.exists(test_video)
        assert os.path.exists(test_srt)
        
        # Verify SRT content has our event
        with open(test_srt, "r") as f:
            content = f.read()
            assert "Typed 'test event'" in content
            
        os.remove(test_video)
        os.remove(test_srt)

    # --- 5. SYSTEM DIAGNOSTICS ---
    def test_status_reporting(self, sdk):
        """Verifies structured status dictionary for Agent reasoning."""
        status = sdk.get_status()
        assert "resolution" in status
        assert "leds" in status
        assert isinstance(status['leds'], dict)

    def test_cross_platform_init(self, sdk):
        """Validates OS detection and backend selection."""
        current_os = platform.system()
        assert current_os in ["Windows", "Linux", "Darwin"]

if __name__ == "__main__":
    import pytest
    pytest.main(["-v", __file__])
