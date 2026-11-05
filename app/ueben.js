'use strict';
/* Üben: fallende Noten über der Klaviatur, Klavier per Web MIDI, Wartemodus, Hände einzeln, Tempo, Schleife. */

const Midi = {
  ein: null, aus: null, zugang: null, hoerer: new Set(), ton: null, klingend: new Map(),
  async start() {
    if (this.zugang || !navigator.requestMIDIAccess) return;
    try {
      this.zugang = await navigator.requestMIDIAccess();
      this.zugang.onstatechange = () => this.waehlen();
      this.waehlen();
    } catch { this.zugang = null; }
  },
  waehlen() {
    const passt = (ports) => {
      const alle = [...ports.values()].filter((p) => p.state !== 'disconnected');
      return alle.find((p) => /roland|fp-?30|digital piano/i.test(p.name)) || alle[0] || null;
    };
    if (this.ein) this.ein.onmidimessage = null;
    this.ein = passt(this.zugang.inputs);
    this.aus = passt(this.zugang.outputs);
    if (this.ein) this.ein.onmidimessage = (e) => {
      const [st, ton, v] = e.data;
      if ((st & 0xF0) === 0x90 && v > 0) this.anschlag(ton, true, v);
      else if ((st & 0xF0) === 0x80 || (st & 0xF0) === 0x90) this.anschlag(ton, false, 0);
    };
    for (const h of this.hoerer) h.klavierGeaendert?.();
  },
  anschlag(ton, an, v = 90) { for (const h of this.hoerer) h.taste?.(ton, an, v); },
  note(ton, an, v = 80) {
    if (this.aus) { this.aus.send(an ? [0x90, ton, v] : [0x80, ton, 0]); return; }
    this.macTon(ton, an, v);
  },
  pedal(an) { this.aus?.send([0xB0, 64, an ? 127 : 0]); },
  stille() {
    this.aus?.send([0xB0, 64, 0]);
    this.aus?.send([0xB0, 123, 0]);
    for (const ton of [...this.klingend.keys()]) this.macTon(ton, false);
  },
  /* Ohne Klavier klingt ein einfacher Ton aus dem Mac, damit man den Song trotzdem hört */
  macTon(ton, an, v = 80) {
    if (!an) {
      const k = this.klingend.get(ton);
      if (k) {
        k.g.gain.setTargetAtTime(0, this.ton.currentTime, .12);
        k.o.stop(this.ton.currentTime + .6);
        this.klingend.delete(ton);
      }
      return;
    }
    this.ton ??= new AudioContext();
    this.ton.resume?.();
    const o = this.ton.createOscillator(), g = this.ton.createGain(), t = this.ton.currentTime;
    o.type = 'triangle';
    o.frequency.value = 440 * 2 ** ((ton - 69) / 12);
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(.16 * (v / 127), t + .008);
    g.gain.setTargetAtTime(.05 * (v / 127), t + .02, .5);
    o.connect(g).connect(this.ton.destination);
    o.start();
    this.macTon(ton, false);
    this.klingend.set(ton, {o, g});
  },
};

const UEBEN_ICON = {
  zurueck: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3 5 8l5 5"/></svg>',
  spiel: '<svg width="12" height="12" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 2l9 5-9 5z" fill="currentColor"/></svg>',
  pause: '<svg width="12" height="12" viewBox="0 0 14 14" aria-hidden="true"><rect x="2.5" y="2" width="3" height="10" rx="1" fill="currentColor"/><rect x="8.5" y="2" width="3" height="10" rx="1" fill="currentColor"/></svg>',
};
const FRUEH_S = .3;       // so lange vor dem Ziel zählt ein Anschlag schon
const GNADE_S = .25;      // ohne Warten: so lange danach zählt er noch
const VORLAUF_S = 2.5;    // vor dem ersten Ton
const STUFEN = [30, 40, 50, 60, 70, 80, 90, 100];

