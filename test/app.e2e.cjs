// Prüft die fertige Mac-App von außen: node test/app.e2e.cjs [Pfad zur App]
// Eigenes Profil im Temp-Ordner, nie die echte Bibliothek. Braucht testlauf/aufnahmen (test/testaufnahmen.py).
const { chromium } = require('playwright');
const { execSync, spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert');

const WURZEL = path.join(__dirname, '..');
const APP = process.argv[2] || '/Applications/Klavier-Trainer.app/Contents/MacOS/Klavier-Trainer';
const PROFIL = fs.mkdtempSync(path.join(os.tmpdir(), 'klavier-'));
const AUFNAHME = path.join(WURZEL, 'testlauf/aufnahmen/1-aufnahme.wav');
const FOTOS = path.join(WURZEL, 'testlauf/app');
fs.mkdirSync(FOTOS, { recursive: true });
const warte = (ms) => new Promise((r) => setTimeout(r, ms));
/** Startet die fertige App wie ein Doppelklick und hängt sich von außen ans Fenster. */
async function start() {
  const proz = spawn(APP, ['--remote-debugging-port=9337'], { env: { ...process.env, KLAVIER_PROFIL: PROFIL }, stdio: 'ignore' });
  for (let i = 0; i < 60; i++) {
    await warte(500);
    try {
      const browser = await chromium.connectOverCDP('http://127.0.0.1:9337');
      const seite = browser.contexts().flatMap((c) => c.pages()).find((p) => p.url().startsWith('http://127.0.0.1'));
      if (seite) return { proz, browser, seite };
      await browser.close();
    } catch { /* noch nicht bereit */ }
  }
  throw new Error('Das App-Fenster kommt nicht.');
}
/** Beendet die App wie das Schließen des Fensters. */
async function schliessen(a) {
  const weg = new Promise((r) => a.proz.once('exit', r));
  await a.seite.evaluate(() => window.close()).catch(() => {});
  await Promise.race([weg, warte(8000)]);
  await warte(1000);
}
const dienste = () => { try { return execSync(`pgrep -f "umwandler.(dienst|auftrag)" | wc -l`).toString().trim(); } catch { return '0'; } };
const ok = (t) => console.log('ok  ', t);

(async () => {
  const vorher = dienste();
  let app = await start();
  let w = app.seite;
  const fehler = [];
  w.on('pageerror', (e) => fehler.push(e.message));
  await w.waitForSelector('#los');
  ok('App startet ohne Terminal, Start erscheint');
  assert.ok(Number(dienste()) > Number(vorher));
  ok('Umwandler läuft mit');

  const midi = await w.evaluate(async () => { const a = await navigator.requestMIDIAccess(); return a.inputs.size + a.outputs.size >= 0; });
  assert.strictEqual(midi, true);
  ok('Web MIDI ist in der App erlaubt');

  await w.waitForTimeout(3600);
  await w.screenshot({ path: path.join(FOTOS, 'start.png') });
  await w.click('#los');
  await w.waitForSelector('#ohne-klavier');
  await w.click('#ohne-klavier');
  await w.waitForSelector('.held');
  await w.setInputFiles('#waehler', AUFNAHME);
  await w.waitForSelector('#songname');
  await w.fill('#songname', 'Abbruch-Test');
  await w.click('#starten');
  await w.waitForSelector('#schritte');
  await w.waitForFunction(() => /[1-9]\d* %/.test(document.querySelector('.schritt.jetzt .wert')?.textContent || ''), null, { timeout: 90000 });
  ok('Fortschritt zählt hoch: ' + await w.textContent('.schritt.jetzt .wert'));
  await w.screenshot({ path: path.join(FOTOS, 'umwandeln.png') });

  await schliessen(app);
  assert.strictEqual(dienste(), vorher);
  ok('App beendet: Umwandler und laufende Umwandlung sind mit weg');

  app = await start();
  w = app.seite;
  w.on('pageerror', (e) => fehler.push(e.message));
  await w.waitForSelector('#los');
  await w.click('#los');
  await w.click('#menue a[href="#songs"]');
  await w.waitForSelector('.karte');
  ok('Neustart: Song ist noch da, Umwandlung läuft weiter: ' + (await w.textContent('.karte .stand')));
  await w.click('.karte');
  await w.waitForSelector('#unten a.haupt', { timeout: 180000 });
  await w.click('#unten a.haupt');
  await w.waitForSelector('#rolle');
  await w.waitForTimeout(500);
  await w.screenshot({ path: path.join(FOTOS, 'song.png') });
  ok('Fertig umgewandelt: ' + await w.textContent('.titelzeile .klein'));

  await w.click('#spiel');
  await w.waitForTimeout(1000);
  const t = await w.evaluate(() => document.querySelector('#ton').currentTime);
  assert.ok(t > 0.3, 'Hörprobe läuft nicht: ' + t);
  ok('Hörprobe spielt');
  await w.click('#spiel');

  const midi2 = await w.evaluate(async () => {
    const a = document.querySelector('#laden');
    const r = await fetch(a.href);
    const b = new Uint8Array(await r.arrayBuffer());
    return { kopf: String.fromCharCode(...b.slice(0, 4)), name: r.headers.get('content-disposition') };
  });
  assert.strictEqual(midi2.kopf, 'MThd');
  assert.ok(midi2.name.includes('.mid'));
  ok('MIDI-Export liefert eine MIDI-Datei');

  assert.strictEqual(await w.locator('#menue').isVisible(), true);
  await w.click('#menue a[href="#songs"]');
  await w.waitForSelector('.karte');
  assert.strictEqual(await w.locator('#menue').isVisible(), true);
  await w.screenshot({ path: path.join(FOTOS, 'songs.png') });
  ok('Menü steht auf jedem Bildschirm');

  await schliessen(app);
  assert.strictEqual(dienste(), vorher);
  assert.deepStrictEqual(fehler, []);
  ok('Keine Fehler in der Oberfläche');
  fs.rmSync(PROFIL, { recursive: true, force: true });
  console.log('Alles grün.');
})().catch((e) => { console.error('FEHLER', e.message); process.exit(1); });
