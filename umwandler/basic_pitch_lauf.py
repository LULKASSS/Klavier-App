"""Basic Pitch auf einer Aufnahme laufen lassen (Umgebung .venv-rueckfall).

Aufruf: .venv-rueckfall/bin/python umwandler/basic_pitch_lauf.py <eingabe.wav> <ausgabe.json>
Schreibt die Noten als {start, ende, ton, anschlag}, gewertet wird in der Hauptumgebung.
"""
import json
import sys

from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict

_, _, ereignisse = predict(sys.argv[1], ICASSP_2022_MODEL_PATH)
noten = sorted(
    ({"start": float(a), "ende": float(e), "ton": int(t), "anschlag": int(min(127, s * 127))} for a, e, t, s, *_ in ereignisse),
    key=lambda n: (n["start"], n["ton"]),
)
with open(sys.argv[2], "w") as f:
    json.dump(noten, f)
print(len(noten), "Noten")
