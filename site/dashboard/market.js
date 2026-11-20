// The whole market. From HMDA: which score lenders named on every kind of loan, which lenders named what, who uses each model, and applications per loan.
// From SEC filings: which model private-label deal reports name, and how much of the market they let us see.
// From Ginnie Mae's loan files: whose VA loans show scores Classic FICO almost never gets to.
// Runs after the other scripts; what they share is on window.vx.
(() => {
  const vx = window.vx;
  const { root, rowsOf, statusOf, int, pct1, prep, legend, tooltip, mark, col } = vx;
  const two = d3.format('.2f');
  const pct0 = d3.format('.0%');
  const node = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const CLASSIC = col(1), NEWER = col(2), VS = col(0), UNNAMED = 'var(--cds-chart-muted)', NONE = 'color-mix(in srgb, var(--cds-chart-muted) 70%, transparent)';
  const GROUPS = [['classic', 'Classic FICO', CLASSIC], ['fico_new', 'Newer FICO', NEWER], ['vs', 'VantageScore', VS], ['unnamed', 'Model not named', UNNAMED], ['none', 'No score reported', NONE]];
  // The private securitizers' card draws "No score reported" hatched and outlined in the muted ink, so it never reads as one grey with "Model not named", in light
  // or dark: a CSS background for swatches and bars, and an SVG pattern in the yearly columns (mixColumns).
  const HATCH = 'repeating-linear-gradient(135deg, var(--color-fg-muted) 0 1px, transparent 1px 4px)';
  const PH_GROUPS = GROUPS.map(([k, label, color]) => [k, label, k === 'none' ? HATCH : color]);
  const FAMILY = { classic: CLASSIC, fico_new: NEWER, vs4: VS, vs_old: VS, multi: UNNAMED, other: UNNAMED };
  const SHARE_CELLS = ['classic', 'fico_new', 'vs4', 'vs_old', 'multi', 'other', 'none'];
  const OPTIONAL = new Set(['usd_bn', 'vs_old', 'multi', 'other', 'equity_share', 'filer', 'k_high', 'ms_p5', 'ms_rev', 'ph_buyer', 'ph_classic', 'ph_fico_new']);
  const CHART_LENDERS = 15;

  const WHOLE_LINES = (r) => [[CLASSIC, 'Classic FICO', pct1(r.classic)], [NEWER, 'Newer FICO', pct1(r.fico_new)], [VS, 'VS4', pct1(r.vs4)], [VS, 'VantageScore 2.0, 3.0', pct1(r.vs_old)],
    [UNNAMED, 'More than one model', pct1(r.multi)], [UNNAMED, 'Other model', pct1(r.other)], [NONE, 'No score reported', pct1(r.none)]];
  const pct2 = d3.format('.2%');
  const DEAL_LINES = (r) => [[CLASSIC, 'Classic FICO', `${pct1(r.classic)}, ${int(r.classic_n)}`], [NEWER, 'Newer FICO', `${pct1(r.fico_new)}, ${int(r.fico_new_n)}`], [VS, 'VS4', `${pct2(r.vs4)}, ${int(r.vs4_n)}`], [VS, 'Other VantageScore', `${pct2(r.vs_old)}, ${int(r.vs_old_n)}`],
    [UNNAMED, 'A code or word not read', `${pct1(r.unclear)}, ${int(r.unclear_n)}`], [NONE, 'None named', `${pct1(r.blank)}, ${int(r.blank_n)}`]];

  function bars(box, rows, status, labelOf, cls, lines = WHOLE_LINES, vsFmt = pct1, groups = GROUPS) {
    if (!box || !prep(box, status)) return;
    box.replaceChildren();
    const tip = tooltip(box);
    rows.forEach((r, i) => {
      const row = node('div', `mk-row ${cls ? cls(r, i) : ''}`);
      const name = node('div', 'mk-l', labelOf(r));
      name.append(', ', node('span', 'mk-n', `${int(r.n)} loans`));
      const val = node('div', 'mk-v');
      val.append('FICO', node('b', null, pct1(r.fico)), ' ', 'VantageScore', node('b', null, vsFmt(r.vs)));
      const track = node('div', 'mk-t');
      track.setAttribute('role', 'img');
      track.setAttribute('aria-label', `${labelOf(r)}: ${groups.map(([k, l]) => `${l} ${pct1(r[k])}`).join(', ')}`);
      groups.forEach(([k, , color]) => {
        if (r[k] < 0.0005) return;
        const part = node('span');
        part.style.flex = `${r[k]} 1 0`;
        part.style.background = color;
        if (color === HATCH) part.style.boxShadow = 'inset 0 0 0 1px var(--color-fg-muted)';
        track.append(part);
      });
      row.append(name, val, track);
      row.addEventListener('pointermove', (event) => tip.show(event, `${labelOf(r)}, ${int(r.n)} loans`, lines(r)));
      row.addEventListener('pointerleave', () => tip.hide());
      box.append(row);
    });
  }

  function table(id, rows, keyOf, cells) {
    const body = document.querySelector(`#${id} tbody`);
    if (!body) return;
    body.replaceChildren(...rows.map((r) => {
      const tr = node('tr');
      tr.dataset.key = keyOf(r);
      cells(r).forEach(([key, text, left]) => tr.append(node('td', [left ? 'vx-l' : '', OPTIONAL.has(key) ? 'vx-opt' : ''].filter(Boolean).join(' '), text)));
      return tr;
    }));
  }

  function drawMarket(p) {
    const st = statusOf('whole_market');
    const rows = rowsOf('whole_market');
    const meta = rows.find((r) => r.view === 'meta') || {};
    const seg = rows.filter((r) => r.view === 'segment').sort((a, b) => a.order - b.order);
    const at = (k) => seg.find((r) => r.key === k) || {};
    const first = at('first'), equity = at('equity');
    const pc = (v) => (v == null ? null : pct1(v));
    mark('.mk-year', 'year', 'view=meta', st, meta.year == null ? null : String(meta.year));
    const next = root.querySelector('.mk-next');
    if (next) next.textContent = meta.year == null ? '—' : String(meta.year + 2);
    mark('.mk-first-fico', 'fico', 'view=segment&key=first', st, pc(first.fico));
    mark('.mk-first-vs', 'vs', 'view=segment&key=first', st, pc(first.vs));
    mark('.mk-first-unknown', 'unknown', 'view=segment&key=first', st, pc(first.unknown));
    mark('.mk-eq-fico', 'fico', 'view=segment&key=equity', st, pc(equity.fico));
    mark('.mk-eq-new', 'fico_new', 'view=segment&key=equity', st, pc(equity.fico_new));
    mark('.mk-eq-vs', 'vs', 'view=segment&key=equity', st, pc(equity.vs));
    mark('.mk-eq-vs4', 'vs4', 'view=segment&key=equity', st, pc(equity.vs4));
    root.querySelectorAll('.mk-legend').forEach((el) => legend(el, GROUPS.map(([, label, color]) => [color, label, 'box'])));
    bars(document.getElementById('mk-seg-bars'), seg, st, (r) => r.label, (r, i) => `${i < 2 ? 'mk-sum' : ''} ${i === 1 ? 'mk-rule' : ''}`);
    const shareCells = (r) => SHARE_CELLS.map((k) => [k, pct1(r[k])]);
    table('mk-seg-table', seg, (r) => `segment,${r.key}`, (r) => [['label', r.label, true], ['n', int(r.n)], ['usd_bn', vx.usdM(r.usd_bn * 1e9)], ...shareCells(r)]);
    const lenders = rows.filter((r) => r.view === 'lender' && r.scope === p.mscope).sort((a, b) => a.rank - b.rank);
    bars(document.getElementById('mk-lender-bars'), lenders.slice(0, CHART_LENDERS), st, (r) => r.name);
    table('mk-lender-table', lenders, (r) => `lender,${r.scope},${r.rank}`, (r) => [['name', r.name, true], ['n', int(r.n)], ['equity_share', pct1(r.equity_share)], ...shareCells(r)]);
    const models = rows.filter((r) => r.view === 'model');
    const firstNamed = (code) => d3.min(rows.filter((r) => r.view === 'model_year' && r.code === code && r.share >= 0.0001), (r) => r.year);
    table('mk-model-table', models, (r) => `model,${r.code}`, (r) => [['name', r.name, true], ['n', int(r.n)], ['equity_share', r.equity_share == null ? '—' : pct1(r.equity_share)], ['first_named', String(firstNamed(r.code) ?? '—')], ['users', r.users, true]]);
    root.querySelectorAll('#mk-model-table tbody tr').forEach((tr, i) => {
      const sw = node('span', 'vx-sw');
      sw.style.background = FAMILY[models[i].family];
      tr.firstChild.prepend(sw);
    });
    const apps = document.getElementById('mk-apps-bars');
    if (apps) {
      apps.classList.toggle('dash-skeleton', st === 'loading');
      const list = rows.filter((r) => r.view === 'apps');
      const top = Math.max(d3.max(list, (r) => r.per_loan) || 1, 1);
      apps.replaceChildren(...list.map((r) => {
        const row = node('div', 'hb');
        row.append(node('div', 'hb-l', `${r.label}, ${int(r.n)} loans`), node('div', 'hb-v', two(r.per_loan)));
        const track = node('div', 'hb-t');
        const fill = node('span');
        fill.style.width = `${(r.per_loan / top) * 100}%`;
        fill.style.background = 'var(--cds-chart-muted)';
        track.append(fill);
        row.append(track);
        return row;
      }));
    }
  }

  const DEAL_GROUPS = [['classic', 'Classic FICO', CLASSIC], ['fico_new', 'Newer FICO', NEWER], ['vs', 'VantageScore', VS], ['unnamed', 'A code or word not read', UNNAMED], ['none', 'None named', NONE]];
  const shortDay = d3.utcFormat('%b %-d, %Y');
  const day = (s) => shortDay(new Date(`${s}T00:00:00Z`));
  const key = (...parts) => parts.map(encodeURIComponent).join(',');
  // Deal names come as filed: an all-capital name of two or more words goes to title case, and the shelf filed both ways keeps one spelling.
  const dealName = (s) => s.replace(/^[A-Z][A-Z ]+(?= 20\d\d-)/, (m) => (m.includes(' ') ? m.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase()) : m)).replace(/^Cross (?=20\d\d-)/, 'CROSS ');

  function linked(tbody, rows, urlOf, column) {
    tbody.querySelectorAll('tr').forEach((tr, i) => {
      const td = tr.children[column], a = node('a', 'vx-link', td.textContent);
      a.href = urlOf(rows[i]);
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      td.replaceChildren(a);
    });
  }

  function drawPrivate(p) {
    const st = statusOf('private_label');
    const rows = rowsOf('private_label');
    const meta = rows.find((r) => r.view === 'meta') || {};
    const num = (v) => (v == null ? null : int(v));
    mark('.pl-n', 'n', 'view=meta', st, num(meta.n));
    mark('.pl-named', 'named', 'view=meta', st, num(meta.named));
    mark('.pl-deals', 'deals', 'view=meta', st, num(meta.deals));
    mark('.pl-from', 'from', 'view=meta', st, meta.from ? day(meta.from) : null);
    mark('.pl-vs', 'vs', 'view=meta', st, meta.vs == null ? null : pct2(meta.vs));
    mark('.pl-vs-n', 'vs4_n', 'view=meta', st, num(meta.vs4_n));
    mark('.pl-vs-only', 'vs4_no_fico_n', 'view=meta', st, num(meta.vs4_no_fico_n));  // of the VS4 loans just before it, so the two counts agree
    mark('.pl-recent', 'recent_vs', 'view=meta', st, meta.recent_vs == null ? null : pct2(meta.recent_vs));
    mark('.pl-recent-k', 'recent_vs_n', 'view=meta', st, num(meta.recent_vs_n));
    mark('.pl-recent-n', 'recent_n', 'view=meta', st, num(meta.recent_n));
    mark('.pl-lag', 'lag_months', 'view=meta', st, meta.lag_months == null ? null : String(meta.lag_months));
    const mixSt = statusOf('score_mix');
    const head = rowsOf('score_mix').find((r) => r.view === 'month' && r.agency === 'All' && r.headline) || {};
    const where = head.start ? `view=month&agency=All&start=${encodeURIComponent(head.start)}` : null;
    mark('.pl-gse', 'vs_share', where, mixSt, head.vs_share == null ? null : pct1(head.vs_share));
    mark('.pl-gse-month', 'start', where, mixSt, head.start ? vx.monthYear(head.start) : null);
    root.querySelectorAll('.pl-legend').forEach((el) => legend(el, DEAL_GROUPS.map(([, label, color]) => [color, label, 'box'])));
    const picked = p.pbasis === 'kind' ? rows.filter((r) => r.view === 'kind') : rows.filter((r) => r.view === 'period' && r.basis === p.pbasis);
    const list = picked.slice().sort((a, b) => a.order - b.order);
    bars(document.getElementById('pl-bars'), p.pbasis === 'pulled' ? list.slice(-12) : list, st, (r) => r.label, null, DEAL_LINES, pct2, DEAL_GROUPS);
    const deals = rows.filter((r) => r.view === 'deal');
    table('pl-deal-table', deals, (r) => key('deal', r.key), (r) => [['filed', day(r.filed), true], ['label', dealName(r.label), true], ['filer', r.filer, true], ['n', int(r.n)], ['vs4_n', int(r.vs4_n)], ['vs_old_n', int(r.vs_old_n)]]);
    const dealBody = document.querySelector('#pl-deal-table tbody');
    if (dealBody) linked(dealBody, deals, (r) => r.url, 1);
    const mentions = rows.filter((r) => r.view === 'mention');
    table('pl-mention-table', mentions, (r) => key('mention', r.key), (r) => [['filed', day(r.filed), true], ['label', dealName(r.label), true], ['filer', r.filer, true], ['count', int(r.count)]]);
    const mentionBody = document.querySelector('#pl-mention-table tbody');
    if (mentionBody) linked(mentionBody, mentions, (r) => r.url, 1);
    const filers = rows.filter((r) => r.view === 'filer').sort((a, b) => a.rank - b.rank);
    table('pl-filer-table', filers, (r) => key('filer', r.key), (r) => [['label', r.label, true], ['filings', int(r.filings)], ['with_model', int(r.with_model)], ['n', int(r.n)], ['fico', r.named ? pct1(r.fico) : '—'], ['vs', r.named ? pct2(r.vs) : '—']]);
  }

  // ---- The VantageScore watch: SEC filings from the weekly search and what is kept by hand, newest first. Each date carries the word that says what it is, a filing's
  // own words sit in quotes, and a mark goes on what was first listed in the week to the build's day. Every word comes from the file. ----
  function drawWatch() {
    const card = document.getElementById('vw-card');
    if (!card) return;
    const st = statusOf('vs_watch');
    const rows = rowsOf('vs_watch');
    const meta = rows.find((r) => r.view === 'meta') || {};
    card.hidden = st === 'ok' && !meta.items_n;  // nothing to list, or a build that stopped, which the weekly report says
    if (card.hidden) return;
    [['vw-lead', 'lead'], ['vw-search', 'search']].forEach(([id, said]) => sizeLine(id, rows, st, said));
    const items = rows.filter((r) => r.view === 'item').sort((a, b) => a.order - b.order);
    tableBox('vw-table', st, !items.length);
    document.querySelector('#vw-table tbody').replaceChildren(...items.map((r) => {
      const tr = node('tr');
      tr.dataset.key = key('item', r.key);
      const when = node('td', 'vx-l vw-when');
      if (r.new) when.append(node('span', 'vw-new', 'New'), ' ');
      when.append(`${r.basis} `, node('span', 'vw-day', day(r.date)));
      const src = node('td', 'vx-l vw-src');
      src.append(srcLink(r.source, r.url));
      const what = node('td', 'vx-l vw-what', r.quote ? `“${r.what}”` : r.what);
      if (r.also) what.append(' ', node('span', 'vw-also', r.also));  // the other filings that repeat a company's sentence word for word
      tr.append(when, node('td', 'vx-l vw-kind', r.kind_label), node('td', 'vx-l vw-who', r.who), what, src);
      return tr;
    }));
  }

  // A column with a rounded top, from the baseline up.
  const capped = (x, y, w, h, r = 4) => {
    const c = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + c}Q${x},${y} ${x + c},${y}H${x + w - c}Q${x + w},${y} ${x + w},${y + c}V${y + h}Z`;
  };
  const yearOf = (k) => k;
  // Values at the end of the lines, spread so they never print on each other and held above the axis labels.
  const endLabels = (svg, ends, floor) => {
    ends.sort((a, b) => a.y - b.y).forEach((e, i) => { if (i && e.y - ends[i - 1].y < 14) e.y = ends[i - 1].y + 14; });
    ends.reduceRight((low, e) => { e.y = Math.min(e.y, low); return e.y - 14; }, floor);
    ends.forEach((e) => svg.append('text').attr('x', e.x + 8).attr('y', e.y).attr('dy', '0.35em').style('fill', 'var(--color-fg)').text(e.text));
  };

  // A column of 100 a year, stacked by the score named in the groups' order and colors (GROUPS, or the private securitizers' card's PH_GROUPS, whose hatch draws
  // as an SVG pattern), with the share naming a FICO model on top where the places allow. The yearly chart above and the private securitizers' card draw with it.
  // The axis thins counting out from anchor, so that year always has its label. Where only the ends have room for their numbers, the first stands over the first
  // column the axis names, so no number sits over a year left unnamed.
  function mixColumns(box, data, H, label, tipOf, anchor = 0, groups = GROUPS) {
    const W = box.clientWidth, m = { top: 20, right: 6, bottom: 24, left: 0 };
    const keys = data.map((d) => d.slot);
    const svg = vx.svgFor(box, W, H, label);
    const hatch = `${box.id}-hatch`;
    if (groups.some(([, , color]) => color === HATCH)) {
      const pattern = svg.append('defs').append('pattern').attr('id', hatch).attr('patternUnits', 'userSpaceOnUse').attr('width', 4).attr('height', 4).attr('patternTransform', 'rotate(45)');
      pattern.append('rect').attr('width', 1.25).attr('height', 4).style('fill', 'var(--color-fg-muted)');
    }
    const paint = (piece, color) => (color === HATCH ? piece.style('fill', `url(#${hatch})`).style('stroke', 'var(--color-fg-muted)').style('stroke-width', 1) : piece.attr('fill', color));
    const y = d3.scaleLinear([0, 1], [H - m.bottom, m.top]);
    const ticks = [0, 0.25, 0.5, 0.75, 1];
    const { x, widest } = vx.bandFrame(svg, keys, yearOf, y, pct0, ticks, W, m);
    vx.yAxis(svg, y, pct0, m.left, W - m.right, ticks);
    const named = new Set(vx.bandAxis(svg, x, keys, yearOf, widest, H - m.bottom + 8, anchor));
    const firstNamed = data.find((d) => named.has(d.slot)) || data[0];
    const bw = Math.min(24, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    for (const d of data) {
      const parts = groups.filter(([k]) => d[k] >= 0.0005);
      let below = 0;
      parts.forEach(([k, , color], i) => {
        const y0 = y(below), y1 = y(below + d[k]);
        below += d[k];
        const h = Math.max(0, y0 - y1 - (i ? 2 : 0));
        if (i === parts.length - 1) paint(svg.append('path').attr('d', capped(x(d.slot) + off, y1, bw, h)), color);
        else paint(svg.append('rect').attr('x', x(d.slot) + off).attr('width', bw).attr('y', y1 + 0).attr('height', h), color);
      });
      if (d.fico != null && (x.step() >= 32 || d === firstNamed || d === data[data.length - 1])) svg.append('text').attr('x', x(d.slot) + x.bandwidth() / 2).attr('y', y(1) - 5).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(pct0(d.fico));
    }
    vx.bandHover(svg, box, x, data, 'slot', m, H, tipOf);
  }

  function drawYears(p) {
    const st = statusOf('whole_market');
    const data = rowsOf('whole_market').filter((r) => r.view === 'trend' && r.key === p.myseg).sort((a, b) => a.year - b.year).map((r) => ({ ...r, slot: String(r.year) }));
    const keys = data.map((d) => d.slot);
    const tipOf = (d) => [`${d.year}, ${d.label}, ${int(d.n)} loans`, WHOLE_LINES(d)];
    const box = document.getElementById('mk-year-stack');
    if (box && prep(box, st) && data.length) mixColumns(box, data, 260, 'Which score lenders named each year', tipOf);
    const SERIES = [['fico_new', 'Newer FICO', NEWER], ['vs', 'VantageScore', VS], ['other', 'Other model', UNNAMED]];
    legend(document.getElementById('mk-zoom-legend'), SERIES.map(([, label, color]) => [color, label, 'line']));
    const zoom = document.getElementById('mk-year-zoom');
    if (zoom && prep(zoom, st) && data.length) {
      const W = zoom.clientWidth, H = 260, m = { top: 20, right: 30, bottom: 24, left: 0 };
      const svg = vx.svgFor(zoom, W, H, 'Newer FICO, VantageScore and other model each year, closer up');
      const top = Math.max(d3.max(data, (d) => Math.max(d.fico_new, d.vs, d.other)) * 1.15, 0.005);
      const y = d3.scaleLinear([0, top], [H - m.bottom, m.top]).nice(4);
      const yf = y.domain()[1] >= 0.05 ? d3.format('.0%') : d3.format('.1%');
      const { x, widest } = vx.bandFrame(svg, keys, yearOf, y, yf, 4, W, m);
      vx.yAxis(svg, y, yf, m.left, W - m.right, 4);
      vx.bandAxis(svg, x, keys, yearOf, widest, H - m.bottom + 8);
      const cx = (d) => x(d.slot) + x.bandwidth() / 2;
      const last = data[data.length - 1];
      const ends = [];
      SERIES.forEach(([k, , color]) => {
        svg.append('path').attr('d', d3.line().x(cx).y((d) => y(d[k]))(data)).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
        svg.append('g').selectAll('circle').data(data).join('circle').attr('cx', cx).attr('cy', (d) => y(d[k])).attr('r', 4).attr('fill', color).attr('stroke', 'var(--color-panel)').attr('stroke-width', 2);
        ends.push({ x: cx(last), y: y(last[k]), text: pct1(last[k]) });
      });
      endLabels(svg, ends, H - m.bottom - 4);
      vx.bandHover(svg, zoom, x, data, 'slot', m, H, tipOf);
    }
  }

  function drawLenderYears(p) {
    const body = document.querySelector('#mk-lender-years tbody');
    if (!body) return;
    const rows = rowsOf('whole_market').filter((r) => r.view === 'lender_year' && r.scope === p.mscope);
    const years = [...new Set(rows.map((r) => r.year))].sort();
    const head = document.querySelector('#mk-lender-years thead');
    const tr = node('tr');
    tr.append(node('th', 'vx-l', 'Lender'), ...years.map((v) => node('th', null, String(v))));
    head.replaceChildren(tr);
    const color = { classic: CLASSIC, fico_new: NEWER, vs: VS }[p.mmeasure];
    const lenders = d3.groups(rows, (r) => r.rank).sort((a, b) => a[0] - b[0]);
    body.replaceChildren(...lenders.map(([, list]) => {
      const row = node('tr');
      row.append(node('td', 'vx-l vx-name', list[0].name));
      years.forEach((v) => {
        const r = list.find((c) => c.year === v);
        const td = node('td', 'mk-heat', r ? pct0(r[p.mmeasure]) : '—');
        if (r) td.style.background = `color-mix(in srgb, ${color} ${Math.round(r[p.mmeasure] * 65)}%, transparent)`;
        if (r) td.title = `${int(r.n)} loans`;
        row.append(td);
      });
      return row;
    }));
    // On a narrow screen the table opens on its newest years, beside the lender names.
    const yearBox = body.closest('.vx-tablebox');
    yearBox.scrollLeft = yearBox.scrollWidth;
  }

  // VA loans at the top of the score range, by closing month. Lender names come from the data.
  const monthOf = (m) => new Date(`${m}-01T00:00:00Z`);
  const monthLab = (m) => d3.utcFormat('%b %Y')(monthOf(m));
  const monthLong = (m) => d3.utcFormat('%B %Y')(monthOf(m));
  const LEAD = col(0), LEAD_ALL = `color-mix(in srgb, ${col(0)} 50%, var(--color-panel))`, NEXT = col(3);
  const VA_LINES = [['lead_retail', LEAD], ['lead_own', LEAD_ALL], ['second', NEXT], ['others', UNNAMED]];
  const seen =(r) => `${pct2(r.share)}, ${int(r.k)} of ${int(r.n)}`;

  function drawVaChart(box, st, monthly) {
    const keys = [...new Set(monthly.map((r) => r.month))].sort();
    if (!box || !prep(box, st) || !keys.length) return;
    const W = box.clientWidth, H = 280;
    const svg = vx.svgFor(box, W, H, 'Share of VA loans at 830 or above, by closing month');
    const of = (key) => monthly.filter((r) => r.key === key).sort((a, b) => d3.ascending(a.month, b.month));
    // Names sit on the lines when they leave room for the plot; the legend names the lines otherwise.
    const tag = (r) => `${r.label} ${pct1(r.share)}`;
    const nameW = vx.textWidth(svg, VA_LINES.flatMap(([key]) => of(key).slice(-1).map(tag)));
    const roomy = W - nameW >= 340;
    const m = { top: 16, right: roomy ? Math.ceil(nameW) + 14 : 48, bottom: 32, left: 0 };
    const top =Math.max(d3.max(monthly.filter((r) => r.key !== 'fha'), (r) => r.share) * 1.1, 0.01);
    const y = d3.scaleLinear([0, top], [H - m.bottom, m.top]).nice(4);
    const yf = y.domain()[1] >= 0.05 ? pct0 : d3.format('.1%');
    const { x, widest } = vx.bandFrame(svg, keys, monthLab, y, yf, 4, W, m);
    vx.yAxis(svg, y, yf, m.left, W - m.right, 4);
    vx.bandAxis(svg, x, keys, monthLab, widest, H - m.bottom + 8);
    const cx = (r) => x(r.month) + x.bandwidth() / 2;
    const ends = [];
    VA_LINES.forEach(([key, color]) => {
      const line = of(key);
      if (!line.length) return;
      svg.append('path').attr('d', d3.line().x(cx).y((r) => y(r.share))(line)).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
      const last = line[line.length - 1];
      svg.append('circle').attr('cx', cx(last)).attr('cy', y(last.share)).attr('r', 4).attr('fill', color).attr('stroke', 'var(--color-panel)').attr('stroke-width', 2);
      ends.push({ x: cx(last), y: y(last.share), text: roomy ? tag(last) : pct1(last.share) });
    });
    endLabels(svg, ends, H - m.bottom - 4);
    const labelOf = (key) => (of(key)[0] || {}).label;
    vx.bandHover(svg, box, x, keys.map((month) => ({ month })), 'month', m, H, ({ month }) => [
      `Closed ${monthLong(month)}${month === keys[keys.length - 1] ? ' (still filling in)' : ''}`,
      [...VA_LINES, ['fha', NONE]].flatMap(([key, color]) => {
        const r = monthly.find((c) => c.key === key && c.month === month);
        return r ? [[color, labelOf(key), seen(r)]] : [];
      })]);
  }

  function drawVaChannels(rows) {
    const body = document.querySelector('#va-channels tbody');
    if (!body) return;
    const months = [...new Set(rows.map((r) => r.month))].sort();
    const tr = node('tr');
    tr.append(node('th', 'vx-l', 'Loans'), ...months.map((m) => node('th', null, monthLab(m))));
    document.querySelector('#va-channels thead').replaceChildren(tr);
    const groups = d3.groups(rows, (r) => `${r.name}, ${r.channel} ${r.kind}`).filter(([, list]) => d3.sum(list, (r) => r.n) >= 100);
    body.replaceChildren(...groups.map(([label, list]) => {
      const row = node('tr');
      row.append(node('td', 'vx-l vx-name', label));
      months.forEach((m) => {
        const r = list.find((c) => c.month === m);
        const shown = r && r.signal != null && r.n >= 50;
        const td = node('td', 'mk-heat', shown ? pct0(r.signal) : '—');
        if (shown) td.style.background = `color-mix(in srgb, ${LEAD} ${Math.round(Math.min(r.signal, 1) * 65)}%, transparent)`;
        if (r) td.title = `${int(r.k)} of ${int(r.n)} loans at 830 or above`;
        row.append(td);
      });
      return row;
    }));
  }

  function drawVa() {
    const st = statusOf('ginnie_va');
    const rows = rowsOf('ginnie_va');
    const meta = rows.find((r) => r.view === 'meta') || {};
    const range = (key) => rows.find((r) => r.view === 'range' && r.key === key);
    const at = (key) => `view=range&key=${key}`;
    const markRange = (sel, key) => ['low', 'high'].forEach((end) => {
      const v = (range(key) || {})[end];
      mark(`${sel}-${end}`, end, at(key), st, v == null ? null : pct0(v));
    });
    mark('.va-ref-vs4', 'ref_vs4', 'view=meta', st, meta.ref_vs4 == null ? null : pct1(meta.ref_vs4));
    mark('.va-ref-classic', 'ref_classic', 'view=meta', st, meta.ref_classic == null ? null : pct2(meta.ref_classic));
    mark('.va-lead-name', 'lead', 'view=meta', st, meta.lead);
    mark('.va-second-name', 'second', 'view=meta', st, meta.second);
    markRange('.va-lead', 'lead_own');
    markRange('.va-retail', 'lead_retail');
    markRange('.va-second', 'second');
    markRange('.va-all', 'all');
    mark('.va-m1', 'm1', 'view=meta', st, meta.m1 ? monthLong(meta.m1) : null);
    mark('.va-m2', 'm2', 'view=meta', st, meta.m2 ? monthLong(meta.m2) : null);
    mark('.va-last', 'last_issue', 'view=meta', st, meta.last_issue ? monthLong(meta.last_issue) : null);
    mark('.va-both', 'leaders_share', 'view=meta', st, meta.leaders_share == null ? null : pct0(meta.leaders_share));
    mark('.va-since', 'since', 'view=meta', st, meta.since ? monthLong(meta.since) : null);
    mark('.va-fha-k', 'fha_k', 'view=meta', st, meta.fha_k == null ? null : int(meta.fha_k));
    mark('.va-fha-n', 'fha_n', 'view=meta', st, meta.fha_n == null ? null : int(meta.fha_n));
    const monthly = rows.filter((r) => r.view === 'month');
    const labelOf = (key) => (monthly.find((r) => r.key === key) || {}).label || '';
    legend(document.getElementById('va-legend'), VA_LINES.map(([key, color]) => [color, labelOf(key), 'line']));
    drawVaChart(document.getElementById('va-chart'), st, monthly);
    const under = (r) => {
      if (r.too_few) return 'too few to read';
      return r.upper != null ? `under ${pct0(Math.ceil(r.upper * 100) / 100)}` : pct0(r.signal);
    };
    const lenders = rows.filter((r) => r.view === 'lender').sort((a, b) => d3.descending(a.k, b.k) || a.rank - b.rank);
    table('va-lender-table', lenders, (r) => key('lender', r.issuer), (r) => [['name', r.name, true], ['n', int(r.n)], ['k', int(r.k)], ['k_high', int(r.k_high)], ['full', int(Math.round(r.full))], ['signal', under(r)]]);
    drawVaChannels(rows.filter((r) => r.view === 'channel'));
  }

  // ---- How big each piece is, and what if FHA and VA follow. Every sentence comes from the file, where its guard is. ----
  // The pieces' colors, one set for the size bar, the yearly chart, the piece table and the first screen's small picture. Fannie and Freddie the strongest: the size ink
  // halfway to the text color. FHA, VA and USDA one ramp of the size ink, Other conforming size, Business purpose and Jumbo one ramp of a second ink, each from half way
  // toward the page background up to full strength as the stack rises. The middle and top steps are theme variables in page.css (--ms-step-mid, --ms-step-top): in
  // dark the middle step sits nearer its ink, so the figures printed in it read at 4.5:1, and the top step leans toward the text color, so it stays apart from the
  // middle. Neighbours sit 1.5:1 apart or more and every piece 2:1 or more on the panel, in both themes. A share is a number, or the step mid or top.
  const SIZE_INK = col(7), REST_INK = col(3);
  const STEP = { mid: 76, top: 100 };  // light's steps, as page.css sets them, for a fill drawn where those variables do not reach
  const toward = (color, share, end) => `color-mix(in srgb, ${color} ${typeof share === 'number' ? `${share}%` : `var(--ms-step-${share}, ${STEP[share]}%)`}, var(${end}))`;
  const PIECE_FILL = { gse: toward(SIZE_INK, 50, '--color-fg'), fha: toward(SIZE_INK, 50, '--color-bg'), va: toward(SIZE_INK, 'mid', '--color-bg'), usda: toward(SIZE_INK, 'top', '--color-fg'),
    other_conforming: toward(REST_INK, 50, '--color-bg'), business: toward(REST_INK, 'mid', '--color-bg'), jumbo: toward(REST_INK, 'top', '--color-fg'), rest: toward(REST_INK, 50, '--color-bg'), equity: NONE };
  const ASSUME = {
    on: 'Assumption, on: FHA and VA reach the same level of VS4 only as the GSEs. No file can show VS4 only on FHA or VA, so the rows for today stay on the GSEs alone.',
    off: 'Assumption off: Fannie and Freddie alone. FHA and VA add nothing here.',
  };
  const sizeSaid = (rows, key) => (rows.find((r) => r.view === 'sentence' && r.key === key) || {}).text;

  function sizeLine(id, rows, st, key) {
    const el = document.getElementById(id);
    if (!el) return;
    el.dataset.where = `view=sentence&key=${key}`;  // the row it prints, as a line that follows a toggle changes rows
    const text = sizeSaid(rows, key);
    el.textContent = text || (st === 'loading' ? '—' : '');
    el.hidden = st !== 'loading' && !text;
    el.classList.toggle('dash-skeleton', st === 'loading');
  }

  function srcLink(label, url) {
    const a = node('a', 'vx-link', label || 'Source');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    return a;
  }

  // One bar, each piece's share of it. With labels, a share prints inside its piece where it fits. The first screen's small picture draws with this too.
  function pieceTrack(box, pieces, field, labels) {
    const track = node('div', 'ms-t');
    track.setAttribute('role', 'img');
    track.setAttribute('aria-label', pieces.map((r) => `${r.label} ${pct1(r[field])}`).join(', '));
    pieces.forEach((r) => {
      const part = node('span');
      const fill = PIECE_FILL[r.key];
      part.style.flex = `${r[field]} 1 0`;
      part.style.background = fill;
      const room = box.clientWidth * r[field];
      const text = !labels ? '' : room >= 38 ? pct1(r[field]) : room >= 24 ? pct0(r[field]) : '';
      if (text) {
        part.textContent = text;
        part.style.color = vx.inkOn(fill);
      }
      track.append(part);
    });
    return track;
  }
  vx.pieceTrack = pieceTrack;  // and the first screen's small picture
  vx.PIECE_FILL = PIECE_FILL;

  function drawSizeBars(rows, st, meta) {
    const box = document.getElementById('ms-bars');
    const pieces = rows.filter((r) => r.view === 'piece' && r.first_lien).sort((a, b) => a.order - b.order);
    legend(document.getElementById('ms-legend'), pieces.map((r) => [PIECE_FILL[r.key], r.label, 'box']));
    if (!box || !prep(box, st)) return;
    box.replaceChildren();
    if (!pieces.length) return;
    const tip = tooltip(box);
    const block = (title, total, field, sizeOf, reach) => {
      const wrap = node('div', 'ms-bar');
      const head = node('div', 'ms-bar-l');
      head.append(node('span', null, title), node('span', 'ms-bar-n', total));
      wrap.append(head, pieceTrack(box, pieces, field, true));
      if (reach != null) {
        const brace = node('div', 'ms-brace', `Fannie, Freddie, FHA and VA: ${pct1(reach)}`);
        brace.style.width = `${Math.min(100, reach * 100)}%`;
        wrap.append(brace);
      }
      wrap.addEventListener('pointermove', (event) => tip.show(event, `${title}, ${total}`, pieces.map((r) => [PIECE_FILL[r.key], r.label, `${pct1(r[field])}, ${sizeOf(r)}`])));
      wrap.addEventListener('pointerleave', () => tip.hide());
      return wrap;
    };
    box.append(block(`First-lien loans made in ${meta.year}`, `${int(meta.first_n)} loans`, 'share_n', (r) => `${int(r.n)} loans`, meta.three_share));
    if (pieces.every((r) => r.share_usd != null)) box.append(block(`First-lien dollars, ${meta.year}`, vx.usdM(meta.first_usd_bn * 1e9), 'share_usd', (r) => vx.usdM(r.usd_bn * 1e9), meta.usd_own));
  }

  // The bar above for every year, built the same way, stacked in its order and colors. Home equity stays off the stack, in the hover and the table under the chart.
  // A year the file leaves out keeps its place and says why in a word. Every year, word and figure comes from the file.
  const millions = (v) => `${d3.format('.1f')(v / 1e6)}m`;
  const shortYear = (k) => `’${k.slice(2)}`;  // ’18, where four figures do not fit
  const GAP = 1;  // px of panel between two pieces of a column

  // Each piece's height in whole pixels: every edge where the sums put it on the axis, rounded, so on a 1x screen a 1px piece paints its own color and not a blend.
  // Less the gap below it, and never under 1px, so every kind shows; what the small pieces gain comes off the biggest, so the column still ends on its rounded total.
  function stackHeights(vals, y) {
    let below = 0;
    const edges = [y(0), ...vals.map((v) => y(below += v))].map(Math.round);
    const hs = vals.map((v, i) => edges[i] - edges[i + 1] - (i ? GAP : 0));
    const lift = d3.sum(hs, (h) => Math.max(0, 1 - h)), big = d3.maxIndex(hs);
    return hs.map((h, i) => Math.max(1, h) - (i === big ? lift : 0));
  }

  // Whether what stands at a place, a column or a left-out year's word, leaves room for a total of this width over a column dist places off whose top is at top: no
  // taller than that column, or far enough to the side for half the total's width and 2px. Each place gives its top and half its width as reach.
  const clearOf = (n, top, width, dist, step) => n.reach.top >= top || width / 2 + 2 <= dist * step - n.reach.half;

  // Which columns print their total over them: each one where every total fits its place; else every k-th counting back from the newest, k the places the widest needs,
  // as the axis is thinned. Of those, a total prints only where it clears what stands in the places beside it (clearOf). Where that leaves fewer than two, as on a phone
  // where the thinned places stand beside taller columns, every total that clears its neighbours and the totals already kept, counting back from the newest, if that
  // keeps more.
  function totalsAt(data, newest, widthOf, step) {
    const drawn = data.filter((d) => d.ok), last = data.indexOf(newest);
    const every = Math.max(1, Math.ceil((d3.max(drawn, widthOf) + 6) / step));
    const clears = (d) => {
      const i = data.indexOf(d);
      return data.every((n, j) => j === i || !n.reach || clearOf(n, d.reach.top, widthOf(d), Math.abs(j - i), step));
    };
    const picked = drawn.filter((d) => (last - data.indexOf(d)) % every === 0 && clears(d));
    if (picked.length >= 2) return picked;
    const kept = [];
    drawn.slice().reverse().forEach((d) => {
      const i = data.indexOf(d);
      if (clears(d) && kept.every((k) => Math.abs(data.indexOf(k) - i) * step >= (widthOf(k) + widthOf(d)) / 2 + 6)) kept.push(d);
    });
    return kept.length > picked.length ? kept.reverse() : picked;
  }

  function drawMix(p, rows, st) {
    const usd = p.munit === 'usd', share = p.mscale === 'share';
    sizeLine('ms-mix-cap', rows, st, usd ? 'mix_caption_usd' : 'mix_caption');  // the caption speaks of the view's own unit
    const list = rows.filter((r) => r.view === 'mix_year');
    const kinds = d3.groups(list.filter((r) => r.first_lien).sort((a, b) => a.order - b.order), (r) => r.key);
    legend(document.getElementById('ms-mix-legend'), kinds.map(([key, of]) => [PIECE_FILL[key], of[0].label, 'box']));
    drawMixTable(p, rows, st);
    const box = document.getElementById('ms-mix-chart');
    if (!box || !prep(box, st)) return;
    const gaps = rows.filter((r) => r.view === 'mix_gap');
    const gapOf = (year) => gaps.find((r) => r.year === year && r.measure === (usd ? 'usd' : 'n'));
    const shareOf = (r) => r[usd ? 'share_usd' : 'share_n'];
    const valueOf = (r) => (share ? shareOf(r) : usd ? (r.usd_bn == null ? null : r.usd_bn * 1e9) : r.n);
    const sizeOf = (r) => (!usd ? millions(r.n) : r.usd_bn >= 999.5 ? vx.usdM(r.usd_bn * 1e9) : `$${d3.format(',.0f')(r.usd_bn)}bn`);  // whole $bn, short enough to sit in a column
    const data = [...new Set([...list, ...gaps].map((r) => r.year))].sort((a, b) => a - b).map((year) => {
      const of = list.filter((r) => r.year === year).sort((a, b) => a.order - b.order);
      const parts = of.filter((r) => r.first_lien);
      const ok = !gapOf(year) && parts.length > 0 && parts.every((r) => valueOf(r) != null);
      return { year, slot: String(year), of, parts, ok, total: ok ? (usd ? parts[0].first_usd_bn * 1e9 : parts[0].first_n) : null, sum: ok ? d3.sum(parts, valueOf) : 0 };
    });
    if (!data.length) return;
    const drawn = data.filter((d) => d.ok), newest = drawn[drawn.length - 1];
    const W = box.clientWidth, H = 280;
    const svg = vx.svgFor(box, W, H, `First-lien loans made each year, by kind: ${share ? `share of each year's ${usd ? 'dollars' : 'loans'}` : usd ? 'dollars' : 'loans'}`);
    // From 768px wide the kinds are named beside the newest column, as the VA chart names its lines, when it is the last place on the axis. The legend names them below
    // that width, where the names would crowd the columns, and where a left-out year's place follows the newest column, as the names would then stand beside nothing.
    const names = newest ? newest.parts.filter((r) => valueOf(r) > 0).map((r) => r.label) : [];
    const nameW = names.length && window.matchMedia('(min-width: 768px)').matches ? Math.ceil(vx.textWidth(svg, names)) : 0;
    const named = nameW > 0 && W - nameW >= 420 && newest === data[data.length - 1];
    const m = { top: 22, right: named ? nameW + 20 : 6, bottom: 24, left: 0 };
    const y = d3.scaleLinear([0, share ? 1 : d3.max(data, (d) => Math.max(d.sum, d.total || 0)) || 1], [H - m.bottom, m.top]);
    if (!share) y.nice(4);
    const inTn = y.domain()[1] >= 1e12;
    const yf = share ? pct0 : usd ? (v) => (v ? `$${d3.format('~g')(v / (inTn ? 1e12 : 1e9))}${inTn ? 'tn' : 'bn'}` : '$0') : (v) => (v ? `${d3.format('~g')(v / 1e6)}m` : '0');
    const ticks = share ? [0, 0.25, 0.5, 0.75, 1] : 4;
    const keys = data.map((d) => d.slot);
    const { x, widest } = vx.bandFrame(svg, keys, yearOf, y, yf, ticks, W, m);
    vx.yAxis(svg, y, yf, m.left, W - m.right, ticks);
    // Years in four figures where they fit, else in two; where even those would meet, thinned counting back from the newest year with a column, so it always has its year.
    const four = widest + 10 <= x.step();
    const labelled = new Set(vx.bandAxis(svg, x, keys, four ? yearOf : shortYear, four ? widest : vx.textWidth(svg, keys.map(shortYear)), H - m.bottom + 8, keys.indexOf((newest || data[data.length - 1]).slot)));
    const bw = Math.min(56, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    const cx = (d) => x(d.slot) + x.bandwidth() / 2;
    // Whole pixels from the baseline up, as stackHeights gives them.
    drawn.forEach((d) => {
      const parts = d.parts.filter((r) => valueOf(r) > 0), hs = stackHeights(parts.map(valueOf), y);
      let at = Math.round(y(0));
      d.boxes = parts.map((r, i) => {
        at -= hs[i] + (i ? GAP : 0);
        return { r, top: at, h: hs[i] };
      });
      d.reach = { top: at, half: bw / 2 };
      d.boxes.forEach(({ r, top, h }, i) => {
        if (i === d.boxes.length - 1) svg.append('path').attr('d', capped(x(d.slot) + off, top, bw, h)).attr('fill', PIECE_FILL[r.key]);
        else svg.append('rect').attr('x', x(d.slot) + off).attr('width', bw).attr('y', top).attr('height', h).attr('fill', PIECE_FILL[r.key]);
      });
    });
    // A year left out keeps its place with a word for why, across its place where the word fits and up it where it does not; where the axis thins its year away, the
    // word carries the year, unless the year would stand the word over the newest column beside it and too near for that column's total (clearOf), as on a phone when
    // a left-out year is the last place. The caption, the hover and the table name that year. Its reach, for the totals beside it: the word's top and half its width,
    // as drawn.
    const said = (d) => (usd ? vx.usdM(d.total) : millions(d.total)), saidWidth = (d) => vx.textWidth(svg, [said(d)]);
    data.filter((d) => !d.ok).forEach((d) => {
      const short = (gapOf(d.year) || {}).short || '—';
      const word = svg.append('text');
      const put = (text) => {
        word.text(text).attr('text-anchor', 'middle').attr('dy', null).attr('transform', null);
        const across = word.node().getComputedTextLength() + 4 <= x.step();
        if (across) word.attr('x', cx(d)).attr('y', y(0) - 6);
        else word.attr('x', null).attr('y', null).attr('text-anchor', 'start').attr('dy', '0.35em').attr('transform', `translate(${cx(d)},${y(0) - 6}) rotate(-90)`);
        const b = word.node().getBBox();  // before its turn, if it is turned
        d.reach = across ? { top: b.y, half: b.width / 2 } : { top: y(0) - 6 - b.x - b.width, half: Math.max(-b.y, b.y + b.height) };
      };
      put(labelled.has(d.slot) ? short : `${d.year}: ${short}`);
      const beside = newest && Math.abs(data.indexOf(d) - data.indexOf(newest)) === 1;
      const room = (n) => clearOf(n, newest.reach.top, saidWidth(newest), Math.abs(data.indexOf(n) - data.indexOf(newest)), x.step());
      if (!share && beside && !labelled.has(d.slot) && !room(d) && drawn.every((n) => n === newest || room(n))) put(short);
    });
    // Inside every piece 16px tall or more: its share of the year, or in Totals its size where the sizes fit, in whichever ink reads on its fill. One form across the
    // chart: where any size would not fit its column every piece prints its share, and where any share would not fit to one place, every share prints whole.
    const ink = {}, fits = (text) => vx.textWidth(svg, [text]) + 6 <= bw;
    const tall = drawn.flatMap((d) => d.boxes.filter(({ r, h }) => h >= 16 && shareOf(r) != null).map((b) => ({ d, ...b })));
    const forms = [...(share ? [] : [sizeOf]), (r) => pct1(shareOf(r)), (r) => pct0(shareOf(r))];
    const form = forms.find((f) => tall.every(({ r }) => fits(f(r)))) || forms[forms.length - 1];
    tall.forEach(({ d, r, top, h }) => {
      const text = form(r);
      ink[r.key] ??= vx.inkOn(PIECE_FILL[r.key]);
      if (fits(text)) svg.append('text').attr('x', cx(d)).attr('y', top + h / 2).attr('dy', '0.35em').attr('text-anchor', 'middle').style('fill', ink[r.key]).text(text);
    });
    // Totals over the columns: over each where they all fit, else thinned from the newest as the axis is, and only where one clears what stands beside it (totalsAt).
    if (!share) {
      totalsAt(data, newest, saidWidth, x.step()).forEach((d) => svg.append('text').attr('x', cx(d)).attr('y', d.reach.top - 5).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(said(d)));
    }
    if (named) {
      // Each name at its piece's middle, spread so none meets the next; a name moved off its middle is tied back to it by a short line.
      const right = x(newest.slot) + off + bw;
      const ends = newest.boxes.map(({ r, top, h }) => ({ x: right + 6, y: top + h / 2, mid: top + h / 2, text: r.label }));
      endLabels(svg, ends, H - m.bottom - 4);
      ends.filter((e) => Math.abs(e.y - e.mid) > 2).forEach((e) => svg.append('line').attr('x1', right + 1).attr('x2', right + 11).attr('y1', e.mid).attr('y2', e.y).attr('stroke', 'var(--cds-chart-reference)'));
    }
    const head = (d) => `First-lien loans made in ${d.year}`;
    vx.bandHover(svg, box, x, data, 'slot', m, H, (d) => {
      if (!d.ok) return [head(d), [[null, (gapOf(d.year) || {}).text || '—']]];
      const lines = d.parts.map((r) => [PIECE_FILL[r.key], r.label, `${pct1(shareOf(r))}, ${usd ? vx.usdM(r.usd_bn * 1e9) : `${int(r.n)} loans`}`]);
      d.of.filter((r) => !r.first_lien).forEach((r) => lines.push([null, `${r.label}, not in the bar`, usd ? vx.usdM(r.usd_bn * 1e9) : `${int(r.n)} loans`]));
      return [`${head(d)}, ${usd ? vx.usdM(d.total) : `${int(d.total)} loans`}`, lines];
    });
  }

  // Each year's numbers, under the chart: a row a year, a column a kind, then the year's first-lien total and home equity, which is not in the bars. Loans or dollars as
  // the chart shows them, each kind's share of the year beside its size, dollars all in $bn so a column copies as one unit. A year left out says why across its row.
  // It serves phones, where the hover does not open.
  const bn = d3.format(',.1f');

  function drawMixTable(p, rows, st) {
    const table = document.getElementById('ms-mix-table');
    if (!table) return;
    const usd = p.munit === 'usd', sizeF = usd ? 'usd_bn' : 'n', shareF = usd ? 'share_usd' : 'share_n';
    const list = rows.filter((r) => r.view === 'mix_year');
    const gaps = rows.filter((r) => r.view === 'mix_gap' && r.measure === (usd ? 'usd' : 'n'));
    const kinds = d3.groups(list.filter((r) => r.first_lien).sort((a, b) => a.order - b.order), (r) => r.key).map(([k, of]) => [k, of[0].label]);
    const equity = list.find((r) => !r.first_lien);
    const size = (v) => (v == null ? '—' : usd ? `$${bn(v)}bn` : int(v));
    const th = (text, field, where, cls) => {
      const e = node('th', cls, text);
      e.scope = 'col';
      e.dataset.field = field;
      if (where) e.dataset.where = where;
      return e;
    };
    const head = node('tr');
    head.append(th('Year made', 'year', null, 'vx-l'), ...kinds.map(([k, label]) => th(label, sizeF, `view=mix_year&key=${k}`)), th(usd ? 'First-lien dollars' : 'First-lien loans', usd ? 'first_usd_bn' : 'first_n'),
      ...(equity ? [th(`${equity.label}, not in the bars`, sizeF, 'view=mix_year&key=equity')] : []));
    table.tHead.replaceChildren(head);
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const years = [...new Set([...list, ...gaps].map((r) => r.year))].sort((a, b) => a - b);
    table.tBodies[0].replaceChildren(...years.map((year) => {
      const tr = node('tr');
      tr.dataset.key = key('mix_year', year);
      tr.append(node('td', 'vx-l', String(year)));
      const gap = gaps.find((r) => r.year === year);
      if (gap) {
        const td = node('td', 'vx-l ms-why');
        td.colSpan = head.cells.length - 1;
        td.append(node('span', null, gap.text));
        tr.append(td);
        return tr;
      }
      const of = list.filter((r) => r.year === year);
      kinds.forEach(([k]) => {
        const r = of.find((c) => c.key === k), td = node('td', null, r ? size(r[sizeF]) : '—');
        if (r && r[shareF] != null) td.append(' ', node('span', 'ms-of', pct1(r[shareF])));
        tr.append(td);
      });
      const first = of.find((r) => r.first_lien) || {};
      tr.append(node('td', null, size(usd ? first.first_usd_bn : first.first_n)));
      if (equity) {
        const e = of.find((r) => !r.first_lien);
        tr.append(node('td', null, e ? size(e[sizeF]) : '—'));
      }
      return tr;
    }));
  }

  function drawPieceTable(rows) {
    const body = document.querySelector('#ms-piece-table tbody');
    if (!body) return;
    const heads = [...document.querySelectorAll('#ms-piece-table thead th')].map((th) => th.textContent);
    const pieces = rows.filter((r) => r.view === 'piece').sort((a, b) => a.order - b.order);
    body.replaceChildren(...pieces.map((r) => {
      const tr = node('tr');
      tr.dataset.key = `piece,${r.key}`;
      const name = node('td', 'vx-l ms-name');
      const sw = node('span', 'vx-sw');
      sw.style.background = PIECE_FILL[r.key];
      const label = node('span', null, r.label);
      if (r.key === 'other_conforming') label.dataset.term = 'othconf';
      name.append(sw, label);
      if (r.note) name.append(node('span', 'ms-note', r.note));
      const words = (text, srcs) => {
        const td = node('td', 'vx-l vx-wrap', text || '—');
        srcs.filter(([, url]) => url).forEach(([src, url]) => td.append(' ', srcLink(src, url)));
        return td;
      };
      const cells = [name, node('td', null, int(r.n)), node('td', null, r.share_n == null ? '—' : pct1(r.share_n)), node('td', null, r.usd_bn == null ? '—' : vx.usdM(r.usd_bn * 1e9)), node('td', null, r.share_usd == null ? '—' : pct1(r.share_usd)),
        words(r.uses, [[r.size_src_label, r.size_src_url], [r.size2_src_label, r.size2_src_url]]), words(r.move, [[r.move_src_label, r.move_src_url]]), words(r.fresh, [])];
      cells.forEach((td, i) => { if (i) td.dataset.h = heads[i]; });
      tr.append(...cells);
      return tr;
    }));
  }

  function drawFollow(p, rows, st) {
    const on = p.mfollow !== 'off';
    const pick = (r, name) => (on && r.assumed ? r[`both_${name}`] : r[`gse_${name}`]);
    const list = rows.filter((r) => r.view === 'follow').sort((a, b) => a.order - b.order);
    const first = document.getElementById('ms-follow-first');
    if (first) first.textContent = on ? 'VS4 only at the GSEs, and the same at FHA and VA' : 'VS4 only at the GSEs';
    const share = document.getElementById('ms-follow-share');
    if (share) share.textContent = on ? 'Share of first-lien loans: GSEs alone, then with FHA and VA' : 'Share of first-lien loans';
    const assume = document.getElementById('ms-assume');
    if (assume) assume.textContent = ASSUME[on ? 'on' : 'off'];
    const reach = document.getElementById('ms-reach');
    if (reach && !on) reach.hidden = true;
    const followTable = document.getElementById('ms-follow-table');
    if (followTable) followTable.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    table('ms-follow-table', list, (r) => `follow,${r.key}`, (r) => [['label', r.label, true], ['share', on ? r.pair_text : r.gse_share_text], ['ms_p4', pick(r, 'p4_text')], ['ms_p5', pick(r, 'p5_text')], ['ms_p6', pick(r, 'p6_text')], ['ms_rev', pick(r, 'rev_text')]]);
  }

  function sourced(li, r) {
    if (r.src_url) li.append(' ', srcLink(r.src_label, r.src_url));
    return li;
  }

  function drawParts(rows, st) {
    const box = document.getElementById('ms-parts');
    if (box) {
      box.classList.toggle('dash-skeleton', st === 'loading');
      const parts = rows.filter((r) => r.view === 'part').sort((a, b) => a.order - b.order);
      box.replaceChildren(...d3.groups(parts, (r) => r.part_label).map(([label, items]) => {
        const column = node('div');
        column.append(node('h3', null, label));
        const list = node('ul', 'vx-list');
        list.append(...items.map((r) => {
          const li = node('li');
          li.append(node('b', 'ms-prog', `${r.program}: `), r.text);
          if (r.as_of) li.append(` ${r.as_of}.`);
          if (r.key === 'use_va') {
            const go = node('button', 'vx-link', 'See the VA chart');
            go.type = 'button';
            go.dataset.mkView = 'va';
            li.append(' ', go);
          }
          return sourced(li, r);
        }));
        column.append(list);
        return column;
      }));
    }
    const breaks = document.getElementById('ms-breaks');
    if (breaks) {
      breaks.classList.toggle('dash-skeleton', st === 'loading');
      const said = rows.filter((r) => r.view === 'break').sort((a, b) => a.order - b.order);
      breaks.replaceChildren(...said.map((r) => sourced(node('li', null, r.text), r)));
      document.getElementById('ms-breaks-h').hidden = st !== 'loading' && !said.length;
    }
  }

  function drawSize(p) {
    if (!document.getElementById('size-sec')) return;
    const st = statusOf('market_size');
    const rows = rowsOf('market_size');
    const meta = rows.find((r) => r.view === 'meta') || {};
    const ready = st !== 'ok' || !!meta.ok;
    document.getElementById('ms-none').hidden = ready;
    ['ms-bars-card', 'ms-piece-card', 'ms-follow-card'].forEach((id) => { document.getElementById(id).hidden = !ready; });
    if (st === 'ok' && !rows.some((r) => r.view === 'follow')) document.getElementById('ms-follow-card').hidden = true;  // an input it needs is missing, and the weekly report says so
    mark('.ms-lead', 'text', 'view=sentence&key=lead', st, sizeSaid(rows, 'lead'));
    root.querySelector('.ms-lead').hidden = st !== 'loading' && !sizeSaid(rows, 'lead');  // no input file: the line under it says why, with no dash above it
    mark('.ms-year', 'year', 'view=meta', st, meta.year == null ? null : String(meta.year));
    [['ms-dollars', 'dollars'], ['ms-all', 'all_loans'], ['ms-fhfa', 'fhfa_count'], ['ms-gap', 'hmda_gap'], ['ms-rest', 'rest_mix'], ['ms-pl', 'private_label'], ['ms-reach', 'reach'], ['ms-basis', 'basis'], ['ms-pulls', 'pulls_check'], ['mk-hmda-gap', 'hmda_gap'], ['va-fha-note', 'fha_note'], ['va-fha-check', 'fha_check']]
      .forEach(([id, key]) => sizeLine(id, rows, st, key));
    // The yearly card stands on its own rows: it shows whatever years can be built, and goes only when none can, which the weekly report says.
    const mixCard = document.getElementById('ms-mix-card');
    mixCard.hidden = st === 'ok' && !rows.some((r) => r.view === 'mix_year');
    if (!mixCard.hidden) drawMix(p, rows, st);
    if (ready) {
      drawSizeBars(rows, st, meta);
      drawPieceTable(rows);
      drawFollow(p, rows, st);
    }
    drawParts(rows, st);
    document.getElementById('ms-parts-card').hidden = st !== 'loading' && !rows.some((r) => r.view === 'part' || r.view === 'break');
  }

  // ---- Loans sold to private securitizers, from HMDA, beside the SEC deal reports: the latest year in tiles, the score named each year and by kind; below the pair,
  // the biggest sellers and every lender putting VS4 on loans sold outside the agencies. Every figure and sentence comes from the file; a year before the form named
  // VS4 says so, and a seller's count the year before that is not comparable carries a mark and the file's words on why. ----
  const soldLines = (r) => WHOLE_LINES(r).map((line) => (line[1] === 'VS4' && r.vs4_on_form === false ? [line[0], 'VS4', 'not on the form that year'] : line[0] === NONE ? [HATCH, line[1], line[2]] : line));

  function tableBox(id, st, empty) {
    const box = document.getElementById(id).closest('.vx-tablebox');
    box.classList.toggle('dash-skeleton', st === 'loading');
    box.hidden = st === 'ok' && empty;
  }

  function drawPlHmda() {
    const card = document.getElementById('ph-card');
    if (!card) return;
    const more = document.getElementById('ph-more-card');
    const st = statusOf('pl_hmda');
    const rows = rowsOf('pl_hmda');
    const meta = rows.find((r) => r.view === 'meta') || {};
    card.hidden = st === 'ok' && meta.year == null;  // no HMDA file on disk, or a build that stopped, which the weekly report says
    if (more) more.hidden = card.hidden;
    if (card.hidden) return;
    const pc = (v) => (v == null ? null : pct1(v));
    mark('.ph-year', 'year', 'view=meta', st, meta.year == null ? null : String(meta.year));
    mark('.ph-n', 'n', 'view=meta', st, meta.n == null ? null : int(meta.n));
    mark('.ph-usd', 'usd_bn', 'view=meta', st, meta.usd_bn == null ? null : vx.usdM(meta.usd_bn * 1e9));
    mark('.ph-fico', 'fico', 'view=meta', st, pc(meta.fico));
    mark('.ph-classic', 'classic', 'view=meta', st, pc(meta.classic));
    mark('.ph-unknown', 'unknown', 'view=meta', st, pc(meta.unknown));
    mark('.ph-vs4', 'vs4_n', 'view=meta', st, meta.vs4_n == null ? null : meta.vs4_n ? int(meta.vs4_n) : 'None');  // a word, not a lone 0 in old-style figures
    [['ph-vs4-sub', 'vs4_tile'], ['ph-route', 'route'], ['ph-dips', 'dips'], ['ph-form', 'form'], ['ph-kinds', 'kinds'], ['ph-unsold', 'unsold'], ['ph-outside', 'outside'], ['ph-next', 'next']]
      .forEach(([id, said]) => sizeLine(id, rows, st, said));
    if (meta.lender_file_url && sizeSaid(rows, 'next')) document.getElementById('ph-next').append(' ', srcLink('CFPB', meta.lender_file_url));
    legend(document.getElementById('ph-legend'), PH_GROUPS.map(([, label, color]) => [color, label, color === HATCH ? 'hatch' : 'box']));
    const years = rows.filter((r) => r.view === 'year').sort((a, b) => a.year - b.year).map((r) => ({ ...r, slot: String(r.year) }));
    const chart = document.getElementById('ph-chart');
    if (chart && prep(chart, st) && years.length) {
      mixColumns(chart, years, 200, 'Which score lenders named on loans sold to private securitizers, each year', (d) => [`${d.year}, ${int(d.n)} loans sold to private securitizers, ${vx.usdM(d.usd_bn * 1e9)}`,
        d.n ? soldLines(d) : [[null, 'None sold to them that year']]], years.length - 1, PH_GROUPS);
    }
    // By kind, the biggest first, each with the year before in its hover.
    const kinds = rows.filter((r) => r.view === 'kind');
    const before = (r) => kinds.find((c) => c.year === meta.prior && c.key === r.key);
    bars(document.getElementById('ph-kind-bars'), kinds.filter((r) => r.year === meta.year).sort((a, b) => b.n - a.n), st, (r) => r.label, null, (r) => {
      const was = before(r);
      return meta.prior == null ? soldLines(r) : [...soldLines(r), [null, String(meta.prior), was ? `${int(was.n)} loans, Classic FICO ${pct1(was.classic)}, VS4 loans ${int(was.vs4_n)}` : 'none sold to them']];
    }, pct1, PH_GROUPS);
    // The biggest sellers: any FICO model and no score reported right after the name, before Loans, so a phone from 320px shows both; Classic and newer FICO where
    // there is room. Dollars all in $bn, so the column copies as one unit.
    const sellers = rows.filter((r) => r.view === 'lender').sort((a, b) => a.rank - b.rank);
    document.getElementById('ph-prior-h').textContent = meta.prior == null ? 'Loans the year before' : `Loans in ${meta.prior}`;
    tableBox('ph-lender-table', st, !sellers.length);
    const priorCell = (r) => (r.prior_n == null ? '—' : r.prior_mark ? `${int(r.prior_n)}*` : int(r.prior_n));
    table('ph-lender-table', sellers, (r) => key('lender', r.rank), (r) => [['name', r.name, true], ['fico', pct1(r.fico)], ['none', pct1(r.none)], ['n', int(r.n)], ['usd_bn', `$${bn(r.usd_bn)}bn`],
      ['ph_classic', pct1(r.classic)], ['ph_fico_new', pct1(r.fico_new)], ['vs4_n', int(r.vs4_n)], ['prior_n', priorCell(r)]]);
    root.querySelectorAll('#ph-lender-table tbody tr').forEach((tr, i) => {
      const r = sellers[i];
      if (r.prior_n == null) return;
      const was = `${meta.prior}: ${int(r.prior_n)} loans, ${vx.usdM(r.prior_usd_bn * 1e9)}, Classic FICO ${pct1(r.prior_classic)}, VS4 loans ${int(r.prior_vs4_n)}`;
      tr.lastChild.title = r.prior_mark ? `${r.name} reported ${pct1(r.prior_unsold)} of its ${meta.prior} loans as not sold that year, so its ${meta.prior} count of loans sold to private securitizers is not comparable. ${was}` : was;
    });
    const users = rows.filter((r) => r.view === 'vs4_lender').sort((a, b) => a.rank - b.rank);
    tableBox('ph-vs4-table', st, !users.length);
    table('ph-vs4-table', users, (r) => key('vs4_lender', r.rank), (r) => [['name', r.name, true], ['n', int(r.n)], ['vs4_n', int(r.vs4_n)], ['vs4', pct1(r.vs4)], ['ph_buyer', r.buyer || '—', true]]);
  }

  root.addEventListener('click', (event) => {
    const go = event.target.closest('[data-mk-view]');
    if (!go) return;
    dash.setParams({ mview: go.dataset.mkView });
    document.getElementById('market-sec').scrollIntoView({ block: 'start' });
  });

  function drawWholeMarket(p) {
    drawSize(p);
    root.querySelectorAll('.mk-only-hmda').forEach((el) => { el.hidden = p.mview !== 'hmda'; });
    root.querySelectorAll('.mk-only-pl').forEach((el) => { el.hidden = p.mview !== 'pl'; });
    root.querySelectorAll('.mk-only-va').forEach((el) => { el.hidden = p.mview !== 'va'; });
    drawMarket(p);
    if (p.mview === 'hmda') drawYears(p);
    drawLenderYears(p);
    drawPrivate(p);
    if (p.mview === 'pl') drawPlHmda();
    if (p.mview === 'pl') drawWatch();
    if (p.mview === 'va') drawVa();
  }

  vx.hooks.market.push(drawWholeMarket);
  vx.redraw();
})();
