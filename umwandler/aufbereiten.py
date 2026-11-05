"""Tempo und Takt schätzen, auf Sechzehntel einrasten, Hände nach Tonhöhe trennen."""
from dataclasses import dataclass

import numpy as np

SCHRITTE_JE_VIERTEL = 4
TRENNPUNKT = 60  # c', verschiebbar


@dataclass
class Raster:
    schlaege: np.ndarray  # Sekunden je Viertel
    erster_takt: int  # Index des ersten Schlags, der auf einer Eins liegt
    taktart: int = 4

    @property
    def bpm(self):
        return 60 / float(np.median(np.diff(self.schlaege)))

    def schritt(self, sek):
        """Sekunde → Sechzehntel-Position (gebrochen), außerhalb linear fortgesetzt."""
        i = np.arange(len(self.schlaege)) * SCHRITTE_JE_VIERTEL
        s, m = self.schlaege, np.median(np.diff(self.schlaege))
        if sek < s[0]:
            return (sek - s[0]) / m * SCHRITTE_JE_VIERTEL
        if sek > s[-1]:
            return i[-1] + (sek - s[-1]) / m * SCHRITTE_JE_VIERTEL
        return float(np.interp(sek, s, i))

    def sekunde(self, schritt):
        """Sechzehntel-Position → Sekunde, außerhalb linear fortgesetzt."""
        i = np.arange(len(self.schlaege)) * SCHRITTE_JE_VIERTEL
        d = np.median(np.diff(self.schlaege)) / SCHRITTE_JE_VIERTEL
        if schritt > i[-1]:
            return float(self.schlaege[-1] + (schritt - i[-1]) * d)
        if schritt < 0:
            return float(self.schlaege[0] + schritt * d)
        return float(np.interp(schritt, i, self.schlaege))

    def in_zeit(self, noten):
        """Eingerastete Noten mit Sekunden, so klingt die Fassung."""
        return [{**n, "start": max(0.0, self.sekunde(n["schritt"])),
                 "ende": max(0.01, self.sekunde(n["schritt"] + n["laenge"]))} for n in noten]

    def taktanfaenge(self):
        return self.schlaege[self.erster_takt % self.taktart :: self.taktart]


