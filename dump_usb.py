import usb.core
import usb.util
import sys

def dump_device():
    # Epiphan KVM2USB 3.0 VID and PID
    vid = 0x2b77
    pid = 0x3661
    
    print(f"Searching for Epiphan Device {hex(vid)}:{hex(pid)}...")
    dev = usb.core.find(idVendor=vid, idProduct=pid)
    
    if dev is None:
        print("Device not found. Make sure it is plugged in.")
        sys.exit(1)
        
    print(f"Device Found: {dev.manufacturer} {dev.product}")
    
    for cfg in dev:
        print(f"Configuration Value: {cfg.bConfigurationValue}")
        for intf in cfg:
            print(f"  Interface: {intf.bInterfaceNumber}, Alt: {intf.bAlternateSetting}")
            print(f"    Class: {intf.bInterfaceClass}, Subclass: {intf.bInterfaceSubClass}, Protocol: {intf.bInterfaceProtocol}")
            for ep in intf:
                print(f"    Endpoint Address: {hex(ep.bEndpointAddress)}")
                print(f"      Attributes: {hex(ep.bmAttributes)}")
                print(f"      Max Packet Size: {ep.wMaxPacketSize}")

if __name__ == "__main__":
    dump_device()
