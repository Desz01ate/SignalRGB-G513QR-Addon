#!/usr/bin/env python3
import argparse
import fcntl
import json
import logging
import os
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MAGIC = b"SRASUS1"
DEFAULT_TOKEN = "fc28b2e1a9ad4c1798d47bfb"


def parse_args():
    parser = argparse.ArgumentParser(description="SignalRGB UDP bridge for ASUS asusd D-Bus Aura devices.")
    parser.add_argument("--host", default="0.0.0.0", help="UDP bind address")
    parser.add_argument("--port", type=int, default=21324, help="UDP bind port")
    parser.add_argument("--ddp-port", type=int, default=4048, help="DDP/WLED-compatible UDP bind port")
    parser.add_argument("--wled-http-port", type=int, default=8095, help="WLED-compatible HTTP status port")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="shared token expected after the SRASUS1 header")
    parser.add_argument("--min-interval", type=float, default=0.05, help="minimum seconds between hardware writes")
    parser.add_argument("--idle-timeout", type=float, default=5.0, help="seconds without valid RGB packets before forcing black; 0 disables")
    parser.add_argument("--change-threshold", type=int, default=18, help="minimum RGB channel delta before applying a new color")
    parser.add_argument("--smoothing", type=float, default=0.35, help="0 disables smoothing; higher values blend more slowly toward target colors")
    parser.add_argument("--hidraw", default="", help="path to hidraw device (e.g. /dev/hidraw3); auto-detected when omitted")
    parser.add_argument("--usb-product-id", default="1866", help="USB product ID for the ASUS N-KEY device")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def make_wled_handler(led_count):
    class WledHandler(BaseHTTPRequestHandler):
        server_version = "WLED/0.14"

        def log_message(self, fmt, *args):
            logging.debug("wled-http " + fmt, *args)

        def do_GET(self):
            if self.path.startswith("/json/info"):
                self.send_json({
                    "ver": "0.14.0",
                    "vid": 2310130,
                    "cn": "SignalRGB ASUS Bridge",
                    "name": "ASUS ROG Strix G513QR",
                    "leds": {
                        "count": led_count,
                        "rgbw": False,
                        "wv": 0,
                        "cct": False,
                        "pwr": led_count * 55,
                        "fps": 60,
                        "maxpwr": led_count * 55,
                        "maxseg": 1,
                        "lc": 1
                    },
                    "str": False,
                    "udpport": 21324,
                    "live": True,
                    "fxcount": 1,
                    "palcount": 1,
                    "arch": "python",
                    "core": "asusd",
                    "freeheap": 100000,
                    "uptime": int(time.monotonic()),
                    "opt": 127,
                    "brand": "WLED",
                    "product": "FOSS",
                    "mac": "020000000513",
                    "ip": self.server.server_address[0]
                })
            elif self.path.startswith("/json/state"):
                self.send_json({
                    "on": True,
                    "bri": 255,
                    "transition": 0,
                    "ps": -1,
                    "pl": -1,
                    "nl": {"on": False},
                    "udpn": {"send": False, "recv": True},
                    "lor": 0,
                    "mainseg": 0,
                    "seg": [{
                        "id": 0,
                        "start": 0,
                        "stop": led_count,
                        "len": led_count,
                        "grp": 1,
                        "spc": 0,
                        "on": True,
                        "bri": 255,
                        "col": [[0, 155, 222], [0, 0, 0], [0, 0, 0]],
                        "fx": 0,
                        "sx": 128,
                        "ix": 128,
                        "pal": 0,
                        "sel": True,
                        "rev": False,
                        "mi": False
                    }]
                })
            elif self.path.startswith("/json"):
                self.send_json({
                    "state": {"on": True, "bri": 255},
                    "info": {"name": "ASUS ROG Strix G513QR", "leds": {"count": led_count}, "brand": "WLED"}
                })
            else:
                body = b"SignalRGB ASUS WLED bridge\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length:
                self.rfile.read(length)
            self.send_json({"success": True})

        def send_json(self, value):
            body = json.dumps(value, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return WledHandler


def start_wled_http_server(host, port, led_count):
    server = ThreadingHTTPServer((host, port), make_wled_handler(led_count))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


KEYBOARD_LED_COUNT = 97
LIGHTBAR_LED_COUNT = 6
TOTAL_LED_COUNT = KEYBOARD_LED_COUNT + LIGHTBAR_LED_COUNT

# SignalRGB LED index → ASUS HID LED index.
# Packet = index // 16, slot = index % 16, byte offset = 9 + slot * 3.
# -1 = ghost key (no physical LED, used for canvas alignment).
KEY_LED_MAP = [
    # Row 0 (media): ghost, VolDn, VolUp, MicMute, FanCtrl, ROGKey, ghost×9
    -1, 2, 3, 4, 5, 6, -1, -1, -1, -1, -1, -1, -1, -1, -1,
    # Row 1: Esc, F1-F12, Del
    21, 23, 24, 25, 26, 28, 29, 30, 31, 33, 34, 35, 36, 37,
    # Row 2: `, 1-0, -, =, Bksp(×3), Home
    42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, (55, 56, 57), 58,
    # Row 3: Tab, Q-P, [, ], \, PgUp
    63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 79,
    # Row 4: Caps, A-L, ;, ', Enter(×3), PgDn
    84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, (97, 98, 99), 100,
    # Row 5: LShift, Z-/, RShift(×3), Up, End
    105, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, (118, 119, 120), 139, 121,
    # Row 6: LCtrl, Fn, LWin, LAlt, Space(×4), RAlt, RCtrl, Left, Down, Right, PrtSc
    126, 127, 128, 129, (130, 131, 132, 133), 135, 137, 159, 160, 161, 142,
]


class HidRawAuraController:
    REPORT_SIZE = 64
    HIDIOCSFEATURE = 0xC0004806 | ((REPORT_SIZE & 0x3FFF) << 16)

    def __init__(self, hidraw_path, product_id):
        self._path = hidraw_path or self._detect_hidraw(product_id)
        self._fd = os.open(self._path, os.O_RDWR)
        self._set_feature(bytearray([0x5d, 0xbc]))

    @staticmethod
    def _detect_hidraw(product_id):
        pid = product_id.upper().lstrip("0")
        for entry in sorted(os.listdir("/sys/class/hidraw")):
            try:
                with open(f"/sys/class/hidraw/{entry}/device/uevent") as f:
                    content = f.read().upper()
                for line in content.splitlines():
                    if line.startswith("HID_ID="):
                        fields = line.split(":")
                        if len(fields) >= 3 and fields[2].lstrip("0") == pid:
                            path = f"/dev/{entry}"
                            logging.info("auto-detected hidraw device: %s", path)
                            return path
            except OSError:
                continue
        raise RuntimeError(f"could not find hidraw device for USB product {product_id}")

    def _set_feature(self, data):
        buf = bytearray(self.REPORT_SIZE)
        buf[:len(data)] = data
        fcntl.ioctl(self._fd, self.HIDIOCSFEATURE, buf)

    def set_static_rgb(self, rgb):
        r, g, b = rgb
        for count in range(11):
            pkt = bytearray(self.REPORT_SIZE)
            pkt[0] = 0x5d
            pkt[1] = 0xbc
            pkt[3] = 0x01
            pkt[4] = 0x01
            pkt[5] = 0x01
            pkt[6] = count << 4
            pkt[7] = 0x08 if count == 10 else 0x10
            for off in range(9, 58, 3):
                pkt[off] = r
                pkt[off + 1] = g
                pkt[off + 2] = b
            self._set_feature(pkt)
        lightbar = bytearray(self.REPORT_SIZE)
        lightbar[0] = 0x5d
        lightbar[1] = 0xbc
        lightbar[3] = 0x01
        lightbar[4] = 0x04
        for off in range(9, 60, 3):
            lightbar[off] = r
            lightbar[off + 1] = g
            lightbar[off + 2] = b
        self._set_feature(lightbar)

    def set_per_key_rgb(self, colors):
        packets = []
        for row in range(11):
            pkt = bytearray(self.REPORT_SIZE)
            pkt[0] = 0x5d
            pkt[1] = 0xbc
            pkt[3] = 0x01
            pkt[4] = 0x01
            pkt[5] = 0x01
            pkt[6] = row << 4
            pkt[7] = 0x08 if row == 10 else 0x10
            packets.append(pkt)

        num_keys = min(len(colors), len(KEY_LED_MAP))
        for i in range(num_keys):
            entry = KEY_LED_MAP[i]
            if isinstance(entry, tuple):
                indices = entry
            elif entry < 0:
                continue
            else:
                indices = (entry,)
            r, g, b = colors[i]
            for led_idx in indices:
                row = led_idx >> 4
                slot = led_idx & 0x0f
                if row >= 11:
                    continue
                offset = 9 + slot * 3
                packets[row][offset] = r
                packets[row][offset + 1] = g
                packets[row][offset + 2] = b

        for pkt in packets:
            self._set_feature(pkt)

        lightbar = bytearray(self.REPORT_SIZE)
        lightbar[0] = 0x5d
        lightbar[1] = 0xbc
        lightbar[3] = 0x01
        lightbar[4] = 0x04
        for i in range(LIGHTBAR_LED_COUNT):
            color_idx = KEYBOARD_LED_COUNT + i
            if color_idx < len(colors):
                r, g, b = colors[color_idx]
            else:
                r = g = b = 0
            offset = 9 + i * 3
            lightbar[offset] = r
            lightbar[offset + 1] = g
            lightbar[offset + 2] = b
        self._set_feature(lightbar)

    def close(self):
        if self._fd >= 0:
            try:
                self.set_static_rgb((0, 0, 0))
            except OSError:
                pass
            os.close(self._fd)
            self._fd = -1


def hex_to_rgb(hex_color):
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def rgb_to_hex(rgb):
    return f"{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def max_channel_delta(left, right):
    if left is None or right is None:
        return 255
    return max(abs(left[0] - right[0]), abs(left[1] - right[1]), abs(left[2] - right[2]))


def blend_rgb(current, target, smoothing):
    if current is None or smoothing <= 0:
        return target
    alpha = max(0.01, min(1.0, 1.0 - smoothing))
    return (
        round(current[0] + (target[0] - current[0]) * alpha),
        round(current[1] + (target[1] - current[1]) * alpha),
        round(current[2] + (target[2] - current[2]) * alpha),
    )


def parse_signalrgb_packet(packet, prefix):
    if not packet.startswith(prefix) or len(packet) < len(prefix) + 3:
        return None

    red, green, blue = packet[len(prefix):len(prefix) + 3]
    return f"{red:02x}{green:02x}{blue:02x}"


def parse_ddp_packet(packet):
    if len(packet) < 13:
        return None

    data_type = packet[2]
    if data_type != 0x0A:
        return None

    payload_length = int.from_bytes(packet[8:10], "big")
    payload = packet[10:10 + payload_length] if payload_length else packet[10:]
    usable = len(payload) - (len(payload) % 3)
    if usable < 3:
        return None

    colors = []
    for index in range(0, usable, 3):
        colors.append((payload[index], payload[index + 1], payload[index + 2]))
    return colors


def make_udp_socket(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    return sock


def main():
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    token = args.token.encode("ascii")
    prefix = MAGIC + token
    last_color = None
    last_rgb = None
    last_write = 0.0
    last_packet_time = time.monotonic()
    idle_timeout = max(0.0, args.idle_timeout)
    is_idle = False
    black_rgb = (0, 0, 0)
    aura = HidRawAuraController(args.hidraw, args.usb_product_id)

    sock = make_udp_socket(args.host, args.port)
    ddp_sock = make_udp_socket(args.host, args.ddp_port)
    http_server = start_wled_http_server(args.host, args.wled_http_port, TOTAL_LED_COUNT)
    logging.info("listening on udp://%s:%s", args.host, args.port)
    logging.info("listening for DDP/WLED realtime on udp://%s:%s", args.host, args.ddp_port)
    logging.info("serving WLED-compatible HTTP on http://%s:%s", args.host, args.wled_http_port)
    logging.info("aura backend: hidraw=%s (direct, no dbus)", aura._path)
    logging.info("per-key mode: %d keyboard + %d lightbar LEDs", KEYBOARD_LED_COUNT, LIGHTBAR_LED_COUNT)

    try:
        while True:
            timeout = min(idle_timeout, 0.5) if idle_timeout > 0 else None
            readable, _, _ = select.select([sock, ddp_sock], [], [], timeout)
            now = time.monotonic()

            if not readable:
                if idle_timeout > 0 and now - last_packet_time >= idle_timeout and not is_idle:
                    if now - last_write >= args.min_interval:
                        try:
                            aura.set_static_rgb(black_rgb)
                            is_idle = True
                            last_write = now
                            logging.info("idle timeout %.2fs reached, forced black", idle_timeout)
                        except Exception as exc:
                            logging.warning("aura apply failed for idle: %s", str(exc))
                continue

            active_sock = readable[0]
            packet, address = active_sock.recvfrom(65535)

            if active_sock is sock:
                hex_color = parse_signalrgb_packet(packet, prefix)
                if hex_color is None:
                    logging.debug("ignored packet from %s", address)
                    continue
                last_packet_time = now
                is_idle = False
                target_rgb = hex_to_rgb(hex_color)
                if max_channel_delta(last_rgb, target_rgb) < args.change_threshold:
                    continue
                if now - last_write < args.min_interval:
                    continue
                output_rgb = blend_rgb(last_rgb, target_rgb, args.smoothing)
                output_hex = rgb_to_hex(output_rgb)
                if output_hex == last_color:
                    continue
                try:
                    aura.set_static_rgb(output_rgb)
                    last_color = output_hex
                    last_rgb = output_rgb
                    last_write = now
                    logging.info("set %s target %s from %s via srgb", output_hex, hex_color, address)
                except Exception as exc:
                    logging.warning("aura apply failed for %s: %s", output_hex, str(exc))
            else:
                colors = parse_ddp_packet(packet)
                if colors is None:
                    logging.debug("ignored packet from %s", address)
                    continue
                last_packet_time = now
                is_idle = False
                if now - last_write < args.min_interval:
                    continue
                try:
                    aura.set_per_key_rgb(colors)
                    last_write = now
                    last_color = None
                    last_rgb = None
                    logging.info("set per-key %d colors from %s via ddp", len(colors), address)
                except Exception as exc:
                    logging.warning("aura per-key apply failed: %s", str(exc))
    finally:
        aura.close()


if __name__ == "__main__":
    main()
