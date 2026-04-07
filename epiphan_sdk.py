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
import secrets
import string
import re
from pathlib import Path
from frame_processor import MotionDetector, OverlayManager, SRTGenerator

class EpiphanKVM_SDK:
    """
    Universal, Agent-Ready SDK for Epiphan KVM2USB 3.0.
    Supports Advanced Naming, Optional Logging, and Cross-Platform UVC/HID.
    """
    
    KEY_MAP = {
        "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
        "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
        "f1": 0x3A, "f2": 0x3B, "f5": 0x3E, "f12": 0x45, "delete": 0x4C,
        "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52
    }
    MOD_MAP = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "gui": 0x08, "win": 0x08, "cmd": 0x08}

    PRESETS = {
        "Default": {
            "motion_threshold": 25, "motion_min_area": 500,
            "brightness": 128, "contrast": 128, "saturation": 128
        },
        "High Sensitivity": {
            "motion_threshold": 10, "motion_min_area": 100,
            "brightness": 128, "contrast": 128, "saturation": 128
        },
        "High Contrast (OCR)": {
            "motion_threshold": 30, "motion_min_area": 1000,
            "brightness": 100, "contrast": 180, "saturation": 0
        },
        "VGA Legacy": {
            "motion_threshold": 25, "motion_min_area": 500,
            "brightness": 140, "contrast": 110, "saturation": 160
        }
    }

    def __init__(self, target_name="KVM2USB 3.0"):
        self.vid = 0x2b77
        self.pid = 0x3661
        self.kb_dev = None
        self.mouse_dev = None
        self.touch_dev = None
        self.sys_dev = None
        self.cap = None
        self.latest_frame = None
        self.current_camera_name = None
        self._stop_video = False
        self.last_action_text = ""
        self.last_action_expiry = 0
        self._lock = threading.Lock()
        
        # Paths
        self.user_presets_path = "user_presets.json"
        self.config_path = "config.json"
        
        # Session Data
        self.session_events = []
        self.session_start_time = None
        self.logging_enabled = False
        
        # Frame Processor State
        self.motion_detector = MotionDetector()
        self.is_motion_detected = False
        self.motion_locs = []
        self.enable_motion_detection = False
        self.enable_overlays = True
        self.show_motion_boxes = False
        self.srt_generator = None
        
        self._load_all_presets()
        self._load_config()
        self._connect_hid()
        self._auto_start_video(target_name)

    def _load_config(self):
        """Loads general application configuration."""
        self.config = {"startup_preset": "Default", "device_mappings": {}}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.config.update(json.load(f))
            except: pass

    def save_config(self):
        """Saves current configuration to file."""
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=4)
            return True
        except: return False

    def apply_preset(self, name):
        """Applies all parameters of a named preset to the SDK and Hardware."""
        if name not in self.PRESETS:
            return False
        
        p = self.PRESETS[name]
        
        # 1. Update Motion Detector
        self.motion_detector.update_params(
            threshold=p.get("motion_threshold", 25),
            min_area=p.get("motion_min_area", 500)
        )
        
        # 2. Update Hardware UVC Properties
        self.set_camera_property("brightness", p.get("brightness", 128))
        self.set_camera_property("contrast", p.get("contrast", 128))
        self.set_camera_property("saturation", p.get("saturation", 128))
        
        # 3. Store mapping for current device
        if self.current_camera_name:
            self.config["device_mappings"][self.current_camera_name] = name
            self.save_config()
            
        return True

    def _load_all_presets(self):
        """Loads user presets and merges them with defaults."""
        if os.path.exists(self.user_presets_path):
            try:
                with open(self.user_presets_path, "r") as f:
                    user_p = json.load(f)
                    self.PRESETS.update(user_p)
            except: pass

    def save_user_preset(self, name, params):
        """Saves a new custom preset to the user_presets.json file."""
        self.PRESETS[name] = params
        user_only = {k: v for k, v in self.PRESETS.items() if k not in ["Default", "High Sensitivity", "High Contrast (OCR)", "VGA Legacy"]}
        user_only[name] = params
        try:
            with open(self.user_presets_path, "w") as f:
                json.dump(user_only, f, indent=4)
            return True
        except: return False

    def delete_user_preset(self, name):
        """Deletes a user preset."""
        if name in ["Default", "High Sensitivity", "High Contrast (OCR)", "VGA Legacy"]:
            return False
        if name in self.PRESETS:
            del self.PRESETS[name]
            user_only = {k: v for k, v in self.PRESETS.items() if k not in ["Default", "High Sensitivity", "High Contrast (OCR)", "VGA Legacy"]}
            try:
                with open(self.user_presets_path, "w") as f:
                    json.dump(user_only, f, indent=4)
                return True
            except: return False
        return False

    # --- FILENAME & LOGGING UTILITIES ---

    def _generate_filename(self, prefix="", extension="jpg"):
        ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        salt = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
        clean_prefix = re.sub(r'[^a-zA-Z0-9_-]', '', prefix).strip()
        if clean_prefix:
            return f"{clean_prefix}_{ts}_{salt}.{extension}"
        return f"kvm_{ts}_{salt}.{extension}"

    def _log_event(self, event_type, details):
        """Logs a time-aligned event if logging is enabled."""
        if not self.logging_enabled:
            # Still update OSD for visual feedback in GUI
            self.last_action_text = f"{event_type}: {details}"
            self.last_action_expiry = time.time() + 2.0
            return

        abs_ts = datetime.datetime.now().isoformat()
        rel_ts = (time.time() - self.session_start_time) if self.session_start_time else 0
            
        self.session_events.append({
            "timestamp": abs_ts,
            "relative_sec": round(rel_ts, 3),
            "type": event_type,
            "details": details
        })
        self.last_action_text = f"{event_type}: {details}"
        self.last_action_expiry = time.time() + 2.0

    def start_session(self, enable_logging=True):
        """Starts a new automation session. Logging is optional."""
        self.logging_enabled = enable_logging
        self.session_start_time = time.time()
        self.session_events = []
        if self.logging_enabled:
            self._log_event("SESSION_START", "Recording initialized")

    def save_log(self, prefix="session"):
        """Saves the event log to a JSON file if logging was enabled."""
        if not self.logging_enabled or not self.session_events:
            return None
        filename = self._generate_filename(prefix, "json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.session_events, f, indent=2)
        return os.path.abspath(filename)

    # --- CORE HARDWARE LOGIC ---

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
        cameras = self.list_available_cameras()
        for idx, name in cameras:
            if "KVM2USB" in name:
                self.switch_camera(idx, name); break

    def list_available_cameras(self):
        available = []
        sys_name = platform.system()
        backend = cv2.CAP_DSHOW if sys_name == "Windows" else cv2.CAP_ANY
        
        if sys_name == "Windows":
            try:
                from pygrabber.dshow_graph import FilterGraph
                graph = FilterGraph()
                names = graph.get_input_devices()
                for i, name in enumerate(names):
                    # We open the camera once to confirm it's not in use and check resolution
                    c = cv2.VideoCapture(i, backend)
                    if c.isOpened():
                        c.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                        is_kvm = c.get(cv2.CAP_PROP_FRAME_WIDTH) == 1920
                        tag = "[KVM2USB 3.0]" if (is_kvm or "KVM2USB" in name) else "[Webcam]"
                        available.append((i, f"{tag} {name}"))
                        c.release()
            except ImportError:
                # Fallback to manual scan if pygrabber isn't installed
                for i in range(5):
                    c = cv2.VideoCapture(i, backend)
                    if c.isOpened():
                        c.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                        tag = "[KVM2USB 3.0]" if c.get(cv2.CAP_PROP_FRAME_WIDTH) == 1920 else "[Webcam]"
                        available.append((i, f"{tag} Camera {i}"))
                        c.release()
        else:
            # Linux/Mac fallback
            for i in range(5):
                c = cv2.VideoCapture(i, backend)
                if c.isOpened():
                    available.append((i, f"Camera {i}"))
                    c.release()
        return available

    def switch_camera(self, index, name=None):
        with self._lock:
            self.latest_frame = None
            if self.cap: self.cap.release()
            
            # If name not provided, try to find it in the list
            if name is None:
                cameras = self.list_available_cameras()
                for i, n in cameras:
                    if i == index:
                        name = n
                        break
            
            self.current_camera_name = name
            
            sys_name = platform.system()
            backend = cv2.CAP_DSHOW if sys_name == "Windows" else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(index, backend)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            
            if not hasattr(self, '_thread') or not self._thread.is_alive():
                self._stop_video = False
                self._thread = threading.Thread(target=self._upd, daemon=True); self._thread.start()

        # Outside the lock, apply the relevant preset
        target_preset = self.config.get("device_mappings", {}).get(name)
        if not target_preset:
            target_preset = self.config.get("startup_preset", "Default")
        
        self.apply_preset(target_preset)

    def _upd(self):
        while not self._stop_video:
            if self._lock.acquire(timeout=0.1):
                try:
                    if self.cap and self.cap.isOpened():
                        ret, f = self.cap.read()
                        if ret:
                            self.latest_frame = f
                            if self.enable_motion_detection:
                                self.is_motion_detected, self.motion_locs = self.motion_detector.detect(f)
                        else:
                            self.is_motion_detected = False
                finally: self._lock.release()
            time.sleep(0.01)

    def get_processed_frame(self):
        """Returns the latest frame with all enabled overlays applied."""
        with self._lock:
            if self.latest_frame is None:
                return None
            frame = self.latest_frame.copy()
            is_motion = self.is_motion_detected
            locs = self.motion_locs
        
        if self.enable_overlays:
            status = self.last_action_text if time.time() < self.last_action_expiry else ""
            frame = OverlayManager.apply_standard_overlay(frame, status_text=status, is_motion=is_motion)
            if self.show_motion_boxes and is_motion:
                frame = OverlayManager.draw_motion_boxes(frame, locs)
        
        return frame

    # --- ACTIONS ---

    def click(self, x_percent, y_percent, button=1):
        self._log_event("MOUSE_CLICK", f"{x_percent:.2f},{y_percent:.2f} btn={button}")
        if not self.touch_dev: return
        x = int(x_percent * 32767); y = int(y_percent * 32767)
        report = [button & 0xFF, x & 0xFF, (x >> 8) & 0xFF, y & 0xFF, (y >> 8) & 0xFF]
        self.touch_dev.write([0x00] + report)
        time.sleep(0.1); self.touch_dev.write([0x00, 0, 0, 0, 0, 0])

    def type(self, text):
        self._log_event("KEYBOARD_TYPE", text)
        for char in text.lower():
            if char in self.KEY_MAP: self.press(char)
            elif 'a' <= char <= 'z':
                code = ord(char) - ord('a') + 4
                self._raw_kb(0, [code]); time.sleep(0.02); self._raw_kb(0, [0])
            elif char == ' ':
                self._raw_kb(0, [0x2C]); time.sleep(0.02); self._raw_kb(0, [0])
            time.sleep(0.05)

    def press(self, key_name):
        self._log_event("KEYBOARD_PRESS", key_name)
        code = self.KEY_MAP.get(key_name.lower())
        if code: self._raw_kb(0, [code]); time.sleep(0.02); self._raw_kb(0, [0])

    def hotkey(self, *args):
        self._log_event("KEYBOARD_HOTKEY", "+".join(args))
        mods = 0; keys = []
        for a in args:
            a = a.lower()
            if a in self.MOD_MAP: mods |= self.MOD_MAP[a]
            elif a in self.KEY_MAP: keys.append(self.KEY_MAP[a])
        self._raw_kb(mods, keys); time.sleep(0.05); self._raw_kb(0, [0])

    def get_screen(self, prefix="capture", overlay=True):
        filename = self._generate_filename(prefix, "jpg")
        with self._lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()
                if overlay:
                    h, w = frame.shape[:2]
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    cv2.putText(frame, ts, (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
                    if time.time() < self.last_action_expiry:
                        cv2.putText(frame, self.last_action_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)
                cv2.imwrite(filename, frame)
                self._log_event("SNAPSHOT", filename)
                return os.path.abspath(filename)
        return None

    def record_session(self, duration_sec, prefix="session", generate_srt=True):
        filename = self._generate_filename(prefix, "mp4")
        srt_filename = filename.replace(".mp4", ".srt") if generate_srt else None
        
        if not self.cap: return
        with self._lock:
            if self.latest_frame is None: return
            h, w = self.latest_frame.shape[:2]
        
        out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'mp4v'), 30.0, (w, h))
        srt = SRTGenerator(srt_filename) if generate_srt else None
        
        self._log_event("RECORDING_START", filename)
        rec_start = time.time()
        last_motion_state = False
        motion_start_time = 0
        
        while (time.time() - rec_start) < duration_sec:
            # Use processed frame for recording if overlays are enabled
            frame = self.get_processed_frame()
            if frame is None: break
            
            # SRT Logic: Track motion transitions
            if generate_srt:
                current_time = time.time() - rec_start
                with self._lock:
                    current_motion = self.is_motion_detected
                
                if current_motion and not last_motion_state:
                    motion_start_time = current_time
                elif not current_motion and last_motion_state:
                    srt.add_entry(motion_start_time, current_time, "Motion Detected")
                last_motion_state = current_motion

            out.write(frame)
            time.sleep(1/30.0)
            
        out.release()
        if last_motion_state and generate_srt:
            srt.add_entry(motion_start_time, time.time() - rec_start, "Motion Detected")
            
        self._log_event("RECORDING_END", filename)
        return os.path.abspath(filename)

    # --- DIAGNOSTICS ---

    def get_status(self):
        w, h = self.get_input_resolution()
        l = self.get_led_status()
        return {"resolution": f"{w}x{h}", "is_signal_active": w > 0, "leds": l}

    def get_input_resolution(self):
        if not self.sys_dev: return (0, 0)
        try:
            d = self.sys_dev.get_feature_report(0, 9)
            if len(d) >= 5: return (d[1] | (d[2] << 8), d[3] | (d[4] << 8))
        except: pass
        return (0, 0)

    def get_led_status(self):
        if not self.kb_dev: return {"caps": False, "num": False, "scroll": False}
        try:
            d = self.kb_dev.get_feature_report(0, 2)
            if len(d) >= 2:
                b = d[1]
                return {"num": bool(b&1), "caps": bool(b&2), "scroll": bool(b&4)}
        except: pass
        return {"caps": False, "num": False, "scroll": False}

    def reenumerate_target(self):
        if not self.sys_dev: return
        self._log_event("SYSTEM", "Re-enumerating target")
        try: self.sys_dev.write([0x00, 0x01] + [0x00]*7)
        except: pass
        time.sleep(2)

    def _raw_kb(self, mods, keys):
        if not self.kb_dev: return
        r = [0x00]*8; r[0] = mods
        for i, k in enumerate(keys[:6]): r[2+i] = k
        try: self.kb_dev.write([0x00] + r)
        except: self.kb_dev.write(r)

    def set_performance_mode(self, enabled):
        with self._lock:
            if not self.cap: return
            code = cv2.VideoWriter_fourcc(*'MJPG') if enabled else cv2.VideoWriter_fourcc(*'YUY2')
            self.cap.set(cv2.CAP_PROP_FOURCC, code)

    def set_camera_property(self, prop_name, value):
        """Sets an OpenCV camera property (e.g., brightness, contrast)."""
        prop_map = {
            "brightness": cv2.CAP_PROP_BRIGHTNESS,
            "contrast": cv2.CAP_PROP_CONTRAST,
            "saturation": cv2.CAP_PROP_SATURATION,
            "hue": cv2.CAP_PROP_HUE
        }
        if prop_name in prop_map and self.cap:
            with self._lock:
                self.cap.set(prop_map[prop_name], value)
                return True
        return False

    def cleanup_session_data(self, days=7):
        """Deletes snapshots, logs, and recordings older than specified days."""
        count = 0
        now = time.time()
        cutoff = now - (days * 86400)
        
        extensions = [".jpg", ".json", ".mp4", ".srt"]
        # Pattern for files generated by the app: prefix_dateTtime_salt.ext
        # We'll just look for files with these extensions that match the timestamp pattern
        for f in os.listdir("."):
            if any(f.endswith(ext) for ext in extensions):
                path = os.path.join(".", f)
                if os.path.getmtime(path) < cutoff:
                    # Basic safety check: only delete if it looks like our file
                    # (e.g. contains '202' for the decade 2020s)
                    if "202" in f and ("_" in f or f.startswith("kvm_")):
                        try:
                            os.remove(path)
                            count += 1
                        except: pass
        return count

    def close(self):
        self._stop_video = True
        if self.cap: self.cap.release()
        for d in [self.kb_dev, self.mouse_dev, self.touch_dev, self.sys_dev]:
            if d: d.close()

if __name__ == "__main__":
    sdk = EpiphanKVM_SDK()
    sdk.start_session(enable_logging=True)
    sdk.type("test")
    sdk.get_screen("test_capture")
    sdk.save_log()
    sdk.close()
