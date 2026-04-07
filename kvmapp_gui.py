import sys
import time
import os
import cv2
import numpy as np
import threading
import subprocess
from PySide6.QtCore import Qt, QTimer, QSize, QPoint
from PySide6.QtGui import QImage, QPixmap, QAction, QIcon, QKeySequence, QGuiApplication, QCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                             QWidget, QStatusBar, QToolBar, QFileDialog, QMessageBox)
from epiphan_sdk import EpiphanKVM_SDK
from settings_dialog import SettingsDialog

class KvmAppGUI(QMainWindow):
    """
    A professional, full-featured GUI replacement for Epiphan KvmApp.exe.
    Powered by the reverse-engineered AgentKVM2USB SDK.
    """
    
    # Comprehensive Qt to HID Scan Code Map
    QT_HID_MAP = {
        Qt.Key_A: 0x04, Qt.Key_B: 0x05, Qt.Key_C: 0x06, Qt.Key_D: 0x07, Qt.Key_E: 0x08,
        Qt.Key_F: 0x09, Qt.Key_G: 0x0A, Qt.Key_H: 0x0B, Qt.Key_I: 0x0C, Qt.Key_J: 0x0D,
        Qt.Key_K: 0x0E, Qt.Key_L: 0x0F, Qt.Key_M: 0x10, Qt.Key_N: 0x11, Qt.Key_O: 0x12,
        Qt.Key_P: 0x13, Qt.Key_Q: 0x14, Qt.Key_R: 0x15, Qt.Key_S: 0x16, Qt.Key_T: 0x17,
        Qt.Key_U: 0x18, Qt.Key_V: 0x19, Qt.Key_W: 0x1A, Qt.Key_X: 0x1B, Qt.Key_Y: 0x1C, Qt.Key_Z: 0x1D,
        Qt.Key_1: 0x1E, Qt.Key_2: 0x1F, Qt.Key_3: 0x20, Qt.Key_4: 0x21, Qt.Key_5: 0x22,
        Qt.Key_6: 0x23, Qt.Key_7: 0x24, Qt.Key_8: 0x25, Qt.Key_9: 0x26, Qt.Key_0: 0x27,
        Qt.Key_Enter: 0x28, Qt.Key_Return: 0x28, Qt.Key_Escape: 0x29, Qt.Key_Backspace: 0x2A,
        Qt.Key_Tab: 0x2B, Qt.Key_Space: 0x2C, Qt.Key_Minus: 0x2D, Qt.Key_Equal: 0x2E,
        Qt.Key_BracketLeft: 0x2F, Qt.Key_BracketRight: 0x30, Qt.Key_Backslash: 0x31,
        Qt.Key_Semicolon: 0x33, Qt.Key_QuoteLeft: 0x34, Qt.Key_Comma: 0x36, Qt.Key_Period: 0x37, Qt.Key_Slash: 0x38,
        Qt.Key_F1: 0x3A, Qt.Key_F2: 0x3B, Qt.Key_F3: 0x3C, Qt.Key_F4: 0x3D, Qt.Key_F5: 0x3E,
        Qt.Key_F6: 0x3F, Qt.Key_F7: 0x40, Qt.Key_F8: 0x41, Qt.Key_F9: 0x42, Qt.Key_F10: 0x43,
        Qt.Key_F11: 0x44, Qt.Key_F12: 0x45, Qt.Key_Print: 0x46, Qt.Key_ScrollLock: 0x47,
        Qt.Key_Pause: 0x48, Qt.Key_Insert: 0x49, Qt.Key_Home: 0x4A, Qt.Key_PageUp: 0x4B,
        Qt.Key_Delete: 0x4C, Qt.Key_End: 0x4D, Qt.Key_PageDown: 0x4E,
        Qt.Key_Right: 0x4F, Qt.Key_Left: 0x50, Qt.Key_Down: 0x51, Qt.Key_Up: 0x52,
        Qt.Key_NumLock: 0x53
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AgentKVM2USB - Universal Control Application")
        self.setMinimumSize(1024, 768)
        
        # Initialize SDK
        self.sdk = EpiphanKVM_SDK()
        self.sdk.start_session() # Automatically start logging
        
        # UI State
        self.mouse_mode = "relative"
        self.is_recording = False
        self.is_grabbed = False
        self.host_key = Qt.Key_Control
        self._is_switching = False
        self.user_prefix = "dev" # Default prefix
        
        # Central Widget
        self.video_label = QLabel("INITIALIZING HARDWARE...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #111; color: #aaa; font-family: 'Consolas'; font-size: 18px;")
        self.setCentralWidget(self.video_label)
        
        self.setMouseTracking(True)
        self.video_label.setMouseTracking(True)

        self._create_menus()
        self._create_toolbar()
        self._create_status_bar()
        
        # Video Timer (30 FPS)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(33)
        
        # Status Timer (1s)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)

    def _create_menus(self):
        mb = self.menuBar()
        
        # File
        file_m = mb.addMenu("&File")
        file_m.addAction("&Save Still Image...", self.save_screenshot, QKeySequence.Save)
        file_m.addAction("&Copy Still Image to Buffer", self.copy_to_clipboard, "Ctrl+C")
        file_m.addSeparator()
        file_m.addAction("Cleanup Old Session Data...", self.cleanup_data)
        file_m.addSeparator()
        file_m.addAction("E&xit", self.close, "Alt+F4")

    def cleanup_data(self):
        msg = "Are you sure you want to delete all snapshots and logs older than 7 days?"
        if QMessageBox.question(self, "Cleanup", msg) == QMessageBox.Yes:
            count = self.sdk.cleanup_session_data(days=7)
            self.status.showMessage(f"Cleanup complete. Removed {count} files.", 5000)
            QMessageBox.information(self, "Cleanup", f"Successfully removed {count} old files.")
        
        # View
        view_m = mb.addMenu("&View")
        self.fs_act = view_m.addAction("&Full Screen", self.toggle_fullscreen, "F11")
        self.fs_act.setCheckable(True)
        view_m.addAction("Show &Host Cursor", self.toggle_cursor_vis).setCheckable(True)
        
        # Devices (Manual Selection)
        self.dev_m = mb.addMenu("&Devices")
        self.refresh_devices()

        # Tools
        tools_m = mb.addMenu("&Tools")
        tools_m.addAction("Send Ctrl+Alt+Del", lambda: self.sdk.hotkey("ctrl", "alt", "delete"))
        tools_m.addAction("Send Alt+Tab", lambda: self.sdk.hotkey("alt", "tab"))
        tools_m.addSeparator()
        self.rec_act = tools_m.addAction("Start &Recording session", self.toggle_recording)
        
        # Options
        opt_m = mb.addMenu("&Options")
        
        self.log_act = opt_m.addAction("Enable Session Logging", self.toggle_logging)
        self.log_act.setCheckable(True)
        self.log_act.setChecked(True)
        
        opt_m.addSeparator()
        self.motion_act = opt_m.addAction("Enable Motion Detection", self.toggle_motion)
        self.motion_act.setCheckable(True)
        self.boxes_act = opt_m.addAction("Show Motion Boxes", self.toggle_boxes)
        self.boxes_act.setCheckable(True)
        self.overlay_act = opt_m.addAction("Show HUD Overlays", self.toggle_overlays)
        self.overlay_act.setCheckable(True)
        self.overlay_act.setChecked(True)
        self.srt_act = opt_m.addAction("Generate SRT for Recordings", self.toggle_srt)
        self.srt_act.setCheckable(True)
        self.srt_act.setChecked(True)
        
        opt_m.addSeparator()
        mouse_sm = opt_m.addMenu("Mouse Emulation")
        self.rel_act = mouse_sm.addAction("Relative (Legacy/BIOS)", lambda: self.set_mouse_mode("relative"))
        self.rel_act.setCheckable(True)
        self.rel_act.setChecked(True)
        self.abs_act = mouse_sm.addAction("Absolute (Modern/Touch)", lambda: self.set_mouse_mode("absolute"))
        self.abs_act.setCheckable(True)
        
        opt_m.addSeparator()
        self.perf_act = opt_m.addAction("&Performance Mode", lambda: self.sdk.set_performance_mode(self.perf_act.isChecked()))
        self.perf_act.setCheckable(True)
        opt_m.addAction("&Reconnect Remote USB", self.sdk.reenumerate_target)
        opt_m.addSeparator()
        opt_m.addAction("&Settings...", self.open_settings)
        opt_m.addAction("&Configuration tool...", self.run_config_tool)

    def _create_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.addAction("📸 Capture", self.save_screenshot)
        tb.addAction("📋 Copy", self.copy_to_clipboard)
        tb.addSeparator()
        
        # Motion Sensitivity Quick Toggle
        self.sens_btn = tb.addAction("⚡ Sens: Med", self.toggle_sensitivity_quick)
        self.sens_level = 1 # 0=Low, 1=Med, 2=High
        
        tb.addSeparator()
        tb.addAction("🔄 Reconnect", self.sdk.reenumerate_target)
        tb.addSeparator()
        self.grab_btn = tb.addAction("🔒 Grab Input (Ctrl+G)", self.toggle_grab)

    def toggle_sensitivity_quick(self):
        self.sens_level = (self.sens_level + 1) % 3
        levels = [
            ("Low", 40, 1000),
            ("Med", 25, 500),
            ("High", 10, 100)
        ]
        label, thresh, area = levels[self.sens_level]
        self.sdk.motion_detector.update_params(threshold=thresh, min_area=area)
        self.sens_btn.setText(f"⚡ Sens: {label}")
        self.status.showMessage(f"Motion Sensitivity set to {label}", 3000)

    def _create_status_bar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    # --- LOGIC ---

    def refresh_devices(self):
        self.dev_m.clear()
        cameras = self.sdk.list_available_cameras()
        if not cameras:
            self.dev_m.addAction("No Devices Found")
        for idx, name in cameras:
            act = QAction(name, self)
            act.triggered.connect(lambda checked, i=idx, n=name: self._switch_camera(i, n))
            self.dev_m.addAction(act)
        self.dev_m.addSeparator()
        self.dev_m.addAction("Refresh List", self.refresh_devices)

    def _switch_camera(self, index, name):
        self._is_switching = True
        self.video_label.setText(f"CONNECTING TO {name}...")
        # Use a single-shot timer to allow the UI to update before blocking
        QTimer.singleShot(100, lambda: self._do_switch(index, name))

    def _do_switch(self, index, name):
        self.sdk.switch_camera(index, name)
        self._is_switching = False
        self.status.showMessage(f"Switched to {name}", 3000)

    def update_status(self):
        state = self.sdk.get_status()
        l = state['leds']
        led_str = f"LEDs: [{'C' if l['caps'] else '-'}{'N' if l['num'] else '-'}{'S' if l['scroll'] else '-'}]"
        sig_str = "SIGNAL OK" if state['is_signal_active'] else "NO SIGNAL"
        motion_str = " | [MOTION]" if self.sdk.is_motion_detected and self.sdk.enable_motion_detection else ""
        self.status.showMessage(f"Mode: {self.mouse_mode.upper()} | Res: {state['resolution']} | {sig_str} | {led_str}{motion_str}")

    def update_frame(self):
        if self._is_switching:
            return

        frame_copy = self.sdk.get_processed_frame()

        if frame_copy is not None:
            rgb = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            px = QPixmap.fromImage(qt_img)
            self.video_label.setPixmap(px.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            if self.sdk.cap is None:
                self.video_label.setText("NO HARDWARE DETECTED\nSelect a device from the 'Devices' menu")
            else:
                self.video_label.setText("NO SIGNAL DETECTED\nCheck physical VGA/DVI connection")

    def toggle_grab(self):
        self.is_grabbed = not self.is_grabbed
        if self.is_grabbed:
            self.grab_btn.setText("🔓 Release Input (Ctrl)")
            self.setCursor(Qt.BlankCursor if self.mouse_mode == "relative" else Qt.CrossCursor)
            self.status.showMessage("INPUT GRABBED. Press CTRL to release.", 5000)
        else:
            self.grab_btn.setText("🔒 Grab Input (Ctrl+G)")
            self.setCursor(Qt.ArrowCursor)
            self.status.showMessage("Input Released", 2000)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_G and event.modifiers() & Qt.ControlModifier:
            self.toggle_grab()
            return
        
        if self.is_grabbed:
            if event.key() == self.host_key:
                self.toggle_grab()
                return
            
            modifiers = 0
            if event.modifiers() & Qt.ControlModifier: modifiers |= 0x01
            if event.modifiers() & Qt.ShiftModifier: modifiers |= 0x02
            if event.modifiers() & Qt.AltModifier: modifiers |= 0x04
            if event.modifiers() & Qt.MetaModifier: modifiers |= 0x08
            
            key = self.QT_HID_MAP.get(event.key(), 0)
            self.sdk._raw_kb(modifiers, [key] if key else [])

    def keyReleaseEvent(self, event):
        if self.is_grabbed:
            self.sdk._raw_kb(0, [0])

    def mouseMoveEvent(self, event):
        if self.is_grabbed and self.mouse_mode == "absolute":
            lbl_w, lbl_h = self.video_label.width(), self.video_label.height()
            x_p = event.position().x() / lbl_w
            y_p = event.position().y() / lbl_h
            self.sdk.click(x_p, y_p, button=0)

    def mousePressEvent(self, event):
        if not self.is_grabbed:
            self.toggle_grab()
            return
            
        btn = 1 if event.button() == Qt.LeftButton else 2
        x_p = event.position().x() / self.video_label.width()
        y_p = event.position().y() / self.video_label.height()
        self.sdk.click(x_p, y_p, button=btn)

    # --- ACTIONS ---

    def toggle_logging(self, checked):
        self.sdk.start_session(enable_logging=checked)
        self.status.showMessage(f"Logging {'Enabled' if checked else 'Disabled'}", 3000)

    def toggle_motion(self, checked):
        self.sdk.enable_motion_detection = checked
        self.status.showMessage(f"Motion Detection {'Enabled' if checked else 'Disabled'}", 3000)

    def toggle_boxes(self, checked):
        self.sdk.show_motion_boxes = checked

    def toggle_overlays(self, checked):
        self.sdk.enable_overlays = checked

    def toggle_srt(self, checked):
        pass

    def set_mouse_mode(self, mode):
        self.mouse_mode = mode
        self.rel_act.setChecked(mode == "relative")
        self.abs_act.setChecked(mode == "absolute")

    def copy_to_clipboard(self):
        with self.sdk._lock:
            if self.sdk.latest_frame is not None:
                rgb = cv2.cvtColor(self.sdk.latest_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qi = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                QGuiApplication.clipboard().setImage(qi)
                self.status.showMessage("Frame copied to clipboard", 3000)

    def save_screenshot(self):
        path = self.sdk.get_screen(prefix=self.user_prefix)
        if path:
            self.status.showMessage(f"Captured: {os.path.basename(path)}", 3000)

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.rec_act.setText("Stop Recording")
            gen_srt = self.srt_act.isChecked()
            threading.Thread(target=self.sdk.record_session, 
                             args=(3600, self.user_prefix, gen_srt), 
                             daemon=True).start()
            self.status.showMessage(f"Recording Started {'(with SRT)' if gen_srt else ''}", 3000)
        else:
            self.is_recording = False
            self.rec_act.setText("Start Recording")
            self.status.showMessage("Recording Stopped", 3000)

    def toggle_fullscreen(self, checked):
        if checked: self.showFullScreen()
        else: self.showNormal()

    def toggle_cursor_vis(self):
        pass

    def open_settings(self):
        dlg = SettingsDialog(self.sdk, self)
        dlg.exec()

    def run_config_tool(self):
        p = os.path.join(os.getcwd(), "EpiphanTools", "CaptureConfig", "EpiphanCaptureConfig-r40343-20171227", "EpiphanCaptureConfig.exe")
        if os.path.exists(p): subprocess.Popen([p])
        else: QMessageBox.warning(self, "Error", "Config Tool not found in EpiphanTools folder.")

    def closeEvent(self, event):
        log_path = self.sdk.save_log(prefix=self.user_prefix)
        print(f"Session log saved to: {log_path}")
        self.sdk.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = KvmAppGUI()
    win.show()
    sys.exit(app.exec())
