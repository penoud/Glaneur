#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
VERSION=${1:-$(python -c 'from Glaneur import __version__; print(__version__)')}
OUT=${2:-"$ROOT/dist"}
PACKAGE="$OUT/glaneur_${VERSION}_amd64"

rm -rf "$PACKAGE"
mkdir -p "$PACKAGE/DEBIAN" \
    "$PACKAGE/opt/Glaneur" \
    "$PACKAGE/usr/bin" \
    "$PACKAGE/usr/share/applications" \
    "$PACKAGE/usr/share/icons/hicolor/scalable/apps"

cp -a "$ROOT/dist/Glaneur/." "$PACKAGE/opt/Glaneur/"
cp "$ROOT/packaging/linux/Glaneur-launcher" "$PACKAGE/usr/bin/Glaneur"
cp "$ROOT/packaging/linux/Glaneur.desktop" \
    "$PACKAGE/usr/share/applications/org.glaneur.Glaneur.desktop"
cp "$ROOT/packaging/linux/org.glaneur.Glaneur.svg" \
    "$PACKAGE/usr/share/icons/hicolor/scalable/apps/org.glaneur.Glaneur.svg"

cat > "$PACKAGE/DEBIAN/control" <<EOF
Package: glaneur
Version: $VERSION
Section: net
Priority: optional
Architecture: amd64
Maintainer: Glaneur contributors
Depends: libxcb-cursor0, libxkbcommon-x11-0
Description: WordPress image downloader
 Synchronize images from a WordPress media library through its REST API.
EOF

chmod 0755 "$PACKAGE/usr/bin/Glaneur"
dpkg-deb --build "$PACKAGE" "$OUT/glaneur_${VERSION}_amd64.deb"