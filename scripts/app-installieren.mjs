// Baut die Mac-App und legt sie nach /Applications (oder ~/Applications, falls kein Schreibrecht).
// Die App merkt sich diesen Repo-Ordner: Oberfläche, Umwandler und Modell laufen von hier.
// Läuft sie gerade, wird sie vorher beendet und danach wieder geöffnet.
import { execSync } from 'node:child_process';
import { accessSync, constants, cpSync, existsSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';

const wurzel = resolve(import.meta.dirname, '..');
const sh = (c, o = {}) => execSync(c, { cwd: wurzel, stdio: 'inherit', ...o });
const merker = join(wurzel, 'desktop', 'wurzel.txt');

writeFileSync(merker, wurzel);
try {
  sh('npx electron-builder --mac --arm64 --dir', { env: { ...process.env, CSC_IDENTITY_AUTO_DISCOVERY: 'false' } });
} finally {
  rmSync(merker);
}
const gebaut = join(wurzel, 'dist/mac-arm64/Klavier-Trainer.app');
if (!existsSync(gebaut)) { console.error('Build fehlgeschlagen: ' + gebaut + ' fehlt'); process.exit(1); }
// Ad-hoc signieren: ohne gültige Signatur startet die App auf Apple-Silicon-Macs nicht
sh(`codesign --force --deep --sign - "${gebaut}"`);
sh(`codesign --verify --deep --strict "${gebaut}"`);

let ziel = '/Applications';
try { accessSync(ziel, constants.W_OK); } catch { ziel = join(homedir(), 'Applications'); }
const app = join(ziel, 'Klavier-Trainer.app');
let lief = false;
try { execSync('pgrep -f "Klavier-Trainer.app/Contents/MacOS/Klavier-Trainer"', { stdio: 'ignore' }); lief = true; } catch { /* läuft nicht */ }
if (lief) { try { execSync(`osascript -e 'quit app "Klavier-Trainer"'`); execSync('sleep 2'); } catch { /* egal */ } }
rmSync(app, { recursive: true, force: true });
cpSync(gebaut, app, { recursive: true, verbatimSymlinks: true });
console.log(`Installiert: ${app}`);
if (lief) execSync(`open "${app}"`);
