import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "kshare.screen"
    manageIpc: false

    property var anchorItem: null
    property var hostWidget: null
    property var service: null
    readonly property var barIdentity: hostWidget || root
    readonly property color ink: bar ? bar.barForeground : Color.foreground
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

    function open() { controller.show() }
    function close() { controller.hide() }
    function toggle() { opened ? close() : open() }
    function switchPanel(direction) {
        if (bar && typeof bar.switchPanelFrom === "function")
            return bar.switchPanelFrom(barIdentity, direction)
        return false
    }

    KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem
        owner: root.barIdentity
        bar: root.bar
        open: root.opened
        centerOnBar: true
        contentWidth: popup.fittedContentWidth(280)
        contentHeight: popup.fittedContentHeight(column.implicitHeight)

        ColumnLayout {
            id: column
            width: popup.contentWidth
            spacing: Style.space(10)

            Text {
                Layout.fillWidth: true
                Layout.leftMargin: Style.space(14)
                Layout.rightMargin: Style.space(14)
                Layout.topMargin: Style.space(14)
                text: "KShare"
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.weight: Font.DemiBold
            }

            Text {
                Layout.fillWidth: true
                Layout.leftMargin: Style.space(14)
                Layout.rightMargin: Style.space(14)
                wrapMode: Text.WordWrap
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                text: {
                    if (!root.service)
                        return "Enable the KShare service, then open this again."
                    if (root.service.errorText)
                        return root.service.errorText
                    if (root.service.sharing)
                        return "On the Windows PC, open KShare and enter this PIN."
                    return "Share this screen with a Windows PC on the same network."
                }
            }

            Text {
                visible: root.service && root.service.sharing
                Layout.fillWidth: true
                Layout.leftMargin: Style.space(14)
                horizontalAlignment: Text.AlignHCenter
                text: root.service ? root.service.pin : ""
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: 36
                font.letterSpacing: 6
            }

            Text {
                visible: root.service && root.service.url !== ""
                Layout.fillWidth: true
                Layout.leftMargin: Style.space(14)
                Layout.rightMargin: Style.space(14)
                wrapMode: Text.WordWrap
                text: root.service ? root.service.url : ""
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Button {
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: Style.space(14)
                text: root.service && root.service.sharing ? "Stop sharing" : "Start sharing"
                enabled: root.service !== null
                onClicked: {
                    if (!root.service)
                        return
                    if (root.service.sharing)
                        root.service.stop()
                    else
                        root.service.start()
                }
            }
        }
    }
}
