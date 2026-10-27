// Browser-side collector. Run it in a signed-in tab of fanniemae.mbs-securities.com/fannie or
// freddiemac.mbs-securities.com/freddie (Claude in Chrome javascript_tool): this whole file, then
//   __gseCollect(HAVE, STAMP)
// HAVE is the list of file names already collected (`gsescore have`), STAMP the run date (YYYY-MM-DD).
// It lists the loan-level issuance files the portal has for this year (and last year in January),
// fetches the intraday and month-end ones not in HAVE, checks each against the size the portal sends,
// and saves them as one zip, <issuer>_loan_files_<STAMP>.zip, with a manifest.json that
// `gsescore unpack` verifies. It returns at once; window.__gse.progress reports the stage:
// listing -> fetching -> zipping -> downloaded | nothing-new | failed.
window.__gseCollect = function (have, stamp) {
  const issuer = location.pathname.split('/')[1];
  const agency = { freddie: 'FHLMC', fannie: 'FNMA' }[issuer];
  const P = { stage: 'listing', done: 0, total: 0, mb: 0, errors: [], files: [] };
  window.__gse = { progress: P };
  const fail = (msg) => { P.stage = 'failed'; P.errors.push(msg); return P; };
  if (!agency) return fail('not on a portal page');

  const meta = Object.fromEntries([...document.querySelectorAll('meta[name]')].map((m) => [m.name, m.content]));
  const headers = meta._csrf_header && meta._csrf ? { [meta._csrf_header]: meta._csrf } : {};
  const KEYS = /^(L1_INTRADAY_ISSUANCE_LOAN_LEVEL_[1-4]|L1_MONTHLY_CUMMULATIVE_ISSUANCE_LOAN_LEVEL)$/;
  const haveSet = new Set(have);

  const T = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    T[n] = c >>> 0;
  }
  const crc32 = (u8) => {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < u8.length; i++) c = T[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  };

  async function list() {
    const now = new Date();
    const years = now.getUTCMonth() === 0 ? [now.getUTCFullYear() - 1, now.getUTCFullYear()] : [now.getUTCFullYear()];
    const seen = new Set(), docs = [];
    for (const y of years) {
      const r = await fetch(`/api/report/${issuer}/list/1/${y}`, { credentials: 'include', headers });
      if (r.status === 401 || r.status === 403) throw new Error('signed out');
      if (!r.ok) throw new Error(`list ${y}: HTTP ${r.status}`);
      for (const it of await r.json()) {
        const d = it.document || {};
        if (!KEYS.test(it.headingKey) || !d.id || !d.name || seen.has(d.id) || haveSet.has(d.name)) continue;
        seen.add(d.id);
        docs.push({ report: it.headingKey, id: d.id, name: d.name, effectiveDate: d.effectiveDate });
      }
    }
    return docs.sort((a, b) => a.name.localeCompare(b.name));
  }

  async function get(d) {
    for (let attempt = 1; ; attempt++) {
      try {
        const r = await fetch(`/api/report/download/${d.id}/${d.name}`, { credentials: 'include' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const sent = Number(r.headers.get('content-length'));
        const u8 = new Uint8Array(await r.arrayBuffer());
        if (sent && u8.length !== sent) throw new Error(`got ${u8.length} of ${sent} bytes`);
        return u8;
      } catch (err) {
        if (attempt === 3) throw err;
        await new Promise((res) => setTimeout(res, 1000 * attempt));
      }
    }
  }

  function zip(entries) {
    const enc = new TextEncoder(), parts = [], central = [];
    const date = ((Number(stamp.slice(0, 4)) - 1980) << 9) | (Number(stamp.slice(5, 7)) << 5) | Number(stamp.slice(8, 10));
    let offset = 0;
    for (const [path, u8, crc] of entries) {
      const name = enc.encode(path);
      const lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(12, date, true);
      lh.setUint32(14, crc, true); lh.setUint32(18, u8.length, true); lh.setUint32(22, u8.length, true);
      lh.setUint16(26, name.length, true);
      parts.push(lh.buffer, name, u8);
      const ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true);
      ch.setUint16(14, date, true); ch.setUint32(16, crc, true); ch.setUint32(20, u8.length, true);
      ch.setUint32(24, u8.length, true); ch.setUint16(28, name.length, true); ch.setUint32(42, offset, true);
      central.push(ch.buffer, name);
      offset += 30 + name.length + u8.length;
    }
    const size = central.reduce((s, b) => s + b.byteLength, 0);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true); end.setUint16(10, entries.length, true);
    end.setUint32(12, size, true); end.setUint32(16, offset, true);
    return new Blob([...parts, ...central, end.buffer], { type: 'application/zip' });
  }

  (async () => {
    try {
      const docs = await list();
      P.total = docs.length;
      if (!docs.length) { P.stage = 'nothing-new'; return; }
      P.stage = 'fetching';
      const got = new Array(docs.length);
      let next = 0;
      const worker = async () => {
        while (next < docs.length) {
          const k = next++;
          try {
            got[k] = await get(docs[k]);
            P.mb += got[k].length / 1e6;
          } catch (err) {
            P.errors.push(`${docs[k].name}: ${err.message}`);
          }
          P.done++;
        }
      };
      await Promise.all(Array.from({ length: 6 }, worker));
      P.stage = 'zipping';
      const entries = [], files = [];
      docs.forEach((d, k) => {
        if (!got[k]) return;
        const kind = d.report.startsWith('L1_INTRADAY') ? 'intraday' : 'monthend';
        const crc = crc32(got[k]);
        entries.push([`${agency}/${kind}/${d.name}`, got[k], crc]);
        files.push({ agency, kind, ...d, bytes: got[k].length, crc32: crc });
      });
      if (!files.length) throw new Error('every fetch failed');
      const manifest = new TextEncoder().encode(JSON.stringify({ source: location.origin, collected_at: new Date().toISOString(), files }, null, 1));
      entries.push(['manifest.json', manifest, crc32(manifest)]);
      const blob = zip(entries);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${issuer}_loan_files_${stamp}.zip`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 600000);
      Object.assign(P, { stage: 'downloaded', fileName: a.download, zipMb: +(blob.size / 1e6).toFixed(1), files: files.map((f) => f.name) });
    } catch (err) {
      fail(err.message);
    }
  })();
  return P;
};
