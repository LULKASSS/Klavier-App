---
name: musik-umwandlung
description: Macht aus einem Band-Song ein spielbares Klavier-Cover (rechts Stimme, links Begleitung) und prüft es. Nutzen bei Arbeit am Umwandler des Klavier-Trainers, bei „klingt nicht wie der Song“, falschen Tönen, Stimme, Akkorden, Takt oder Vergleich mit einem Maßstab.
---

# Musik-Umwandlung

Ziel ist, dass Lukas den Song am Klavier erkennt. Ein Band-Song wird arrangiert, nicht nur transkribiert. Das Klaviermodell allein taugt nur für echte Klavieraufnahmen.

## Aufbau eines Covers
1. **Takt:** Schläge erkennen (Beat This!), über den ganzen Song eine Gerade anpassen, wenn das Tempo fest ist. Beat-Tracker zählen oft das doppelte Tempo: 8 Schläge können ein Takt sein.
2. **Akkorde und Pausen:** eigenes Akkordmodell auf dem ganzen Mix (`lv-chordia`). Es findet auch Pausen (`N`), dort schweigt die Begleitung.
3. **Stimme:** Hauptstimme abtrennen (Karaoke-Modell), Tonhöhe je 10 ms (CREPE), daraus Noten.
4. **Linke Hand:** Basston, dann Akkordtöne als gebundenes Sechzehntel-Muster.
5. **Rechte Hand:** Stimme, eine Oktave über der Begleitung, wenn sie sonst darin untergeht. In Gesangspausen und über der Stimme Töne aus der Rest-Spur.
6. **Fassungen:** Leicht und Mittel leiten sich daraus ab.

## Lehren aus Glatteis (05.11.2026)
Jede davon hat Lukas erst hören müssen, also vorher prüfen:
- Ganze Linie transponieren, nie einzelne Töne falten. Nur echte Oktavfehler korrigieren, sonst fehlen Höhen und Tiefen.
- Bass nicht in eine feste Lage zwingen.
- Töne unter einer Sechzehntel und Flackern raus, aber klar getroffene kleine Schritte behalten. Zu viel Filter klingt leer, zu wenig zappelig. Maßstab: Tonwechsel je Sekunde.
- Töne binden, aber nicht über Gesangspausen halten. Pedal je halben Takt neu.
- MIDI mit festem Tempo und Vorlauf schreiben, sonst läuft sie gegen den Song weg.
- Refrains haben oft viele Backing-Stimmen: Bei Glatteis war die Hauptstimme dort nur rund die Hälfte aller Stimmen. Ob die Melodie darin liegt, muss das Ohr entscheiden, deshalb beide Fassungen anbieten.
- Pausen prüfen: `N` im Akkordmodell heißt oft nur unsicher. Begleitung schweigt nur, wenn der Song selbst leise ist (Lautstärke samt Schlagzeug), sonst Akkord aus dem Muster davor übernehmen. Sonst hört man Beat-Aussetzer.
- Über Wiederholungen abstimmen brachte bei Glatteis nichts: Gleiche Stellen ähneln sich im 32stel-Raster höchstens zu 63 %.
- Filter asymmetrisch: Kurze Spitzen nach oben sind Melodie und bleiben, kurze Ausschläge nach unten fliegen eher raus. Sonst fehlen die hohen Töne.
- Im Mix hohe Töne von Obertönen unterscheiden: F♯5 und B5 über gesungenem B3 sind Obertöne. Trotzdem klingt das Original hell, Melodie-Oktaven in der rechten Hand tragen das ins Klavier.
- Wer Tonhöhen ausgibt, rundet: Abschneiden hat F♯ als F angezeigt und eine falsche Spur gelegt.

## Muster aus dem Maßstab (Notenbild, 8 Takte)
Fassung und Maßstab Note für Note vergleichen (`.cover/diff.py`), daraus Regeln für den ganzen Song ableiten, nie Noten übernehmen:
- Anschläge im Viertel auf gerade Stellen und auf das letzte Zweiunddreißigstel vor dem Schlag.
- Takt ohne Gesang: rechts eine lange Note, die Terz des Akkords, nah an der letzten.
- Ruhige Teile bleiben rechts einstimmig, Instrumente und Zweitöne nur in kräftigen Teilen, klar hohe Instrumententöne auch sonst. Wo nur Backing-Stimmen klar singen, übernehmen diese.
- Links: tiefer Basston, dann drei Akkordtöne in Sechzehnteln, der oberste gebunden.
Die Regeln stammen aus 4 Gesangstakten einer Strophe. Für Refrains sind sie unbelegt.

## Prüfen
- **Maßstab, wenn vorhanden:** Notenbild von Hand ablesen, Balken zählen (doppelt = Sechzehntel). Tempo im Notenbild ist gerundet, auf das gemessene skalieren.
- **Was zählt:** Wie lange klingt der richtige Ton, Tonwechsel je Sekunde, Treffer links. F1 der obersten Stimme ist bei Begleitung irreführend.
- **Ganzer Song:** Ein Maßstab gilt nur für seine Takte. Immer auch den Rest gegen die Spuren messen. Der Anfang ist oft der leichteste Teil.
- **Nicht überanpassen:** nur Regeln, die für jeden Song Sinn ergeben. Der Maßstab wird gemessen, nie eingebaut.
- **Das Ohr entscheidet:** Claude kann nicht hören. Lukas nach Sekunde und Art des Fehlers fragen, nach jeder Änderung Hörprobe bereitstellen und prüfen, dass sie lädt.

## Werkzeuge
| Zweck | Werkzeug | Stand |
| --- | --- | --- |
| Hauptstimme von Backing trennen | `audio-separator`, `mel_band_roformer_karaoke_aufr33_viperx` | PyPI, braucht ffmpeg (`imageio-ffmpeg`), Modell 913 MB, 5:23 Min. für einen 3:23-Song |
| Stimmen trennen | Demucs `htdemucs_ft` | genauer als `htdemucs`, deutlich langsamer |
| Tonhöhe | `torchcrepe`, Modell `full` | läuft |
| Akkorde | `lv-chordia` | 11 s für einen Song, traf das Notenbild |
| Takt | `beat-this` | läuft |
| Cover-Modell | Etude (`Xiugapurin/Etude`) | läuft lokal in `.cover/etude` (rund 3 Min. je Song, Lukas hat es selbst installiert, weil die Umgebung Installationen von GitHub-Code blockiert). `torchcodec` ohne passendes ffmpeg: Audio-Laden in `extractor.py` und `run_separation.py` auf `soundfile` umgestellt, Backend `demucs`. Eine Spur ohne Handtrennung, rund 8 Noten/s. Modelldaten nur nicht-kommerziell |
| Cover-Modell | Pop2Piano (`transformers`) | läuft, klang für Lukas schlecht |
| Noten aus Gesang | SOME (`openvpi/SOME`) | nicht getestet |
| Songteile | `allin1` | nicht getestet |

Quellen: [Beat This!](https://pypi.org/project/beat-this/), [lv-chordia](https://pypi.org/project/lv-chordia/), [Etude](https://github.com/Xiugapurin/Etude), [SOME](https://github.com/openvpi/SOME), [allin1](https://pypi.org/project/allin1/), [Karaoke-Modelle](https://mvsep.com/news/64).

Versuche liegen unversioniert in `.cover/`, Hörproben in `testlauf/`. Keine Audio- oder MIDI-Dateien ins Repo.
