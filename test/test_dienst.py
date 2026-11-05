"""Tests des lokalen Dienstes, mit einem Schein-Umwandler statt des Modells."""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from umwandler import dienst  # noqa: E402

SCHEIN = """
import json, sys, pathlib
o = pathlib.Path(sys.argv[1])
if "kaputt" in json.loads((o / "meta.json").read_text())["name"]:
    print('@' + json.dumps({"fehler": "Die Datei lässt sich nicht lesen."}), flush=True)
    sys.exit(1)
print('@' + json.dumps({"dauer": 10.0}), flush=True)
print('@' + json.dumps({"schritt": "erkennen"}), flush=True)
print('Segment 1 / 2', flush=True)
for k in ("leicht", "mittel", "original"):
    (o / f"{k}.mid").write_bytes(b"MThd" + k.encode())
    (o / f"{k}.json").write_text("[[0, 1, 60, 1]]")
    (o / f"{k}.m4a").write_bytes(b"0123456789")
print('@' + json.dumps({"bpm": 96, "takte": 4, "notenzahl": {"leicht": 1, "mittel": 1, "original": 1}}), flush=True)
"""


class Dienst(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        schein = Path(self.t.name) / "schein.py"
        schein.write_text(SCHEIN)
        self.server = dienst.starte(port=0, daten=Path(self.t.name) / "songs", befehl=[sys.executable, str(schein)])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.basis = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.t.cleanup()

    def frage(self, pfad, daten=None, methode=None, kopf=None):
        r = urllib.request.Request(self.basis + pfad, data=daten, method=methode, headers=kopf or {})
        with urllib.request.urlopen(r) as a:
            return a.status, a.read(), a.headers

    def anlegen(self, name="Glatteis", datei="07_Song.m4a", band="0"):
        q = urllib.parse.urlencode({"name": name, "datei": datei, "band": band})
        _, b, _ = self.frage(f"/api/songs?{q}", b"audio", "POST")
        return json.loads(b)

    def warten(self, sid, status="fertig"):
        for _ in range(100):
            m = json.loads(self.frage(f"/api/songs/{sid}")[1])
            if m["status"] == status:
                return m
            time.sleep(0.05)
        self.fail(f"Status bleibt {m['status']}")

    def test_song_laeuft_durch_und_laesst_sich_laden(self):
        m = self.warten(self.anlegen()["id"])
        self.assertEqual((m["bpm"], m["takte"], m["dauer"]), (96, 4, 10.0))
        self.assertEqual(self.frage(f"/api/songs/{m['id']}/aufnahme")[1], b"audio")
        s, b, h = self.frage(f"/api/songs/{m['id']}/leicht.mid")
        self.assertEqual(b, b"MThdleicht")
        self.assertIn("Glatteis%20%E2%80%93%20Leicht.mid", h["Content-Disposition"])
        self.assertEqual(len(json.loads(self.frage("/api/songs")[1])), 1)

    def test_einstellungen_bleiben(self):
        self.assertEqual(json.loads(self.frage("/api/einstellungen")[1]), {})
        self.frage("/api/einstellungen", json.dumps({"haende": "r"}).encode(), "POST")
        self.assertEqual(json.loads(self.frage("/api/einstellungen")[1]), {"haende": "r"})

    def test_verlauf_zaehlt_je_tag(self):
        for _ in range(2):
            self.frage("/api/verlauf", json.dumps({"tag": "2026-11-05", "takte": 4, "sekunden": 30}).encode(), "POST")
        self.assertEqual(json.loads(self.frage("/api/verlauf")[1])["tage"]["2026-11-05"], {"takte": 8, "sekunden": 60})
        with self.assertRaises(urllib.error.HTTPError) as f:
            self.frage("/api/verlauf", json.dumps({"tag": "../boese"}).encode(), "POST")
        self.assertEqual(f.exception.code, 400)

    def test_begleitung_nimmt_die_spur_ohne_stimme(self):
        m = self.warten(self.anlegen()["id"])
        self.assertEqual(self.frage(f"/api/songs/{m['id']}/begleitung")[1], b"audio")
        spuren = self.server.bibliothek.pfad(m["id"]) / "spuren"
        spuren.mkdir()
        (spuren / "instrumental.wav").write_bytes(b"ohne")
        self.assertEqual(self.frage(f"/api/songs/{m['id']}/begleitung")[1], b"ohne")

    def test_hoerprobe_laesst_sich_vorspulen(self):
        m = self.warten(self.anlegen()["id"])
        s, b, h = self.frage(f"/api/songs/{m['id']}/leicht.m4a", kopf={"Range": "bytes=4-7"})
        self.assertEqual((s, b, h["Content-Range"]), (206, b"4567", "bytes 4-7/10"))

    def test_fehler_kommt_an_und_nochmal_geht(self):
        m = self.warten(self.anlegen(name="kaputt")["id"], "fehler")
        self.assertEqual(m["fehler"], "Die Datei lässt sich nicht lesen.")
        self.frage(f"/api/songs/{m['id']}/nochmal", b"", "POST")
        self.warten(m["id"], "fehler")

    def test_umbenennen_und_loeschen(self):
        m = self.warten(self.anlegen()["id"])
        self.frage(f"/api/songs/{m['id']}", json.dumps({"name": "Neu"}).encode(), "PATCH")
        self.assertEqual(json.loads(self.frage(f"/api/songs/{m['id']}")[1])["name"], "Neu")
        self.frage(f"/api/songs/{m['id']}", None, "DELETE")
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.frage(f"/api/songs/{m['id']}")
        self.assertEqual(e.exception.code, 404)

    def test_fremde_seite_darf_nichts_aendern(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.frage("/api/songs?datei=a.m4a", b"x", "POST", {"Origin": "https://boese.example"})
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(json.loads(self.frage("/api/songs")[1]), [])

    def test_falsches_format_und_fremde_pfade(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.frage("/api/songs?datei=virus.exe", b"x", "POST")
        self.assertEqual(e.exception.code, 400)
        for pfad in ("/api/songs/..%2F..%2Fetc", "/..%2F..%2FCLAUDE.md", "/api/songs/abc/passwd"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.frage(pfad)
            self.assertEqual(e.exception.code, 404, pfad)

    def test_beenden_laesst_umwandlung_offen(self):
        bib = self.server.bibliothek
        m = self.anlegen(name="lang")
        pfad = bib.ordner / m["id"]
        self.warten(m["id"])  # erst durchlaufen lassen, dann wie nach einem Abbruch neu einlesen
        bib.aendern(m["id"], status="laeuft")
        neu = dienst.Bibliothek(bib.ordner, bib.befehl)
        self.warten(m["id"])
        self.assertTrue((pfad / "meta.json").exists())
        self.assertIsNone(neu.lese(m["id"])["fehler"])

    def test_fortschritt_bleibt_erhalten(self):
        m = self.warten(self.anlegen()["id"])
        self.assertEqual(json.loads(self.frage(f"/api/songs/{m['id']}/fortschritt.json")[1]), {})
        self.frage(f"/api/songs/{m['id']}/fortschritt", json.dumps({"takte": {"3": 1}}).encode(), "POST")
        self.assertEqual(json.loads(self.frage(f"/api/songs/{m['id']}/fortschritt.json")[1]), {"takte": {"3": 1}})

    def test_midi_wird_angenommen(self):
        m = self.anlegen(datei="Stueck.mid")
        self.assertTrue(m["midi"])
        self.warten(m["id"])

    def test_oberflaeche_kommt_an(self):
        self.assertIn(b"Klavier-Trainer", self.frage("/")[1])


if __name__ == "__main__":
    unittest.main()
