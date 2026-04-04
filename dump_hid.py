import sys
import platform

# Ensure we use hidapi
try:
    import hid
except ImportError:
    print("hid module not found. Please install it.")
    sys.exit(1)

def enumerate_hid():
    vid = 0x2b77
    pid = 0x3661
    
    print(f"Enumerating HID devices for {hex(vid)}:{hex(pid)}...")
    devices = hid.enumerate(vid, pid)
    
    if not devices:
        print("No KVM2USB 3.0 HID devices found. The WinUSB driver might be preventing hidapi from seeing it, or we need to use libusb backend.")
        sys.exit(0)
        
    for dev in devices:
        print("Found HID Device:")
        print(f"  Path: {dev['path']}")
        print(f"  Manufacturer: {dev['manufacturer_string']}")
        print(f"  Product: {dev['product_string']}")
        print(f"  Interface: {dev['interface_number']}")
        print(f"  Usage Page: {hex(dev['usage_page'])}")
        print(f"  Usage: {hex(dev['usage'])}")
        print("---")

if __name__ == "__main__":
    enumerate_hid()
