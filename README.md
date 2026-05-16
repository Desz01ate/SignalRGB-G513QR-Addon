# ASUS G513QR SignalRGB Bridge

SignalRGB network add-on for an ASUS ROG Strix G513QR laptop running the local `signalrgb-asus-bridge.py` daemon.

The add-on announces one fixed network controller:

- IP: `192.168.1.76`
- Realtime protocol: DDP over UDP `4048`
- LED model: one averaged color over 83 logical keyboard LEDs

Install in SignalRGB through **Settings > Add-ons > Add Git Repo** after uploading this repository to GitHub or GitLab.

Direct install URL format:

```text
signalrgb://addon/install?url=https://github.com/YOUR_USER/signalrgb-g513qr-plugin
```

If you use a different laptop IP, update `AsusG513QR.js` before uploading the repository.

## Laptop Daemon

The bridge now writes directly to `asusd` over D-Bus and does not call `asusctl` per color update.  
This is intended for the Arch Linux laptop host. This repo includes:

```text
signalrgb-asus-bridge.py
```

It listens for:

- DDP/WLED realtime packets on UDP `4048`
- a simple test protocol on UDP `21324`
- WLED-compatible HTTP metadata on the configured HTTP port

Prerequisites on the laptop:

```sh
sudo pacman -S asusctl
```

Run the bridge:

```sh
python3 ./signalrgb-asus-bridge.py --wled-http-port 50000
```

Default write filtering/timing:

```text
--min-interval 0.05
--change-threshold 18
--smoothing 0.35
```

If you still see visual stepping, lower `--change-threshold` and `--smoothing`.  
If updates are too aggressive, raise `--min-interval`.

If your Aura object path differs from auto-detect, pass it explicitly:

```sh
python3 ./signalrgb-asus-bridge.py --aura-object /xyz/ljones/aura/1866_3_3
```

## Arch Linux Systemd Install

Copy the daemon into place:

```sh
sudo install -Dm755 ./signalrgb-asus-bridge.py /usr/local/bin/signalrgb-asus-bridge.py
```

Create the system service:

```sh
sudo tee /etc/systemd/system/signalrgb-asus-bridge.service >/dev/null <<'EOF'
[Unit]
Description=SignalRGB ASUS Aura WLED/DDP bridge
After=network-online.target asusd.service
Wants=network-online.target
Requires=asusd.service

[Service]
Type=simple
User=YOUR_LINUX_USER
ExecStart=/usr/local/bin/signalrgb-asus-bridge.py --wled-http-port 50000 --min-interval 0.05 --change-threshold 18 --smoothing 0.35
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
curl http://127.0.0.1:50000/json/info
ss -lunp | grep -E '21324|4048'
```

Expected log line:

```text
INFO set b5309a target ff00ff from ('192.168.1.50', ...) via ddp
```

## Optional Port 80 Binding

If a SignalRGB WLED integration requires plain `http://192.168.1.76/json/info`, run the HTTP shim on port `80` instead. Keep `User=YOUR_LINUX_USER`, but grant the service permission to bind a privileged port:

```ini
[Service]
Type=simple
User=YOUR_LINUX_USER
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ExecStart=/usr/local/bin/signalrgb-asus-bridge.py --wled-http-port 80 --min-interval 0.35 --change-threshold 18 --smoothing 0.35
Restart=on-failure
RestartSec=2
```

Then:

```sh
sudo systemctl daemon-reload
sudo systemctl restart signalrgb-asus-bridge.service
curl http://127.0.0.1/json/info
```

## Desktop Tests

From the Windows desktop:

```powershell
Invoke-RestMethod http://192.168.1.76:50000/json/info
```

Minimal DDP test packet from PowerShell:

```powershell
$ip = "192.168.1.76"
$port = 4048
$color = "ff00ff"
$pixels = 83

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
