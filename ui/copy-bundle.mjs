// Copies the single-file build to scripts/ui/, where the installer picks it up with the rest of scripts/.
import {copyFileSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, '..', 'scripts', 'ui');
mkdirSync(out, {recursive: true});
copyFileSync(join(here, 'dist', 'index.html'), join(out, 'sdlc-ui.html'));
const pkg = JSON.parse(readFileSync(join(here, 'package.json'), 'utf8'));
const html = readFileSync(join(out, 'sdlc-ui.html'));
writeFileSync(join(out, 'sdlc-ui.json'), JSON.stringify({
  name: 'sdlc-ui', version: pkg.version,
  a2ui: {lit: pkg.dependencies['@a2ui/lit'], web_core: pkg.dependencies['@a2ui/web_core'], protocol: '1.0'},
  sha256: createHash('sha256').update(html).digest('hex'), bytes: html.length,
}, null, 2) + '\n');
console.log(`scripts/ui/sdlc-ui.html (${html.length} bytes)`);
