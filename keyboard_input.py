"""Keyboard report encoding and semantic state for the Phase B input path."""

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class KeyboardReportProfile:
    report_id: int = 1
    report_length: int = 8
    report_id_prefix: bool = True
    rollover_limit: int = 6

    @classmethod
    def from_collection(cls, collection) -> "KeyboardReportProfile":
        required = ("report_id", "report_length", "report_id_prefix", "rollover_limit")
        missing = [name for name in required if getattr(collection, name, None) is None]
        if missing:
            raise KeyboardProfileError(
                "missing_metadata",
                f"Keyboard collection is missing required metadata: {', '.join(missing)}.",
                missing=missing,
            )
        if not 0 <= collection.report_id <= 0xFF:
            raise KeyboardProfileError("invalid_metadata", "Keyboard report_id must be 0..255.")
        if collection.report_length < 2:
            raise KeyboardProfileError("invalid_metadata", "Keyboard report_length must be at least 2.")
        if collection.rollover_limit < 1 or collection.rollover_limit > collection.report_length - 2:
            raise KeyboardProfileError("invalid_metadata", "Keyboard rollover_limit exceeds the report payload.")
        return cls(
            report_id=collection.report_id,
            report_length=collection.report_length,
            report_id_prefix=collection.report_id_prefix,
            rollover_limit=collection.rollover_limit,
        )


class KeyboardProfileError(ValueError):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class KeyboardActionResult:
    ok: bool
    code: str = "ok"
    message: str = ""
    reports: tuple[tuple[int, ...], ...] = ()
    details: dict = field(default_factory=dict)

    def __bool__(self):
        return self.ok


class KeyboardCodec:
    """Encode HID keyboard payloads without performing device I/O."""

    MODIFIERS = {
        "lctrl": 0x01, "lshift": 0x02, "lalt": 0x04, "lgui": 0x08,
        "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40, "rgui": 0x80,
        "ctrl": 0x01, "shift": 0x02, "alt": 0x04,
        "gui": 0x08, "win": 0x08, "cmd": 0x08, "meta": 0x08,
    }

    MODIFIER_USAGES = {0xE0 + index: 1 << index for index in range(8)}

    NAMED_KEYS = {
        "enter": 0x28, "return": 0x28, "esc": 0x29, "escape": 0x29,
        "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
        "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31,
        ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38,
        "capslock": 0x39, "caps_lock": 0x39,
        **{f"f{number}": 0x39 + number for number in range(1, 13)},
        "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48,
        "insert": 0x49, "home": 0x4A, "pageup": 0x4B, "pgup": 0x4B,
        "delete": 0x4C, "end": 0x4D, "pagedown": 0x4E, "pgdn": 0x4E,
        "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
        "numlock": 0x53, "application": 0x65, "menu": 0x65,
    }

    _SHIFTED = {
        "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
        "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
        "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\",
        ":": ";", '"': "'", "~": "`", "<": ",", ">": ".", "?": "/",
    }

    def __init__(self, profile: KeyboardReportProfile | None = None):
        self.profile = profile or KeyboardReportProfile()

    def normalize_modifier(self, key: str) -> str | None:
        normalized = str(key).lower()
        aliases = {
            "ctrl": "lctrl", "control": "lctrl", "leftctrl": "lctrl", "lctrl": "lctrl",
            "shift": "lshift", "leftshift": "lshift", "lshift": "lshift",
            "alt": "lalt", "leftalt": "lalt", "lalt": "lalt",
            "altgr": "ralt", "rightalt": "ralt", "ralt": "ralt",
            "gui": "lgui", "win": "lgui", "cmd": "lgui", "meta": "lgui",
            "leftgui": "lgui", "lgui": "lgui", "rightctrl": "rctrl", "rctrl": "rctrl",
            "rightshift": "rshift", "rshift": "rshift", "rightgui": "rgui", "rgui": "rgui",
        }
        return aliases.get(normalized)

    def modifier_for_usage(self, usage: int) -> str | None:
        bit = self.MODIFIER_USAGES.get(usage)
        if bit is None:
            return None
        return next(name for name, value in self.MODIFIERS.items() if value == bit and len(name) > 2)

    def usage_for_key(self, key: str) -> int | None:
        normalized = str(key).lower()
        if len(normalized) == 1 and "a" <= normalized <= "z":
            return 0x04 + ord(normalized) - ord("a")
        if len(normalized) == 1 and normalized.isdigit():
            return 0x1E + (ord(normalized) - ord("1")) if normalized != "0" else 0x27
        return self.NAMED_KEYS.get(normalized)

    def character(self, value: str) -> tuple[int, int] | None:
        if len(value) != 1:
            return None
        if "a" <= value <= "z":
            return 0, self.usage_for_key(value)
        if "A" <= value <= "Z":
            return self.MODIFIERS["shift"], self.usage_for_key(value.lower())
        if value in self._SHIFTED:
            return self.MODIFIERS["shift"], self.usage_for_key(self._SHIFTED[value])
        usage = self.usage_for_key(value)
        if usage is not None:
            return 0, usage
        if value == "\n" or value == "\r":
            return 0, self.NAMED_KEYS["enter"]
        if value == "\t":
            return 0, self.NAMED_KEYS["tab"]
        if value == "\b":
            return 0, self.NAMED_KEYS["backspace"]
        if value == " ":
            return 0, self.NAMED_KEYS["space"]
        return None

    def encode(self, modifiers: int, usages: Iterable[int]) -> tuple[int, ...]:
        usages = tuple(usages)
        if modifiers < 0 or modifiers > 0xFF:
            raise ValueError("modifier byte must be between 0 and 255")
        if len(usages) > self.profile.rollover_limit:
            raise ValueError(f"keyboard rollover limit is {self.profile.rollover_limit}")
        if any(usage <= 0 or usage > 0xFF for usage in usages):
            raise ValueError("keyboard usages must be between 1 and 255")
        payload = (modifiers, 0, *usages)
        if len(payload) > self.profile.report_length:
            raise ValueError("keyboard payload exceeds configured report length")
        payload += (0,) * (self.profile.report_length - len(payload))
        if self.profile.report_id_prefix:
            return (self.profile.report_id, *payload)
        return tuple(payload)


