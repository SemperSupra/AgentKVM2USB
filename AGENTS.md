# Instructions for AI Agents

The following guidelines govern AI agent interactions with the AgentKVM2USB project.

## Core Purpose

The SDK facilitates interaction with target machines via hardware KVM (Keyboard, Video, Mouse) emulation, bypassing OS-level remote desktop software. Operations mimic physical interaction.

## Utilizing the Macro Engine

For sequential actions, use the Macro Engine (`sdk.run_macro()`) rather than individual method calls (`sdk.type()`, `sdk.press()`, etc.).

### Macro Engine Benefits
- **Reliability:** A single macro script defines the event sequence, handling timing locally to mitigate network latency between the execution environment and target.
- **Readability:** Macro scripts improve code auditability.
- **Suitability:** Designed for complex routines, including BIOS navigation and setup scripts execution.

### Example Macro Usage

Instead of doing this:
```python
sdk.press('f2')
time.sleep(1)
sdk.press('down')
sdk.press('enter')
sdk.type('password')
sdk.press('enter')
```

Do this:
```python
routine = """
PRESS f2
DELAY 1000
PRESS down
PRESS enter
TYPE password
PRESS enter
"""
sdk.run_macro(routine)
```

Please review `MACROS.md` for a full list of supported commands (`DELAY`, `TYPE`, `PRESS`, `HOTKEY`, `CLICK`).

## Operational Guidelines
- Verify target signal status using `sdk.get_status()` prior to interaction.
- For screen analysis, retrieve the latest frame with `sdk.get_screen()` and utilize vision or OCR capabilities.
- Coordinate parameters for `sdk.click()` require normalized percentages (0.0 to 1.0) relative to screen resolution, rather than absolute pixel values.