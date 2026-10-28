// Probe *_imaq.avi (and other .avi) entries in P1 archive via Range/ZIP64 central directory. Read-only listing.
import fs from 'node:fs';
const files = JSON.parse(fs.readFileSync(new URL('../data/fetch_manifest/figshare_files.json', import.meta.url), 'utf8'));
const parts = files.filter(f => /shape_analysis_P1\.zip/.test(f.title)).sort((a, b) => a.title.localeCompare(b.title));
let starts = [], acc = 0;
for (const p of parts) { starts.push(acc); acc += p.size; }
async function range(start, end) {
  const chunks = []; let pos = start;
  while (pos < end) {
    let i = parts.length - 1; while (i > 0 && starts[i] > pos) i--;
    const off = pos - starts[i], take = Math.min(parts[i].size - off, end - pos);
    const r = await fetch(parts[i].url || parts[i].download_url, { headers: { Range: `bytes=${off}-${off + take - 1}` } });
    chunks.push(Buffer.from(await r.arrayBuffer()).subarray(0, take)); pos += take;
  }
  return Buffer.concat(chunks);
}
const tail = await range(acc - 8 * 1024 * 1024, acc);
let cdOff = 0, cdSize = 0;
for (let i = tail.length - 56; i >= 0; i--) if (tail.readUInt32LE(i) === 0x06064b50) {
  cdSize = Number(tail.readBigUInt64LE(i + 40)); cdOff = Number(tail.readBigUInt64LE(i + 48)); break;
}
const cd = await range(cdOff, cdOff + cdSize);
let p = 0, avis = [];
while (p + 46 <= cd.length && cd.readUInt32LE(p) === 0x02014b50) {
  let csize = cd.readUInt32LE(p + 20), usize = cd.readUInt32LE(p + 24), lho = cd.readUInt32LE(p + 42);
  const nlen = cd.readUInt16LE(p + 28), elen = cd.readUInt16LE(p + 30), clen = cd.readUInt16LE(p + 32);
  const name = cd.subarray(p + 46, p + 46 + nlen).toString('utf8');
  const extra = cd.subarray(p + 46 + nlen, p + 46 + nlen + elen);
  let q = 0;
  while (q + 4 <= extra.length) { const tag = extra.readUInt16LE(q), len = extra.readUInt16LE(q + 2);
    if (tag === 1) { let r = q + 4;
      if (usize === 0xffffffff) { usize = Number(extra.readBigUInt64LE(r)); r += 8; }
      if (csize === 0xffffffff) { csize = Number(extra.readBigUInt64LE(r)); r += 8; }
      if (lho === 0xffffffff) { lho = Number(extra.readBigUInt64LE(r)); r += 8; } }
    q += 4 + len; }
  if (/\.avi$/i.test(name)) avis.push({ name, usize, csize, lho });
  p += 46 + nlen + elen + clen;
}
console.log('AVI entries:', avis.length);
avis.slice(0, 15).forEach(a => console.log(a.usize, a.name));
const imaq = avis.filter(a => /imaq/i.test(a.name));
console.log('IMAQ entries:', imaq.length);
imaq.slice(0, 10).forEach(a => console.log(a.usize, a.name));
fs.writeFileSync(new URL('../data/fetch_manifest/p1_avi_entries.json', import.meta.url),
  JSON.stringify(avis.map(a => ({ name: a.name.replace(/(^|\/)P1(?=[/(_])/g, '$1P1').replace(/_P1(?=\()/g, '_P1'), usize: a.usize })), null, 1));
