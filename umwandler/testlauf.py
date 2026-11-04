"""Schritt 2: Umwandler ohne Oberfläche gegen Testaufnahmen mit bekannten Noten messen.

Aufruf: .venv/bin/python -m umwandler.testlauf
Erwartet testlauf/aufnahmen/ (test/testaufnahmen.py). Schreibt testlauf/ergebnis/<Stück>/ mit
MIDI und Hörprobe je Fassung und testlauf/ergebnis/messung.json.
"""
import json
import subprocess
import time
from pathlib import Path

import mir_eval
import numpy as np
import soundfile as sf

from . import aufbereiten as auf
from . import erkennen as erk
from . import fassungen as fas

WURZEL = Path(__file__).parent.parent
AUFNAHMEN = WURZEL / "testlauf" / "aufnahmen"
ERGEBNIS = WURZEL / "testlauf" / "ergebnis"
RENDERN = WURZEL / "test" / "rendern.swift"


def _arrays(noten):
    iv = np.array([[n["start"], max(n["ende"], n["start"] + 0.01)] for n in noten]).reshape(-1, 2)
    hz = mir_eval.util.midi_to_hz(np.array([n["ton"] for n in noten], dtype=float))
    return iv, hz


def noten_wertung(ref, est, toleranz=0.05):
    ri, rp = _arrays(ref)
    ei, ep = _arrays(est)
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=toleranz, offset_ratio=None)
    _, _, f_ende, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=toleranz, offset_ratio=0.2, offset_min_tolerance=0.05)
    paare = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=toleranz, offset_ratio=None)
    links = {i for i, n in enumerate(ref) if n["hand"] == "links"} if ref and "hand" in ref[0] else set()
    rechts = set(range(len(ref))) - links
    treffer = {i for i, _ in paare}
    return {"genauigkeit": p, "vollstaendigkeit": r, "f1": f, "f1_mit_ende": f_ende, "gefunden": len(est), "soll": len(ref),
            "falsch": len(est) - len(paare), "fehlend": len(ref) - len(paare),
            "vollst_links": len(treffer & links) / max(1, len(links)), "vollst_rechts": len(treffer & rechts) / max(1, len(rechts))}, paare


def raster_wertung(raster, ref):
    soll = np.array(ref["taktanfaenge"])
    ist = raster.taktanfaenge()
    naechster = np.array([np.min(np.abs(ist - s)) for s in soll])
    d_soll = np.median(np.diff(soll)) / raster.taktart
    return {"tempo_soll": ref["bpm"], "tempo_ist": raster.bpm, "takte_auf_der_eins": float(np.mean(naechster < d_soll / 2)),
            "abstand_ms_median": float(np.median(naechster) * 1000), "schlaege": int(len(raster.schlaege))}


def schritt_wertung(quant, ref_noten, est_noten, paare, raster, ref):
    """Wie viele richtig erkannte Noten stehen an der richtigen Stelle im Takt?"""
    takte = np.array(ref["taktanfaenge"])
    versatz = raster.erster_takt % raster.taktart * auf.SCHRITTE_JE_VIERTEL
    nach = {(n["start"], n["ton"]): n for n in quant}
    takt_ok = viertel_ok = gesamt = hand_ok = 0
    for i, j in paare:
        e = nach.get((est_noten[j]["start"], est_noten[j]["ton"]))
        if e is None:
            continue
        r = np.interp(ref_noten[i]["start"], takte, np.arange(len(takte))) * 16
        rp = int(round(r)) % 16
        ep = (e["schritt"] - versatz) % 16
        gesamt += 1
        takt_ok += rp == ep
        viertel_ok += rp % 4 == ep % 4
        hand_ok += ref_noten[i]["hand"] == e["hand"]
    return {"stelle_im_takt": takt_ok / max(1, gesamt), "stelle_im_viertel": viertel_ok / max(1, gesamt), "hand_richtig": hand_ok / max(1, gesamt)}