class Uebung {
  constructor(wurzel, song, fassung, noten, pedal, fortschritt, wechseln, zurueck) {
    Object.assign(this, {wurzel, song, fassung, pedal, wechseln, zurueck});
    this.noten = noten.map(([a, e, ton, hand], i) => ({a, e, ton, hand, i})).sort((x, y) => x.a - y.a || x.ton - y.ton);
    this.takt_s = song.takt_s || 240 / (song.bpm || 120);
    this.takt_ab = song.takt_ab || 0;
    this.ende = this.noten.length ? Math.max(...this.noten.map((n) => n.e)) : 0;
    this.taktzahl = Math.max(1, Math.ceil((this.ende - this.takt_ab) / this.takt_s));
    this.sicher = new Set(fortschritt?.[fassung]?.sicher || []);
    this.fortschritt = fortschritt || {};
    this.haende = 'beide'; this.tempo = 100; this.warten = true;
    this.schleife = null; this.laeuft = false; this.t = 0; this.gedrueckt = new Map(); this.falsch = new Map();
    this.funken = []; this.klingt = new Map(); this.werte = {}; this.fertig = false;
    this.lage = this.tastenLage();
    this.bauen();
    this.t = Math.max(0, (this.noten[0]?.a ?? 0) - VORLAUF_S);
    this.neuPlanen();
    Midi.hoerer.add(this);
    Midi.start().then(() => this.klavierGeaendert());
    this.klavierGeaendert();
    this.leben = true;
    this.davor = null;
    requestAnimationFrame((z) => this.bild(z));
    this.rs = () => this.flaeche();
    window.addEventListener('resize', this.rs);
    this.ts = (e) => this.tastatur(e);
    document.addEventListener('keydown', this.ts);
    this.ms = () => this.wach();
    this.wurzel.addEventListener('pointermove', this.ms);
  }

  beenden() {
    this.leben = false;
    this.anhalten();
    Midi.hoerer.delete(this);
    window.removeEventListener('resize', this.rs);
    document.removeEventListener('keydown', this.ts);
    this.wurzel.removeEventListener('click', this.ks);
    this.wurzel.removeEventListener('pointermove', this.ms);
    clearTimeout(this.ruhe);
    this.speichern();
    this.wurzel.innerHTML = '';
    this.wurzel.hidden = true;
  }

  /* ---------- Plan ---------- */
  aktiv(n) { return this.haende === 'beide' || (this.haende === 'r' ? n.hand === 1 : n.hand === 0); }
  mitKlavier() { return !!Midi.ein; }

  neuPlanen() {
    // Ohne Klavier gibt es nichts zu drücken: Die App spielt alles selbst
    const zuSpielen = this.noten.filter((n) => this.mitKlavier() && this.aktiv(n));
    this.gruppen = [];
    for (const n of zuSpielen) {
      const g = this.gruppen[this.gruppen.length - 1];
      if (g && n.a - g.t < .04) { g.toene.add(n.ton); g.noten.push(n); } else this.gruppen.push({t: n.a, toene: new Set([n.ton]), noten: [n]});
    }
    this.selbst = [];
    for (const n of this.noten) {
      if (!this.mitKlavier() || !this.aktiv(n)) {
        this.selbst.push({t: n.a, an: 1, n});
        this.selbst.push({t: n.e, an: 0, n});
      }
    }
    for (const [a, e] of this.pedal) { this.selbst.push({t: a, an: 2}); this.selbst.push({t: e, an: 3}); }
    this.selbst.sort((x, y) => x.t - y.t);
    this.springen(this.t);  // Handwechsel oder Klavier einstecken unterbricht das Spielen nicht
  }

  springen(t, spielen = this.laeuft) {
    Midi.stille();
    this.klingt.clear();
    this.t = t;
    this.gi = this.gruppen?.findIndex((g) => g.t >= t - .001) ?? 0;
    if (this.gi < 0) this.gi = this.gruppen.length;
    for (const g of this.gruppen || []) g.rest = new Set(g.toene);
    this.ei = this.selbst?.findIndex((e) => e.t >= t) ?? 0;
    if (this.ei < 0) this.ei = this.selbst?.length ?? 0;
    this.laeuft = spielen;
    this.anzeigen();
  }

  takt(t) { return Math.floor((t - this.takt_ab) / this.takt_s); }

