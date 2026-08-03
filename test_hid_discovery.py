import json

import epiphan_sdk
from epiphan_sdk import EpiphanKVM_SDK
from hid_discovery import DeviceProfile, HidCollectionProfile, UsbIdentity, discover_hid_devices


ROLES = (
    ("keyboard", 0x0101),
    ("relative_mouse", 0x0102),
    ("absolute_pointer", 0x0103),
    ("system", 0x0104),
)


def profile(shared=False):
    return DeviceProfile(
        profile_id="fixture-kvm",
        identities=(UsbIdentity(0x1234, 0x5678, shared=shared),),
        collections=tuple(
            HidCollectionProfile(role, 0xFF00, usage, 3)
            for role, usage in ROLES
        ),
    )


def entry(device, role, *, serial=None, usage_page=0xFF00, usage=None):
    if usage is None:
        usage = dict(ROLES)[role]
    return {
        "path": f"hid://{device}&Col{dict(ROLES)[role] - 0x100:02d}",
        "vendor_id": 0x1234,
        "product_id": 0x5678,
        "serial_number": serial or device,
        "release_number": 1,
        "manufacturer_string": "Fixture",
        "product_string": "Fixture KVM",
        "usage_page": usage_page,
        "usage": usage,
        "interface_number": 3,
        "bus_type": 1,
    }


def complete(device="one", serial=None):
    return [entry(device, role, serial=serial) for role, _ in ROLES]


def codes(result):
    return {diagnostic.code for diagnostic in result.diagnostics}


def test_zero_devices_is_structured():
    result = discover_hid_devices([], profiles=(profile(),))

    assert result.selected is None
    assert "missing_device" in codes(result)
    assert result.as_dict()["ok"] is False


def test_one_complete_device_groups_all_collections():
    result = discover_hid_devices(complete(), profiles=(profile(),))

    assert result.ok
    assert result.selected is not None
    assert set(result.selected.collections) == {role for role, _ in ROLES}
    assert len(result.devices) == 1
    assert len(result.devices[0].records) == 4


def test_multiple_devices_require_explicit_selection_and_do_not_mix():
    entries = complete("one", "serial-one") + complete("two", "serial-two")
    result = discover_hid_devices(entries, profiles=(profile(),))

    assert result.selected is None
    assert "selection_required" in codes(result)

    selected = discover_hid_devices(
        entries, profiles=(profile(),), serial="serial-two"
    )
    assert selected.ok
    assert selected.selected is not None
    assert selected.selected.device_id.endswith(":serial:serial-two:path:hid://two")
    assert all(
        record.serial_number == "serial-two"
        for record in selected.selected.collections.values()
    )


def test_partial_device_reports_missing_collection():
    result = discover_hid_devices(
        complete()[:-1], profiles=(profile(),)
    )

    assert result.selected is not None
    assert not result.ok
    assert "missing_collection" in codes(result)
    assert any(d.role == "system" for d in result.diagnostics)


def test_duplicate_collection_is_not_silently_overwritten():
    entries = complete() + [entry("one", "keyboard", serial="one")]
    result = discover_hid_devices(entries, profiles=(profile(),))

    assert not result.ok
    assert "duplicate_collection" in codes(result)
    assert result.selected is not None
    assert len(result.selected.collections) == 4


def test_duplicate_serials_keep_physical_devices_separate_and_require_path():
    entries = []
    for role, _ in ROLES:
        entries.append(entry("one", role, serial="same"))
        entries.append(entry("two", role, serial="same"))

    result = discover_hid_devices(entries, profiles=(profile(),), serial="same")

    assert result.selected is None
    assert len(result.devices) == 2
    assert "serial_ambiguous" in codes(result)

    selected = discover_hid_devices(
        entries, profiles=(profile(),), serial="same", stable_path="hid://two"
    )
    assert selected.ok
    assert selected.selected is not None
    assert selected.selected.device_id.endswith(":path:hid://two")


def test_inaccessible_collection_is_reported():
    entries = complete()
    path = entries[0]["path"]
    result = discover_hid_devices(
        entries, profiles=(profile(),), inaccessible_paths=(path,)
    )

    assert not result.ok
    assert any(
        diagnostic.code == "inaccessible_collection"
        and diagnostic.role == "keyboard"
        for diagnostic in result.diagnostics
    )


