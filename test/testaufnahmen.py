"""Erzeugt drei Testaufnahmen mit bekannten Noten (eigens geschriebene Stücke, nichts Fremdes).

  1 aufnahme  Klavier allein, einfach, frei gespielt (schwankendes Tempo, Raum, Rauschen)
  2 cover     Klavier allein, dicht: Arpeggien links, Oktaven rechts, Pedal, Hall
  3 band      Das Cover-Klavier in einer Band mit Gesang, Bass, Schlagzeug, Flächen

Klang: GS-Klangsatz von macOS. Das ist kein echtes Klavier im Raum; die Messung sagt also,
wie gut der Umwandler bei sauberem Sample-Klavier ist, nicht wie bei einer echten Aufnahme.

Aufruf: python test/testaufnahmen.py <zielordner>
Schreibt je Stück <name>.wav und <name>.json (Referenz: Klaviernoten, Melodie, Akkorde, Takt).
"""
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

HIER = Path(__file__).parent
TEIL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Akkorde je Takt: Grundton (Name), Stufen über dem Grundton
FOLGE_A = [("C", (0, 4, 7)), ("A", (0, 3, 7)), ("F", (0, 4, 7)), ("G", (0, 4, 7))]
FOLGE_B = [("D", (0, 3, 7)), ("G", (0, 4, 7)), ("E", (0, 3, 7)), ("A", (0, 3, 7)),
           ("F", (0, 4, 7)), ("C", (0, 4, 7)), ("D", (0, 3, 7)), ("G", (0, 4, 7))]


def akkorde(takte, folge):
    return [folge[i % len(folge)] for i in range(takte)]


