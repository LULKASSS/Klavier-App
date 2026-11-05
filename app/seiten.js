'use strict';
/* Zuhause, Übungsplan, Vor dem Spielen, Klavier verbinden, Einstellungen. Zeichnen und Zustand kommen aus index.html und ueben.js. */

const NOTENNAMEN = ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B', 'H'];
const notenname = (m) => NOTENNAMEN[m % 12] + (Math.floor(m / 12) - 1);
const taktText = (t) => (t.von === t.bis ? `Takt ${t.von + 1}` : `Takt ${t.von + 1}–${t.bis + 1}`);
const startFassung = (m) => (m.band || m.midi ? 'original' : 'leicht');
const dauerText = (s) => {
  const min = Math.round((s || 0) / 60);
  return min < 60 ? `${min} Min` : `${Math.floor(min / 60)} Std ${min % 60} Min`;
};
const zuletztText = (ms) => {
  if (!ms) return 'noch nicht geübt';
  const tage = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(ms).setHours(0, 0, 0, 0)) / 864e5);
  return tage <= 0 ? 'zuletzt heute' : tage === 1 ? 'zuletzt gestern' : `zuletzt vor ${tage} Tagen`;
};

/* ---------- Auswertung ---------- */
/** Stufe wächst mit den gespielten Takten: Stufe 2 ab 200, Stufe 3 ab 600, Stufe 4 ab 1.200 (Annahme). */
const stufenGrenze = (n) => 100 * (n - 1) * n;
function auswertung(verlauf) {
  const tage = verlauf?.tage || {};
  const tagVor = (i) => {
    const d = new Date();
    d.setDate(d.getDate() - i);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const takte = (i) => tage[tagVor(i)]?.takte || 0;
  let serie = 0;
  for (let i = takte(0) ? 0 : 1; takte(i); i++) serie++;
  const gesamt = Object.values(tage).reduce((s, t) => s + (t.takte || 0), 0);
  let stufe = 1;
  while (gesamt >= stufenGrenze(stufe + 1)) stufe++;
  const anteil = (gesamt - stufenGrenze(stufe)) / (stufenGrenze(stufe + 1) - stufenGrenze(stufe));
  const summe = (von, bis) => { let s = 0; for (let i = von; i <= bis; i++) s += takte(i); return s; };
  return {serie, stufe, anteil, gesamt, woche: summe(0, 6), davor: summe(7, 13), tage14: Array.from({length: 14}, (_, i) => takte(13 - i)), woche7: Array.from({length: 7}, (_, i) => takte(6 - i) > 0)};
}
/** Wo steht ein Song in seinem Plan? */
function planStand(m, s) {
  const teile = teileVon(m).map((t) => {
    const w = s?.teile?.[t.nr] || {runden: 0, beste: 0, gut: 0};
    return {...t, ...w, sicher: w.gut >= SICHER_RUNDEN};
  });
  return {teile, sicher: teile.filter((t) => t.sicher).length, jetzt: teile.find((t) => !t.sicher) || null, runden: teile.reduce((x, t) => x + t.runden, 0)};
}

/* ---------- Kopf ---------- */
async function kopfStand() {
  const box = $('#kopf-stand');
  if (!box) return;
  const a = auswertung(await api('verlauf').catch(() => null));
  box.innerHTML = `${a.serie ? `<span class="st-pille"><span class="st-tage">${a.woche7.map((an) => `<i class="${an ? 'an' : ''}"></i>`).join('')}</span>${a.serie} ${a.serie === 1 ? 'Tag' : 'Tage'}</span>` : ''}
    <span class="st-pille">Stufe <b>${a.stufe}</b><span class="st-balken"><i style="width:${Math.round(a.anteil * 100)}%"></i></span></span>`;
}

/* ---------- Zuhause ---------- */
async function seiteZuhause() {
  S.songs = await api('songs');
  const fertig = S.songs.filter((m) => m.status === 'fertig');
  const [staende, verlauf] = await Promise.all([
    Promise.all(fertig.map(async (m) => ({m, f: await api(`songs/${m.id}/fortschritt.json`).catch(() => ({}))}))),
    api('verlauf').catch(() => null),
  ]);
  if (S.seite !== 'zuhause') return;
  const geuebt = staende.map(({m, f}) => {
    let beste = null;
    for (const k of Object.keys(fassungen(m))) if (f[k]?.zuletzt && (!beste || f[k].zuletzt > beste.s.zuletzt)) beste = {m, fassung: k, s: f[k]};
    return beste;
  }).filter(Boolean).sort((x, y) => y.s.zuletzt - x.s.zuletzt);
  const a = auswertung(verlauf);
  const held = geuebt[0] || (fertig[0] ? {m: fertig[0], fassung: startFassung(fertig[0]), s: {}, neu: true} : null);
  $('#haupt').innerHTML = `<div class="auftritt zuhause">${heldHtml(held)}<div class="drei">${takteKarte(a)}${zuletztKarte(geuebt)}${zielKarte(held)}</div></div>`;
  fallSzene($('#heldbild'), {tasten: false, dunkel: .8});
}
function heldHtml(h) {
  const laeuft = S.songs.find((m) => m.status === 'laeuft' || m.status === 'wartet');
  if (!h) {
    return `<section class="held gross"><canvas id="heldbild" aria-hidden="true"></canvas><div class="deck"></div><div class="text">
      ${laeuft ? `<span class="klein">Wird gerade umgewandelt</span><h1>${esc(laeuft.name)}</h1><a class="haupt" href="#umwandeln/${laeuft.id}">Ansehen</a>`
      : `<span class="klein">Audiodatei rein, spielbare Noten raus</span><h1>Dein erster Song</h1><button class="haupt" data-waehlen>${ICON.plus}Audiodatei wählen</button>`}</div></section>`;
  }
  const p = planStand(h.m, h.s), j = p.jetzt;
  const zeile = !j ? 'Alle Teile sicher' : `Teil ${j.nr} von ${p.teile.length} · ${taktText(j)}${j.beste ? ` · beste Runde ${j.beste} %` : ''}`;
  const ziel = j ? `#ueben/${h.m.id}/${h.fassung}/${j.von}/${j.bis}` : `#ueben/${h.m.id}/${h.fassung}`;
  return `<section class="held gross"><canvas id="heldbild" aria-hidden="true"></canvas><div class="deck"></div><div class="text">
    <span class="klein">${h.neu ? 'Leg los' : 'Weiter, wo du warst'}</span><h1>${esc(h.m.name)}</h1><span class="klein">${esc(zeile)}</span>
    <div class="teilbalken">${p.teile.map((t) => `<i class="${t.sicher ? 'sicher' : t === j ? 'jetzt' : ''}"></i>`).join('')}</div>
    <div class="knopfreihe"><a class="haupt" id="weiter" href="${ziel}">${ICON.spiel}${h.neu ? 'Loslegen' : j ? 'Weiterspielen' : 'Ganzer Song'}</a><a class="pille" href="#plan/${h.m.id}/${h.fassung}">Übungsplan</a></div></div></section>`;
}
function takteKarte(a) {
  const hoch = Math.max(1, ...a.tage14);
  const plus = a.davor ? Math.round((a.woche - a.davor) / a.davor * 100) : null;
  return `<div class="karte-grund ruhe"><div class="ruhe-kopf"><span class="klein">Gespielte Takte</span>${plus === null ? '' : `<span class="klein ${plus >= 0 ? 'gut' : ''}">${plus >= 0 ? '+' : ''}${plus} %</span>`}</div>
    <span class="ruhe-zahl">${a.woche.toLocaleString('de-DE')} <small>diese Woche</small></span>
    <div class="tagesbalken" aria-hidden="true">${a.tage14.map((v, i) => `<i class="${!v ? 'leer' : i === 13 ? 'heute' : ''}" style="height:${Math.max(3, Math.round(v / hoch * 52))}px"></i>`).join('')}</div></div>`;
}
function zuletztKarte(geuebt) {
  return `<div class="karte-grund ruhe"><div class="ruhe-kopf"><span class="klein">Zuletzt geübt</span><a class="klein" href="#songs">Alle Songs</a></div>
    ${geuebt.length ? geuebt.slice(0, 3).map(({m, fassung, s}) => {
      const p = planStand(m, s);
      return `<a class="ruhe-zeile" href="#plan/${m.id}/${fassung}"><i class="${p.jetzt ? 'offen' : 'sicher'}"></i><span class="name">${esc(m.name)}</span><span class="klein">${p.jetzt ? `Teil ${p.jetzt.nr} / ${p.teile.length}` : 'sicher'}</span></a>`;
    }).join('') : '<span class="klein ruhe-leer">Noch nichts geübt</span>'}</div>`;
}
function zielKarte(h) {
  const j = h && planStand(h.m, h.s).jetzt;
  if (!j) {
    return `<div class="karte-grund ruhe"><div class="ruhe-kopf"><span class="klein">Nächstes Ziel</span></div>
      <span class="ruhe-ziel">${h ? 'Ganzen Song durchspielen' : 'Ersten Song hinzufügen'}</span><span class="klein">${h ? 'Alle Teile sind sicher' : 'MP3, WAV, M4A oder MID'}</span></div>`;
  }
  const rest = SICHER_RUNDEN - j.gut;
  return `<div class="karte-grund ruhe"><div class="ruhe-kopf"><span class="klein">Nächstes Ziel</span></div>
    <span class="ruhe-ziel">Teil ${j.nr} sicher spielen</span><span class="klein">noch ${rest} ${rest === 1 ? 'Runde' : 'Runden'} über ${SICHER_PROZENT} %</span>
    <div class="zielrunden" aria-hidden="true">${Array.from({length: SICHER_RUNDEN}, (_, i) => `<i class="${i < j.gut ? 'an' : ''}"></i>`).join('')}</div></div>`;
}

/* ---------- Übungsplan ---------- */
async function seitePlan(id, fassung) {
  const m = S.song = await api('songs/' + id);
  if (m.status !== 'fertig') { location.hash = `#umwandeln/${id}`; return; }
  const f = await api(`songs/${id}/fortschritt.json`).catch(() => ({}));
  if (S.seite !== 'plan') return;
  const s = f[fassung] || {};
  const p = planStand(m, s), j = p.jetzt;
  const name = fassungen(m)[fassung]?.titel || '';
  const spalten = Math.min(8, p.teile.length);
  $('#haupt').innerHTML = `<div class="auftritt plan">
    <div class="songkopf"><a class="pille zurueck" href="#song/${id}">${ICON.zurueck}${esc(m.name)}</a><span class="klein">Sicher ab ${SICHER_RUNDEN} Runden über ${SICHER_PROZENT} %</span></div>
    <div class="plan-kopf"><div><span class="klein">${esc(m.name)} · ${esc(name)}</span><div class="plan-zahl">${p.sicher} <small>von ${p.teile.length} Teilen sicher</small></div></div>
      <span class="klein">${p.runden} ${p.runden === 1 ? 'Runde' : 'Runden'} · ${dauerText(s.sekunden)} · ${zuletztText(s.zuletzt)}</span></div>
    ${verlaufBild(m, s, p)}
    <div class="teile" style="grid-template-columns:repeat(${spalten},minmax(0,1fr))">${p.teile.map((t) => `<a class="teil ${t.sicher ? 'sicher' : t === j ? 'jetzt' : ''}" href="#ueben/${id}/${fassung}/${t.von}/${t.bis}">
      <span class="teil-kopf"><b>Teil ${t.nr}</b><span class="teil-stand">${t.sicher ? 'sicher' : t === j ? 'jetzt' : 'offen'}</span></span><span class="klein">${taktText(t).replace('Takt ', '')}${t.beste ? ` · ${t.beste} %` : ''}</span></a>`).join('')}</div>
    <div class="kette"><span class="klein">Danach zusammensetzen</span>${ketteHtml(m, fassung, p)}</div>
    <div class="plan-fuss"><span class="klein">${j ? `Teil ${j.nr} · ${taktText(j)}${j.beste ? ` · beste Runde ${j.beste} %` : ''}` : 'Alle Teile sicher'}</span>
      <a class="haupt" id="plan-weiter" href="${j ? `#ueben/${id}/${fassung}/${j.von}/${j.bis}` : `#ueben/${id}/${fassung}`}">${ICON.spiel}${j ? `Weiter mit Teil ${j.nr}` : 'Ganzer Song'}</a></div></div>`;
}
function ketteHtml(m, fassung, p) {
  const n = p.teile.length;
  const stufen = [];
  const dazu = (a, b) => { if (b > a && b <= n && !stufen.some((x) => x[0] === a && x[1] === b)) stufen.push([a, b]); };
  dazu(1, 2); dazu(1, Math.min(4, n)); if (n > 4) dazu(5, Math.min(8, n)); if (n > 8) dazu(1, Math.min(8, n));
  for (let a = 9; a <= n; a += 8) dazu(a, Math.min(a + 7, n));
  let naechste = true;
  const chips = stufen.map(([a, b]) => {
    const fertig = p.teile.slice(a - 1, b).every((t) => t.sicher);
    const art = fertig ? 'sicher' : naechste ? 'naechste' : '';
    if (!fertig) naechste = false;
    return `<a class="chip ${art}" href="#ueben/${m.id}/${fassung}/${p.teile[a - 1].von}/${p.teile[b - 1].bis}">${a} bis ${b}</a>`;
  });
  chips.push(`<a class="chip ${naechste ? 'naechste' : ''}" href="#ueben/${m.id}/${fassung}">Ganzer Song</a>`);
  return chips.join('');
}
/** Wie oft jeder Takt gespielt wurde, als weiche Kurve. */
function verlaufBild(m, s, p) {
  const n = Math.max(1, m.takte || 1);
  const werte = Array.from({length: n}, (_, k) => s.takte?.[k] || 0);
  const hoch = Math.max(4, ...werte) * 1.2;
  const B = 1000, H = 160, x = (i) => (i + .5) / n * B, y = (v) => H - 8 - v / hoch * (H - 24);
  let linie = `M 0 ${y(werte[0]).toFixed(1)} L ${x(0).toFixed(1)} ${y(werte[0]).toFixed(1)}`;
  for (let i = 1; i < n; i++) {
    const mitte = (x(i - 1) + x(i)) / 2;
    linie += ` C ${mitte.toFixed(1)} ${y(werte[i - 1]).toFixed(1)} ${mitte.toFixed(1)} ${y(werte[i]).toFixed(1)} ${x(i).toFixed(1)} ${y(werte[i]).toFixed(1)}`;
  }
  linie += ` L ${B} ${y(werte[n - 1]).toFixed(1)}`;
  const spitze = werte.indexOf(Math.max(...werte));
  const j = p.jetzt;
  const hinweis = (i, text, klasse = '') => `<span class="kurve-tip ${klasse}" style="left:${Math.max(7, Math.min(93, x(i) / B * 100)).toFixed(1)}%;top:${Math.max(0, y(werte[i]) / H * 100 - 16).toFixed(1)}%">${text}</span>`;
  return `<div class="karte-grund kurve"><svg viewBox="0 0 ${B} ${H}" preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id="kurve-f" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${handFarbe(0)}"/><stop offset="1" stop-color="${handFarbe(1)}"/></linearGradient></defs>
      ${p.teile.slice(1).map((t) => `<line x1="${(t.von / n * B).toFixed(1)}" x2="${(t.von / n * B).toFixed(1)}" y1="0" y2="${H}" stroke="rgba(255,255,255,.06)"/>`).join('')}
      <path d="${linie} L ${B} ${H} L 0 ${H} Z" fill="url(#kurve-f)" opacity=".14"/><path d="${linie}" fill="none" stroke="url(#kurve-f)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>
    ${werte[spitze] ? hinweis(spitze, `Takt ${spitze + 1} · ${werte[spitze]}×`) : ''}
    ${j && werte[j.von] && j.von !== spitze ? hinweis(j.von, `hier bist du · ${werte[j.von]}×`, 'jetzt') : ''}</div>`;
}

/* ---------- Vor dem Spielen (auf der Song-Seite) ---------- */
function vorabHtml() {
  const e = Einst.werte;
  return `<div class="karte-grund vorab" id="vorab">
    <div class="vorab-feld"><span class="klein">Hände</span><div class="ue-wahl" role="group" aria-label="Hände">${[['beide', 'Beide'], ['r', 'Rechts'], ['l', 'Links']].map(([k, t]) => `<button data-haende="${k}" aria-pressed="${e.haende === k}">${t}</button>`).join('')}</div></div>
    <div class="vorab-feld"><span class="klein">Tempo</span><div class="ue-tempo" role="group" aria-label="Tempo"><button data-stufe="-1" aria-label="Langsamer">−</button><span id="vorab-tempo">${e.tempo} %</span><button data-stufe="1" aria-label="Schneller">+</button></div></div>
    <div class="vorab-feld"><span class="klein" id="vorab-w">Wartemodus</span><button class="schalter" role="switch" data-schalter="warten" aria-labelledby="vorab-w" aria-checked="${e.warten}"></button></div>
    <div class="vorab-feld"><span class="klein" id="vorab-b">Band leise dazu</span><button class="schalter" role="switch" data-schalter="band" aria-labelledby="vorab-b" aria-checked="${e.band}"></button></div>
    <div class="vorab-feld breit"><span class="klein">Tastenbereich</span><canvas id="bereich" aria-hidden="true"></canvas></div></div>`;
}
function vorabBinden() {
  $('#vorab').addEventListener('click', (ev) => {
    const b = ev.target.closest('button');
    if (!b) return;
    if (b.dataset.haende) {
      Einst.setzen('haende', b.dataset.haende);
      for (const x of $('#vorab').querySelectorAll('[data-haende]')) x.setAttribute('aria-pressed', x === b);
      tastenbereichZeigen();
    } else if (b.dataset.stufe) {
      const i = STUFEN.indexOf(Einst.werte.tempo);
      Einst.setzen('tempo', STUFEN[Math.max(0, Math.min(STUFEN.length - 1, i + +b.dataset.stufe))]);
      $('#vorab-tempo').textContent = `${Einst.werte.tempo} %`;
    } else if (b.dataset.schalter) {
      const k = b.dataset.schalter;
      Einst.setzen(k, !Einst.werte[k]);
      b.setAttribute('aria-checked', Einst.werte[k]);
    }
  });
  tastenbereichZeigen();
}
async function tastenbereichZeigen() {
  const m = S.song, key = S.fassung;
  const liste = await noten(m.id, key).catch(() => []);
  const cv = $('#bereich');
  if (!cv || S.song !== m || S.fassung !== key) return;
  const h = Einst.werte.haende;
  const belegt = new Map();
  for (const [, , ton, hand] of liste) {
    if (h !== 'beide' && (h === 'r') !== !!hand) continue;
    if (!belegt.has(ton) || hand) belegt.set(ton, hand);
  }
  miniTasten(cv, 21, 108, (ton) => (belegt.has(ton) ? handFarbe(belegt.get(ton)) : null));
}
/** Kleine Klaviatur. farbe(ton) gibt die Leuchtfarbe einer Taste oder null. */
function miniTasten(cv, lo, hi, farbe) {
  const {c, w, h} = flaeche(cv);
  c.clearRect(0, 0, w, h);
  const weiss = (n) => [0, 2, 4, 5, 7, 9, 11].includes(n % 12);
  const weisse = [];
  for (let n = lo; n <= hi; n++) if (weiss(n)) weisse.push(n);
  const b = w / weisse.length;
  weisse.forEach((n, i) => {
    const f = farbe(n);
    c.fillStyle = f || 'rgba(255,255,255,.26)';
    if (f) { c.shadowColor = f; c.shadowBlur = 8; }
    c.beginPath(); c.roundRect(i * b + .5, 0, Math.max(1, b - 1), h, [0, 0, 2, 2]); c.fill();
    c.shadowBlur = 0;
  });
  for (let n = lo + 1; n < hi; n++) {
    if (weiss(n)) continue;
    const f = farbe(n);
    c.fillStyle = f || '#101013';
    const i = weisse.indexOf(n - 1);
    if (i >= 0) c.fillRect((i + 1) * b - b * .29, 0, b * .58, h * .6);
  }
}

/* ---------- Klavier verbinden ---------- */
function seiteKlavier() {
  const zeichnen = (an = new Map()) => {
    const cv = $('#verbinden-tasten');
    if (cv) miniTasten(cv, 48, 84, (ton) => (an.has(ton) ? handFarbe(ton >= 60) : null));
  };
  const seite = {
    an: new Map(),
    taste(ton, an) {
      if (an) { this.an.set(ton, true); this.erkannt = notenname(ton); } else this.an.delete(ton);
      zeichnen(this.an);
      this.stand();
    },
    klavierGeaendert() { this.stand(); },
    stand() {
      if (S.seite !== 'klavier') return;
      const da = !!Midi.ein;
      const kabel = $('#schritt-kabel');
      kabel.className = `schritt ${da ? 'fertig' : 'jetzt'}`;
      $('.nr', kabel).textContent = da ? '✓' : '1';
      $('.wert', kabel).textContent = da ? Midi.kurzname(Midi.ein) : 'wartet';
      const taste = $('#schritt-taste');
      taste.className = `schritt ${this.erkannt ? 'fertig' : da ? 'jetzt' : ''}`;
      $('.nr', taste).textContent = this.erkannt ? '✓' : '2';
      $('.wert', taste).textContent = this.erkannt ? `${this.erkannt} erkannt` : da ? 'wartet' : '';
      $('#testton').disabled = !Midi.aus;
      $('#klavier-fertig').disabled = !this.erkannt;
    },
  };
  $('#haupt').innerHTML = `<div class="auftritt verbinden"><div class="verbinden-kopf"><h1>Klavier verbinden</h1><span class="klein">Einmalig. Danach erkennt die App dein Klavier von selbst.</span></div>
    <div class="schritte">
      <div class="schritt" id="schritt-kabel"><div class="oben"><span class="nr">1</span><span class="titel">USB-Kabel vom Klavier an den Mac</span><span class="wert"></span></div></div>
      <div class="schritt" id="schritt-taste"><div class="oben"><span class="nr">2</span><span class="titel">Drück irgendeine Taste</span><span class="wert"></span></div>
        <canvas id="verbinden-tasten" aria-hidden="true"></canvas>
        <div class="verbinden-ton"><span class="klein">Ton kommt aus dem Klavier</span><button class="pille" id="testton">Testton spielen</button></div></div>
    </div>
    <div class="unten"><button class="pille" id="ohne-klavier">Ohne Klavier weiter</button><button class="haupt" id="klavier-fertig" disabled>Fertig</button></div></div>`;
  S.hoerer = seite;
  Midi.hoerer.add(seite);
  Midi.start().then(() => seite.stand());
  zeichnen();
  seite.stand();
  const abschluss = () => { Einst.setzen('klavierFertig', true); location.hash = '#zuhause'; };
  $('#ohne-klavier').addEventListener('click', abschluss);
  $('#klavier-fertig').addEventListener('click', abschluss);
  $('#testton').addEventListener('click', () => {
    Midi.note(60, true, 90);
    setTimeout(() => Midi.note(60, false), 700);
  });
}

/* ---------- Einstellungen ---------- */
const FARBEN = {
  links: [['Pink', '#FF4D7D'], ['Rosa', '#FF7AB6'], ['Orange', '#FFB347'], ['Flieder', '#B79CFF']],
  rechts: [['Gelb', '#FFE14D'], ['Orange', '#FFB347'], ['Flieder', '#B79CFF'], ['Rosa', '#FF7AB6']],
};
function seiteEinstellungen() {
  const zeile = (titel, inhalt, id) => `<div class="eins-zeile"><span ${id ? `id="${id}"` : ''}>${titel}</span>${inhalt}</div>`;
  const schalter = (k, titel) => zeile(titel, `<button class="schalter" role="switch" data-schalter="${k}" aria-label="${titel}" aria-checked="${Einst.werte[k]}"></button>`);
  const wahl = (k, art, titel) => {
    const namen = Midi.namen(art);
    const jetzt = (art === 'inputs' ? Midi.ein : Midi.aus)?.name;
    return zeile(titel, namen.length
      ? `<select class="wahl" data-wahl="${k}" aria-label="${titel}">${namen.map((n) => `<option ${n === jetzt ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>`
      : '<span class="klein">Kein Klavier</span>');
  };
  const farben = (k, titel) => zeile(titel, `<div class="farben" role="group" aria-label="${titel}">${FARBEN[k].map(([n, f]) => `<button aria-label="${n}" aria-pressed="${Einst.werte[k] === f}" data-farbe="${k}" data-wert="${f}" style="--f:${f}"></button>`).join('')}</div>`);
  const zeichnen = () => {
    if (S.seite !== 'einstellungen') return;
    $('#haupt').innerHTML = `<div class="eins">
      <section class="karte-grund eins-gruppe"><h2>Klavier</h2>${wahl('eingang', 'inputs', 'Eingang')}${wahl('ausgang', 'outputs', 'Ausgang')}${schalter('tonAmKlavier', 'Ton über das Klavier')}${zeile('Verbindung', '<a class="pille klein-pille" href="#klavier">Prüfen</a>')}</section>
      <section class="karte-grund eins-gruppe"><h2>Klang</h2>${schalter('band', 'Band leise dazu')}${zeile('Lautstärke der Band', `<span class="regler"><input type="range" id="band-laut" min="5" max="100" step="5" value="${Einst.werte.bandLaut}" aria-label="Lautstärke der Band"><span class="klein" id="band-wert">${Einst.werte.bandLaut} %</span></span>`)}</section>
      <section class="karte-grund eins-gruppe"><h2>Darstellung</h2>${farben('links', 'Linke Hand')}${farben('rechts', 'Rechte Hand')}${schalter('ruhig', 'Leiste beim Spielen ausblenden')}${schalter('noten', 'Notenblatt beim Start')}</section></div>`;
    const raum = $('#haupt');
    raum.onclick = (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.schalter) {
        const k = b.dataset.schalter;
        Einst.setzen(k, !Einst.werte[k]);
        b.setAttribute('aria-checked', Einst.werte[k]);
        if (k === 'tonAmKlavier') Midi.waehlen();
      } else if (b.dataset.farbe) {
        Einst.setzen(b.dataset.farbe, b.dataset.wert);
        for (const x of raum.querySelectorAll(`[data-farbe="${b.dataset.farbe}"]`)) x.setAttribute('aria-pressed', x === b);
      }
    };
    raum.onchange = (ev) => {
      const t = ev.target;
      if (t.dataset.wahl) { Einst.setzen(t.dataset.wahl, t.value); Midi.waehlen(); }
      if (t.id === 'band-laut') Einst.setzen('bandLaut', +t.value);
    };
    raum.oninput = (ev) => { if (ev.target.id === 'band-laut') $('#band-wert').textContent = `${ev.target.value} %`; };
  };
  S.hoerer = {klavierGeaendert: zeichnen};
  Midi.hoerer.add(S.hoerer);
  zeichnen();
  Midi.start().then(zeichnen);
}
