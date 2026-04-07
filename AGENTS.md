# Instructions for AI Agents

Welcome! If you are an AI agent (like Gemini, Codex, Claude, etc.) working with the AgentKVM2USB project, please adhere to these guidelines to maximize your effectiveness.

## Core Purpose

This SDK is designed to let you physically interact with target machines via hardware KVM (Keyboard, Video, Mouse) emulation, bypassing standard OS-level remote desktop software. You are acting as a physical operator sitting in front of the machine.

## Utilizing the Macro Engine

When you need to execute a sequence of actions on the target machine, **prefer using the Macro Engine** (`sdk.run_macro()`) over issuing individual method calls (`sdk.type()`, `sdk.press()`, etc.) in rapid succession.

### Why use Macros?
1. **Reliability:** By passing a single macro script, you define the exact sequence of events, ensuring timing is handled correctly by the SDK without relying on network latency between your execution environment and the target.
2. **Readability:** It makes your generated code cleaner and easier for humans to audit.
3. **Complex Routines:** It's perfect for navigating BIOS menus, logging in, or executing standard setup scripts.

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

## General Tips
- Always check `sdk.get_status()` to verify the target is outputting a signal before attempting to interact.
- If you are trying to find text on the screen, use `sdk.get_screen()` to pull the latest frame, and then analyze it using your vision capabilities (or pass it to an OCR tool if available).
- The `sdk.click()` method uses normalized percentages (0.0 to 1.0) relative to the screen resolution, not absolute pixels.