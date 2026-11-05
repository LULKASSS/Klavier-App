"""Eine Fassung hörbar machen: rendert die Noten mit dem Klavierklang von macOS nach .m4a."""
import json
import subprocess
from pathlib import Path

RENDERN = Path(__file__).parent / "rendern.swift"


def hoerprobe(noten_in_zeit, ziel):
    ziel = Path(ziel)
    j = ziel.with_name(ziel.name + ".noten.json")
    wav = ziel.with_name(ziel.name + ".wav")
    m4a = ziel.with_name(ziel.name + ".m4a")
    j.write_text(json.dumps({"dauer": max(n["ende"] for n in noten_in_zeit), "spuren": [{
        "programm": 0, "schlagzeug": False, "gain": 1.0,
        "noten": [[max(0, n["start"]), n["ende"], n["ton"], n["anschlag"]] for n in noten_in_zeit]}]}))
    subprocess.run(["swift", str(RENDERN), str(j), str(wav)], check=True, capture_output=True)
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(wav), str(m4a)], check=True, capture_output=True)
    wav.unlink()
    j.unlink()
    return m4a
