// Batch: extract adjudication-queue frames, one sequential inflate per M10 run.
// Usage: node tools/extract_queue_frames.mjs [--max-frame=20000] [--patient=P1] [--date=20170627]
// Existing frame files are skipped. Progress: data/frames/coverage.json updated after each run.
import fs from 'node:fs';
import zlib from 'node:zlib';
import { Readable, Writable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
const argv = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v] = a.replace(/^--/, '').split('='); return [k, v ?? true]; }));
const MAXF = Number(argv['max-frame'] || 20000);
const targets = JSON.parse(fs.readFileSync('data/frames/targets.json', 'utf8'));
const files = JSON.parse(fs.readFileSync('data/fetch_manifest/figshare_files.json', 'utf8'));

async function extractRun(patient, date, want) {
  const parts = files.filter(f => new RegExp(`shape_analysis_${patient}\\.zip`).test(f.title)).sort((a, b) => a.title.localeCompare(b.title));
  let starts = [], acc = 0; for (const p of parts) { starts.push(acc); acc += p.size; }
  async function range(s, e) { const ch = []; let pos = s;
    while (pos < e) { let i = parts.length - 1; while (i > 0 && starts[i] > pos) i--;
      const off = pos - starts[i], take = Math.min(parts[i].size - off, e - pos);
      const r = await fetch(parts[i].url, { headers: { Range: `bytes=${off}-${off + take - 1}` } });
      if (r.status !== 206) throw new Error('range ' + r.status);
      ch.push(Buffer.from(await r.arrayBuffer()).subarray(0, take)); pos += take; }
    return Buffer.concat(ch); }
  async function* stream(s, e, chunk = 8 * 1024 * 1024) { let pos = s; while (pos < e) { const take = Math.min(chunk, e - pos); yield await range(pos, pos + take); pos += take; } }
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
    if (name.includes('/M10_') && name.endsWith('_imaq.avi') && name.includes(date)) entry = { name, method, cs, us, lh };
    p += 46 + nl + el + cl; }
  if (!entry) { console.log('NO ENTRY', patient, date); return 0; }
  const outdir = `data/frames/${patient}_${date}_M10`; fs.mkdirSync(outdir, { recursive: true });
  const wantMap = new Map(); // frame -> [cells]
  for (const t of want) { if (t.frame > MAXF) continue; if (fs.existsSync(`${outdir}/frame_${t.frame}.raw`)) continue;
    if (!wantMap.has(t.frame)) wantMap.set(t.frame, []); wantMap.get(t.frame).push(t.cell); }
  if (!wantMap.size) { console.log(patient, date, 'nothing new'); return 0; }
  const maxTarget = Math.max(...wantMap.keys());
  const lhBuf = await range(entry.lh, entry.lh + 30);
  const dataStart = entry.lh + 30 + lhBuf.readUInt16LE(26) + lhBuf.readUInt16LE(28);
  let buf = Buffer.alloc(0), frameIdx = -1, inMovi = false, width = 0, height = 0, saved = 0;
  async function feed(chunk) {
    buf = Buffer.concat([buf, chunk]);
    if (!width) { const i = buf.indexOf('avih'); if (i >= 0 && buf.length > i + 56) { width = buf.readUInt32LE(i + 40); height = buf.readUInt32LE(i + 44); } }
    const mi = buf.indexOf('movi');
    if (!inMovi) { if (mi < 0) { if (buf.length > 4 * 1024 * 1024) buf = buf.subarray(buf.length - 1024); return; } inMovi = true; buf = buf.subarray(mi + 4); }
    while (buf.length >= 8) {
      const id = buf.subarray(0, 4).toString('ascii'); const sz = buf.readUInt32LE(4);
      if (!/^(00|01)(db|dc|wb)$/.test(id)) { if (id === 'LIST' || id === 'JUNK') { if (buf.length < 8 + sz) return; buf = buf.subarray(8 + sz + (sz % 2)); continue; } buf = buf.subarray(1); continue; }
      if (buf.length < 8 + sz) return;
      frameIdx++;
      if (wantMap.has(frameIdx)) { fs.writeFileSync(`${outdir}/frame_${frameIdx}.raw`, buf.subarray(8, 8 + sz));
        fs.writeFileSync(`${outdir}/frame_${frameIdx}.json`, JSON.stringify({ width, height, bytes: sz, frame: frameIdx })); saved++; }
      buf = buf.subarray(8 + sz + (sz % 2));
      if (frameIdx >= maxTarget) break; } }
  const inflate = zlib.createInflateRaw();
  const src = Readable.from(stream(dataStart, dataStart + entry.cs));
  const sink = new Writable({ async write(chunk, enc, cb) { try { await feed(chunk); if (frameIdx >= maxTarget) { src.destroy(); inflate.destroy(); } cb(); } catch (e) { cb(e); } } });
  try { await pipeline(src, inflate, sink); } catch (e) { if (frameIdx < maxTarget) throw e; }
  console.log(patient, date, 'saved', saved, 'frames up to', maxTarget);
  return saved;
}

let total = 0;
for (const patient of Object.keys(targets).sort()) {
  if (argv.patient && patient !== argv.patient) continue;
  for (const date of Object.keys(targets[patient]).sort()) {
    if (argv.date && date !== argv.date) continue;
    total += await extractRun(patient, date, targets[patient][date]);
    // coverage snapshot
    let have = 0, want = 0;
    for (const [pp, dd] of Object.entries(targets)) for (const [dt, rows] of Object.entries(dd)) {
      want += rows.length;
      for (const r of rows) if (fs.existsSync(`data/frames/${pp}_${dt}_M10/frame_${r.frame}.raw`)) have++; }
    fs.writeFileSync('data/frames/coverage.json', JSON.stringify({ have, want, updated: new Date().toISOString() }, null, 1));
    console.log('COVERAGE', have, '/', want);
  }
}
console.log('BATCH DONE new frames:', total);
