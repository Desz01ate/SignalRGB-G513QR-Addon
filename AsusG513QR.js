export function Name() { return "ASUS G513QR Bridge"; }
export function Version() { return "0.1.0"; }
export function Type() { return "network"; }
export function Publisher() { return "local"; }
export function Size() { return [15, 8]; }
export function DefaultPosition() { return [75, 70]; }
export function DefaultScale() { return 1.0; }
export function DeviceType() { return "keyboard"; }
export function ImageUrl() { return "https://assets.signalrgb.com/devices/default/keyboards/full-size-keyboard-render.png"; }

/* global
discovery:readonly
controller:readonly
LightingMode:readonly
forcedColor:readonly
shutdownColor:readonly
*/

export function ControllableParameters() {
	return [
		{property: "LightingMode", group: "lighting", label: "Lighting Mode", type: "combobox", values: ["Canvas", "Forced"], default: "Canvas"},
		{property: "forcedColor", group: "lighting", label: "Forced Color", min: "0", max: "360", type: "color", default: "#009bde"},
		{property: "shutdownColor", group: "lighting", label: "Shutdown Color", min: "0", max: "360", type: "color", default: "#000000"},
	];
}

const DDP_PORT = 4048;
const LED_NAMES = [
	"Ghost Key 1", "Volume Down", "Volume Up", "Microphone Mute", "Fan Control", "ROG Key", "Ghost Key 2", "Ghost Key 3", "Ghost Key 4", "Ghost Key 5", "Ghost Key 6", "Ghost Key 7", "Ghost Key 8", "Ghost Key 9", "Ghost Key 10",
	"Esc", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "Delete",
	"Back Quote", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Minus", "Equals", "Backspace", "Home",
	"Tab", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "Left Bracket", "Right Bracket", "Backslash", "Page Up",
	"Caps Lock", "A", "S", "D", "F", "G", "H", "J", "K", "L", "Semicolon", "Quote", "Enter", "Page Down",
	"Left Shift", "Z", "X", "C", "V", "B", "N", "M", "Comma", "Period", "Forward Slash", "Right Shift", "Up Arrow", "End",
	"Left Control", "Fn", "Left Windows", "Left Alt", "Space", "Right Alt", "Right Control", "Left Arrow", "Down Arrow", "Right Arrow", "Print Screen",
	"Lightbar 1", "Lightbar 2", "Lightbar 3", "Lightbar 4", "Lightbar 5", "Lightbar 6"
];

