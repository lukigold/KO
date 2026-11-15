# Contract: Keyboard firmware

**ID prefix:** `FW` · **Status:** draft v0.1 · **First phase:** P0 (dev kit), P1 · **License:** GPL-3.0-or-later
(shared crates `ko-module-bus` and the module-facing parts of `ko-protocol`: MIT OR Apache-2.0)

## Purpose

The firmware of the main keyboard (nRF52840). Other images have their own contracts: dongle
([wireless.md](wireless.md)), knob module ([knob-module.md](knob-module.md)), side modules
([module-interface.md](module-interface.md)).

## Stack

- **Rust + Embassy**, based on **RMK** (contribute upstream where it makes sense; keep KO-specific code in our own crates).
- **P1–P2:** keymaps edited with the existing **Vial** app (RMK supports it). Everything Vial covers stays
  in the backlog for the KO app ([host-app.md](host-app.md)).
- **From P5:** the KO host protocol and app take over. Vial and the KO protocol must be able to coexist
  during the transition (OPEN-13).

## Workspace (target)

```
firmware/
  keyboard/        nRF52840 application (board support per core-board revision)
  dongle/          dongle application
  knob-module/     knob module application
  side-module/     macro column / numpad application
  ko-keymap/       keymap engine, tap-hold, combos, macros, SOCD   (host-testable)
  ko-haptics/      knob haptics, music-follow, safety guards       (host-testable, see knob-module.md)
  ko-switching/    output-selection state machine                   (host-testable)
  ko-link/         2.4 GHz link protocol                             (host-testable parts)
  ko-protocol/     host protocol messages and versioning
  ko-module-bus/   module bus protocol, descriptor                   (host-testable)
```

## Internal contract: keymap engine

- **Input:** timestamped key events (main matrix and modules, same type), output state, OS mode.
- **Output:** HID reports for the active output.
- **Guarantees:** no event lost, order preserved. Identical input sequences produce identical output
  (deterministic, so it can be unit-tested on the host).
- **Invariant:** when the active output changes, every pressed key is released on the old output first.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| FW-001 | At least 8 layers; each connection slot has its own OS mode (macOS / Windows / iOS). | P1 | T |
| FW-002 | Tap-hold shall support home-row modifiers: per-key tapping term, permissive hold, quick-tap. | P1 | T |
| FW-003 | Combos shall be supported. | P1 | T |
| FW-004 | Macros shall be stored on the keyboard and editable through Vial / the KO app. | P1 | T |
| FW-005 | Gaming mode shall disable Win/Cmd and other configurable keys, remove tap-hold delays on the gaming layer, and select the lowest-latency radio settings. | P2 | T |
| FW-006 | SOCD shall be configurable per key pair: off (default), last input wins, neutral, first input wins. Some games and tournaments forbid it; it stays off unless the user enables it. | P2 | T |
| FW-007 | Debounce shall be eager: a press is reported on the first edge; release debounce ≤ 5 ms; scan rate ≥ 1 kHz while keys are active. | P1 | M |
| FW-008 | Matrix scanning shall use the switch board interface; layout, matrix and LED maps come from the descriptor EEPROM ([switch-board.md](switch-board.md)). | P1 | T |
| FW-009 | Indicators shall use the per-key LEDs: Caps Lock, battery level (Fn held), pairing, charging, module attached. Behaviour is configurable. On battery, indicator flashes last ≤ 2 s at ≤ 10 % brightness. | P1 | T |
| FW-010 | Lighting policy: on USB power RGB follows the user's settings; on battery RGB is off by default, with an optional dim "light while typing" mode; a brightness cap keeps the LED rail within budget. | P1 | T |
| FW-011 | Power management: light sleep after a configurable idle time, deep sleep later; wake on key, knob, module event or USB; sleep current per CORE-008. | P1 | M |
| FW-012 | Battery level shall be reported through the Bluetooth Battery Service and the host protocol; low battery triggers a key indication and an app notice. | P1 | T |
| FW-013 | Updates: a UF2 drag-and-drop bootloader (the keyboard appears as a drive), and updates through the KO app over USB (P5). App updates never overwrite the bootloader; an interrupted update shall not brick the keyboard. | P1 | T |
| FW-014 | A module manager shall run the detection/power state machine, enumerate modules, parse descriptors, merge module key events into the keymap (module keys are mappable like main keys) and update module firmware automatically. | P3 | T |
| FW-015 | The output-selection rules R1–R4 shall be implemented as specified in [wireless.md](wireless.md). | P2 | T |
| FW-016 | The keyboard shall implement the device side of the KO host protocol ([host-app.md](host-app.md)). | P5 | T |
| FW-017 | USB shall present a composite HID device (NKRO keyboard, consumer, system, vendor interface) at 1,000 Hz. | P1 | T |
| FW-018 | NKRO over USB and 2.4 GHz; over Bluetooth as far as the host supports it. | P2 | T |
| FW-019 | Logging via `defmt` over RTT; release builds carry no logging overhead in the scan path. | P1 | I |
| FW-020 | Hardware-independent crates (see workspace) shall have host unit tests that run in CI. | P1 | T |
| FW-021 | A latency test procedure (key actuation → host report timestamp) shall exist and its results be recorded for USB and 2.4 GHz. | P2 | M |
| FW-022 | Wireless (OTA) firmware updates. | Later | T |
