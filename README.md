# KShare

Share an Omarchy screen on the local network and watch it in a native Windows window.

The Omarchy side is a shell plugin (`kshare.screen`) plus a Python host. The Windows side is a WinForms app. There is no browser viewer.

## Omarchy

Install from the AUR once the package is published:

```bash
yay -S kshare
kshare-enable
omarchy-shell shell rescanPlugins
omarchy plugin enable kshare.screen
```

Or clone this repo and add it as a plugin (the manifest is at the repository root):

```bash
omarchy plugin add <git-url-of-this-repo>
omarchy plugin enable kshare.screen
```

The host then runs from this checkout if `/usr/bin/kshare` is not installed. It needs `python`, `ffmpeg`, and `gpu-screen-recorder`.

Click **Share** on the bar, then **Start sharing**. The popup shows a 6-digit PIN.

`python -m kshare host` still starts the host from a terminal. `python -m kshare find` lists hosts announced on the LAN.

## Windows

On a Windows PC on the same network:

```bash
cd windows/KShareView
dotnet build -c Release
```

Run `KShare.exe`. It listens for the Omarchy host, or you can type `http://<omarchy-ip>:47330/`. Enter the PIN and press Watch.

Requires the .NET 8 desktop runtime.

## AUR

`PKGBUILD` installs:

- `/usr/bin/kshare` and `/usr/bin/kshare-enable`
- the Python package under `/usr/lib/kshare`
- the plugin files under `/usr/share/kshare/plugin`

Publish by pushing a `v0.2.0` tag and pointing the AUR `source` at that tarball, then run `makepkg --printsrcinfo > .SRCINFO`.
