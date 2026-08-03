"""Profile-driven HID discovery for physical KVM devices.

This module describes HID topology only. It does not encode or write input
reports; report codecs remain in the SDK transport layer.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class UsbIdentity:
    vid: int
    pid: int
    shared: bool = False


@dataclass(frozen=True)
class HidCollectionProfile:
    role: str
    usage_page: int
    usage: int
    interface_number: int | None = None
    report_id: int | None = None
    report_length: int | None = None
    report_id_prefix: bool | None = None
    rollover_limit: int | None = None

    def matches(self, record: "HidInterfaceRecord") -> bool:
        return (
            record.usage_page == self.usage_page
            and record.usage == self.usage
            and (
                self.interface_number is None
                or record.interface_number == self.interface_number
            )
        )


@dataclass(frozen=True)
class DeviceProfile:
    profile_id: str
    identities: tuple[UsbIdentity, ...]
    collections: tuple[HidCollectionProfile, ...]

    def matching_identity(self, record: "HidInterfaceRecord") -> UsbIdentity | None:
        return next((
            identity
            for identity in self.identities
            if identity.vid == record.vendor_id and identity.pid == record.product_id
        ), None)

    def identity_matches(self, record: "HidInterfaceRecord") -> bool:
        return self.matching_identity(record) is not None


@dataclass(frozen=True)
class HidInterfaceRecord:
    path: str | bytes
    vendor_id: int
    product_id: int
    serial_number: str | None
    release_number: int | None
    manufacturer_string: str | None
    product_string: str | None
    usage_page: int | None
    usage: int | None
    interface_number: int | None
    bus_type: int | None
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    @property
    def path_text(self) -> str:
        if isinstance(self.path, bytes):
            return self.path.decode("utf-8", errors="replace")
        return self.path

    @property
    def stable_path(self) -> str:
        """Return the physical path with collection-specific suffix removed."""
        path = re.sub(r"&Col\d+", "", self.path_text, count=1, flags=re.IGNORECASE)
        return re.sub(r"&\d+(?=#\{)", "", path, count=1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path_text,
            "stable_path": self.stable_path,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "serial_number": self.serial_number,
            "release_number": self.release_number,
            "manufacturer_string": self.manufacturer_string,
            "product_string": self.product_string,
            "usage_page": self.usage_page,
            "usage": self.usage,
            "interface_number": self.interface_number,
            "bus_type": self.bus_type,
        }

    @classmethod
    def from_hidapi(cls, item: Mapping[str, Any]) -> "HidInterfaceRecord":
        path = item.get("path", "")
        return cls(
            path=path,
            vendor_id=int(item.get("vendor_id", 0)),
            product_id=int(item.get("product_id", 0)),
            serial_number=item.get("serial_number") or None,
            release_number=item.get("release_number"),
            manufacturer_string=item.get("manufacturer_string") or None,
            product_string=item.get("product_string") or None,
            usage_page=item.get("usage_page"),
            usage=item.get("usage"),
            interface_number=item.get("interface_number"),
            bus_type=item.get("bus_type"),
            raw=dict(item),
        )


@dataclass
class DiscoveryDiagnostic:
    code: str
    message: str
    device_id: str | None = None
    role: str | None = None
    path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "device_id": self.device_id,
            "role": self.role,
            "path": self.path.decode("utf-8", errors="replace")
            if isinstance(self.path, bytes)
            else self.path,
            "details": self.details,
        }


@dataclass
class PhysicalKvmDevice:
    device_id: str
    profile: DeviceProfile
    collections: dict[str, HidInterfaceRecord] = field(default_factory=dict)
    records: list[HidInterfaceRecord] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    devices: list[PhysicalKvmDevice]
    selected: PhysicalKvmDevice | None
    diagnostics: list[DiscoveryDiagnostic]
    connection_ready: bool | None = None

    @property
    def topology_valid(self) -> bool:
        if self.selected is None:
            return False
        fatal_codes = {
            "missing_collection",
            "duplicate_collection",
            "inaccessible_collection",
        }
        return not any(
            diagnostic.code in fatal_codes
            and diagnostic.device_id == self.selected.device_id
            for diagnostic in self.diagnostics
        )

    @property
    def ok(self) -> bool:
        return self.topology_valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok if self.connection_ready is None else self.ok and self.connection_ready,
            "topology_valid": self.topology_valid,
            "connection_ready": self.connection_ready,
            "selected_device_id": self.selected.device_id if self.selected else None,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
            "devices": [
                {
                    "device_id": device.device_id,
                    "profile_id": device.profile.profile_id,
                    "collections": {
                        role: record.as_dict()
                        for role, record in device.collections.items()
                    },
                    "records": [record.as_dict() for record in device.records],
                }
                for device in self.devices
            ],
        }


EPIPHAN_KVM2USB3_PROFILE = DeviceProfile(
    profile_id="epiphan-kvm2usb3",
    identities=(UsbIdentity(0x2B77, 0x3661),),
    collections=(
        HidCollectionProfile("keyboard", 0xFF00, 0x0101, 3, 1, 8, True, 6),
        HidCollectionProfile("relative_mouse", 0xFF00, 0x0102, 3),
        HidCollectionProfile("absolute_pointer", 0xFF00, 0x0103, 3),
        HidCollectionProfile("system", 0xFF00, 0x0104, 3),
    ),
)


def _device_id(record: HidInterfaceRecord) -> str:
    serial = record.serial_number or "no-serial"
    return f"{record.vendor_id:04x}:{record.product_id:04x}:serial:{serial}:path:{record.stable_path}"


def discover_hid_devices(
    entries: Iterable[Mapping[str, Any]],
    profiles: Iterable[DeviceProfile] = (EPIPHAN_KVM2USB3_PROFILE,),
    *,
    serial: str | None = None,
    stable_path: str | None = None,
    development_mode: bool = False,
    inaccessible_paths: Iterable[str] = (),
) -> DiscoveryResult:
    records = [HidInterfaceRecord.from_hidapi(entry) for entry in entries]
    profiles = tuple(profiles)
    inaccessible = set(inaccessible_paths)
    diagnostics: list[DiscoveryDiagnostic] = []
    grouped: dict[str, PhysicalKvmDevice] = {}

    for record in records:
        matched = next((
            (candidate, candidate.matching_identity(record))
            for candidate in profiles
            if candidate.identity_matches(record)
        ), None)
        if matched is None:
            continue
        profile, identity = matched
        if identity.shared and not development_mode:
            diagnostics.append(DiscoveryDiagnostic(
                "shared_identity_disabled",
                f"Shared development identity {record.vendor_id:04x}:{record.product_id:04x} requires development_mode.",
            path=record.path_text,
            ))
            continue
        device_id = _device_id(record)
        device = grouped.setdefault(device_id, PhysicalKvmDevice(device_id, profile))
        device.records.append(record)
        role_profile = next(
            (collection for collection in profile.collections if collection.matches(record)),
            None,
        )
        if role_profile is None:
            usage_page = "none" if record.usage_page is None else f"{record.usage_page:#06x}"
            usage = "none" if record.usage is None else f"{record.usage:#06x}"
            diagnostics.append(DiscoveryDiagnostic(
                "unexpected_collection",
                f"Unexpected HID collection usage page/usage {usage_page}/{usage}.",
                device_id=device_id,
                path=record.path_text,
            ))
            continue
        if record.path in inaccessible or record.path_text in inaccessible:
            diagnostics.append(DiscoveryDiagnostic(
                "inaccessible_collection",
                f"HID collection {role_profile.role} could not be opened.",
                device_id=device_id,
                role=role_profile.role,
                path=record.path_text,
            ))
            continue
        if role_profile.role in device.collections:
            diagnostics.append(DiscoveryDiagnostic(
                "duplicate_collection",
                f"Multiple HID collections match role {role_profile.role}.",
                device_id=device_id,
                role=role_profile.role,
                path=record.path_text,
            ))
            continue
        device.collections[role_profile.role] = record

    devices = list(grouped.values())
    if not devices:
        diagnostics.append(DiscoveryDiagnostic("missing_device", "No approved HID device profile matched."))
    for device in devices:
        for collection in device.profile.collections:
            if collection.role not in device.collections and not any(
                diagnostic.device_id == device.device_id
                and diagnostic.role == collection.role
                and diagnostic.code == "inaccessible_collection"
                for diagnostic in diagnostics
            ):
                diagnostics.append(DiscoveryDiagnostic(
                    "missing_collection",
                    f"Required HID collection {collection.role} is missing.",
                    device_id=device.device_id,
                    role=collection.role,
                ))

    candidates = devices
    if serial is not None:
        candidates = [device for device in candidates if any(
            record.serial_number == serial for record in device.records
        )]
        if not candidates:
            diagnostics.append(DiscoveryDiagnostic("serial_not_found", f"No HID device has serial {serial!r}."))
        elif len(candidates) > 1:
            diagnostics.append(DiscoveryDiagnostic(
                "serial_ambiguous",
                f"Serial {serial!r} matches multiple physical HID devices; select by stable_path.",
                details={"device_ids": [device.device_id for device in candidates]},
            ))
    if stable_path is not None:
        candidates = [device for device in candidates if any(
            record.stable_path == stable_path or record.path_text == stable_path
            for record in device.records
        )]
        if not candidates:
            diagnostics.append(DiscoveryDiagnostic("path_not_found", f"No HID device matches path {stable_path!r}."))
    if serial is None and stable_path is None and len(candidates) > 1:
        diagnostics.append(DiscoveryDiagnostic(
            "selection_required",
            "Multiple physical HID devices match; select by serial or stable_path.",
            details={"device_ids": [device.device_id for device in candidates]},
        ))
        selected = None
    else:
        selected = candidates[0] if len(candidates) == 1 else None
    if serial is not None and len(candidates) != 1:
        selected = None
    return DiscoveryResult(devices, selected, diagnostics)
