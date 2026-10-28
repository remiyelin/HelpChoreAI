// Extract exact frames from Online/M10_*_imaq.avi (deflate-in-ZIP) via sequential Range + inflate.
// AVI frames are uncompressed 1280x48 grayscale DIBs inside 'movi'. Stops at maxFrame or output cap.
// Usage: node tools/extract_imaq_frames.mjs --patient=P1 --visit=0w --date=20170627 --run=M10 --frames=120,640,1200
import fs from 'node:fs';
import zlib from 'node:zlib';
const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v] = a.replace(/^--/, '').split('='); return [k, v]; }));
const PAT = args.patient || 'P1', DATE = args.date || '20170627', RUN = args.run || 'M10';
const TARGETS = new Set((args.frames || '120').split(',').map(Number));
const OUTDIR = `data/frames/${PAT}_${DATE}_${RUN}`;
fs.mkdirSync(OUTDIR, { recursive: true });
const files = JSON.parse(fs.readFileSync('data/fetch_manifest/figshare_files.json', 'utf8'));
const parts = files.filter(f => new RegExp(`shape_analysis_${PAT}\\.zip`).test(f.title)).sort((a, b) => a.title.localeCompare(b.title));
let starts = [], acc = 0; for (const p of parts) { starts.push(acc); acc += p.size; }
async function range(s, e) {
  const ch = []; let pos = s;
  while (pos < e) { let i = parts.length - 1; while (i > 0 && starts[i] > pos) i--;
    const off = pos - starts[i], take = Math.min(parts[i].size - off, e - pos);
    const r = await fetch(parts[i].url, { headers: { Range: `bytes=${off}-${off + take - 1}` } });
    if (r.status !== 206) throw new Error('range status ' + r.status);
    ch.push(Buffer.from(await r.arrayBuffer()).subarray(0, take)); pos += take; }
  return Buffer.concat(ch);
}
async function* rangeStream(s, e, chunk = 8 * 1024 * 1024) { let pos = s; while (pos < e) { const take = Math.min(chunk, e - pos); yield await range(pos, pos + take); pos += take; } }
// central directory
const tail = await range(acc - 8 * 1024 * 1024, acc);
let cdOff = 0, cdSize = 0;
for (let i = tail.length - 56; i >= 0; i--) if (tail.readUInt32LE(i) === 0x06064b50) { cdSize = Number(tail.readBigUInt64LE(i + 40)); cdOff = Number(tail.readBigUInt64LE(i + 48)); break; }
const cd = await range(cdOff, cdOff + cdSize);
let entry = null, p = 0;
while (p + 46 <= cd.length && cd.readUInt32LE(p) === 0x02014b50) {
  const method = cd.readUInt16LE(p + 10);
  let cs = cd.readUInt32LE(p + 20), us = cd.readUInt32LE(p + 24), lh = cd.readUInt32LE(p + 42);
  const nl = cd.readUInt16LE(p + 28), el = cd.readUInt16LE(p + 30), cl = cd.readUInt16LE(p + 32);
  const name = cd.subarray(p + 46, p + 46 + nl).toString('utf8');
  const ex = cd.subarray(p + 46 + nl, p + 46 + nl + el); let q = 0;
  while (q + 4 <= ex.length) { const t = ex.readUInt16LE(q), l = ex.readUInt16LE(q + 2);
    if (t === 1) { let r = q + 4; if (us === 0xffffffff) { us = Number(ex.readBigUInt64LE(r)); r += 8; } if (cs === 0xffffffff) { cs = Number(ex.readBigUInt64LE(r)); r += 8; } if (lh === 0xffffffff) { lh = Number(ex.readBigUInt64LE(r)); r += 8; } } q += 4 + l; }
  if (name.includes(`/${RUN}_`) && name.endsWith('_imaq.avi') && name.includes(DATE)) entry = { name, method, cs, us, lh };
  p += 46 + nl + el + cl;
}
if (!entry) throw new Error('imaq entry not found');
console.log('entry', entry.name, 'method', entry.method, 'usize', entry.us);
const lhBuf = await range(entry.lh, entry.lh + 30);
const dataStart = entry.lh + 30 + lhBuf.readUInt16LE(26) + lhBuf.readUInt16LE(28);
// sequential inflate, AVI parse
const inflate = zlib.createInflateRaw();
let buf = Buffer.alloc(0), frameIdx = -1, inMovi = false, width = 0, height = 0, saved = [];
const maxTarget = Math.max(...TARGETS);
async function feed(chunk) {
  buf = Buffer.concat([buf, chunk]);
  // parse RIFF/hdrl minimally: find 'avih' for w/h and 'movi'
  if (!width) { const i = buf.indexOf('avih'); if (i >= 0 && buf.length > i + 56) { width = buf.readUInt32LE(i + 40); height = buf.readUInt32LE(i + 44); console.log('AVI dimensions', width, 'x', height); } }
  const mi = buf.indexOf('movi');
  if (!inMovi) { if (mi < 0) { if (buf.length > 4 * 1024 * 1024) buf = buf.subarray(buf.length - 1024); return; } inMovi = true; buf = buf.subarray(mi + 4); }
  while (buf.length >= 8) {
    const id = buf.subarray(0, 4).toString('ascii'); const sz = buf.readUInt32LE(4);
    if (!/^(00|01)(db|dc|wb)$/.test(id)) { // resync: list chunk or junk
      if (id === 'LIST' || id === 'JUNK') { if (buf.length < 8 + sz) return; buf = buf.subarray(8 + sz + (sz % 2)); continue; }
      buf = buf.subarray(1); continue; }
    if (buf.length < 8 + sz) return;
    frameIdx++;
    if (TARGETS.has(frameIdx)) {
      const raw = buf.subarray(8, 8 + sz);
      fs.writeFileSync(`${OUTDIR}/frame_${frameIdx}.raw`, raw);
      fs.writeFileSync(`${OUTDIR}/frame_${frameIdx}.json`, JSON.stringify({ width, height, bytes: sz, frame: frameIdx }));
      saved.push(frameIdx); console.log('saved frame', frameIdx, sz, 'bytes');
    }
    buf = buf.subarray(8 + sz + (sz % 2));
    if (frameIdx >= maxTarget) break;
  }
}
const { Readable, Writable } = await import('node:stream');
const { pipeline } = await import('node:stream/promises');
const src = Readable.from(rangeStream(dataStart, dataStart + entry.cs));
const sink = new Writable({ async write(chunk, enc, cb) { try { await feed(chunk); if (frameIdx >= maxTarget) { src.destroy(); inflate.destroy(); } cb(); } catch (e) { cb(e); } } });
try { await pipeline(src, inflate, sink); } catch (e) { if (frameIdx < maxTarget) throw e; }
console.log('DONE saved', saved, 'to', OUTDIR);