class KeyboardState:
    """Track semantic keyboard state and produce encoded report sequences."""

    def __init__(self, codec: KeyboardCodec | None = None):
        self.codec = codec or KeyboardCodec()
        self.active_modifiers: set[str] = set()
        self.pressed_usages: list[int] = []

    @property
    def modifier_byte(self) -> int:
        return sum(self.codec.MODIFIERS[modifier] for modifier in self.active_modifiers)

    @property
    def pressed_keys(self) -> tuple[int, ...]:
        return tuple(self.pressed_usages)

    def _error(self, code: str, message: str, **details) -> KeyboardActionResult:
        return KeyboardActionResult(False, code, message, details=details)

    def key_down(self, key: str) -> tuple[KeyboardActionResult, tuple[int, ...] | None]:
        normalized = str(key).lower()
        modifier = self.codec.normalize_modifier(normalized)
        if modifier is not None:
            normalized = modifier
            if normalized in self.active_modifiers:
                return self._error("already_pressed", f"Modifier {key!r} is already pressed."), None
            self.active_modifiers.add(normalized)
        else:
            usage = self.codec.usage_for_key(normalized)
            if usage is None:
                return self._error("unsupported_key", f"Unsupported key {key!r}."), None
            return self.key_down_usage(usage, key)
        try:
            report = self.codec.encode(self.modifier_byte, self.pressed_usages)
        except ValueError as exc:
            if normalized in self.active_modifiers:
                self.active_modifiers.remove(normalized)
            usage = self.codec.usage_for_key(normalized)
            if usage in self.pressed_usages:
                self.pressed_usages.remove(usage)
            return self._error("invalid_state", str(exc)), None
        return KeyboardActionResult(True, reports=(report,)), report

    def key_down_usage(self, usage: int, label: str = "usage"):
        modifier = self.codec.modifier_for_usage(usage)
        if modifier is not None:
            return self.key_down(modifier)
        if not 1 <= usage <= 0xFF:
            return self._error("invalid_usage", f"Keyboard usage {usage!r} is invalid."), None
        if usage in self.pressed_usages:
            return self._error("already_pressed", f"Key {label!r} is already pressed."), None
        if len(self.pressed_usages) >= self.codec.profile.rollover_limit:
            return self._error(
                "rollover_limit",
                f"Keyboard rollover limit is {self.codec.profile.rollover_limit}."
            ), None
        self.pressed_usages.append(usage)
        try:
            report = self.codec.encode(self.modifier_byte, self.pressed_usages)
        except ValueError as exc:
            self.pressed_usages.remove(usage)
            return self._error("invalid_state", str(exc)), None
        return KeyboardActionResult(True, reports=(report,)), report

    def key_up(self, key: str) -> tuple[KeyboardActionResult, tuple[int, ...] | None]:
        normalized = str(key).lower()
        modifier = self.codec.normalize_modifier(normalized)
        if modifier is not None:
            normalized = modifier
            if normalized not in self.active_modifiers:
                return self._error("not_pressed", f"Modifier {key!r} is not pressed."), None
            self.active_modifiers.remove(normalized)
        else:
            usage = self.codec.usage_for_key(normalized)
            if usage is None:
                return self._error("unsupported_key", f"Unsupported key {key!r}."), None
            return self.key_up_usage(usage, key)
        report = self.codec.encode(self.modifier_byte, self.pressed_usages)
        return KeyboardActionResult(True, reports=(report,)), report

    def key_up_usage(self, usage: int, label: str = "usage"):
        modifier = self.codec.modifier_for_usage(usage)
        if modifier is not None:
            return self.key_up(modifier)
        if not 1 <= usage <= 0xFF:
            return self._error("invalid_usage", f"Keyboard usage {usage!r} is invalid."), None
        if usage not in self.pressed_usages:
            return self._error("not_pressed", f"Key {label!r} is not pressed."), None
        self.pressed_usages.remove(usage)
        report = self.codec.encode(self.modifier_byte, self.pressed_usages)
        return KeyboardActionResult(True, reports=(report,)), report

    def reset(self) -> None:
        self.active_modifiers.clear()
        self.pressed_usages.clear()
