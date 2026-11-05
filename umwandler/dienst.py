"""Das Innere der App: liefert die Oberfläche aus, nimmt Dateien an, wandelt nacheinander um.

Startet und endet mit der App (desktop/main.js), nur von diesem Mac erreichbar.
Songs liegen dauerhaft in ~/Library/Application Support/Klavier-Trainer/songs/<id>/.
"""
import json
import mimetypes
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

WURZEL = Path(__file__).parent.parent
ENDUNGEN = {".m4a", ".mp3", ".wav", ".aif", ".aiff", ".flac", ".aac", ".caf", ".mp4"}
MAX_BYTES = 2 * 1024**3
ID = re.compile(r"^[0-9a-f]{12}$")
FASSUNGEN = {"leicht": "Leicht", "mittel": "Mittel", "original": "Original"}
SEGMENT = re.compile(r"Segment (\d+) / (\d+)")


class Bibliothek:
    def __init__(self, ordner, befehl=None):
        self.ordner = Path(ordner)
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.befehl = befehl or [sys.executable, "-u", "-m", "umwandler.auftrag"]
        self.warteschlange = queue.Queue()
        self.laufend = None
        self.sperre = threading.Lock()
        threading.Thread(target=self._arbeiten, daemon=True).start()
        # Was beim letzten Beenden noch nicht fertig war, läuft wieder an
        for m in self.alle():
            if m["status"] in ("wartet", "laeuft"):
                self.aendern(m["id"], status="wartet", schritt=None, anteil=0)
                self.warteschlange.put(m["id"])

    def pfad(self, sid):
        if not ID.match(sid):
            raise KeyError(sid)
        p = self.ordner / sid
        if not (p / "meta.json").exists():
            raise KeyError(sid)
        return p

    def lese(self, sid):
        return json.loads((self.pfad(sid) / "meta.json").read_text())

    def alle(self):
        aus = []
        for p in self.ordner.iterdir():
            if ID.match(p.name) and (p / "meta.json").exists():
                aus.append(json.loads((p / "meta.json").read_text()))
        return sorted(aus, key=lambda m: -m["erstellt"])

    def aendern(self, sid, **werte):
        with self.sperre:
            p = self.pfad(sid) / "meta.json"
            m = json.loads(p.read_text())
            m.update(werte)
            t = p.with_suffix(".tmp")
            t.write_text(json.dumps(m, ensure_ascii=False))
            t.replace(p)
            return m

    def anlegen(self, name, datei, band, lesen, laenge):
        endung = Path(datei).suffix.lower()
        if endung not in ENDUNGEN:
            raise ValueError("Dieses Dateiformat kenne ich nicht.")
        sid = uuid.uuid4().hex[:12]
        ordner = self.ordner / sid
        ordner.mkdir()
        ziel = "aufnahme" + endung
        with open(ordner / ziel, "wb") as f:
            rest = laenge
            while rest > 0:
                stueck = lesen(min(rest, 1024 * 1024))
                if not stueck:
                    break
                f.write(stueck)
                rest -= len(stueck)
        m = {"id": sid, "name": (name or Path(datei).stem).strip()[:120] or "Ohne Titel", "herkunft": Path(datei).name[:200], "datei": ziel,
             "band": bool(band), "status": "wartet", "schritt": None, "anteil": 0, "erstellt": time.time(), "fehler": None}
        (ordner / "meta.json").write_text(json.dumps(m, ensure_ascii=False))
        self.warteschlange.put(sid)
        return m

    def nochmal(self, sid):
        m = self.aendern(sid, status="wartet", schritt=None, anteil=0, fehler=None)
        self.warteschlange.put(sid)
        return m

    def loeschen(self, sid):
        shutil.rmtree(self.pfad(sid))

    def stoppen(self):
        """Beim Beenden der App: laufende Umwandlung abbrechen, sie startet beim nächsten Mal neu."""
        if self.laufend and self.laufend.poll() is None:
            self.laufend.terminate()

    def _arbeiten(self):
        while True:
            sid = self.warteschlange.get()
            try:
                self._umwandeln(sid)
            except KeyError:
                pass  # inzwischen gelöscht

    def _umwandeln(self, sid):
        ordner = self.pfad(sid)
        self.aendern(sid, status="laeuft", beginn=time.time())
        fehler = None
        with subprocess.Popen([*self.befehl, str(ordner)], cwd=WURZEL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace") as proz, \
                open(ordner / "protokoll.txt", "w") as protokoll:
            self.laufend = proz
            for zeile in proz.stdout:
                protokoll.write(zeile)
                protokoll.flush()
                try:
                    if zeile.startswith("@"):
                        w = json.loads(zeile[1:])
                        fehler = w.pop("fehler", fehler)
                        if "schritt" in w:
                            w["anteil"] = 0
                        if w:
                            self.aendern(sid, **w)
                    elif s := SEGMENT.search(zeile):
                        self.aendern(sid, anteil=(int(s[1]) + 1) / int(s[2]))
                except (KeyError, ValueError):
                    pass
        ok = proz.wait() == 0
        if proz.returncode in (-signal.SIGTERM, -signal.SIGKILL):
            return  # von der App beendet, nicht von einem Fehler: bleibt offen
        self.aendern(sid, status="fertig" if ok else "fehler", schritt=None, anteil=1 if ok else 0,
                     fehler=None if ok else (fehler or "Die Umwandlung ist abgebrochen."), fertig=time.time())


def baue_handler(bib, oberflaeche):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _json(self, wert, code=200):
            b = json.dumps(wert, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _fremd(self):
            """Nur die eigene Seite darf etwas ändern, nicht irgendeine Website im selben Browser."""
            herkunft = self.headers.get("Origin")
            return herkunft is not None and urlparse(herkunft).netloc != self.headers.get("Host")

        def _datei(self, pfad, name=None):
            groesse = pfad.stat().st_size
            start, ende, code = 0, groesse - 1, 200
            bereich = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
            if bereich and groesse and (bereich[1] or bereich[2]):
                if bereich[1]:
                    start = int(bereich[1])
                    ende = min(int(bereich[2]), groesse - 1) if bereich[2] else groesse - 1
                else:
                    start = max(0, groesse - int(bereich[2]))
                if start > ende:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{groesse}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                code = 206
            self.send_response(code)
            typ = "audio/midi" if pfad.suffix == ".mid" else mimetypes.guess_type(pfad.name)[0] or "application/octet-stream"
            self.send_header("Content-Type", typ)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(ende - start + 1))
            self.send_header("Cache-Control", "no-cache")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{ende}/{groesse}")
            if name:
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
            self.end_headers()
            with open(pfad, "rb") as f:
                f.seek(start)
                rest = ende - start + 1
                while rest > 0:
                    b = f.read(min(rest, 256 * 1024))
                    if not b:
                        break
                    self.wfile.write(b)
                    rest -= len(b)

        def do_GET(self):
            url = urlparse(self.path)
            teile = [unquote(t) for t in url.path.split("/") if t]
            try:
                if teile[:2] == ["api", "songs"]:
                    if len(teile) == 2:
                        return self._json(bib.alle())
                    sid = teile[2]
                    if len(teile) == 3:
                        return self._json(bib.lese(sid))
                    if len(teile) == 4:
                        return self._song_datei(sid, teile[3])
                    raise KeyError
                name = "/".join(teile) or "index.html"
                pfad = (oberflaeche / name).resolve()
                if oberflaeche.resolve() not in pfad.parents or not pfad.is_file():
                    raise KeyError
                return self._datei(pfad)
            except (KeyError, FileNotFoundError):
                return self._json({"fehler": "nicht gefunden"}, 404)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _song_datei(self, sid, datei):
            ordner = bib.pfad(sid)
            m = bib.lese(sid)
            if datei == "aufnahme":
                return self._datei(ordner / m["datei"])
            if datei == "wellen.json":
                return self._datei(ordner / datei)
            stamm, _, endung = datei.rpartition(".")
            if stamm not in FASSUNGEN or endung not in ("mid", "json", "m4a"):
                raise KeyError
            titel = "Cover" if m.get("band") and stamm == "original" else FASSUNGEN[stamm]
            name = f'{m["name"]} – {titel}.mid'.replace("/", "-") if endung == "mid" else None
            return self._datei(ordner / datei, name)

        def do_POST(self):
            if self._fremd():
                return self._json({"fehler": "fremde Seite"}, 403)
            url = urlparse(self.path)
            teile = [t for t in url.path.split("/") if t]
            laenge = int(self.headers.get("Content-Length") or 0)
            try:
                if teile == ["api", "songs"]:
                    if not 0 < laenge <= MAX_BYTES:
                        self.close_connection = True
                        return self._json({"fehler": "Die Datei ist leer oder zu groß."}, 400)
                    q = parse_qs(url.query)
                    wert = lambda k: q.get(k, [""])[0]
                    return self._json(bib.anlegen(wert("name"), wert("datei"), wert("band") == "1", self.rfile.read, laenge), 201)
                if len(teile) == 4 and teile[:2] == ["api", "songs"] and teile[3] == "nochmal":
                    self.rfile.read(laenge)
                    return self._json(bib.nochmal(teile[2]))
                raise KeyError
            except ValueError as e:
                self.close_connection = True
                return self._json({"fehler": str(e)}, 400)
            except KeyError:
                return self._json({"fehler": "nicht gefunden"}, 404)

        def do_PATCH(self):
            if self._fremd():
                return self._json({"fehler": "fremde Seite"}, 403)
            teile = [t for t in urlparse(self.path).path.split("/") if t]
            werte = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            name = str(werte.get("name", "")).strip()[:120]
            try:
                if len(teile) == 3 and teile[:2] == ["api", "songs"] and name:
                    return self._json(bib.aendern(teile[2], name=name))
                raise KeyError
            except KeyError:
                return self._json({"fehler": "nicht gefunden"}, 404)

        def do_DELETE(self):
            if self._fremd():
                return self._json({"fehler": "fremde Seite"}, 403)
            teile = [t for t in urlparse(self.path).path.split("/") if t]
            try:
                if len(teile) == 3 and teile[:2] == ["api", "songs"]:
                    if bib.lese(teile[2])["status"] == "laeuft":
                        return self._json({"fehler": "Läuft gerade."}, 409)
                    bib.loeschen(teile[2])
                    return self._json({})
                raise KeyError
            except KeyError:
                return self._json({"fehler": "nicht gefunden"}, 404)

    return Handler


def starte(port=5199, daten=None, befehl=None):
    daten = Path(daten or os.environ.get("KLAVIER_DATEN") or Path.home() / "Library/Application Support/Klavier-Trainer/songs")
    bib = Bibliothek(daten, befehl)
    server = ThreadingHTTPServer(("127.0.0.1", port), baue_handler(bib, WURZEL / "app"))
    server.daemon_threads = True
    server.bibliothek = bib
    return server


if __name__ == "__main__":
    s = starte(port=int(os.environ.get("KLAVIER_PORT", 5199)))

    def ende(*_):
        s.bibliothek.stoppen()
        os._exit(0)

    signal.signal(signal.SIGTERM, ende)
    signal.signal(signal.SIGINT, ende)
    eltern = os.getppid()

    def wache():
        # Stirbt die App, ohne aufzuräumen, geht der Dienst mit
        while os.getppid() == eltern:
            time.sleep(2)
        ende()

    threading.Thread(target=wache, daemon=True).start()
    print(f"bereit:{s.server_address[1]}", flush=True)
    s.serve_forever()