def melodie(rnd, liste, unten=67, oben=84):
    """Melodie: pro Takt Motiv aus Akkordtönen und Durchgängen, Zeiten in Vierteln."""
    leiter = [m for m in range(unten - 2, oben + 3) if m % 12 in (0, 2, 4, 5, 7, 9, 11)]
    aktuell = 72
    noten = []
    motive = [
        [(0, 1), (1, 0.5), (1.5, 0.5), (2, 1.5), (3.5, 0.5)],
        [(0, 1.5), (1.5, 0.5), (2, 1), (3, 1)],
        [(0, 0.5), (0.5, 0.5), (1, 1), (2, 0.5), (2.5, 0.5), (3, 1)],
        [(0, 2), (2, 1), (3, 1)],
    ]
    for t, (wurzel, stufen) in enumerate(liste):
        motiv = motive[(t // 2) % len(motive)]
        ton_klassen = {(TEIL[wurzel] + s) % 12 for s in stufen}
        for i, (beat, dauer) in enumerate(motiv):
            if i == 0 or beat == 2:  # schwere Zeit: Akkordton
                nah = [m for m in range(unten, oben + 1) if m % 12 in ton_klassen]
                aktuell = min(nah, key=lambda m: (abs(m - aktuell), rnd.random()))
            else:
                k = leiter.index(min(leiter, key=lambda m: abs(m - aktuell)))
                aktuell = leiter[int(np.clip(k + rnd.choice([-2, -1, 1, 2]), 0, len(leiter) - 1))]
                aktuell = int(np.clip(aktuell, unten, oben))
            noten.append((t * 4 + beat, dauer, aktuell))
    return noten


def stueck_aufnahme(rnd):
    """Einfach: rechts Melodie, links Grundton und Quinte in Vierteln."""
    liste = akkorde(16, FOLGE_A)
    mel = melodie(rnd, liste)
    rechts = [(b, d, m, rnd.randint(70, 95)) for b, d, m in mel]
    links = []
    for t, (w, st) in enumerate(liste):
        g = 48 + TEIL[w]
        g = g - 12 if g > 54 else g
        links += [(t * 4, 1.8, g, 62), (t * 4 + 2, 1.8, g + st[2], 55)]
    return {"bpm": 84, "takte": 16, "rechts": rechts, "links": links, "melodie": mel, "liste": liste}


def stueck_cover(rnd):
    """Dicht: Oktav-Melodie mit Akkordfüllung, links gebrochene Akkorde in Achteln."""
    liste = akkorde(24, FOLGE_B)
    mel = melodie(rnd, liste, unten=69, oben=88)
    rechts = []
    for b, d, m in mel:
        rechts.append((b, d, m, rnd.randint(85, 110)))
        t = int(b // 4)
        w, st = liste[t]
        if b % 2 == 0:  # schwere Zeit: Akkord unter der Melodie
            klassen = [(TEIL[w] + s) % 12 for s in st]
            unter = [x for x in range(m - 9, m) if x % 12 in klassen and x >= 60][-2:]
            rechts += [(b, d, x, rnd.randint(55, 72)) for x in unter]
        if t % 8 >= 4 and d >= 1:  # zweite Hälfte: Oktave
            rechts.append((b, d, m - 12, rnd.randint(65, 80)))
    links = []
    for t, (w, st) in enumerate(liste):
        g = 36 + TEIL[w]
        muster = [g, g + 12, g + 12 + st[1], g + 12 + st[2], g + 24, g + 12 + st[2], g + 12 + st[1], g + 12]
        links += [(t * 4 + i * 0.5, 0.48, m, rnd.randint(50, 72) + (12 if i == 0 else 0)) for i, m in enumerate(muster)]
    return {"bpm": 96, "takte": 24, "rechts": rechts, "links": links, "melodie": mel, "liste": liste, "pedal": True}


def in_sekunden(st, rnd, frei):
    """Viertel → Sekunden, bei frei mit langsamem Tempo-Schwanken und Anschlags-Ungenauigkeit."""
    bpm = st["bpm"]
    gesamt = st["takte"] * 4 + 2
    raster = np.arange(0, gesamt + 1, 0.25)
    if frei:
        phase = rnd.random() * 6.28
        lokal = bpm * (1 + 0.05 * np.sin(raster / 9 + phase) + 0.02 * np.sin(raster / 2.3))
    else:
        lokal = np.full_like(raster, float(bpm))
    zeit = np.concatenate([[0], np.cumsum(0.25 * 60 / lokal[:-1])])
    return lambda b: float(np.interp(b, raster, zeit))


def klavier_noten(st, rnd, frei):
    uhr = in_sekunden(st, rnd, frei)
    streu = 0.012 if frei else 0.003
    roh, ref = [], []
    for hand, noten in (("rechts", st["rechts"]), ("links", st["links"])):
        for b, d, m, v in noten:
            a = max(0.0, uhr(b) + rnd.gauss(0, streu))
            e = uhr(b + d * 0.93)
            roh.append([round(a, 4), round(e, 4), int(m), int(np.clip(v, 1, 127))])
            ref.append({"start": round(a, 4), "ende": round(e, 4), "ton": int(m), "hand": hand})
    pedal = []
    if st.get("pedal"):
        pedal = [[round(uhr(t * 4 + 0.05), 4), round(uhr(t * 4 + 3.9), 4)] for t in range(st["takte"])]
    return uhr, roh, ref, pedal


def band_spuren(st, uhr, rnd):
    bass, trommel, flaeche, stimme = [], [], [], []
    for t, (w, s) in enumerate(st["liste"]):
        g = 36 + TEIL[w] - 12 if TEIL[w] > 4 else 36 + TEIL[w]
        for b, d, m in [(0, .9, g), (1.5, .4, g), (2, .9, g), (3, .4, g + 7), (3.5, .4, g + 12)]:
            bass.append([uhr(t * 4 + b), uhr(t * 4 + b + d), m, rnd.randint(90, 110)])
        for i in range(8):
            trommel.append([uhr(t * 4 + i / 2), uhr(t * 4 + i / 2 + .1), 42, rnd.randint(60, 85)])
        for b in (0, 2.5):
            trommel.append([uhr(t * 4 + b), uhr(t * 4 + b + .1), 36, 110])
        for b in (1, 3):
            trommel.append([uhr(t * 4 + b), uhr(t * 4 + b + .1), 38, 105])
        for x in s:
            flaeche.append([uhr(t * 4), uhr(t * 4 + 3.95), 60 + (TEIL[w] + x) % 12, 60])
    # Gesang: eigene Linie, nicht dieselbe wie die Klaviermelodie, ab Takt 5
    for t in range(4, st["takte"]):
        w, s = st["liste"][t]
        for b, d, x in [(0, 1, s[1]), (1, .5, s[2]), (1.5, 1.5, s[0]), (3, 1, s[1])]:
            stimme.append([uhr(t * 4 + b), uhr(t * 4 + b + d), 64 + (TEIL[w] + x) % 12, 95])
    return [
        {"programm": 33, "schlagzeug": False, "gain": .9, "noten": bass},
        {"programm": 0, "schlagzeug": True, "gain": .8, "noten": trommel},
        {"programm": 50, "schlagzeug": False, "gain": .35, "noten": flaeche},
        {"programm": 53, "schlagzeug": False, "gain": .8, "noten": stimme},
    ]


def hall(x, sr, nachhall, anteil):
    n = int(sr * nachhall)
    rng = np.random.default_rng(7)
    ir = rng.standard_normal((n, 2)) * np.exp(-6.9 * np.arange(n) / n)[:, None]
    nass = np.stack([fftconvolve(x[:, k], ir[:, k])[: len(x)] for k in range(2)], axis=1)
    nass *= np.max(np.abs(x)) / (np.max(np.abs(nass)) + 1e-9)
    return (1 - anteil) * x + anteil * nass


def rendern(spuren, dauer, ziel, arbeitsordner):
    j = arbeitsordner / (ziel.stem + ".noten.json")
    j.write_text(json.dumps({"dauer": dauer, "spuren": spuren}))
    subprocess.run(["swift", str(HIER / "rendern.swift"), str(j), str(ziel)], check=True)


def bauen(name, st, rnd, ziel, frei=False, band=False, nachhall=.3, anteil=.1, rauschen=0.0):
    uhr, roh, ref, pedal = klavier_noten(st, rnd, frei)
    spuren = [{"programm": 0, "schlagzeug": False, "gain": 1.0, "noten": roh, "pedal": pedal}]
    andere = {}
    if band:
        extra = band_spuren(st, uhr, rnd)
        spuren += extra
        andere = {"flaeche": extra[2]["noten"], "gesang": extra[3]["noten"], "bass": extra[0]["noten"]}
    dauer = uhr(st["takte"] * 4) + 1
    wav = ziel / f"{name}.wav"
    rendern(spuren, dauer, wav, ziel)
    x, sr = sf.read(wav, always_2d=True)
    x = hall(x, sr, nachhall, anteil)
    if rauschen:
        x = x + np.random.default_rng(3).standard_normal(x.shape) * rauschen
    sf.write(wav, x * (0.9 / np.max(np.abs(x))), sr, subtype="PCM_16")
    (ziel / f"{name}.json").write_text(json.dumps({
        "name": name, "bpm": st["bpm"], "takte": st["takte"], "taktart": 4, "frei": frei, "noten": ref, "andere": andere,
        "melodie": [{"start": uhr(b), "ende": uhr(b + d), "ton": m} for b, d, m in st["melodie"]],
        "akkorde": [{"start": uhr(t * 4), "ende": uhr(t * 4 + 4), "grundton": TEIL[w],
                     "toene": [(TEIL[w] + x) % 12 for x in s]} for t, (w, s) in enumerate(st["liste"])],
        "taktanfaenge": [uhr(t * 4) for t in range(st["takte"] + 1)],
    }, indent=1))
    print(f"{name}: {len(ref)} Klaviernoten, {dauer:.0f} s")


if __name__ == "__main__":
    ziel = Path(sys.argv[1])
    ziel.mkdir(parents=True, exist_ok=True)
    bauen("1-aufnahme", stueck_aufnahme(random.Random(11)), random.Random(12), ziel, frei=True,
          nachhall=.5, anteil=.14, rauschen=.0015)
    bauen("2-cover", stueck_cover(random.Random(21)), random.Random(22), ziel, nachhall=1.1, anteil=.2)
    bauen("3-band", stueck_cover(random.Random(21)), random.Random(22), ziel, band=True, nachhall=.8, anteil=.14)