const LED_POSITIONS = [
	[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [6, 0], [7, 0], [8, 0], [9, 0], [10, 0], [11, 0], [12, 0], [13, 0], [14, 0],
	[0, 1], [1, 1], [2, 1], [3, 1], [4, 1], [5, 1], [6, 1], [7, 1], [8, 1], [9, 1], [10, 1], [11, 1], [12, 1], [14, 1],
	[0, 2], [1, 2], [2, 2], [3, 2], [4, 2], [5, 2], [6, 2], [7, 2], [8, 2], [9, 2], [10, 2], [11, 2], [12, 2], [13, 2], [14, 2],
	[0, 3], [1, 3], [2, 3], [3, 3], [4, 3], [5, 3], [6, 3], [7, 3], [8, 3], [9, 3], [10, 3], [11, 3], [12, 3], [13, 3], [14, 3],
	[0, 4], [1, 4], [2, 4], [3, 4], [4, 4], [5, 4], [6, 4], [7, 4], [8, 4], [9, 4], [10, 4], [11, 4], [13, 4], [14, 4],
	[0, 5], [2, 5], [3, 5], [4, 5], [5, 5], [6, 5], [7, 5], [8, 5], [9, 5], [10, 5], [11, 5], [12, 5], [13, 5], [14, 5],
	[0, 6], [1, 6], [2, 6], [3, 6], [5, 6], [9, 6], [10, 6], [11, 6], [12, 6], [13, 6], [14, 6],
	[1, 7], [4, 7], [6, 7], [9, 7], [11, 7], [13, 7]
];

let sequence = 0;

export function LedNames() { return LED_NAMES; }
export function LedPositions() { return LED_POSITIONS; }

export function Initialize() {
	device.setName(controller.name);
	device.setSize([15, 8]);
	device.setControllableLeds(LED_NAMES, LED_POSITIONS);
	device.addFeature("udp");
	device.log(`ASUS G513QR bridge target: ${controller.ip}:${DDP_PORT}`);
}

export function Render() {
	const colors = getPerKeyColors();
	udp.send(controller.ip, DDP_PORT, makeDdpPacket(colors), false);
}

export function Shutdown() {
	const rgb = hexToRgb(shutdownColor);
	const colors = [];
	for (let i = 0; i < LED_POSITIONS.length; i++) {
		colors.push(rgb);
	}
	udp.send(controller.ip, DDP_PORT, makeDdpPacket(colors), false);
}

function getPerKeyColors() {
	const colors = [];
	if (LightingMode === "Forced") {
		const rgb = hexToRgb(forcedColor);
		for (let i = 0; i < LED_POSITIONS.length; i++) {
			colors.push(rgb);
		}
	} else {
		for (let i = 0; i < LED_POSITIONS.length; i++) {
			const pos = LED_POSITIONS[i];
			const color = device.color(pos[0], pos[1]);
			colors.push([color[0], color[1], color[2]]);
		}
	}
	return colors;
}

function makeDdpPacket(colors) {
	const payloadLength = colors.length * 3;
	const packet = [
		0x41,
		sequence++ & 0xff,
		0x0A,
		0x01,
		0x00, 0x00, 0x00, 0x00,
		(payloadLength >> 8) & 0xff,
		payloadLength & 0xff
	];

	for (let i = 0; i < colors.length; i++) {
		packet.push(colors[i][0], colors[i][1], colors[i][2]);
	}

	return packet;
}

function hexToRgb(hex) {
	const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
	return result ? [
		parseInt(result[1], 16),
		parseInt(result[2], 16),
		parseInt(result[3], 16)
	] : [0, 0, 0];
}

export function DiscoveryService() {
	this.IconUrl = "https://assets.signalrgb.com/brands/asus/logo.png";
	this.firstRun = true;
	this.controllerCreated = false;

	this.Initialize = function() {
		service.log("Initializing ASUS G513QR bridge add-on.");
		this.EnsureController();
	};

	this.Update = function() {
		this.EnsureController();
		for (const cont of service.controllers) {
			cont.obj.update();
		}
	};

	this.EnsureController = function() {
		if (this.controllerCreated) {
			return;
		}

		this.firstRun = false;
		this.controllerCreated = true;
		service.log("Announcing fixed ASUS G513QR bridge controller.");
		this.CreateController({
			id: "asus-g513qr-192.168.1.76",
			name: "ASUS ROG Strix G513QR",
			ip: "192.168.1.76",
			hostname: "arch-supremacy",
			port: 4048,
			model: "ROG Strix G513QR",
			firmwareVersion: "asusd"
		});
	};

	this.CreateController = function(value) {
		service.log(`CreateController ${value.id} ${value.ip}:${value.port}`);
		const existing = service.getController(value.id);
		if (existing === undefined) {
			service.log("Adding ASUS G513QR controller.");
			service.addController(new AsusG513QRController(value));
		} else {
			service.log("Updating existing ASUS G513QR controller.");
			existing.updateWithValue(value);
			service.updateController(existing);
		}
	};
}

class AsusG513QRController {
	constructor(value) {
		this.updateWithValue(value);
		this.connected = true;
		this.deviceCreated = false;
		service.updateController(this);
	}

	updateWithValue(value) {
		this.id = value.id;
		this.name = value.name;
		this.ip = value.ip;
		this.hostname = value.hostname;
		this.port = value.port;
		this.model = value.model;
		this.firmwareVersion = value.firmwareVersion;
	}

	update() {
		if (!this.deviceCreated) {
			this.announce();
		}
	}

	announce() {
		service.log(`AnnounceController ${this.id}`);
		this.deviceCreated = true;
		service.updateController(this);
		service.announceController(this);
	}
}
