'use strict';
/* Üben: fallende Noten über der Klaviatur, Klavier per Web MIDI, Wartemodus, Hände einzeln, Tempo, Schleife. */

/* Einstellungen liegen beim Dienst: Die App startet auf wechselndem Port, Browser-Speicher wäre jedes Mal leer. */
const Einst = {
  werte: {haende: 'beide', tempo: 100, warten: true, noten: false, band: false, bandLaut: 35, tonAmKlavier: true, ruhig: true,
    links: '#FF4D7D', rechts: '#FFE14D', eingang: '', ausgang: '', klavierFertig: false},
  async laden() {
    try { Object.assign(this.werte, await (await fetch('/api/einstellungen')).json()); } catch { /* dann gelten die Vorgaben */ }
    this.farben();
  },
  setzen(k, v) {
    this.werte[k] = v;
    this.farben();
    fetch('/api/einstellungen', {method: 'POST', body: JSON.stringify(this.werte)}).catch(() => {});
  },
  farben() {
    document.documentElement.style.setProperty('--links', this.werte.links);
    document.documentElement.style.setProperty('--rechts', this.werte.rechts);
  },
};
const handFarbe = (hand) => (hand ? Einst.werte.rechts : Einst.werte.links);

/* Ein Song zerfällt in gleich lange Teile, lange Songs in längere. */
const SICHER_RUNDEN = 3, SICHER_PROZENT = 90;
function teileVon(song) {
  const n = song.takte || 0, je = n <= 40 ? 4 : 8, aus = [];
  for (let von = 0; von < n; von += je) aus.push({nr: aus.length + 1, von, bis: Math.min(n, von + je) - 1});
  // Ein kurzer Rest am Ende ist kein eigener Teil
  const letzter = aus[aus.length - 1];
  if (aus.length > 1 && letzter.bis - letzter.von + 1 < je / 2) { aus.pop(); aus[aus.length - 1].bis = letzter.bis; }
  return aus;
}
const heute = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

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
    const passt = (ports, gewuenscht) => {
      const alle = [...ports.values()].filter((p) => p.state !== 'disconnected');
      return alle.find((p) => p.name === gewuenscht) || alle.find((p) => /roland|fp-?30|digital piano/i.test(p.name)) || alle[0] || null;
    };
    if (this.ein) this.ein.onmidimessage = null;
    this.ein = passt(this.zugang.inputs, Einst.werte.eingang);
    this.aus = Einst.werte.tonAmKlavier ? passt(this.zugang.outputs, Einst.werte.ausgang) : null;
    if (this.ein) this.ein.onmidimessage = (e) => {
      const [st, ton, v] = e.data;
      if ((st & 0xF0) === 0x90 && v > 0) this.anschlag(ton, true, v);
      else if ((st & 0xF0) === 0x80 || (st & 0xF0) === 0x90) this.anschlag(ton, false, 0);
    };
    for (const h of this.hoerer) h.klavierGeaendert?.();
  },
  namen(art) { return this.zugang ? [...this.zugang[art].values()].filter((p) => p.state !== 'disconnected').map((p) => p.name) : []; },
  anschlag(ton, an, v = 90) { for (const h of this.hoerer) h.taste?.(ton, an, v); },
  note(ton, an, v = 80, wann) {
    if (this.aus) { this.aus.send(an ? [0x90, ton, v] : [0x80, ton, 0], wann); return; }
    this.macTon(ton, an, v);
  },
  pedal(an, wann) { this.aus?.send([0xB0, 64, an ? 127 : 0], wann); },
  kurzname(port) { return /fp-?30|roland|digital piano/i.test(port.name) ? 'FP-30X' : port.name.slice(0, 18); },
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

