from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QSlider, QSpinBox, QPushButton, QComboBox, 
                             QGroupBox, QFormLayout, QTabWidget, QWidget, 
                             QListWidget, QInputDialog, QMessageBox, QTextEdit)
from PySide6.QtCore import Qt

class SettingsDialog(QDialog):
    def __init__(self, sdk, parent=None):
        super().__init__(parent)
        self.sdk = sdk
        self.setWindowTitle("Hardware & Processor Settings")
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout(self)
        
        # Main Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_motion_tab(), "Motion Detection")
        self.tabs.addTab(self._create_hardware_tab(), "Hardware Tuning")
        self.tabs.addTab(self._create_presets_tab(), "Presets")
        self.tabs.addTab(self._create_macro_tab(), "Macro Editor")
        
        layout.addWidget(self.tabs)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.save_as_btn = QPushButton("Save Current as Preset...")
        self.save_as_btn.clicked.connect(self.save_current_as_preset)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_settings)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.save_as_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _create_motion_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        group = QGroupBox("Sensitivity Parameters")
        form = QFormLayout(group)
        
        self.thresh_spin = QSpinBox()
        self.thresh_spin.setRange(1, 255)
        self.thresh_spin.setValue(self.sdk.motion_detector.threshold)
        form.addRow("Threshold (Pixel Delta):", self.thresh_spin)
        
        self.area_spin = QSpinBox()
        self.area_spin.setRange(1, 10000)
        self.area_spin.setValue(self.sdk.motion_detector.min_area)
        form.addRow("Minimum Area (Pixels):", self.area_spin)
        
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _create_hardware_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        group = QGroupBox("UVC Camera Controls")
        form = QFormLayout(group)
        
        self.bright_slider = QSlider(Qt.Horizontal)
        self.bright_slider.setRange(0, 255)
        self.bright_slider.setValue(128)
        form.addRow("Brightness:", self.bright_slider)
        
        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(0, 255)
        self.contrast_slider.setValue(128)
        form.addRow("Contrast:", self.contrast_slider)
        
        self.sat_slider = QSlider(Qt.Horizontal)
        self.sat_slider.setRange(0, 255)
        self.sat_slider.setValue(128)
        form.addRow("Saturation:", self.sat_slider)
        
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _create_presets_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        
        # Sidebar for preset selection
        self.preset_list = QListWidget()
        self.refresh_preset_list()
        self.preset_list.currentRowChanged.connect(self.load_preset_preview)
        
        # Details view
        details_group = QGroupBox("Preset Details")
        self.details_label = QLabel("Select a preset to view details")
        self.details_label.setWordWrap(True)
        self.details_label.setAlignment(Qt.AlignTop)
        det_layout = QVBoxLayout(details_group)
        det_layout.addWidget(self.details_label)
        
        self.startup_btn = QPushButton("Set as Startup Preset")
        self.startup_btn.clicked.connect(self.set_as_startup)
        det_layout.addWidget(self.startup_btn)
        
        det_layout.addStretch()
        
        btn_box = QHBoxLayout()
        self.load_btn = QPushButton("Load Preset")
        self.load_btn.clicked.connect(self.apply_preset)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_selected_preset)
        btn_box.addWidget(self.load_btn)
        btn_box.addWidget(self.delete_btn)
        det_layout.addLayout(btn_box)
        
        layout.addWidget(self.preset_list, 1)
        layout.addWidget(details_group, 2)
        
        return page

    def _create_macro_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        help_text = QLabel("<b>HID Macro DSL Guide:</b><br>"
                          "DELAY 500 | TYPE hello | PRESS enter | HOTKEY ctrl alt delete | CLICK 0.5 0.5")
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(help_text)
        
        self.macro_edit = QTextEdit()
        self.macro_edit.setPlaceholderText("# Enter macro script here...\nDELAY 500\nTYPE Admin123\nPRESS enter")
        self.macro_edit.setFontFamily("Consolas")
        layout.addWidget(self.macro_edit)
        
        btn_layout = QHBoxLayout()
        self.run_macro_btn = QPushButton("▶ Run Macro (Immediate)")
        self.run_macro_btn.clicked.connect(self.run_macro_logic)
        self.run_macro_btn.setStyleSheet("background-color: #dcfce7; color: #166534; font-weight: bold;")
        
        self.clear_macro_btn = QPushButton("Clear")
        self.clear_macro_btn.clicked.connect(self.macro_edit.clear)
        
        btn_layout.addWidget(self.run_macro_btn)
        btn_layout.addWidget(self.clear_macro_btn)
        layout.addLayout(btn_layout)
        
        return page

    def run_macro_logic(self):
        script = self.macro_edit.toPlainText()
        if not script.strip():
            return
        
        self.run_macro_btn.setEnabled(False)
        self.run_macro_btn.setText("⏳ Executing...")
        # We'll run it in a thread to avoid blocking UI during DELAYs
        import threading
        def _run():
            self.sdk.run_macro(script)
            # Re-enable on UI thread
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self.run_macro_btn, "setEnabled", Qt.QueuedConnection, Q_ARG(bool, True))
            QMetaObject.invokeMethod(self.run_macro_btn, "setText", Qt.QueuedConnection, Q_ARG(str, "▶ Run Macro (Immediate)"))
        
        threading.Thread(target=_run, daemon=True).start()

    def refresh_preset_list(self):
        self.preset_list.clear()
        for name in sorted(self.sdk.PRESETS.keys()):
            self.preset_list.addItem(name)

    def load_preset_preview(self, index):
        if not self.preset_list.currentItem(): return
        name = self.preset_list.currentItem().text()
        p = self.sdk.PRESETS[name]
        is_system = name in ["Default", "High Sensitivity", "High Contrast (OCR)", "VGA Legacy"]
        is_startup = self.sdk.config.get("startup_preset") == name
        
        text = f"<b>Preset: {name}</b><br>"
        text += f"<span style='color: #008800;'>[STARTUP PRESET]</span><br>" if is_startup else ""
        text += f"{'(System)' if is_system else '(User)'}<br><br>"
        text += f"Motion Threshold: {p['motion_threshold']}<br>"
        text += f"Motion Min Area: {p['motion_min_area']}<br>"
        text += f"Brightness: {p['brightness']}<br>"
        text += f"Contrast: {p['contrast']}<br>"
        text += f"Saturation: {p['saturation']}"
        self.details_label.setText(text)
        
        self.delete_btn.setEnabled(not is_system)
        self.startup_btn.setEnabled(not is_startup)

    def set_as_startup(self):
        if not self.preset_list.currentItem(): return
        name = self.preset_list.currentItem().text()
        self.sdk.config["startup_preset"] = name
        if self.sdk.save_config():
            self.load_preset_preview(0) # Refresh text
            QMessageBox.information(self, "Success", f"'{name}' is now your startup preset.")

    def apply_preset(self):
        if not self.preset_list.currentItem(): return
        name = self.preset_list.currentItem().text()
        if self.sdk.apply_preset(name):
            # Sync UI spinners/sliders with loaded preset
            p = self.sdk.PRESETS[name]
            self.thresh_spin.setValue(p['motion_threshold'])
            self.area_spin.setValue(p['motion_min_area'])
            self.bright_slider.setValue(p['brightness'])
            self.contrast_slider.setValue(p['contrast'])
            self.sat_slider.setValue(p['saturation'])
            print(f"Preset '{name}' applied successfully.")

    def save_current_as_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Enter preset name:")
        if ok and name:
            if name in ["Default", "High Sensitivity", "High Contrast (OCR)", "VGA Legacy"]:
                QMessageBox.warning(self, "Error", "Cannot overwrite system presets.")
                return
                
            params = {
                "motion_threshold": self.thresh_spin.value(),
                "motion_min_area": self.area_spin.value(),
                "brightness": self.bright_slider.value(),
                "contrast": self.contrast_slider.value(),
                "saturation": self.sat_slider.value()
            }
            if self.sdk.save_user_preset(name, params):
                self.refresh_preset_list()
                QMessageBox.information(self, "Success", f"Preset '{name}' saved.")
            else:
                QMessageBox.critical(self, "Error", "Failed to save preset.")

    def delete_selected_preset(self):
        if not self.preset_list.currentItem(): return
        name = self.preset_list.currentItem().text()
        if QMessageBox.question(self, "Delete", f"Are you sure you want to delete '{name}'?") == QMessageBox.Yes:
            if self.sdk.delete_user_preset(name):
                self.refresh_preset_list()
                self.details_label.setText("Select a preset to view details")
            else:
                QMessageBox.warning(self, "Error", "Could not delete preset.")

    def apply_settings(self):
        # Manually update SDK with UI values
        self.sdk.motion_detector.update_params(
            threshold=self.thresh_spin.value(),
            min_area=self.area_spin.value()
        )
        self.sdk.set_camera_property("brightness", self.bright_slider.value())
        self.sdk.set_camera_property("contrast", self.contrast_slider.value())
        self.sdk.set_camera_property("saturation", self.sat_slider.value())
        print("Settings Applied Successfully")
