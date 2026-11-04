"""Die drei Fassungen: Original, Mittel (Melodie + einfache Akkorde), Leicht (Melodie + Grundton)."""
import mido
import numpy as np

from .aufbereiten import SCHRITTE_JE_VIERTEL, TRENNPUNKT

TICKS_JE_VIERTEL = 480
TICKS_JE_SCHRITT = TICKS_JE_VIERTEL // SCHRITTE_JE_VIERTEL
DUR, MOLL = (0, 4, 7), (0, 3, 7)


def melodie(noten, trennpunkt=TRENNPUNKT):
    """Oberste Stimme: je Schritt der höchste Ton der rechten Hand, einstimmig gemacht."""
    je_schritt = {}
    for n in noten:
        if n["ton"] >= trennpunkt:
            je_schritt.setdefault(n["schritt"], {})[n["ton"]] = n
    if not je_schritt:
        return []
    # Oktave über einem zugleich angeschlagenen Ton ist oft nur ein Oberton, aber manchmal die Melodie
    # über einer Füllstimme: von beiden gilt der Ton, der näher an der bisherigen Linie liegt.
    zuletzt = float(np.median([max(t) for t in je_schritt.values()]))
    linie = []
    for s in sorted(je_schritt):
        toene = je_schritt[s]
        kette = [max(toene)]
        while kette[-1] - 12 in toene:
            kette.append(kette[-1] - 12)
        ton = min(kette, key=lambda t: (abs(t - zuletzt), t))
        linie.append(toene[ton])
        zuletzt = ton
    # Füllstimmen unter einem klingenden Melodieton streichen
    rein = []
    for n in linie:
        if rein:
            v = rein[-1]
            if n["ton"] < v["ton"] - 7 and n["schritt"] < v["schritt"] + v["laenge"] and n["anschlag"] < v["anschlag"] * 0.8:
                continue
        rein.append(dict(n, hand="rechts"))
    for a, b in zip(rein, rein[1:]):
        a["laenge"] = min(a["laenge"], b["schritt"] - a["schritt"])
    return rein


def akkorde(noten, raster, je_takt=2):
    """Je Halbtakt der beste Dur-/Moll-Dreiklang aus den Noten. Rückgabe: Liste {schritt, laenge, grundton, art}."""
    if not noten:
        return []
    takt = raster.taktart * SCHRITTE_JE_VIERTEL
    versatz = raster.erster_takt % raster.taktart * SCHRITTE_JE_VIERTEL
    fach = takt // je_takt
    ende = max(n["schritt"] + n["laenge"] for n in noten)
    aus = []
    frueh = min(n["schritt"] for n in noten)
    versatz -= int(np.ceil(max(0, versatz - frueh) / takt)) * takt  # Auftakt gehört dazu
    for start in range(versatz, ende, fach):
        h = np.zeros(12)
        tiefst = np.zeros(12)
        for n in noten:
            ueber = min(n["schritt"] + n["laenge"], start + fach) - max(n["schritt"], start)
            if ueber > 0:
                g = (n["anschlag"] / 127) * ueber
                h[n["ton"] % 12] += g
                if n["ton"] < TRENNPUNKT:
                    tiefst[n["ton"] % 12] += g * (1.6 if n["ton"] < 48 else 1)
        if h.sum() == 0:
            continue
        beste, wert = None, -1e9
        for wurzel in range(12):
            for art, st in (("dur", DUR), ("moll", MOLL)):
                drin = [(wurzel + s) % 12 for s in st]
                w = h[drin].sum() - 0.6 * (h.sum() - h[drin].sum()) + 0.8 * tiefst[wurzel]
                if w > wert:
                    beste, wert = (wurzel, art), w
        aus.append({"schritt": start, "laenge": fach, "grundton": beste[0], "art": beste[1]})
    # Gleiche Nachbarn zusammenziehen
    zus = []
    for a in aus:
        if zus and (zus[-1]["grundton"], zus[-1]["art"]) == (a["grundton"], a["art"]):
            zus[-1]["laenge"] = a["schritt"] + a["laenge"] - zus[-1]["schritt"]
        else:
            zus.append(dict(a))
    return zus


def _links(a, unten=43):
    """Grundton der linken Hand im Griffbereich G2–F#3."""
    return unten + ((a["grundton"] - unten) % 12)


def fassung_leicht(noten, raster):
    rechts = melodie(noten)
    links = [{"schritt": a["schritt"], "laenge": a["laenge"], "ton": _links(a), "anschlag": 70, "hand": "links"} for a in akkorde(noten, raster)]
    return rechts + links


def fassung_mittel(noten, raster):
    rechts = melodie(noten)
    links = []
    for a in akkorde(noten, raster):
        g = _links(a)
        for s in (DUR if a["art"] == "dur" else MOLL):
            links.append({"schritt": a["schritt"], "laenge": a["laenge"], "ton": g + s, "anschlag": 64, "hand": "links"})
    return rechts + links


def schreibe_midi(noten, raster, pfad, titel=""):
    """Zwei Spuren (rechts, links), Tempo-Karte aus dem Raster: Noten liegen im Takt, die Dauer bleibt wie im Original."""
    d = mido.MidiFile(type=1, ticks_per_beat=TICKS_JE_VIERTEL, charset="utf8")  # Songtitel dürfen alles enthalten
    tempo = mido.MidiTrack()
    d.tracks.append(tempo)
    tempo.append(mido.MetaMessage("track_name", name=titel, time=0))
    tempo.append(mido.MetaMessage("time_signature", numerator=raster.taktart, denominator=4, time=0))
    # Tick 0 ist die erste Eins, Noten davor (Auftakt) werden um einen ganzen Takt nach hinten verschoben
    versatz = raster.erster_takt % raster.taktart * SCHRITTE_JE_VIERTEL
    fruehester = min(n["schritt"] for n in noten)
    takt = raster.taktart * SCHRITTE_JE_VIERTEL
    null = versatz - int(np.ceil(max(0, versatz - fruehester) / takt)) * takt
    letzter = 0
    vorher = None
    abstaende = np.diff(raster.schlaege)
    for i, sek in enumerate(abstaende):
        tick = (i * SCHRITTE_JE_VIERTEL - null) * TICKS_JE_SCHRITT
        if tick < 0:
            continue
        us = int(sek * 1e6)
        if vorher is None or abs(us - vorher) > 2000:
            tempo.append(mido.MetaMessage("set_tempo", tempo=us, time=tick - letzter))
            letzter = tick
            vorher = us
    for hand in ("rechts", "links"):
        spur = mido.MidiTrack()
        d.tracks.append(spur)
        spur.append(mido.MetaMessage("track_name", name=hand, time=0))
        ereignisse = []
        for n in noten:
            if n["hand"] != hand:
                continue
            a = (n["schritt"] - null) * TICKS_JE_SCHRITT
            e = a + n["laenge"] * TICKS_JE_SCHRITT
            ereignisse += [(a, 1, n["ton"], n["anschlag"]), (e, 0, n["ton"], 0)]
        t = 0
        for tick, an, ton, v in sorted(ereignisse):
            spur.append(mido.Message("note_on" if an else "note_off", note=ton, velocity=v, time=tick - t))
            t = tick
    d.save(pfad)
