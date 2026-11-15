# KO — Keyboard Organization

A premium, slim, wireless keyboard for competitive gaming and creative work, built as a **platform**:
one fixed core board, generated switch boards from 40 % to full size, and magnetic hot-pluggable
modules on all four sides, including force-feedback knobs. Open hardware, Rust firmware.

> **Status:** Phase 0 – requirements frozen as draft v0.1 (2026-11-15). No hardware or code yet.
> **Owner:** the repository owner (personal project, 1–3 units, then published as open source).

---

## How to read this repo

You never need more than these four documents for any task:

1. **This README** – the goal, the architecture, the top-level requirements and the roadmap.
2. **[AGENTS.md](AGENTS.md)** – the working rules for every contributor, human or AI.
3. **The contract for your subsystem** in [`docs/contracts/`](docs/contracts/) – what it must do and how it connects to its neighbours.
4. **[docs/decisions.md](docs/decisions.md)** – why things are the way they are, plus the list of open items.

Contracts follow *design by contract*: every interface states what the provider **guarantees**, what
the consumer must **ensure** (preconditions) and what must **always stay true** (invariants).
Every requirement has a permanent ID, a phase and a verification method.

---

## The product

```
            ┌───────────── Top module: 3 FOC knobs + programmable keys ─────────────┐
            └───────┬──────────── bridges over the two USB-C plugs ────────────┬────┘
┌───────┐┌───────┐┌─┴───────────────────────────────────────────────────────────┴─┐┌──────────┐
│ Macro ││ Macro ││                                                               ││          │
│  1×6  ││  1×6  ││                 KO main keyboard · 75 % · ISO-CH              ││  Numpad  │
│       ││       ││                                                               ││          │
└───────┘└───────┘└───────────────────────────────────────────────────────────────┘└──────────┘
   ← side modules chain left and right          side modules chain left and right →
            ┌──────────────── Front module: wrist rest / power (later) ──────────────┐
            └────────────────────────────────────────────────────────────────────────┘
```

- **Main keyboard:** 75 %, one piece, low profile (~20 mm including keycaps, ~2° built-in tilt),
  CNC aluminium in dark creamy warm silver, per-key RGB, no status LEDs.
- **Connections:** USB-C (any time), 2.4 GHz with its own USB-C dongle for gaming (1,000 Hz),
  Bluetooth for Mac and iOS. Switches between them automatically.
- **Two identical USB-C ports** on the back edge: whichever one sees a computer is the host port,
  the other becomes a small hub port (mouse dongle, USB stick) while the keyboard is wired.
- **Modules** snap on with magnets on all four sides and can be plugged in while running.
  Left and right modules chain (e.g. three 1×6 macro columns plus a numpad).
- **Knob module:** three small force-feedback knobs (smooth, "thocky", music-following),
  profiles switch per application.

### Architecture

```
 Host (Mac/PC) ═USB-C═╗                                       ┌─ 2.4 GHz ── KO dongle ══USB══ Windows PC
                      ║                                       │
   [USB-C A]──┐   role logic   ┌──────────── 7-port USB 2.0 HS hub ───────────┐
   [USB-C B]──┴── + data mux ──┤  ├─ nRF52840 radio module (MCU) ── BLE ── Mac / iOS
                               │  ├─ accessory USB-C port (≤ 500 mA)
                               │  └─ USB lane → each of the 4 module sides
                               └──────────────────────────────────────────────┘
   nRF52840 ══ size-independent connector ══ Switch board (sockets, RGB driver, descriptor EEPROM)
   nRF52840 ══ module bus + 5 V power ══════ 4 module sides (magnets, 6 contacts)
   Flat LiPo ── charger / power path / fuel gauge ── system rails
```

