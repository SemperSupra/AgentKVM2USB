import hid
import time
import cv2
import threading
import os
import platform
import subprocess
import datetime
import json
import numpy as np
from pathlib import Path

class EpiphanKVM_SDK:
    """
    Enhanced, Cross-Platform, Agent-Ready SDK for Epiphan KVM2USB 3.0.
    Includes Vision-Agent Ready Artifacts, Discovery, and Autotuning.
    """
    
    KEY_MAP = {
        "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
        "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
        "f1": 0x3A, "f2": 0x3B, "f5": 0x3E, "f12": 0x45, "delete": 0x4C,
        "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52
    }
    MOD_MAP = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "gui": 0x08, "win": 0x08, "cmd": 0x08}
    PRESETS_FILE = Path(".kvm_presets.json")

    def __init__(self, target_name="KVM2USB 3.0"):
        self.vid = 0x2b77
        self.pid = 0x3661
        self.kb_dev = None
        self.mouse_dev = None
        self.touch_dev = None
        self.sys_dev = None
        self.cap = None
        self.latest_frame = None
        self._stop_video = False
        self.last_action_text = ""
        self.last_action_expiry = 0
        
        self._connect_hid()
        self._auto_start_video(target_name)

    def _connect_hid(self):
        for d in hid.enumerate(self.vid, self.pid):
            usage = d.get('usage', 0)
            try:
                dev = hid.device(); dev.open_path(d['path'])
                if usage == 0x101: self.kb_dev = dev
                elif usage == 0x102: self.mouse_dev = dev
                elif usage == 0x103: self.touch_dev = dev
                elif usage == 0x104: self.sys_dev = dev
            except: pass

    def _auto_start_video(self, target_name):
        # ... (keep existing auto logic but allow it to fail gracefully)
        pass

    def list_available_cameras(self):
        """Returns a list of (index, name) for all detected UVC devices."""
        available = []
        sys_name = platform.system()
        backend = cv2.CAP_ANY
        if sys_name == "Windows": backend = cv2.CAP_DSHOW
        elif sys_name == "Linux": backend = cv2.CAP_V4L2
        elif sys_name == "Darwin": backend = cv2.CAP_AVFOUNDATION

        # Use PowerShell on Windows to get friendly names
        names = []
        if sys_name == "Windows":
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_PnPEntity | Where-Object { $_.Service -eq 'usbvideo' } | Select-Object -ExpandProperty Caption"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                names = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
            except: pass

        for i in range(10):
            c = cv2.VideoCapture(i, backend)
            if c.isOpened():
                name = names[i] if i < len(names) else f"Camera {i}"
                available.append((i, name))
            c.release()
        return available

    def switch_camera(self, index):
        """Switches the active video capture to a specific index."""
        # Signal existing thread to pause/stop if needed, but here we just swap 'cap'
        if self.cap:
            self.cap.release()
        
        sys_name = platform.system()
        backend = cv2.CAP_ANY
        if sys_name == "Windows": backend = cv2.CAP_DSHOW
        elif sys_name == "Linux": backend = cv2.CAP_V4L2
        elif sys_name == "Darwin": backend = cv2.CAP_AVFOUNDATION
        
        new_cap = cv2.VideoCapture(index, backend)
        new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        # Atomically swap the capture object
        self.cap = new_cap
        print(f"[SDK] Switched to camera index {index}")
        
        # Ensure the update thread is running (only starts once)
        if not hasattr(self, '_thread') or not self._thread.is_alive():
            def _upd():
                while not self._stop_video:
                    if self.cap and self.cap.isOpened():
                        ret, f = self.cap.read()
                        if ret: self.latest_frame = f
                    time.sleep(0.01)
            self._thread = threading.Thread(target=_upd, daemon=True)
            self._thread.start()

    # --- VISION-AGENT ARTIFACTS ---
    def autotune(self, target_mean=128):
        """Automatically adjust brightness to achieve target mean pixel value."""
        if not self.cap: return
        print("[SDK] Autotuning signal brightness...")
        for _ in range(5):
            if self.latest_frame is None: time.sleep(0.1); continue
            mean_val = np.mean(self.latest_frame)
            diff = target_mean - mean_val
            if abs(diff) < 10: break
            curr = self.cap.get(cv2.CAP_PROP_BRIGHTNESS)
            self.cap.set(cv2.CAP_PROP_BRIGHTNESS, curr + (5 if diff > 0 else -5))
            time.sleep(0.2)
        print(f"[SDK] Autotune complete. Current mean: {np.mean(self.latest_frame):.2f}")

    def get_screen(self, filename="frame.jpg", overlay=True):
        """Capture screen with optional timestamp/event overlay."""
        if self.latest_frame is not None:
            frame = self.latest_frame.copy()
            if overlay:
                h, w = frame.shape[:2]
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                cv2.putText(frame, ts, (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1, cv2.LINE_AA)
                if time.time() < self.last_action_expiry:
                    cv2.putText(frame, f"ACTION: {self.last_action_text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1, cv2.LINE_AA)
            cv2.imwrite(filename, frame)
            return os.path.abspath(filename)
        return None

    # --- AGENT ACTIONS ---
    def _log_action(self, text):
        self.last_action_text = text
        self.last_action_expiry = time.time() + 2.0

    def type(self, text):
        self._log_action(f"Typed '{text}'")
        for char in text.lower():
            if char in self.KEY_MAP: self.press(char)
            elif 'a' <= char <= 'z':
                code = ord(char) - ord('a') + 4
                self._raw_kb(0, [code]); time.sleep(0.02); self._raw_kb(0, [0])
            elif char == ' ':
                self._raw_kb(0, [0x2C]); time.sleep(0.02); self._raw_kb(0, [0])
            time.sleep(0.05)

    def press(self, key_name):
        self._log_action(f"Pressed {key_name}")
        code = self.KEY_MAP.get(key_name.lower())
        if code: self._raw_kb(0, [code]); time.sleep(0.02); self._raw_kb(0, [0])

    def hotkey(self, *args):
        self._log_action(f"Hotkey {'+'.join(args)}")
        mods = 0; keys = []
        for a in args:
            a = a.lower()
            if a in self.MOD_MAP: mods |= self.MOD_MAP[a]
            elif a in self.KEY_MAP: keys.append(self.KEY_MAP[a])
        self._raw_kb(mods, keys); time.sleep(0.05); self._raw_kb(0, [0])

    def click(self, x_percent, y_percent, button=1):
        self._log_action(f"Clicked {x_percent:.2f},{y_percent:.2f}")
        if not self.touch_dev: return
        x = int(x_percent * 32767); y = int(y_percent * 32767)
        report = [button & 0xFF, x & 0xFF, (x >> 8) & 0xFF, y & 0xFF, (y >> 8) & 0xFF]
        self.touch_dev.write([0x00] + report)
        time.sleep(0.1); self.touch_dev.write([0x00, 0, 0, 0, 0, 0])

    def run_macro(self, macro_script: str):
        """
        Executes a sequence of commands defined in a Domain Specific Language (DSL).
        Available commands:
        - DELAY <ms>: Pauses execution.
        - TYPE <string>: Types literal text.
        - PRESS <key>: Presses a single key.
        - HOTKEY <mod1> <mod2> <key>: Presses a key combination.
        - CLICK <x_percent> <y_percent> [button]: Performs a mouse click.
        """
        lines = macro_script.strip().splitlines()
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(" ", 1)
            cmd = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            try:
                if cmd == "DELAY":
                    ms = int(args.strip())
                    time.sleep(ms / 1000.0)
                elif cmd == "TYPE":
                    self.type(args)
                elif cmd == "PRESS":
                    self.press(args.strip())
                elif cmd == "HOTKEY":
                    keys = [k.strip() for k in args.split()]
                    self.hotkey(*keys)
                elif cmd == "CLICK":
                    click_args = [arg.strip() for arg in args.split()]
                    if len(click_args) >= 2:
                        x = float(click_args[0])
                        y = float(click_args[1])
                        button = int(click_args[2]) if len(click_args) > 2 else 1
                        self.click(x, y, button)
                    else:
                        print(f"[SDK] Macro Error at line {line_num}: CLICK requires at least x_percent and y_percent")
                else:
                    print(f"[SDK] Macro Error at line {line_num}: Unknown command '{cmd}'")
            except Exception as e:
                print(f"[SDK] Macro Error at line {line_num}: Exception executing '{line}': {e}")

    # --- SESSION RECORDING & SRT ---
    def record_session(self, duration_sec, filename="session.mp4"):
        """Records video and generates an .srt file with HID event history."""
        if not self.cap: return
        output_path = Path(filename)
        srt_path = output_path.with_suffix(".srt")
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        h, w = self.latest_frame.shape[:2]
        out = cv2.VideoWriter(str(output_path), fourcc, 30.0, (w, h))
        
        events = [] # (relative_time, text)
        start_time = time.time()
        print(f"[SDK] Recording session to {filename}...")

        while (time.time() - start_time) < duration_sec:
            frame = self.latest_frame.copy()
            # Overlay logic
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            cv2.putText(frame, ts, (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
            
            if time.time() < self.last_action_expiry:
                if not events or events[-1][1] != self.last_action_text:
                    events.append((time.time() - start_time, self.last_action_text))
            
            out.write(frame)
            time.sleep(1/30.0)
            
        out.release()
        
        # Build SRT
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, (rel_ts, txt) in enumerate(events):
                end_ts = rel_ts + 2.0
                f.write(f"{i+1}\n{self._fmt_srt(rel_ts)} --> {self._fmt_srt(end_ts)}\n{txt}\n\n")
        print(f"[SDK] Session saved. Subtitles: {srt_path}")

    def _fmt_srt(self, sec):
        h, m, s = int(sec//3600), int((sec%3600)//60), int(sec%60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    # --- SYSTEM DIAGNOSTICS ---
    def get_status(self):
        """Returns hardware status dictionary for ANY connected target."""
        w, h = self.get_input_resolution()
        leds = self.get_led_status()
        return {
            "resolution": f"{w}x{h}",
            "is_signal_active": w > 0,
            "leds": leds
        }

    def get_input_resolution(self):
        """Returns (width, height) currently being output by the target."""
        if not self.sys_dev: return (0, 0)
        try:
            # Feature Report 0 usually contains the resolution info
            data = self.sys_dev.get_feature_report(0, 9)
            if len(data) >= 5:
                return (data[1] | (data[2] << 8), data[3] | (data[4] << 8))
        except: pass
        return (0, 0)

    def get_led_status(self):
        """Returns dict of LED states from the target (NumLock, CapsLock, ScrollLock)."""
        if not self.kb_dev: return {"caps": False, "num": False, "scroll": False}
        try:
            # Standard HID Keyboard Output report for LEDs
            data = self.kb_dev.get_feature_report(0, 2)
            if len(data) >= 2:
                b = data[1]
                return {"num": bool(b&1), "caps": bool(b&2), "scroll": bool(b&4)}
        except: pass
        return {"caps": False, "num": False, "scroll": False}

    def reenumerate_target(self):
        """Digitally 'unplugs' and 'replugs' the KVM from the target's perspective."""
        if not self.sys_dev: return
        print("[SDK] Re-enumerating target USB device...")
        report = [0x01] + [0x00] * 7 
        try:
            self.sys_dev.write([0x00] + report)
        except:
            self.sys_dev.write(report)
        time.sleep(2)

    def _raw_kb(self, mods, keys):
        if not self.kb_dev: return
        r = [0x00]*8; r[0] = mods
        for i, k in enumerate(keys[:6]): r[2+i] = k
        try: self.kb_dev.write([0x00] + r)
        except: self.kb_dev.write(r)

    def set_performance_mode(self, enabled):
        """
        Toggles between high-quality (uncompressed) and high-performance (MJPEG).
        If enabled, attempts to switch to MJPEG to reduce USB bandwidth.
        """
        if not self.cap: return
        # fourcc codes: YUY2 (uncompressed), MJPG (compressed)
        code = cv2.VideoWriter_fourcc(*'MJPG') if enabled else cv2.VideoWriter_fourcc(*'YUY2')
        self.cap.set(cv2.CAP_PROP_FOURCC, code)
        print(f"[SDK] Performance Mode: {'ON (MJPEG)' if enabled else 'OFF (YUY2)'}")

    def close(self):
        self._stop_video = True
        if self.cap: self.cap.release()
        for d in [self.kb_dev, self.mouse_dev, self.touch_dev, self.sys_dev]:
            if d: d.close()

if __name__ == "__main__":
    sdk = EpiphanKVM_SDK()
    sdk.autotune()
    sdk.type("reboot")
    sdk.get_screen("audit_log.jpg")
    sdk.close()
