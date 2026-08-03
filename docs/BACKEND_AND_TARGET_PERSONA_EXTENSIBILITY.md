# Backend and Target Persona Extensibility

This document records future host-side work that allows AgentKVM2USB to control
multiple KVM device families and multiple target-side HID personas without
embedding device-specific report formats in the application layer.

Related records:

- Issue #8: profile-driven input discovery and semantic input path
- `docs/INPUT_PATH_STRATEGY.md`: current keyboard and pointer recovery plan
- `docs/REMOTE_AGENT_COORDINATION.md`: GitHub coordination protocol
- `SemperSupra/OpenKVM2USB/docs/TARGET_USB_AND_HID_EXPANSION.md`: target-side
  firmware, USB-channel, HID-persona, and future hardware roadmap

## Ownership Boundary

AgentKVM2USB owns:

- discovering supported host-visible KVM devices;
- selecting one physical device deterministically;
- presenting semantic keyboard, pointer, system-control, and custom-control APIs;
- selecting or requesting an available target persona;
- validating capabilities before an action is sent;
- video capture and status integration;
- structured diagnostics, provenance, tests, and operator policy.

AgentKVM2USB does not own:

- proprietary firmware recovery;
- target-side USB descriptor implementation;
- FPGA design;
- persistent device writes without explicit hardware-safe workflows;
- arbitrary assumptions about endpoint capacity or target-side USB channels.

Those belong in OpenKVM2USB and the private research vault.

## Long-Term Host Architecture

Refactor toward explicit backend contracts:

```text
Application / agent workflows
        |
Semantic KVM service
        |
Capability and target-persona policy
        |
KVM backend interface
        |
+----------------------+----------------------+--------------------+
| Epiphan KVM2USB 3.0  | OpenKVM2USB          | Other KVM backend  |
| UVC + vendor HID     | UVC/HID/WinUSB       | Device-specific    |
+----------------------+----------------------+--------------------+
```

The application should not construct raw HID report bytes. It should request
semantic operations such as:

```text
key_down(key)
key_up(key)
press(key)
type_text(text, layout)
release_all()
move_relative(dx, dy)
move_absolute(x, y)
button_down(button)
button_up(button)
wheel(vertical, horizontal)
contact_down(x, y)
contact_up(x, y)
consumer_control(action)
system_control(action)
custom_control(control_id, value)
```

A backend profile translates those requests into verified device operations.

## Backend Contract

Each backend should expose:

- backend identifier and implementation version;
- supported USB identities and discovery rules;
- physical-device grouping and stable selection identifiers;
- video sources and modes;
- input transports and report codecs;
- target-persona discovery and selection behavior;
- capability set;
- status and health information;
- reconnect and recovery behavior;
- safety class for each operation;
- read-only versus persistent operations;
- firmware or protocol compatibility range;
- structured errors and diagnostics.

Suggested interface shape:

```python
class KvmBackend:
    def discover(self) -> list[PhysicalKvm]: ...
    def connect(self, selector: DeviceSelector) -> ConnectedKvm: ...
    def capabilities(self) -> CapabilitySet: ...
    def active_target_persona(self) -> TargetPersonaInfo: ...
    def available_target_personas(self) -> list[TargetPersonaInfo]: ...
    def request_target_persona(self, persona_id: str) -> OperationResult: ...
    def input(self) -> SemanticInputDevice: ...
    def video(self) -> VideoSource: ...
    def status(self) -> KvmStatus: ...
    def release_all(self) -> OperationResult: ...
    def close(self) -> None: ...
```

Persona selection may require a controlled target-port re-enumeration or device
restart. It must therefore be represented as an explicit operation with clear
impact rather than a transparent property change.

## Capability Model

Capabilities should be machine-readable and tied to the active target persona:

```text
keyboard.boot
keyboard.complete
keyboard.nkro
keyboard.consumer_control
keyboard.system_control
pointer.relative
pointer.buttons.3
pointer.buttons.5
pointer.wheel.vertical
pointer.wheel.horizontal
pointer.absolute_pen
pointer.absolute_touch
pointer.multitouch
custom.keypad
custom.axis
custom.switches
target_persona.selectable
virtual_serial
virtual_media.read_only
```

