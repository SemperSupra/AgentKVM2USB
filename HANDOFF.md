# AgentKVM2USB Handoff - Session: April 6, 2026

## 🟢 Status & Completed Features

### 1. Vision & Frame Processing (Enhanced)
- **Modular Engine**: `frame_processor.py` provides real-time video enhancements, motion detection, and HUD overlays.
- **SRT Syncing**: Sidecar `.srt` files are generated during recordings to log motion events with sub-second accuracy.
- **Toolbar Sensitivity**: Added a "⚡ Sens" quick-toggle to the main toolbar to cycle between Low, Med, and High motion sensitivity.

### 2. Device-Aware Persistence
- **Per-Device Preset Memory**: The app now remembers which preset (e.g., "VGA Legacy") was last used for a specific hardware device (e.g., "KVM2USB 3.0") using `config.json`.
- **Automatic Application**: Switching cameras now triggers an immediate, relevant preset load without user intervention.

### 3. HID Automation & Macros
- **Macro DSL**: Implemented `run_macro` in the SDK to execute Domain Specific Language (DSL) scripts (e.g., `DELAY 500 | TYPE hello | PRESS enter`).
- **Macro Editor GUI**: A new tab in the Settings dialog allows users to write, test, and execute macros against the live hardware.
- **Robust Performance Mode**: Refactored `set_performance_mode` to reliably switch between MJPG and YUY2 by restarting the capture stream, ensuring high frame rates on demand.

### 4. Session & Log Management
- **Cleanup Tool**: Added "Cleanup Old Session Data" to the File menu, allowing users to safely delete snapshots, logs, and recordings older than 7 days.
- **Unified Logging**: Improved session event logging to include hardware-level re-enumeration and OSD status updates.

### 5. Validation
- **`test_sdk.py`**: Expanded to 8 tests covering the new Macro DSL, Motion Detection logic, SRT generation, and Preset Persistence. All **PASS**.
- **Mock Testing**: Verified per-device memory and cleanup logic using specialized mock scripts.

---

## 🟡 Pending Work & Next Steps

### 1. Vision-Conditional Macros (DSL Extension)
- **Goal**: Make macros "aware" of the screen state.
- **Tasks**:
  - Extend DSL with `WAIT_FOR_MOTION`, `WAIT_FOR_SIGNAL`, and `WAIT_FOR_NO_MOTION`.
  - Implement feedback-loop automation where a macro waits for a reboot to finish before typing a password.

### 2. Named Macro Library
- **Goal**: Allow users to save their DSL scripts with names (e.g., "Reset to BIOS").
- **Tasks**:
  - Add a persistent gallery in the Macro Editor to store and recall common sequences.

### 3. Remote Control API (Headless Mode)
- **Goal**: Enable cloud-based AI agents to control the hardware.
- **Tasks**:
  - Implement a FastAPI or WebSocket wrapper to expose the SDK's core functions (frame capture and macro execution) over the network.

---

## 🛠️ Environment Note
- **Dependencies**: `pygrabber`, `PySide6`, `opencv-python`, `hidapi`.
- **Files Created/Modified**:
  - `epiphan_sdk.py` (Updated: Per-device logic, Macro DSL, Cleanup)
  - `kvmapp_gui.py` (Updated: Toolbar, Cleanup menu, Camera naming)
  - `settings_dialog.py` (Updated: Macro Editor tab, UI refinements)
  - `test_sdk.py` (Updated: Enhanced test suite)
  - `BACKLOG.md` (Updated: Agent-Ready feature pipeline)
  - `config.json` (New: Persistent device mappings)
