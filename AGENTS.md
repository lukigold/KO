# Working on KO — rules for every contributor

These rules apply to AI agents and humans alike. Read them once before your first change.

## 1. Read order

1. [README.md](README.md) – goal, architecture, top-level requirements, roadmap.
2. This file.
3. The contract(s) in [`docs/contracts/`](docs/contracts/) for the subsystem you touch.
4. [docs/decisions.md](docs/decisions.md) – before you question a decision, read why it was made.

If your task touches an interface, also read the contract that **owns** that interface
(each contract says which interfaces it owns).

## 2. Source of truth

- **Contracts define what must be true.** Code, schematics and CAD implement contracts.
  If an implementation and a contract disagree, the contract wins until it is changed.
- **Interfaces are owned by exactly one contract.** Others reference it; they never redefine it.
- **Design notes** in [`docs/design/`](docs/design/) explain *how* a contract is implemented (parts, circuits,
  budgets). They never override a contract; if they disagree, fix one of them in the same change.
- **Do not invent requirements.** A feature, part or dependency that no requirement asks for goes
  into the backlog (README) or an open item (decisions.md), not into the design.
- **When something is unclear, do not guess.** Add an `OPEN-xx` item to decisions.md and ask the owner.

## 3. Changing a contract

1. Edit the contract.
2. Add a decision entry in decisions.md: what changed, why, which subsystems are affected.
3. Changes that alter an **interface** or a **SYS requirement** need the owner's approval before
   any implementation depends on them.
4. Requirement IDs are permanent. Never renumber or reuse an ID. To retire one, strike it through
   and write "superseded by X".

## 4. Requirement format

```
| ID | Requirement | Phase | Verify |
```
- Wording: "shall" = mandatory, "should" = goal, "may" = allowed.
- Phase: `P0`–`P7` (see README roadmap) or `Later` (backlog).
- Verify: **T** test · **M** measurement · **I** inspection · **A** analysis · **D** demonstration.
- Interfaces are written as **Guarantees** (what the provider promises), **Preconditions**
  (what the consumer must ensure) and **Invariants** (what is always true).

## 5. Task workflow

1. Start from requirement IDs. If a task has none, find or propose them first.
2. Check every interface you touch against its owning contract.
3. Implement.
4. Verify against the Definition of Done below.
5. Commit with the requirement IDs in the message, e.g. `CORE-024: add reverse-current blocking on VBUS`.
6. Record verification results (measurements, logs, photos) in `docs/verification/<phase>.md`.

## 6. Definition of Done

| Area | Done means |
|---|---|
| **Hardware** | Generated or edited by script where practical · `kicad-cli sch erc` and `kicad-cli pcb drc` clean (waivers written down) · BOM with LCSC part numbers, stock checked, second source or note per part · JLCPCB fabrication + assembly files generated · 3D render and 1:1 PDF for the owner's fit check · review checklist answered (power paths, ESD, test points, keep-outs, current limits) |
| **Firmware** | `cargo fmt` · `cargo clippy -- -D warnings` · host unit tests pass for all hardware-independent crates · all targets build · hardware test procedure written; when tested on hardware, defmt logs attached |
| **App** | Builds and passes tests on macOS and Windows CI · protocol compatibility tests pass against the current firmware protocol version |
| **Mechanical** | Geometry and parameters in code (`mechanical/`) · STEP exported · functional features unchanged unless the contract was changed |
| **Generator** | Example packages pass ERC/DRC · output is deterministic (same input → same files) |
| **Docs** | Contract and decisions updated in the same change as the implementation |

## 7. Working with hardware you cannot see

- Agents cannot touch hardware. The owner can flash, measure, photograph and assemble.
  Write test procedures the owner can follow: what to connect, what to expect, what counts as pass or fail.
- In firmware phases the owner runs Claude Code on their own computer with the boards attached.
  Then agents flash with `probe-rs` and read `defmt` logs directly.
- **Never** erase or overwrite a bootloader, UICR or option bytes, or enable read-out protection,
  without the owner's explicit approval.
- **LiPo safety:** never bypass battery protection; first charging tests are supervised and use a
  current-limited bench supply; never design a charger without temperature monitoring.

## 8. Engineering rules

- Follow chip makers' reference designs and proven open designs; cite them in the design notes.
- Prefer JLCPCB Basic/Extended parts that are in stock. Avoid BGA and parts smaller than 0402.
- Keep the core board simple: pre-certified radio module, 4 layers, generous spacing.
- Every power-hungry block must be switchable and **off by default on battery**.
- No status LEDs, and no feature that needs one.
- Units: SI, millimetres. Module positions are measured from the **front edge** of the keyboard.
- Hardware-independent logic (keymap engine, tap-hold, combos, SOCD, connection switching,
  module bus protocol) lives in crates that compile and are tested on the host.

## 9. Conventions

- Language: English everywhere (code, comments, docs, commits).
- Names: project **KO**, repository `KO`, Rust crates prefixed `ko-`.
- Commits: `<ID or area>: <imperative summary>`, e.g. `FW-006: add SOCD last-input mode`.
- Branches: `p<phase>/<topic>`, e.g. `p1/core-board-rev-a`.
- Hardware revisions: `rev-A`, `rev-B` … tagged in git as `<board>-rev-A`.

## 10. Toolchain (versions get pinned in P0)

| Area | Tools |
|---|---|
| PCB | KiCad 9 or newer (`kicad-cli`), KiKit, JLCPCB fabrication plugin |
| Firmware | Rust stable, Embassy, RMK, `probe-rs`, `defmt` |
| Mechanical | Python 3.12+, build123d; Fusion for the owner's surface refinement |
| Generator | Python 3.12+, KiCad Python API / file generation, build123d |
| App | Tauri 2 (Rust core + web UI) |
| Measurement | Nordic PPK2 (power), logic analyzer, oscilloscope (optional) |
