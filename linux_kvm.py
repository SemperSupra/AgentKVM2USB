"""Linux hidraw compatibility for the descriptor-verified KVM2USB profile.

No USB driver detachment or device configuration writes are performed.
"""
import os
from pathlib import Path

# Independently observed HID descriptor: four vendor collections, interface 3.
KVM_DESCRIPTOR = bytes.fromhex(
    '0600ff0a0101a1018501750895080901150026ff009102c0'
    '0a0201a10185027508950409029102c0'
    '0a0301a1018503750895050903b1028506750895010906b102'
    '8507750895010907b102c00a0401a10185057508950609049102c0'
)


def enumerate_kvm_hidraw(root=Path('/sys/class/hidraw')):
    entries = []
    for node in sorted(root.glob('hidraw*')):
        device = node / 'device'
        try:
            info = dict(line.split('=', 1) for line in
                        (device / 'uevent').read_text().splitlines() if '=' in line)
            if info.get('HID_ID', '').upper() != '0003:00002B77:00003661':
                continue
            if (device / 'report_descriptor').read_bytes() != KVM_DESCRIPTOR:
                continue
            for usage in range(0x101, 0x105):
                entries.append(dict(path=os.fsencode('/dev/' + node.name),
                    vendor_id=0x2b77, product_id=0x3661,
                    serial_number=info.get('HID_UNIQ'), usage_page=0xff00,
                    usage=usage, interface_number=3))
        except OSError:
            # Let callers report missing topology; never guess a descriptor.
            continue
    return entries


class HidrawDevice:
    def open_path(self, path):
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)

    def write(self, data):
        data = bytes(data)
        count = os.write(self.fd, data)
        if count != len(data):
            raise OSError(f'Short HID write: {count}/{len(data)} bytes')
        return count

    def get_feature_report(self, report_id, length):
        import fcntl
        data = bytearray(length)
        data[0] = report_id
        count = fcntl.ioctl(self.fd, (3 << 30) | (length << 16) |
                            (ord('H') << 8) | 7, data, True)
        return bytes(data[:count])

    def close(self):
        os.close(self.fd)
