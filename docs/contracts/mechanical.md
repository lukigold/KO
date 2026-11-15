# Contract: Mechanical and industrial design

**ID prefix:** `MECH` · **Status:** draft v0.1 · **First phase:** P1 (printed prototypes), P6 (final) · **License:** CERN-OHL-S-2.0
**Owns:** case geometry, heights, materials, finish, acoustics, the CAD workflow.

## Design intent

Minimal, warm and precise, in the spirit of Apple, Teenage Engineering, Nothing and the Nomad [E]:
honest aluminium, nothing that blinks, no visible fasteners where avoidable. Slim enough for the
main keyboard to travel; modules can be bigger, but the default look is clean and low.

## Stack-up (estimate, Choc build)

| Layer (bottom → top) | mm |
|---|---|
| Case floor | 1.2–1.5 |
| Battery (front: none, back: in the space the tilt creates, where possible) | 0–3.0 |
| Socket clearance below PCB | ~2.0 |
| Switch board | 1.6 (1.2 if needed) |
| PCB top → plate top (Choc) | ~2.2 |
| Switch + keycap above plate | ~8 |
| **Total including keycaps** | **≈ 16–18 front, ≈ 20–22 back at ~2° tilt** |

MX switches need ~5 mm more below the plate and ~8 mm more above it. They use the same switch board
but need a taller top case (later variant). Exact numbers: OPEN-11.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| MECH-001 | Height including keycaps (Choc build) shall be ≤ 18 mm front and ≤ 22 mm back; goal 20 mm at the back. | P6 | M |
| MECH-002 | The case shall have a built-in tilt of about 2° (barely noticeable), no fold-out feet, and rubber feet. | P1 | I |
| MECH-003 | The battery sits under the switch board; the core board sits at the back edge; both USB-C ports exit through the back edge. | P1 | I |
| MECH-004 | The MX variant shall reuse the switch board with a taller top case and plate. | Later | I |
| MECH-010 | Final case: CNC-machined aluminium (top and bottom), anodized **dark creamy warm silver**. Physical anodizing samples shall be approved before the final order. | P6 | I |
| MECH-011 | No transparent window, no visible status LEDs, no fold-out parts. | P1 | I |
| MECH-012 | The case shall provide a 2.4 GHz RF path to the antenna without a bottom window (e.g. a colour-matched polymer section or plate zone near the antenna) and pass RF-011 in the final case (OPEN-06). | P1/P6 | M |
| MECH-013 | Keycaps: bought, clean look with a metallic appearance, Choc-compatible for v1. Metal caps may block RGB and add weight (OPEN-08). | P1 | I |
| MECH-014 | Knob caps: small (15–20 mm), flat, round discs sitting low in the module surface, protruding only enough to grip (target 3–6 mm), with an indicator line on top. Our own design, inspired by the OB-4's look. | P4 | I |
| MECH-020 | Sound and feel shall be slightly soft, muted and deep: soft-mounted plate (thin gaskets), internal damping foam, tuned stabilizers, no metallic ping or rattle. | P6 | D |
| MECH-030 | The seam between keyboard and modules shall be as tight as possible (target visible gap ≤ 0.5 mm). | P6 | M |
| MECH-031 | Module contacts shall be flush and minimal in an insulating insert; magnets hidden ([module-interface.md](module-interface.md)). | P3 | I |
| MECH-032 | The knob module shall bridge over the back-edge USB-C plugs with room for straight and angled plugs. | P4 | M |
| MECH-033 | All module features shall be positioned from the keyboard's front edge. | P3 | I |
| MECH-040 | The power switch shall be discreet but reachable without lifting the keyboard (position: OPEN-07). | P6 | D |
| MECH-041 | Space for a future haptic actuator in the body shall be reserved. | Later | I |

## CAD workflow (code ↔ Fusion contract)

1. **Code-CAD** (`mechanical/`, build123d) produces the **functional skeleton**: STEP + `parameters.yaml`
   with PCB outlines and positions, battery bay, port openings, module contact and magnet positions,
   RF zone, mounting and gasket points, keep-out zones.
2. **The owner** refines surfaces and proportions in Fusion. Functional features are named `KO_FUNC_*`
   and stay locked; moving one means changing this contract first.
3. Once the style is final, it is translated back into parameters (edge radii, chamfers, wall profile)
   so the generator ([generator.md](generator.md)) reproduces it for every size.

**Prototypes:** 1:1 PCB printouts for fit checks, FDM/resin printed cases in P1–P5, CNC only in P6.
