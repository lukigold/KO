# Contract: Host protocol and KO desktop app

**ID prefix:** `APP` · **Status:** draft v0.1 · **First phase:** P5 (protocol drafted in P2–P3) · **License:** GPL-3.0-or-later
**Owns:** the KO host protocol.

## Purpose

A small desktop app for macOS and Windows that configures the keyboard and adds the live features
firmware alone cannot do: per-app profiles, the music knob, on-screen notices. The keyboard must stay
fully usable without the app.

## Phasing

- **P1–P2:** keymaps through the existing **Vial** app. Every Vial feature is listed in the backlog
  (APP-020) so the KO app can replace it.
- **P5:** the KO app (Tauri 2: Rust core + web UI) replaces Vial.

## KO host protocol

- **Transport:** a vendor-defined HID interface over USB; relayed by the dongle over 2.4 GHz;
  a vendor GATT service over Bluetooth.
- **Versioned:** every session starts with a version and capability exchange. The app supports the
  current and the previous protocol version.
- **Message groups:** keymap/layers/macros/combos/tap-hold · lighting · knob profiles ·
  module list and descriptors · battery and status · notices · firmware update (USB only in v1) ·
  media state for the music knob · focus-change notifications for per-app profiles.
- **Invariants:** settings are stored on the keyboard; the app is never the only copy.
  An unknown message is answered with "unsupported", never a crash.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| APP-001 | The app shall be built with Tauri 2 and run on macOS and Windows. | P5 | T |
| APP-002 | Keymap and layer editor, including per-connection OS modes. | P5 | D |
| APP-003 | Macro, combo and tap-hold editors; gaming mode and SOCD settings. | P5 | D |
| APP-004 | Per-app profiles: detect the focused application (macOS: NSWorkspace; Windows: foreground window) and switch keyboard and knob profiles automatically. | P5 | T |
| APP-005 | Knob profile editor with live feel preview on the connected knob module. | P5 | D |
| APP-006 | Lighting editor: effects, brightness, battery behaviour, indicator configuration. | P5 | D |
| APP-007 | Battery and module status, including the physical order of chained modules. | P5 | T |
| APP-008 | On-screen notices: Caps Lock, low battery, connection switched, module attached. Small, unobtrusive, individually switchable. | P5 | D |
| APP-009 | Firmware updates for keyboard, dongle and modules over USB, safe against interruption. | P5 | T |
| APP-010 | Music knob: send playback state and position to the knob module. Windows: system media transport controls. macOS has no stable public now-playing API, so per-player integrations (Apple Music, Spotify) may be needed (OPEN-10). | P5 | T |
| APP-011 | The app shall run in the background (menu bar / tray), start at login, use ≤ 1 % CPU and ≤ 150 MB RAM when idle. | P5 | M |
| APP-012 | No internet connection, account or telemetry required. | P5 | I |
| APP-013 | All settings shall live on the keyboard; the app is only needed for per-app switching and live features. | P5 | T |
| APP-014 | Screen-edge switching: moving the mouse past the screen edge switches the keyboard between Mac and PC (both running the app). | Later | T |
| APP-020 | Backlog: every feature used through Vial in P1–P2 shall be available in the KO app before Vial support is dropped. | P5 | I |