  /* ---------- Spielen ---------- */
  taste(ton, an, v) {
    if (!an) {
      this.gedrueckt.delete(ton);
      return;
    }
    const g = this.gruppen[this.gi];
    const richtig = g && g.t - this.t <= FRUEH_S && g.rest.has(ton);
    this.gedrueckt.set(ton, richtig ? (g.noten.find((n) => n.ton === ton)?.hand ?? 1) : -1);
    if (richtig) {
      g.rest.delete(ton);
      const w = this.wert(this.takt(g.t));
      w.ist += 1;
      this.spruehen(ton, g.noten.find((n) => n.ton === ton)?.hand);
      if (!g.rest.size) this.weiter();
    } else if (this.laeuft) {
      this.wert(this.takt(this.t)).falsch += 1;
      this.falsch.set(ton, performance.now());
    }
  }

  wert(k) { return (this.werte[k] ??= {ist: 0, falsch: 0}); }

  weiter() {
    this.gi += 1;
    const k = this.takt(this.gruppen[this.gi - 1].t);
    const naechste = this.gruppen[this.gi];
    if (!naechste || this.takt(naechste.t) !== k) this.taktFertig(k);
  }

  taktFertig(k) {
    const soll = this.gruppen.filter((g) => this.takt(g.t) === k).reduce((s, g) => s + g.toene.size, 0);
    const w = this.wert(k);
    if (soll && w.ist / soll >= .9 && w.falsch <= soll * .1) this.sicher.add(k);
    this.zellen();
  }

  umschalten() {
    if (this.fertig) { this.nochmal(); return; }
    this.laeuft = !this.laeuft;
    if (!this.laeuft) { this.anhalten(); this.speichern(); } else this.wach();
    this.anzeigen();
  }

  anhalten() {
    this.laeuft = false;
    Midi.stille();
    this.klingt.clear();
  }

  nochmal() {
    this.fertig = false;
    this.werte = {};
    $('.ue-ergebnis', this.wurzel)?.remove();
    const von = this.schleife ? this.takt_ab + this.schleife[0] * this.takt_s : Math.max(0, (this.noten[0]?.a ?? 0) - VORLAUF_S);
    this.springen(von, true);
  }

  schritt(dt) {
    if (!this.laeuft) return;
    let t = this.t + dt * (this.tempo / 100);
    const g = this.gruppen[this.gi];
    this.wartet = false;
    if (this.warten && g && t >= g.t) {
      t = g.t;
      this.wartet = true;
    }
    if (!this.warten) {
      while (this.gruppen[this.gi] && this.gruppen[this.gi].t + GNADE_S < t) this.weiter();
    }
    // Was die App selbst spielt
    while (this.ei < this.selbst.length && this.selbst[this.ei].t <= t) {
      const e = this.selbst[this.ei++];
      if (e.an === 1) { Midi.note(e.n.ton, true, 72); this.klingt.set(e.n.ton, e.n.hand); }
      else if (e.an === 0) { Midi.note(e.n.ton, false); this.klingt.delete(e.n.ton); }
      else Midi.pedal(e.an === 2);
    }
    this.t = t;
    if (this.schleife) {
      const bis = this.takt_ab + (this.schleife[1] + 1) * this.takt_s;
      if (t >= bis) {
        // Takt-Bewertung vor dem Rücksprung sichern, die Runde beginnt neu
        const von = this.takt_ab + this.schleife[0] * this.takt_s;
        for (let k = this.schleife[0]; k <= this.schleife[1]; k++) delete this.werte[k];
        this.springen(von, true);
        return;
      }
    }
    if (t > this.ende + 1) this.abschluss();
  }

  abschluss() {
    this.anhalten();
    this.fertig = true;
    this.speichern();
    const soll = this.gruppen.reduce((s, g) => s + g.toene.size, 0);
    const ist = Object.values(this.werte).reduce((s, w) => s + w.ist, 0);
    const prozent = soll ? Math.round(ist / soll * 100) : null;
    const box = document.createElement('div');
    box.className = 'ue-ergebnis';
    box.innerHTML = `<div class="ue-karte auftritt"><span class="klein">${esc(this.song.name)}</span>
      ${prozent === null ? '<h2>Durchgehört</h2>' : `<div class="ue-zahl">${prozent}<small>%</small></div><span>getroffen</span>`}
      <div class="ue-reihe"><button class="pille" data-ue="zurueck">Zum Song</button><button class="haupt" data-ue="nochmal">Nochmal</button></div></div>`;
    this.wurzel.append(box);
    this.anzeigen();
    $('[data-ue="nochmal"]', box).focus();
  }

