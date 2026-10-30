// The analyst tools: this week's note, each company's read, your scenario and the FICO exposure calculator.
// Runs after the page's main script, which shares what these need on window.vx. Yours to change on the page; nothing here is saved.
(() => {
  const vx = window.vx;
  const { root, rowsOf, statusOf, int, pct1, money, usdM, olName, openSeller, monthShort } = vx;
  const pct0 = d3.format('.0%');
  const one = d3.format('.1f');
  const signed = d3.format('+.1f');
  const num = (v) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100));
  const orDash = (fmt) => (v) => (v == null ? '—' : fmt(v));
  const node = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const link = (text, url) => {
    const a = node('a', 'vx-link', text);
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    return a;
  };
  const day = (s) => d3.utcFormat('%b %-d, %Y')(new Date(s));

  // ---- This week ----
  let noteWeek = null;
  function drawNote() {
    const sel = document.getElementById('note-week');
    if (!sel) return;
    const rows = rowsOf('week_note');
    const weeks = rows.filter((r) => r.view === 'week').sort((a, b) => (a.week < b.week ? 1 : -1));
    const list = document.getElementById('note-list');
    list.classList.toggle('dash-skeleton', dash.data('week_note').status === 'loading');
    if (!weeks.length) return list.replaceChildren();
    if (!weeks.some((w) => w.week === noteWeek)) noteWeek = (weeks.find((w) => w.latest) || weeks[0]).week;
    sel.replaceChildren(...weeks.map((w) => new Option(`${w.label}${w.partial ? ', so far' : ''}`, w.week)));
    sel.value = noteWeek;
    list.replaceChildren(...rows.filter((r) => r.view === 'line' && r.week === noteWeek).sort((a, b) => a.order - b.order).map((r) => {
      const li = node('li', null, r.text);
      if (r.url) li.append(' ', link(r.source || 'Source', r.url));
      return li;
    }));
  }

  // ---- A company's read ----
  const RULES = { whenever: 'Uses VS4 whenever its score is higher', moving: 'A 20-point rule, moving below the line', line: 'A 20-point rule',
    some: 'Some loans at 20 or more points higher', rare: 'Rarely, even at 20 or more points higher' };

  function lenderOf(e) {
    const rows = rowsOf('lender_stage').filter((r) => r.view === 'lender');
    return rows.find((r) => r.id === e.id) || (e.ticker ? rows.filter((r) => r.ticker === e.ticker).sort((a, b) => b.share - a.share)[0] : null) || null;
  }

  function drawChips(e) {
    const box = document.getElementById('co-chips');
    const seen = new Map();
    for (const s of rowsOf('sellers').filter((r) => r.ticker && r.level === 'seller').sort((a, b) => b.mkt_share_recent - a.mkt_share_recent)) {
      if (!seen.has(s.ticker)) seen.set(s.ticker, s);
    }
    box.replaceChildren(...[...seen.values()].map((s) => {
      const b = node('button', 'vx-chip', s.ticker);
      b.type = 'button';
      b.dataset.seller = s.id;
      b.title = s.short;
      b.setAttribute('aria-pressed', String(!!e && e.ticker === s.ticker));
      return b;
    }));
  }

  function fillTable(table, rows) {
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const cells of rows) {
      const tr = body.insertRow();
      cells.forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
    }
  }

  function asks(l, fee, better, same, banks) {
    const out = [];
    const month = fee && fee.month ? monthShort(fee.month) : 'this month';
    if (l.stage === 'fico' || l.stage === 'trace') {
      out.push(`${pct1(l.mix_fico_only)} of its loans show only a Classic FICO. Is VantageScore in its systems, and what would make it switch?`);
      if (fee && fee.option_bp != null) out.push(`The lower fee could be worth about ${one(fee.option_bp)} bp of its balance on the grid. Who would keep it, the borrower or the lender?`);
    }
    if (l.stage === 'both') {
      out.push(`It shows both scores on ${pct1(l.both_share)} of its loans but prices on VS4 on ${pct1(l.vs4_share)}. What holds it back: investors, mortgage insurers, buyback risk?`);
      if (fee && fee.left_usd >= 1e5) out.push(`It left about ${usdM(fee.left_usd)} of fees on ${month} loans with both scores. Is that a choice or a systems gap?`);
    }
    if (l.stage === 'pricing' || l.stage === 'some') {
      if (l.rule === 'line' && l.above != null && l.below_late != null) out.push(`It keeps to about a 20-point rule (${pct0(l.below_late)} under the line, ${pct0(l.above)} above it). With one fee grid since Oct 1, why?`);
      if (l.rule === 'moving' && l.below_early != null) out.push(`Its rule is moving: ${pct0(l.below_early)} to ${pct0(l.below_late)} with VS4 under 20 points higher. Where does it stop?`);
      if (l.rule === 'whenever' && l.below_late != null) out.push(`It uses VS4 on ${pct0(l.below_late)} of loans under 20 points higher, where the fee often does not change. What does it gain?`);
      if (better && better.n >= 100 && better.reaches != null) out.push(`About ${pct0(better.reaches)} of a better fee tier reaches the rate. Where does the rest go: margin, points or credits?`);
      if (same && same.n >= 100 && same.net_bp >= 3) out.push(`Its VS4 loans with no fee benefit carry ${signed(same.net_bp)} bp against the model. Is that mix, or investors charging for VS4?`);
    }
    if (l.fhlmc_vs_only != null && l.fnma_vs_only != null && l.fhlmc_vs_only - l.fnma_vs_only >= 0.05) {
      out.push(`Freddie Mac's files show VS4 alone on ${pct1(l.fhlmc_vs_only)} of its loans, Fannie Mae's on ${pct1(l.fnma_vs_only)}. Does it deliver both scores to both GSEs?`);
    }
    if (l.kind === 'Bank' && banks && !banks.using) out.push('No bank prices on VS4 regularly so far. What would it take, and who moves first?');
    return out.slice(0, 4);
  }

  function drawCompany(p) {
    const card = document.getElementById('co-read');
    if (!card) return;
    const e = vx.entityOf(p);
    drawChips(e);
    const l = e ? lenderOf(e) : null;
    const line = document.getElementById('co-line');
    const body = document.getElementById('co-body');
    card.classList.toggle('dash-skeleton', statusOf('lender_stage', 'fees', 'pricing') === 'loading');
    body.hidden = !l;
    if (!l) {
      line.textContent = e ? `${e.short} is not among the lenders tracked in detail: the 60 largest and every other lender using VS4 with 100 or more loans.` : '';
      return;
    }
    const stages = rowsOf('lender_stage');
    const stage = stages.find((r) => r.view === 'stage' && r.key === l.stage);
    const banks = stages.find((r) => r.view === 'kind' && r.key === 'Bank');
    const fee = rowsOf('fees').find((r) => r.view === 'lender' && r.id === l.id);
    const pricing = rowsOf('pricing');
    const rate = pricing.find((r) => r.view === 'seller' && r.cover === 'all' && r.basis === 'headline' && r.key === l.id);
    const better = pricing.find((r) => r.view === 'value' && r.scope === l.id && r.key === 'better');
    const same = pricing.find((r) => r.view === 'value' && r.scope === l.id && r.key === 'same');
    const name = olName(l);
    line.textContent = `${name}: ${pct1(l.share)} of GSE loans disclosed with every score, number ${int(l.rank)} by loans. ${l.kind}, ${l.lead === 'Mixed' ? 'no main channel' : `${l.lead.toLowerCase()}-led`}. ${stage ? `${stage.label}.` : ''}`;

    const market = rowsOf('score_mix').find((r) => r.view === 'month' && r.agency === 'All' && r.headline);
    const mixRow = (label, f, n) => [[label, 'vx-l'], [orDash(pct1)(f('fico_only'))], [orDash(pct1)(f('both_fico'))], [orDash(pct1)(f('both_vs'))], [orDash(pct1)(f('vs_only'))], [n == null ? '—' : int(n), 'vx-opt']];
    const mixRows = [mixRow('Both GSEs', (k) => l[`mix_${k}`], l.loans), mixRow('Fannie Mae', (k) => l[`fnma_${k}`], l.fnma_loans), mixRow('Freddie Mac', (k) => l[`fhlmc_${k}`], l.fhlmc_loans)];
    if (market) mixRows.push(mixRow('All lenders', (k) => market[`${k}_share`], market.loans));
    fillTable(document.getElementById('co-mix'), mixRows);

    const facts = [];
    const add = (label, text) => { if (text != null) facts.push([[label, 'vx-l'], [text, 'vx-l']]); };
    add('Priced on VS4', `${pct1(l.vs4_share)}${l.recent_share == null ? '' : `; ${pct1(l.recent_share)} in the latest weeks`}`);
    add('Rule', l.rule ? RULES[l.rule] : null);
    add('Prices on VS4 when its score is higher', l.uses_higher == null ? null : `${pct1(l.uses_higher)} of ${int(l.higher_loans)} loans`);
    add('Under 20 points higher, earlier to latest weeks', l.below_early == null || l.below_late == null ? null : `${pct0(l.below_early)} to ${pct0(l.below_late)}`);
    add('20 or more points higher', l.above == null ? null : pct0(l.above));
    add(`Both scores${l.both_at === 'FNMA' ? ' at Fannie Mae' : ''}, earlier to latest weeks`, l.both_early == null || l.both_late == null ? null : `${pct0(l.both_early)} to ${pct0(l.both_late)}`);
    if (fee) {
      add('Fee saved on a VS4 loan that saves one', fee.saving_avg_usd == null || fee.priced_loans < 20 ? null : `${money(fee.saving_avg_usd)}, on ${pct0(fee.saving_share)} of its VS4 loans with both scores`);
      add(`Fees on ${monthShort(fee.month)} loans: taken, left, estimated`, `${usdM(fee.taken_usd)}, ${usdM(fee.left_usd)}, ${usdM(fee.est_usd)}`);
      add('Potential, all three', fee.option_bp == null ? null : `${one(fee.option_bp)} bp of its balance`);
    }
    add('VS4 rate against the FICO model', rate ? `${signed(rate.net_bp)} bp on ${int(rate.n)} loans` : null);
    add('A better fee tier reaching the rate', better && better.n >= 100 && better.reaches != null ? `${pct0(better.reaches)} (${signed(better.net_bp)} bp against ${one(better.worth_bp)} bp of worth)` : null);
    add('No fee benefit, rate against the model', same && same.n >= 100 ? `${signed(same.net_bp)} bp on ${int(same.n)} loans` : null);
    fillTable(document.getElementById('co-facts'), facts);

    const list = (id, items) => document.getElementById(id).replaceChildren(...items);
    const q = asks(l, fee, better, same, banks);
    list('co-ask', q.length ? q.map((t) => node('li', null, t)) : [node('li', null, 'Nothing stands out yet.')]);
    const said = rowsOf('statements').filter((r) => r.seller_id === l.id).sort((a, b) => (a.date < b.date ? 1 : -1));
    list('co-said', said.length ? said.map((r) => {
      const li = node('li', null, `${day(r.date)}: ${r.statement} `);
      if (r.url) li.append(link(r.source || 'Source', r.url));
      return li;
    }) : [node('li', null, 'Nothing logged yet.')]);
  }

  // ---- Your scenario ----
  const scn = { rows: null, v: 'today', nf: 'today', mine: new Map() };
  const heavy = (r) => r.status === 'heavy';
  const today = () => (rowsOf('outlook').find((r) => r.view === 'ladder' && r.key === 'today') || {}).value;

  function assumption(key) {
    const row = rowsOf('assumptions').find((r) => r.key === key);
    return row ? Number(row.value) : null;
  }

  function scnRows() {
    if (scn.rows) return scn.rows;
    const lenders = rowsOf('outlook').filter((r) => r.view === 'lender').sort((a, b) => (a.status === 'other') - (b.status === 'other') || b.share - a.share);
    if (!lenders.length || dash.data('lender_stage').status !== 'ok' || dash.data('assumptions').status !== 'ok') return [];
    const stage = new Map(rowsOf('lender_stage').filter((r) => r.view === 'lender').map((r) => [r.id, r]));
    const rows = lenders.map((r) => {
      const s = stage.get(r.id);
      return { ...r, nf0: s ? (s.fnma_vs_only != null ? s.fnma_vs_only : s.mix_vs_only) || 0 : 0 };
    });
    // Everyone else takes what is left of the market's share with no Classic FICO, read at Fannie Mae.
    const rest = rows.find((r) => r.status === 'other');
    if (rest && rest.share > 0) {
      const known = d3.sum(rows.filter((r) => r !== rest), (r) => r.share * r.nf0);
      rest.nf0 = Math.max(0, ((assumption('no_fico_fnma') || 0) - known) / rest.share);
    }
    scn.rows = rows;
    return rows;
  }

  function preset(r, v) {
    const pick = { today: r.vs4_share, recent: r.recent_share, higher: r.on_higher, better: r.on_better }[v];
    return pick == null ? r.vs4_share : pick;
  }
  const valueOf = (r) => {
    const m = scn.mine.get(r.id) || {};
    return m.v != null ? m.v : preset(r, scn.v);
  };
  const noFicoOf = (r) => {
    const m = scn.mine.get(r.id) || {};
    if (m.nf != null) return m.nf;
    return scn.nf === 'all' || (scn.nf === 'heavy' && heavy(r)) ? Math.max(r.nf0, valueOf(r)) : r.nf0;
  };
  const scnTotals = () => {
    const rows = scnRows();
    return { v: d3.sum(rows, (r) => r.share * valueOf(r)), nf: d3.sum(rows, (r) => r.share * noFicoOf(r)) };
  };

  function drawScenarioTable() {
    const table = document.getElementById('scn-table');
    if (!table) return;
    const rows = scnRows();
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', !rows.length && statusOf('outlook', 'lender_stage', 'assumptions') === 'loading');
    const body = table.tBodies[0];
    body.replaceChildren();
    const box = (r, field, value) => {
      const i = node('input', 'vx-in');
      i.type = 'number';
      i.min = '0';
      i.max = '100';
      i.step = '1';
      i.value = num(Math.round(value * 1000) / 10);
      i.dataset.id = r.id;
      i.dataset.field = field;
      i.setAttribute('aria-label', `${field === 'v' ? 'VS4-priced share' : 'Share with no Classic FICO'}, ${r.short || 'everyone else'}`);
      return i;
    };
    for (const r of rows) {
      const tr = body.insertRow();
      tr.dataset.key = ['lender', r.id].map(encodeURIComponent).join(',');
      const cells = [[r.status === 'other' ? 'Everyone else' : olName(r), 'vx-l vx-name'], [pct1(r.share)], [pct1(r.vs4_share), 'vx-opt']];
      cells.forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
      tr.insertCell().append(box(r, 'v', valueOf(r)));
      const nf = tr.insertCell();
      nf.className = 'vx-opt';
      nf.textContent = pct1(r.nf0);
      tr.insertCell().append(box(r, 'nf', noFicoOf(r)));
    }
    drawSegs();
  }

  function drawSegs() {
    for (const [id, cur] of [['scn-v', scn.v], ['scn-nf', scn.nf]]) {
      const seg = document.getElementById(id);
      if (seg) seg.querySelectorAll('button[data-v]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === cur)));
    }
  }

  // ---- FICO exposure ----
  const EXPO = [
    { group: 'The market', keys: ['gse_loans_year', 'borrowers_per_loan', 'bureaus', 'pulls_per_loan'] },
    { group: "FICO's price", keys: ['price_per_score', 'closing_fee', 'vs_price'] },
    { group: "FICO's reported revenue", keys: ['fico_mortgage_q', 'fico_revenue_year'] },
  ];
  const expo = { mine: new Map(), built: false };
  const input = (key) => (expo.mine.has(key) ? expo.mine.get(key) : assumption(key));
  const step = (row) => (row.unit === 'count' && row.value > 1000 ? 10000 : row.unit === 'usd_m' ? 10 : row.unit === 'usd' ? 0.5 : 1);

  function buildExpo() {
    const box = document.getElementById('expo-inputs');
    if (!box || expo.built || dash.data('assumptions').status !== 'ok') return;
    expo.built = true;
    const rows = new Map(rowsOf('assumptions').map((r) => [r.key, r]));
    const field = (key, label, note, value, row) => {
      const wrap = node('label', 'expo-row');
      wrap.append(node('span', 'expo-label', label));
      const i = node('input', 'vx-in');
      i.type = 'number';
      i.min = '0';
      i.step = row ? String(step(row)) : '0.5';
      i.value = value == null ? '' : num(value >= 1000 ? Math.round(value) : value);
      i.dataset.expo = key;
      wrap.append(i);
      const n = node('span', 'expo-note', note ? `${note} ` : '');
      if (row && row.url) n.append(link(row.source || 'Source', row.url));
      wrap.append(n);
      return wrap;
    };
    const groups = EXPO.map((g) => {
      const div = node('div');
      div.append(node('h3', null, g.group));
      for (const key of g.keys) {
        const r = rows.get(key);
        if (r) div.append(field(key, r.label, r.note, r.value, r));
      }
      return div;
    });
    const mine = node('div');
    mine.append(node('h3', null, 'Your scenario, beyond the table'));
    mine.append(field('scn_pulls', 'FICO pulls per funded loan', 'A lender can keep FICO for the loan it delivers and pull VantageScore earlier. These files cannot show that.', input('pulls_per_loan'), rows.get('pulls_per_loan') && { ...rows.get('pulls_per_loan'), url: null }));
    mine.append(field('scn_price', 'FICO price per score', 'Price can outrun lost units, as FICO\'s latest quarter shows.', input('price_per_score'), rows.get('price_per_score') && { ...rows.get('price_per_score'), url: null }));
    box.replaceChildren(...groups, mine);
  }

  function drawExpo() {
    const out = document.getElementById('expo-out');
    if (!out) return;
    buildExpo();
    const t = scnRows().length ? scnTotals() : null;
    const put = (id, text) => {
      const e = document.getElementById(id);
      if (e) {
        e.textContent = text == null ? '—' : text;
        e.classList.toggle('dash-skeleton', text == null && dash.data('assumptions').status === 'loading');
      }
    };
    const loans = input('gse_loans_year'), borrowers = input('borrowers_per_loan'), bureaus = input('bureaus'), pulls = input('pulls_per_loan');
    const price = input('price_per_score'), fee = input('closing_fee'), vs = input('vs_price'), q = input('fico_mortgage_q'), company = input('fico_revenue_year');
    const nf0 = assumption('no_fico_fnma');
    const v0 = today();
    put('scn-v-val', t ? pct1(t.v) : null);
    put('scn-v-sub', t && v0 != null ? `${pct1(v0)} today, ${signed((t.v - v0) * 100)} pts` : null);
    put('scn-nf-val', t ? pct1(t.nf) : null);
    put('scn-nf-sub', t && nf0 != null ? `${pct1(nf0)} today at Fannie Mae, ${signed((t.nf - nf0) * 100)} pts` : null);
    const ready = t && [loans, borrowers, bureaus, pulls, price, fee, q, company, nf0].every((x) => x != null);
    if (!ready) {
      ['expo-today', 'expo-today-sub', 'expo-scn', 'expo-scn-sub', 'expo-share', 'expo-share-sub', 'expo-point', 'expo-offset', 'expo-offset-sub', 'expo-lender', 'expo-lender-sub', 'scn-rev-val', 'scn-rev-sub'].forEach((id) => put(id, null));
      return;
    }
    const scnPulls = expo.mine.has('scn_pulls') ? expo.mine.get('scn_pulls') : pulls;
    const scnPrice = expo.mine.has('scn_price') ? expo.mine.get('scn_price') : price;
    const scores = bureaus * borrowers;
    const perLoan = (n, at) => scores * (n * at + fee);
    const revToday = loans * (1 - nf0) * perLoan(pulls, price);
    const revScn = loans * (1 - t.nf) * perLoan(scnPulls, scnPrice);
    const change = revScn - revToday;
    const yearly = q * 4 * 1e6;
    put('expo-today', usdM(revToday));
    put('expo-today-sub', `${money(perLoan(pulls, price))} a funded loan`);
    put('expo-scn', usdM(revScn));
    put('expo-scn-sub', `${change >= 0 ? '+' : '−'}${usdM(Math.abs(change))} from today`);
    put('expo-share', pct1(change / (company * 1e6)));
    put('expo-share-sub', `${pct1(change / yearly)} of mortgage revenue at the latest quarter's pace`);
    put('expo-point', usdM(loans * 0.01 * perLoan(pulls, price)));
    const offset = revScn > 0 ? revToday / revScn - 1 : null;
    put('expo-offset', offset == null ? null : offset > 0 ? pct1(offset) : 'None');
    put('expo-offset-sub', `on ${d3.format('$.2f')(scnPrice)} a score`);
    put('expo-lender', money(scores * (pulls * (price - (vs || 0)) + fee)));
    put('expo-lender-sub', `at ${d3.format('$.2f')(price)} a FICO score against ${d3.format('$.2f')(vs || 0)} for VantageScore`);
    put('scn-rev-val', usdM(revScn));
    put('scn-rev-sub', `${change >= 0 ? '+' : '−'}${usdM(Math.abs(change))} from today`);
    put('expo-check', `Check: at these inputs GSE loans are ${pct0(revToday / yearly)} of FICO's mortgage origination revenue at the latest quarter's pace (${usdM(yearly)} a year). GSE loans are only part of mortgage lending, so this should sit well under 100%.`);
  }

  function drawOutlookTools() {
    if (!document.getElementById('scn-card')) return;
    const table = document.getElementById('scn-table');
    if (!table.tBodies[0].rows.length) drawScenarioTable();
    drawExpo();
  }

  root.addEventListener('input', (event) => {
    const t = event.target;
    if (t.dataset.field && t.closest('#scn-table')) {
      const v = Number(t.value);
      if (t.value === '' || !Number.isFinite(v)) return;
      const m = scn.mine.get(t.dataset.id) || {};
      m[t.dataset.field] = Math.min(100, Math.max(0, v)) / 100;
      scn.mine.set(t.dataset.id, m);
      drawExpo();
    } else if (t.dataset.expo) {
      const v = Number(t.value);
      if (t.value === '' || !Number.isFinite(v) || v < 0) return;
      expo.mine.set(t.dataset.expo, v);
      drawExpo();
    }
  });
  root.addEventListener('change', (event) => {
    if (event.target.id === 'note-week') {
      noteWeek = event.target.value;
      drawNote();
    }
  });
  root.addEventListener('click', (event) => {
    const chip = event.target.closest('.vx-chip[data-seller]');
    if (chip) return openSeller(chip.dataset.seller);
    const seg = event.target.closest('#scn-v button[data-v], #scn-nf button[data-v]');
    if (seg) {
      const which = seg.closest('.vx-seg').id === 'scn-v' ? 'v' : 'nf';
      scn[which] = seg.dataset.v;
      for (const m of scn.mine.values()) delete m[which];  // a preset replaces what was typed in its column
      drawScenarioTable();
      return drawExpo();
    }
    if (event.target.id === 'expo-reset') {
      expo.mine.clear();
      expo.built = false;
      drawExpo();
    }
  });

  vx.hooks.overview.push(drawNote);
  vx.hooks.lenders.push(drawCompany);
  vx.hooks.outlook.push(drawOutlookTools);
  vx.redraw();
})();
