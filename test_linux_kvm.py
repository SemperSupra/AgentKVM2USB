from unittest.mock import Mock
import pytest
from linux_kvm import KVM_DESCRIPTOR, enumerate_kvm_hidraw, HidrawDevice
from hid_discovery import discover_hid_devices
from epiphan_sdk import EpiphanKVM_SDK


def test_descriptor_verified_collections(tmp_path):
    d = tmp_path / 'hidraw9' / 'device'
    d.mkdir(parents=True)
    (d / 'uevent').write_text('HID_ID=0003:00002B77:00003661\n')
    (d / 'report_descriptor').write_bytes(KVM_DESCRIPTOR)
    result = discover_hid_devices(enumerate_kvm_hidraw(tmp_path))
    assert result.topology_valid
    assert set(result.selected.collections) == {'keyboard', 'relative_mouse', 'absolute_pointer', 'system'}
    (d / 'report_descriptor').write_bytes(KVM_DESCRIPTOR + b'\x00')
    assert enumerate_kvm_hidraw(tmp_path) == []


def test_keyboard_framing_and_release():
    s = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
    s.kb_dev = Mock()
    s._raw_kb(2, [])
    s._raw_kb(0, [])
    assert [c.args[0] for c in s.kb_dev.write.call_args_list] == [
        [1, 2, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0, 0]]


def test_short_write_is_error(monkeypatch):
    d = HidrawDevice()
    d.fd = 7
    monkeypatch.setattr('linux_kvm.os.write', lambda *_: 2)
    with pytest.raises(OSError, match='Short HID write'):
        d.write([1] * 9)
