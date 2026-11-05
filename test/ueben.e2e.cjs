// Prüft die Übungsansicht mit simuliertem Klavier: node test/ueben.e2e.cjs
// Eigener Datenordner, nie die echte Bibliothek. Keine Tastenfolge aus echten Songs.
const { chromium } = require('playwright');
const { spawn, execFileSync } = require('node:child_process');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const WURZEL = path.join(__dirname, '..');
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'klavier-ue-'));
const MID = path.join(TMP, 'Probe.mid');
const FOTOS = path.join(WURZEL, 'testlauf/ueben');
fs.mkdirSync(FOTOS, { recursive: true });
// Vier Takte bei 120 BPM: rechts Viertel, links Halbe
execFileSync(path.join(WURZEL, '.venv/bin/python'), ['-c', `
import pretty_midi as p,sys
m=p.PrettyMIDI(initial_tempo=120);r=p.Instrument(0,name='rechts');l=p.Instrument(0,name='links')
for i in range(16):r.notes.append(p.Note(90,60+(i%5)*2,i*.5,i*.5+.45))
for i in range(8):l.notes.append(p.Note(70,36+i%3,i*1.,i*1.+.9))
m.instruments=[r,l];m.write(sys.argv[1])`, MID]);
const FAKE = () => {
  const gesendet = []; window.__gesendet = gesendet;
  const ein = { name: 'Roland Digital Piano', state: 'connected', onmidimessage: null };
  const aus = { name: 'Roland Digital Piano', state: 'connected', send: (d) => gesendet.push([...d]) };
  window.__klavier = (ton, an) => ein.onmidimessage?.({ data: an ? [0x90, ton, 90] : [0x80, ton, 0] });
  navigator.requestMIDIAccess = async () => ({ inputs: new Map([['a', ein]]), outputs: new Map([['b', aus]]), onstatechange: null });
};
const ok = (t) => console.log('ok  ', t);
const warte = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const dienst = spawn(path.join(WURZEL, '.venv/bin/python'), ['-m', 'umwandler.dienst'], { cwd: WURZEL, env: { ...process.env, KLAVIER_PORT: '0', KLAVIER_DATEN: path.join(TMP, 'songs') }, stdio: ['ignore', 'pipe', 'inherit'] });
  const B = await new Promise((r) => dienst.stdout.on('data', (d) => { const m = String(d).match(/bereit:(\d+)/); if (m) r(`http://127.0.0.1:${m[1]}`); }));
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
  const fehler = []; p.on('pageerror', (e) => fehler.push(e.message));
  await p.addInitScript(FAKE);
  try {
    await p.goto(B + '/?ohnestart#neu');
    await p.setInputFiles('#waehler', MID);
    await p.waitForSelector('#songname');
    assert.strictEqual(await p.locator('[data-band="1"]').isVisible(), false);
    await p.click('#starten');
    await p.waitForSelector('#unten a.haupt', { timeout: 60000 });
    ok('Fertige MIDI wird ohne Rückfrage übernommen');
    await p.click('#unten a.haupt');
    await p.waitForSelector('#ueben-los');
    await p.click('#ueben-los');
    await p.waitForSelector('.ue-leiste');
    await warte(200);
    assert.ok((await p.textContent('#ue-klavier')).includes('FP-30X'));
    ok('Klavier wird erkannt');
    const uebung = () => p.evaluate(() => { const u = S.uebung; return { t: u.t, gi: u.gi, laeuft: u.laeuft, wartet: u.wartet, ruhig: u.leiste.classList.contains('ruhig'), sicher: [...u.sicher], schleife: u.schleife, tempo: u.tempo, gruppen: u.gruppen.length, fertig: u.fertig }; });
    await p.keyboard.press(' ');
    await warte(3200);
    let z = await uebung();
    assert.ok(z.wartet && z.gi === 0, 'hält am ersten Ton an');
    assert.ok(Math.abs(z.t) < .01);
    await p.screenshot({ path: path.join(FOTOS, 'warten.png') });
    ok('Wartemodus hält am ersten Ton an');
    await p.evaluate(() => window.__klavier(61, true));
    await p.evaluate(() => window.__klavier(61, false));
    await warte(100);
    z = await uebung();
    assert.strictEqual(z.gi, 0, 'falscher Ton geht nicht weiter');
    ok('Falscher Ton führt nicht weiter');
    await p.evaluate(() => { window.__klavier(60, true); window.__klavier(36, true); });
    await warte(150);
    z = await uebung();
    assert.ok(z.gi >= 1 && !z.wartet, 'richtige Töne gehen weiter');
    await p.evaluate(() => { window.__klavier(60, false); window.__klavier(36, false); });
    ok('Richtige Töne führen weiter');
    await warte(700);
    z = await uebung();
    assert.ok(z.wartet && z.gi === 1, 'wartet beim nächsten Ton');
    // Linke Hand übernimmt die App, rechte Hand übe ich
    await p.mouse.move(300, 300);
    await p.click('[data-haende="r"]');
    await warte(60);
    z = await uebung();
    assert.strictEqual(z.gruppen, 16);
    await p.evaluate(() => { window.__gesendet.length = 0; });
    const taktVor = await p.evaluate(() => S.uebung.t);
    for (let i = 0; i < 4; i++) {
      const toene = await p.evaluate(() => [...(S.uebung.gruppen[S.uebung.gi]?.rest || [])]);
      await p.evaluate((t) => { for (const x of t) { window.__klavier(x, true); window.__klavier(x, false); } }, toene);
      await warte(560);
    }
    const ges = await p.evaluate(() => window.__gesendet);
    assert.ok(ges.some(([s, t]) => s === 0x90 && t < 60), 'linke Hand kommt aus dem Klavier');
    ok('Hände einzeln: Die andere Hand spielt das Klavier');
    assert.ok((await p.evaluate(() => S.uebung.t)) > taktVor);
    await p.mouse.move(10, 400);
    await warte(2800);
    z = await uebung();
    assert.ok(z.ruhig, 'Leiste verschwindet beim Spielen');
    await p.screenshot({ path: path.join(FOTOS, 'spielen.png') });
    await p.mouse.move(40, 420);
    await warte(100);
    z = await uebung();
    assert.ok(!z.ruhig, 'Leiste kommt bei Mausbewegung');
    ok('Leiste verschwindet beim Spielen und kommt bei Bewegung');
    await p.keyboard.press(' ');
    await p.keyboard.press('ArrowDown');
    await p.keyboard.press('ArrowDown');
    z = await uebung();
    assert.strictEqual(z.tempo, 80);
    await p.mouse.move(310, 300);
    await p.click('[data-tempo="-1"]');
    assert.strictEqual((await uebung()).tempo, 70);
    assert.strictEqual(await p.textContent('#ue-tempo'), '70 %');
    ok('Tempo lässt sich ändern');
    // Schleife über Takt 2–3 ziehen
    const box = await p.locator('#ue-zellen').boundingBox();
    const zelle = (k) => box.x + box.width * ((k + .5) / 4);
    await p.mouse.move(zelle(1), box.y + box.height / 2);
    await p.mouse.down();
    await p.mouse.move(zelle(2), box.y + box.height / 2, { steps: 4 });
    await p.mouse.up();
    z = await uebung();
    assert.deepStrictEqual(z.schleife, [1, 2]);
    assert.ok(Math.abs(z.t - 2) < .02, 'springt an den Schleifenanfang');
    await p.screenshot({ path: path.join(FOTOS, 'schleife.png') });
    await p.mouse.move(330, 300);
    await p.click('#ue-warten');
    await p.click('[data-tempo="1"]'); await p.click('[data-tempo="1"]'); await p.click('[data-tempo="1"]');
    await p.keyboard.press(' ');
    await warte(4500);
    z = await uebung();
    assert.ok(z.t >= 2 && z.t < 6, 'Schleife springt zurück: ' + z.t);
    ok('Schleife läuft in Runden');
    await p.mouse.move(320, 300);
    await p.click('#ue-schleife');
    await p.evaluate(() => S.uebung.springen(7.4, true));
    await warte(1800);
    z = await uebung();
    assert.ok(z.fertig, 'Ende erreicht');
    await p.waitForSelector('.ue-ergebnis');
    await p.screenshot({ path: path.join(FOTOS, 'ergebnis.png') });
    ok('Ergebnis erscheint am Ende');
    const id = await p.evaluate(() => S.uebung.song.id);
    await warte(150);
    const stand = await (await p.request.get(`${B}/api/songs/${id}/fortschritt.json`)).json();
    assert.ok(stand.original && Array.isArray(stand.original.sicher));
    ok('Fortschritt wird gespeichert');
    await p.keyboard.press('Escape');
    await p.waitForFunction(() => document.querySelector('#ueben').hidden);
    await p.waitForSelector('#ueben-los');
    // Zweiter Durchgang: Knöpfe dürfen nach dem Wiederkommen nicht doppelt reagieren
    await p.click('#ueben-los');
    await p.waitForSelector('.ue-leiste');
    await warte(150);
    const vor = await p.evaluate(() => S.uebung.warten);
    await p.click('#ue-warten');
    assert.strictEqual(await p.evaluate(() => S.uebung.warten), !vor);
    await p.keyboard.press('Escape');
    await p.waitForFunction(() => document.querySelector('#ueben').hidden);
    const nach = await p.evaluate(() => window.__gesendet.slice(-2));
    assert.ok(nach.some(([s, c]) => s === 0xB0 && c === 123), 'beim Verlassen verstummt das Klavier');
    ok('Verlassen stellt alles still');
    assert.strictEqual(await p.locator('#meldung').isVisible(), false, 'keine Fehlermeldung');
    assert.deepStrictEqual(fehler, []);
    ok('Keine Fehler in der Oberfläche');
    console.log('Alles grün.');
  } catch (e) {
    await p.screenshot({ path: path.join(FOTOS, 'fehler.png') }).catch(() => {});
    console.error('FEHLER', e.message, '\nBrowser:', fehler.join(' | '));
    process.exitCode = 1;
  } finally {
    await b.close();
    dienst.kill();
    fs.rmSync(TMP, { recursive: true, force: true });
  }
})();
