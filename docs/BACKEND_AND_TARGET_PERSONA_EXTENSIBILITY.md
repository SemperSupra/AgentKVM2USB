# Backend and Target Persona Extensibility

Canonical issue: #12. Cross-repo roadmap: #23 and
`docs/MULTI_DEVICE_MEDIA_SPEECH_ROADMAP.md`.

## Purpose

AgentKVM2USB should become the semantic orchestration and target-routing layer for
multiple KVM device families and multiple target-side HID personas. Application,
macro, media, and speech workflows must not construct device-specific reports.

## Ownership Boundary

AgentKVM2USB owns:

- supported KVM discovery and stable physical grouping;
- explicit device and target selection;
- semantic keyboard, pointer, status, and system-control APIs;
- KVM video and health;
- target-persona capability enforcement;
- isolated KVM workers, target bundles, leases, authorization, and evidence.

OpenKVM2USB owns target-side USB implementation and firmware personas.
AgentWebCam owns general cameras, microphones, speakers, STT, and TTS.

## Architecture

```text
Application / agents / voice proposals
              |
Target-addressed semantic KVM service
              |
TargetBundle registry, leases, authorization, capabilities
              |
Backend contract
              |
+----------------------+----------------------+--------------------+
| Epiphan KVM2USB 3.0  | OpenKVM2USB          | Other KVM backend  |
+----------------------+----------------------+--------------------+
```

## Backend Contract

A backend exposes:

- backend ID and implementation version;
- supported USB identities and discovery rules;
- stable physical-device grouping and selectors;
- video source and modes;
- semantic input transport and codecs;
- target-persona discovery and selection;
- capability set and safety class per operation;
- status, health, reconnect, release-all, and close;
- protocol/firmware compatibility and structured diagnostics.

Suggested shape:

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

## Physical KVM and Target Bundle

`PhysicalKvm` groups all interfaces belonging to one unit using serial,
ContainerId, composite instance, location path, hub, and port. HID, UVC, and
configuration interfaces may never be grouped by enumeration order alone.

`TargetBundle` associates:

- target identity/profile;
- physical KVM and KVM video;
- optional auxiliary cameras;
- optional controller microphone/speaker;
- optional target-audio adapters;
- runtime/evidence root;
- active lease and authorization state.

## Capability Model

Capabilities are machine-readable and tied to backend, physical device, active
persona, and policy. Callers must distinguish unsupported, disabled, temporarily
unavailable, disruptive, and persistent operations.

Example capabilities:

```text
keyboard.boot
keyboard.complete
keyboard.consumer_control
pointer.relative
pointer.buttons.3
pointer.wheel.vertical
pointer.absolute_pen
pointer.absolute_touch
target_persona.selectable
video.capture
status.health
```

Silent semantic fallback is prohibited.

## Target Profiles and Personas

Target profiles describe BIOS/UEFI, bootloader, installer, desktop, server,
appliance, embedded, or OT requirements. They record required capabilities,
layout, pacing, quirks, preferred personas, calibration, prohibited controls,
and validation evidence.

Persona changes that require re-enumeration are explicit disruptive operations.

## Multi-Target Control Plane

- one worker per physical KVM;
- explicit `/targets/{target_id}/...` routes;
- one control lease per target;
- no implicit target when multiple targets exist;
- synchronized correlation IDs for actions and evidence;
- emergency release-all and media stop;
- consume AgentWebCam media/STT/TTS as structured services;
- voice interpretation proposes semantic actions and never emits HID reports.

## Initial Backends

- Epiphan KVM2USB 3.0;
- OpenKVM2USB baseline/enhanced personas;
- simulator/replay;
- later generic UVC plus independent HID and documented/open network KVMs.

## Conformance Tests

- zero, one, and multiple devices;
- deterministic selection and no interface mixing;
- complete capability serialization;
- semantic keyboard and pointer operations;
- unsupported-action rejection;
- disconnect, reconnect, cancellation, shutdown, and release-all;
- target-persona changes and re-enumeration;
- two-target concurrent routing;
- target-side receipt, not only successful host writes.

## Safety

Classify read-only discovery, transient input, disruptive re-enumeration,
persistent configuration, and firmware operations separately. Persistent and
disruptive actions require explicit authorization and auditable results.

## Delivery Order

1. Complete #22 → #14 → PR #13 / #8 Phase B.
2. Complete #8 relative mouse and pen/touch.
3. Complete #8 stable multi-device grouping.
4. Define backend, capability, worker, registry, and target-bundle contracts.
5. Convert the headless API to target-addressed routes.
6. Integrate AgentWebCam#3 media and speech service.
7. Integrate #24 target audio.
8. Add other backends one at a time.

## Exit Gate

Two KVM devices and targets operate concurrently without interface or command
mixing, backend/persona capabilities are enforced, target/media resources route
by stable ID, and lease, authorization, reconnect, evidence, and conformance tests
pass.