def _glaetten(schlaege):
    """Beat-Tracker zappeln: bei gleichmäßigem Tempo Gerade anpassen, sonst gleitend glätten."""
    n = np.arange(len(schlaege))
    a = np.polyfit(n, schlaege, 1)
    gerade = np.polyval(a, n)
    if np.median(np.abs(schlaege - gerade)) < 0.02:
        return gerade
    breite = 9
    abstand = np.convolve(np.pad(np.diff(schlaege), breite // 2, mode="edge"), np.ones(breite) / breite, "valid")
    return schlaege[0] + np.concatenate([[0], np.cumsum(abstand)])


def _onset_kurve(noten, sr=100):
    """Eigene Onset-Kurve aus den erkannten Noten (robuster als aus dem Mix: Schlagzeug ist schon weg)."""
    laenge = int((max(n["start"] for n in noten) + 2) * sr)
    kurve = np.zeros(laenge)
    for n in noten:
        kurve[int(n["start"] * sr)] += (n["anschlag"] / 127) ** 2
    fenster = np.hanning(7)
    return np.convolve(kurve, fenster, "same"), sr


def _periode(kurve, sr):
    """Viertel-Abstand in Frames: Autokorrelation mit Kammfilter (Grundschlag + Vielfache), bevorzugt 60–140 BPM."""
    k = kurve - kurve.mean()
    ak = np.fft.irfft(np.abs(np.fft.rfft(k, 2 * len(k))) ** 2)[: len(k)]
    ak = ak / (ak[0] + 1e-9)
    beste, wert = None, -1e9
    for lag in range(int(sr * 60 / 180), min(int(sr * 60 / 45), len(ak) // 4)):
        bpm = 60 * sr / lag
        vorliebe = np.exp(-0.5 * (np.log2(bpm / 95) / 0.7) ** 2)
        kamm = sum(ak[min(lag * m, len(ak) - 1)] for m in (1, 2, 4)) / 3
        w = kamm * vorliebe
        if w > wert:
            beste, wert = lag, w
    return beste


def _schlaege(kurve, sr, strenge=120.0):
    """Schläge per dynamischer Programmierung (Ellis 2007): Onsets treffen, Abstand nah an der Periode halten."""
    p = _periode(kurve, sr)
    wert = kurve.astype(float).copy()
    zurueck = np.full(len(kurve), -1)
    abstand = np.arange(p // 2, 2 * p + 1)
    strafe = -strenge * np.log(abstand / p) ** 2
    for t in range(p // 2, len(kurve)):
        gueltig = abstand <= t
        kand = wert[t - abstand[gueltig]] + strafe[gueltig]
        i = int(np.argmax(kand))
        if kand[i] > 0:
            wert[t] += kand[i]
            zurueck[t] = t - abstand[gueltig][i]
    # Letzter Schlag: bestes Ende innerhalb der letzten Periode vor dem letzten Onset
    letzter_onset = int(np.nonzero(kurve > 0)[0][-1])
    t = max(range(max(0, letzter_onset - p), letzter_onset + 1), key=lambda i: wert[i])
    kette = []
    while t >= 0:
        kette.append(t)
        t = zurueck[t]
    return np.array(kette[::-1], dtype=float) / sr


def schaetze_raster(noten, taktart=4):
    kurve, sr = _onset_kurve(noten)
    frames = _schlaege(kurve, sr)
    schlaege = _glaetten(np.asarray(frames, dtype=float))
    # Nach hinten und vorn bis zu den ersten und letzten Noten verlängern
    d = np.median(np.diff(schlaege))
    while schlaege[0] - d > min(n["start"] for n in noten) - d / 2:
        schlaege = np.r_[schlaege[0] - d, schlaege]
    while schlaege[-1] < max(n["ende"] for n in noten):
        schlaege = np.r_[schlaege, schlaege[-1] + d]
    # Die Eins: dort, wo tiefe Töne und Harmoniewechsel am stärksten zusammenfallen
    wertung = np.zeros(taktart)
    for n in noten:
        i = int(np.argmin(np.abs(schlaege - n["start"])))
        if abs(schlaege[i] - n["start"]) < d / 8:
            wertung[i % taktart] += (n["anschlag"] / 127) * (2.5 if n["ton"] < 55 else 1.0)
    wechsel = _harmonie_wechsel(noten, schlaege, taktart)
    return Raster(schlaege, int(np.argmax(wertung / (wertung.max() + 1e-9) + wechsel)), taktart)


def _harmonie_wechsel(noten, schlaege, taktart):
    """Je Phase: wie stark ändert sich die Tonart-Verteilung zwischen aufeinanderfolgenden Takten?"""
    kanten = schlaege
    chroma = np.zeros((len(kanten), 12))
    for n in noten:
        i = np.searchsorted(kanten, n["start"]) - 1
        if 0 <= i < len(kanten):
            chroma[i, n["ton"] % 12] += n["anschlag"]
    wert = np.zeros(taktart)
    for phase in range(taktart):
        bl = [chroma[k : k + taktart].sum(0) for k in range(phase, len(kanten) - taktart, taktart)]
        ds = [1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9) for a, b in zip(bl, bl[1:])]
        wert[phase] = np.mean(ds) if ds else 0
    return wert / (wert.max() + 1e-9)


def quantisiere(noten, raster, trennpunkt=TRENNPUNKT):
    """Hängt an jede Note: Schritt (Sechzehntel), Länge in Schritten, Hand, Takt."""
    aus = []
    versatz = raster.erster_takt % raster.taktart * SCHRITTE_JE_VIERTEL
    for n in noten:
        a = int(round(raster.schritt(n["start"])))
        e = int(round(raster.schritt(n["ende"])))
        aus.append({**n, "schritt": a, "laenge": max(1, e - a), "hand": "rechts" if n["ton"] >= trennpunkt else "links",
                    "takt": (a - versatz) // (raster.taktart * SCHRITTE_JE_VIERTEL)})
    # Dieselbe Taste doppelt auf demselben Schritt fällt zusammen
    gesehen, rein = set(), []
    for n in sorted(aus, key=lambda n: (n["schritt"], -n["anschlag"])):
        if (n["schritt"], n["ton"]) not in gesehen:
            gesehen.add((n["schritt"], n["ton"]))
            rein.append(n)
    return sorted(rein, key=lambda n: (n["schritt"], n["ton"]))
