# Contract: Knob module (top module)

**ID prefix:** `KNOB` · **Status:** draft v0.2 · **First phase:** P0 (motor evaluation), P4 · **License:** CERN-OHL-S-2.0 / GPL-3.0-or-later
**Implements:** [module-interface.md](module-interface.md), side `B` (back edge).
**Owns:** the knob profile format.

## Purpose

Three **small** force-feedback knobs and a few programmable keys on the keyboard's back edge.
The motors create every feel in software: smooth, clicky ("thocky"), end stops, spring-back,
free spin, and a knob that turns by itself with the music.

This is a new design. Earlier knob experiments are not its base (D-28).

## Design goal: as small as the feel allows

| Item | Target |
|---|---|
| Knob cap | 12–20 mm diameter, flat round disc with a line marker, protruding only 3–6 mm (MECH-014). Final size from KNOB-001 |
| Motor | Outer diameter ≤ 20 mm preferred, height ≤ 12 mm |
| Module body | Same height as the keyboard where possible (≤ 21 mm) |

**Sizing physics:**
- **Fingertip force is torque divided by the knob's radius.** A smaller cap needs less torque for the same felt force.
- **Torque scales roughly with rotor volume (diameter² × length).** An 1105-class motor has about 30 % of the torque of an 1806-class motor.
- **At 5 V, voltage-mode control gives at most about 2.9 V across the windings**, with space-vector PWM.
- **Rough estimates:**
  - 1806 class (about 6 Ω) behind a 20 mm cap: about 1 N at the rim.
  - 1105 class behind a 12–15 mm cap: about 0.4–0.5 N at the rim. That's enough for fine clicks, but probably weak for a "thocky" click.
- **Datasheets can't settle this.** Neither the felt strength nor the cogging (built-in notchiness) shows up in a datasheet, so the choice comes from a physical comparison (KNOB-001).

## Hardware

| Part | v1 choice |
|---|---|
| Motor | Micro gimbal outrunner (high phase resistance, many poles, solid shaft). Candidates: **1105 class** (≈ 14 mm bell, smallest), **1806 class** (≈ 23 mm), **2204 class** (≈ 27 mm, upper bound). Requirements: phase resistance 5–15 Ω, ≥ 6 pole pairs, low cogging, room for a diametric magnet at the shaft end. Choice: OPEN-05 |
| Angle sensor | MT6701 over SSI (14-bit), diametric magnet at the specified gap |
| Driver | TMC6300 class per motor (2–11 V), 5 V from `VMOD`, thermal shutdown built in (stock risk: OPEN-19) |
| MCU | One MCU for all three motors, with enough motor-control timers and Rust/Embassy support (STM32G4 class; OPEN-16) |
| Keys | Programmable keys, same switch family as the main board (count and layout: OPEN-09) |
| Not included | No press function, no displays, no touch sensors |

**Considered and rejected for v1: 16 mm slotless motors.** They have no cogging at all, which is ideal for
the feel. But they are long cylinders (≥ 25 mm), which breaks the slim module, they need about 1 A for useful
torque, and they are expensive. They are an option for a later "premium knob" variant.

## Profile format (owned here)

KO defines its own versioned profile format in P4 (JSON in the app, compact binary on the module).
Minimum content:

| Group | Parameters |
|---|---|
| Positions | count (0 = unbounded), start, angle per position |
| Detents | strength, snap point / hysteresis, optional subset of positions that click |
| End stops | strength (ceiling measured per motor) |
| Motion | friction, damping, inertia (free spin), spring-return strength |
| Music-follow | enable, follow speed source, grip behaviour |
| Action | what a step does: scroll, volume, keycodes, app event |

**Rules:**
- **Missing fields:** they take their defaults.
- **Values:** every value is clamped to its allowed range.
- **Invalid profile:** it is rejected and the previous one stays active.
- **Version:** the format version is checked.

