from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epiphan_config import READ_ONLY_REQUESTS, parse_recovered_response


KVM2USB3_VID = 0x2B77
KVM2USB3_PID = 0x3661
KVM2USB3_MI_00_GUID = "{9f543223-cede-4fa3-b376-a25ce9a30e74}"


class Mi00ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mi00ReadResult:
    name: str
    request: int
    bm_request_type: int
    w_value: int
    w_index: int
    expected_length: int
    payload_hex: str
    parsed: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "request": self.request,
            "request_hex": f"0x{self.request:02x}",
            "bmRequestType": self.bm_request_type,
            "bmRequestType_hex": f"0x{self.bm_request_type:02x}",
            "wValue": self.w_value,
            "wIndex": self.w_index,
            "expectedLength": self.expected_length,
            "payloadHex": self.payload_hex,
            "parsed": self.parsed,
        }


def read_only_request_by_name(name: str):
    for request in READ_ONLY_REQUESTS:
        if request.name == name:
            return request
    raise Mi00ProbeError(f"{name!r} is not an approved read-only MI_00 request")


def _load_pyusb_backend(libusb_dll: str | Path | None):
    try:
        import usb.backend.libusb1
        import usb.core
    except ImportError as exc:
        raise Mi00ProbeError("PyUSB is not installed. Install the optional 'pyusb' dependency.") from exc

    backend = None
    if libusb_dll:
        dll_path = str(Path(libusb_dll).resolve())
        if not Path(dll_path).exists():
            raise Mi00ProbeError(f"libusb DLL not found: {dll_path}")
        backend = usb.backend.libusb1.get_backend(find_library=lambda _: dll_path)
        if backend is None:
            raise Mi00ProbeError(f"PyUSB could not load libusb backend from {dll_path}")
    return usb.core, backend


def find_device(libusb_dll: str | Path | None = None, usb_core=None, backend=None):
    if usb_core is None:
        usb_core, loaded_backend = _load_pyusb_backend(libusb_dll)
        backend = backend or loaded_backend
    kwargs = {"idVendor": KVM2USB3_VID, "idProduct": KVM2USB3_PID}
    if backend is not None:
        kwargs["backend"] = backend
    return usb_core.find(**kwargs)


def describe_device(dev) -> dict[str, Any]:
    if dev is None:
        return {"found": False, "vid": KVM2USB3_VID, "pid": KVM2USB3_PID}

    description = {
        "found": True,
        "vid": KVM2USB3_VID,
        "pid": KVM2USB3_PID,
        "manufacturer": _safe_string(lambda: dev.manufacturer),
        "product": _safe_string(lambda: dev.product),
        "serial_number": _safe_string(lambda: dev.serial_number),
        "interfaces": [],
    }
    try:
        for cfg in dev:
            for intf in cfg:
                description["interfaces"].append(
                    {
                        "configuration": int(getattr(cfg, "bConfigurationValue", 0)),
                        "interface": int(getattr(intf, "bInterfaceNumber", 0)),
                        "alternate": int(getattr(intf, "bAlternateSetting", 0)),
                        "class": int(getattr(intf, "bInterfaceClass", 0)),
                        "subclass": int(getattr(intf, "bInterfaceSubClass", 0)),
                        "protocol": int(getattr(intf, "bInterfaceProtocol", 0)),
                    }
                )
    except Exception as exc:
        description["descriptor_error"] = str(exc)
    return description


def _safe_string(func):
    try:
        return func()
    except Exception:
        return None


def read_config_request(dev, name: str, w_value: int = 0, w_index: int = 0, timeout_ms: int = 1000) -> Mi00ReadResult:
    request = read_only_request_by_name(name)
    if request.direction != "in" or request.risk != "read_only" or request.payload_size is None:
        raise Mi00ProbeError(f"{name!r} is not safe for read-only probing")

    try:
        payload = dev.ctrl_transfer(
            request.bm_request_type,
            request.request,
            int(w_value) & 0xFFFF,
            int(w_index) & 0xFFFF,
            request.payload_size,
            timeout=timeout_ms,
        )
    except Exception as exc:
        raise Mi00ProbeError(
            f"read-only MI_00 transfer {request.name} failed: {exc}"
        ) from exc
    payload_bytes = bytes(payload)
    return Mi00ReadResult(
        name=request.name,
        request=request.request,
        bm_request_type=request.bm_request_type,
        w_value=int(w_value) & 0xFFFF,
        w_index=int(w_index) & 0xFFFF,
        expected_length=request.payload_size,
        payload_hex=payload_bytes.hex(" "),
        parsed=parse_recovered_response(request.name, payload_bytes),
    )


def probe_summary(libusb_dll: str | Path | None = None) -> dict[str, Any]:
    dev = find_device(libusb_dll=libusb_dll)
    summary = describe_device(dev)
    summary["interface_guid"] = KVM2USB3_MI_00_GUID
    return summary


def to_json(data: Any, pretty: bool = False) -> str:
    return json.dumps(data, indent=2 if pretty else None, sort_keys=True)
