# Multi-Device, Media, Audio, and Speech Roadmap

Tracking epic: issue #23.

Related work:

- issue #8 — device profiles, semantic input, physical-device grouping, and multi-device resilience;
- issue #12 — pluggable backends, target personas, target bundles, and multi-target control plane;
- issue #14 and issue #22 — current single-device reverse-engineering critical path;
- issue #24 — controlled-target audio characterization and integration;
- `SemperSupra/AgentWebCam#3` — general media-device and controller-side speech service.

## Purpose

This document records the future architecture and phased feature bring-up required
to operate multiple KVM2USB units and controlled targets from one host while also
supporting auxiliary webcams, snapshots, video, microphones, speakers, voice
notes, spoken commands, spoken feedback, and optional controlled-target audio.

It is a roadmap, not authorization for live target input, capture, persistent
device changes, or audio monitoring.

## Current State and Gap

The current implementation is single-device by construction:

- one `EpiphanKVM_SDK` instance owns one keyboard, mouse, touch, and system HID
  handle plus one active camera;
- HID discovery matches VID/PID and usage without first grouping interfaces by
  physical device;
- later enumeration records can overwrite earlier handles;
- the first camera whose name resembles KVM2USB is selected;
- the headless API wraps one implicit SDK instance and has no target identifier;
- DirectShow/UVC capture is effectively exclusive and must have clear ownership.

Therefore, attaching multiple KVM2USB units today is not safe: interfaces can be
mixed, camera indices can move, and commands do not carry an explicit target.

AgentWebCam already provides useful media foundations:

- camera discovery;
- snapshots and base64 frames;
- fixed-duration video and timelapse;
- overlays, SRT, and motion metadata;
- microphone enumeration and recording;
- synchronized audio/video muxing.

Those capabilities should become a shared media service instead of being copied
into the KVM backend.

## Architectural Boundaries

### AgentKVM2USB owns

- physical KVM discovery and grouping;
- stable KVM identity and target association;
- semantic keyboard, pointer, and system operations;
- KVM video and health;
- one isolated KVM worker/session per physical unit;
- target routing, leases, authorization, and evidence correlation;
- target-audio adapter association and policy.

### AgentWebCam owns

- general camera, microphone, and speaker discovery;
- stable media-device identity;
- snapshots, video, timelapse, microphone capture, and playback;
- media workers and health;
- speech-to-text and text-to-speech provider interfaces;
- voice-note recording and transcript provenance.

### Shared control plane owns

- target and media registry;
- `TargetBundle` records;
- explicit target/device selection;
- operation leases and safety classes;
- synchronized timestamps and correlation IDs;
- API/UI routing and emergency stop;
- confirmation policy for voice-proposed operations.

## Target Data Model

A physical KVM must be identified as a whole device, not as unrelated HID and
camera indices.

```text
PhysicalKvm
  stable_id
  backend_id
  serial
  pnp_container_id
  composite_instance
  location_path
  usb_controller
  hub_and_port
  hid_collections
  uvc_source
  config_interface
  capabilities
```

A controlled system is represented as a target bundle:

```text
TargetBundle
  target_id
  target_profile
  kvm_device_id
  kvm_video_id
  auxiliary_camera_ids[]
  controller_microphone_id?
  controller_speaker_id?
  target_audio_capture_id?
  target_audio_injection_id?
  session_root
  active_lease
  authorization_state
```

Stable IDs must survive index reordering. When more than one device exists,
implicit target selection is prohibited.

## Runtime Shape

Use one supervised worker process per physical KVM or opened media device.

```text
Agent Device Control Plane
  Device and Target Registry
  Authorization and Lease Manager
  KVM Worker: target-a
  KVM Worker: target-b
  Camera Worker: room-overview
  Camera Worker: front-panel
  Audio Worker: desk-microphone
  Audio Worker: selected-speaker
  Speech Service
  Evidence and Event Store
```

Worker isolation provides:

- exclusive DirectShow/UVC ownership;
- failure and reconnect isolation;
- separate locks and runtime roots;
- no cross-target HID state;
- independent health and restart;
- clear evidence provenance.

## Concentrated Delivery Plan

### Phase 0 — Preserve the current critical path

Complete in order:

1. issue #22 workstation dependencies and passing no-live preflight;
2. issue #14 official-app differential experiment and first downstream HID
   divergence;
3. PR #13 target-receipt validation and issue #8 Phase B exit gate.

Do not add multi-device, media, or speech orchestration to those work items.

### Phase 1 — Complete one-KVM semantics

Owner: issue #8.

- validate keyboard target receipt and release-all;
- complete generic relative mouse;
- complete distinct pen/touch behavior;
- retain structured errors and capability enforcement;
- validate preboot, Windows, and Linux targets.

Exit: one explicitly selected KVM reliably controls one target.

### Phase 2 — Stable physical-device registry

