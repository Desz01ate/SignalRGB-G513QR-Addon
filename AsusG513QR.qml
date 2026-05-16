Item {
	anchors.fill: parent

	Column {
		width: parent.width
		height: parent.height
		spacing: 10

		Rectangle {
			width: 360
			height: content.childrenRect.height + 20
			color: theme.background3
			radius: theme.radius

			Column {
				id: content
				x: 10
				y: 10
				width: parent.width - 20
				spacing: 6

				Text {
					color: theme.primarytextcolor
					text: "ASUS ROG Strix G513QR"
					font.pixelSize: 16
					font.family: "Poppins"
					font.bold: true
				}

				Text {
					color: theme.secondarytextcolor
					text: "Bridge: 192.168.1.76 UDP 4048"
					font.pixelSize: 13
					font.family: "Montserrat"
				}

				Text {
					color: theme.secondarytextcolor
					text: service.controllers.length > 0 ? "Status: controller announced" : "Status: waiting for controller"
					font.pixelSize: 13
					font.family: "Montserrat"
				}

				ToolButton {
					height: 34
					width: 160
					text: "Create Device"
					visible: service.controllers.length > 0
					onClicked: {
						service.controllers[0].obj.announce();
					}
				}
			}
		}
	}
}
