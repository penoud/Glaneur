#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
VERSION=${1:-$(python -c 'from WpImageDownloader import __version__; print(__version__)')}
OUT=${2:-"$ROOT/dist"}
PACKAGE="$OUT/wpimagedownloader_${VERSION}_amd64"

rm -rf "$PACKAGE"
mkdir -p "$PACKAGE/DEBIAN" \
    "$PACKAGE/opt/WpImageDownloader" \
    "$PACKAGE/usr/bin" \
    "$PACKAGE/usr/share/applications" \
    "$PACKAGE/usr/share/icons/hicolor/scalable/apps"

cp -a "$ROOT/dist/ServetteDownloader/." "$PACKAGE/opt/WpImageDownloader/"
cp "$ROOT/packaging/linux/WpImageDownloader-launcher" "$PACKAGE/usr/bin/WpImageDownloader"
cp "$ROOT/packaging/linux/WpImageDownloader.desktop" \
    "$PACKAGE/usr/share/applications/org.wpimagedownloader.WpImageDownloader.desktop"
cp "$ROOT/packaging/linux/org.wpimagedownloader.WpImageDownloader.svg" \
    "$PACKAGE/usr/share/icons/hicolor/scalable/apps/org.wpimagedownloader.WpImageDownloader.svg"

cat > "$PACKAGE/DEBIAN/control" <<EOF
Package: wpimagedownloader
Version: $VERSION
Section: net
Priority: optional
Architecture: amd64
Maintainer: WP Image Downloader contributors
Depends: libxcb-cursor0, libxkbcommon-x11-0
Description: WordPress image downloader
 Synchronize images from a WordPress media library through its REST API.
EOF

chmod 0755 "$PACKAGE/usr/bin/WpImageDownloader"
dpkg-deb --build "$PACKAGE" "$OUT/wpimagedownloader_${VERSION}_amd64.deb"