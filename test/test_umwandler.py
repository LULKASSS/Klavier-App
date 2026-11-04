"""Tests der Aufbereitung ohne Modell: .venv/bin/python -m unittest discover -s test"""
import sys
import tempfile
import unittest
from pathlib import Path

import mido
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from umwandler import aufbereiten as auf  # noqa: E402
from umwandler import fassungen as fas  # noqa: E402


def stueck(bpm=120, takte=8):
    """Bekanntes Stück: C-Dur / a-Moll im Wechsel, links Grundton auf der Eins, rechts Akkord und Melodie."""
    v = 60 / bpm
    noten = []
    for t in range(takte):
        wurzel, drei = (48, 52) if t % 2 == 0 else (45, 48)
        a = t * 4 * v
        noten.append({"start": a, "ende": a + 2 * v, "ton": wurzel, "anschlag": 110})
        noten.append({"start": a + 2 * v, "ende": a + 3.9 * v, "ton": wurzel + 7, "anschlag": 60})
        for i in range(4):
            b = a + i * v
            noten.append({"start": b, "ende": b + v * 0.9, "ton": 72 + (i * 2 if t % 2 == 0 else -i), "anschlag": 90})
            noten.append({"start": b, "ende": b + v * 0.9, "ton": 64 if t % 2 == 0 else 60, "anschlag": 50})
    return sorted(noten, key=lambda n: n["start"])


def raster(bpm=120, takte=8):
    return auf.Raster(np.arange(takte * 4 + 1) * 60 / bpm, 0)


class Einrasten(unittest.TestCase):
    def test_leicht_daneben_landet_auf_dem_raster(self):
        n = [{"start": 0.51, "ende": 0.74, "ton": 60, "anschlag": 80}]
        q = auf.quantisiere(n, raster())[0]
        self.assertEqual((q["schritt"], q["laenge"]), (4, 2))

    def test_haende_nach_tonhoehe_und_trennpunkt(self):
        n = [{"start": 0, "ende": .5, "ton": 60, "anschlag": 80}, {"start": 0, "ende": .5, "ton": 59, "anschlag": 80}]
        self.assertEqual([x["hand"] for x in auf.quantisiere(n, raster())], ["links", "rechts"])
        self.assertEqual({x["hand"] for x in auf.quantisiere(n, raster(), trennpunkt=70)}, {"links"})

    def test_doppelter_anschlag_faellt_zusammen(self):
        n = [{"start": 0, "ende": .5, "ton": 60, "anschlag": 80}, {"start": 0.01, "ende": .5, "ton": 60, "anschlag": 90}]
        self.assertEqual(len(auf.quantisiere(n, raster())), 1)

    def test_raster_findet_tempo_und_eins(self):
        r = auf.schaetze_raster(stueck(bpm=100, takte=16))
        self.assertAlmostEqual(r.bpm, 100, delta=1.5)
        self.assertEqual(r.erster_takt % 4, 0)


class Fassungen(unittest.TestCase):
    def setUp(self):
        self.r = raster()
        self.q = auf.quantisiere(stueck(), self.r)

    def test_melodie_ist_einstimmig_und_oben(self):
        m = fas.melodie(self.q)
        schritte = [n["schritt"] for n in m]
        self.assertEqual(len(schritte), len(set(schritte)))
        self.assertTrue(all(n["ton"] >= 69 for n in m))
        for a, b in zip(m, m[1:]):
            self.assertLessEqual(a["schritt"] + a["laenge"], b["schritt"])

    def test_oktave_ueber_einem_ton_gilt_als_oberton(self):
        n = [{"schritt": s, "laenge": 4, "ton": t, "anschlag": 90}
             for s, t in ((0, 72), (4, 74), (8, 72), (8, 84), (12, 74))]
        self.assertEqual([x["ton"] for x in fas.melodie(n)], [72, 74, 72, 74])

    def test_fuellstimme_eine_oktave_tiefer_verdraengt_die_melodie_nicht(self):
        n = [{"schritt": s, "laenge": 4, "ton": t, "anschlag": 90}
             for s, t in ((0, 72), (4, 74), (8, 72), (8, 60), (12, 74))]
        self.assertEqual([x["ton"] for x in fas.melodie(n)], [72, 74, 72, 74])

    def test_auftakt_bekommt_einen_akkord(self):
        n = [{"schritt": -4, "laenge": 4, "ton": t, "anschlag": 90} for t in (48, 52, 55)]
        self.assertEqual(fas.akkorde(n, self.r)[0]["schritt"], -8)

    def test_akkorde_und_grundton(self):
        ak = fas.akkorde(self.q, self.r)
        self.assertEqual([(a["grundton"], a["art"]) for a in ak[:2]], [(0, "dur"), (9, "moll")])
        leicht = [n for n in fas.fassung_leicht(self.q, self.r) if n["hand"] == "links"]
        self.assertEqual([n["ton"] % 12 for n in leicht[:2]], [0, 9])

    def test_mittel_hat_dreiklaenge_links(self):
        links = [n for n in fas.fassung_mittel(self.q, self.r) if n["hand"] == "links"]
        self.assertEqual(sorted((n["ton"] - links[0]["ton"]) for n in links[:3]), [0, 4, 7])

    def test_original_bleibt_unberuehrt(self):
        vorher = [dict(n) for n in self.q]
        fas.fassung_leicht(self.q, self.r)
        fas.fassung_mittel(self.q, self.r)
        self.assertEqual(vorher, self.q)

    def test_songtitel_mit_sonderzeichen(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "a.mid"
            fas.schreibe_midi(self.q, self.r, p, "Größe – 夜")
            self.assertEqual(mido.MidiFile(p, charset="utf8").tracks[0].name, "Größe – 夜")

    def test_midi_hat_zwei_haende_und_richtige_laenge(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "a.mid"
            fas.schreibe_midi(self.q, self.r, p)
            d = mido.MidiFile(p)
            self.assertEqual([s.name for s in d.tracks[1:]], ["rechts", "links"])
            self.assertAlmostEqual(d.length, 16, delta=0.5)
            an = sum(m.type == "note_on" for s in d.tracks for m in s)
            self.assertEqual(an, len(self.q))


if __name__ == "__main__":
    unittest.main()
