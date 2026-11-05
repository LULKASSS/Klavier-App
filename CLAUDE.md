# Klavier-Trainer (Arbeitstitel)

## Ziel
- Wofür: Aus einer Audiodatei (meist ein Klavier-Cover) wird eine spielbare, auf Wunsch vereinfachte MIDI, die Lukas am Mac mit seinem Roland FP-30X üben kann wie in Synthesia.
- Wer, wann: Lukas, abends am Klavier, MacBook auf dem Notenpult, Kopfhörer am Klavier.
- Gelungen, wenn: Die MIDI klingt nach dem Song (Maßstab: Lukas' zwei von Hand gesetzte MIDIs, Hollow Knight und Gravity Falls); Datei rein, nach wenigen Minuten spielbar; der Wartemodus erkennt seine Anschläge; eine schwere Stelle schafft er über die Schleife.
- Abgenommen (04.11.2026):
  - Richtung „Mischung“ (Design-Fläche, Entwurf 1). Menü als obere Leiste mit Songtitel, Takt-Leiste (32 Zellen, sicher = grün, Schleife schraffiert) und Knöpfen (Hände, Tempo, Warten, Schleife, Vereinfacht, Noten, Pause). Farben links Pink #FF4D7D, rechts Gelb #FFE14D. Noten halb gefüllt mit leuchtendem Rand. Notenblatt unter dem Menü, die fallenden Noten beginnen darunter.
  - Bildschirme laut Design-Fläche, Seite „App“: Start (Animation), Klavier verbinden, Zuhause, Bibliothek, Umwandeln, Vor dem Spielen, Übungsplan, Üben, Schleife ziehen, Ergebnis, Einstellungen.
  - Zuhause: einladend, klar gegliedert. Menü oben mittig (Zuhause, Songs, Hinzufügen, Einstellungen), Serie und Stufe als kleine Pillen oben rechts, großer Bereich „Weiter, wo du warst“ mit fallenden Leuchtnoten, darunter drei ruhige Karten (gespielte Takte klein über 14 Tage, zuletzt geübte Songs, nächstes Ziel).
  - Fallende Noten kommen von außerhalb ins Bild, die Taste leuchtet beim Treffer (Start, 05.11.2026 gebaut; im Entwurf warten sie sichtbar oben und springen los).
  - Design der Entwürfe „ganz gut“ (Lukas, 04.11.2026), das Menü-Band oben bleibt aber auf jedem Bildschirm stehen, auch bei Songs (im Entwurf fehlt es dort).
- Klang (Lukas, 05.11.2026): Die Fassungen sollen wie sein Klavier klingen, nicht wie der Mac-Klang.
- Hände (05.11.2026): Lukas kam mit R/L nicht weiter. Der Knopf reagierte in der echten App, was genau hakte, ist offen. Jetzt „Rechts“/„Links“, ohne Klavier hört man nur die gewählte Hand, mit Klavier spielt die App die andere leiser, die Wahl bleibt gemerkt.
- Nicht gewollt: Umwandler als eigenes Werkzeug neben der App, Terminal-Befehle für Lukas, Tasten-Animationen, die ruckelig anfangen (Lukas, 04.11.2026, am Entwurf), Web-App auf dem iPad (Safari kann kein Web MIDI), YouTube-Download, überladenes Dashboard mit großen Kacheln und Abzeichen-Leiste, fast leere Seite.

## Stand
Mac-App mit Bibliothek, Umwandlung und Üben (05.11.2026). Nur Klavier: Erkennung mit dem Klaviermodell. Cover aus der Band: Regeln im Skill `musik-umwandlung`, Bau in `umwandler/cover.py`. Fertige MIDIs lassen sich direkt importieren. Üben: fallende Noten, Klavier per Web MIDI, Wartemodus, Hände einzeln, Tempo 30–100 %, Schleife durch Ziehen über die Takt-Leiste, Fortschritt je Takt.
Notenblatt zuschaltbar (Knopf „Noten“): zwei Zeilen zu 4 Takten mit Tonart, nur Notenköpfe ohne Hälse und Balken. Klang: Sobald ein Klavier da ist, kommt „Anhören“ der Fassung per MIDI aus dem Klavier statt aus der Datei, mit der Anschlagstärke aus dem Song (Song-Seite zeigt FP-30X oder Mac-Klang). Am Klavier noch ungeprüft.
**Üben am FP-30X von Lukas bestätigt (05.11.2026).** **Fehlt noch:** Zuhause, Einstellungen, Übungsplan, Klavier-verbinden-Bildschirm, Band leise mitlaufen, Schleifen-Ende auf den letzten vollen Ton, Trennpunkt verschieben.

Umwandlung (Stand Glatteis und Gutmensch, nur nach Lukas' Ohr und 8 Takten Notenbild geprüft): An den Gesangstakten klingt der richtige Ton 83 % der Zeit, links 92 % Treffer. Lukas: Beat gut, Stimme noch nicht 100 %, oft passt Ansatz und Länge eines Tons nicht ganz; Gutmensch 0:28–0:32 perfekt. Kürzeres Binden und freieres Raster waren messbar schlechter. Logik kann später weiter besser werden; „Neu umwandeln“ nutzt die Spuren erneut (Sekunden statt Minuten, erstes Umwandeln hochgerechnet rund 4,5-mal so lang wie der Song). Der Maßstab liegt lokal in `testlauf/vergleich/`, Versuche unversioniert in `.cover/`.

Reihenfolge laut Auftrag:
1. Repo, `CLAUDE.md`, Einrichtungsskript (erledigt)
2. Umwandler ohne Oberfläche testen (erledigt)
3. Plan und Testergebnisse gezeigt (erledigt)
4. Übungsansicht mit MIDI-Eingang und Wartemodus (gebaut, am Klavier ungeprüft)
5. Bibliothek, Vereinfachen, Schleife, Export, Notenblatt gebaut
6. `ui-pruefung`, Tests grün, Zielkarte nachziehen

## Aufbau
- `desktop/main.js`: die Mac-App (Electron). Öffnet das Fenster, startet den Dienst auf einem freien Port und beendet ihn mit der App. Lukas sieht nur eine App, kein Terminal. Die installierte App enthält nur den Rahmen und läuft aus diesem Repo-Ordner (Pfad in `wurzel.txt`, beim Bauen eingesetzt): Änderungen an `app/` und `umwandler/` wirken ohne neu Bauen.
- `app/index.html`: die Oberfläche (kein Build). Start, Songs, Hinzufügen, Umwandeln, Song. `app/ueben.js`: Üben und Web MIDI.
- `umwandler/dienst.py`: das Innere der App, wandelt nacheinander um und setzt Abgebrochenes beim nächsten Start fort. `umwandler/auftrag.py` wandelt einen Song im eigenen Prozess um, `spuren.py` rechnet die Spuren und `cover.py` baut daraus das Cover. Songs liegen in `~/Library/Application Support/Klavier-Trainer/songs/`.
- `einrichten.sh`: legt `.werkzeug/` (uv), `.venv/` (Python 3.11) und `.modelle/` an. Die App startet es beim ersten Mal selbst, falls etwas fehlt.
- `test/`: Testaufnahmen mit bekannten Noten erzeugen, Ergebnisse dagegen messen.
- `design/`: Entwürfe als Vorlage, eine `.dc.html` je Bildschirm, `canvas.json` mit Reihenfolge und Titeln. Sie brauchen die Laufzeit der Design-Fläche (`design/support.js`, nicht im Repo; aus dem Artifact „Klavier-Trainer · 4 Richtungen“, `artifact-type/dc-runtime.js`). Damit lassen sie sich lokal ansehen: `python3 -m http.server 5198 --directory design`. Die Entwürfe binden keine Bilder ein, alles ist CSS und eingebettetes SVG. Der Titel von „Zuhause“ in `canvas.json` ist veraltet (nennt Abzeichen), es gilt die Zielkarte.

## Befehle
- `npm run app:install`: baut die Mac-App und legt sie nach `/Applications`. `npm run app`: startet sie aus dem Quellcode.
- `npm test`: Tests, vor jedem Commit grün. `npm run test:app`: prüft die installierte App von außen (Start, Umwandeln, Abbruch und Fortsetzen, Hörprobe, Export), mit eigenem Profil.
- `./einrichten.sh`: Umgebung von Hand. `node test/ueben.e2e.cjs`: Üben mit simuliertem Klavier. `.venv/bin/python -m umwandler "song.m4a" zielordner [--band]`: nur für Tests, Lukas nutzt die App.
- `.venv/bin/python test/testaufnahmen.py testlauf/aufnahmen`, dann `.venv/bin/python -m umwandler.testlauf`: Messung, Ergebnis in `testlauf/ergebnis/`.

## Rahmen
- Eine Mac-App, kein getrenntes Werkzeug (Lukas, 05.11.2026). Electron statt Chrome: bringt Web MIDI mit. Läuft lokal, der Dienst ist nur von diesem Mac erreichbar.
- Klavier per USB am Mac (Bluetooth-MIDI als Alternative). Der Ton läuft als MIDI über den Klang des Klaviers in den Kopfhörer (am FP-30X bestätigt).
- Look: Leuchtstil, nur dunkel, Farben je Hand einstellbar. Bewusst anders als der helle `app-ui`-Look; Bauweise und Bedienung (Geist, Pillen, Tab/Enter, kein Titelbalken oben links) bleiben nach `app-ui`.

## Regeln
- Repo ist **öffentlich**: keine Audio-, Song- oder MIDI-Dateien (`.gitignore`), keine Anbindung an YouTube. Lukas' gekaufte Songs wandelt er mit dem fertigen Tool selbst um, sie kommen weder ins Repo noch in Tests.
- Testdaten nur selbst erzeugen (`test/`), die Stücke darin sind eigens geschrieben. Ergebnisse liegen in `testlauf/`.
- Sprache in App, Code-Kommentaren und Commits: Deutsch.
- Tests vor jedem Commit grün.