  speichern() {
    this.fortschritt[this.fassung] = {sicher: [...this.sicher]};
    fetch(`/api/songs/${this.song.id}/fortschritt`, {method: 'POST', body: JSON.stringify(this.fortschritt)}).catch(() => {});
  }

  /* ---------- Oberfläche ---------- */
  bauen() {
    const m = this.song;
    const f = this.fassungen = m.midi ? ['original'] : ['leicht', 'mittel', 'original'];
    const name = {leicht: 'Leicht', mittel: 'Mittel', original: m.midi ? 'Original' : 'Cover'};
    this.namen = name;
    this.wurzel.hidden = false;
    this.wurzel.innerHTML = `<canvas class="ue-bild" aria-hidden="true"></canvas>
      <div class="ue-leiste">
        <button class="ue-rund" data-ue="zurueck" aria-label="Zurück zum Song">${UEBEN_ICON.zurueck}</button>
        <div class="ue-titel"><b>${esc(m.name)}</b><span id="ue-stand"></span></div>
        <div class="ue-zellen" id="ue-zellen" role="group" aria-label="Takte, ziehen für eine Schleife" style="grid-template-columns:repeat(${this.taktzahl},minmax(0,1fr))"></div>
        <div class="ue-knoepfe">
          <span class="ue-klavier" id="ue-klavier"></span>
          <div class="ue-wahl" role="group" aria-label="Hände">
            <button data-haende="beide" aria-pressed="true">Beide</button><button data-haende="r" aria-pressed="false">R</button><button data-haende="l" aria-pressed="false">L</button>
          </div>
          <div class="ue-tempo" role="group" aria-label="Tempo"><button data-tempo="-1" aria-label="Langsamer">−</button><span id="ue-tempo">100 %</span><button data-tempo="1" aria-label="Schneller">+</button></div>
          <button class="ue-pille" id="ue-warten" aria-pressed="true">Warten</button>
          <button class="ue-pille" id="ue-schleife" aria-pressed="false">Schleife</button>
          ${f.length > 1 ? `<button class="ue-pille an" id="ue-fassung">${name[this.fassung]}</button>` : ''}
          <button class="ue-spiel" id="ue-spiel" aria-label="Abspielen">${UEBEN_ICON.spiel}</button>
        </div>
      </div>`;
    this.cv = $('.ue-bild', this.wurzel);
    this.leiste = $('.ue-leiste', this.wurzel);
    this.flaeche();
    this.ks = (e) => this.klick(e);
    this.wurzel.addEventListener('click', this.ks);
    const z = $('#ue-zellen', this.wurzel);
    z.innerHTML = Array.from({length: this.taktzahl}, (_, i) => `<i data-takt="${i}"></i>`).join('');
    this.zellenKnoten = [...z.children];
    z.addEventListener('pointerdown', (e) => this.ziehen(e));
    this.zellen();
  }

  flaeche() {
    const r = this.wurzel.getBoundingClientRect();
    const d = window.devicePixelRatio || 1;
    this.cv.width = r.width * d;
    this.cv.height = r.height * d;
    this.c = this.cv.getContext('2d');
    this.c.setTransform(d, 0, 0, d, 0, 0);
    this.b = r.width; this.h = r.height;
  }