def schritt_zu_sek(raster, schritt):
    i = np.arange(len(raster.schlaege)) * auf.SCHRITTE_JE_VIERTEL
    d = np.median(np.diff(raster.schlaege)) / auf.SCHRITTE_JE_VIERTEL
    if schritt > i[-1]:
        return raster.schlaege[-1] + (schritt - i[-1]) * d
    if schritt < 0:
        return raster.schlaege[0] + schritt * d
    return float(np.interp(schritt, i, raster.schlaege))


def in_zeit(noten, raster):
    return [{**n, "start": max(0.0, schritt_zu_sek(raster, n["schritt"])), "ende": max(0.01, schritt_zu_sek(raster, n["schritt"] + n["laenge"]))} for n in noten]


def fassung_wertung(quant, raster, ref):
    mel = in_zeit(fas.melodie(quant), raster)
    r_mel = [{**m, "hand": "rechts"} for m in ref["melodie"]]
    mw, _ = noten_wertung(r_mel, mel, toleranz=0.1)
    ak = fas.akkorde(quant, raster)
    zeit = [(schritt_zu_sek(raster, a["schritt"]), schritt_zu_sek(raster, a["schritt"] + a["laenge"]), a) for a in ak]
    wurzel = art = n = 0
    for soll in ref["akkorde"]:
        for anteil in (0.25, 0.75):
            t = soll["start"] + anteil * (soll["ende"] - soll["start"])
            ist = next((a for s, e, a in zeit if s <= t < e), None)
            n += 1
            if ist and ist["grundton"] == soll["grundton"]:
                wurzel += 1
                terz = (ist["grundton"] + (4 if ist["art"] == "dur" else 3)) % 12
                art += terz in soll["toene"]
    return {"melodie_genauigkeit": mw["genauigkeit"], "melodie_vollstaendigkeit": mw["vollstaendigkeit"], "melodie_f1": mw["f1"],
            "grundton_richtig": wurzel / max(1, n), "akkord_richtig": art / max(1, n), "akkordwechsel": len(ak)}


def fremde_noten(ref, est, paare):
    """Falsche Noten im Band-Stück: Wie viele gehören zu einem anderen Instrument, wie viele sind Obertöne?"""
    treffer = {j for _, j in paare}
    falsch = [n for j, n in enumerate(est) if j not in treffer]
    def klingt(n, liste):
        return any(a - 0.05 <= n["start"] < e and t == n["ton"] for a, e, t, _ in liste)
    fl = sum(klingt(n, ref["andere"]["flaeche"]) for n in falsch)
    ge = sum(klingt(n, ref["andere"]["gesang"]) for n in falsch)
    ob = sum(any(abs(q["start"] - n["start"]) < 0.05 and n["ton"] - q["ton"] in (12, 19, 24) for q in ref["noten"]) for n in falsch)
    return {"falsch": len(falsch), "flaeche": fl, "gesang": ge, "oberton": ob}


def gesang_wertung(name, stimmen, sr, ref):
    """Gesangsstimme mit Basic Pitch lesen (einstimmig gemacht) und gegen die bekannte Linie messen."""
    py = WURZEL / ".venv-rueckfall" / "bin" / "python"
    if not py.exists():
        return None
    wav = ERGEBNIS / name / "stimme vocals htdemucs.wav"
    sf.write(wav, stimmen["vocals"], sr)
    aus = wav.with_suffix(".json")
    subprocess.run([str(py), str(WURZEL / "test" / "rueckfall.py"), str(wav), str(aus)], check=True, capture_output=True)
    roh = sorted(json.loads(aus.read_text()), key=lambda n: (n["start"], -n["anschlag"]))
    linie = []
    for n in roh:
        if n["ende"] - n["start"] < 0.1:
            continue
        if linie and n["start"] < linie[-1]["ende"] - 0.05:
            continue
        linie.append(n)
    soll = [{"start": a, "ende": e, "ton": t, "hand": "rechts"} for a, e, t, _ in ref["andere"]["gesang"]]
    w, _ = noten_wertung(soll, linie, toleranz=0.1)
    return {k: w[k] for k in ("genauigkeit", "vollstaendigkeit", "f1", "gefunden", "soll")}