**Calibration is per motor model, not per profile.** It covers strength gain, damping gain, dead zone, torque ceiling, max velocity and thermal limits. The values are measured in KNOB-001.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| KNOB-001 | 1105-, 1806- and 2204-class candidates shall be compared on a test jig at 5 V (TMC6300-class driver, MT6701 sensor). The smallest motor and cap size shall be chosen that give (a) a clearly felt click, (b) a smooth profile without perceptible notchiness, (c) no overheating while held against an end stop for 2 minutes. Output: chosen motor, cap size, calibration values, end-stop ceiling. | P0 | D/M |
| KNOB-002 | All three knobs shall use identical hardware; every feel is a profile. | P4 | I |
| KNOB-003 | The angle sensor shall have ≥ 12-bit resolution and be read every control cycle. | P4 | M |
| KNOB-004 | The torque control loop shall run at ≥ 5 kHz per motor; motor PWM ≥ 20 kHz (inaudible). | P4 | M |
| KNOB-005 | Profiles: smooth, detent ("thocky"), end stops, spring-return, free spin with inertia, music-follow. Any profile on any knob. | P4 | D |
| KNOB-006 | Default profiles: knob 1 smooth, knob 2 thocky detents, knob 3 music-follow; tuned with the owner in P4. | P4 | D |
| KNOB-007 | In a blind test the smooth profile shall show no perceptible notchiness to the owner; torque ripple shall be measured and recorded. | P4 | D/M |
| KNOB-008 | Profiles shall switch per application through the KO app within 100 ms of the focus-change notification. | P5 | M |
| KNOB-009 | Rotation events shall reach the keyboard within 1 ms over the module bus; the keyboard maps them to HID (scroll, volume) or app events. | P4 | M |
| KNOB-010 | Power: full mode on USB or a power module. On battery: torque limited, music-follow paused by default (the user may allow it), motor drivers asleep until the encoder sees motion, awake within 5 ms. No extra sensor. | P4 | M |
| KNOB-011 | Idle module current on battery shall be ≤ 3 mA (target, confirmed in P4). | P4 | M |
| KNOB-012 | No audible whine from 30 cm in a quiet room. | P4 | D |
| KNOB-013 | The module body should match the keyboard height (target ≤ 21 mm), with the flat knob caps protruding only 3–6 mm (MECH-014); motors sit inside the body. It shall bridge over the two back-edge USB-C plugs (straight and angled plugs fit). | P4 | M |
| KNOB-014 | Firmware shall be Rust; SimpleFOC may be used as an algorithm reference. C++ is allowed only on the P0 test jig. | P4 | I |
| KNOB-015 | A horizontal haptic roller (motor mounted sideways, its outer shell as the wheel) may be prototyped as an experiment. | Later | D |
| KNOB-016 | Safety: a hard torque ceiling no profile can exceed; thermal protection (driver thermal shutdown plus a firmware heat estimate that folds back sustained load smoothly); zero torque above max velocity, on invalid sensor data or non-finite values. | P4 | T |
| KNOB-017 | The module shall store the last profile of each knob and restore it at power-up. | P4 | T |
| KNOB-018 | The haptics math shall be a pure, host-tested Rust crate (`ko-haptics`) with unit tests for every profile type and every safety rule in KNOB-016. | P4 | T |
| KNOB-019 | Music-follow: knob 3 turns with the playback state sent by the host; grabbing it overrides the motor at once; releasing hands control back smoothly. | P4 | D |
| KNOB-020 | The module shall report health once per second: control-loop rate, heat estimate, magnet state per knob. | P4 | T |
| KNOB-021 | Every knob's sensor shall report a magnet strength inside its valid window; the mechanics fix the magnet-to-sensor gap. | P4 | M |


## Default uses (configured in the app)

Photoshop: brush size, opacity, zoom, canvas rotation · Rhino / Fusion: orbit, zoom, pan ·
KeyShot: lens settings · System: volume, per-app volume mixer, scrolling, timelines ·
Music: knob 3 follows playback.
