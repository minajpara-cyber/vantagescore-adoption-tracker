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
  const FAMILY = { classic: CLASSIC, fico_new: NEWER, vs4: VS, vs_old: VS, multi: UNNAMED, other: UNNAMED };
  const SHARE_CELLS = ['classic', 'fico_new', 'vs4', 'vs_old', 'multi', 'other', 'none'];
  const OPTIONAL = new Set(['usd_bn', 'vs_old', 'multi', 'other', 'equity_share', 'filer', 'k_high', 'ms_p5', 'ms_rev']);
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
    mark('.pl-vs-only', 'vs_no_fico_n', 'view=meta', st, num(meta.vs_no_fico_n));
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

  function drawYears(p) {
    const st = statusOf('whole_market');
    const data = rowsOf('whole_market').filter((r) => r.view === 'trend' && r.key === p.myseg).sort((a, b) => a.year - b.year).map((r) => ({ ...r, slot: String(r.year) }));
    const keys = data.map((d) => d.slot);
    const tipOf = (d) => [`${d.year}, ${d.label}, ${int(d.n)} loans`, WHOLE_LINES(d)];
    const box = document.getElementById('mk-year-stack');
    if (box && prep(box, st) && data.length) {
      const W = box.clientWidth, H = 260, m = { top: 20, right: 6, bottom: 24, left: 0 };
      const svg = vx.svgFor(box, W, H, 'Which score lenders named each year');
      const y = d3.scaleLinear([0, 1], [H - m.bottom, m.top]);
      const yf = d3.format('.0%');
      const ticks = [0, 0.25, 0.5, 0.75, 1];
      const { x, widest } = vx.bandFrame(svg, keys, yearOf, y, yf, ticks, W, m);
      vx.yAxis(svg, y, yf, m.left, W - m.right, ticks);
      vx.bandAxis(svg, x, keys, yearOf, widest, H - m.bottom + 8);
      const bw = Math.min(24, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
      for (const d of data) {
        const parts = GROUPS.filter(([k]) => d[k] >= 0.0005);
        let below = 0;
        parts.forEach(([k, , color], i) => {
          const y0 = y(below), y1 = y(below + d[k]);
          below += d[k];
          const h = Math.max(0, y0 - y1 - (i ? 2 : 0));
          if (i === parts.length - 1) svg.append('path').attr('d', capped(x(d.slot) + off, y1, bw, h)).attr('fill', color);
          else svg.append('rect').attr('x', x(d.slot) + off).attr('width', bw).attr('y', y1 + 0).attr('height', h).attr('fill', color);
        });
        if (x.step() >= 32 || d === data[0] || d === data[data.length - 1]) svg.append('text').attr('x', x(d.slot) + x.bandwidth() / 2).attr('y', y(1) - 5).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(pct0(d.fico));
      }
      vx.bandHover(svg, box, x, data, 'slot', m, H, tipOf);
    }
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
  const SIZE_INK = col(7);
  const withPanel = (color, share) => `color-mix(in srgb, ${color} ${share}%, var(--color-panel))`;
  const PIECE_FILL = { gse: SIZE_INK, fha: withPanel(SIZE_INK, 65), va: withPanel(SIZE_INK, 40), usda: 'var(--cds-chart-muted)', other_conforming: withPanel('var(--cds-chart-muted)', 80), business: withPanel('var(--cds-chart-muted)', 60), jumbo: withPanel('var(--cds-chart-muted)', 40), rest: withPanel('var(--cds-chart-muted)', 60), equity: NONE };
  const ASSUME = {
    on: 'Assumption, on: FHA and VA reach the same level of VS4 only as the GSEs. No file can show VS4 only on FHA or VA, so the rows for today stay on the GSEs alone.',
    off: 'Assumption off: Fannie and Freddie alone. FHA and VA add nothing here.',
  };
  const sizeSaid = (rows, key) => (rows.find((r) => r.view === 'sentence' && r.key === key) || {}).text;

  function sizeLine(id, rows, st, key) {
    const el = document.getElementById(id);
    if (!el) return;
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
    if (ready) {
      drawSizeBars(rows, st, meta);
      drawPieceTable(rows);
      drawFollow(p, rows, st);
    }
    drawParts(rows, st);
    document.getElementById('ms-parts-card').hidden = st !== 'loading' && !rows.some((r) => r.view === 'part' || r.view === 'break');
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
    if (p.mview === 'va') drawVa();
  }

  vx.hooks.market.push(drawWholeMarket);
  vx.redraw();
})();
