import sys
import time
import os
import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                             QWidget, QStatusBar, QToolBar, QFileDialog, QMessageBox)
from epiphan_sdk import EpiphanKVM_SDK

class KvmAppGUI(QMainWindow):
    """
    A full-featured GUI replacement for Epiphan KvmApp.exe.
    Powered by the reverse-engineered AgentKVM2USB SDK.
    """
    
    # Qt to HID Scan Code Map (Selection)
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
        Qt.Key_F11: 0x44, Qt.Key_F12: 0x45, Qt.Key_Delete: 0x4C,
        Qt.Key_Right: 0x4F, Qt.Key_Left: 0x50, Qt.Key_Down: 0x51, Qt.Key_Up: 0x52
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AgentKVM2USB - Control Application")
        self.setMinimumSize(800, 600)
        
        # Initialize SDK
        try:
            self.sdk = EpiphanKVM_SDK()
        except Exception as e:
            QMessageBox.critical(self, "Hardware Error", f"Failed to initialize KVM hardware: {e}")
            sys.exit(1)

        # UI State
        self.mouse_mode = "relative"
        self.is_recording = False
        
        # Central Widget (Video Display)
        self.video_label = QLabel("No Signal")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: white;")
        self.setCentralWidget(self.video_label)
        
        # Enable Mouse Tracking for Absolute Coordinates
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
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("&File")
        save_action = QAction("&Save Still Image...", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_screenshot)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View Menu
        view_menu = menubar.addMenu("&View")
        self.fullscreen_action = QAction("&Full Screen", self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.setShortcut(Qt.Key_F11)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(self.fullscreen_action)
        
        # Tools Menu
        tools_menu = menubar.addMenu("&Tools")
        cad_action = QAction("Send Ctrl+Alt+Del", self)
        cad_action.triggered.connect(lambda: self.sdk.hotkey("ctrl", "alt", "delete"))
        tools_menu.addAction(cad_action)
        
        self.record_action = QAction("Start &Recording session", self)
        self.record_action.triggered.connect(self.toggle_recording)
        tools_menu.addAction(self.record_action)
        
        # Options Menu
        opt_menu = menubar.addMenu("&Options")
        
        # Mouse Mode Submenu
        mouse_menu = opt_menu.addMenu("Mouse Emulation")
        self.rel_mouse_action = QAction("Relative (Mouse)", self)
        self.rel_mouse_action.setCheckable(True)
        self.rel_mouse_action.setChecked(True)
        self.abs_mouse_action = QAction("Absolute (Touch/Tablet)", self)
        self.abs_mouse_action.setCheckable(True)
        
        mouse_menu.addAction(self.rel_mouse_action)
        mouse_menu.addAction(self.abs_mouse_action)
        
        self.rel_mouse_action.triggered.connect(lambda: self.set_mouse_mode("relative"))
        self.abs_mouse_action.triggered.connect(lambda: self.set_mouse_mode("absolute"))
        
        opt_menu.addSeparator()
        autotune_action = QAction("&Autotune Brightness", self)
        autotune_action.triggered.connect(self.sdk.autotune)
        opt_menu.addAction(autotune_action)
        
        reenum_action = QAction("&Reconnect Remote USB", self)
        reenum_action.triggered.connect(self.sdk.reenumerate_target)
        opt_menu.addAction(reenum_action)

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        # Add basic icons or text buttons
        toolbar.addAction("Capture", self.save_screenshot)
        toolbar.addAction("Autotune", self.sdk.autotune)
        toolbar.addAction("Reconnect", self.sdk.reenumerate_target)

    def _create_status_bar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Initializing...")

    def update_status(self):
        state = self.sdk.get_status()
        res = state['resolution']
        leds = state['leds']
        led_str = f"L: {'C' if leds['caps'] else '-'}{'N' if leds['num'] else '-'}{'S' if leds['scroll'] else '-'}"
        self.status.showMessage(f"Resolution: {res} | Signal: {'OK' if state['is_signal_active'] else 'NO SIGNAL'} | {led_str} | Mode: {self.mouse_mode.upper()}")

    def update_frame(self):
        frame = self.sdk.latest_frame
        if frame is not None:
            # Convert BGR to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            
            # Scale to window while keeping aspect ratio
            pixmap = QPixmap.fromImage(qt_img)
            self.video_label.setPixmap(pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.video_label.setText("NO SIGNAL DETECTED")

    # --- INPUT EVENT HANDLING ---
    
    def keyPressEvent(self, event):
        self._handle_key(event, True)

    def keyReleaseEvent(self, event):
        self._handle_key(event, False)

    def _handle_key(self, event, is_press):
        modifiers = 0
        if event.modifiers() & Qt.ControlModifier: modifiers |= 0x01
        if event.modifiers() & Qt.ShiftModifier: modifiers |= 0x02
        if event.modifiers() & Qt.AltModifier: modifiers |= 0x04
        if event.modifiers() & Qt.MetaModifier: modifiers |= 0x08
        
        key = self.QT_HID_MAP.get(event.key(), 0)
        
        if is_press:
            self.sdk._raw_kb(modifiers, [key] if key else [])
        else:
            self.sdk._raw_kb(0, [0]) # Release all

    def mouseMoveEvent(self, event):
        if self.mouse_mode == "absolute":
            # Calculate percent based on the label geometry (accounting for pillarboxing)
            # For simplicity in this replacement, we use the raw window relative coords
            x_p = event.position().x() / self.width()
            y_p = event.position().y() / self.height()
            self.sdk.click(x_p, y_p, button=0) # Move only

    def mousePressEvent(self, event):
        btn = 1 if event.button() == Qt.LeftButton else 2
        x_p = event.position().x() / self.width()
        y_p = event.position().y() / self.height()
        self.sdk.click(x_p, y_p, button=btn)

    # --- UI ACTIONS ---

    def set_mouse_mode(self, mode):
        self.mouse_mode = mode
        self.rel_mouse_action.setChecked(mode == "relative")
        self.abs_mouse_action.setChecked(mode == "absolute")
        # In relative mode, we might want to grab the cursor
        if mode == "relative":
            self.setCursor(Qt.BlankCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def toggle_fullscreen(self):
        if self.fullscreen_action.isChecked():
            self.showFullScreen()
        else:
            self.showNormal()

    def save_screenshot(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Still Image", "", "PNG Images (*.png);;JPEG Images (*.jpg)")
        if filename:
            path = self.sdk.get_screen(filename)
            if path:
                self.status.showMessage(f"Saved to {filename}", 3000)

    def toggle_recording(self):
        if not self.is_recording:
            filename, _ = QFileDialog.getSaveFileName(self, "Start Session Recording", "session.mp4", "MP4 Video (*.mp4)")
            if filename:
                self.is_recording = True
                self.record_action.setText("Stop &Recording session")
                # Start recording in a thread so UI doesn't hang
                threading.Thread(target=self.sdk.record_session, args=(3600, filename), daemon=True).start()
        else:
            self.sdk._stop_video = True # This is a bit hacky, should have a dedicated stop_recording
            self.is_recording = False
            self.record_action.setText("Start &Recording session")

    def closeEvent(self, event):
        self.sdk.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KvmAppGUI()
    window.show()
    sys.exit(app.exec())