  klick(e) {
    const t = e.target.closest('button');
    if (!t) return;
    t.blur();
    const u = t.dataset.ue;
    if (u === 'zurueck') { this.zurueck(); return; }
    if (u === 'nochmal') { this.nochmal(); return; }
    if (t.dataset.haende) { this.haendeSetzen(t.dataset.haende); return; }
    if (t.dataset.tempo) { this.tempoStufe(+t.dataset.tempo); return; }
    if (t.id === 'ue-warten') { this.warten = !this.warten; this.anzeigen(); return; }
    if (t.id === 'ue-schleife') {
      if (this.schleife) this.schleife = null;
      else { const k = Math.max(0, this.takt(this.t)); this.schleife = [k, Math.min(this.taktzahl - 1, k + 3)]; this.springen(this.takt_ab + k * this.takt_s); }
      this.anzeigen(); this.zellen();
      return;
    }
    if (t.id === 'ue-fassung') {
      this.wechseln(this.fassungen[(this.fassungen.indexOf(this.fassung) + 1) % this.fassungen.length]);
      return;
    }
    if (t.id === 'ue-spiel') this.umschalten();
  }

  haendeSetzen(h) {
    this.haende = h;
    for (const b of this.wurzel.querySelectorAll('[data-haende]')) b.setAttribute('aria-pressed', b.dataset.haende === h);
    this.neuPlanen();
  }

  tempoStufe(r) {
    const i = STUFEN.indexOf(this.tempo);
    this.tempo = STUFEN[Math.max(0, Math.min(STUFEN.length - 1, i + r))];
    this.anzeigen();
  }

