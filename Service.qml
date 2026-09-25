import QtQuick
import Quickshell
import Quickshell.Io

// Headless host. The bar widget calls start() and stop(); this item stays
// loaded so sharing continues after the popup closes.
Item {
    id: root

    property var shell: null
    property var manifest: null

    property bool sharing: false
    property string pin: ""
    property string url: ""
    property string hostName: ""
    property string errorText: ""

    readonly property string home: Quickshell.env("HOME") || ""
    readonly property string statusPath: home + "/.local/state/kshare/host.json"
    readonly property string pluginDir: {
        var url = Qt.resolvedUrl(".").toString()
        var path = url.indexOf("file://") === 0 ? url.slice(7) : url
        return path.replace(/\/+$/, "")
    }
    readonly property int fps: {
        var cfg = shell && shell.shellConfig ? shell.shellConfig : null
        if (!cfg || !cfg.bar || !cfg.bar.layout)
            return 15
        var sections = [cfg.bar.layout.left, cfg.bar.layout.center, cfg.bar.layout.right]
        for (var s = 0; s < sections.length; s++) {
            var list = sections[s]
            if (!list)
                continue
            for (var i = 0; i < list.length; i++) {
                var entry = list[i]
                if (entry && entry.id === "kshare.screen" && entry.fps)
                    return Math.max(5, Math.min(30, parseInt(entry.fps, 10) || 15))
            }
        }
        return 15
    }

    function start() {
        errorText = ""
        if (hostProc.running)
            return
        hostProc.running = true
    }

    function stop() {
        if (hostProc.running)
            hostProc.running = false
        sharing = false
        pin = ""
        url = ""
    }

    function applyStatus(text) {
        try {
            var data = JSON.parse(text)
        } catch (e) {
            return
        }
        pin = String(data.pin || "")
        url = String(data.url || "")
        hostName = String(data.name || "")
        sharing = data.sharing === true || pin.length === 6
    }

    Process {
        id: hostProc
        command: [
            "bash", "-c",
            "if command -v kshare >/dev/null 2>&1; then exec kshare cast --fps \"$1\" --status-file \"$2\"; fi; export PYTHONPATH=\"$0${PYTHONPATH:+:$PYTHONPATH}\"; exec python3 -m kshare cast --fps \"$1\" --status-file \"$2\"",
            root.pluginDir, String(root.fps), root.statusPath
        ]
        stdout: StdioCollector {
            waitForEnd: false
        }
        stderr: StdioCollector {
            id: hostErr
            waitForEnd: false
        }
        onRunningChanged: {
            if (!hostProc.running && root.sharing)
                root.errorText = "Host stopped."
        }
        onExited: function(code) {
            root.sharing = false
            if (code !== 0 && code !== 143)
                root.errorText = hostErr.text ? hostErr.text.trim() : ("Host exited " + code)
        }
    }

    FileView {
        path: root.statusPath
        watchChanges: true
        printErrors: false
        blockLoading: false
        onLoaded: root.applyStatus(text())
        onFileChanged: reload()
    }
}
