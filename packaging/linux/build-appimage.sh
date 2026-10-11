#!/bin/sh
# Builds an AppImage for Glaneur from the PyInstaller bundle.
#
# Usage: build-appimage.sh [version] [output_dir]
#
# Requires: python3, curl, dpkg-deb (for arch detection)
# Downloads appimagetool from GitHub on first run.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
VERSION=${1:-$(python3 -c 'from Glaneur import __version__; print(__version__)')}
OUT=${2:-"$ROOT/dist"}
ARCH=$(dpkg --print-architecture 2>/dev/null || echo "x86_64")

APPDIR="$ROOT/packaging/linux/Glaneur.AppDir"
APPIMAGE="$OUT/Glaneur-${VERSION}-${ARCH}.AppImage"

# ── 1. Populate the AppDir (FHS structure) ──────────────────────────
#
# PyInstaller bundle needs all its files (Qt libs, translations, build/,
# python3.x.zip) alongside the binaire (sys.prefix). In FHS AppImage the
# binaire lives in usr/bin/ and the runtime tree in usr/lib/<app>/. We
# create the split, then add symlinks so the binaire can still find its
# resources through the paths it expects.
#
#     AppDir/usr/bin/Glaneur          → executable (shim)
#     AppDir/usr/lib/Glaneur/         → real PyInstaller bundle
#     AppDir/usr/bin/Glaneur → ../lib/Glaneur/ → symlinks for resources
# Clean only the generated usr/ subtree so the committed AppRun at
# "$APPDIR/AppRun" survives — appimagetool requires it and nothing in
# this script would recreate it.
rm -rf "$APPDIR/usr"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/lib/Glaneur" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
         "$APPDIR/usr/share/metainfo"

# Copy the full PyInstaller bundle into usr/lib/Glaneur/
cp -a "$ROOT/dist/Glaneur/." "$APPDIR/usr/lib/Glaneur/"

# Create a shim executable in usr/bin/ that exec's the real bundle.
cat > "$APPDIR/usr/bin/Glaneur" <<'SHIM'
#!/bin/sh
SELF="$(cd "$(dirname "$0")/.." && pwd)"
exec "$SELF/lib/Glaneur/Glaneur" "$@"
SHIM
chmod +x "$APPDIR/usr/bin/Glaneur"

# Desktop file, icon, metainfo
cp "$ROOT/packaging/linux/Glaneur.desktop" \
   "$APPDIR/usr/share/applications/org.glaneur.Glaneur.desktop"
cp "$ROOT/packaging/linux/org.glaneur.Glaneur.svg" \
   "$APPDIR/usr/share/icons/hicolor/scalable/apps/org.glaneur.Glaneur.svg"
cp "$ROOT/packaging/linux/org.glaneur.Glaneur.metainfo.xml" \
   "$APPDIR/usr/share/metainfo/org.glaneur.Glaneur.metainfo.xml"

# appimagetool requires the .desktop file and the icon referenced by its
# Icon= key at the AppDir root, in addition to the FHS copies that end
# up installed on the user's system. Without the root .desktop,
# appimagetool fails with "Desktop file not found, aborting".
ln -sf usr/share/applications/org.glaneur.Glaneur.desktop \
       "$APPDIR/org.glaneur.Glaneur.desktop"
ln -sf usr/share/icons/hicolor/scalable/apps/org.glaneur.Glaneur.svg \
       "$APPDIR/org.glaneur.Glaneur.svg"
ln -sf org.glaneur.Glaneur.svg "$APPDIR/.DirIcon"

chmod +x "$APPDIR/AppRun"

# ── 2. Download appimagetool (cached) ────────────────────────────────
TOOLS="$ROOT/.github/tools"
mkdir -p "$TOOLS"
APPIMAGETOOL="$TOOLS/appimagetool-x86_64.AppImage"

if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    curl -fSL "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
         -o "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# ── 3. Build the AppImage ──────────────────────────────────────────
echo "Building AppImage: $APPIMAGE"
APPIMAGE_OUTPUT="$APPIMAGE" "$APPIMAGETOOL" -s "$APPDIR"

echo "AppImage ready: $(ls -lh "$APPIMAGE" | awk '{print $5}')"
