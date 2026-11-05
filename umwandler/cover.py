"""Cover aus einem Band-Song: rechts die Stimme, links die Begleitung nach Bass und Akkorden.

Regeln und Herkunft stehen im Skill `.claude/skills/musik-umwandlung`. Eingabe sind die Spuren aus
`spuren.py`, Ausgabe die drei Fassungen in Sekunden samt Pedal und Tempo.
"""
import json
from dataclasses import dataclass

import librosa
import mido
import numpy as np
import soundfile as sf
from scipy.signal import medfilt, stft

STUFEN = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11}


@dataclass
class Spuren:
    grund: str
    ft: str
    lead: str
    rest: str
    stimmen: str
    akkorde: str
    instrumental: str


def griff(t3):
    """Drei Akkordtöne unterhalb von c', weit genug, damit jeder Akkord drei findet."""
    g = [m for m in range(44, 60) if m % 12 in t3]
    return g[-3:]


def lese_akkord(name):
    """'F#:min', 'D:maj/5', 'N' -> (Basston, Akkordtöne) oder None für Pause."""
    if name in ('N', 'X') or ':' not in name:
        return None
    wurzel, rest_ = name.split(':', 1)
    w = STUFEN[wurzel]
    art, _, umk = rest_.partition('/')
    moll = art.startswith('min') or art.startswith('dim')
    t3 = [w, (w + (3 if moll else 4)) % 12, (w + 7) % 12]
    bass = w
    if umk:
        schr = {'3': 4, 'b3': 3, '5': 7, '7': 11, 'b7': 10, '2': 2, '4': 5, '6': 9}.get(umk, 0)
        if umk == '3' and moll:
            schr = 3
        bass = (w + schr) % 12
    return bass, t3


def schreibe_midi(pfad, viertel_s, pedal, rechts, links, titel=''):
    """Festes Tempo und Vorlauf: Zeit im Song = Zeit in der Datei."""
    d = mido.MidiFile(type=1, ticks_per_beat=480, charset='utf8')
    k_ = mido.MidiTrack()
    d.tracks.append(k_)
    k_.append(mido.MetaMessage('track_name', name=titel, time=0))
    k_.append(mido.MetaMessage('set_tempo', tempo=int(viertel_s * 1e6), time=0))
    k_.append(mido.MetaMessage('time_signature', numerator=4, denominator=4, time=0))
    tick = lambda t_: int(round(t_ / viertel_s * 480))
    for name, liste in (('rechts', rechts), ('links', links)):
        tr_ = mido.MidiTrack()
        d.tracks.append(tr_)
        tr_.append(mido.MetaMessage('track_name', name=name, time=0))
        ev = []
        if name == 'links':
            for a_, e_ in pedal:
                ev += [(tick(a_), 2, 127, 0), (tick(e_), -1, 0, 0)]
        for n_ in liste:
            ev += [(tick(n_['start']), 1, n_['ton'], n_['anschlag']), (tick(n_['ende']), 0, n_['ton'], 0)]
        tt_ = 0
        for x_, an, m_, v_ in sorted(ev):
            if an in (2, -1):
                tr_.append(mido.Message('control_change', control=64, value=m_, time=x_ - tt_))
            else:
                tr_.append(mido.Message('note_on' if an else 'note_off', note=m_, velocity=v_, time=x_ - tt_))
            tt_ = x_
    d.save(pfad)


