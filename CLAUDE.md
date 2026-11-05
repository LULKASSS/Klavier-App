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
- Nicht gewollt: Umwandler als eigenes Werkzeug neben der App, Terminal-Befehle für Lukas, Tasten-Animationen, die ruckelig anfangen (Lukas, 04.11.2026, am Entwurf), Web-App auf dem iPad (Safari kann kein Web MIDI), YouTube-Download, überladenes Dashboard mit großen Kacheln und Abzeichen-Leiste, fast leere Seite.

## Stand
Mac-App steht (05.11.2026, Lukas: „bau das zusammen als service in unsrer App“): Datei rein, umwandeln, Fassungen anhören, MIDI exportieren. **Üben fehlt noch**, ebenso Zuhause, Einstellungen, Übungsplan, Schleife, Notenblatt, Trennpunkt verschieben. Erster echter Song (Glatteis, 05.11.2026): laut Lukas „wirklich schrecklich“, klingt nicht nach dem Song.

Befund Glatteis (lief ohne Trennung, Vorgabe war „Nur Klavier“): Energie Bass 46 %, Schlagzeug 39 %, Gesang 12 %, Rest 3 %, es ist also kaum etwas Klavierartiges da. Oberstimme springt im Median 9 Halbtöne, Noten 0,22 s kurz, Ton-Median 78. Lukas' Vorbilder: Sprung 3–4, Noten 0,5–1 s, Ton-Median 57–60, von Hand gesetzt. Die Messwerte oben stammen aus Stücken mit Klavier und gelten für solche Songs nicht.
Maßstab seit 05.11.2026: 8 Takte aus Lukas' Songscription-Notenbild (lokal in `testlauf/vergleich/referenz-8-takte.mid`, nicht im Repo). Aufbau dort: links ein durchgehendes Muster aus Basston und drei Akkordtönen in Sechzehnteln, rechts die Gesangsmelodie, in Takten ohne Gesang eine lange Note. Songscription fragt vorher in einer kurzen Strecke, was man will (nur Klavier, Cover aus der Band). Messung gegen diese 8 Takte, Melodie F1 (Höchstwert der Messung 0,78): App 0,08, Pop2Piano 0,55, eigene Kette (Gesang, nur Bass) 0,57. Die App trifft also fast nichts, der Hörvergleich liegt in `testlauf/vergleich/index.html`, Lukas' Urteil steht aus. Versuchsskripte liegen unversioniert in `.cover/`.
Versuch `cover2` (05.11.2026, `.cover/`): 135,00 BPM (Notenbild rundet auf 68 statt 67,5), Takt ab 1,91 s und alle Akkorde der 8 Takte ohne Hilfe vom Maßstab gefunden; links F1 0,94 und rechts 0,50 bei exaktem Ton. Vier Ursachen des schlechten Klangs waren: Melodie eine Oktave zu tief, verschobenes Taktraster, fehlende lange Noten, falsches Begleitmuster. Hörprobe in `testlauf/vergleich2/`, Lukas' Urteil steht aus. Nur an diesem einen Song geprüft.
Lukas zu `cover2`: „viel besser“, die Stimme soll öfter kleine Schritte machen und die Töne sollen ineinander übergehen. Neu daher: genauere Trennung `htdemucs_ft`, Tonhöhe ohne Anschleifen, strikt in der Tonart, Legato, Pedal, Lautstärke aus dem Gesang. Danach Lukas: zu viele schnelle Tonwechsel (ab etwa 21 s), manche Töne hören zu früh auf. Daher Töne unter einer Sechzehntel und direktes Hin und Her raus, Töne klingen bis zum nächsten. Richtiger Ton klingt an den 4 Gesangstakten 63 % der Zeit (Anfang 43 %), 0,8 Tonwechsel/s (Maßstab 1,2). Hörprobe in `testlauf/vergleich4/`, Urteil steht aus.
Offen im Code: `schreibe_midi` lässt den Vorlauf vor dem ersten Schlag weg, die MIDI startet gegenüber dem Song zu früh (wichtig, sobald Band oder Original mitlaufen). Die Eins wird bei Glatteis falsch erkannt (der Versuch nutzte Takt 1 aus dem Notenbild). Etude ist ungetestet, die Installation braucht Lukas' Freigabe.
Folge: Für Band-Songs ohne Klavier reicht Erkennen nicht, es braucht ein Arrangement (Melodie aus dem Gesang, Grundton aus dem Bass, Akkorde). Erste Probe liegt lokal in `testlauf/glatteis-probe/`, Lukas' Urteil steht aus. Akkordart dort noch unbrauchbar (fast alles Dur). Die Vorgabe „Nur Klavier“ ist bei Band-Songs falsch und gehört durch eine Erkennung ersetzt.
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
3. Plan und Testergebnisse gezeigt (erledigt)
4. Übungsansicht mit MIDI-Eingang und Wartemodus (offen, Go von Lukas steht aus)
5. Bibliothek, Hörprobe und Export gebaut; offen: Vereinfachen verbessern, Schleife, Notenblatt
6. `ui-pruefung`, Tests grün, Zielkarte nachziehen