/* Anhören am Klavier: Das Audio-Element läuft stumm als Uhr, die Töne kommen per MIDI aus dem Klavier. */
const Vorspiel = {
  ton: null, ev: [], pedale: [], i: 0, uhr: null, null_ms: 0, geaendert: null,
  amKlavier() { return !!Midi.aus && this.ev.length > 0; },
  laden(ton, noten, pedal) {
    this.leeren();
    this.ton = ton;
    this.pedale = pedal;
    for (const [a, e, t, , v = 80] of noten) { this.ev.push({t: a, an: true, ton: t, v}); this.ev.push({t: e, an: false, ton: t}); }
    for (const [a, e] of pedal) { this.ev.push({t: a, pedal: true}); this.ev.push({t: e, pedal: false}); }
    // Zur selben Zeit erst loslassen, dann anschlagen, sonst verstummt ein wiederholter Ton
    this.ev.sort((x, y) => x.t - y.t || (x.an ? 1 : 0) - (y.an ? 1 : 0));
    Midi.hoerer.add(this);
    Midi.start().then(() => this.stimmen());
    this.stimmen();
  },
  leeren() {
    this.stopp();
    this.ev = []; this.pedale = [];
    Midi.hoerer.delete(this);
    if (this.ton) this.ton.muted = false;
    this.geaendert?.();
  },
  klavierGeaendert() { this.stimmen(); },
  stimmen() {
    if (!this.ton) return;
    this.ton.muted = this.amKlavier();
    if (this.amKlavier() && !this.ton.paused) this.los(); else this.stopp();
    this.geaendert?.();
  },
  los() {
    if (this.uhr) return;
    this.anUhr(this.ton.currentTime);
    this.uhr = setInterval(() => this.schritt(), 20);
  },
  stopp() {
    if (!this.uhr) return;
    clearInterval(this.uhr);
    this.uhr = null;
    Midi.stille();
  },
  // Eigene gleichmäßige Uhr, das Audio-Element stellt sie nur nach, wenn gesprungen wurde
  anUhr(t) {
    Midi.stille();
    this.null_ms = performance.now() - t * 1000;
    // Etwas zurückschauen: Beim Start steht die Uhr schon knapp hinter dem ersten Ton
    const i = this.ev.findIndex((e) => e.t >= t - .05);
    this.i = i < 0 ? this.ev.length : i;
    if (this.pedale.some(([a, e]) => a <= t && t < e)) Midi.pedal(true);
  },
  schritt() {
    const nun = performance.now();
    if (Math.abs((nun - this.null_ms) / 1000 - this.ton.currentTime) > .15) this.anUhr(this.ton.currentTime);
    const bis = (nun - this.null_ms) / 1000 + .1;
    while (this.i < this.ev.length && this.ev[this.i].t <= bis) {
      const e = this.ev[this.i++];
      const wann = Math.max(nun, this.null_ms + e.t * 1000);
      if (e.pedal !== undefined) Midi.pedal(e.pedal, wann);
      else Midi.note(e.ton, e.an, e.v, wann);
    }
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

/* ---------- Notenschrift ---------- */
const BUCHSTABEN = [0, 2, 4, 5, 7, 9, 11];
const KREUZ_FOLGE = [3, 0, 4, 1, 5, 2, 6];  // F C G D A E H als Stufen
const B_FOLGE = [6, 2, 5, 1, 4, 0, 3];      // H E A D G C F
// Übliche Lage der Vorzeichen im Violinschlüssel (Stufe = Oktave*7+Buchstabe, C4 = 35), im Bassschlüssel zwei Oktaven tiefer
const KREUZ_LAGE = [45, 42, 46, 43, 40, 44, 41];
const B_LAGE = [41, 44, 40, 43, 39, 42, 38];
const ZEICHEN_VERSATZ = {'♯': 2.5, '♭': 3, '♮': 2.5};  // Grundlinie unter der Mitte des Zeichens
const DUR_PROFIL = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
const MOLL_PROFIL = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17];
const VORZEICHEN_DUR = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 5: -1, 10: -2, 3: -3, 8: -4, 1: -5};

/** Tonart aus den Noten: Rückgabe Anzahl Vorzeichen, positiv Kreuze, negativ Bs. */
function tonartAus(noten) {
  const h = new Array(12).fill(0);
  for (const [a, e, ton] of noten) h[ton % 12] += Math.min(e - a, 2);
  const korr = (p, w) => {
    const r = h.map((_, i) => p[(i - w + 12) % 12]);
    const mx = h.reduce((x, y) => x + y) / 12, my = r.reduce((x, y) => x + y) / 12;
    let z = 0, a2 = 0, b2 = 0;
    for (let i = 0; i < 12; i++) { z += (h[i] - mx) * (r[i] - my); a2 += (h[i] - mx) ** 2; b2 += (r[i] - my) ** 2; }
    return z / Math.sqrt(a2 * b2 || 1);
  };
  let best = -2, dur = 0;
  for (let w = 0; w < 12; w++) {
    const d = korr(DUR_PROFIL, w), m = korr(MOLL_PROFIL, w);
    if (d > best) { best = d; dur = w; }
    if (m > best) { best = m; dur = (w + 3) % 12; }
  }
  return VORZEICHEN_DUR[dur];
}

