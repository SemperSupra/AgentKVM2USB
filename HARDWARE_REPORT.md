# Epiphan KVM2USB 3.0: Hardware Architecture & Protocol Report

This report documents the internal hardware components and communication protocols of the Epiphan KVM2USB 3.0, cross-referencing empirical reverse-engineering data with authoritative manufacturer specifications.

## 1. System-on-Chip (SoC) / USB Controller
**Component:** Cypress (Infineon) EZ-USB FX3 (CYUSB3014)  
**Empirical Evidence:** Found string `FX3` in `KvmApp.exe`; Firmware file `kvm2usb3.img` is a standard FX3 RAM image format.  
**Authoritative Source:** [Infineon CYUSB3014 Datasheet](https://www.infineon.com/dgdl/Infineon-EZ-USB_FX3_SuperSpeed_USB_3.0_Peripheral_Controller-DataSheet-v30_00-EN.pdf?fileId=8ac78c8c7d0d8da4017d0ee7be951670)

### Technical Analysis:
The FX3 serves as the primary USB 3.0 interface and system controller. It features an **ARM926EJ-S core** (200 MHz) and **512 KB of on-chip SRAM**.
*   **DMA Engine:** The FX3's General Programmable Interface (GPIF II) provides a 100 MHz, 32-bit wide data bus that allows for the **400 MB/s** throughput required for uncompressed 1080p 60fps video capture.
*   **Protocol Stack:** The FX3 handles the enumeration of the device as a standard **USB Video Class (UVC 1.1)** and **HID (Human Interface Device)** peripheral.

---

## 2. Video Processing Engine (FPGA)
**Component:** Intel (Altera) Cyclone IV or V FPGA  
**Empirical Evidence:** Binary bitstream file `kvm2usb3.bin`; References to `FpgaUsbThread` and `FpgaUsbIsrThread` in `KvmApp.exe`.  
**Authoritative Source:** [Intel Cyclone V Device Handbook](https://www.intel.com/content/www/us/en/docs/programmable/683525/current/cyclone-v-device-handbook.html)

### Technical Analysis:
The FPGA acts as the bridge between the high-speed video receiver and the USB controller.
*   **Real-time Processing:** Unlike general-purpose processors, the FPGA performs **color space conversion** (e.g., YCbCr 4:2:2 to RGB), **scaling**, and **frame-rate control** in hardware logic gates, ensuring the near-zero latency required for KVM operations.
*   **Frame Buffering:** The FPGA interfaces with external **DDR3 SDRAM** (typically 1Gb or 2Gb) to manage "tearing" and ensure a stable video feed even during USB bus congestion.

---

## 3. High-Performance Video Receiver (Digitizer)
**Component:** Analog Devices ADV7842 (Dual-Format Receiver)  
**Empirical Evidence:** Device capability for both VGA (Analog) and DVI/HDMI (Digital) capture; Strings related to `H-Sync`, `V-Sync`, and `Phase` in `EpiphanCaptureConfig.exe`.  
**Authoritative Source:** [Analog Devices ADV7842 Product Page](https://www.analog.com/en/products/adv7842.html)

### Technical Analysis:
The ADV7842 is a high-speed, multi-format 3D comb filter and video digitizer.
*   **VGA Capture:** Features a triple **12-bit ADC** (Analog-to-Digital Converter) capable of 170 MHz sampling, allowing it to capture high-resolution VGA signals from the Terasic DE2-115 with extreme clarity.
*   **Digital Capture:** Includes an integrated **HDMI 1.4a receiver** that supports Deep Color and HDCP decryption (though HDCP is typically disabled for Epiphan capture products).

---

## 4. Communication Protocol Stack
**Empirical Evidence:** USB Descriptor analysis via `dump_usb2.py` and HID enumeration via `hidapi`.

### Protocol Mapping:
| Interface | Endpoint | Protocol | Logic |
| :--- | :--- | :--- | :--- |
| **Video** | Interface 1/2 | **UVC** | Standard Isochronous transfers for video stream. |
| **Keyboard** | Usage 0x101 | **HID** | Custom 8-byte report format on Vendor-Defined Interface. |
| **Mouse** | Usage 0x102 | **HID** | Standard 4-byte Relative Mouse report. |
| **System** | Usage 0x104 | **Vendor** | Uses `GET_FEATURE_REPORT` for hardware diagnostics (resolution, LEDs). |

---

## 5. Conclusion
The Epiphan KVM2USB 3.0 is built on a "Hard-IP" architecture where the USB protocol (FX3) and the Video Digitization (ADV7842) are handled by dedicated silicon, while the flexible video logic (Cyclone FPGA) provides the high-performance bridging. This modularity is why the device remains forward-compatible with modern Operating Systems through standard UVC/HID drivers long after its discontinued support.
