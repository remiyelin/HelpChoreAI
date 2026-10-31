// P-23 Part C only: fetch Offline M10 pickles for the sealed patients from the
// Figshare shape_analysis ZIPs via HTTP Range. Entry names inside the archive
// carry author codes; they are renamed through the git-ignored initials map
// and raw entry names are never printed. Output:
// data/dev/<P>/<P>__<date>_<P>(<visit>)__Offline__M10_results.p
import fs from 'node:fs';
import zlib from 'node:zlib';

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\//, '');
const MAP = JSON.parse(fs.readFileSync(ROOT + 'private/initials_map.json', 'utf8'));
const files = JSON.parse(fs.readFileSync(ROOT + 'data/fetch_manifest/figshare_files.json', 'utf8'));

function partsFor(p) {
  return files.filter(f => new RegExp(`shape_analysis_${p}\\.zip`).test(f.title))
    .sort((a, b) => a.title.localeCompare(b.title));
}
async function range(parts, starts, s, e) {
  const ch = []; let pos = s;
  while (pos < e) {
    let i = parts.length - 1; while (i > 0 && starts[i] > pos) i--;
    const off = pos - starts[i], take = Math.min(parts[i].size - off, e - pos);
    const r = await fetch(parts[i].url, { headers: { Range: `bytes=${off}-${off + take - 1}` } });
    if (r.status !== 206) throw new Error('range status ' + r.status);
    ch.push(Buffer.from(await r.arrayBuffer()).subarray(0, take)); pos += take;
  }
  return Buffer.concat(ch);
}
function deidentify(name, archivePatient) {
  for (const [init, p] of Object.entries(MAP)) {
    const owns = new RegExp(`(^|/)${init}(?=[/(_])|_${init}(?=[(])`).test(name);
    if (owns && p !== archivePatient) return null;
  }
  let out = name;
  for (const [init, p] of Object.entries(MAP)) {
    out = out.replace(new RegExp(`(^|/)${init}(?=[/(_])`, 'g'), `$1${p}`);
    out = out.replace(new RegExp(`_${init}(?=[(])`, 'g'), `_${p}`);
  }
  return out;
}

for (const patient of ['P3', 'P5']) {
  const parts = partsFor(patient);
  const starts = []; let acc = 0;
  for (const p of parts) { starts.push(acc); acc += p.size; }
  const tail = await range(parts, starts, Math.max(0, acc - 8 * 1024 * 1024), acc);
  let cdOff = 0, cdSize = 0;
  for (let i = tail.length - 56; i >= 0; i--) if (tail.readUInt32LE(i) === 0x06064b50) { cdSize = Number(tail.readBigUInt64LE(i + 40)); cdOff = Number(tail.readBigUInt64LE(i + 48)); break; }
  const cd = await range(parts, starts, cdOff, cdOff + cdSize);
  const entries = [];
  let p = 0;
  while (p + 46 <= cd.length && cd.readUInt32LE(p) === 0x02014b50) {
    const method = cd.readUInt16LE(p + 10);
    let cs = cd.readUInt32LE(p + 20), us = cd.readUInt32LE(p + 24), lh = cd.readUInt32LE(p + 42);
    const nl = cd.readUInt16LE(p + 28), el = cd.readUInt16LE(p + 30), cl = cd.readUInt16LE(p + 32);
    const name = cd.subarray(p + 46, p + 46 + nl).toString('utf8');
    const ex = cd.subarray(p + 46 + nl, p + 46 + nl + el); let q = 0;
    while (q + 4 <= ex.length) { const t = ex.readUInt16LE(q), l = ex.readUInt16LE(q + 2);
      if (t === 1) { let r = q + 4; if (us === 0xffffffff) { us = Number(ex.readBigUInt64LE(r)); r += 8; } if (cs === 0xffffffff) { cs = Number(ex.readBigUInt64LE(r)); r += 8; } if (lh === 0xffffffff) { lh = Number(ex.readBigUInt64LE(r)); r += 8; } } q += 4 + l; }
    if (/Offline\/M10_results\.p$/.test(name)) entries.push({ name, method, cs, us, lh });
    p += 46 + nl + el + cl;
  }
  console.log(`${patient}: ${entries.length} offline M10 pickles in archive`);
  for (const e of entries) {
    const clean = deidentify(e.name, patient);
    if (!clean) { console.log(`${patient}: skipped nested other-patient entry`); continue; }
    // clean like P3/20170809_P3(0w)/Offline/M10_results.p
    const m = clean.match(/^(P\d)\/(\d{8})_(P\d\(([^)]+)\))\/Offline\/M10_results\.p$/);
    if (!m) { console.log(`${patient}: unparsed sanitized entry, skipped`); continue; }
    const outName = `${m[1]}__${m[2]}_${m[3]}__Offline__M10_results.p`;
    const outDir = `${ROOT}data/dev/${patient}`;
    fs.mkdirSync(outDir, { recursive: true });
    const outPath = `${outDir}/${outName}`;
    if (fs.existsSync(outPath) && fs.statSync(outPath).size === e.us) { console.log(`${patient} ${m[2]}: cached on disk`); continue; }
    const lhBuf = await range(parts, starts, e.lh, e.lh + 30);
    const dataStart = e.lh + 30 + lhBuf.readUInt16LE(26) + lhBuf.readUInt16LE(28);
    const raw = await range(parts, starts, dataStart, dataStart + e.cs);
    const data = e.method === 8 ? zlib.inflateRawSync(raw) : raw;
    if (data.length !== e.us) throw new Error(`size mismatch ${data.length} != ${e.us}`);
    fs.writeFileSync(outPath, data);
    console.log(`${patient} ${m[2]}: wrote ${outName} (${data.length} bytes)`);
  }
}