| Subsystem | What it is | Contract | ID prefix |
|---|---|---|---|
| Core board | Fixed "brain": radio MCU, battery, USB ports and hub, module ports | [core-board.md](docs/contracts/core-board.md) | `CORE` |
| Switch board | Generated board: MX + Choc hot-swap sockets, RGB, owns the core↔switch interface | [switch-board.md](docs/contracts/switch-board.md) | `SWB` |
| Module interface | Open spec: magnets, contacts, power, bus, chaining, module catalog | [module-interface.md](docs/contracts/module-interface.md) | `MOD` |
| Wireless | Bluetooth, 2.4 GHz link, dongle, automatic switching | [wireless.md](docs/contracts/wireless.md) | `RF` |
| Firmware | Keyboard firmware (Rust, RMK-based) | [firmware.md](docs/contracts/firmware.md) | `FW` |
| Knob module | Top module with three FOC haptic knobs | [knob-module.md](docs/contracts/knob-module.md) | `KNOB` |
| Host app | Desktop app (Tauri) and host protocol | [host-app.md](docs/contracts/host-app.md) | `APP` |
| Mechanical | Industrial design, case, acoustics, CAD workflow | [mechanical.md](docs/contracts/mechanical.md) | `MECH` |
| Generator | Layout → complete orderable keyboard package | [generator.md](docs/contracts/generator.md) | `GEN` |

---

## Principles (in priority order)

1. **Reliable and simple beats feature-rich.** Every feature must survive daily use for years.
2. **Stable interfaces beat clever implementations.** Contracts are designed to outlive any single board revision.
3. **Performance where you feel it:** typing latency, wireless stability, knob haptics.
4. **Low power by default:** anything power-hungry is off on battery unless the user asks for it.
5. **Everything scripted and reproducible:** PCBs, cases and firmware are generated or built from text files, so agents can work on them.
6. **Open:** share-alike for the product, permissive for the module spec so anyone can build modules.

---

## Top-level requirements

Detailed requirements live in the contracts. These are the ones the whole project is judged by.
Verification: **T** test · **M** measurement · **I** inspection · **A** analysis · **D** demonstration.

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| SYS-01 | The main keyboard shall be a one-piece 75 % layout; the owner's build is ISO-CH, and ANSI/ISO variants shall come from the generator. | P1 | I |
| SYS-02 | Height including keycaps shall be ≤ 18 mm at the front and ≤ 22 mm at the back (goal: 20 mm), with a built-in tilt of about 2° and no fold-out feet. | P6 | M |
| SYS-03 | In basic mode (RGB off, no powered modules) the battery shall last ≥ 4 weeks at 8 h/day of use over 2.4 GHz or Bluetooth. | P2 | M + A |
| SYS-04 | The keyboard shall connect over USB-C (any time, battery or not), 2.4 GHz via the KO dongle, and Bluetooth (Mac/iOS), and choose automatically. | P2 | T |
| SYS-05 | Report rate shall be 1,000 Hz over USB and 2.4 GHz; key-to-host latency ≤ 2 ms wired and ≤ 3 ms over 2.4 GHz (p99). | P2 | M |
| SYS-06 | Any MX-style or Kailh Choc v1/v2 switch shall fit the v1 switch board without soldering. | P1 | T |
| SYS-07 | Two identical USB-C ports: either can be the host/charging port; the other is an accessory port (≤ 500 mA) that works while the keyboard is wired. | P2 | T |
| SYS-08 | Modules shall attach magnetically on all four sides and be hot-pluggable; side modules shall chain left and right; the interface spec shall be public. | P3 | T |
| SYS-09 | The top module shall provide three force-feedback knobs whose behaviour switches per application. | P4 | D |
| SYS-10 | Per-key RGB: on with USB power, off on battery by default. No dedicated status LEDs; the keys are the indicators. | P1 | T |
| SYS-11 | Supported hosts: macOS, Windows, iOS (Bluetooth). Each connection remembers its own keymap / OS mode. | P2 | T |
| SYS-12 | Firmware in Rust; configurable without reflashing (Vial in P1–P2, KO app from P5). | P1 | D |
| SYS-13 | All boards and cases shall be orderable at JLCPCB/PCBWay (PCB, assembly, CNC) and repairable by hand. | P1 | I |
| SYS-14 | Battery and all external contacts shall be protected: LiPo protection, current limits, ESD protection. | P1 | T |
| SYS-15 | Total prototyping spend shall stay around CHF 2,000. | all | A |
| SYS-16 | License: GPL-3.0-or-later (software), CERN-OHL-S-2.0 (hardware), CC-BY-4.0 + MIT/Apache-2.0 (module spec and its reference code). | P0 | I |