/** Wie ein Ton in dieser Tonart geschrieben wird: Stufe (Oktave*7+Buchstabe) und Versetzungszeichen. */
function schreibweise(ton, vorz) {
  const verschiebung = new Array(7).fill(0);
  for (let i = 0; i < Math.abs(vorz); i++) verschiebung[(vorz > 0 ? KREUZ_FOLGE : B_FOLGE)[i]] = Math.sign(vorz);
  const okt = Math.floor(ton / 12), pc = ton % 12;
  for (let b = 0; b < 7; b++) {
    if ((BUCHSTABEN[b] + verschiebung[b] + 12) % 12 === pc) {
      const o = BUCHSTABEN[b] + verschiebung[b] < 0 ? okt + 1 : BUCHSTABEN[b] + verschiebung[b] >= 12 ? okt - 1 : okt;
      return {stufe: o * 7 + b, zeichen: ''};
    }
  }
  const nat = BUCHSTABEN.indexOf(pc);
  if (nat >= 0) return {stufe: okt * 7 + nat, zeichen: '♮'};
  const b = BUCHSTABEN.indexOf(vorz < 0 ? pc + 1 : pc - 1);
  return {stufe: okt * 7 + b, zeichen: vorz < 0 ? '♭' : '♯'};
}

class Uebung {
  constructor(wurzel, song, fassung, noten, pedal, fortschritt, wechseln, zurueck, bereich = null) {
    Object.assign(this, {wurzel, song, fassung, pedal, wechseln, zurueck});
    this.noten = noten.map(([a, e, ton, hand, v], i) => ({a, e, ton, hand, v, i})).sort((x, y) => x.a - y.a || x.ton - y.ton);
    this.takt_s = song.takt_s || 240 / (song.bpm || 120);
    this.takt_ab = song.takt_ab || 0;
    this.ende = this.noten.length ? Math.max(...this.noten.map((n) => n.e)) : 0;
    this.taktzahl = Math.max(1, Math.ceil((this.ende - this.takt_ab) / this.takt_s));
    this.sicher = new Set(fortschritt?.[fassung]?.sicher || []);
    this.fortschritt = fortschritt || {};
    this.stand = {takte: {}, teile: {}, sekunden: 0, ...(this.fortschritt[fassung] || {})};
    this.teile = teileVon(song);
    this.neueTakte = 0; this.neueSekunden = 0;
    this.haende = Einst.werte.haende; this.tempo = Einst.werte.tempo; this.warten = Einst.werte.warten;
    this.schleife = bereich ? [Math.min(bereich[0], this.taktzahl - 1), Math.min(bereich[1], this.taktzahl - 1)] : null;
    this.laeuft = false; this.t = 0; this.gedrueckt = new Map(); this.falsch = new Map();
    this.funken = []; this.klingt = new Map(); this.werte = {}; this.fertig = false;
    this.lage = this.tastenLage();
    this.vorz = song.vorzeichen ?? tonartAus(noten);
    this.blatt = Einst.werte.noten;
    this.bauen();
    this.t = Math.max(0, (this.schleife ? this.takt_ab + this.schleife[0] * this.takt_s - 1.5 : this.noten[0]?.a ?? 0) - (this.schleife ? 0 : VORLAUF_S));
    this.band = new Audio(`/api/songs/${song.id}/begleitung`);
    this.band.preload = Einst.werte.band ? 'auto' : 'none';
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
    this.band.pause();
    this.band.removeAttribute('src');
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
    // Ohne Klavier gibt es nichts zu drücken: Man hört die gewählte Hand. Mit Klavier spielt man sie selbst, die andere kommt von der App.
    const zuSpielen = this.noten.filter((n) => this.mitKlavier() && this.aktiv(n));
    this.gruppen = [];
    for (const n of zuSpielen) {
      const g = this.gruppen[this.gruppen.length - 1];
      if (g && n.a - g.t < .04) { g.toene.add(n.ton); g.noten.push(n); } else this.gruppen.push({t: n.a, toene: new Set([n.ton]), noten: [n]});
    }
    this.selbst = [];
    for (const n of this.noten) {
      if (this.mitKlavier() !== this.aktiv(n)) {
        this.selbst.push({t: n.a, an: 1, n});
        this.selbst.push({t: n.e, an: 0, n});
      }
    }
    for (const [a, e] of this.pedal) { this.selbst.push({t: a, an: 2}); this.selbst.push({t: e, an: 3}); }
    this.selbst.sort((x, y) => x.t - y.t);
    this.sollJe = {};
    for (const g of this.gruppen) { const k = this.takt(g.t); this.sollJe[k] = (this.sollJe[k] || 0) + g.toene.size; }
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
    const soll = this.sollJe[k] || 0;
    const w = this.wert(k);
    if (soll && w.ist / soll >= .9 && w.falsch <= soll * .1) this.sicher.add(k);
    if (w.ist) {
      this.stand.takte[k] = (this.stand.takte[k] || 0) + 1;
      this.neueTakte += 1;
    }
    this.zellen();
  }

