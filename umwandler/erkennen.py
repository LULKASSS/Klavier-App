"""Audio lesen, Stimmen trennen, Klaviernoten erkennen."""
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch

WURZEL = Path(__file__).parent.parent
MODELL = WURZEL / ".modelle" / "note_F1=0.9677_pedal_F1=0.9186.pth"
TRENN_MODELL, TRENN_STIMME = "htdemucs", "other"
SCHWELLE_ANSCHLAG = 0.7  # Standard 0,3 liefert viele Obertöne (Testlauf 04.11.2026)
MIN_DAUER_S = 0.05
VORLAUF_S = 1.0  # Das Modell verschluckt Anschläge ganz am Dateianfang, deshalb Stille davor


def geraet():
    return "mps" if torch.backends.mps.is_available() else "cpu"


def lese_audio(pfad):
    """Liest alles, was macOS kennt (m4a, mp3, wav …) über afconvert. Rückgabe (Samples, Kanäle) und Rate."""
    pfad = Path(pfad)
    if pfad.suffix.lower() in (".wav", ".flac", ".aif", ".aiff"):
        return sf.read(pfad, always_2d=True)
    with tempfile.TemporaryDirectory() as t:
        ziel = Path(t) / "a.wav"
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", str(pfad), str(ziel)], check=True)
        return sf.read(ziel, always_2d=True)


def trenne_stimmen(x, sr, modell="htdemucs"):
    """Demucs: Rückgabe {Stimme: (Samples, Kanäle)} in der Modell-Rate und diese Rate."""
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    m = get_model(modell)
    m.eval()
    if sr != m.samplerate:
        x = librosa.resample(x.T, orig_sr=sr, target_sr=m.samplerate).T
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    w = torch.tensor(x.T, dtype=torch.float32)
    mitte, streu = w.mean(), w.std() + 1e-8
    with torch.no_grad():
        q = apply_model(m, ((w - mitte) / streu)[None], device=geraet(), progress=False, shifts=1, overlap=0.25)[0]
    q = q * streu + mitte
    return {n: q[i].cpu().numpy().T for i, n in enumerate(m.sources)}, m.samplerate


def erkenne_klavier(x, sr, schwelle_anschlag=SCHWELLE_ANSCHLAG):
    """ByteDance-Klaviermodell. Rückgabe: Liste {start, ende, ton, anschlag}."""
    from piano_transcription_inference import PianoTranscription, sample_rate as modell_rate

    mono = x.mean(axis=1) if x.ndim == 2 else x
    if sr != modell_rate:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=modell_rate)
    mono = np.concatenate([np.zeros(int(VORLAUF_S * modell_rate)), mono])
    with tempfile.TemporaryDirectory() as t:
        pt = PianoTranscription(device=torch.device("cpu"), checkpoint_path=str(MODELL))
        pt.onset_threshold = schwelle_anschlag
        erg = pt.transcribe(mono.astype(np.float32), str(Path(t) / "roh.mid"))
    return sorted(
        ({"start": max(0.0, float(e["onset_time"]) - VORLAUF_S), "ende": float(e["offset_time"]) - VORLAUF_S,
          "ton": int(e["midi_note"]), "anschlag": int(e["velocity"])}
         for e in erg["est_note_events"] if e["offset_time"] - e["onset_time"] >= MIN_DAUER_S and e["offset_time"] > VORLAUF_S),
        key=lambda n: (n["start"], n["ton"]),
    )
