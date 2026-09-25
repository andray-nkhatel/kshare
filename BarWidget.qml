import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "kshare.screen"

    readonly property var service: bar && bar.shell && typeof bar.shell.serviceFor === "function"
                                   ? bar.shell.serviceFor("kshare.screen") : null
    readonly property bool sharing: service ? service.sharing : false
    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

    function open() { if (panelLoader.item) panelLoader.item.open() }
    function close() { if (panelLoader.item) panelLoader.item.close() }
    function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }

    function injectPanel() {
        var target = panelLoader.item
        if (!target)
            return
        if ("bar" in target) target.bar = root.bar
        if ("settings" in target) target.settings = root.settings
        if ("anchorItem" in target) target.anchorItem = button
        if ("hostWidget" in target) target.hostWidget = root
        if ("service" in target) target.service = root.service
    }

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    onBarChanged: injectPanel()
    onSettingsChanged: injectPanel()
    onServiceChanged: injectPanel()

    Loader {
        id: panelLoader
        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: {
            root.injectPanel()
            Qt.callLater(root.injectPanel)
        }
    }

    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.vertical ? "" : (root.sharing ? "Live" : "Share")
        labelVisible: !root.vertical
        hasVisualContent: true
        horizontalMargin: 8
        onPressed: root.togglePanel()

        Text {
            anchors.centerIn: parent
            visible: root.vertical
            text: root.sharing ? "●" : "▣"
            color: button.foreground
            font.pixelSize: Style.bar.iconSlot * 0.45
        }
    }
}