Owner: issue #8 Phase E.

- group HID, UVC, and MI_00 by serial, ContainerId, composite device, location
  path, hub, and port;
- expose stable KVM IDs independent of camera index;
- require explicit selection for ambiguous matches;
- reject partial, duplicate, inaccessible, and mixed devices;
- support disconnect and reconnect;
- record USB topology for bandwidth planning.

Exit: two KVM2USB units enumerate as two complete isolated devices.

### Phase 3 — Multi-KVM workers and target bundles

Owner: issue #12.

- one worker per KVM;
- exclusive UVC and HID ownership;
- supervised restart/reconnect;
- target registry and `TargetBundle` model;
- one lease and evidence stream per target;
- target-addressed API;
- no implicit target with multiple targets.

Exit: two targets are monitored and controlled concurrently without mixing.

### Phase 4 — General media-device service

Owner: `SemperSupra/AgentWebCam#3`.

- stable camera, microphone, and speaker IDs;
- isolated workers and leases;
- list, health, snapshot, record, stop, timelapse, audio note, and playback API;
- target association metadata;
- synchronized timestamps and correlation IDs;
- private/ignored raw media storage.

Exit: multiple cameras and a microphone operate concurrently by stable ID.

### Phase 5 — Voice notes, STT, and TTS

Owners: AgentWebCam#3 and issue #12 integration.

- local-first STT provider contract;
- TTS provider contract and explicit speaker routing;
- push-to-talk first;
- separate note and command modes;
- voice-note audio, transcript, confidence, UTC, target, and correlation metadata;
- proposed commands returned as semantic actions;
- target resolution, policy checks, and confirmations in AgentKVM2USB;
- immediate stop/cancel;
- echo suppression so TTS cannot trigger STT.

Exit: a voice note can be transcribed and a harmless read-only action can be
confirmed and acknowledged without unintended HID input.

### Phase 6 — Controlled-target audio

Owner: issue #24.

- characterize KVM2USB audio interfaces and actual streams;
- do not infer streaming capability from the recovered audio-selector flag;
- use explicit USB audio adapters when required;
- map each audio direction to exactly one target;
- expose capture, playback, and injection only through capability and lease gates;
- measure latency and A/V synchronization.

Exit: target audio capability is explicitly supported, unsupported, or routed
through validated external hardware.

### Phase 7 — Scale and reliability

- USB-controller-aware placement and bandwidth budgets;
- background targets use snapshots or reduced stream profiles;
- dashboard grid for 2–4 targets;
- long-duration soak and reconnect testing;
- disk quotas and retention;
- auditable emergency stop and release-all.

## API Direction

```text
GET  /targets
GET  /targets/{target_id}/status
GET  /targets/{target_id}/frame
POST /targets/{target_id}/keyboard
POST /targets/{target_id}/pointer
POST /targets/{target_id}/macro

GET  /media/devices
GET  /media/devices/{device_id}/health
POST /cameras/{camera_id}/snapshot
POST /cameras/{camera_id}/record
POST /cameras/{camera_id}/stop
POST /microphones/{microphone_id}/record
POST /speakers/{speaker_id}/speak
POST /speech/transcribe
POST /speech/interpret
```

## Voice Safety Model

- voice input never produces raw HID directly;
- explicit target selection is required;
- push-to-talk is the initial mode;
- note and command modes are visibly distinct;
- consequential actions require confirmation;
- ambiguity or low confidence causes refusal;
- TTS output is suppressed from command recognition;
- one control lease exists per target;
- immediate stop releases input and stops media operations;
- proposed, confirmed, rejected, and executed actions are audited.

## USB Bandwidth

Uncompressed 1080p60 YUY2 is roughly 2 Gb/s of pixel payload before USB overhead.
Multiple full-rate KVM2USB streams should not be assumed to work behind one hub or
controller.

The registry must record controller/hub placement, and the control plane should
support:

- one full-rate active stream per constrained controller;
- reduced resolution/frame rate for background targets;
- snapshot-only monitoring;
- bandwidth health and explicit resource errors.

## Validation Matrix

- zero, one, and multiple physical KVM devices;
- two same-model devices without interface mixing;
- reconnect and index churn;
- two target workers with concurrent health/video;
- input delivered only to the selected target;
- multiple cameras and duplicate friendly names;
- concurrent camera and microphone recording;
- selected speaker routing;
- STT silence, ambiguity, and provider failure;
- TTS/STT feedback-loop prevention;
- target-audio cross-routing prevention;
- bandwidth saturation and graceful degradation;
- long-duration operation and retention limits.

## Decision Summary

Do not turn `EpiphanKVM_SDK` into a monolithic handler for every KVM, camera, and
audio device. Establish stable device identities and isolated workers, keep media
and speech in AgentWebCam, keep target routing and authorization in AgentKVM2USB,
and integrate through explicit target/media IDs and structured semantic actions.