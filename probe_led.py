#!/usr/bin/env python3
"""Probe HID LED indices to find the correct one for a specific key.

Lights up one LED at a time (white) while keeping everything else black.
Press Enter to advance to the next index, or type an index to jump to it.
"""
import fcntl
import os
import sys
import time


REPORT_SIZE = 64
HIDIOCSFEATURE = 0xC0004806 | ((REPORT_SIZE & 0x3FFF) << 16)


def detect_hidraw(product_id="1866"):
    pid = product_id.upper().lstrip("0")
    for entry in sorted(os.listdir("/sys/class/hidraw")):
        try:
            with open(f"/sys/class/hidraw/{entry}/device/uevent") as f:
                content = f.read().upper()
            for line in content.splitlines():
                if line.startswith("HID_ID="):
                    fields = line.split(":")
                    if len(fields) >= 3 and fields[2].lstrip("0") == pid:
                        return f"/dev/{entry}"
        except OSError:
            continue
    raise RuntimeError(f"could not find hidraw device for USB product {product_id}")


def set_feature(fd, data):
    buf = bytearray(REPORT_SIZE)
    buf[:len(data)] = data
    fcntl.ioctl(fd, HIDIOCSFEATURE, buf)


def set_single_led(fd, led_idx, r, g, b):
    for row in range(11):
        pkt = bytearray(REPORT_SIZE)
        pkt[0] = 0x5d
        pkt[1] = 0xbc
        pkt[3] = 0x01
        pkt[4] = 0x01
        pkt[5] = 0x01
        pkt[6] = row << 4
        pkt[7] = 0x08 if row == 10 else 0x10

        target_row = led_idx >> 4
        target_slot = led_idx & 0x0f
        if row == target_row:
            off = 9 + target_slot * 3
            pkt[off] = r
            pkt[off + 1] = g
            pkt[off + 2] = b

        set_feature(fd, pkt)

    lightbar = bytearray(REPORT_SIZE)
    lightbar[0] = 0x5d
    lightbar[1] = 0xbc
    lightbar[3] = 0x01
    lightbar[4] = 0x04
    set_feature(fd, lightbar)


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 177

    path = detect_hidraw()
    print(f"using {path}")
    fd = os.open(path, os.O_RDWR)
    set_feature(fd, bytearray([0x5d, 0xbc]))

    idx = start
    try:
        while idx <= end:
            row = idx >> 4
            slot = idx & 0x0f
            print(f"\r  LED {idx:3d}  (packet {row}, slot {slot:2d}, offset {9 + slot * 3})  "
                  f"[Enter=next, number=jump, q=quit] ", end="", flush=True)
            set_single_led(fd, idx, 255, 255, 255)
            resp = input().strip()
            if resp.lower() == "q":
                break
            elif resp.isdigit():
                idx = int(resp)
            else:
                idx += 1
    finally:
        set_single_led(fd, 0, 0, 0, 0)
        os.close(fd)


if __name__ == "__main__":
    main()
