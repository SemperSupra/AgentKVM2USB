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
        shared_identity=shared,
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
    assert selected.selected.device_id == "1234:5678:serial:serial-two"
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