  umschalten() {
    if (this.fertig) { this.nochmal(); return; }
    this.laeuft = !this.laeuft;
    if (!this.laeuft) { this.anhalten(); this.speichern(); } else this.wach();
    this.anzeigen();
  }

  /* Eine Runde über diese Takte ist durch: Jeder ganz gespielte Teil bekommt seine Wertung. */
  rundeWerten(von, bis) {
    for (const teil of this.teile) {
      if (teil.von < von || Math.min(teil.bis, this.taktzahl - 1) > bis) continue;
      let soll = 0, ist = 0, falsch = 0;
      for (let k = teil.von; k <= teil.bis; k++) {
        soll += this.sollJe[k] || 0;
        ist += this.werte[k]?.ist || 0;
        falsch += this.werte[k]?.falsch || 0;
      }
      if (!soll || !ist) continue;
      const prozent = Math.round(Math.max(0, ist - falsch) / soll * 100);
      const s = (this.stand.teile[teil.nr] ??= {runden: 0, beste: 0, gut: 0});
      s.runden += 1;
      s.beste = Math.max(s.beste, prozent);
      // Sicher heißt mit beiden Händen
      if (prozent >= SICHER_PROZENT && this.haende === 'beide') s.gut += 1;
    }
  }

  /* Schleife endet auf dem letzten vollen Ton: Was im letzten Takt anfängt, darf ausklingen, höchstens einen halben Takt. */
  grenzen() {
    const schluessel = this.schleife.join('-');
    if (this.grenzenFuer === schluessel) return this.grenzenWert;
    const von = this.takt_ab + this.schleife[0] * this.takt_s, taktEnde = this.takt_ab + (this.schleife[1] + 1) * this.takt_s;
    let ende = taktEnde;
    for (const n of this.noten) if (n.a >= von && n.a < taktEnde) ende = Math.max(ende, n.e);
    this.grenzenFuer = schluessel;
    this.grenzenWert = {von, taktEnde, ende: Math.min(ende, taktEnde + this.takt_s / 2)};
    return this.grenzenWert;
  }

  bandStimmen() {
    const b = this.band;
    const soll = Einst.werte.band && this.laeuft && !this.wartet && this.t >= 0 && !this.fertig;
    if (!soll) { if (!b.paused) b.pause(); return; }
    b.volume = Math.min(1, Einst.werte.bandLaut / 100);
    b.playbackRate = this.tempo / 100;
    if (Math.abs(b.currentTime - this.t) > .15) { try { b.currentTime = this.t; } catch { /* lädt noch */ } }
    if (b.paused) b.play().catch(() => {});
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
    if (this.mitKlavier()) this.neueSekunden += dt;
    const gr = this.schleife ? this.grenzen() : null;
    const dran = (x) => x && (!gr || x.t < gr.taktEnde);
    const g = this.gruppen[this.gi];
    this.wartet = false;
    if (this.warten && dran(g) && t >= g.t) {
      t = g.t;
      this.wartet = true;
    }
    if (!this.warten) {
      while (dran(this.gruppen[this.gi]) && this.gruppen[this.gi].t + GNADE_S < t) this.weiter();
    }
    // Was die App selbst spielt
    while (this.ei < this.selbst.length && this.selbst[this.ei].t <= t) {
      const e = this.selbst[this.ei++];
      if (gr && e.an === 1 && e.t >= gr.taktEnde) continue;  // der Takt nach der Schleife klingt nicht mehr an
      if (e.an === 1) {
        // Die andere Hand etwas leiser, damit man sich selbst hört
        const v = e.n.v ?? 72;
        Midi.note(e.n.ton, true, this.mitKlavier() ? Math.max(40, Math.round(v * .8)) : v);
        this.klingt.set(e.n.ton, e.n.hand);
      }
      else if (e.an === 0) { Midi.note(e.n.ton, false); this.klingt.delete(e.n.ton); }
      else Midi.pedal(e.an === 2);
    }
    this.t = t;
    if (gr && t >= gr.ende) {
      // Takt-Bewertung vor dem Rücksprung sichern, die Runde beginnt neu
      this.rundeWerten(this.schleife[0], this.schleife[1]);
      for (let k = this.schleife[0]; k <= this.schleife[1]; k++) delete this.werte[k];
      this.speichern();
      this.springen(gr.von, true);
      return;
    }
    if (t > this.ende + 1) this.abschluss();
  }

