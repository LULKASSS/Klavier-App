// Klickt die App wie Lukas durch. Braucht den Dienst mit zwei fertigen Songs (siehe CLAUDE.md, Befehle).
import path from 'node:path';

const AUFNAHME = path.resolve('testlauf/zum-anhoeren/1-aufnahme – Testaufnahme.m4a');

export default async (page, foto) => {
  await page.waitForSelector('#start:not([hidden])', {timeout: 2000}).catch(() => {});
  if (await page.locator('#los').isVisible()) {
    await page.waitForTimeout(4200); // Noten sind angekommen, Tasten leuchten
    await foto('start');
    await page.click('#los');
    await page.waitForTimeout(1100);
  }
  await page.waitForSelector('.karte');
  await page.waitForTimeout(400);
  await foto('songs');

  await page.click('#menue a[href="#neu"]');
  await page.waitForSelector('#grossablage');
  await foto('hinzufuegen');
  await page.setInputFiles('#waehler', AUFNAHME);
  await page.waitForSelector('#songname');
  await page.click('[data-band="1"]');
  await page.waitForTimeout(200);
  await foto('neu-band');
  await page.click('#abbrechen');

  await page.click('#menue a[href="#songs"]');
  await page.waitForSelector('.karte');
  await page.click('.karte');
  await page.waitForSelector('#rolle');
  await page.waitForTimeout(500);
  await foto('song');
  await page.click('[data-fassung="original"]');
  await page.waitForTimeout(400);
  await page.click('#spiel');
  await page.waitForTimeout(1500);
  await page.click('#spiel');
  await foto('song-original');
  await page.click('[data-quelle="aufnahme"]');
  await page.waitForTimeout(300);
  await page.click('[data-quelle="fassung"]');
};
