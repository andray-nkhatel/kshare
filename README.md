# KShare

Share an Omarchy screen on the local network and watch it in the native Windows app. Both computers must be on the same network. There is no browser viewer.

## 1. Prepare the Omarchy computer

Install the capture tools if they are not already there:

```bash
sudo pacman -S --needed python ffmpeg gpu-screen-recorder
```

Add this repository as a shell plugin and turn it on:

```bash
omarchy plugin add https://github.com/andray-nkhatel/kshare.git
omarchy plugin enable kshare.screen
```

If **Share** does not show up on the bar, reload plugins and enable it again:

```bash
omarchy-shell shell rescanPlugins
omarchy plugin enable kshare.screen
```

The button lands on the right side of the bar. You can move it later with `omarchy bar move`.

## 2. Start sharing

1. Click **Share** on the bar.
2. Click **Start sharing**.
3. Leave the popup open long enough to read the 6-digit PIN. Sharing keeps running after you close the popup.
4. Click **Stop sharing** when you are done.

If the popup says the service is not enabled, run `omarchy plugin enable kshare.screen` again. The host needs the KShare service running, not only the bar button.

You can also start the host from a terminal. It prints the same PIN:

```bash
python -m kshare host
```

Stop that process with Ctrl+C.

## 3. Build the Windows app

On the Windows PC, install the [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0), then:

```bash
git clone https://github.com/andray-nkhatel/kshare.git
cd kshare\windows\KShareView
dotnet build -c Release
```

The program is `windows\KShareView\bin\Release\net8.0-windows\KShare.exe`.

## 4. Watch the screen

1. Start sharing on Omarchy first, so the Windows app can find the host.
2. Run `KShare.exe`.
3. Wait until a host appears, or type `http://<omarchy-ip>:47330/` yourself.
4. Enter the PIN from the Omarchy popup.
5. Press **Watch**. Press **Stop** to disconnect.

Find the Omarchy address on that machine with `ip -4 addr`. The host announces itself on UDP port 47331 and serves the picture on TCP port 47330. If the Windows app stays empty, allow those ports through the firewall on both computers.

## 5. Optional: install from the AUR later

`PKGBUILD` is ready for an AUR upload. After `yay -S kshare`:

```bash
kshare-enable
omarchy-shell shell rescanPlugins
omarchy plugin enable kshare.screen
```

That links `/usr/share/kshare/plugin` into your Omarchy plugin folder and uses `/usr/bin/kshare` as the host.
