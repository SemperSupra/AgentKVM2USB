import hid
import time
import cv2
import threading
import os
import platform
import datetime
import json
import numpy as np
import secrets
import string
import re
from pathlib import Path
from frame_processor import MotionDetector, OverlayManager, SRTGenerator

VERSION = "0.2.0"
RUNTIME_SESSION_ROOT = "runtime_sessions"

class EpiphanKVM_SDK:
    """
    Universal, Agent-Ready SDK for Epiphan KVM2USB 3.0.
    Supports Advanced Naming, Optional Logging, and Cross-Platform UVC/HID.
    """
    
    KEY_MAP = {
        "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
        "g": 0x0A, "h": 0x0B, "i": 0x0C, "j": 0x0D, "k": 0x0E, "l": 0x0F,
        "m": 0x10, "n": 0x11, "o": 0x12, "p": 0x13, "q": 0x14, "r": 0x15,
        "s": 0x16, "t": 0x17, "u": 0x18, "v": 0x19, "w": 0x1A, "x": 0x1B,
        "y": 0x1C, "z": 0x1D,
        "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
        "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
        "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
        "f1": 0x3A, "f2": 0x3B, "f3": 0x3C, "f4": 0x3D, "f5": 0x3E,
        "f6": 0x3F, "f7": 0x40, "f8": 0x41, "f9": 0x42, "f10": 0x43,
        "f11": 0x44, "f12": 0x45, "delete": 0x4C,
        "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52
    }
    MOD_MAP = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "gui": 0x08, "win": 0x08, "cmd": 0x08}

    HID_REPORT_KEYBOARD = 0x01
    HID_REPORT_MOUSE = 0x02
    HID_REPORT_INPUT_SIZE = 0x03
    HID_REPORT_TOUCH = 0x05
    HID_REPORT_TOUCH_TYPE = 0x06
    HID_REPORT_REENUMERATE_SLAVE = 0x07

    CONFIG_FLAG_PRESERVE_ASPECT_RATIO = 0x02
    CONFIG_FLAG_PERFORMANCE_MODE = 0x04
    CONFIG_FLAG_AUDIO_SELECTOR = 0x10

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
        self.latest_frame_seq = 0
        self.latest_frame_at = None
        self.current_camera_name = None
        self._stop_video = False
        self.last_action_text = ""
        self.last_action_expiry = 0
        self._lock = threading.Lock()
        
        self.session_started_at = datetime.datetime.now(datetime.timezone.utc)
        self.session_correlation_id = secrets.token_hex(4)
        self.session_dir = self._create_runtime_session_dir()

        # Per-run state paths. The repository root config.json is treated as a default seed only.
        self.default_config_path = Path("config.json")
        self.user_presets_path = self.session_dir / "user_presets.json"
        self.config_path = self.session_dir / "config.json"
        
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
        self._stop_recording = False
        
        self._load_all_presets()
        self._load_config()
        self._connect_hid()
        self._auto_start_video(target_name)

    def _load_config(self):
        """Loads general application configuration."""
        self.config = {"startup_preset": "Default", "device_mappings": {}}
        for path in (self.default_config_path, self.config_path):
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        self.config.update(json.load(f))
                except: pass

    def _create_runtime_session_dir(self):
        """Creates a per-run output directory for logs, captures, and recordings."""
        timestamp = self.session_started_at.strftime("%Y%m%dT%H%M%SZ")
        path = Path(RUNTIME_SESSION_ROOT) / f"{timestamp}-{self.session_correlation_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

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

    def _runtime_path(self, filename):
        self.session_dir.mkdir(parents=True, exist_ok=True)
        return self.session_dir / filename

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
        path = self._runtime_path(self._generate_filename(prefix, "json"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.session_events, f, indent=2)
        return str(path.resolve())

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
                            self.latest_frame_seq += 1
                            self.latest_frame_at = time.time()
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
        x_percent = min(max(float(x_percent), 0.0), 1.0)
        y_percent = min(max(float(y_percent), 0.0), 1.0)
        self._log_event("MOUSE_CLICK", f"{x_percent:.2f},{y_percent:.2f} btn={button}")
        if not self.touch_dev: return
        x = int(x_percent * 32767); y = int(y_percent * 32767)
        self._raw_touch(button & 0xFF, x, y)
        time.sleep(0.1)
        self._raw_touch(0, x, y)

    def move_mouse_relative(self, dx, dy, wheel=0, buttons=0):
        """Moves the target pointer with the recovered relative mouse HID report."""
        self._log_event("MOUSE_MOVE_REL", f"dx={dx} dy={dy} wheel={wheel} buttons={buttons}")
        self._raw_mouse(buttons, dx, dy, wheel)

    def mouse_button(self, button=1, pressed=True):
        """Sends a relative mouse button state without pointer movement."""
        self._log_event("MOUSE_BUTTON", f"button={button} pressed={pressed}")
        buttons = int(button) & 0xFF if pressed else 0
        self._raw_mouse(buttons, 0, 0, 0)

    def mouse_click_relative(self, button=1):
        """Clicks using the relative mouse HID collection."""
        self.mouse_button(button, pressed=True)
        time.sleep(0.05)
        self.mouse_button(button, pressed=False)

    def scroll_mouse(self, wheel):
        """Scrolls using the relative mouse HID collection."""
        self._log_event("MOUSE_SCROLL", str(wheel))
        self._raw_mouse(0, 0, 0, wheel)

    def type(self, text):
        self._log_event("KEYBOARD_TYPE", text)
        for char in text.lower():
            if char in self.KEY_MAP: self.press(char)
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

    def run_macro(self, macro_script: str):
        """
        Executes a sequence of commands defined in a Domain Specific Language (DSL).
        Available commands:
        - DELAY <ms>: Pauses execution.
        - TYPE <string>: Types literal text.
        - PRESS <key>: Presses a single key.
        - HOTKEY <mod1> <mod2> <key>: Presses a key combination.
        - CLICK <x_percent> <y_percent> [button]: Performs a mouse click.
        - MOVE <dx> <dy> [wheel]: Performs relative mouse movement.
        - SCROLL <wheel>: Performs relative mouse wheel movement.
        """
        result = {"success": True, "executed": [], "errors": []}
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
                    result["executed"].append({"line": line_num, "command": cmd, "args": {"ms": ms}})
                elif cmd == "TYPE":
                    self.type(args)
                    result["executed"].append({"line": line_num, "command": cmd, "args": {"text": args}})
                elif cmd == "PRESS":
                    key = args.strip()
                    self.press(key)
                    result["executed"].append({"line": line_num, "command": cmd, "args": {"key": key}})
                elif cmd == "HOTKEY":
                    keys = [k.strip() for k in args.split()]
                    self.hotkey(*keys)
                    result["executed"].append({"line": line_num, "command": cmd, "args": {"keys": keys}})
                elif cmd == "CLICK":
                    click_args = [arg.strip() for arg in args.split()]
                    if len(click_args) >= 2:
                        x = float(click_args[0])
                        y = float(click_args[1])
                        button = int(click_args[2]) if len(click_args) > 2 else 1
                        self.click(x, y, button)
                        result["executed"].append({
                            "line": line_num,
                            "command": cmd,
                            "args": {"x": x, "y": y, "button": button},
                        })
                    else:
                        self._macro_error(result, line_num, line, "CLICK requires at least x_percent and y_percent")
                elif cmd == "MOVE":
                    move_args = [arg.strip() for arg in args.split()]
                    if len(move_args) >= 2:
                        dx = int(move_args[0])
                        dy = int(move_args[1])
                        wheel = int(move_args[2]) if len(move_args) > 2 else 0
                        self.move_mouse_relative(dx, dy, wheel)
                        result["executed"].append({
                            "line": line_num,
                            "command": cmd,
                            "args": {"dx": dx, "dy": dy, "wheel": wheel},
                        })
                    else:
                        self._macro_error(result, line_num, line, "MOVE requires dx and dy")
                elif cmd == "SCROLL":
                    wheel = int(args.strip())
                    self.scroll_mouse(wheel)
                    result["executed"].append({"line": line_num, "command": cmd, "args": {"wheel": wheel}})
                else:
                    self._macro_error(result, line_num, line, f"Unknown command '{cmd}'")
            except Exception as e:
                self._macro_error(result, line_num, line, f"Exception executing command: {e}")
        return result

    def _macro_error(self, result, line_num, line, message):
        result["success"] = False
        error = {"line": line_num, "text": line, "message": message}
        result["errors"].append(error)
        print(f"[SDK] Macro Error at line {line_num}: {message}")

    def get_screen(self, prefix="capture", overlay=True):
        path = self._runtime_path(self._generate_filename(prefix, "jpg"))
        with self._lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()
                if overlay:
                    h, w = frame.shape[:2]
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    cv2.putText(frame, ts, (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
                    if time.time() < self.last_action_expiry:
                        cv2.putText(frame, self.last_action_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)
                cv2.imwrite(str(path), frame)
                self._log_event("SNAPSHOT", str(path))
                return str(path.resolve())
        return None

    def record_session(self, duration_sec, prefix="session", generate_srt=True):
        path = self._runtime_path(self._generate_filename(prefix, "mp4"))
        srt_path = path.with_suffix(".srt") if generate_srt else None
        self._stop_recording = False
        
        if not self.cap: return
        with self._lock:
            if self.latest_frame is None: return
            h, w = self.latest_frame.shape[:2]
        
        out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 30.0, (w, h))
        srt = SRTGenerator(str(srt_path)) if generate_srt else None
        
        self._log_event("RECORDING_START", str(path))
        rec_start = time.time()
        last_motion_state = False
        motion_start_time = 0
        
        while not self._stop_recording and (time.time() - rec_start) < duration_sec:
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
            
        self._log_event("RECORDING_END", str(path))
        return str(path.resolve())

    def stop_recording(self):
        """Requests that the active recording loop stop at the next frame boundary."""
        self._stop_recording = True

    # --- DIAGNOSTICS ---

    def get_status(self):
        signal = self.get_input_signal()
        w, h = signal["width"], signal["height"]
        l = self.get_led_status()
        return {
            "resolution": f"{w}x{h}",
            "is_signal_active": signal["is_active"],
            "leds": l,
            "signal_source": signal["source"],
            "firmware_version": self.get_firmware_version(),
        }

    def get_config_status(self, libusb_dll=None, timeout_ms=1000):
        """Reads static-confirmed MI_00 config status through vendor IN requests only."""
        from mi00_probe import Mi00ProbeError, find_device, read_config_request

        try:
            dev = find_device(libusb_dll=libusb_dll)
            if dev is None:
                return {
                    "available": False,
                    "error": "KVM2USB 3.0 USB device not found",
                    "requests": {},
                    "user_modes": [],
                }
            requests = {}
            for name in ("input_status", "device_flags"):
                requests[name] = read_config_request(
                    dev,
                    name,
                    timeout_ms=timeout_ms,
                ).as_dict()
            user_modes = [
                read_config_request(
                    dev,
                    "user_mode",
                    w_value=index,
                    timeout_ms=timeout_ms,
                ).as_dict()
                for index in range(3)
            ]
            requests["user_mode"] = user_modes[0]
            return {
                "available": True,
                "error": None,
                "requests": requests,
                "user_modes": user_modes,
            }
        except Mi00ProbeError as exc:
            return {
                "available": False,
                "error": str(exc),
                "requests": {},
                "user_modes": [],
            }
        except Exception as exc:
            return {
                "available": False,
                "error": f"unexpected MI_00 probe failure: {exc}",
                "requests": {},
                "user_modes": [],
            }

    def get_device_health(self, stale_after_sec=2.0, include_mi00=False, libusb_dll=None):
        """Returns a structured HID/UVC/frame health model for agents and GUI."""
        status = self.get_status()
        with self._lock:
            frame = self.latest_frame.copy() if self.latest_frame is not None else None
            frame_seq = self.latest_frame_seq
            frame_at = self.latest_frame_at

        frame_age = time.time() - frame_at if frame_at else None
        frame_stats = self._frame_health_stats(frame)
        frame_present = frame_stats is not None
        frame_stale = bool(frame_age is not None and frame_age > float(stale_after_sec))
        frame_nonblank = bool(
            frame_stats
            and frame_stats["non_black_ratio"] >= 0.0001
            and frame_stats["max"] > 10
        )
        hid_active = bool(status.get("is_signal_active"))
        cap_opened = bool(self.cap and self.cap.isOpened())
        mi00 = self.get_config_status(libusb_dll=libusb_dll) if include_mi00 else None
        mi00_input = ((mi00 or {}).get("requests", {}).get("input_status") or {}).get("parsed") or {}
        mi00_active = bool(mi00_input.get("is_signal_active"))

        health = {
            "status": status,
            "camera": {
                "name": self.current_camera_name,
                "opened": cap_opened,
            },
            "frame": {
                "present": frame_present,
                "sequence": frame_seq,
                "age_sec": round(frame_age, 3) if frame_age is not None else None,
                "stale": frame_stale,
                "stats": frame_stats,
            },
            "effective_signal": {
                "active": hid_active or frame_nonblank or mi00_active,
                "hid_active": hid_active,
                "mi00_active": mi00_active,
                "frame_present": frame_present,
                "frame_nonblank": frame_nonblank,
                "frame_stale": frame_stale,
                "reason": self._effective_signal_reason(
                    hid_active,
                    frame_present,
                    frame_nonblank,
                    frame_stale,
                    mi00_active,
                ),
            },
        }
        if include_mi00:
            health["mi00"] = mi00
        return health

    @staticmethod
    def _frame_health_stats(frame):
        if frame is None:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return {
            "shape": list(frame.shape),
            "mean": round(float(gray.mean()), 3),
            "std": round(float(gray.std()), 3),
            "min": int(gray.min()),
            "max": int(gray.max()),
            "non_black_ratio": round(float(np.count_nonzero(gray > 10) / gray.size), 6),
        }

    @staticmethod
    def _effective_signal_reason(hid_active, frame_present, frame_nonblank, frame_stale, mi00_active=False):
        if hid_active and mi00_active and frame_nonblank and not frame_stale:
            return "hid_mi00_and_frame"
        if hid_active and frame_nonblank and not frame_stale:
            return "hid_and_frame"
        if hid_active and mi00_active:
            return "hid_and_mi00"
        if hid_active:
            return "hid_report"
        if mi00_active and frame_nonblank and not frame_stale:
            return "mi00_and_frame"
        if mi00_active:
            return "mi00_report"
        if frame_nonblank and not frame_stale:
            return "frame_content"
        if frame_stale:
            return "stale_frame"
        if frame_present:
            return "blank_frame"
        return "no_frame"

    def get_firmware_version(self):
        # Official KvmApp reads USB string descriptor index 3 via hidapi.
        for dev in (self.kb_dev, self.mouse_dev, self.touch_dev, self.sys_dev):
            if not dev or not hasattr(dev, "get_indexed_string"):
                continue
            try:
                value = dev.get_indexed_string(3)
                if value:
                    return value.strip()
            except Exception:
                continue
        return None

    def get_input_resolution(self):
        signal = self.get_input_signal()
        return (signal["width"], signal["height"])

    def get_input_signal(self):
        # KVM2USB 3.0 exposes live input mode on the touch HID collection:
        # report 3 => width_le16, height_le16, active_flag.
        signal = self._read_mode_report(self.touch_dev, self.HID_REPORT_INPUT_SIZE, 8, 0, "touch_feature_3")
        if signal:
            return signal

        # Older reverse-engineering assumed a system collection report with a
        # leading report byte. Keep it as a fallback for other firmware builds.
        signal = self._read_mode_report(self.sys_dev, 0, 9, 1, "system_feature_0")
        if signal:
            return signal

        return {"width": 0, "height": 0, "is_active": False, "source": None}

    def _read_mode_report(self, dev, report_id, length, offset, source):
        if not dev:
            return None
        try:
            d = dev.get_feature_report(report_id, length)
            if len(d) < offset + 4:
                return None
            w = d[offset] | (d[offset + 1] << 8)
            h = d[offset + 2] | (d[offset + 3] << 8)
            active = bool(d[offset + 4]) if len(d) > offset + 4 else w > 0
            if w > 0 and h > 0:
                return {"width": w, "height": h, "is_active": active, "source": source}
        except: pass
        return None

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
        self._send_feature_report(self.sys_dev, [self.HID_REPORT_REENUMERATE_SLAVE, 0x00])
        time.sleep(2)

    def set_touch_type(self, touch_type):
        """Sets the device touch-report mode using the vendor app's feature report."""
        if not self.sys_dev:
            return False
        return self._send_feature_report(self.sys_dev, [self.HID_REPORT_TOUCH_TYPE, int(touch_type) & 0xFF])

    def _raw_kb(self, mods, keys):
        if not self.kb_dev: return
        r = [0x00]*8; r[0] = mods
        for i, k in enumerate(keys[:6]): r[2+i] = k
        self._write_hid_report(self.kb_dev, [self.HID_REPORT_KEYBOARD] + r, r)

    def _raw_mouse(self, buttons, dx, dy, wheel=0):
        if not self.mouse_dev:
            return

        def s8(value):
            value = min(max(int(value), -127), 127)
            return value & 0xFF

        report = [
            self.HID_REPORT_MOUSE,
            int(buttons) & 0xFF,
            s8(dx),
            s8(dy),
            s8(wheel),
        ]
        self._write_hid_report(self.mouse_dev, report, report[1:])

    def _raw_touch(self, flags, x, y):
        if not self.touch_dev:
            return
        flags = (flags | 0x02) & 0xFF
        report = [
            self.HID_REPORT_TOUCH,
            flags,
            x & 0xFF,
            (x >> 8) & 0xFF,
            y & 0xFF,
            (y >> 8) & 0xFF,
            0x00,
        ]
        self._write_hid_report(self.touch_dev, report, report[1:-1])

    def _write_hid_report(self, dev, report, legacy_report=None):
        try:
            return dev.write(report)
        except Exception:
            if legacy_report is None:
                return None
            try:
                return dev.write(legacy_report)
            except Exception:
                return None

    def _send_feature_report(self, dev, report):
        if not dev:
            return False
        try:
            result = dev.send_feature_report(report)
            return result is None or result >= 0
        except AttributeError:
            return False
        except Exception:
            return False

    @staticmethod
    def parse_config_input_status(payload):
        """Parses recovered MI_00 request 0xB2 InputStatusInfo bytes."""
        if payload is None or len(payload) < 29:
            return None

        def ascii_z(start, end):
            raw = bytes(payload[start:end]).split(b"\x00", 1)[0]
            return raw.decode("ascii", errors="ignore") or None

        source = ascii_z(0, 12)
        mode_name = ascii_z(12, 20) or "unknown"
        refresh_hz = int.from_bytes(bytes(payload[20:24]), "little") / 1000.0
        width = int.from_bytes(bytes(payload[24:26]), "little")
        height = int.from_bytes(bytes(payload[26:28]), "little")
        scan_flag_raw = int(payload[28]) & 0xFF
        progressive = scan_flag_raw == 0
        active = width > 0 and height > 0 and refresh_hz > 0

        return {
            "source": source,
            "mode_name": mode_name,
            "width": width,
            "height": height,
            "refresh_hz": refresh_hz,
            "scan_mode": "p" if progressive else "i",
            "scan_flag_raw": scan_flag_raw,
            "is_signal_active": active,
            "label": f"{source or 'unknown'} {width}x{height}{'p' if progressive else 'i'}@{refresh_hz:g}, {mode_name}" if active else "no signal",
        }

    @classmethod
    def parse_config_flags(cls, flags):
        """Parses recovered MI_00 requests 0xE2/0xE3 device flag byte."""
        if flags is None:
            return None
        if isinstance(flags, (bytes, bytearray, list, tuple)):
            if not flags:
                return None
            flags = flags[0]
        flags = int(flags) & 0xFF
        known = (
            cls.CONFIG_FLAG_PRESERVE_ASPECT_RATIO
            | cls.CONFIG_FLAG_PERFORMANCE_MODE
            | cls.CONFIG_FLAG_AUDIO_SELECTOR
        )
        return {
            "raw": flags,
            "preserve_aspect_ratio": bool(flags & cls.CONFIG_FLAG_PRESERVE_ASPECT_RATIO),
            "performance_mode": bool(flags & cls.CONFIG_FLAG_PERFORMANCE_MODE),
            "audio_selector_multichannel": bool(flags & cls.CONFIG_FLAG_AUDIO_SELECTOR),
            "unknown_bits": flags & ~known,
        }

    @classmethod
    def build_config_flags(cls, preserve_aspect_ratio=False, performance_mode=False, audio_selector_multichannel=False):
        """Builds the recovered MI_00 request 0xE3 device flag byte."""
        flags = 0
        if preserve_aspect_ratio:
            flags |= cls.CONFIG_FLAG_PRESERVE_ASPECT_RATIO
        if performance_mode:
            flags |= cls.CONFIG_FLAG_PERFORMANCE_MODE
        if audio_selector_multichannel:
            flags |= cls.CONFIG_FLAG_AUDIO_SELECTOR
        return flags

    @staticmethod
    def parse_config_user_mode(payload):
        """Parses one recovered MI_00 request 0xB3 UserMode record."""
        if payload is None or len(payload) < 5:
            return None
        width = int.from_bytes(bytes(payload[0:2]), "little")
        height = int.from_bytes(bytes(payload[2:4]), "little")
        disabled = bool(payload[4])
        return {
            "width": width,
            "height": height,
            "enabled": not disabled,
            "disabled_byte": int(payload[4]) & 0xFF,
        }

    @staticmethod
    def build_config_user_mode(width, height, enabled=True):
        """Builds one recovered MI_00 request 0xB3 UserMode record."""
        width = min(max(int(width), 0), 0xFFFF)
        height = min(max(int(height), 0), 0xFFFF)
        disabled = 0 if enabled else 1
        return [
            width & 0xFF,
            (width >> 8) & 0xFF,
            height & 0xFF,
            (height >> 8) & 0xFF,
            disabled,
        ]

    def set_performance_mode(self, enabled):
        """Toggles between MJPG (compressed) and YUY2 (uncompressed) modes."""
        with self._lock:
            if not self.cap or not self.cap.isOpened():
                return

            # Identify current camera state
            current_index = 0
            # We don't store the index directly, but we can infer it or just use the current camera name
            # Actually, switch_camera already handles index and name. 
            # Let's find the current index by re-scanning if needed, or store it.

            # Better: set_performance_mode should just update a flag and then 
            # we trigger a re-initialization of the capture.

            self.performance_mode_enabled = enabled
            code = cv2.VideoWriter_fourcc(*'MJPG') if enabled else cv2.VideoWriter_fourcc(*'YUY2')

            # Attempt to set it directly first (some backends allow this)
            self.cap.set(cv2.CAP_PROP_FOURCC, code)

            # Verify if it worked (OpenCV 4+ often ignores this)
            actual_code = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            if actual_code != code:
                # If direct set failed, we MUST restart the capture
                # But we don't want to lose the stream in the GUI
                # So we'll just flag it for the next switch_camera or 
                # do a quick restart if a camera is active.
                if self.current_camera_name:
                    # Find index from name
                    cameras = self.list_available_cameras()
                    target_idx = -1
                    for idx, name in cameras:
                        if name == self.current_camera_name:
                            target_idx = idx; break

                    if target_idx != -1:
                        # We release and reopen
                        self.cap.release()
                        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
                        self.cap = cv2.VideoCapture(target_idx, backend)
                        self.cap.set(cv2.CAP_PROP_FOURCC, code)
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                        return True
            return False
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
        
        root = Path(RUNTIME_SESSION_ROOT)
        if not root.exists():
            return 0

        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                try:
                    path.unlink()
                    count += 1
                except: pass

        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
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
