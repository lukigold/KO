# Contract: Knob module (top module)

**ID prefix:** `KNOB` · **Status:** draft v0.1 · **First phase:** P0 (motor evaluation), P4 · **License:** CERN-OHL-S-2.0 / GPL-3.0-or-later
**Implements:** [module-interface.md](module-interface.md), side `B` (back edge).

## Purpose

Three small force-feedback knobs and a few programmable keys, attached to the keyboard's back edge.
The motors create every feel in software: smooth, clicky ("thocky"), end stops, spring-back,
and a knob that turns by itself with the music.

## Hardware

| Part | v1 choice |
|---|---|
| Knobs | 3 upright knobs; caps 15–20 mm, flat and round with a line marker on top ([mechanical.md](mechanical.md)) |
| Motors | The smallest solid-shaft gimbal BLDC that passes the feel tests. Candidates: 1806 class (e.g. SteadyWin GB1806: 5.9 Ω, 7 pole pairs; HAITAI HT1806: 16.5 mm tall) and 2204 class. Selection: OPEN-05 |
| Angle sensor | Magnetic absolute encoder, MT6701 class (as in the open-source SmartKnob) |
| Driver | Integrated low-voltage 3-phase driver per motor, TMC6300 class, 5 V from `VMOD` |
| MCU | One MCU drives all three motors; needs enough motor-control timers and Rust/Embassy support (STM32G4 class; OPEN-16) |
| Keys | Programmable keys, same switch family as the main board (count and layout: OPEN-09) |
| Not included | No press function, no displays, no touch sensors |

**Why small motors work:** the force at the fingertip is torque ÷ knob radius. A 15–20 mm knob needs
about half the torque of a 40 mm knob for the same feel, and an 1806-class motor gives roughly
20 mNm at 5 V (≈ 2 N at the rim of a 20 mm knob).

**The main risk is cogging,** the motor's built-in magnetic notchiness. It spoils the smooth knob and
fine detents, and datasheets don't show it. That is why motor candidates are bought and compared in P0.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| KNOB-001 | 3–4 candidate motors shall be compared on the owner's existing test rig; the 2 best go into the P4 design. | P0 | D |
| KNOB-002 | All three knobs shall use identical hardware; every feel is a software profile. | P4 | I |
| KNOB-003 | The angle sensor shall be read at ≥ 5 kHz with ≥ 12-bit resolution. | P4 | M |
| KNOB-004 | The torque control loop shall run at ≥ 5 kHz; motor PWM ≥ 20 kHz (inaudible). | P4 | M |
| KNOB-005 | Profiles: smooth (friction, inertia), detent (count, strength, snap: the "thocky" knob), end stops, spring-return, music-follow (the motor turns the knob with playback; grabbing it scrubs). Any profile on any knob. | P4 | D |
| KNOB-006 | The owner's tuned "smooth" and "thocky" parameters from their existing test project shall become the default profiles (owner provides the values). | P4 | D |
| KNOB-007 | In a blind test, the smooth profile shall show no perceptible notchiness to the owner; torque ripple shall be measured and recorded. | P4 | D/M |
| KNOB-008 | Profiles shall switch per application through the KO app within 100 ms of the focus change notification. | P5 | M |
| KNOB-009 | Rotation events shall reach the keyboard within 1 ms over the module bus; the keyboard maps them to HID (scroll, volume) or app events. | P4 | M |
| KNOB-010 | Power: full mode on USB or a power module. On battery: torque limited, music-follow paused, motor drivers asleep until the encoder sees motion, then awake within 5 ms. No extra sensor for this. | P4 | M |
| KNOB-011 | Idle module current on battery shall be ≤ 3 mA (target, confirm in P4). | P4 | M |
| KNOB-012 | No audible whine from 30 cm in a quiet room. | P4 | D |
| KNOB-013 | The module body should match the keyboard height (target ≤ 21 mm), with the flat knob caps protruding only 3–6 mm (MECH-014); motors sit inside the body. It shall bridge over the two back-edge USB-C plugs (straight and angled plugs fit). | P4 | M |
| KNOB-014 | Firmware shall be Rust, using SimpleFOC's methods as the algorithm reference. C++ SimpleFOC is allowed only for motor evaluation in P0. | P4 | I |
| KNOB-015 | A horizontal haptic roller (motor mounted sideways, its outer shell as the wheel) may be prototyped as an experiment. | Later | D |

## Default uses (configured in the app)

Photoshop: brush size, opacity, zoom, canvas rotation · Rhino / Fusion: orbit, zoom, pan ·
KeyShot: lens settings · System: volume, per-app volume mixer, scrolling, timelines ·
Music: knob 3 follows playback.