  tastatur(e) {
    if (e.target.matches?.('input')) return;
    if (e.key === ' ') { e.preventDefault(); this.umschalten(); }
    else if (e.key === 'Escape') this.zurueck();
    else if (e.key === 'ArrowUp') { e.preventDefault(); this.tempoStufe(1); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); this.tempoStufe(-1); }
    else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const k = Math.max(0, Math.min(this.taktzahl - 1, this.takt(this.t) + (e.key === 'ArrowRight' ? 1 : -1)));
      this.springen(this.takt_ab + k * this.takt_s);
    }
  }

  ziehen(e) {
    const zelle = (ev) => {
      const r = $('#ue-zellen', this.wurzel).getBoundingClientRect();
      return Math.max(0, Math.min(this.taktzahl - 1, Math.floor((ev.clientX - r.left) / r.width * this.taktzahl)));
    };
    const von = zelle(e);
    let bis = von;
    const zug = (ev) => {
      bis = zelle(ev);
      if (bis !== von) { this.schleife = [Math.min(von, bis), Math.max(von, bis)]; this.zellen(); this.anzeigen(); }
    };
    const los = () => {
      window.removeEventListener('pointermove', zug);
      window.removeEventListener('pointerup', los);
      const start = this.schleife && bis !== von ? this.schleife[0] : von;
      this.springen(this.takt_ab + start * this.takt_s);
      this.zellen();
    };
    window.addEventListener('pointermove', zug);
    window.addEventListener('pointerup', los);
  }

  zellen() {
    const jetzt = this.takt(this.t);
    this.zellenKnoten?.forEach((z, k) => {
      z.className = (this.sicher.has(k) ? 'sicher ' : '') + (k === jetzt ? 'jetzt ' : '') + (this.schleife && k >= this.schleife[0] && k <= this.schleife[1] ? 'schleife' : '');
    });
    this.letzterTakt = jetzt;
  }

  anzeigen() {
    const w = this.wurzel;
    if (!$('#ue-stand', w)) return;
    $('#ue-stand', w).textContent = `${this.namen[this.fassung]} · Takt ${Math.max(1, Math.min(this.taktzahl, this.takt(this.t) + 1))} / ${this.taktzahl}`;
    $('#ue-tempo', w).textContent = `${this.tempo} %`;
    $('#ue-warten', w).setAttribute('aria-pressed', this.warten);
    $('#ue-warten', w).hidden = !this.mitKlavier();
    $('#ue-schleife', w).setAttribute('aria-pressed', !!this.schleife);
    const s = $('#ue-spiel', w);
    s.innerHTML = this.laeuft ? UEBEN_ICON.pause : UEBEN_ICON.spiel;
    s.setAttribute('aria-label', this.laeuft ? 'Pause' : 'Abspielen');
    this.zellen();
    this.wach();
  }

  klavierGeaendert() {
    const k = $('#ue-klavier', this.wurzel);
    if (!k) return;
    const name = Midi.ein ? (/fp-?30|roland|digital piano/i.test(Midi.ein.name) ? 'FP-30X' : Midi.ein.name.slice(0, 18)) : 'Kein Klavier';
    k.textContent = name;
    k.classList.toggle('da', !!Midi.ein);
    this.neuPlanen();
  }

  wach() {
    this.leiste.classList.remove('ruhig');
    clearTimeout(this.ruhe);
    if (this.laeuft) this.ruhe = setTimeout(() => { if (this.laeuft) this.leiste.classList.add('ruhig'); }, 2500);
  }

  spruehen(ton, hand) {
    const k = this.lage[ton];
    if (!k) return;
    const farbe = hand === 0 ? '#FF4D7D' : '#FFE14D';
    for (let i = 0; i < 14; i++) this.funken.push({x: k.mitte, y: 0, vx: (Math.random() - .5) * 90, vy: -60 - Math.random() * 140, leben: 1, f: farbe});
  }

  tastenLage() {
    const weiss = (n) => [0, 2, 4, 5, 7, 9, 11].includes(n % 12);
    const l = {};
    let i = 0;
    for (let n = 21; n <= 108; n++) if (weiss(n)) l[n] = {i: i++, weiss: true};
    for (let n = 21; n <= 108; n++) if (!weiss(n)) l[n] = {i: l[n - 1].i + 1, weiss: false};
    return l;
  }

  /* ---------- Zeichnen ---------- */
  bild(jetzt) {
    if (!this.leben) return;
    const dt = this.davor === null ? 0 : Math.min(.05, (jetzt - this.davor) / 1000);
    this.davor = jetzt;
    this.schritt(dt);
    if (this.leben) {
      this.malen(jetzt, dt);
      if (this.takt(this.t) !== this.letzterTakt) {
        const r = this.leiste.classList.contains('ruhig');
        this.anzeigen();
        if (r) { clearTimeout(this.ruhe); this.leiste.classList.add('ruhig'); }
      }
      requestAnimationFrame((z) => this.bild(z));
    }
  }

  malen(jetzt, dt) {
    const {c, b: W, h: H, t} = this;
    c.clearRect(0, 0, W, H);
    const hoeheT = Math.min(170, H * .21);
    const linie = H - hoeheT;
    const tb = W / 52;
    const v = linie / 4;
    for (const n of Object.values(this.lage)) {
      n.x = n.weiss ? n.i * tb : n.i * tb - tb * .29;
      n.w = n.weiss ? tb : tb * .58;
      n.mitte = n.x + n.w / 2;
    }
    c.save();
    c.beginPath(); c.rect(0, 0, W, linie); c.clip();
    // Taktlinien
    c.strokeStyle = 'rgba(255,255,255,.05)'; c.lineWidth = 1;
    for (let k = Math.max(0, this.takt(t)); k <= this.takt(t) + 3; k++) {
      const y = linie - (this.takt_ab + k * this.takt_s - t) * v;
      if (y > 0 && y < linie) { c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); }
    }
    // Noten
    const sollTasten = new Set();
    for (const n of this.noten) {
      const unten = linie - (n.a - t) * v;
      const oben = linie - (n.e - t) * v;
      if (unten < 0) break;
      if (oben > linie) continue;
      const k = this.lage[n.ton];
      if (!k) continue;
      const farbe = n.hand ? '#FFE14D' : '#FF4D7D';
      const pad = k.weiss ? 3 : 1;
      const klingt = n.a <= t && t < n.e;
      const dabei = this.aktiv(n);
      const breit = k.w - 2 * pad, hoch = Math.max(5, unten - oben);
      c.globalAlpha = dabei ? (klingt ? .75 : .42) : .14;
      c.fillStyle = farbe;
      c.beginPath(); c.roundRect(k.x + pad, oben, breit, hoch, Math.min(5, breit / 3)); c.fill();
      c.globalAlpha = dabei ? 1 : .35;
      c.strokeStyle = farbe; c.lineWidth = 1.5;
      if (dabei && unten > linie * .55) { c.shadowColor = farbe; c.shadowBlur = 10; }
      c.stroke();
      c.shadowBlur = 0;
    }
    c.globalAlpha = 1;
    const g = this.gruppen[this.gi];
    if (g && g.t - t <= FRUEH_S) for (const ton of g.rest) sollTasten.add(ton);
    // Lichtkegel über gedrückten Tasten
    const an = new Map([...this.klingt, ...[...this.gedrueckt].filter(([, h]) => h >= 0)]);
    for (const [ton, hand] of an) {
      const k = this.lage[ton];
      if (!k) continue;
      const f = hand ? '#FFE14D' : '#FF4D7D';
      const gr = c.createLinearGradient(0, linie, 0, linie - 170);
      gr.addColorStop(0, f + '55'); gr.addColorStop(1, f + '00');
      c.fillStyle = gr;
      c.beginPath(); c.moveTo(k.mitte - tb * .45, linie); c.lineTo(k.mitte + tb * .45, linie); c.lineTo(k.mitte + tb * 1.1, linie - 170); c.lineTo(k.mitte - tb * 1.1, linie - 170); c.fill();
    }
    for (let j = this.funken.length - 1; j >= 0; j--) {
      const f = this.funken[j];
      f.leben -= dt * 1.5;
      if (f.leben <= 0) { this.funken.splice(j, 1); continue; }
      f.x += f.vx * dt; f.y += f.vy * dt; f.vy += 90 * dt;
      c.globalAlpha = f.leben; c.fillStyle = f.f;
      c.fillRect(f.x, linie + f.y, 2, 2);
    }
    c.restore();
    c.globalAlpha = 1;
    // Glutlinie
    const gl = c.createLinearGradient(0, 0, W, 0);
    gl.addColorStop(0, '#FF4D7D'); gl.addColorStop(.38, '#FF4D7D'); gl.addColorStop(.62, '#FFE14D'); gl.addColorStop(1, '#FFE14D');
    c.fillStyle = gl;
    c.shadowColor = '#ffffff55'; c.shadowBlur = 10;
    c.fillRect(0, linie - 2, W, 3);
    c.shadowBlur = 0;
    // Klaviatur
    const puls = .55 + .45 * Math.sin(jetzt / 160);
    const tasteFarbe = (n) => {
      const fal = this.falsch.get(n);
      if (this.gedrueckt.get(n) === -1 || (fal && jetzt - fal < 180)) return '#E5484D';
      return an.has(n) ? (an.get(n) ? '#FFE14D' : '#FF4D7D') : null;
    };
    for (let n = 21; n <= 108; n++) {
      const k = this.lage[n];
      if (!k.weiss) continue;
      const f = tasteFarbe(n);
      const gr = c.createLinearGradient(0, linie, 0, H);
      if (f) { gr.addColorStop(0, '#fff'); gr.addColorStop(.35, f); gr.addColorStop(1, f); } else { gr.addColorStop(0, '#BFC0C8'); gr.addColorStop(.4, '#ECECF0'); gr.addColorStop(1, '#DCDCE2'); }
      c.fillStyle = gr;
      c.beginPath(); c.roundRect(k.x + .5, linie + 1, tb - 1, hoeheT - 1, [0, 0, 4, 4]); c.fill();
      if (sollTasten.has(n) && !f) this.markieren(c, k.mitte, H - 16, puls, n);
    }
    for (let n = 21; n <= 108; n++) {
      const k = this.lage[n];
      if (k.weiss) continue;
      const f = tasteFarbe(n);
      c.fillStyle = f || '#141418';
      c.beginPath(); c.roundRect(k.x, linie + 1, k.w, hoeheT * .6, [0, 0, 3, 3]); c.fill();
      if (sollTasten.has(n) && !f) this.markieren(c, k.mitte, linie + hoeheT * .6 - 12, puls, n);
    }
    for (const [n, z] of this.falsch) if (jetzt - z > 180) this.falsch.delete(n);
  }

  markieren(c, x, y, puls, ton) {
    const hand = this.gruppen[this.gi]?.noten.find((n) => n.ton === ton)?.hand;
    c.globalAlpha = puls;
    c.fillStyle = hand === 0 ? '#FF4D7D' : '#D9B800';
    c.beginPath(); c.arc(x, y, 5, 0, 7); c.fill();
    c.globalAlpha = 1;
  }
}

window.Uebung = Uebung;
window.Midi = Midi;
