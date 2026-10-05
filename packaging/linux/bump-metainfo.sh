#!/bin/sh
# Rewrites the <release ... /> line of the AppStream metainfo file with
# the current version (Glaneur.__version__ by default) and today's UTC
# date. Idempotent, to be called before flatpak-builder and dpkg-deb so
# the version shown by package managers stays in sync with the one
# actually shipped in the packages.
#
# Usage: bump-metainfo.sh [version]
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
FICHIER="$ROOT/packaging/linux/org.glaneur.Glaneur.metainfo.xml"

VERSION=${1:-$(python -c 'from Glaneur import __version__; print(__version__)')}
DATE=$(date -u +%Y-%m-%d)

# A single <release> placeholder — the format must stay exactly this
# one in the source file so this sed remains stable.
python - "$FICHIER" "$VERSION" "$DATE" <<'PY'
import re
import sys

chemin, version, date = sys.argv[1], sys.argv[2], sys.argv[3]
with open(chemin, encoding="utf-8") as f:
    texte = f.read()
nouveau = re.sub(
    r'<release version="[^"]+" date="[^"]+" />',
    f'<release version="{version}" date="{date}" />',
    texte,
    count=1,
)
if nouveau == texte:
    raise SystemExit("bump-metainfo: <release ... /> tag not found")
with open(chemin, "w", encoding="utf-8") as f:
    f.write(nouveau)
print(f"metainfo updated: version={version} date={date}")
PY
