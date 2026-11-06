// Parses every script of the PWA as ES2018: the newest syntax Safari 12 (iOS 12.0-12.5) understands.
// (Optional chaining, ??, class fields, optional catch binding, BigInt ... would make a whole file fail to load there.)
// usage: node tests/check_syntax.js <path to acorn.js> [files...]
const fs = require('fs');
const path = require('path');
const acorn = require(process.argv[2]);
const root = path.join(__dirname, '..', 'web');
let files = process.argv.slice(3);
if (!files.length) {
  files = fs.readdirSync(path.join(root, 'js')).filter(f => f.endsWith('.js')).map(f => path.join(root, 'js', f));
  files.push(path.join(root, 'sw.js'), path.join(root, 'vendor', 'qrcode.js'));
}
let bad = 0;
for (const f of files) {
  const src = fs.readFileSync(f, 'utf8');
  try {
    acorn.parse(src, { ecmaVersion: 2018, sourceType: 'script' });
    console.log('ES2018 ok  ', path.relative(root, f));
  } catch (e) {
    bad++;
    console.log('NOT ES2018 ', path.relative(root, f), '-', e.message);
  }
}
// APIs that do not exist in Safari 12 (a quick text scan of our own files)
const risky = [/\?\?/, /\?\./, /\.replaceAll\(/, /\.matchAll\(/, /Promise\.allSettled/, /\.at\(-?\d/, /structuredClone/, /ResizeObserver/, /\bnew AbortController/, /\.flat\(/, /\bObject\.fromEntries/, /\.finally\(/, /\bBigInt/, /\(\?<[=!]/];
for (const f of files.filter(f => !f.includes('vendor'))) {
  const lines = fs.readFileSync(f, 'utf8').split('\n');
  lines.forEach((l, i) => {
    if (/^\s*(\/\/|\*|\/\*)/.test(l)) return;
    for (const re of risky) if (re.test(l.replace(/'[^']*'|"[^"]*"/g, "''"))) console.log('  check API', path.relative(root, f) + ':' + (i + 1), re.source, '->', l.trim().slice(0, 100));
  });
}
process.exit(bad ? 1 : 0);
