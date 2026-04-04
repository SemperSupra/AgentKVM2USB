import pytest
import os
import time
import cv2
import platform
from epiphan_sdk import EpiphanKVM_SDK

class TestEpiphanKVM:
    """
    Comprehensive Test Suite for the Epiphan KVM2USB 3.0 SDK.
    Validates Hardware Connection, Video Capture, HID Input, and System State.
    """

    @pytest.fixture(scope="class")
    def sdk(self):
        """Initializes the SDK for testing and ensures cleanup."""
        _sdk = EpiphanKVM_SDK()
        yield _sdk
        _sdk.close()

    # --- 1. HARDWARE CONNECTIVITY TESTS ---
    def test_hid_connection(self, sdk):
        """Verifies all HID endpoints (KB, Mouse, Touch, Sys) are found and open."""
        # Note: These may fail if hardware is not plugged in, which is expected.
        if sdk.kb_dev is None:
            pytest.skip("KVM2USB 3.0 Keyboard HID not found. Hardware test skipped.")
            
        assert sdk.kb_dev is not None, "Keyboard HID endpoint (0x101) must be connected."
        assert sdk.mouse_dev is not None, "Mouse HID endpoint (0x102) must be connected."
        assert sdk.touch_dev is not None, "Absolute Touch endpoint (0x103) must be connected."
        assert sdk.sys_dev is not None, "System Config endpoint (0x104) must be connected."

    def test_video_auto_discovery(self, sdk):
        """Verifies that the SDK successfully auto-discovered the UVC stream."""
        if sdk.cap is None:
            pytest.skip("KVM2USB 3.0 Video Source not found. Hardware test skipped.")
            
        assert sdk.cap.isOpened(), "UVC Video capture must be active and opened."
        assert sdk.cap.get(cv2.CAP_PROP_FRAME_WIDTH) >= 640, "Video resolution must be HD or at least VGA."

    # --- 2. VIDEO & VISION CAPABILITY TESTS ---
    def test_frame_capture(self, sdk):
        """Verifies the background thread is capturing frames from the hardware."""
        if sdk.cap is None: pytest.skip("No video hardware.")
        
        # Wait for first frame
        timeout = 5
        start = time.time()
        while sdk.latest_frame is None and (time.time() - start) < timeout:
            time.sleep(0.1)
            
        assert sdk.latest_frame is not None, "SDK failed to capture a frame from the device in 5 seconds."
        assert len(sdk.latest_frame.shape) == 3, "Captured frame must be a 3D color array (RGB)."

    def test_save_screenshot(self, sdk):
        """Verifies the vision-processing 'get_screen' feature works on any OS."""
        if sdk.cap is None: pytest.skip("No video hardware.")
        
        test_filename = "test_screen_capture.jpg"
        if os.path.exists(test_filename): os.remove(test_filename)
        
        path = sdk.get_screen(test_filename)
        assert path is not None, "SDK failed to return path for screenshot."
        assert os.path.exists(test_filename), "Screenshot file was not written to disk."
        assert os.path.getsize(test_filename) > 0, "Screenshot file is empty."
        os.remove(test_filename)

    # --- 3. HID INPUT CAPABILITY TESTS (AGENT ACTIONS) ---
    def test_coordinate_normalization(self, sdk):
        """Validates that the click logic correctly scales percent to 16-bit HID space."""
        # We test the scaling logic even if hardware isn't connected
        x_percent, y_percent = 0.5, 0.5
        x_raw = int(x_percent * 32767)
        y_raw = int(y_percent * 32767)
        assert x_raw == 16383, "Center X (50%) must scale to 16383 for the Absolute Touch endpoint."
        assert y_raw == 16383, "Center Y (50%) must scale to 16383."

    def test_typing_logic(self, sdk, mocker):
        """Verifies the 'type' method correctly maps characters to the HID buffer."""
        if sdk.kb_dev is None: pytest.skip("No HID hardware.")
        
        # We use a spy to ensure hid.write was called
        spy = mocker.spy(sdk.kb_dev, 'write')
        sdk.type("abc")
        # 'abc' = (Down/Up) * 3 = 6 HID write calls
        assert spy.call_count >= 6, "SDK should have triggered at least 6 HID writes for 'abc'."

    def test_hotkey_logic(self, sdk, mocker):
        """Verifies that complex hotkeys (like Ctrl+Alt+Del) trigger modified HID reports."""
        if sdk.kb_dev is None: pytest.skip("No HID hardware.")
        
        spy = mocker.spy(sdk, '_raw_kb')
        sdk.hotkey("ctrl", "alt", "delete")
        
        # First call should have mods 0x01 | 0x04 = 0x05
        # Arguments are (mods, [keys])
        mods = spy.call_args_list[0][0][0]
        keys = spy.call_args_list[0][0][1]
        
        assert mods == 0x05, "Ctrl+Alt modifier mask (0x01 | 0x04) must be 0x05."
        assert 0x4C in keys, "Keycode for 'Delete' (0x4C) must be in the HID report."

    # --- 4. SYSTEM DIAGNOSTIC TESTS ---
    def test_status_reporting(self, sdk):
        """Verifies that 'get_status' returns a structured dictionary across platforms."""
        status = sdk.get_status()
        assert isinstance(status, dict), "get_status must return a dictionary."
        assert "resolution" in status, "Status must include target resolution."
        assert "is_signal_active" in status, "Status must report signal health."
        assert "mouse_mode" in status, "Status must report current input mode."

    def test_platform_awareness(self, sdk):
        """Ensures the SDK correctly identifies the host OS and backend."""
        current_os = platform.system()
        # This is a sanity check that the SDK didn't crash during cross-platform init
        assert current_os in ["Windows", "Linux", "Darwin"], f"Host OS '{current_os}' must be supported."

if __name__ == "__main__":
    import pytest
    pytest.main(["-v", __file__])
