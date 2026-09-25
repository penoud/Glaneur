#!/bin/sh
# Réécrit la ligne <release ... /> du fichier metainfo AppStream avec la
# version en cours (Glaneur.__version__ par défaut) et la date
# UTC du jour. Idempotent, à appeler avant flatpak-builder et dpkg-deb
# pour éviter que la version affichée par les gestionnaires ne s'écarte
# de celle réellement embarquée dans les paquets.
#
# Usage : bump-metainfo.sh [version]
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
FICHIER="$ROOT/packaging/linux/org.glaneur.Glaneur.metainfo.xml"

VERSION=${1:-$(python -c 'from Glaneur import __version__; print(__version__)')}
DATE=$(date -u +%Y-%m-%d)

# Un placeholder d'un seul <release> — le format doit rester exactement
# celui-là dans le fichier source pour que ce sed reste stable.
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
    raise SystemExit("bump-metainfo : balise <release ... /> introuvable")
with open(chemin, "w", encoding="utf-8") as f:
    f.write(nouveau)
print(f"metainfo mis à jour : version={version} date={date}")
PY
