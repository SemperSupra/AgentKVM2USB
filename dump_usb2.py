import usb.core
import usb.util
import usb.backend.libusb1
import sys
import os

def dump_descriptors():
    dll_path = os.path.join(os.getcwd(), "EpiphanTools", "KvmApp", "KvmAppWin64-0.99.27-20171125", "libusb-1.0.dll")
    if not os.path.exists(dll_path):
        print(f"libusb DLL not found at {dll_path}")
        sys.exit(1)
        
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    vid = 0x2b77
    pid = 0x3661
    
    dev = usb.core.find(idVendor=vid, idProduct=pid, backend=backend)
    
    if dev is None:
        print("Device not found with libusb backend.")
        sys.exit(1)
        
    print(f"Device: {dev.manufacturer} {dev.product}")
    
    for cfg in dev:
        for intf in cfg:
            print(f"Interface {intf.bInterfaceNumber}, Alt {intf.bAlternateSetting}, Class {intf.bInterfaceClass}")
            # If HID class (3)
            if intf.bInterfaceClass == 3:
                # We need to get the HID descriptor
                # Request type: 10000001b (0x81) Standard, Device-to-Host, Interface
                # Request: GET_DESCRIPTOR (0x06)
                # Value: Descriptor Type (HID Report = 0x22) << 8 | Index (0)
                # Index: Interface Number
                try:
                    data = dev.ctrl_transfer(0x81, 0x06, 0x2200, intf.bInterfaceNumber, 1024)
                    print(f"  HID Report Descriptor (len {len(data)}):")
                    print("  " + " ".join(f"{b:02x}" for b in data))
                except Exception as e:
                    print(f"  Failed to get HID report descriptor: {e}")

if __name__ == "__main__":
    dump_descriptors()