  abschluss() {
    this.anhalten();
    this.fertig = true;
    this.rundeWerten(0, this.taktzahl - 1);
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
    const sekunden = Math.floor(this.neueSekunden);
    if (sekunden || this.neueTakte) {
      this.stand.sekunden += sekunden;
      this.stand.zuletzt = Date.now();
      fetch('/api/verlauf', {method: 'POST', body: JSON.stringify({tag: heute(), takte: this.neueTakte, sekunden})}).catch(() => {});
      this.neueTakte = 0;
      this.neueSekunden -= sekunden;
    }
    this.fortschritt[this.fassung] = {...this.stand, sicher: [...this.sicher]};
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
            ${[['beide', 'Beide'], ['r', 'Rechts'], ['l', 'Links']].map(([k, t]) => `<button data-haende="${k}" aria-pressed="${this.haende === k}">${t}</button>`).join('')}
          </div>
          <div class="ue-tempo" role="group" aria-label="Tempo"><button data-tempo="-1" aria-label="Langsamer">−</button><span id="ue-tempo">${this.tempo} %</span><button data-tempo="1" aria-label="Schneller">+</button></div>
          <button class="ue-pille" id="ue-warten" aria-pressed="${this.warten}">Warten</button>
          <button class="ue-pille" id="ue-schleife" aria-pressed="false">Schleife</button>
          <button class="ue-pille" id="ue-noten" aria-pressed="false">Noten</button>
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
    if (t.id === 'ue-warten') { this.warten = !this.warten; Einst.setzen('warten', this.warten); this.anzeigen(); return; }
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
    if (t.id === 'ue-noten') { this.notenUmschalten(); return; }
    if (t.id === 'ue-spiel') this.umschalten();
  }

  notenUmschalten() {
    this.blatt = !this.blatt;
    Einst.setzen('noten', this.blatt);
    this.anzeigen();
  }

  haendeSetzen(h) {
    this.haende = h;
    Einst.setzen('haende', h);
    for (const b of this.wurzel.querySelectorAll('[data-haende]')) b.setAttribute('aria-pressed', b.dataset.haende === h);
    this.neuPlanen();
  }

  tempoStufe(r) {
    const i = STUFEN.indexOf(this.tempo);
    this.tempo = STUFEN[Math.max(0, Math.min(STUFEN.length - 1, i + r))];
    Einst.setzen('tempo', this.tempo);
    this.anzeigen();
  }

  tastatur(e) {
    if (e.target.matches?.('input')) return;
    if (e.key === ' ') { e.preventDefault(); this.umschalten(); }
    else if (e.key === 'Escape') this.zurueck();
    else if (e.key === 'n' || e.key === 'N') this.notenUmschalten();
    else if (e.key === 'r' || e.key === 'R') this.haendeSetzen('r');
    else if (e.key === 'l' || e.key === 'L') this.haendeSetzen('l');
    else if (e.key === 'b' || e.key === 'B') this.haendeSetzen('beide');
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
    $('#ue-noten', w).setAttribute('aria-pressed', this.blatt);
    const s = $('#ue-spiel', w);
    s.innerHTML = this.laeuft ? UEBEN_ICON.pause : UEBEN_ICON.spiel;
    s.setAttribute('aria-label', this.laeuft ? 'Pause' : 'Abspielen');
    this.zellen();
    this.wach();
  }

