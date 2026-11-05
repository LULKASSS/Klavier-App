"""Rechnet aus einer Audiodatei alle Spuren für das Cover und merkt sie sich im Song-Ordner.

Das dauert beim ersten Mal einige Minuten. Wer nur die Regeln in cover.py ändert, nutzt die Spuren erneut.
"""
import json
import os
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
import torchcrepe

from . import erkennen as erk
from .cover import Spuren

WURZEL = Path(__file__).parent.parent
KARAOKE = 'mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt'


def _tonhoehe(v, sr):
    v16 = librosa.resample(v, orig_sr=sr, target_sr=16000)
    f, p = torchcrepe.predict(torch.tensor(v16, dtype=torch.float32)[None], 16000, 160, 50, 1000, 'full', batch_size=512,
                              device='mps' if torch.backends.mps.is_available() else 'cpu', return_periodicity=True)
    rms = np.array([np.sqrt(np.mean(v16[i:i + 160] ** 2)) for i in range(0, len(v16), 160)])[:f.shape[1]]
    return f[0].cpu().numpy(), p[0].cpu().numpy(), rms


def pfade(ordner):
    d = Path(ordner) / 'spuren'
    return Spuren(*[str(d / n) for n in ('grund.npz', 'ft.npz', 'lead.npz', 'rest.json', 'stimmen.json', 'akkorde.json', 'instrumental.wav')])


def berechne(audio, ordner, melde=lambda **_: None):
    """Fehlende Spuren rechnen. Rückgabe: Pfade und Wellenformen je Stimme für die Anzeige."""
    from beat_this.inference import File2Beats
    from lv_chordia.chord_recognition import chord_recognition

    sp = pfade(ordner)
    d = Path(sp.grund).parent
    d.mkdir(exist_ok=True)
    wav = d / 'song.wav'
    x, sr = None, None

    def lade():
        nonlocal x, sr
        if x is None:
            x, sr = erk.lese_audio(audio)
            if not wav.exists():
                sf.write(wav, x, sr, subtype='PCM_16')
        return x, sr

    melde(schritt='trennen')
    if not Path(sp.grund).exists():
        lade()
        st, r = erk.trenne_stimmen(x, sr, 'htdemucs')
        voc, bas, oth = st['vocals'].mean(axis=1), st['bass'].mean(axis=1), st['other'].mean(axis=1)
        beats, _ = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)(str(wav))
        f, p, rms = _tonhoehe(voc, r)
        np.savez(sp.grund, voc=voc.astype(np.float32), bas=bas.astype(np.float32), oth=oth.astype(np.float32),
                 beats=np.array(beats), f0=f, per=p, rms=rms, r=r)
    if not Path(sp.ft).exists():
        lade()
        st, r = erk.trenne_stimmen(x, sr, 'htdemucs_ft')
        f, p, rms = _tonhoehe(st['vocals'].mean(axis=1), r)
        np.savez(sp.ft, f0=f, per=p, rms=rms)

    melde(schritt='hauptstimme')
    if not Path(sp.lead).exists() or not Path(sp.instrumental).exists():
        lade()
        umgebung = {**os.environ, 'PATH': f"{WURZEL / '.venv-trennung' / 'ffmpeg-bin'}:{os.environ['PATH']}"}
        subprocess.run([str(WURZEL / '.venv-trennung' / 'bin' / 'audio-separator'), str(wav), '-m', KARAOKE, '--output_dir', str(d),
                        '--output_format', 'WAV', '--model_file_dir', str(WURZEL / '.modelle')], check=True, env=umgebung, cwd=d)
        for datei in d.glob('*(Instrumental)*.wav'):
            datei.replace(sp.instrumental)
        for datei in d.glob('*(Vocals)*.wav'):
            y, s_r = sf.read(datei, always_2d=True)
            f, p, rms = _tonhoehe(y.mean(axis=1), s_r)
            np.savez(sp.lead, f0=f, per=p, rms=rms)
            datei.unlink()

    melde(schritt='akkorde')
    c = np.load(sp.grund)
    r = int(c['r'])
    if not Path(sp.rest).exists():
        json.dump(erk.erkenne_klavier(c['oth'], r, .5), open(sp.rest, 'w'))
    if not Path(sp.stimmen).exists():
        temp = d / 'stimmen.wav'
        sf.write(temp, c['voc'], r)
        subprocess.run([str(WURZEL / '.venv-rueckfall' / 'bin' / 'python'), str(WURZEL / 'umwandler' / 'basic_pitch_lauf.py'), str(temp), sp.stimmen],
                       check=True, capture_output=True, cwd=WURZEL)
        temp.unlink()
    if not Path(sp.akkorde).exists():
        lade()
        json.dump(chord_recognition(str(wav.resolve()), 'submission'), open(sp.akkorde, 'w'))
    wav.unlink(missing_ok=True)
    return sp
