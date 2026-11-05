"""Wandelt einen Song im Bibliotheks-Ordner um. Läuft als eigener Prozess des Dienstes.

Aufruf: python -m umwandler.auftrag <songordner>
Meldet den Fortschritt als Zeilen `@{json}` auf stdout. Das Modell selbst schreibt `Segment i / n`.
"""
import json
import sys
from pathlib import Path

import numpy as np

from . import aufbereiten as auf
from . import erkennen as erk
from . import fassungen as fas
from .cover import baue_cover, schreibe_midi
from .hoerprobe import hoerprobe
from .spuren import berechne

FASSUNGEN = {"leicht": "Leicht", "mittel": "Mittel", "original": "Cover"}
BALKEN = 96


def melde(**werte):
    print("@" + json.dumps(werte, ensure_ascii=False), flush=True)


def welle(x):
    """Lautstärke in festen Abschnitten, 0–1, für die Anzeige."""
    mono = np.abs(x.mean(axis=1) if x.ndim == 2 else x)
    teile = np.array_split(mono, BALKEN)
    w = np.array([float(np.sqrt(np.mean(t**2))) if len(t) else 0.0 for t in teile])
    return [round(float(v), 3) for v in w / (w.max() + 1e-9)]


def fertige_midi(ordner, meta):
    """Fertige MIDI-Datei: Noten übernehmen. Zwei Spuren sind die Hände, sonst trennt die Tonhöhe."""
    import pretty_midi

    melde(schritt="fassungen")
    try:
        m = pretty_midi.PrettyMIDI(str(ordner / meta["datei"]))
    except Exception as e:
        raise ValueError("Die MIDI-Datei lässt sich nicht lesen.") from e
    spuren = [i for i in m.instruments if not i.is_drum and i.notes]
    if not spuren:
        raise ValueError("In der MIDI-Datei sind keine Noten.")
    noten = []
    if len(spuren) == 2:
        oben = max(spuren, key=lambda i: np.median([n.pitch for n in i.notes]))
        for i in spuren:
            noten += [(n.start, n.end, n.pitch, n.velocity, 1 if i is oben else 0) for n in i.notes]
    else:
        noten = [(n.start, n.end, n.pitch, n.velocity, 1 if n.pitch >= auf.TRENNPUNKT else 0) for i in spuren for n in i.notes]
    noten.sort()
    (ordner / "original.json").write_text(json.dumps([[round(a, 3), round(e, 3), t, h] for a, e, t, _, h in noten]))
    (ordner / "original.mid").write_bytes((ordner / meta["datei"]).read_bytes())
    pedal, an = [], None
    for i in spuren[:1] if len(spuren) == 1 else spuren:
        for c in i.control_changes:
            if c.number == 64:
                if c.value >= 64 and an is None:
                    an = c.time
                elif c.value < 64 and an is not None:
                    pedal.append([round(an, 3), round(c.time, 3)])
                    an = None
    pedal.sort()
    (ordner / "pedal.json").write_text(json.dumps(pedal))
    hoerprobe([{"start": a, "ende": e, "ton": t, "anschlag": v} for a, e, t, v, _ in noten], ordner / "original", pedal)
    tempo = float(m.get_tempo_changes()[1][0])
    takt_s = 240 / tempo
    ende = max(n[1] for n in noten)
    melde(dauer=ende, bpm=round(tempo), takte=int(np.ceil(ende / takt_s)), takt_ab=0.0, takt_s=takt_s, notenzahl={"original": len(noten)})


def cover_aus_band(ordner, meta):
    """Band-Song: Rechts die Stimme, links die Begleitung. Die Spuren werden gemerkt, Neu-Umwandeln geht dann schnell."""
    sp = berechne(ordner / meta["datei"], ordner, melde)
    c = np.load(sp.grund)
    (ordner / "wellen.json").write_text(json.dumps({"Gesang": welle(c["voc"]), "Bass": welle(c["bas"]), "Rest": welle(c["oth"])}))
    melde(wellen=True)
    melde(schritt="fassungen")
    e = baue_cover(sp)
    for key in FASSUNGEN:
        rechts, links = e[key]["rechts"], e[key]["links"]
        schreibe_midi(ordner / f"{key}.mid", e["viertel_s"], e["pedal"], rechts, links, f'{meta["name"]} {FASSUNGEN[key]}')
        (ordner / f"{key}.json").write_text(json.dumps(
            sorted([[round(n["start"], 3), round(n["ende"], 3), n["ton"], 1] for n in rechts] + [[round(n["start"], 3), round(n["ende"], 3), n["ton"], 0] for n in links])))
        hoerprobe(sorted(rechts + links, key=lambda n: n["start"]), ordner / key, e["pedal"])
    (ordner / "pedal.json").write_text(json.dumps([[round(a, 3), round(b, 3)] for a, b in e["pedal"]]))
    melde(bpm=round(e["bpm"]), takte=e["takte"], takt_ab=e["takt_ab"], takt_s=e["takt_s"], notenzahl={k: len(e[k]["rechts"]) + len(e[k]["links"]) for k in FASSUNGEN})


def umwandeln(ordner):
    ordner = Path(ordner)
    meta = json.loads((ordner / "meta.json").read_text())
    if meta.get("midi"):
        return fertige_midi(ordner, meta)
    try:
        x, sr = erk.lese_audio(ordner / meta["datei"])
    except Exception as e:
        raise ValueError("Die Datei lässt sich nicht lesen.") from e
    if not len(x):
        raise ValueError("Die Datei ist leer.")
    dauer = len(x) / sr
    melde(dauer=dauer)

    if meta.get("band"):
        return cover_aus_band(ordner, meta)
    wellen = {"Aufnahme": welle(x)}
    (ordner / "wellen.json").write_text(json.dumps(wellen))
    melde(wellen=True)

    melde(schritt="erkennen")
    noten = erk.erkenne_klavier(x, sr)
    if len(noten) < 8:
        raise ValueError("Hier sind fast keine Klaviernoten zu finden.")
    melde(schritt="takt", erkannt=len(noten))
    raster = auf.schaetze_raster(noten)
    quant = auf.quantisiere(noten, raster)

    melde(schritt="fassungen")
    inhalte = {"original": quant, "mittel": fas.fassung_mittel(quant, raster), "leicht": fas.fassung_leicht(quant, raster)}
    for key, inhalt in inhalte.items():
        fas.schreibe_midi(inhalt, raster, ordner / f"{key}.mid", f'{meta["name"]} {key.capitalize()}')
        zeit = raster.in_zeit(inhalt)
        (ordner / f"{key}.json").write_text(json.dumps(
            [[round(n["start"], 3), round(n["ende"], 3), n["ton"], 1 if n["hand"] == "rechts" else 0] for n in zeit]))
        hoerprobe(zeit, ordner / key)
    takte = (max(n["schritt"] for n in quant) - raster.erster_takt % 4 * 4) // 16 + 1
    (ordner / "pedal.json").write_text("[]")
    melde(bpm=round(raster.bpm), takte=takte, takt_ab=float(raster.taktanfaenge()[0]), takt_s=float(4 * 60 / raster.bpm), notenzahl={k: len(v) for k, v in inhalte.items()})


if __name__ == "__main__":
    try:
        umwandeln(sys.argv[1])
    except ValueError as e:
        melde(fehler=str(e))
        sys.exit(1)
