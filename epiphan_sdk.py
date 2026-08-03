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
from hid_discovery import (
    EPIPHAN_KVM2USB3_PROFILE,
    DiscoveryDiagnostic,
    discover_hid_devices,
)
from keyboard_input import KeyboardActionResult, KeyboardCodec, KeyboardReportProfile, KeyboardState

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

    def __init__(
        self,
        target_name="KVM2USB 3.0",
        *,
        hid_serial=None,
        hid_path=None,
        development_mode=False,
    ):
        self.vid = 0x2b77
        self.pid = 0x3661
        self.kb_dev = None
        self.mouse_dev = None
        self.touch_dev = None
        self.sys_dev = None
        self.hid_serial = hid_serial
        self.hid_path = hid_path
        self.development_mode = development_mode
        self.hid_discovery = None
        self.hid_diagnostics = []
        self.hid_connection_ready = False
        self.keyboard_codec = KeyboardCodec()
        self.keyboard_state = KeyboardState(self.keyboard_codec)
        self.cap = None
        self.latest_frame = None
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
        entries = hid.enumerate()
        self.hid_discovery = discover_hid_devices(
            entries,
            profiles=(EPIPHAN_KVM2USB3_PROFILE,),
            serial=self.hid_serial,
            stable_path=self.hid_path,
            development_mode=self.development_mode,
        )
        self.hid_discovery.connection_ready = False
        self.hid_diagnostics = list(self.hid_discovery.diagnostics)
        selected = self.hid_discovery.selected
        if selected is None or not self.hid_discovery.topology_valid:
            return

        keyboard_collection = next(
            (collection for collection in selected.profile.collections if collection.role == "keyboard"),
            None,
        )
        if keyboard_collection is not None:
            self.keyboard_codec = KeyboardCodec(
                KeyboardReportProfile.from_collection(keyboard_collection)
            )
            self.keyboard_state = KeyboardState(self.keyboard_codec)

        handles = {
            "keyboard": "kb_dev",
            "relative_mouse": "mouse_dev",
            "absolute_pointer": "touch_dev",
            "system": "sys_dev",
        }
        opened = []
        for role, record in selected.collections.items():
            try:
                dev = hid.device()
                dev.open_path(record.path)
            except Exception as exc:
                self.hid_diagnostics.append(DiscoveryDiagnostic(
                    "inaccessible_collection",
                    f"HID collection {role} could not be opened: {exc}",
                    device_id=selected.device_id,
                    role=role,
                    path=record.path_text,
                ))
                for opened_dev in opened:
                    try:
                        opened_dev.close()
                    except Exception:
                        pass
                for handle_name in handles.values():
                    setattr(self, handle_name, None)
                return
            setattr(self, handles[role], dev)
            opened.append(dev)

        required_handles = (self.kb_dev, self.mouse_dev, self.touch_dev, self.sys_dev)
        self.hid_connection_ready = all(handle is not None for handle in required_handles)
        self.hid_discovery.connection_ready = self.hid_connection_ready

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
        x_percent = min(max(float(x_percent), 0.0), 1.0)
        y_percent = min(max(float(y_percent), 0.0), 1.0)
        self._log_event("MOUSE_CLICK", f"{x_percent:.2f},{y_percent:.2f} btn={button}")
        if not self.touch_dev: return
        x = int(x_percent * 32767); y = int(y_percent * 32767)
        report = [button & 0xFF, x & 0xFF, (x >> 8) & 0xFF, y & 0xFF, (y >> 8) & 0xFF]
        self.touch_dev.write([0x00] + report)
        time.sleep(0.1); self.touch_dev.write([0x00, 0, 0, 0, 0, 0])

    def _write_keyboard_reports(self, reports):
        if not self.kb_dev:
            self.keyboard_state.reset()
            return KeyboardActionResult(False, "no_device", "Keyboard HID collection is unavailable.")
        try:
            for report in reports:
                self.kb_dev.write(list(report))
        except Exception as exc:
            self.keyboard_state.reset()
            return KeyboardActionResult(False, "write_failed", f"Keyboard report write failed: {exc}")
        return KeyboardActionResult(True, reports=tuple(reports))

    def _send_keyboard_action(self, action):
        if not action.ok:
            return action
        return self._write_keyboard_reports(action.reports)

    def key_down(self, key):
        self._log_event("KEYBOARD_KEY_DOWN", str(key))
        action, _ = self.keyboard_state.key_down(key)
        return self._send_keyboard_action(action)

    def key_up(self, key):
        self._log_event("KEYBOARD_KEY_UP", str(key))
        action, _ = self.keyboard_state.key_up(key)
        return self._send_keyboard_action(action)

    def raw_key_down(self, usage):
        try:
            usage = int(usage)
        except (TypeError, ValueError):
            return KeyboardActionResult(False, "invalid_usage", "Keyboard usage must be an integer.")
        action, _ = self.keyboard_state.key_down_usage(usage, f"0x{usage:02x}")
        return self._send_keyboard_action(action)

    def raw_key_up(self, usage):
        try:
            usage = int(usage)
        except (TypeError, ValueError):
            return KeyboardActionResult(False, "invalid_usage", "Keyboard usage must be an integer.")
        action, _ = self.keyboard_state.key_up_usage(usage, f"0x{usage:02x}")
        return self._send_keyboard_action(action)

    def press(self, key_name):
        self._log_event("KEYBOARD_PRESS", str(key_name))
        down = self.key_down(key_name)
        if not down.ok:
            return down
        time.sleep(0.02)
        up = self.key_up(key_name)
        if not up.ok:
            self.release_all()
        return KeyboardActionResult(
            up.ok,
            up.code,
            up.message,
            reports=down.reports + up.reports,
            details=up.details,
        )

    def hotkey(self, *args):
        self._log_event("KEYBOARD_HOTKEY", "+".join(str(arg) for arg in args))
        pressed = []
        reports = []
        for key in args:
            action = self.key_down(key)
            if not action.ok:
                self.release_all()
                return action
            reports.extend(action.reports)
            pressed.append(key)
        for key in reversed(pressed):
            action = self.key_up(key)
            reports.extend(action.reports)
            if not action.ok:
                self.release_all()
                return action
        return KeyboardActionResult(True, reports=tuple(reports))

    def type_text(self, text, layout="us"):
        if layout.lower() != "us":
            return KeyboardActionResult(False, "unsupported_layout", f"Unsupported keyboard layout {layout!r}.")
        reports = []
        for index, char in enumerate(text):
            character = self.keyboard_codec.character(char)
            if character is None:
                self.release_all()
                return KeyboardActionResult(
                    False,
                    "unsupported_character",
                    f"Unsupported character {char!r} at index {index}.",
                    reports=tuple(reports),
                    details={"character": char, "index": index, "layout": layout},
                )
            modifiers, usage = character
            added_shift = bool(modifiers & self.keyboard_codec.MODIFIERS["shift"] and "shift" not in self.keyboard_state.active_modifiers)
            if added_shift:
                action = self.key_down("shift")
                if not action.ok:
                    self.release_all()
                    return action
                reports.extend(action.reports)
            action, _ = self.keyboard_state.key_down_usage(usage, char)
            action = self._send_keyboard_action(action)
            if not action.ok:
                self.release_all()
                return action
            reports.extend(action.reports)
            action, _ = self.keyboard_state.key_up_usage(usage, char)
            action = self._send_keyboard_action(action)
            if not action.ok:
                self.release_all()
                return action
            reports.extend(action.reports)
            if added_shift:
                action = self.key_up("shift")
                if not action.ok:
                    self.release_all()
                    return action
                reports.extend(action.reports)
            time.sleep(0.05)
        return KeyboardActionResult(True, reports=tuple(reports))

    def type(self, text):
        self._log_event("KEYBOARD_TYPE", text)
        return self.type_text(text, layout="us")

    def release_all(self):
        report = self.keyboard_codec.encode(0, ())
        self.keyboard_state.reset()
        if not self.kb_dev:
            return KeyboardActionResult(False, "no_device", "Keyboard HID collection is unavailable.", reports=(report,))
        return self._write_keyboard_reports((report,))

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
        try:
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
        finally:
            self.release_all()

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
        try:
            report = self.keyboard_codec.encode(mods, keys)
        except ValueError as exc:
            return KeyboardActionResult(False, "invalid_report", str(exc))
        return self._write_keyboard_reports((report,))

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
        self.release_all()
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
