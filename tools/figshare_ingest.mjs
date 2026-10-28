// HelpChoreAI Step 1: Figshare Collection 5793482 Range / ZIP64 ingest.
// Dev patients P1,P2,P4: list central directory + extract Results/*.txt + sample contours/frames.
// Holdout P3,P5: SEALED - only hashed central-directory manifest, no entry names stored, no content fetched.
// Usage: node tools/figshare_ingest.mjs [--list-only] [--patient P1]
import fs from 'node:fs';
import zlib from 'node:zlib';
import crypto from 'node:crypto';

const API = 'https://api.figshare.com/v2/collections/5793482/articles?page_size=100';
const ROOT = new URL('..', import.meta.url).pathname.replace(/^\//, '');
const MANIFEST_DIR = ROOT + 'data/fetch_manifest';
const DEV_DIR = ROOT + 'data/dev';
const DEV = new Set(['P1', 'P2', 'P4']);
// Authors' initial codes -> P-codes (notebook order). Used ONLY to rename on ingest; initials are never written to disk.
const CODE = { P1: 'P1', P2: 'P2', P3: 'P3', P4: 'P4', P5: 'P5' };
function deidentify(name, archivePatient) {
  // Returns sanitized name, or null if the entry belongs to a different (nested) patient -> skip.
  // Any occurrence of an initial code as a path segment or as _XX( visit token counts as ownership.
  for (const [init, p] of Object.entries(CODE)) {
    const owns = new RegExp(`(^|/)${init}(?=[/(_])|_${init}(?=[(])`).test(name);
    if (owns && p !== archivePatient) return null;
  }
  let out = name;
  for (const [init, p] of Object.entries(CODE)) {
    out = out.replace(new RegExp(`(^|/)${init}(?=[/(_])`, 'g'), `$1${p}`);
    out = out.replace(new RegExp(`_${init}(?=[(])`, 'g'), `_${p}`);
  }
  return out;
}
const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
fs.mkdirSync(MANIFEST_DIR, { recursive: true });
fs.mkdirSync(DEV_DIR, { recursive: true });

async function articleFiles() {
  const arts = await (await fetch(API)).json();
  const out = [];
  for (const a of arts) {
    const d = await (await fetch('https://api.figshare.com/v2/articles/' + a.id)).json();
    const f = (d.files || [])[0] || {};
    out.push({ id: a.id, title: a.title, size: f.size, md5: f.computed_md5 || null, url: f.download_url });
  }
  return out;
}

function patientParts(files) {
  const groups = {};
  for (const f of files) {
    const m = f.title.match(/shape_analysis_(P\d+)\.zip(?:\.(\d+))?/);
    if (!m) continue;
    (groups[m[1]] ||= []).push({ ...f, part: m[2] ? parseInt(m[2], 10) : 1 });
  }
  for (const k of Object.keys(groups)) groups[k].sort((a, b) => a.part - b.part);
  return groups;
}

// Virtual concatenated split-archive reader over HTTP Range.
class SplitReader {
  constructor(parts) {
    this.parts = parts;
    this.starts = [];
    let acc = 0;
    for (const p of parts) { this.starts.push(acc); acc += p.size; }
    this.total = acc;
  }
  async range(start, endExclusive) {
    const end = Math.min(endExclusive, this.total);
    const chunks = [];
    let pos = start;
    while (pos < end) {
      let i = this.parts.length - 1;
      while (i > 0 && this.starts[i] > pos) i--;
      const part = this.parts[i];
      const off = pos - this.starts[i];
      const take = Math.min(part.size - off, end - pos);
      const res = await fetch(part.url, { headers: { Range: `bytes=${off}-${off + take - 1}` } });
      if (res.status !== 206 && res.status !== 200) throw new Error(`Range failed ${res.status} part ${part.part}`);
      const buf = Buffer.from(await res.arrayBuffer());
      chunks.push(buf.subarray(0, take));
      pos += take;
    }
    return Buffer.concat(chunks);
  }
}

function findEocd64(tail, totalSize, tailStart) {
  // Search backwards for ZIP64 EOCD record signature 0x06064b50, then locator 0x07064b50.
  for (let i = tail.length - 56; i >= 0; i--) {
    if (tail.readUInt32LE(i) === 0x06064b50) {
      const cdSize = Number(tail.readBigUInt64LE(i + 40));
      const cdOff = Number(tail.readBigUInt64LE(i + 48));
      const count = Number(tail.readBigUInt64LE(i + 32));
      return { cdSize, cdOff, count, eocdAbs: tailStart + i };
    }
  }
  // Fallback: classic EOCD 0x06054b50 with ZIP64 sentinel values.
  for (let i = tail.length - 22; i >= 0; i--) {
    if (tail.readUInt32LE(i) === 0x06054b50) {
      return { cdSize: tail.readUInt32LE(i + 12), cdOff: tail.readUInt32LE(i + 16), count: tail.readUInt16LE(i + 10), eocdAbs: tailStart + i };
    }
  }
  throw new Error('EOCD not found in tail window');
}

function parseCentralDirectory(cd, count) {
  const entries = [];
  let p = 0;
  while (p + 46 <= cd.length && entries.length < count + 5) {
    if (cd.readUInt32LE(p) !== 0x02014b50) break;
    const method = cd.readUInt16LE(p + 10);
    let csize = cd.readUInt32LE(p + 20);
    let usize = cd.readUInt32LE(p + 24);
    let lho = cd.readUInt32LE(p + 42);
    const nlen = cd.readUInt16LE(p + 28), elen = cd.readUInt16LE(p + 30), clen = cd.readUInt16LE(p + 32);
    const name = cd.subarray(p + 46, p + 46 + nlen).toString('utf8');
    const extra = cd.subarray(p + 46 + nlen, p + 46 + nlen + elen);
    // ZIP64 extra field 0x0001: usize, csize, lho (only for sentinel fields, in that order).
    let q = 0;
    while (q + 4 <= extra.length) {
      const tag = extra.readUInt16LE(q), len = extra.readUInt16LE(q + 2);
      if (tag === 0x0001) {
        let r = q + 4;
        if (usize === 0xffffffff) { usize = Number(extra.readBigUInt64LE(r)); r += 8; }
        if (csize === 0xffffffff) { csize = Number(extra.readBigUInt64LE(r)); r += 8; }
        if (lho === 0xffffffff) { lho = Number(extra.readBigUInt64LE(r)); r += 8; }
      }
      q += 4 + len;
    }
    entries.push({ name, method, csize, usize, lho });
    p += 46 + nlen + elen + clen;
  }
  return entries;
}

async function extractEntry(reader, entry) {
  const lh = await reader.range(entry.lho, entry.lho + 30);
  if (lh.readUInt32LE(0) !== 0x04034b50) throw new Error('Bad local header for ' + entry.name);
  const nlen = lh.readUInt16LE(26), elen = lh.readUInt16LE(28);
  const dataStart = entry.lho + 30 + nlen + elen;
  const raw = await reader.range(dataStart, dataStart + entry.csize);
  if (entry.method === 0) return raw;
  if (entry.method === 8) return zlib.inflateRawSync(raw);
  throw new Error('Unsupported method ' + entry.method);
}

async function main() {
  const listOnly = process.argv.includes('--list-only');
  const onlyP = (process.argv.find((a) => a.startsWith('--patient=')) || '').split('=')[1] || null;
  const files = await articleFiles();
  fs.writeFileSync(MANIFEST_DIR + '/figshare_files.json', JSON.stringify(files, null, 1));
  const groups = patientParts(files);
  const fetchLog = [];
  for (const [patient, parts] of Object.entries(groups).sort()) {
    if (onlyP && patient !== onlyP) continue;
    const reader = new SplitReader(parts);
    const tailLen = Math.min(32 * 1024 * 1024, reader.total);
    const tail = await reader.range(reader.total - tailLen, reader.total);
    const eocd = findEocd64(tail, reader.total, reader.total - tailLen);
    const cd = await reader.range(eocd.cdOff, eocd.cdOff + eocd.cdSize);
    const entries = parseCentralDirectory(cd, eocd.count);
    console.log(`${patient}: parts=${parts.length} totalGB=${(reader.total / 1e9).toFixed(1)} entries=${entries.length} cdMB=${(eocd.cdSize / 1e6).toFixed(1)}`);
    if (!DEV.has(patient)) {
      // SEALED: store only hashes/counts, never entry names or content.
      const nameHash = sha(Buffer.from(entries.map((e) => e.name).join('\n')));
      const manifest = { patient, sealed: true, parts: parts.map((p) => ({ part: p.part, size: p.size, md5: p.md5, article_id: p.id })), entry_count: entries.length, cd_sha256: sha(cd), entry_names_sha256: nameHash, total_bytes: reader.total, created: new Date().toISOString() };
      fs.writeFileSync(`${MANIFEST_DIR}/holdout_${patient}_manifest.json`, JSON.stringify(manifest, null, 1));
      console.log(`  SEALED holdout manifest written (names hashed, no content fetched)`);
      continue;
    }
    if (listOnly) {
      fs.writeFileSync(`${MANIFEST_DIR}/dev_${patient}_entries.json`, JSON.stringify(entries.map((e) => ({ name: e.name, usize: e.usize, csize: e.csize })), null, 1));
      console.log(`  listed entries -> dev_${patient}_entries.json`);
      continue;
    }
    const pdir = DEV_DIR + '/' + patient;
    fs.mkdirSync(pdir, { recursive: true });
    const own = entries.filter((e) => deidentify(e.name, patient) !== null);
    const skippedNested = entries.length - own.length;
    const wanted = own.filter((e) => /\/Results\/results_[^/]+\.txt$/i.test(e.name));
    const scripts = own.filter((e) => /(shape_selector_Ac|Cell_tracking_new)\.py$/i.test(e.name));
    const chans = own.filter((e) => /channel_size\.txt$/i.test(e.name));
    const contours = own.filter((e) => /_contours\.txt$/i.test(e.name));
    console.log(`  results=${wanted.length} contours=${contours.length} scripts=${scripts.length} channel=${chans.length} skippedNestedOtherPatient=${skippedNested}`);
    fs.writeFileSync(`${MANIFEST_DIR}/dev_${patient}_entries.json`, JSON.stringify({ results: wanted.map((e) => deidentify(e.name, patient)), total_entries: entries.length, skipped_nested_other_patient: skippedNested }, null, 1));
    let toFetch = [...wanted, ...chans, ...(scripts.length ? [scripts[0]] : []), ...(scripts.length > 1 ? [scripts[1]] : []), ...contours.slice(0, 3)];
    if (process.argv.includes('--samples')) {
      const pickles = own.filter((e) => /\/Offline\/M10_results\.p$/i.test(e.name));
      console.log(`  SAMPLE MODE pickles=${pickles.length}`);
      toFetch = [...pickles];
    }
    for (const e of toFetch) {
      const data = await extractEntry(reader, e);
      const safe = deidentify(e.name, patient).replace(/[\\/]/g, '__');
      fs.writeFileSync(pdir + '/' + safe, data);
      fetchLog.push({ patient, entry: safe, bytes: data.length, sha256: sha(data) });
      console.log(`  extracted ${safe} (${data.length} B)`);
    }
  }
  fs.writeFileSync(MANIFEST_DIR + '/fetch_log.json', JSON.stringify(fetchLog, null, 1));
  console.log('DONE. fetch_log entries:', fetchLog.length);
}
main().catch((e) => { console.error('INGEST FAIL:', e.message); process.exit(1); });