  klavierGeaendert() {
    const k = $('#ue-klavier', this.wurzel);
    if (!k) return;
    k.textContent = Midi.ein ? Midi.kurzname(Midi.ein) : 'Kein Klavier';
    k.classList.toggle('da', !!Midi.ein);
    this.neuPlanen();
  }

  wach() {
    this.leiste.classList.remove('ruhig');
    clearTimeout(this.ruhe);
    if (this.laeuft && Einst.werte.ruhig) this.ruhe = setTimeout(() => { if (this.laeuft) this.leiste.classList.add('ruhig'); }, 2500);
  }

  spruehen(ton, hand) {
    const k = this.lage[ton];
    if (!k) return;
    const farbe = handFarbe(hand);
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
    this.bandStimmen();
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
    const PANEL_OBEN = 60, PANEL_H = 258;
    const oben_ = this.blatt ? PANEL_OBEN + PANEL_H : 0;
    for (const n of Object.values(this.lage)) {
      n.x = n.weiss ? n.i * tb : n.i * tb - tb * .29;
      n.w = n.weiss ? tb : tb * .58;
      n.mitte = n.x + n.w / 2;
    }
    c.save();
    c.beginPath(); c.rect(0, oben_, W, linie - oben_); c.clip();
    // Taktlinien
    c.strokeStyle = 'rgba(255,255,255,.05)'; c.lineWidth = 1;
    for (let k = Math.max(0, this.takt(t)); k <= this.takt(t) + 3; k++) {
      const y = linie - (this.takt_ab + k * this.takt_s - t) * v;
      if (y > oben_ && y < linie) { c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); }
    }
    // Noten
    const sollTasten = new Set();
    for (const n of this.noten) {
      const unten = linie - (n.a - t) * v;
      const oben = linie - (n.e - t) * v;
      if (unten < oben_) break;
      if (oben > linie) continue;
      const k = this.lage[n.ton];
      if (!k) continue;
      const farbe = handFarbe(n.hand);
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
      const f = handFarbe(hand);
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
    gl.addColorStop(0, handFarbe(0)); gl.addColorStop(.38, handFarbe(0)); gl.addColorStop(.62, handFarbe(1)); gl.addColorStop(1, handFarbe(1));
    c.fillStyle = gl;
    c.shadowColor = '#ffffff55'; c.shadowBlur = 10;
    c.fillRect(0, linie - 2, W, 3);
    c.shadowBlur = 0;
    // Klaviatur
    const puls = .55 + .45 * Math.sin(jetzt / 160);
    const tasteFarbe = (n) => {
      const fal = this.falsch.get(n);
      if (this.gedrueckt.get(n) === -1 || (fal && jetzt - fal < 180)) return '#E5484D';
      return an.has(n) ? (handFarbe(an.get(n))) : null;
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
    if (this.blatt) this.notenblatt(c, W, PANEL_OBEN, PANEL_H);
  }

  /** Zwei Zeilen zu je vier Takten: aktuelle hell, nächste verblasst. */
  notenblatt(c, W, oben, hoehe) {
    const JE_ZEILE = 4;
    const zeile = Math.max(0, Math.floor(Math.max(0, this.takt(this.t)) / JE_ZEILE));
    c.fillStyle = 'rgba(8,8,10,.94)';
    c.fillRect(0, oben, W, hoehe);
    c.fillStyle = 'rgba(255,255,255,.07)';
    c.fillRect(0, oben + hoehe - 1, W, 1);
    const halb = 3.5;
    const links = Math.min(96, W * .06), rechts_ = W - 24;
    const breite_kopf = links + 56 + Math.abs(this.vorz) * 8;
    const dauer = JE_ZEILE * this.takt_s;
    const xVon = (t, start) => breite_kopf + (t - start) / dauer * (rechts_ - breite_kopf - 8);
    for (let si = 0; si < 2; si++) {
      const start = this.takt_ab + (zeile + si) * JE_ZEILE * this.takt_s;
      const top = oben + (si ? 126 : 6);
      const T0 = top + 42, B0 = top + 92;
      c.globalAlpha = si ? .38 : 1;
      c.strokeStyle = 'rgba(255,255,255,.26)'; c.lineWidth = 1;
      c.beginPath();
      for (const y0 of [T0, B0]) for (let i = 0; i < 5; i++) { c.moveTo(links, y0 - i * 7 + .5); c.lineTo(rechts_, y0 - i * 7 + .5); }
      for (let k = 0; k <= JE_ZEILE; k++) { const x = xVon(start + k * this.takt_s, start) - (k === JE_ZEILE ? 0 : 8) + .5; c.moveTo(x, T0 - 28); c.lineTo(x, B0); }
      c.moveTo(links + .5, T0 - 28); c.lineTo(links + .5, B0);
      c.stroke();
      c.fillStyle = 'rgba(255,255,255,.8)';
      c.textBaseline = 'alphabetic'; c.textAlign = 'left';
      c.font = "36px 'Noto Music',serif"; c.fillText('𝄞', links + 8, T0 - 4);
      c.font = "24px 'Noto Music',serif"; c.fillText('𝄢', links + 10, B0 - 5);
      // Vorzeichen
      const lage = this.vorz > 0 ? KREUZ_LAGE : B_LAGE;
      const zei = this.vorz > 0 ? '♯' : '♭';
      c.font = "16px 'Noto Music',serif";
      c.textAlign = 'center';
      for (let i = 0; i < Math.abs(this.vorz); i++) {
        const x = links + 44 + i * 8;
        c.fillText(zei, x, T0 - (lage[i] - 37) * halb + ZEICHEN_VERSATZ[zei]);
        c.fillText(zei, x, B0 - (lage[i] - 14 - 25) * halb + ZEICHEN_VERSATZ[zei]);
      }
      c.font = '12px Geist,system-ui,sans-serif'; c.textAlign = 'right';
      c.fillStyle = 'rgba(237,237,240,.55)';
      c.fillText(String((zeile + si) * JE_ZEILE + 1), links - 8, T0 - 22);
      // Noten
      for (const n of this.noten) {
        if (n.a < start - .01) continue;
        if (n.a >= start + dauer - .01) break;
        const {stufe, zeichen} = schreibweise(n.ton, this.vorz);
        const y = n.hand ? T0 - (stufe - 37) * halb : B0 - (stufe - 25) * halb;
        const x = xVon(n.a, start);
        const dabei = this.aktiv(n);
        const f = handFarbe(n.hand);
        // Hilfslinien
        c.strokeStyle = 'rgba(255,255,255,.35)'; c.lineWidth = 1;
        c.beginPath();
        const unterst = n.hand ? T0 : B0, oberst = unterst - 28;
        for (let yy = unterst + 7; yy <= y + .1; yy += 7) { c.moveTo(x - 8, yy + .5); c.lineTo(x + 8, yy + .5); }
        for (let yy = oberst - 7; yy >= y - .1; yy -= 7) { c.moveTo(x - 8, yy + .5); c.lineTo(x + 8, yy + .5); }
        c.stroke();
        const vorbei = !si && n.e <= this.t;
        c.globalAlpha = (si ? .38 : 1) * (vorbei ? .35 : 1) * (dabei ? 1 : .45);
        c.fillStyle = f;
        if (!si && !vorbei) { c.shadowColor = f; c.shadowBlur = 6; }
        c.beginPath(); c.ellipse(x, y, 5, 3.5, -.35, 0, 7); c.fill();
        c.shadowBlur = 0;
        if (zeichen) {
          c.font = "12px 'Noto Music',serif"; c.textAlign = 'center';
          c.fillText(zeichen, x - 11, y + ZEICHEN_VERSATZ[zeichen]);
        }
        c.globalAlpha = si ? .38 : 1;
      }
      c.globalAlpha = 1;
    }
    // Abspielkopf
    const start = this.takt_ab + zeile * JE_ZEILE * this.takt_s;
    if (this.t >= start) {
      c.fillStyle = '#fff'; c.shadowColor = 'rgba(255,255,255,.6)'; c.shadowBlur = 10;
      c.fillRect(xVon(this.t, start) - 1, oben + 18, 2, 84);
      c.shadowBlur = 0;
    }
  }

  markieren(c, x, y, puls, ton) {
    const hand = this.gruppen[this.gi]?.noten.find((n) => n.ton === ton)?.hand;
    c.globalAlpha = puls;
    c.fillStyle = handFarbe(hand);
    c.beginPath(); c.arc(x, y, 5, 0, 7); c.fill();
    c.globalAlpha = 1;
  }
}

window.Uebung = Uebung;
window.tonartAus = tonartAus;
window.schreibweise = schreibweise;
window.Midi = Midi;