## Aufbau
- `desktop/main.js`: die Mac-App (Electron). Öffnet das Fenster, startet den Dienst auf einem freien Port und beendet ihn mit der App. Lukas sieht nur eine App, kein Terminal. Die installierte App enthält nur den Rahmen und läuft aus diesem Repo-Ordner (Pfad in `wurzel.txt`, beim Bauen eingesetzt): Änderungen an `app/` und `umwandler/` wirken ohne neu Bauen.
- `app/index.html`: die Oberfläche (eine Datei, kein Build). Start, Songs, Hinzufügen, Umwandeln, Song.
- `umwandler/dienst.py`: das Innere der App, wandelt nacheinander um und setzt Abgebrochenes beim nächsten Start fort. `umwandler/auftrag.py` wandelt einen Song im eigenen Prozess um. Songs liegen in `~/Library/Application Support/Klavier-Trainer/songs/`.
- `einrichten.sh`: legt `.werkzeug/` (uv), `.venv/` (Python 3.11) und `.modelle/` an. Die App startet es beim ersten Mal selbst, falls etwas fehlt.
- `test/`: Testaufnahmen mit bekannten Noten erzeugen, Ergebnisse dagegen messen.
- `design/`: Entwürfe als Vorlage, eine `.dc.html` je Bildschirm, `canvas.json` mit Reihenfolge und Titeln. Sie brauchen die Laufzeit der Design-Fläche (`design/support.js`, nicht im Repo; aus dem Artifact „Klavier-Trainer · 4 Richtungen“, `artifact-type/dc-runtime.js`). Damit lassen sie sich lokal ansehen: `python3 -m http.server 5198 --directory design`. Die Entwürfe binden keine Bilder ein, alles ist CSS und eingebettetes SVG. Der Titel von „Zuhause“ in `canvas.json` ist veraltet (nennt Abzeichen), es gilt die Zielkarte.

## Befehle
- `npm run app:install`: baut die Mac-App und legt sie nach `/Applications`. `npm run app`: startet sie aus dem Quellcode.
- `npm test`: Tests, vor jedem Commit grün. `npm run test:app`: prüft die installierte App von außen (Start, Umwandeln, Abbruch und Fortsetzen, Hörprobe, Export), mit eigenem Profil.
- `./einrichten.sh --rueckfall`: Umgebung von Hand, mit Basic Pitch. `.venv/bin/python -m umwandler "song.m4a" zielordner [--band]`: nur für Tests, Lukas nutzt die App.
- `.venv/bin/python test/testaufnahmen.py testlauf/aufnahmen`, dann `.venv/bin/python -m umwandler.testlauf`: Messung, Ergebnis in `testlauf/ergebnis/`.

## Rahmen
- Eine Mac-App, kein getrenntes Werkzeug (Lukas, 05.11.2026). Electron statt Chrome: bringt Web MIDI mit. Läuft lokal, der Dienst ist nur von diesem Mac erreichbar.
- Klavier per USB am Mac (Bluetooth-MIDI als Alternative). Der Ton läuft als MIDI über den Klang des Klaviers in den Kopfhörer (Annahme: das FP-30X gibt per USB empfangene Noten über seinen Klang aus, noch ungeprüft).
- Look: Leuchtstil, nur dunkel, Farben je Hand einstellbar. Bewusst anders als der helle `app-ui`-Look; Bauweise und Bedienung (Geist, Pillen, Tab/Enter, kein Titelbalken oben links) bleiben nach `app-ui`.

## Regeln
- Repo ist **öffentlich**: keine Audio-, Song- oder MIDI-Dateien (`.gitignore`), keine Anbindung an YouTube. Lukas' gekaufte Songs wandelt er mit dem fertigen Tool selbst um, sie kommen weder ins Repo noch in Tests.
- Testdaten nur selbst erzeugen (`test/`), die Stücke darin sind eigens geschrieben. Ergebnisse liegen in `testlauf/`.
- Sprache in App, Code-Kommentaren und Commits: Deutsch.
- Tests vor jedem Commit grün.
