# Contract: Wireless and connection switching

**ID prefix:** `RF` · **Status:** draft v0.1 · **First phase:** P1 (Bluetooth), P2 (2.4 GHz) · **License:** GPL-3.0-or-later / CERN-OHL-S-2.0
**Owns:** Bluetooth behaviour, the KO 2.4 GHz link, the dongle, the output-selection rules.

## Purpose

Three ways to reach a computer: USB cable, the KO 2.4 GHz link through a USB-C dongle (gaming,
Windows), and Bluetooth (Mac, iPhone, iPad). The keyboard picks the right one by itself.

## 1. Output selection (the core contract)

Rules, evaluated on every connection event, in this order:

| # | Rule |
|---|---|
| R1 | A USB **data** host is present (enumerated and configured; a charger alone does not count) → output to USB. |
| R2 | Otherwise, if a Bluetooth host was **selected** more recently than the dongle became active → output to that host. "Selected" means the host connected or woke up (e.g. the Mac connects to the keyboard), or the user picked it with the key combo. |
| R3 | Otherwise, if the dongle link is up and its computer is awake (not in USB suspend) → output to 2.4 GHz. |
| R4 | Otherwise → the most recently used Bluetooth host. |

- **Manual override:** a key combo selects an output directly. It holds until the next connect/disconnect event.
- **Later:** screen-edge switching through the KO app on both computers ([host-app.md](host-app.md)).
- **Concurrent links:** the keyboard keeps the dongle link and one Bluetooth link alive at the same time
  (radio time-sharing), so switching between them does not need a reconnect.
- **Per-connection profile:** each slot (USB, dongle, BT1–BT3) stores an OS mode (macOS / Windows / iOS)
  that selects keymap and modifier mapping, including the fix for macOS swapping § and < on ISO keyboards.

**Invariants**
- Keystrokes go to exactly one output at a time.
- A switch never leaves a key "stuck": all keys are released on the old output before the new one gets reports.

## 2. KO 2.4 GHz link

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| RF-010 | The link shall be a proprietary protocol on the Nordic radio (Enhanced ShockBurst style, 2 Mbit/s PHY). The keyboard transmits on change plus heartbeat; the USB-powered dongle listens continuously. | P2 | I |
| RF-011 | Radio latency shall be ≤ 1 ms (p99), and packet loss ≤ 0.1 %, at 2 m with the dongle on a PC's rear port and the keyboard in its final case. | P2 | M |
| RF-012 | Every packet shall be encrypted and authenticated (AES-CCM or equivalent AEAD) with per-pairing keys and replay protection. No plaintext keystrokes on air. | P2 | A/T |
| RF-013 | Pairing shall need no tools: via a key combo within 30 s after plugging in the dongle, or via the KO app while both are on USB. | P2 | T |
| RF-014 | The link shall avoid busy channels (channel selection / hopping) and recover from interference within 100 ms. | P2 | T |
| RF-015 | Host → keyboard data (lock LEDs, app messages, knob profiles) shall travel in acknowledgement payloads with ≥ 8 kB/s throughput. | P2 | M |
| RF-016 | 2.4 GHz mode shall stay within the basic-mode power budget behind SYS-03. | P2 | M |
| RF-017 | Report rate shall be 1,000 Hz end-to-end (keyboard → dongle → USB). | P2 | M |

## 3. Dongle

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| RF-030 | The dongle shall be a small USB-C plug device; a bought USB-C → USB-A adapter covers USB-A computers. No storage slot in the keyboard. | P2 | I |
| RF-031 | The dongle shall use an nRF52840- or nRF52820-class chip with Full-Speed USB, presenting a composite HID device: keyboard (NKRO), consumer control, system control, vendor interface for the KO app. | P2 | T |
| RF-032 | The dongle shall report its computer's USB suspend state to the keyboard (rule R3). | P2 | T |
| RF-033 | Dongle firmware shall be updatable by UF2 drag-and-drop and through the KO app. | P2 | T |
| RF-034 | The dongle firmware shall be Rust, sharing link and protocol crates with the keyboard. | P2 | I |

## 4. Bluetooth

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| RF-040 | The keyboard shall provide Bluetooth LE HID that works with macOS and iOS (Windows as fallback), with up to 3 bonded hosts. | P1 | T |
| RF-041 | It shall expose the Battery Service, so macOS and iOS show the battery level natively. | P1 | T |
| RF-042 | It shall request the shortest connection interval the host allows (typically 7.5–15 ms). Latency is best effort. | P1 | M |
| RF-043 | Pairing and slot selection shall be done with key combos; each bond stores its OS mode. | P1 | T |

## 5. Radio hardware and RF path

- Pre-certified nRF52840 module with integrated antenna on the core board ([core-board.md](core-board.md)).
- The aluminium case blocks 2.4 GHz and there is **no bottom window**. The RF path has to be solved
  another way (OPEN-06, [mechanical.md](mechanical.md)) and **must pass RF-011 in the final case**.
- Fallback for difficult desks: a short USB-C extension cable for the dongle.

## Reference

RMK (v0.9.0) includes a Bluetooth-based dongle mode and nRF54L15/nRF54LM20 support. It is a starting
point for the dongle architecture; the 1 kHz encrypted 2.4 GHz link is KO's own work.
