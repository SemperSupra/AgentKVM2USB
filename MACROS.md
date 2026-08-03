# AgentKVM2USB Macro Language

The SDK includes a Macro Engine that processes a Domain Specific Language (DSL) for executing sequential KVM operations.

## How to Run a Macro

You can run a macro using the `run_macro()` method on the SDK instance:

```python
from epiphan_sdk import EpiphanKVM_SDK

sdk = EpiphanKVM_SDK()

macro_script = """
# Navigate to the boot menu (example)
DELAY 2000
PRESS f12
DELAY 500
PRESS down
PRESS enter
"""

result = sdk.run_macro(macro_script)
```

`run_macro()` returns structured execution details:

```python
{
    "success": True,
    "executed": [{"line": 3, "command": "PRESS", "args": {"key": "f12"}}],
    "errors": []
}
```

Use `validate_macro()` to parse a macro without sending HID events:

```python
result = sdk.validate_macro(macro_script)
```

## Named Macro Library

Named macros are stored in the user profile outside the repository by default.
The profile root can be overridden with `AGENTKVM2USB_PROFILE_ROOT`.

```python
sdk.save_macro("Boot Menu", "PRESS f12")
sdk.run_named_macro("Boot Menu")
sdk.run_named_macro("Boot Menu", dry_run=True)
sdk.delete_macro("Boot Menu")
```

In the GUI, open Options -> Settings -> Macro Editor to load, save, delete,
validate, or run named macros.

The same macro operations are available through the local JSON API started by
`scripts/run_headless_api.py`.

## Available Commands

The DSL supports the following commands. Commands are case-insensitive; convention is to use uppercase. Blank lines and lines beginning with `#` are ignored.

### `DELAY <ms>`
Suspends execution for the specified integer milliseconds.
**Example:** `DELAY 500`

### `TYPE <string>`
Injects the literal string characters sequentially.
**Example:** `TYPE admin`

### `PRESS <key>`
Injects a down/up sequence for a specified key. Valid keys: a-z, 0-9,
`enter`, `esc`, `backspace`, `tab`, `space`, `f1`-`f12`,
`printscreen`, `scrolllock`, `pause`, `insert`, `home`, `pageup`,
`delete`, `end`, `pagedown`, `up`, `down`, `left`, `right`, `numlock`,
and `capslock`.
**Example:** `PRESS enter`

Live macro results include `write_result` entries for HID commands. A successful
keyboard report normally shows `{"press": 9, "release": 9}` for the recovered
KVM2USB 3.0 report-ID layout.

### `HOTKEY <mod1> <mod2> ... <key>`
Injects a combination of modifier keys and a final key simultaneously. Valid modifiers: `ctrl`, `shift`, `alt`, `gui`, `win`, `cmd`.
**Example:** `HOTKEY ctrl alt delete`

### `CLICK <x_percent> <y_percent> [button]`
Injects a mouse click event using absolute (touch) positioning, scaled by normalized relative coordinates (0.0 to 1.0). The `button` argument is optional (default: 1). `1` = Left, `2` = Right.
**Example:** `CLICK 0.5 0.5`

### `MOVE <dx> <dy> [wheel]`
Injects relative mouse movement using the recovered mouse HID collection. Values are signed deltas clamped to -127..127.
**Example:** `MOVE 20 -5`

### `SCROLL <wheel>`
Injects relative mouse wheel movement. Positive values scroll up; negative values scroll down.
**Example:** `SCROLL -1`
