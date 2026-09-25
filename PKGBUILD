# Maintainer: KShare contributors
pkgname=kshare
pkgver=0.2.0
pkgrel=1
pkgdesc='Omarchy screen-sharing plugin, watched with the native Windows KShare app'
arch=('any')
url='https://github.com/kshare-org/kshare'
license=('MIT')
depends=('python' 'ffmpeg' 'gpu-screen-recorder' 'bash')
optdepends=('omarchy: bar plugin and shell integration')
install=kshare.install
source=("$pkgname-$pkgver.tar.gz::https://github.com/kshare-org/kshare/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')

package() {
  cd "$pkgname-$pkgver"

  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm755 bin/kshare "$pkgdir/usr/bin/kshare"
  install -Dm755 bin/kshare-enable "$pkgdir/usr/bin/kshare-enable"

  install -d "$pkgdir/usr/lib/kshare/kshare"
  install -m644 kshare/*.py "$pkgdir/usr/lib/kshare/kshare/"

  install -d "$pkgdir/usr/share/kshare/plugin"
  install -m644 manifest.json Service.qml BarWidget.qml Panel.qml "$pkgdir/usr/share/kshare/plugin/"
}
