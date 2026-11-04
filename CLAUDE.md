# Klavier-Trainer (Arbeitstitel)

## Ziel
- Wofür: Aus einer Audiodatei (meist ein Klavier-Cover) wird eine spielbare, auf Wunsch vereinfachte MIDI, die Lukas am Mac mit seinem Roland FP-30X üben kann wie in Synthesia.
- Wer, wann: Lukas, abends am Klavier, MacBook auf dem Notenpult, Kopfhörer am Klavier.
- Gelungen, wenn: Datei rein, nach wenigen Minuten spielbar; der Wartemodus erkennt seine Anschläge; eine schwere Stelle schafft er über die Schleife.
- Abgenommen (04.11.2026):
  - Richtung „Mischung“ (Design-Fläche, Entwurf 1). Menü als obere Leiste mit Songtitel, Takt-Leiste (32 Zellen, sicher = grün, Schleife schraffiert) und Knöpfen (Hände, Tempo, Warten, Schleife, Vereinfacht, Noten, Pause). Farben links Pink #FF4D7D, rechts Gelb #FFE14D. Noten halb gefüllt mit leuchtendem Rand. Notenblatt unter dem Menü, die fallenden Noten beginnen darunter.
  - Bildschirme laut Design-Fläche, Seite „App“: Start (Animation), Klavier verbinden, Zuhause, Bibliothek, Umwandeln, Vor dem Spielen, Übungsplan, Üben, Schleife ziehen, Ergebnis, Einstellungen.
  - Zuhause: einladend, klar gegliedert. Menü oben mittig (Zuhause, Songs, Hinzufügen, Einstellungen), Serie und Stufe als kleine Pillen oben rechts, großer Bereich „Weiter, wo du warst“ mit fallenden Leuchtnoten, darunter drei ruhige Karten (gespielte Takte klein über 14 Tage, zuletzt geübte Songs, nächstes Ziel).
- Nicht gewollt: Web-App auf dem iPad (Safari kann kein Web MIDI), YouTube-Download, überladenes Dashboard mit großen Kacheln und Abzeichen-Leiste, fast leere Seite.

## Stand
Schritt 1 und 2 der Reihenfolge sind gebaut, **Stopp vor Schritt 3: Lukas' Go steht aus.** Noch keine Oberfläche.
Auftrag (Quelle aller Anforderungen): `Projektmanagement Vault/03 Ideen/Klavier-Trainer – Auftrag.md`.

