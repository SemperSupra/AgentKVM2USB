from __future__ import annotations

from dataclasses import dataclass

from epiphan_sdk import EpiphanKVM_SDK


@dataclass(frozen=True)
class VendorControlRequest:
    name: str
    request: int
    direction: str
    payload_size: int | None
    risk: str
    parser: str | None = None
    builder: str | None = None

    @property
    def bm_request_type(self) -> int:
        return 0xC0 if self.direction == "in" else 0x40

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "request": self.request,
            "request_hex": f"0x{self.request:02x}",
            "direction": self.direction,
            "bmRequestType": self.bm_request_type,
            "bmRequestType_hex": f"0x{self.bm_request_type:02x}",
            "payload_size": self.payload_size,
            "risk": self.risk,
            "parser": self.parser,
            "builder": self.builder,
        }


READ_ONLY_REQUESTS = (
    VendorControlRequest(
        name="input_status",
        request=0xB2,
        direction="in",
        payload_size=29,
        risk="read_only",
        parser="EpiphanKVM_SDK.parse_config_input_status",
    ),
    VendorControlRequest(
        name="user_mode",
        request=0xB3,
        direction="in",
        payload_size=5,
        risk="read_only",
        parser="EpiphanKVM_SDK.parse_config_user_mode",
    ),
    VendorControlRequest(
        name="device_flags",
        request=0xE2,
        direction="in",
        payload_size=1,
        risk="read_only",
        parser="EpiphanKVM_SDK.parse_config_flags",
    ),
)

WRITE_REQUESTS = (
    VendorControlRequest(
        name="write_user_mode",
        request=0xB3,
        direction="out",
        payload_size=5,
        risk="device_write",
        builder="EpiphanKVM_SDK.build_config_user_mode",
    ),
    VendorControlRequest(
        name="write_device_flags",
        request=0xE3,
        direction="out",
        payload_size=1,
        risk="device_write",
        builder="EpiphanKVM_SDK.build_config_flags",
    ),
    VendorControlRequest(
        name="update_chunk_write_verify",
        request=0xA0,
        direction="out",
        payload_size=None,
        risk="firmware_write",
    ),
    VendorControlRequest(
        name="update_flash_status",
        request=0xC4,
        direction="in",
        payload_size=1,
        risk="update_flow",
    ),
    VendorControlRequest(
        name="update_initiate",
        request=0xC5,
        direction="out",
        payload_size=0,
        risk="firmware_write",
    ),
    VendorControlRequest(
        name="update_repair_action",
        request=0xD4,
        direction="out",
        payload_size=0,
        risk="firmware_write",
    ),
)


def recovered_request_map(include_writes=False) -> list[dict]:
    requests = list(READ_ONLY_REQUESTS)
    if include_writes:
        requests.extend(WRITE_REQUESTS)
    return [request.as_dict() for request in requests]


def parse_recovered_response(name: str, payload) -> dict | None:
    if name == "input_status":
        return EpiphanKVM_SDK.parse_config_input_status(payload)
    if name == "user_mode":
        return EpiphanKVM_SDK.parse_config_user_mode(payload)
    if name == "device_flags":
        return EpiphanKVM_SDK.parse_config_flags(payload)
    raise ValueError(f"no recovered parser for {name!r}")
