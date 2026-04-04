import hid
import time
import cv2
import threading
import os
import platform

class EpiphanKVM_SDK:
    """
    Cross-Platform, Agent-Ready SDK for Epiphan KVM2USB 3.0.
    Supports Windows, Linux, and macOS.
    """
    
    # Standard HID Map
    KEY_MAP = {
        "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
        "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
        "f1": 0x3A, "f2": 0x3B, "f5": 0x3E, "f12": 0x45, "delete": 0x4C,
        "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52
    }
    MOD_MAP = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "gui": 0x08, "win": 0x08, "cmd": 0x08}

    def __init__(self):
        self.vid = 0x2b77
        self.pid = 0x3661
        self.kb_dev = None
        self.mouse_dev = None
        self.touch_dev = None
        self.sys_dev = None
        self.cap = None
        self.latest_frame = None
        self._stop_video = False
        
        self._connect_hid()
        self._auto_start_video()

    def _connect_hid(self):
        """Connects to HID endpoints. Requires udev rules on Linux."""
        for d in hid.enumerate(self.vid, self.pid):
            usage = d.get('usage', 0)
            try:
                dev = hid.device(); dev.open_path(d['path'])
                if usage == 0x101: self.kb_dev = dev
                elif usage == 0x102: self.mouse_dev = dev
                elif usage == 0x103: self.touch_dev = dev
                elif usage == 0x104: self.sys_dev = dev
            except Exception as e:
                # Common on Linux if permissions are not set
                if platform.system() == "Linux":
                    print(f"[SDK] HID Permission Error on {d['path']}. See README for udev rules.")
                pass

    def _auto_start_video(self):
        """Cross-platform UVC discovery."""
        sys_name = platform.system()
        backend = cv2.CAP_ANY
        
        if sys_name == "Windows": backend = cv2.CAP_DSHOW
        elif sys_name == "Linux": backend = cv2.CAP_V4L2
        elif sys_name == "Darwin": backend = cv2.CAP_AVFOUNDATION

        for i in range(10):
            c = cv2.VideoCapture(i, backend)
            if c.isOpened():
                # Test for HD capability to identify KVM2USB 3.0
                c.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                if c.get(cv2.CAP_PROP_FRAME_WIDTH) > 0:
                    self.cap = c; break
            c.release()
            
        if self.cap:
            def _upd():
                while not self._stop_video:
                    ret, f = self.cap.read()
                    if ret: self.latest_frame = f
                    time.sleep(0.01)
            threading.Thread(target=_upd, daemon=True).start()

    # --- AGENT ACTIONS ---
    def click(self, x_percent, y_percent, button=1):
        if not self.touch_dev: return
        x = int(x_percent * 32767); y = int(y_percent * 32767)
        report = [button & 0xFF, x & 0xFF, (x >> 8) & 0xFF, y & 0xFF, (y >> 8) & 0xFF]
        self.touch_dev.write([0x00] + report)
        time.sleep(0.1); self.touch_dev.write([0x00, 0, 0, 0, 0, 0])

    def type(self, text):
        for char in text.lower():
            if char in self.KEY_MAP: self.press(char)
            elif 'a' <= char <= 'z':
                code = ord(char) - ord('a') + 4
                self._raw_kb(0, [code]); time.sleep(0.02); self._raw_kb(0, [0])
            elif char == ' ':
                self._raw_kb(0, [0x2C]); time.sleep(0.02); self._raw_kb(0, [0])
            time.sleep(0.05)

    def press(self, key_name):
        code = self.KEY_MAP.get(key_name.lower())
        if code: self._raw_kb(0, [code]); time.sleep(0.02); self._raw_kb(0, [0])

    def hotkey(self, *args):
        mods = 0; keys = []
        for a in args:
            a = a.lower()
            if a in self.MOD_MAP: mods |= self.MOD_MAP[a]
            elif a in self.KEY_MAP: keys.append(self.KEY_MAP[a])
        self._raw_kb(mods, keys); time.sleep(0.05); self._raw_kb(0, [0])

    def get_screen(self, filename="frame.jpg"):
        if self.latest_frame is not None:
            cv2.imwrite(filename, self.latest_frame)
            return os.path.abspath(filename)
        return None

    def _raw_kb(self, mods, keys):
        if not self.kb_dev: return
        r = [0x00]*8; r[0] = mods
        for i, k in enumerate(keys[:6]): r[2+i] = k
        try: self.kb_dev.write([0x00] + r)
        except: self.kb_dev.write(r)

    def close(self):
        self._stop_video = True
        if self.cap: self.cap.release()
        for d in [self.kb_dev, self.mouse_dev, self.touch_dev, self.sys_dev]:
            if d: d.close()

if __name__ == "__main__":
    sdk = EpiphanKVM_SDK()
    print(f"SDK Initialized on {platform.system()}. Target detected: {sdk.cap is not None}")
    sdk.close()