def baue_cover(sp: Spuren):
    c = np.load(sp.grund)
    voc, bas, oth, beats_roh, f0, per, rms, r = c['voc'], c['bas'], c['oth'], c['beats'], c['f0'], c['per'], c['rms'], int(c['r'])

    # --- Takt: gleichmäßiges Raster, wenn der Song ein festes Tempo hat ---
    d_ = np.diff(beats_roh)
    k = np.r_[0, np.cumsum(np.round(d_ / np.median(d_)))]  # Lücken im Schlagzeug-Intro zählen als ganze Schläge
    gut = np.ones(len(k), bool)
    for _ in range(5):
        a, b = np.polyfit(k[gut], beats_roh[gut], 1)
        rest = beats_roh - (a * k + b)
        gut = np.abs(rest) < max(.03, 2 * np.median(np.abs(rest)))
    print(f'Raster: {60 / a:.2f} BPM, Abweichung Median {np.median(np.abs(rest)) * 1000:.0f} ms, passend {gut.mean():.0%}', flush=True)
    SCHLAEGE = 8 if 60 / a >= 110 else 4  # schnelle Zählung ist meist das doppelte Tempo
    TAKT_S = SCHLAEGE * a
    schritt_s = TAKT_S / 32  # feinstes Raster: 32stel im notierten Tempo
    print(f'Notiertes Tempo {60 / (TAKT_S / 4):.1f} BPM, {SCHLAEGE} erkannte Schläge je Takt', flush=True)
    vor = int(np.ceil(b / a)) if b > 0 else 0
    b0 = b - vor * a
    gesamt = len(voc) / r
    schlaege = np.arange(b0, gesamt + a, a)

    def schritt(t):
        return int(round((t - b0) / schritt_s))

    def zeit(s):
        return b0 + s * schritt_s

    # --- Stimmung: Viele Produktionen liegen nicht genau auf 440 Hz ---
    _c2 = np.load(sp.ft)
    _f, _p, _r = _c2['f0'], _c2['per'], _c2['rms']
    _m = (_p > .7) & (_r > np.percentile(_r, 40))
    _mi = 69 + 12 * np.log2(np.maximum(_f[_m], 1) / 440)
    _rest = _mi - np.round(_mi)
    TUN = float(np.angle(np.sum(_p[_m] * np.exp(2j * np.pi * _rest))) / (2 * np.pi))
    print(f'Stimmung: {TUN * 100:+.0f} Cent gegen 440 Hz', flush=True)

    # --- Chroma ---
    def chroma(sig, n, lo, hi):
        f, t, S = stft(sig, r, nperseg=n, noverlap=n - 2048)
        P = np.abs(S) ** 2
        m = (f >= lo) & (f <= hi)
        pc = np.round(12 * np.log2(f[m] / 440) + 69 - TUN).astype(int) % 12
        C = np.zeros((12, P.shape[1]))
        for i in range(12):
            C[i] = P[m][pc == i].sum(0)
        return C, t

    Ch, th = chroma(oth + voc * .2, 8192, 80, 2000)
    Cb, tb = chroma(bas, 16384, 30, 300)
    Ct, tt = chroma(oth + voc + bas, 8192, 55, 2000)
    Ka = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    Km = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    pcs = Ct.sum(1)
    _, kt, ka = max([(np.corrcoef(np.roll(Ka, i), pcs)[0, 1], i, 'dur') for i in range(12)] + [(np.corrcoef(np.roll(Km, i), pcs)[0, 1], i, 'moll') for i in range(12)])
    leiter = {(kt + s) % 12 for s in ((0, 2, 4, 5, 7, 9, 11) if ka == 'dur' else (0, 2, 3, 5, 7, 8, 10))}
    print('Tonart', kt, ka, flush=True)

    # --- Stimme -> rechte Hand ---
    c2 = np.load(sp.lead)
    f0, per, rms = c2['f0'], c2['per'], c2['rms']
    per2 = medfilt(per, 5)
    laut = rms > max(np.percentile(rms, 15), rms.max() * .008)  # leise Töne nicht wegwerfen
    # Hohe Töne werden oft leise oder gehaucht gesungen: Klarer Ton zählt auch, wenn er leise ist
    schwelle_ = max(np.percentile(rms, 15), rms.max() * .008)
    stimmhaft = (per2 > .35) & laut
    leise_klar = (per2 > .5) & (rms > schwelle_ * .02) & ~stimmhaft  # nur für hohe Töne, siehe unten
    midi = np.where(stimmhaft, 69 + 12 * np.log2(np.maximum(f0, 1) / 440) - TUN, np.nan)
    for i in range(1, len(midi) - 1):  # kleine Lücken schließen
        if np.isnan(midi[i]) and not np.isnan(midi[i - 1]) and not np.isnan(midi[i + 1]):
            midi[i] = midi[i - 1]

    # Tonhöhe glätten, dann Plateaus suchen: neue Note erst, wenn der Ton wirklich wechselt (kein Vibrato, kein Anschleifen)
    gl = midi.copy()
    ok_ = ~np.isnan(midi)
    for i in np.nonzero(ok_)[0]:
        w = midi[max(0, i - 4):i + 5]
        gl[i] = np.nanmedian(w)
    gewicht = np.where(ok_, per2 * rms / (rms.max() + 1e-9), 0)

    def tonhoehe(i, j):
        """Mittlerer Ton ohne das Anschleifen am Anfang, laute und klare Stellen zählen mehr."""
        start = i + int((j - i + 1) * .25)
        idx = np.arange(start, j + 1)
        idx = idx[ok_[idx]]
        if not len(idx):
            return float(np.nanmedian(gl[i:j + 1]))
        o = np.argsort(gl[idx])
        g = np.cumsum(gewicht[idx][o])
        return float(gl[idx][o][np.searchsorted(g, g[-1] / 2)])

    roh = []  # Start, Ende, genauer Ton, Lautstärke
    i, n = 0, len(gl)
    while i < n:
        if not ok_[i]:
            i += 1
            continue
        j = i
        ton = gl[i]
        bestaetigt = 0
        teile = []
        k_ = i
        while k_ + 1 < n and (ok_[k_ + 1] or np.any(ok_[k_ + 2:k_ + 5])):  # Lücke unter 40 ms trennt nicht
            k_ += 1
            if not ok_[k_]:
                continue
            ref_ = np.nanmedian(gl[j:k_]) if k_ > j else gl[j]
            if abs(gl[k_] - ref_) > .6 and k_ + 7 < n and abs(np.nanmedian(gl[k_:k_ + 7]) - ref_) > .6:
                teile.append((j, k_ - 1))
                j = k_
        teile.append((j, k_))
        for u, v_ in teile:
            if (v_ - u + 1) * .01 >= .06:
                roh.append([u * .01, (v_ + 1) * .01, tonhoehe(u, v_), float(np.mean(rms[u:v_ + 1])), float(np.mean(per2[u:v_ + 1]))])
        i = k_ + 1
    # Wo die Hauptstimme unklar ist, aber die übrigen Stimmen klar singen, übernimmt die rechte Hand diese
    _ca = np.load(sp.ft)
    _fa, _pa, _ra = _ca['f0'], medfilt(_ca['per'], 5), _ca['rms']
    _ma = 69 + 12 * np.log2(np.maximum(_fa, 1) / 440) - TUN
    n_ = min(len(_ma), len(ok_))
    _nur = (_pa[:n_] > .6) & ~ok_[:n_] & (_ra[:n_] > np.percentile(_ra, 40))
    i, zusatz = 0, 0
    while i < n_:
        if not _nur[i]:
            i += 1
            continue
        j = i
        while j + 1 < n_ and _nur[j + 1] and abs(_ma[j + 1] - np.median(_ma[i:j + 1])) <= .7:
            j += 1
        if (j - i + 1) * .01 >= .2:
            roh.append([i * .01, (j + 1) * .01, float(np.median(_ma[i:j + 1])), float(np.mean(_ra[i:j + 1])) * .7, float(np.mean(_pa[i:j + 1]))])
            zusatz += 1
        i = j + 1
    roh.sort(key=lambda x: x[0])
    print('Aus den übrigen Stimmen ergänzt:', zusatz, flush=True)
    # Leise, aber klare Töne bleiben nur, wenn sie über der Umgebung liegen. So fehlen keine Höhen, aber Silbenpausen bleiben Pausen.
    n_ = min(len(leise_klar), len(midi))
    _mi_roh = 69 + 12 * np.log2(np.maximum(f0, 1) / 440) - TUN
    i, gerettet = 0, 0
    _vorhanden = sorted(roh, key=lambda x: x[0])
    while i < n_:
        if not leise_klar[i]:
            i += 1
            continue
        j = i
        while j + 1 < n_ and leise_klar[j + 1] and abs(_mi_roh[j + 1] - np.median(_mi_roh[i:j + 1])) <= .7:
            j += 1
        if (j - i + 1) * .01 >= .22:
            ton_ = float(np.median(_mi_roh[i:j + 1]))
            um_ = [x[2] for x in _vorhanden if abs(x[0] - i * .01) < 2]
            dauer_ = (j - i + 1) * .01
            vor_ = [x for x in _vorhanden if 0 <= x[0] - (j + 1) * .01 < .7 and round(x[2]) % 12 == round(ton_) % 12]
            nach_ = [x for x in _vorhanden if 0 <= i * .01 - x[1] < .3 and round(x[2]) % 12 == round(ton_) % 12]
            in_lage = um_ and abs(ton_ - np.median(um_)) <= 7 and dauer_ >= .4 and np.mean(per2[i:j + 1]) >= .75
            hoch_ = um_ and ton_ >= np.median(um_) + 2.5
            if (hoch_ or in_lage) and not vor_ and not nach_:
                roh.append([i * .01, (j + 1) * .01, ton_, float(np.median(rms[rms > 0])), float(np.mean(per2[i:j + 1]))])
                gerettet += 1
        i = j + 1
    roh.sort(key=lambda x: x[0])
    print('Leise hohe Töne gerettet:', gerettet, flush=True)
    # Mehrstimmiger Gesang: Wo CREPE keinen Ton lesen kann, aber Gesang klingt, liest Basic Pitch die oberste Stimme
    _bp = json.load(open(sp.stimmen))
    _vr = librosa.feature.rms(y=voc, frame_length=1024, hop_length=441)[0]
    _vs = np.percentile(_vr, 55)
    _frei = np.ones(len(midi), bool)
    for x in roh:
        _frei[max(0, int(x[0] * 100) - 8):int(x[1] * 100) + 8] = False
    _bp_neu = []
    for n_ in sorted(_bp, key=lambda x: (x['start'], -x['ton'])):
        a_i, e_i = int(n_['start'] * 100), int(n_['ende'] * 100)
        if e_i - a_i < 15 or e_i >= len(midi) or n_['ton'] < 52:
            continue
        if _frei[a_i:e_i].mean() < .8 or _vr[a_i:min(e_i, len(_vr))].mean() < _vs:
            continue
        _um = [x[2] for x in roh if abs(x[0] - n_['start']) < 3]
        if not _um or abs(n_['ton'] - np.median(_um)) > 5:
            continue  # Tiefe oder hohe Nebenstimme, nicht die Melodie
        _frei[a_i:e_i] = False
        _bp_neu.append([n_['start'], n_['ende'], float(n_['ton']), float(_vr[a_i:e_i].mean()) * .9, .7])
    print('Aus Basic Pitch ergänzt:', len(_bp_neu), flush=True)
    roh += _bp_neu
    roh.sort(key=lambda x: x[0])
    # Gesang in Oktaven: Klingt gleichzeitig dieselbe Stimme eine Oktave höher, trägt die obere die Melodie
    _bp_arr = [(n_['start'], n_['ende'], n_['ton']) for n_ in _bp if n_['ende'] - n_['start'] >= .12]
    gehoben = []
    for x in roh:
        d_ = x[1] - x[0]
        if d_ < .2:
            continue
        ziel_ = round(x[2]) + 12
        ueber = sum(max(0, min(e_, x[1]) - max(a_, x[0])) for a_, e_, t_ in _bp_arr if t_ == ziel_)
        if ueber >= .5 * d_:
            x[2] += 12
            gehoben.append(round(x[0], 1))
    print('Oktave höher genommen:', len(gehoben), 'Noten', flush=True)
    # Silben auf gleichem Ton trennen: Lautstärke fällt deutlich und steigt wieder
    geteilt = []
    for a_, e_, m_, v_, kl_ in roh:
        u, w_ = int(a_ * 100), int(e_ * 100)
        if w_ - u < 18:
            geteilt.append([a_, e_, m_, v_, kl_])
            continue
        h = np.convolve(rms[u:w_], np.ones(3) / 3, 'same')
        tief = [t for t in range(4, len(h) - 4) if h[t] == h[t - 4:t + 5].min() and h[t] < .45 * min(h[max(0, t - 8):t].max(), h[t:t + 9].max())]
        start = a_
        for t in tief:
            geteilt.append([start, u * .01 + t * .01, m_, v_, kl_])
            start = u * .01 + t * .01
        geteilt.append([start, e_, m_, v_, kl_])
    roh = geteilt
    # Oktavfehler einzelner Noten an die Umgebung anpassen, kurze Ausreißer glätten
    ms = np.array([x[2] for x in roh])
    for i in range(len(roh)):
        um = np.median(ms[max(0, i - 8):i + 9])
        # Nur echte Oktavfehler korrigieren, hohe und tiefe Töne der Melodie bleiben, wo sie sind
        if abs(abs(roh[i][2] - um) - 12) <= 1.5:
            roh[i][2] -= 12 * np.sign(roh[i][2] - um)
    aus = []
    for i, x in enumerate(roh):
        d_ = x[1] - x[0]
        if d_ < .11 and 0 < i < len(roh) - 1:
            v_, h_ = roh[i - 1], roh[i + 1]
            oben_ = x[2] > v_[2] and x[2] > h_[2] and x[4] >= .6  # Spitzen nach oben sind Melodie, kein Fehler
            if not oben_ and abs(round(v_[2]) - round(h_[2])) <= 2 and abs(x[2] - v_[2]) > 2.5 and abs(x[2] - h_[2]) > 2.5 and x[0] - v_[1] < .08:
                v_[1] = x[1]  # Sprung für einen Wimpernschlag: gehört zur Nachbarnote
                continue
        aus.append(x)
    roh = aus
    # Rutscher am Phrasenende: Kurz nach unten weggleiten ist kein eigener Ton, der Ton davor zählt
    for _ in range(2):
        aus = []
        for i, x in enumerate(roh):
            nach_ = roh[i + 1][0] - x[1] if i + 1 < len(roh) else 9
            if aus and x[1] - x[0] < .12 and x[0] - aus[-1][1] < .05 and nach_ > .25 and 0 < aus[-1][2] - x[2] <= 3.5:
                aus[-1][1] = x[1]
                continue
            aus.append(x)
        roh = aus

    def einrasten(m, akkord=()):
        """Auf die Tonleiter; liegt der Ton dazwischen, gewinnt der Akkordton."""
        r0 = int(round(m))
        kand_ = [c for c in (r0 - 1, r0, r0 + 1) if c % 12 in leiter] or [r0]  # Popgesang bleibt in der Tonart
        return min(kand_, key=lambda c: abs(c - m) - (.12 if c % 12 in akkord else 0))

    # Oktave: gesamte Linie über die linke Hand legen, nicht einzelne Töne
    t_arr = np.array([round(x[2]) for x in roh])
    tr = 0
    while np.percentile(t_arr + tr, 10) < 62:
        tr += 12
    while np.percentile(t_arr + tr, 10) >= 74:
        tr -= 12
    print(f'Stimme: {len(roh)} Noten, Oktave {tr:+d}', flush=True)

    # --- Akkorde und Takt-Lage ---
    DIA = []
    for w in range(12):
        for art, iv in (('dur', (0, 4, 7)), ('moll', (0, 3, 7))):
            t3 = [(w + q) % 12 for q in iv]
            if set(t3) <= leiter:
                DIA.append((w, art, t3))

    def felder(ph):
        a0 = b0 + ph * a
        while a0 - TAKT_S > -a:
            a0 -= TAKT_S
        return np.arange(a0, gesamt, TAKT_S)

    def bewerte(st_):
        S = np.zeros((len(st_), len(DIA)))
        B = np.zeros((len(st_), 12))
        for f, z in enumerate(st_):
            m = (th >= z) & (th < z + TAKT_S)
            h = Ch[:, m].mean(1) if m.any() else np.zeros(12)
            h = h / (h.sum() + 1e-9)
            q = (tb >= z) & (tb < z + TAKT_S * .3)
            bb = Cb[:, q].mean(1) if q.any() else np.zeros(12)
            bb = bb / (bb.sum() + 1e-9)
            B[f] = bb
            for i_, (_, _, t3) in enumerate(DIA):
                S[f, i_] = h[t3].sum() + .25 * bb[t3].sum()
        return S, B

    def viterbi(S, kosten=.05):
        D, Zv = S[0].copy(), []
        for f in range(1, len(S)):
            K = D[:, None] - kosten + kosten * np.eye(len(DIA))
            Zv.append(K.argmax(0))
            D = S[f] + K.max(0)
        p = [int(D.argmax())]
        for z in Zv[::-1]:
            p.append(int(z[p[-1]]))
        return p[::-1], float(D.max())

    kand = []
    for ph in range(SCHLAEGE):
        st_ = felder(ph)
        S, B = bewerte(st_)
        p, w = viterbi(S)
        # Der Bass setzt auf der Eins neu an: Stärke des Bass-Einsatzes direkt auf der Taktgrenze
        e_b = librosa.feature.rms(y=bas, frame_length=2048, hop_length=512)[0]
        fl = np.maximum(0, np.diff(e_b, prepend=e_b[0]))
        tfl = np.arange(len(fl)) * 512 / r
        an = np.mean([fl[(tfl >= z - .06) & (tfl < z + .08)].sum() for z in st_]) / (fl.mean() + 1e-9)
        # Harmoniewechsel: Bass und Akkord vor gegen nach der Taktgrenze unterscheiden sich am stärksten auf der Eins
        wb = []
        for z in st_:
            v_, n_ = (tb >= z - 1.3) & (tb < z - .15), (tb >= z + .15) & (tb < z + 1.3)
            if v_.sum() and n_.sum():
                x_, y_ = Cb[:, v_].mean(1), Cb[:, n_].mean(1)
                wb.append(1 - np.dot(x_, y_) / (np.linalg.norm(x_) * np.linalg.norm(y_) + 1e-9))
        kand.append((w / len(st_), an, ph, p, st_, B, float(np.mean(wb))))
    hoechst = max(k_[1] for k_ in kand)
    hw = max(k_[6] for k_ in kand)
    _, _, ph, pf, takte, Bx, _ = max(kand, key=lambda k_: k_[6])
    print('gewählt: Lage', ph, 'Takt ab', round(float(takte[0]), 2), '| Akkorde', [f'{DIA[i_][0]}{DIA[i_][1][0]}' for i_ in pf[:12]], flush=True)
    _e = librosa.feature.rms(y=oth + bas, frame_length=4096, hop_length=2048)[0]
    _te = np.arange(len(_e)) * 2048 / r
    _em = np.percentile(_e, 90)

    def takt_energie(z):
        m = (_te >= z) & (_te < z + TAKT_S)
        return float(_e[m].mean() / _em) if m.any() else 0.

    # Begleit-Plan: Die Bassspur ist klar und einstimmig, also bestimmt sie den Akkord.
    # Nur wo kaum Bass spielt (Intro, Pausen), entscheidet die übrige Harmonie.
    _eb = librosa.feature.rms(y=bas, frame_length=4096, hop_length=2048)[0]
    _teb = np.arange(len(_eb)) * 2048 / r
    _ebr = np.percentile(_eb, 75)

    def bass_anteil(a0, b0_):
        q = (tb >= a0) & (tb < b0_)
        h = Cb[:, q].mean(1) if q.any() else np.zeros(12)
        return h / (h.sum() + 1e-9)

    def harmonie(a0, b0_):
        q = (th >= a0) & (th < b0_)
        h = Ch[:, q].mean(1) if q.any() else np.zeros(12)
        return h / (h.sum() + 1e-9)

    def akkord_auf(wurzel, a0, b0_):
        h = harmonie(a0, b0_)
        kand_ = [d_ for d_ in DIA if d_[0] == wurzel]  # Dreiklang auf dem Basston
        if not kand_:
            kand_ = [d_ for d_ in DIA if wurzel in d_[2]]  # sonst ein Akkord, der den Basston enthält
        if not kand_:
            kand_ = [(wurzel, art, [(wurzel + q) % 12 for q in iv]) for art, iv in (('dur', (0, 4, 7)), ('moll', (0, 3, 7)))]
        return max(kand_, key=lambda d_: h[d_[2]].sum())

    AKK = json.load(open(sp.akkorde))

    def akkord_mitte(t_):
        for x in AKK:
            if x['start_time'] <= t_ < x['end_time']:
                return x['chord']
        return 'N'

    _ins_y, _ins_sr = sf.read(sp.instrumental, always_2d=True)  # enthält auch das Schlagzeug
    _ins_e = librosa.feature.rms(y=_ins_y.mean(axis=1), frame_length=4096, hop_length=2048)[0]
    _ins_t = np.arange(len(_ins_e)) * 2048 / _ins_sr
    _ins_r = np.percentile(_ins_e, 75)

    def song_laut(a0, b0_):
        m_ = (_ins_t >= a0) & (_ins_t < b0_)
        return float(_ins_e[m_].mean() / _ins_r) if m_.any() else 0.

    plan = []  # Start (s), Länge (s), Bass-Tonklasse, Akkordtöne; je halber Takt, Gleiches zusammengezogen
    stille = []  # (Start, Länge, Akkord): echte Pause, ein leiser Akkord klingt aus
    gefuellt = 0
    for z in takte:
        for a0 in (z, z + TAKT_S / 2):
            a_k = lese_akkord(akkord_mitte(a0 + TAKT_S / 4))
            if a_k is None:
                if a0 < takte[0] + 2 * TAKT_S:
                    continue
                if song_laut(a0, a0 + TAKT_S / 2) < .35:
                    # Wirkliche Pause im Song: nicht abhacken, der letzte Akkord klingt leise aus
                    if plan and song_laut(a0, a0 + TAKT_S / 2) >= .05:
                        stille.append((float(a0), float(TAKT_S / 2), plan[-1][2], plan[-1][3]))
                    continue
                # Modell unsicher, Song läuft aber: Akkord von derselben Stelle im Muster davor (4 Takte, sonst 8, sonst davor)
                for rueck in (4, 8, 12):
                    a_k = lese_akkord(akkord_mitte(a0 + TAKT_S / 4 - rueck * TAKT_S))
                    if a_k:
                        break
                if a_k is None and plan:
                    a_k = (plan[-1][2], plan[-1][3])
                if a_k is None:
                    continue
                gefuellt += 1
            b_, t3 = a_k
            if plan and plan[-1][2] == b_ and plan[-1][3] == t3 and abs(plan[-1][0] + plan[-1][1] - a0) < .01:
                plan[-1] = (plan[-1][0], plan[-1][1] + TAKT_S / 2, b_, t3)
            else:
                plan.append((float(a0), float(TAKT_S / 2), b_, t3))
    # Muster läuft je Takt weiter: lange Einträge in Takte teilen
    _pl = []
    for a0, l0, b_, t3 in plan:
        t_ = a0
        while t_ < a0 + l0 - .01:
            l_ = min(TAKT_S, a0 + l0 - t_)
            _pl.append((t_, l_, b_, t3))
            t_ += l_
    plan = _pl
    pausen = sum(1 for z in takte if lese_akkord(akkord_mitte(z + TAKT_S / 2)) is None)
    print('Takte ohne Akkord:', pausen, '| Halbtakte trotz Unsicherheit weiter begleitet:', gefuellt, flush=True)
    print('Plan:', ' '.join(str(x[2]) + ('½' if x[1] < TAKT_S else '') for x in plan), flush=True)

    def akkord_bei(t_):
        a_k = lese_akkord(akkord_mitte(t_))
        return a_k[1] if a_k else []

    # Ansatz aus der Lautstärke: Konsonanten setzen vor der erkennbaren Tonhöhe ein
    _rg = np.convolve(rms, np.ones(3) / 3, 'same')
    vorher_ende = 0.
    for x in roh:
        i_ = int(x[0] * 100)
        von_, bis_ = max(int(vorher_ende * 100) + 1, i_ - 12), min(len(_rg) - 2, i_ + 5)
        if bis_ > von_:
            anstieg = _rg[von_ + 1:bis_ + 1] - _rg[von_:bis_]
            j_ = int(anstieg.argmax())
            if anstieg[j_] > 0 and _rg[von_ + j_ + 1] >= 1.3 * max(_rg[von_ + j_], 1e-6):
                x[0] = (von_ + j_) * .01
        vorher_ende = x[1]

    LAUT = np.percentile([x[3] for x in roh], 90)
    rechts = {}
    KLAR = {}
    for a_, e_, m_, v_, kl_ in roh:
        s = schritt(a_)
        e = max(s + 1, schritt(e_))
        ton = einrasten(m_, akkord_bei(a_)) + tr
        anschlag = int(np.clip(66 + 34 * (v_ / LAUT) ** .7, 62, 104))
        if s not in rechts or rechts[s][1] < e - s:
            rechts[s] = [s, e - s, ton, anschlag]
            KLAR[s] = (kl_, abs(m_ - round(m_)))
    rechts = [rechts[s] for s in sorted(rechts)]
    # Muster aus dem Maßstab: Anschläge auf gerade Stellen und kurz vor den nächsten Schlag, nichts dazwischen
    _bar0 = schritt(takte[0])
    _ziel = {0: 0, 1: 0, 2: 2, 3: 4, 4: 4, 5: 4, 6: 6, 7: 7}
    geraster = {}
    for x in rechts:
        lage = (x[0] - _bar0) % 8
        neu_s = x[0] - lage + _ziel[lage]
        if neu_s != x[0]:
            x[1] = max(1, x[1] + x[0] - neu_s)
            KLAR[neu_s] = KLAR.get(x[0], (0, 1))
            x[0] = neu_s
        if neu_s not in geraster or geraster[neu_s][1] < x[1]:
            geraster[neu_s] = x
    rechts = [geraster[s] for s in sorted(geraster)]
    zus = []
    for x in rechts:
        if zus and x[2] == zus[-1][2] and x[0] - (zus[-1][0] + zus[-1][1]) <= 1 and x[1] <= 2:
            zus[-1][1] = x[0] + x[1] - zus[-1][0]
        else:
            zus.append(x)
    rechts = zus

    def sicher(x):
        """Der Sänger hat diesen Ton klar getroffen: hohe Klarheit, nah am Halbton."""
        k_, n_ = KLAR.get(x[0], (0, 1))
        return k_ >= .8 and n_ <= .3

    def ruhiger(liste):
        """Unter einer Sechzehntel: weg. Hin und Her auf benachbarte Töne: nur, wenn der Ton klar getroffen ist.
        So bleiben echte kleine Bewegungen, das Flackern fliegt raus."""
        KURZ = 2
        for phase in (1, 2):
            geaendert = True
            while geaendert:
                geaendert = False
                for i in range(1, len(liste) - 1):
                    a_, b_, c_ = liste[i - 1], liste[i], liste[i + 1]
                    dauer = c_[0] - b_[0]
                    if b_[0] - (a_[0] + a_[1]) > 4 or b_[2] == a_[2]:
                        continue
                    spitze = b_[2] > a_[2] and b_[2] >= c_[2] and KLAR.get(b_[0], (0, 1))[0] >= .6
                    weg = phase == 1 and dauer < KURZ and not spitze
                    if phase == 2 and a_[2] == c_[2] and dauer <= 4 and abs(b_[2] - a_[2]) <= 2 and not sicher(b_) and not spitze:
                        weg = True
                    if weg:
                        a_[1] = b_[0] + b_[1] - a_[0]
                        del liste[i]
                        geaendert = True
                        break
        return liste

    # Weit über der Umgebung und nicht klar getroffen: komische Tonwahl, in die Lage holen oder streichen
    _ausr = 0
    _t = np.array([x[2] for x in rechts], dtype=float)
    _neu = []
    for i, x in enumerate(rechts):
        um_ = np.median(_t[max(0, i - 6):i + 7])
        if x[2] - um_ > 5 and not sicher(x):
            _ausr += 1
            if abs(x[2] - 12 - um_) <= 5:
                x[2] -= 12
                _neu.append(x)
            continue
        _neu.append(x)
    rechts = _neu
    print('Komische hohe Töne korrigiert oder gestrichen:', _ausr, flush=True)
    rechts = ruhiger(rechts)
    # Einwürfe und Nebenstimmen: kurzer Ton weit weg von beiden Nachbarn gehört nicht zur Melodie
    vorher_n = len(rechts)
    rechts = [x for i, x in enumerate(rechts) if not (0 < i < len(rechts) - 1 and x[1] <= 3
              and abs(x[2] - rechts[i - 1][2]) >= 7 and abs(x[2] - rechts[i + 1][2]) >= 7)]
    print('Ausreißer entfernt:', vorher_n - len(rechts), flush=True)
    # Gleicher Ton direkt danach und sehr kurz: gehört zur Note davor
    zus = []
    for x in rechts:
        if zus and x[2] == zus[-1][2] and x[0] - zus[-1][0] <= 2:
            zus[-1][1] = x[0] + x[1] - zus[-1][0]
        else:
            zus.append(x)
    rechts = zus
    # Binden: Ton klingt bis zum nächsten, wenn nur eine kleine Lücke dazwischen ist
    ROH_LANG = {x[0]: x[1] for x in rechts}
    # Lautstärke folgt dem Bogen der Phrase, nicht jeder Silbe
    _v = np.array([x[3] for x in rechts], dtype=float)
    _gl = np.convolve(np.pad(_v, 3, mode='edge'), np.ones(7) / 7, 'valid')
    for x, g_ in zip(rechts, _gl):
        x[3] = int(np.clip(g_, 72, 96))
    BINDEN = 7  # Ton klingt bis zum nächsten nur über kurze Lücken, nicht über Gesangspausen
    MINDEST_AM_ENDE = 8  # letzter Ton einer Phrase klingt mindestens so lange, das Pedal trägt ihn weiter
    for x, y in zip(rechts, rechts[1:]):
        luecke = y[0] - (x[0] + x[1])
        if luecke <= BINDEN:
            x[1] = y[0] - x[0]
        else:
            x[1] = max(x[1], min(MINDEST_AM_ENDE, y[0] - x[0]))
    rechts[-1][1] = max(rechts[-1][1], MINDEST_AM_ENDE)
    print(f'Rechte Hand: {len(rechts)} Noten, Ton-Median {int(np.median([x[2] for x in rechts]))}', flush=True)
    links = []
    rechts_voll = []
    oben = 69
    schritte_r = np.array([x[0] for x in rechts])
    _f_b, _t_b, _S_b = stft(bas, r, nperseg=16384, noverlap=16384 - 2048)
    _P_b = np.abs(_S_b) ** 2

    def bass_ton(pc, a0, b0_):
        """Lage des Basstons wie in der Aufnahme: tiefe Töne bleiben tief. Ohne Bass die übliche Lage."""
        q = (_t_b >= a0) & (_t_b < b0_)
        kand_ = [m for m in range(28, 48) if m % 12 == pc]
        if not q.any() or _eb[(_teb >= a0) & (_teb < b0_)].mean() / _ebr < .3:
            return 36 + ((pc - 36) % 12)
        def en(m):
            fr = 440 * 2 ** ((m + TUN - 69) / 12)
            w = np.abs(_f_b - fr) <= fr * .03
            return _P_b[w][:, q].mean() if w.any() else 0
        return max(kand_, key=en)

    TS = schritt(takte[1]) - schritt(takte[0])
    MUSTER = ((1, 0, 1), (2, 1, 1), (3, 2, 2), (5, 0, 1), (6, 1, 1), (7, 2, 2), (9, 0, 1), (10, 1, 1), (11, 2, 2), (13, 0, 1), (14, 1, 1), (15, 2, 1))
    for z, lang_s, pc, t3 in plan:
        s = schritt(z)
        g = griff(t3)
        laenge = int(round(lang_s / schritt_s))
        if len(g) < 3 or s + laenge < 0 or takt_energie(z) < .015:
            continue  # Pause im Song: Begleitung schweigt
        tief = bass_ton(pc, z, z + lang_s)
        d = TS // 16  # Sechzehntel im notierten Tempo
        links.append((s, d, tief, 62))
        for p16, nr_, lang in MUSTER:
            if p16 * d < laenge:
                links.append((s + p16 * d, min(lang * d, laenge - p16 * d), g[nr_], 50))
    for z, lang_s, pc, t3 in stille:
        s = schritt(z)
        g = griff(t3)
        laenge = int(round(lang_s / schritt_s))
        if len(g) >= 3:
            links.append((s, laenge, 36 + ((pc - 36) % 12), 44))
            for ton in g:
                links.append((s, laenge, ton, 38))
    print('Leise Akkorde in Pausen:', len(stille), flush=True)
    for z in takte:  # Takt ohne Stimme: lange Note wie im Vorbild
        s = schritt(z)
        if not np.any((schritte_r >= s) & (schritte_r < s + TS)) and takt_energie(z) >= .015 and akkord_bei(z + .1):
            # Muster aus dem Maßstab: lange Note ohne Gesang ist die Terz des Akkords, möglichst nah an der letzten
            zt = min((m for m in range(62, 75) if m % 12 == akkord_bei(z + .1)[1]), key=lambda m: abs(m - oben))
            oben = zt
            rechts_voll.append([s, TS, zt, 64])
    lange = list(rechts_voll)  # lange Note in Takten ohne Stimme, gehört in jede Fassung

    # Mehrere Töne rechts: In kräftigen Teilen bekommt ein langer Ton auf dem Schlag einen Akkordton darunter
    zweite = []
    for x in rechts:
        z_ = zeit(x[0])
        m_ = (_teb >= z_) & (_teb < z_ + 1)
        kraeftig = m_.any() and _eb[m_].mean() / _ebr >= .6
        if kraeftig and x[1] >= 4 and x[0] % 4 == schritt(takte[0]) % 4:
            ak_ = akkord_bei(z_ + .05)
            kand_ = [m for m in range(x[2] - 9, x[2] - 2) if m % 12 in ak_ and m >= 60]
            if kand_:
                zweite.append([x[0], x[1], max(kand_), max(52, x[3] - 18)])
    print('Zweitöne rechts:', len(zweite), flush=True)
    rechts_voll += zweite
    # Hell wie das Original: Melodie-Oktave oben. In kräftigen Teilen auf längeren Tönen, in ruhigen nur auf den Spitzen.
    oktaven = []
    for i, x in enumerate(rechts):
        z_ = zeit(x[0])
        m_ = (_teb >= z_) & (_teb < z_ + 1)
        kraeftig = m_.any() and _eb[m_].mean() / _ebr >= .6
        v_ = rechts[i - 1][2] if i else x[2]
        h_ = rechts[i + 1][2] if i + 1 < len(rechts) else x[2]
        spitze = x[2] > v_ and x[2] >= h_
        if x[2] + 12 <= 96 and (kraeftig or (spitze and x[1] >= 3)):  # in kräftigen Teilen durchgehend, damit es nicht flackert
            oktaven.append([x[0], x[1], x[2] + 12, max(50, x[3] - 20)])
    print('Oktaven oben:', len(oktaven), flush=True)
    rechts_voll += oktaven
    # Andere Instrumente: Was im Rest über der Stimme liegt oder in Gesangspausen klingt, gehört in die rechte Hand
    stimme_von = np.array([x[0] for x in rechts])
    stimme_ende = np.array([x[0] + x[1] for x in rechts])
    instr = []
    for n_ in json.load(open(sp.rest)):
        if n_['ton'] < 67 or n_['ende'] - n_['start'] < .12 or n_['ton'] > 96:
            continue
        if n_['ton'] % 12 not in leiter:
            n_['ton'] += 1 if (n_['ton'] + 1) % 12 in leiter else -1  # knapp daneben erkannt, z. B. C statt C#
        laut_ = song_laut(n_['start'], n_['start'] + 1)
        _m_i = (_teb >= n_['start']) & (_teb < n_['start'] + 1)
        kraeftig_ = _m_i.any() and _eb[_m_i].mean() / _ebr >= .6
        if not (kraeftig_ or (n_['ton'] >= 76 and laut_ >= .3)):
            continue  # Muster aus dem Maßstab: ruhige Teile bleiben einstimmig, außer klar hohe Töne
        s = schritt(n_['start'])
        lage = (s - _bar0) % 8
        s = s - lage + _ziel[lage]
        e = max(s + 2, schritt(n_['ende']))
        jetzt = (stimme_von <= s) & (stimme_ende > s)
        ton_st = rechts[int(np.nonzero(jetzt)[0][0])][2] if jetzt.any() else None
        if ton_st is None or abs(n_['ton'] - ton_st) >= 3:  # nicht direkt neben die Stimme legen
            instr.append([s, e - s, int(n_['ton']), 60])
    je_takt = {}
    gefiltert = []
    for x in sorted(instr):
        t_ = x[0] // TS
        if je_takt.get(t_, 0) < 6 and not (gefiltert and gefiltert[-1][0] == x[0]):
            gefiltert.append(x)
            je_takt[t_] = je_takt.get(t_, 0) + 1
    rechts_voll = [x for x in rechts_voll if not any(x[0] <= i_[0] < x[0] + x[1] for i_ in gefiltert)] + gefiltert
    print(f'Andere Instrumente rechts: {len(gefiltert)} Noten, Ton {min(x[2] for x in gefiltert)}–{max(x[2] for x in gefiltert)}', flush=True)

    # Gesangspausen: Was dort hoch klingt, steht im Instrumental (ohne Gesang, also keine Obertöne der Stimme)
    _f_i, _t_i, _S_i = stft(_ins_y.mean(axis=1), _ins_sr, nperseg=8192, noverlap=8192 - 2205)
    _P_i = np.abs(_S_i) ** 2
    _TOENE = [m for m in range(69, 91) if m % 12 in leiter]
    _baender = {m: np.abs(_f_i - 440 * 2 ** ((m + TUN - 69) / 12)) <= 440 * 2 ** ((m + TUN - 69) / 12) * .012 for m in _TOENE}
    _alle = np.stack([_P_i[w].mean(0) for w in _baender.values()])
    _grenze = np.percentile(_alle.max(0), 60)
    # Für die Stimme zählt, wie lange wirklich gesungen wird, nicht das Halten danach
    belegt = sorted([(x[0], x[0] + min(x[1], ROH_LANG.get(x[0], x[1]) + 1)) for x in rechts] + [(x[0], x[0] + x[1]) for x in rechts_voll if x not in oktaven and x not in zweite])
    pausenfueller = []
    D16 = TS // 16
    s_ = schritt(takte[0])
    ende_s = schritt(gesamt)
    zeiger = 0
    while s_ < ende_s:
        while zeiger < len(belegt) and belegt[zeiger][1] <= s_:
            zeiger += 1
        frei = zeiger >= len(belegt) or belegt[zeiger][0] >= s_ + D16
        if frei and song_laut(zeit(s_), zeit(s_ + D16)) >= .3:
            q = (_t_i >= zeit(s_)) & (_t_i < zeit(s_ + D16))
            if q.any():
                e_ = _alle[:, q].mean(1)
                i_ = int(e_.argmax())
                if e_[i_] >= _grenze and e_[i_] >= 3 * np.median(e_):
                    ton = _TOENE[i_]
                    if pausenfueller and pausenfueller[-1][2] == ton and pausenfueller[-1][0] + pausenfueller[-1][1] == s_:
                        pausenfueller[-1][1] += D16
                    else:
                        pausenfueller.append([s_, D16, ton, 64])
        s_ += D16
    pausenfueller = [x for x in pausenfueller if x[1] >= 2 * D16]  # einzelne kurze Töne reißen die Linie nur auf
    # Gehaltene Töne enden, wo ein Füller einsetzt
    for f_ in pausenfueller:
        for x in rechts + oktaven:
            if x[0] < f_[0] < x[0] + x[1]:
                x[1] = f_[0] - x[0]
    print('Pausenfüller aus dem Instrumental:', len(pausenfueller), flush=True)
    rechts_voll += pausenfueller
    # Pedal: wird zu jedem Akkord neu getreten, damit die Töne ineinander übergehen, ohne zu verschwimmen
    _alle_p = sorted(plan + stille, key=lambda x: x[0])
    PEDAL = []
    for x in _alle_p:
        if PEDAL and PEDAL[-1][2] == (x[2], tuple(x[3])) and x[0] - PEDAL[-1][1] < .3:
            PEDAL[-1][1] = x[0] + x[1] - .04
        else:
            PEDAL.append([max(0., x[0] + .06), x[0] + x[1] - .04, (x[2], tuple(x[3]))])
    PEDAL = [p_[:2] for p_ in PEDAL]

    # Fassungen
    def in_zeit(liste, nach=0.):
        return [{'start': max(0., zeit(s)), 'ende': zeit(s + l) + nach, 'ton': t, 'anschlag': v} for s, l, t, v in liste if zeit(s + l) > 0]

    stimme = in_zeit(rechts, .05)
    lange_ = in_zeit(lange, .05)
    ganz_links = in_zeit(links)
    bass_lang = []
    for z, lang_s, pc, t3 in plan:
        s = schritt(z)
        if len(griff(t3)) >= 3 and s + int(round(lang_s / schritt_s)) >= 0 and takt_energie(z) >= .015:
            bass_lang.append((s, int(round(lang_s / schritt_s)), bass_ton(pc, z, z + lang_s), 62))
    return {
        'original': {'rechts': in_zeit(rechts + rechts_voll, .05), 'links': ganz_links},
        'mittel': {'rechts': stimme + lange_, 'links': ganz_links},
        'leicht': {'rechts': stimme + lange_, 'links': in_zeit(bass_lang)},
        'pedal': PEDAL, 'viertel_s': float(TAKT_S / 4), 'bpm': float(60 / (TAKT_S / 4)), 'takte': len(takte),
        'takt_ab': float(takte[0]), 'takt_s': float(TAKT_S),
    }
