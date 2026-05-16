# Lightbar Flicker Investigation — ASUS ROG Strix G513QR

## Problem

The SignalRGB UDP bridge (`signalrgb-asus-bridge.py`) receives RGB color data from a desktop over the network and applies it to the laptop's keyboard and lightbar via the `asusd` D-Bus service. The keyboard was smooth, but the lightbar flickered visibly on every color update.

## Root Cause

Two compounding issues:

### 1. Output reports vs feature reports

The bridge used `busctl set-property` to write `LedModeData` via D-Bus. Internally, `asusd` writes to `/dev/hidraw3` using `file.write_all()`, which sends **USB output reports** (interrupt endpoint). The ASUS N-KEY device (0b05:1866) processes output reports asynchronously — the lightbar controller has a visible off-to-on transition between state changes, while the keyboard controller double-buffers and hides it.

The fix: `ioctl(HIDIOCSFEATURE)` sends **USB feature reports** (control endpoint), which the device processes atomically. This is what [g-helper-linux](https://github.com/utajum/g-helper-linux) uses — zero flicker.

### 2. Built-in mode protocol overhead

Each `LedModeData` D-Bus property write triggered `asusd` to:

1. Send a mode packet (`0x5d 0xb3`) — 17 bytes
2. Send a SET packet (`0x5d 0xb5`) — 17 bytes
3. Send an APPLY packet (`0x5d 0xb4`) — 17 bytes
4. Write brightness to `/sys/class/leds/asus::kbd_backlight/brightness`
5. Write config JSON to disk

Steps 2-5 are unnecessary for real-time RGB control. The SET packet specifically causes the lightbar firmware to reinitialize, and APPLY persists to flash (not needed for ephemeral colors). The `busctl` subprocess added ~50-75ms overhead per update on top of that.

### 3. Per-key mode can't address the lightbar

The G513QR is classified as `PerKey` in asusd's `aura_support.ron`. Per-key packets (`0x5d 0xbc`, groups `0x00`-`0xa0`) control individual keyboard keys but the lightbar is not mapped in this address space — confirmed by probing all 11 per-key groups.

However, the **4-zone mode** (`0x5d 0xbc` with byte[4]=`0x04`) does control the lightbar. Sending both per-key packets (keyboard) and a 4-zone packet (lightbar) in sequence via feature reports gives full coverage with zero flicker.

## Fix

Replaced the `AsusdAuraController` (busctl subprocess, D-Bus, asusd) with `HidRawAuraController` that writes directly to `/dev/hidraw3` via `ioctl(HIDIOCSFEATURE)`:

| | Before | After |
|---|---|---|
| Transport | `busctl` subprocess per update | `ioctl()` on persistent fd |
| Protocol | `0xb3` + SET + APPLY (3 packets) | Per-key + 4-zone (12 packets, no SET/APPLY) |
| Report type | Output report (`write()`) | Feature report (`HIDIOCSFEATURE`) |
| Side effects | Brightness sysfs write, config disk write | None |
| Latency | ~50-75ms (subprocess + D-Bus) | ~2ms (direct ioctl) |
| Keyboard | Smooth | Smooth |
| Lightbar | Flickering | Smooth |

### Protocol details

Each `set_static_rgb()` call sends 12 feature reports (64 bytes each):

**Per-key packets (keyboard, rows 0-10):**
```
[0x5d, 0xbc, 0x00, 0x01, 0x01, 0x01, group, flag, 0x00, R,G,B, R,G,B, ...]
```
- `group` = row index << 4 (`0x00` through `0xa0`)
- `flag` = `0x10` for rows 0-9, `0x08` for the last row (10)
- RGB data fills offsets 9-57 (16 triplets per packet)

**4-zone packet (lightbar):**
```
[0x5d, 0xbc, 0x00, 0x01, 0x04, 0x00, 0x00, 0x00, 0x00, R,G,B, R,G,B, ...]
```
- Byte[4] = `0x04` distinguishes this from per-key packets
- RGB data fills offsets 9-59 (covers all 6 lightbar zones)

**Initialization (once on startup):**
```
[0x5d, 0xbc, 0x00, ..., 0x00]  (64 bytes, via HIDIOCSFEATURE)
```

## Investigation timeline

1. Examined asusd source (`rog-aura`, `asusd/src/aura_laptop/`) — traced `set_led_mode_data` to `write_effect_and_apply` which sends 3 HID packets + brightness + config write
2. Measured busctl overhead at 44-76ms per call
3. Tested direct hidraw `write()` — keyboard smooth, lightbar still flickered
4. Isolated the SET packet (`0xb5`) as the flicker cause via A/B gradient tests
5. Tested per-key mode (`0xbc`) — keyboard works, lightbar not addressable (probed all 11 groups)
6. Checked g-helper-linux source — discovered `ioctl(HIDIOCSFEATURE)` and 4-zone direct mode
7. Tested 4-zone via feature reports — lightbar smooth, zero flicker, but keyboard dark
8. Combined per-key + 4-zone via feature reports — both smooth, zero flicker