The caller must be able to distinguish:

- unsupported by the hardware;
- unsupported by the active persona;
- disabled by policy;
- temporarily unavailable;
- requires target re-enumeration;
- requires persistent firmware or configuration change.

Silent fallback is prohibited when semantics change. In particular, an absolute
click must not be converted into uncalibrated relative movement.

## Target Persona Integration

AgentKVM2USB should consume a versioned persona description supplied by the
backend or maintained in a compatible registry. A persona includes:

- persona ID and version;
- intended target classes and known compatible systems;
- active VID/PID and descriptor identity metadata where available;
- supported semantic capabilities;
- coordinate, button, key, and polling constraints;
- required target drivers;
- re-enumeration requirements;
- safety restrictions;
- validated target environments and known incompatibilities.

The application may recommend a persona from a target profile, but the operator
or automation policy must make the final selection when the change could disrupt
the controlled system.

## System-Specific Target Profiles

A target profile is distinct from a USB device backend. It describes the
controlled system's input requirements, for example:

- generic BIOS or UEFI;
- GRUB or another boot manager;
- Windows login, recovery, or installer;
- Linux console or desktop;
- server and BMC console;
- network appliance;
- embedded or operational-technology device;
- specialized keypad, switch panel, dial, joystick, or other standard HID
  control requirement.

A target profile should record:

- target class, vendor/model, and firmware or OS version when known;
- required and optional capabilities;
- prohibited or unsafe controls;
- keyboard layout;
- input pacing, rollover, polling, and reconnect quirks;
- preferred and fallback personas;
- coordinate transform or calibration;
- test evidence and last validation date.

Avoid storing credentials, secrets, or proprietary firmware in target profiles.

## Additional KVM Device Families

After issue #8 establishes the semantic input boundary, new backends may be added
for:

- future OpenKVM2USB firmware;
- generic UVC capture plus an independent HID emulator;
- network KVM systems with documented APIs;
- PiKVM- or TinyPilot-class systems where their open interfaces and licenses fit
  project policy;
- other USB KVM devices whose protocols are documented or independently
  characterized.

Each backend must pass the same semantic conformance tests. Device-specific
features remain optional capabilities rather than leaking into the common API.

## Conformance Test Suite

Create reusable backend tests for:

- zero, one, and multiple physical devices;
- deterministic selection and no interface mixing;
- complete capability reporting;
- keyboard key-down, key-up, modifiers, layout encoding, and release-all;
- relative pointer movement, buttons, drag, and wheels;
- absolute pen/touch behavior where advertised;
- rejection of unsupported actions;
- disconnect, reconnect, cancellation, exception, and shutdown cleanup;
- target-persona selection and re-enumeration behavior;
- structured diagnostics and stable serialization;
- target-side receipt on representative preboot and operating-system states.

A backend is not considered supported solely because enumeration or a host write
succeeds.

## Safety and Policy

Classify operations:

- read-only discovery and status;
- transient input;
- disruptive re-enumeration;
- persistent configuration;
- firmware or flash modification.

The normal host API should default to read-only and transient operations.
Persistent or disruptive actions require an explicit policy decision and an
auditable result.

System-control and custom-control HID actions should use allowlists. Do not add
profiles intended to impersonate security tokens, smart cards, licensed dongles,
or other protected device identities.

## Delivery Order

1. Complete issue #8 Phase A discovery corrections.
2. Complete semantic keyboard and relative-pointer APIs.
3. Separate Epiphan report codecs from application logic.
4. Define the backend and capability interfaces.
5. Add target-profile and persona data models.
6. Integrate OpenKVM2USB's baseline and enhanced personas.
7. Add reusable backend conformance tests.
8. Add other KVM families one backend at a time.
9. Add optional virtual serial or media capabilities only after the corresponding
   OpenKVM2USB resource and security work is complete.

## Decision Summary

AgentKVM2USB should become the common orchestration and semantic-control layer.
OpenKVM2USB should own target-side USB implementation and channel limits. This
separation allows system-specific HID personas and additional KVM devices without
turning the application into a collection of hard-coded VID/PID and report-byte
branches.