def hoerprobe(noten, raster, ziel):
    z = in_zeit(noten, raster)
    j = ziel.with_suffix(".noten.json")
    j.write_text(json.dumps({"dauer": max(n["ende"] for n in z), "spuren": [{
        "programm": 0, "schlagzeug": False, "gain": 1.0,
        "noten": [[max(0, n["start"]), n["ende"], n["ton"], n["anschlag"]] for n in z]}]}))
    wav = ziel.with_suffix(".wav")
    subprocess.run(["swift", str(RENDERN), str(j), str(wav)], check=True)
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(wav), str(ziel.with_suffix(".m4a"))], check=True)
    wav.unlink()
    j.unlink()


def ausgeben(name, noten, raster, ordner):
    ordner.mkdir(parents=True, exist_ok=True)
    fassungen = {"original": noten, "mittel": fas.fassung_mittel(noten, raster), "leicht": fas.fassung_leicht(noten, raster)}
    for fassung, inhalt in fassungen.items():
        fas.schreibe_midi(inhalt, raster, ordner / f"{name} – {fassung}.mid", f"{name} {fassung}")
        hoerprobe(inhalt, raster, ordner / f"{name} – {fassung}")
    return {k: len(v) for k, v in fassungen.items()}


def stueck(name, varianten):
    ref = json.loads((AUFNAHMEN / f"{name}.json").read_text())
    x, sr = erk.lese_audio(AUFNAHMEN / f"{name}.wav")
    dauer = len(x) / sr
    aus = {"dauer_s": dauer, "varianten": {}}
    for variante in varianten:
        t0 = time.time()
        if variante == "direkt":
            signal, r = x, sr
        else:
            modell, stimme = variante.split(":")
            stimmen, r = erk.trenne_stimmen(x, sr, modell)
            signal = stimmen[stimme]
            sf.write(ERGEBNIS / name / f"stimme {stimme} {modell}.wav", signal, r)
            if modell == erk.TRENN_MODELL:
                aus["gesang"] = gesang_wertung(name, stimmen, r, ref)
        t1 = time.time()
        est = erk.erkenne_klavier(signal, r)
        t2 = time.time()
        wertung, paare = noten_wertung(ref["noten"], est)
        raster = auf.schaetze_raster(est)
        quant = auf.quantisiere(est, raster)
        q_noten, _ = noten_wertung(ref["noten"], in_zeit(quant, raster), toleranz=0.1)
        ergebnis = {
            "noten": wertung, "noten_nach_einrasten": {k: q_noten[k] for k in ("genauigkeit", "vollstaendigkeit", "f1")},
            "raster": raster_wertung(raster, ref), "einrasten": schritt_wertung(quant, ref["noten"], est, paare, raster, ref),
            "fassungen": fassung_wertung(quant, raster, ref),
            "sekunden": {"trennen": t1 - t0, "erkennen": t2 - t1},
        }
        if ref["andere"]:
            ergebnis["falsche_noten"] = fremde_noten(ref, est, paare)
        aus["varianten"][variante] = ergebnis
        ordner = ERGEBNIS / name / variante.replace(":", " ")
        ergebnis["notenzahl"] = ausgeben(name, quant, raster, ordner)
        print(name, variante, json.dumps(ergebnis, ensure_ascii=False, default=float), flush=True)
    return aus


if __name__ == "__main__":
    ERGEBNIS.mkdir(parents=True, exist_ok=True)
    plan = {"1-aufnahme": ["direkt"], "2-cover": ["direkt"], "3-band": ["direkt", "htdemucs:other", "htdemucs_6s:piano"]}
    for n in plan:
        (ERGEBNIS / n).mkdir(exist_ok=True)
    messung = {n: stueck(n, v) for n, v in plan.items()}
    (ERGEBNIS / "messung.json").write_text(json.dumps(messung, indent=1, ensure_ascii=False, default=float))
