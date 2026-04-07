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

sdk.run_macro(macro_script)
```

## Available Commands

The DSL supports the following commands. Commands are case-insensitive; convention is to use uppercase. Blank lines and lines beginning with `#` are ignored.

### `DELAY <ms>`
Suspends execution for the specified integer milliseconds.
**Example:** `DELAY 500`

### `TYPE <string>`
Injects the literal string characters sequentially.
**Example:** `TYPE admin`

### `PRESS <key>`
Injects a down/up sequence for a specified key. Valid keys: a-z, 0-9, `enter`, `esc`, `backspace`, `tab`, `space`, `f1`-`f12`, `delete`, `up`, `down`, `left`, `right`.
**Example:** `PRESS enter`

### `HOTKEY <mod1> <mod2> ... <key>`
Injects a combination of modifier keys and a final key simultaneously. Valid modifiers: `ctrl`, `shift`, `alt`, `gui`, `win`, `cmd`.
**Example:** `HOTKEY ctrl alt delete`

### `CLICK <x_percent> <y_percent> [button]`
Injects a mouse click event using absolute (touch) positioning, scaled by normalized relative coordinates (0.0 to 1.0). The `button` argument is optional (default: 1). `1` = Left, `2` = Right.
**Example:** `CLICK 0.5 0.5`
