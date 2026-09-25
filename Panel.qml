import QtQuick
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
        contentWidth: popup.fittedContentWidth(Style.space(420))
        contentHeight: popup.fittedContentHeight(column.implicitHeight)

        Column {
            id: column
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            spacing: Style.space(12)

            Text {
                width: parent.width
                text: "KShare"
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.weight: Font.DemiBold
                elide: Text.ElideNone
            }

            Text {
                id: message
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                text: {
                    if (!root.service)
                        return "The KShare service is not running. Enable kshare.screen, then open this again."
                    if (root.service.errorText)
                        return root.service.errorText
                    if (root.service.sharing)
                        return "On the Windows PC, open KShare and enter this PIN."
                    return "Share this screen with a Windows PC on the same network."
                }
            }

            Text {
                visible: root.service && root.service.sharing
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: root.service ? root.service.pin : ""
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: 36
                font.letterSpacing: 6
            }

            Text {
                visible: root.service && root.service.url !== ""
                width: parent.width
                wrapMode: Text.WrapAnywhere
                text: root.service ? root.service.url : ""
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Button {
                anchors.horizontalCenter: parent.horizontalCenter
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
