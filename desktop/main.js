/* Klavier-Trainer als Mac-App. Das Fenster zeigt app/index.html, der Umwandler (umwandler/dienst.py)
 * läuft unsichtbar mit: Er startet mit der App und endet mit ihr. Der Code liegt im Repo-Ordner,
 * die fertige App merkt sich den Pfad in wurzel.txt (scripts/app-installieren.mjs). */
const { app, BrowserWindow, Menu, dialog, session } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const wurzelDatei = path.join(__dirname, 'wurzel.txt');
const WURZEL = fs.existsSync(wurzelDatei) ? fs.readFileSync(wurzelDatei, 'utf8').trim() : path.join(__dirname, '..');
const PYTHON = path.join(WURZEL, '.venv', 'bin', 'python');
const HINTERGRUND = '#050507';
let dienst = null, fenster = null, adresse = null, beendet = false;

if (process.env.KLAVIER_PROFIL) app.setPath('userData', process.env.KLAVIER_PROFIL);
if (!app.requestSingleInstanceLock()) app.quit();
app.on('second-instance', () => { if (fenster) { if (fenster.isMinimized()) fenster.restore(); fenster.focus(); } });

function hinweisSeite(text) {
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(`<!doctype html><meta charset="utf-8"><body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:${HINTERGRUND};color:#EDEDF0;font:600 22px Geist,ui-sans-serif,system-ui,sans-serif;-webkit-app-region:drag">${text}</body>`);
}

function fensterOeffnen() {
  fenster = new BrowserWindow({
    width: 1280, height: 860, minWidth: 1040, minHeight: 620, backgroundColor: HINTERGRUND,
    titleBarStyle: 'hiddenInset', show: false,
    webPreferences: { contextIsolation: true, sandbox: true, backgroundThrottling: false }, // das Klavier spielt auch weiter, wenn das Fenster im Hintergrund ist
  });
  fenster.once('ready-to-show', () => fenster.show());
  fenster.on('closed', () => { fenster = null; });
  return fenster;
}

/** Erster Start ohne Umgebung: einrichten.sh läuft einmal im Hintergrund. */
function einrichten() {
  return new Promise((fertig, fehler) => {
    if (fs.existsSync(PYTHON) && fs.existsSync(path.join(WURZEL, '.modelle')) && fs.existsSync(path.join(WURZEL, '.venv-trennung'))) return fertig();
    fenster.loadURL(hinweisSeite('Wird eingerichtet, das dauert beim ersten Mal einige Minuten …'));
    const p = spawn('/bin/bash', [path.join(WURZEL, 'einrichten.sh')], { cwd: WURZEL, stdio: 'ignore' });
    p.on('error', fehler);
    p.on('exit', (code) => (code === 0 ? fertig() : fehler(new Error('Die Einrichtung ist fehlgeschlagen.'))));
  });
}

/** Startet den Dienst auf einem freien Port und wartet, bis er seinen Port meldet. */
function dienstStarten() {
  return new Promise((fertig, fehler) => {
    const daten = path.join(app.getPath('userData'), 'songs');
    dienst = spawn(PYTHON, ['-m', 'umwandler.dienst'], {
      cwd: WURZEL, stdio: ['ignore', 'pipe', 'inherit'],
      env: { ...process.env, KLAVIER_PORT: '0', KLAVIER_DATEN: daten, PYTHONUNBUFFERED: '1' },
    });
    let puffer = '';
    dienst.stdout.on('data', (d) => {
      puffer += d;
      const m = puffer.match(/bereit:(\d+)/);
      if (m) fertig(`http://127.0.0.1:${m[1]}`);
    });
    dienst.on('error', fehler);
    dienst.on('exit', () => {
      const war = adresse;
      dienst = null;
      if (beendet) return;
      if (!war) return fehler(new Error('Der Umwandler ließ sich nicht starten.'));
      dialog.showErrorBox('Klavier-Trainer', 'Der Umwandler ist abgestürzt. Bitte starte die App neu.');
      app.quit();
    });
  });
}

function dienstStoppen() {
  beendet = true;
  if (dienst) dienst.kill('SIGTERM');
}

/* Web MIDI für das Klavier: nur die eigene Seite darf */
function rechte() {
  const eigen = (url) => { try { return adresse && new URL(url).origin === adresse; } catch { return false; } };
  const erlaubt = new Set(['midi', 'midiSysex']);
  session.defaultSession.setPermissionRequestHandler((wc, recht, antwort) => antwort(erlaubt.has(recht) && eigen(wc.getURL())));
  session.defaultSession.setPermissionCheckHandler((_wc, recht, herkunft) => erlaubt.has(recht) && eigen(herkunft));
}

async function start() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { role: 'appMenu' }, { role: 'editMenu' }, { role: 'windowMenu' },
  ]));
  fensterOeffnen();
  try {
    await einrichten();
    adresse = await dienstStarten();
    rechte();
    await fenster.loadURL(adresse);
  } catch (e) {
    dialog.showErrorBox('Klavier-Trainer', e.message);
    app.quit();
  }
}

app.whenReady().then(start);
app.on('activate', () => { if (!fenster && adresse) fensterOeffnen().loadURL(adresse); });
app.on('window-all-closed', () => app.quit());
app.on('before-quit', dienstStoppen);
