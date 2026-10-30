// The analyst tools: this week's note, loans carrying VS4 over time, each company's read, every lender's split, cost or rate, your scenario and the FICO exposure calculator.
// Runs after the page's main script, which shares what these need on window.vx. Yours to change on the page; nothing here is saved.
(() => {
  const vx = window.vx;
  const { root, rowsOf, statusOf, int, pct1, money, usdM, olName, openSeller, monthShort, monthYear, monthLabel, shortDay, reachText, prep, svgFor, bandFrame, yAxis, bandAxis, bandHover, legend, MIX_GROUPS, ADOPT_FROM } = vx;
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

  // ---- Loans carrying VS4 over time ----
  // Bottom to top: the two groups priced on VS4, which line up with the earlier bars, then the loans that carry VS4 but priced on FICO.
  const CELL_MIN = 20;
  const group = (k) => MIX_GROUPS.find((g) => g[0] === k);
  const carrying = () => [group('both_vs'), group('vs_only'), group('both_fico')];
  const earlier = () => `color-mix(in srgb, ${group('both_vs')[2]} 45%, transparent)`;

  function drawCarry(box, legendBox, st, periods, lab, title) {
    const groups = carrying();
    const hasPre = periods.some((r) => r.pre != null), hasSteady = periods.some((r) => r.steady != null);
    legend(legendBox, [...(hasPre ? [[earlier(), 'Priced on VS4, other scores not shown yet', 'box']] : []), ...groups.map(([, l, c]) => [c, l, 'box']),
      ...(hasSteady ? [['var(--color-fg)', 'Carrying VS4, every lender at its usual share', 'line']] : [])]);
    if (!prep(box, st) || !periods.length) return;
    const W = box.clientWidth, H = 230, m = { top: hasPre ? 22 : 10, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, title);
    const total = (r) => (r.pre != null ? r.pre : d3.sum(groups, ([g]) => r[g] || 0));
    const y = d3.scaleLinear([0, Math.max(d3.max(periods, total) || 0.01, d3.max(periods, (r) => r.steady || 0) || 0) * 1.08], [H - m.bottom, m.top]).nice(4);
    const yf = d3.format('.0%');
    const keys = periods.map((r) => r.key);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 4, W, m);
    yAxis(svg, y, yf, m.left, W - m.right, 4);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const bw = Math.min(34, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    for (const r of periods) {
      if (r.pre != null) {
        svg.append('rect').attr('x', x(r.key) + off).attr('width', bw).attr('y', y(r.pre)).attr('height', Math.max(0, y(0) - y(r.pre))).attr('fill', earlier());
        continue;
      }
      let base = 0;
      for (const [g, , color] of groups) {
        const v = r[g] || 0;
        svg.append('rect').attr('x', x(r.key) + off).attr('width', bw).attr('y', y(base + v)).attr('height', Math.max(0, y(base) - y(base + v))).attr('fill', color);
        base += v;
      }
    }
    const firstSplit = periods.findIndex((r) => r.pre == null);
    if (hasPre && firstSplit > 0) {
      const at = x(periods[firstSplit].key) - (x.step() - x.bandwidth()) / 2;
      svg.append('line').attr('x1', at).attr('x2', at).attr('y1', 6).attr('y2', H - m.bottom).attr('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '3 3');
      const label = svg.append('text').attr('y', 12).text('Every score from here');
      const roomy = at - m.left > label.node().getComputedTextLength() + 8;
      label.attr('x', roomy ? at - 4 : at + 4).attr('text-anchor', roomy ? 'end' : 'start');
    }
    const line = periods.filter((r) => r.steady != null);
    if (line.length) {
      const cx = (r) => x(r.key) + x.bandwidth() / 2;
      svg.append('path').attr('d', d3.line().x(cx).y((r) => y(r.steady))(line)).attr('fill', 'none').attr('stroke', 'var(--color-fg)').attr('stroke-width', 1.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
      svg.append('g').selectAll('circle').data(line).join('circle').attr('cx', cx).attr('cy', (r) => y(r.steady)).attr('r', 2.5).attr('fill', 'var(--color-fg)');
    }
    bandHover(svg, box, x, periods, 'key', m, H, (r) => [r.title, r.pre != null ? [[earlier(), 'Priced on VS4', pct1(r.pre)]]
      : [...groups.map(([g, l, c]) => [c, l, pct1(r[g] || 0)]), [null, 'Carrying VS4', pct1(total(r))], ...(r.steady != null ? [['var(--color-fg)', 'At its usual lender mix', pct1(r.steady)]] : [])]]);
  }

  function drawCarryOverview(p) {
    const box = document.getElementById('score-mix-chart');
    if (!box) return;
    const k = p.measure === 'upb' ? '_upb' : '';
    const mix = rowsOf('score_mix');
    const st = statusOf('score_mix', 'weekly', 'monthly');
    const split = (r) => ({ both_vs: r[`both_vs${k}_share`] || 0, vs_only: r[`vs_only${k}_share`] || 0, both_fico: r[`both_fico${k}_share`] || 0 });
    const asc = (f) => (a, b) => (a[f] < b[f] ? -1 : 1);
    if (p.cperiod === 'month') {
      const head = mix.find((r) => r.view === 'month' && r.agency === 'All' && r.headline);
      const months = mix.filter((r) => r.view === 'month' && r.agency === p.agency && head && r.start <= head.start).sort(asc('start'));
      const first = months.length ? months[0].start : null;
      const finals = new Map(rowsOf('monthly').filter((r) => r.agency === p.agency).map((r) => [r.month, r.final]));
      const pre = rowsOf('monthly').filter((r) => r.agency === p.agency && r.month >= ADOPT_FROM && (!first || r.month < first)).sort(asc('month'))
        .map((r) => ({ key: r.month, pre: r[`vs4${k}_share`], title: `${monthYear(r.month)}, ${int(r.scored_loans)} loans` }));
      const post = months.map((r) => ({ key: r.start, ...split(r), title: `${monthYear(r.start)}${finals.get(r.start) === false ? ' so far' : ''}, ${int(r.loans)} loans` }));
      const periods = [...pre, ...post];
      return drawCarry(box, document.getElementById('score-mix-legend'), st, periods, monthLabel(periods.map((r) => r.key)), 'Share of loans carrying VS4 by issue month');
    }
    const weeks = mix.filter((r) => r.view === 'week' && r.agency === p.agency).sort(asc('start'));
    const first = weeks.length ? weeks[0].start : null;
    const pre = rowsOf('weekly').filter((r) => r.agency === p.agency && (!first || r.week < first)).sort(asc('week'))
      .map((r) => ({ key: r.week, pre: r[`vs4${k}_share`], title: `Week of ${shortDay(r.week)}, ${int(r.scored_loans)} loans` }));
    const post = weeks.map((r) => ({ key: r.start, ...split(r), steady: k ? null : r.steady_carrying, title: `Week of ${shortDay(r.start)}, ${int(r.loans)} loans` }));
    drawCarry(box, document.getElementById('score-mix-legend'), st, [...pre, ...post], shortDay, 'Share of loans carrying VS4 by week first disclosed');
  }

  function drawCarryLender(e, l, p) {
    const box = document.getElementById('co-carry-chart');
    if (!box) return;
    const st = statusOf('lender_mix', 'score_mix');
    const asc = (f) => (a, b) => (a[f] < b[f] ? -1 : 1);
    const split = (r) => ({ both_vs: r.bv / r.n, vs_only: r.vo / r.n, both_fico: r.bf / r.n });
    const mine = rowsOf('lender_mix').filter((r) => r.id === l.id && r.agency === p.agency && r.n >= CELL_MIN);
    const mix = rowsOf('score_mix');
    const note = document.getElementById('co-carry-note');
    if (p.cperiod === 'month') {
      const head = mix.find((r) => r.view === 'month' && r.agency === 'All' && r.headline);
      const months = mix.filter((r) => r.view === 'month' && r.agency === 'All' && head && r.start <= head.start).map((r) => r.start).sort();
      const pre = rowsOf('seller_monthly').filter((r) => r.id === l.id && r.level === 'seller' && r.agency === p.agency && r.month >= ADOPT_FROM && (!months.length || r.month < months[0]) && r.scored >= CELL_MIN).sort(asc('month'))
        .map((r) => ({ key: r.month, pre: r.vs4_share, title: `${monthYear(r.month)}, ${int(r.scored)} loans` }));
      const post = mine.filter((r) => r.view === 'month' && months.includes(r.start)).sort(asc('start')).map((r) => ({ key: r.start, ...split(r), title: `${monthYear(r.start)}, ${int(r.n)} loans` }));
      const periods = [...pre, ...post];
      note.textContent = 'Share of loans. Months with 20 or more loans. Lighter bars are a floor: until late September the files show only the score that priced a loan.';
      return drawCarry(box, document.getElementById('co-carry-legend'), st, periods, monthLabel(periods.map((r) => r.key)), `Share of ${l.short}'s loans carrying VS4 by issue month`);
    }
    const weeks = mine.filter((r) => r.view === 'week').sort(asc('start'));
    const firstWeek = mix.filter((r) => r.view === 'week').map((r) => r.start).sort()[0];
    const pre = p.agency === 'All' ? rowsOf('seller_weekly').filter((r) => r.id === l.id && r.level === 'seller' && r.scored >= CELL_MIN && (!firstWeek || r.week < firstWeek)).sort(asc('week'))
      .map((r) => ({ key: r.week, pre: r.vs4_share, title: `Week of ${shortDay(r.week)}, ${int(r.scored)} loans` })) : [];
    note.textContent = `Share of loans. Weeks with 20 or more loans.${pre.length ? ' Lighter bars are a floor: until late September the files show only the score that priced a loan.' : p.agency === 'All' ? ' Earlier weeks are kept for lenders with 50 or more VS4 loans.' : ' Earlier weeks are kept across both GSEs; the issue-month view goes back by GSE.'}`;
    drawCarry(box, document.getElementById('co-carry-legend'), st, [...pre, ...weeks.map((r) => ({ key: r.start, ...split(r), title: `Week of ${shortDay(r.start)}, ${int(r.n)} loans` }))], shortDay, `Share of ${l.short}'s loans carrying VS4 by week first disclosed`);
  }

  // ---- Every large lender's split ----
  function drawLenderSplit(p) {
    const table = document.getElementById('lm-table');
    if (!table) return;
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', statusOf('lender_stage', 'lender_mix', 'score_mix') === 'loading');
    const parts = MIX_GROUPS.map(([k, label, color]) => ({ k, label, color }));
    legend(document.getElementById('lm-legend'), parts.map((g) => [g.color, g.label, 'box']));
    const pre = { All: 'mix', FNMA: 'fnma', FHLMC: 'fhlmc' }[p.agency];
    const nf = { All: 'loans', FNMA: 'fnma_loans', FHLMC: 'fhlmc_loans' }[p.agency];
    const weekRows = rowsOf('lender_mix').filter((r) => r.view === 'week' && r.agency === p.agency);
    const weeks = [...new Set(weekRows.map((r) => r.start))].sort();
    const late = new Set(weeks.slice(-2));
    const byId = d3.group(weekRows, (r) => r.id);
    const rate = (rows) => {
      const n = d3.sum(rows, (r) => r.n);
      return n >= CELL_MIN ? d3.sum(rows, (r) => r.bf + r.bv + r.vo) / n : null;
    };
    const market = rowsOf('score_mix').find((r) => r.view === 'all' && r.agency === p.agency);
    const total = market ? market.loans : null;
    const items = rowsOf('lender_stage').filter((r) => r.view === 'lender' && r[`${pre}_fico_only`] != null).map((l) => {
      const mine = byId.get(l.id) || [];
      const early = rate(mine.filter((r) => !late.has(r.start))), latest = rate(mine.filter((r) => late.has(r.start)));
      return { id: l.id, name: olName(l), share: total ? l[nf] / total : null, fico_only: l[`${pre}_fico_only`], both_fico: l[`${pre}_both_fico`], both_vs: l[`${pre}_both_vs`], vs_only: l[`${pre}_vs_only`], early, latest };
    });
    const carried = (r) => r.both_fico + r.both_vs + r.vs_only;
    const rise = (r) => (r.early == null || r.latest == null ? -Infinity : r.latest - r.early);
    items.sort(p.lsort === 'carrying' ? (a, b) => carried(b) - carried(a) || b.share - a.share : p.lsort === 'rising' ? (a, b) => rise(b) - rise(a) || b.share - a.share : (a, b) => b.share - a.share);
    const body = table.tBodies[0];
    body.replaceChildren();
    const orDash1 = orDash(pct1);
    const orDash0 = orDash(pct0);
    const addRow = (r, cls) => {
      const tr = body.insertRow();
      if (cls) tr.className = cls;
      if (r.id) {
        tr.dataset.key = r.id;
        tr.tabIndex = 0;
      }
      const name = tr.insertCell();
      name.className = 'vx-l vx-name';
      name.textContent = r.name;
      const share = tr.insertCell();
      share.className = 'vx-opt';
      share.textContent = orDash1(r.share);
      const bar = node('div', 'lm-bar');
      for (const g of parts) {
        const seg = node('span');
        seg.style.width = `${(r[g.k] || 0) * 100}%`;
        seg.style.background = g.color;
        bar.append(seg);
      }
      const barCell = tr.insertCell();
      barCell.className = 'vx-l';
      barCell.append(bar);
      for (const g of parts) {
        const td = tr.insertCell();
        td.className = 'vx-opt';
        td.textContent = orDash1(r[g.k]);
      }
      const first = tr.insertCell();
      first.className = 'vx-opt';
      first.textContent = orDash0(r.early);
      tr.insertCell().textContent = orDash0(r.latest);
    };
    if (market) {
      const mw = rowsOf('score_mix').filter((r) => r.view === 'week' && r.agency === p.agency);
      const wrate = (rows) => {
        const n = d3.sum(rows, (r) => r.loans);
        return n ? d3.sum(rows, (r) => r.vs_share * r.loans) / n : null;
      };
      addRow({ name: 'All lenders', share: 1, fico_only: market.fico_only_share, both_fico: market.both_fico_share, both_vs: market.both_vs_share, vs_only: market.vs_only_share,
        early: wrate(mw.filter((r) => !late.has(r.start))), latest: wrate(mw.filter((r) => late.has(r.start))) }, 'lm-all');
    }
    items.forEach((r) => addRow(r));
  }

  // ---- Cost or rate ----
  const COST_ROWS = [['lower|up20', "VS4's fee lower, its score 20+ points higher"], ['lower|up1', "VS4's fee lower, its score 1-19 points higher"], ['same|up20', 'Same fee, VS4 20+ points higher'], ['same|up1', 'Same fee, VS4 1-19 points higher'],
    ['same|equal', 'Same fee, same score'], ['same|down1', 'Same fee, VS4 1-19 points lower'], ['same|down20', 'Same fee, VS4 20+ points lower'], ['higher|all', "VS4's fee higher"]];

  function drawCost(p) {
    const table = document.getElementById('cost-table');
    if (!table) return;
    const st = dash.data('fees').status;
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const rows = rowsOf('fees').filter((r) => r.view === 'choice' && r.cohort === p.ccohort);
    const scopes = [...new Map(rows.slice().sort((a, b) => a.scope_rank - b.scope_rank).map((r) => [r.scope, r.scope_label])).entries()];
    table.tHead.rows[0].replaceChildren(...['What VS4 would do', 'Loans', ...scopes.map(([, l]) => l)].map((text, i) => {
      const th = node('th', i ? null : 'vx-l', text);
      th.scope = 'col';
      return th;
    }));
    const body = table.tBodies[0];
    body.replaceChildren();
    const cells = new Map(rows.map((r) => [`${r.scope}|${r.key}`, r]));
    for (const [key, label] of COST_ROWS) {
      const tr = body.insertRow();
      const c0 = tr.insertCell();
      c0.className = 'vx-l';
      c0.textContent = label;
      const all = cells.get(`All|${key}`);
      tr.insertCell().textContent = all ? int(all.loans) : '—';
      for (const [scope] of scopes) {
        const r = cells.get(`${scope}|${key}`);
        tr.insertCell().textContent = r && r.loans >= CELL_MIN ? pct1(r.vs4_share) : '—';
      }
    }
    const opt = document.getElementById('option-table');
    opt.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const ob = opt.tBodies[0];
    ob.replaceChildren();
    for (const r of rowsOf('fees').filter((d) => d.view === 'option').sort((a, b) => a.scope_rank - b.scope_rank)) {
      const tr = ob.insertRow();
      tr.dataset.key = ['option', r.key].map(encodeURIComponent).join(',');
      const room = r.fee_fico_bp - r.fee_best_bp;
      [[r.scope_label, 'vx-l'], [int(r.loans)], [one(r.fee_fico_bp)], [one(r.fee_vs_bp)], [one(r.fee_best_bp)], [one(r.fee_actual_bp)], [room > 0 ? pct0((r.fee_fico_bp - r.fee_actual_bp) / room) : '—'],
        [money(room * r.avg_upb / 1e4)], [money((r.fee_vs_bp - r.fee_best_bp) * r.avg_upb / 1e4)]].forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
    }
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
      if (better && better.n >= 100 && better.reaches_fee != null && better.reaches_fee < 0.95) out.push(`${better.reaches_fee <= 0.05 ? 'None' : `About ${pct0(better.reaches_fee)}`} of a lower fee shows in its note rate. Where does the saving go: points, credits, broker pay or margin?`);
      if (same && same.n >= 100 && same.net_bp >= 3) out.push(`Its VS4 loans with no fee benefit carry ${signed(same.net_bp)} bp against its own FICO loans. Is that mix, or investors charging for VS4?`);
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
    drawLenderSplit(p);
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
    drawCarryLender(e, l, p);
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
    add('A lower fee reaching the rate', better && better.n >= 100 && better.reaches_fee != null ? `${reachText(better.reaches_fee)} (${signed(better.net_bp)} bp against ${one(better.fee_rate_bp)} bp of fee at 5 to 1)` : null);
    add('Same fee, rate against its own FICO loans', same && same.n >= 100 ? `${signed(same.net_bp)} bp on ${int(same.n)} loans` : null);
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
    // Until you set them, your scenario's pulls and price follow today's.
    for (const [key, value] of [['scn_pulls', pulls], ['scn_price', price]]) {
      const box = root.querySelector(`input[data-expo="${key}"]`);
      if (box && !expo.mine.has(key)) box.value = num(value);
    }
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

  vx.hooks.overview.push(drawNote, drawCarryOverview);
  vx.hooks.lenders.push(drawCompany);
  vx.hooks.scores.push(drawCost);
  vx.hooks.outlook.push(drawOutlookTools);
  vx.redraw();
})();
