# ASUS G513QR SignalRGB Bridge

SignalRGB add-on and Linux bridge for an ASUS ROG Strix G513QR laptop.

This repository has two parts:

- `AsusG513QR.js`: the SignalRGB network add-on. It announces a fixed controller at `192.168.1.76` and streams DDP to UDP `4048`.
- `signalrgb-asus-bridge.py`: the laptop daemon. It receives DDP/WLED packets and writes them directly to the ASUS hidraw device.

## SignalRGB Add-on

The add-on currently exposes:

- Lighting modes: `Canvas` and `Forced`
- Forced color
- Shutdown color

Behavior:

- `Canvas` sends per-position colors from SignalRGB.
- `Forced` fills all 100 logical color positions with one solid color.
- Shutdown sends the configured shutdown color to every position.

The controller is hardcoded to `192.168.1.76` in `AsusG513QR.js`. If your laptop uses a different address, update that file before publishing the repo.

Install it in SignalRGB through **Settings > Add-ons > Add Git Repo** after pushing this repository to GitHub or GitLab.

Direct install URL format:

```text
signalrgb://addon/install?url=https://github.com/YOUR_USER/YOUR_REPO
```

## Laptop Bridge

The bridge does not use `asusctl` or D-Bus. It opens the ASUS N-KEY hidraw device directly and sends feature reports.

It listens on:

- UDP `4048` for DDP/WLED realtime packets from SignalRGB
- UDP `21324` for a small `SRASUS1` test protocol
- HTTP `8095` for WLED-compatible status endpoints

LED layout handled by the bridge:

- 97 keyboard LEDs
- 6 lightbar LEDs
- 103 physical outputs total

SignalRGB sends 100 logical color positions. Several keys map to multiple physical LEDs, which is why the bridge handles more outputs than the SignalRGB canvas exposes.

### Requirements

- Python 3
- Access to the ASUS hidraw device, usually `0b05:1866`

Running the bridge as `root` is the simplest option. If you want to run it as a regular user, add a udev rule that grants access to the ASUS hidraw node.

### Run It

```sh
python3 ./signalrgb-asus-bridge.py
```

Default runtime settings:

```text
--wled-http-port 8095
--min-interval 0.05
--change-threshold 18
--smoothing 0.35
--idle-timeout 5.0
```

Useful overrides:

```sh
python3 ./signalrgb-asus-bridge.py --hidraw /dev/hidraw3
python3 ./signalrgb-asus-bridge.py --usb-product-id 1866
python3 ./signalrgb-asus-bridge.py --wled-http-port 80
python3 ./signalrgb-asus-bridge.py --token YOUR_TOKEN
```

Use `--wled-http-port 80` only if you need plain `http://<ip>/json/info` for a WLED integration and can bind a privileged port.

## Systemd Install

Copy the daemon into place:

```sh
sudo install -Dm755 ./signalrgb-asus-bridge.py /usr/local/bin/signalrgb-asus-bridge.py
```

Create the service:

```sh
sudo tee /etc/systemd/system/signalrgb-asus-bridge.service >/dev/null <<'EOF'
[Unit]
Description=SignalRGB ASUS bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/signalrgb-asus-bridge.py
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
```

Enable it:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now signalrgb-asus-bridge.service
```

Check status:

```sh
sudo systemctl status signalrgb-asus-bridge.service --no-pager
curl http://127.0.0.1:8095/json/info
ss -lunp | grep -E '21324|4048'
```

Expected log lines include:

```text
INFO listening on udp://0.0.0.0:21324
INFO listening for DDP/WLED realtime on udp://0.0.0.0:4048
INFO serving WLED-compatible HTTP on http://0.0.0.0:8095
INFO aura backend: hidraw=/dev/hidraw3 (direct, no dbus)
INFO set ff00ff target ff00ff from ('192.168.1.50', ...) via srgb
INFO set per-key 100 colors from ('192.168.1.50', ...) via ddp
```

## Desktop Tests

From the Windows desktop:

```powershell
Invoke-RestMethod http://192.168.1.76:8095/json/info
```

Minimal DDP test packet from PowerShell:

```powershell
$ip = "192.168.1.76"
$port = 4048
$color = "ff00ff"
$pixels = 103

$payload = [System.Collections.Generic.List[byte]]::new()
for ($pixel = 0; $pixel -lt $pixels; $pixel++) {
    for ($i = 0; $i -lt 6; $i += 2) {
        $payload.Add([Convert]::ToByte($color.Substring($i, 2), 16))
    }
}

$packet = [System.Collections.Generic.List[byte]]::new()
$packet.Add(0x41)
$packet.Add(0x00)
$packet.Add(0x0A)
$packet.Add(0x01)
$packet.AddRange([byte[]](0x00, 0x00, 0x00, 0x00))
$packet.Add([byte](($payload.Count -shr 8) -band 0xff))
$packet.Add([byte]($payload.Count -band 0xff))
$packet.AddRange($payload)

$udp = [System.Net.Sockets.UdpClient]::new()
try {
    [void]$udp.Send($packet.ToArray(), $packet.Count, $ip, $port)
}
finally {
    $udp.Close()
}
```

## Notes

- The bridge auto-detects the ASUS hidraw device by USB product ID `1866` unless you pass `--hidraw` explicitly.
- The `SRASUS1` test protocol on UDP `21324` expects the configured token immediately after the magic prefix, followed by three RGB bytes.
- `probe_led.py` is a helper for identifying hidraw LED indices when you need to debug the hardware mapping.