---

## Roadmap

Phases overlap where dependencies allow (e.g. the app can start once the host protocol exists).
Each phase ends with its exit criteria verified and documented.

| Phase | Goal | Main deliverables | Exit criteria |
|---|---|---|---|
| **P0** Foundations | Ready to build | Repo + contracts (this), pinned toolchains, CI skeleton; nRF52840 dev kit, debug probe, Nordic PPK2, 3–4 candidate knob motors bought; RMK + Vial running on the dev kit with a hand-wired test matrix; first motor feel comparison on the owner's existing test rig | Firmware flashes, logs and types on the dev kit; motor shortlist of 2 |
| **P1** Core keyboard rev A | A usable keyboard | Core board rev A; generated 75 % ISO-CH switch board rev A; 3D-printed case; USB + Bluetooth + Vial; battery and charging; power measured | Daily-usable wired/Bluetooth keyboard; SYS-03 projected from measurements |
| **P2** Wireless and ports | Gaming-grade wireless | Dongle hardware and firmware; encrypted 1 kHz 2.4 GHz link; automatic switching; per-connection keymaps; gaming mode, SOCD; hub and identical ports; core board rev B | SYS-03, SYS-04, SYS-05, SYS-07 verified |
| **P3** Module system | Modules work | Module interface implemented (detection, power, bus, chaining, USB lane); 1×6 macro module; numpad | 3 macro modules + numpad hot-plugged 100× on either side without a fault |
| **P4** Knob module | Haptics | Top module with 3 knobs; Rust FOC firmware; smooth, detent and music profiles; battery modes | Feel matches the owner's reference profiles; power targets met |
| **P5** KO app | Own software | Tauri app replaces Vial: keymaps, macros, lighting, per-app profiles, knob profiles, music knob, notices, updates | All P5 `APP` requirements pass on macOS and Windows |
| **P6** Final design | The premium build | Owner-refined Fusion design → CNC aluminium; acoustics; final board revisions | SYS-02 and finish approved by the owner |
| **P7** Generator | The platform | Local program producing complete packages from 40 % to full size, ANSI/ISO | 3 sizes generated, DRC-clean; one ordered and built |

**Backlog (later, not scheduled):** 8 kHz core board (nRF54LM20), Hall-effect switch board, MX top case,
wireless firmware updates, screen-edge switching between Mac and PC, haptic actuator in the keyboard body,
touch strip / motorized slider modules, screen modules over the USB lane, front power module,
horizontal haptic roller, generator website, Wi-Fi storage module.

---

## Repository layout (target)

```
docs/          contracts/, decisions.md        ← the source of truth
hardware/      core/, switchboard/ (generated), dongle/, modules/<name>/
firmware/      Rust workspace: keyboard, dongle, knob-module, side-module,
               ko-protocol, ko-module-bus (shared crates)
app/           Tauri desktop app (macOS, Windows)
generator/     Python: layout → PCB + plate + case package
mechanical/    build123d case skeleton, STEP exports, Fusion handover
tools/         test rigs (latency, power), scripts
LICENSES/      full license texts
```

Only `docs/` and `LICENSES/` exist today; the rest is created in the phase that needs it.

## License

See [LICENSE.md](LICENSE.md). In short: the product is share-alike (GPL-3.0-or-later,
CERN-OHL-S-2.0), the module interface spec and its reference code are permissive
(CC-BY-4.0, MIT/Apache-2.0) so anyone can build KO modules.