Messung vom 04.11.2026 gegen selbst erzeugte Aufnahmen (GS-Sample-Klavier von macOS, **kein echtes Klavier und kein echter Gesang**; Lukas' Originalsongs sind ungeprüft). F1 = Noten richtig erkannt, Melodie und Grundton aus der fertigen Fassung:

| Stück | Klaviermodell F1 | Basic Pitch F1 | Melodie F1 | Grundton | Hand richtig |
| --- | --- | --- | --- | --- | --- |
| 1 Aufnahme, einfach, freies Tempo | 0,94 | 0,90 | 1,00 | 78 % | 96 % |
| 2 Cover, dicht, Pedal | 0,94 | 0,73 | 0,78 | 100 % | 87 % |
| 3 Band, Stimmen getrennt (Rest) | 0,81 | 0,44 (ungetrennt) | 0,77 | 100 % | 86 % |
| 3 Band, ohne Trennung | 0,61 | | 0,71 | 94 % | 92 % |

Daraus für den Umwandler:
- Einstellungen: Anschlag-Schwelle 0,7 statt 0,3, Noten ab 50 ms, 1 s Stille davor (sonst fehlt der erste Anschlag). An echten Aufnahmen nachprüfen, die Schwelle ist an Sample-Klang eingestellt.
- Klaviermodell bleibt, Basic Pitch ist nur Rückfall. `htdemucs_6s` (eigene Klavier-Stimme) ist schlechter als der Rest aus `htdemucs` (F1 0,55).
- Raster: Tempo, Eins und Rasterstelle trafen in allen Stücken. Die Stücke haben aber nur gerade Achtel im 4/4, Triolen, Swing und andere Taktarten sind ungeprüft.
- Notenenden sind unzuverlässig (F1 mit Ende 0,23–0,75), nur Anschläge sind belastbar.
- Offen für Schritt 5: Wechselbass macht die Quinte zum Grundton (Stück 1). Im dichten Cover rutschen Begleittöne in die Melodie (Genauigkeit 69 %). Band: Der Rest enthält fremde Instrumente, und die gesungene Melodie fehlt in den Fassungen; Basic Pitch auf der Gesangsstimme traf nur F1 0,29 (mit Kunst-Gesang).
- Tempo: 63 s Audio in rund 35 s. Hochgerechnet (nicht gemessen) dauert ein 4-Minuten-Song gut 2 Minuten.

Reihenfolge laut Auftrag:
1. Repo, `CLAUDE.md`, Einrichtungsskript (erledigt)
2. Umwandler ohne Oberfläche testen, Notenqualität bewerten (erledigt, siehe Befehle)
3. **STOPP:** Plan und Testergebnisse zeigen, erst nach Go weiter
4. Übungsansicht mit MIDI-Eingang und Wartemodus, zuerst mit fertiger MIDI-Datei
5. Bibliothek, Vereinfachen, Schleife, Notenblatt, Export
6. `ui-pruefung`, Tests grün, Zielkarte nachziehen

## Aufbau
- `einrichten.sh`: einmal ausführen. Legt `.werkzeug/` (uv), `.venv/` (Python 3.11) und `.modelle/` an.
- `umwandler/`: Audio → Noten → drei Fassungen, ohne Oberfläche.
- `test/`: Testaufnahmen mit bekannten Noten erzeugen, Ergebnisse dagegen messen.
- `design/`: Entwürfe als Vorlage, eine `.dc.html` je Bildschirm, `canvas.json` mit Reihenfolge und Titeln. Sie brauchen die Laufzeit der Design-Fläche (`support.js` fehlt hier) und laufen allein nicht. Ansehen: claude.ai-Artifact „Klavier-Trainer · 4 Richtungen“, Seite „App“. Die Entwürfe binden keine Bilder ein, alles ist CSS und eingebettetes SVG. Der Titel von „Zuhause“ in `canvas.json` ist veraltet (nennt Abzeichen), es gilt die Zielkarte.

## Befehle
- `./einrichten.sh --rueckfall`: einmal, richtet alles ein (ohne `--rueckfall` kein Basic Pitch).
- `.venv/bin/python -m umwandler "song.m4a" zielordner [--band] [--trennpunkt 60]`: eine Datei umwandeln, schreibt Original, Mittel, Leicht.
- `.venv/bin/python test/testaufnahmen.py testlauf/aufnahmen`, dann `.venv/bin/python -m umwandler.testlauf`: Messung, Ergebnis in `testlauf/ergebnis/` (Dauer etwa 5 Minuten).
- `.venv/bin/python -m unittest discover -s test`: Tests, vor jedem Commit grün.

## Rahmen
- Läuft lokal auf dem Mac: Oberfläche im Browser (Chrome, wegen Web MIDI), dazu ein kleiner lokaler Dienst für die Umwandlung.
- Klavier per USB am Mac (Bluetooth-MIDI als Alternative). Der Ton läuft als MIDI über den Klang des Klaviers in den Kopfhörer (Annahme: das FP-30X gibt per USB empfangene Noten über seinen Klang aus, noch ungeprüft).
- Look: Leuchtstil, nur dunkel, Farben je Hand einstellbar. Bewusst anders als der helle `app-ui`-Look; Bauweise und Bedienung (Geist, Pillen, Tab/Enter, kein Titelbalken oben links) bleiben nach `app-ui`.

## Regeln
- Repo ist **öffentlich**: keine Audio-, Song- oder MIDI-Dateien (`.gitignore`), keine Anbindung an YouTube. Lukas' gekaufte Songs wandelt er mit dem fertigen Tool selbst um, sie kommen weder ins Repo noch in Tests.
- Testdaten nur selbst erzeugen (`test/`), die Stücke darin sind eigens geschrieben. Ergebnisse liegen in `testlauf/`.
- Sprache in App, Code-Kommentaren und Commits: Deutsch.
- Tests vor jedem Commit grün.
