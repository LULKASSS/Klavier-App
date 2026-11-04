"""Eine Audiodatei umwandeln, ohne Oberfläche.

  .venv/bin/python -m umwandler "song.m4a" zielordner [--band] [--trennpunkt 60]

--band trennt vorher die Stimmen und erkennt nur das, was Klavier enthält.
Schreibt drei MIDIs: Original, Mittel, Leicht.
"""
import argparse
import time
from pathlib import Path

from . import aufbereiten as auf
from . import erkennen as erk
from . import fassungen as fas


def main():
    a = argparse.ArgumentParser()
    a.add_argument("audio", type=Path)
    a.add_argument("ziel", type=Path)
    a.add_argument("--band", action="store_true")
    a.add_argument("--trennpunkt", type=int, default=auf.TRENNPUNKT)
    o = a.parse_args()
    o.ziel.mkdir(parents=True, exist_ok=True)

    t = time.time()
    x, sr = erk.lese_audio(o.audio)
    if o.band:
        print("Stimmen trennen …", flush=True)
        stimmen, sr = erk.trenne_stimmen(x, sr, erk.TRENN_MODELL)
        x = stimmen[erk.TRENN_STIMME]
    print("Noten erkennen …", flush=True)
    noten = erk.erkenne_klavier(x, sr)
    raster = auf.schaetze_raster(noten)
    quant = auf.quantisiere(noten, raster, o.trennpunkt)
    name = o.audio.stem
    for fassung, inhalt in (("Original", quant), ("Mittel", fas.fassung_mittel(quant, raster)), ("Leicht", fas.fassung_leicht(quant, raster))):
        fas.schreibe_midi(inhalt, raster, o.ziel / f"{name} – {fassung}.mid", f"{name} {fassung}")
    print(f"{len(quant)} Noten, {raster.bpm:.0f} BPM, {time.time() - t:.0f} s → {o.ziel}")


if __name__ == "__main__":
    main()
