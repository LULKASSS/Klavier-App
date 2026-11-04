#!/bin/bash
# Einmal ausführen: richtet die Umwandlung lokal ein (kein Admin, kein Homebrew nötig).
#   ./einrichten.sh            Klavier-Modell, Stimmen-Trennung
#   ./einrichten.sh --rueckfall  zusätzlich Basic Pitch (Rückfall, eigene Umgebung)
# Alles landet in .venv/, .werkzeug/ und .modelle/ (nicht im Repo). Audio-Dateien liest
# macOS selbst (afconvert), ffmpeg ist nicht nötig. Erneutes Ausführen schadet nicht.
set -euo pipefail
cd "$(dirname "$0")"

PY_VERSION=3.11
MODELL_DATEI="note_F1=0.9677_pedal_F1=0.9186.pth"
MODELL_URL="https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
MODELL_MIN_BYTES=160000000

command -v python3 >/dev/null || { echo "python3 fehlt: https://www.python.org/downloads/macos/"; exit 1; }

echo "1/4 Werkzeug uv in .werkzeug/"
[ -x .werkzeug/bin/uv ] || { python3 -m venv .werkzeug; .werkzeug/bin/pip -q install uv; }

echo "2/4 Python $PY_VERSION und Pakete in .venv/ (dauert beim ersten Mal einige Minuten)"
.werkzeug/bin/uv venv --quiet --allow-existing --python "$PY_VERSION" .venv
.werkzeug/bin/uv pip install --quiet --python .venv/bin/python -r umwandler/anforderungen.txt

echo "3/4 Klavier-Modell (ca. 165 MB) in .modelle/"
mkdir -p .modelle
if [ ! -f ".modelle/$MODELL_DATEI" ] || [ "$(stat -f%z ".modelle/$MODELL_DATEI")" -lt "$MODELL_MIN_BYTES" ]; then
  curl -fL --retry 3 -C - -o ".modelle/$MODELL_DATEI" "$MODELL_URL"
fi

if [ "${1:-}" = "--rueckfall" ]; then
  echo "    Basic Pitch als Rückfall in .venv-rueckfall/"
  .werkzeug/bin/uv venv --quiet --allow-existing --python "$PY_VERSION" .venv-rueckfall
  .werkzeug/bin/uv pip install --quiet --python .venv-rueckfall/bin/python "basic-pitch==0.4.0" "setuptools<81"
fi

echo "4/4 Probe"
.venv/bin/python -c "
import torch, librosa, piano_transcription_inference, pretty_midi
from demucs.pretrained import get_model
get_model('htdemucs')  # lädt das Trennmodell schon jetzt, nicht erst beim ersten Song
print('torch', torch.__version__, '· MPS', torch.backends.mps.is_available())"
echo "Fertig."