def test_shared_identity_requires_explicit_development_mode():
    shared = profile(shared=True)
    entries = complete()

    rejected = discover_hid_devices(entries, profiles=(shared,))
    assert rejected.selected is None
    assert "shared_identity_disabled" in codes(rejected)

    accepted = discover_hid_devices(
        entries, profiles=(shared,), development_mode=True
    )
    assert accepted.ok


def test_shared_identity_field_is_authoritative():
    mismatched = DeviceProfile(
        profile_id="shared-fixture",
        identities=(UsbIdentity(0x1234, 0x5678, shared=True),),
        collections=profile().collections,
    )
    result = discover_hid_devices(complete(), profiles=(mismatched,))

    assert result.selected is None
    assert "shared_identity_disabled" in codes(result)


def _epiphan_entries(device="one", serial=None):
    return [
        {
            **record,
            "vendor_id": 0x2B77,
            "product_id": 0x3661,
            "path": record["path"].encode("utf-8"),
        }
        for record in complete(device, serial)
    ]


class _FakeHidDevice:
    opened = []
    fail_path = None

    def open_path(self, path):
        if path == self.fail_path:
            raise OSError("fixture open failure")
        self.opened.append(self)

    def close(self):
        pass


def _sdk_for_discovery(monkeypatch, entries, serial=None, fail_path=None):
    _FakeHidDevice.opened = []
    _FakeHidDevice.fail_path = fail_path
    monkeypatch.setattr(epiphan_sdk.hid, "enumerate", lambda: entries)
    monkeypatch.setattr(epiphan_sdk.hid, "device", _FakeHidDevice)
    sdk = EpiphanKVM_SDK.__new__(EpiphanKVM_SDK)
    sdk.hid_serial = serial
    sdk.hid_path = None
    sdk.development_mode = False
    sdk.kb_dev = sdk.mouse_dev = sdk.touch_dev = sdk.sys_dev = None
    sdk.hid_discovery = None
    sdk.hid_diagnostics = []
    sdk.hid_connection_ready = False
    sdk._connect_hid()
    return sdk


def test_sdk_refuses_partial_and_duplicate_selected_topologies(monkeypatch):
    partial = _sdk_for_discovery(monkeypatch, _epiphan_entries()[:-1], serial="one")
    assert partial.hid_connection_ready is False
    assert all(handle is None for handle in (
        partial.kb_dev, partial.mouse_dev, partial.touch_dev, partial.sys_dev
    ))

    duplicate_entries = _epiphan_entries()
    duplicate_entries.append(dict(duplicate_entries[0], path=b"hid://one&Col05"))
    duplicate = _sdk_for_discovery(monkeypatch, duplicate_entries, serial="one")
    assert duplicate.hid_connection_ready is False
    assert all(handle is None for handle in (
        duplicate.kb_dev, duplicate.mouse_dev, duplicate.touch_dev, duplicate.sys_dev
    ))


def test_sdk_selects_healthy_device_when_other_device_is_invalid(monkeypatch):
    entries = _epiphan_entries("bad", "same")[:-1] + _epiphan_entries("good", "good")
    sdk = _sdk_for_discovery(monkeypatch, entries, serial="good")

    assert sdk.hid_connection_ready is True
    assert sdk.hid_discovery.topology_valid is True
    assert sdk.hid_discovery.selected.device_id.endswith(":serial:good:path:hid://good")


def test_sdk_open_failure_is_json_safe_and_not_connection_ready(monkeypatch):
    entries = _epiphan_entries()
    sdk = _sdk_for_discovery(
        monkeypatch, entries, serial="one", fail_path=entries[0]["path"]
    )

    payload = {
        "hidDiscovery": sdk.hid_discovery.as_dict(),
        "hidDiagnostics": [diagnostic.as_dict() for diagnostic in sdk.hid_diagnostics],
    }
    serialized = json.dumps(payload)

    assert serialized
    assert payload["hidDiscovery"]["topology_valid"] is True
    assert payload["hidDiscovery"]["connection_ready"] is False
    assert payload["hidDiscovery"]["ok"] is False
    assert any(
        diagnostic["code"] == "inaccessible_collection"
        and isinstance(diagnostic["path"], str)
        for diagnostic in payload["hidDiagnostics"]
    )
