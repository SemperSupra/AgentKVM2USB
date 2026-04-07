# AgentKVM2USB Macro Language

The SDK includes a built-in Macro Engine that allows you to define complex, multi-step routines using a simple Domain Specific Language (DSL). This is particularly useful for tasks like navigating BIOS menus, executing predefined install scripts, or performing repetitive actions reliably.

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

sdk.run_macro(macro_script)
```

## Available Commands

The DSL supports the following commands. Commands are case-insensitive, but convention is to use uppercase. Blank lines and lines starting with `#` are ignored.

### `DELAY <ms>`
Pauses the execution for the specified number of milliseconds.
**Example:** `DELAY 500` (Wait half a second)

### `TYPE <string>`
Types the literal text sequence. This is useful for typing out commands or passwords. Note that special keys should be pressed individually.
**Example:** `TYPE admin`

### `PRESS <key>`
Presses and releases a single key. Valid keys include a-z, 0-9, `enter`, `esc`, `backspace`, `tab`, `space`, `f1`-`f12`, `delete`, `up`, `down`, `left`, `right`.
**Example:** `PRESS enter`

### `HOTKEY <mod1> <mod2> ... <key>`
Presses a combination of modifier keys and a final key simultaneously. Modifiers include `ctrl`, `shift`, `alt`, `gui`, `win`, `cmd`.
**Example:** `HOTKEY ctrl alt delete`
**Example:** `HOTKEY ctrl c`

### `CLICK <x_percent> <y_percent> [button]`
Performs a mouse click at the given relative coordinates (0.0 to 1.0) using absolute (touch) positioning. The `button` argument is optional (defaults to 1 for left click). `1` = Left, `2` = Right.
**Example:** `CLICK 0.5 0.5` (Left click center of screen)
**Example:** `CLICK 0.1 0.9 2` (Right click near bottom left)
