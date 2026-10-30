// The whole market. From HMDA: which score lenders named on every kind of loan, which lenders named what, who uses each model, and applications per loan.
// From SEC filings: which model private-label deal reports name, and how much of the market they let us see.
// Runs after the other scripts; what they share is on window.vx.
(() => {
  const vx = window.vx;
  const { root, rowsOf, statusOf, int, pct1, prep, legend, tooltip, mark, col } = vx;
  const compact = d3.format('.3~s');
  const two = d3.format('.2f');
  const pct0 = d3.format('.0%');
  const node = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const CLASSIC = col(1), NEWER = col(2), VS = col(0), UNNAMED = 'var(--cds-chart-muted)', NONE = 'color-mix(in srgb, var(--cds-chart-muted) 45%, transparent)';
  const GROUPS = [['classic', 'Classic FICO', CLASSIC], ['fico_new', 'Newer FICO', NEWER], ['vs', 'VantageScore', VS], ['unnamed', 'Model not named', UNNAMED], ['none', 'No score reported', NONE]];
  const FAMILY = { classic: CLASSIC, fico_new: NEWER, vs4: VS, vs_old: VS, multi: UNNAMED, other: UNNAMED };
  const SHARE_CELLS = ['classic', 'fico_new', 'vs4', 'vs_old', 'multi', 'other', 'none'];
  const OPTIONAL = new Set(['usd_bn', 'vs_old', 'multi', 'other', 'equity_share', 'filer']);
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
      name.append(node('span', 'mk-n', `${compact(r.n)} loans`));
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
    table('mk-seg-table', seg, (r) => `segment,${r.key}`, (r) => [['label', r.label, true], ['n', int(r.n)], ['usd_bn', d3.format(',.0f')(r.usd_bn)], ...shareCells(r)]);
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
        row.append(node('div', 'hb-l', `${r.label}, ${compact(r.n)} loans`), node('div', 'hb-v', two(r.per_loan)));
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
    table('pl-deal-table', deals, (r) => key('deal', r.key), (r) => [['filed', day(r.filed), true], ['label', r.label, true], ['filer', r.filer, true], ['n', int(r.n)], ['vs4_n', int(r.vs4_n)], ['vs_old_n', int(r.vs_old_n)]]);
    const dealBody = document.querySelector('#pl-deal-table tbody');
    if (dealBody) linked(dealBody, deals, (r) => r.url, 1);
    const mentions = rows.filter((r) => r.view === 'mention');
    table('pl-mention-table', mentions, (r) => key('mention', r.key), (r) => [['filed', day(r.filed), true], ['label', r.label, true], ['filer', r.filer, true], ['count', int(r.count)]]);
    const mentionBody = document.querySelector('#pl-mention-table tbody');
    if (mentionBody) linked(mentionBody, mentions, (r) => r.url, 1);
    const filers = rows.filter((r) => r.view === 'filer').sort((a, b) => a.rank - b.rank);
    table('pl-filer-table', filers, (r) => key('filer', r.key), (r) => [['label', r.label, true], ['filings', int(r.filings)], ['with_model', int(r.with_model)], ['n', int(r.n)], ['fico', r.n ? pct1(r.fico) : '—'], ['vs', r.n ? pct2(r.vs) : '—']]);
  }

  // A column with a rounded top, from the baseline up.
  const capped = (x, y, w, h, r = 4) => {
    const c = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + c}Q${x},${y} ${x + c},${y}H${x + w - c}Q${x + w},${y} ${x + w},${y + c}V${y + h}Z`;
  };
  const yearOf = (k) => k;

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
      vx.bandAxis(svg, x, keys, yearOf, widest, H - m.bottom);
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
      vx.bandAxis(svg, x, keys, yearOf, widest, H - m.bottom);
      const cx = (d) => x(d.slot) + x.bandwidth() / 2;
      SERIES.forEach(([k, , color]) => {
        svg.append('path').attr('d', d3.line().x(cx).y((d) => y(d[k]))(data)).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
        svg.append('g').selectAll('circle').data(data).join('circle').attr('cx', cx).attr('cy', (d) => y(d[k])).attr('r', 4).attr('fill', color).attr('stroke', 'var(--color-panel)').attr('stroke-width', 2);
        const last = data[data.length - 1];
        svg.append('text').attr('x', cx(last) + 8).attr('y', y(last[k])).attr('dy', '0.35em').style('fill', 'var(--color-fg)').text(pct1(last[k]));
      });
      vx.bandHover(svg, zoom, x, data, 'slot', m, H, tipOf);
    }
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
  }

  function drawWholeMarket(p) {
    root.querySelectorAll('.mk-only-hmda').forEach((el) => { el.hidden = p.mview !== 'hmda'; });
    root.querySelectorAll('.mk-only-pl').forEach((el) => { el.hidden = p.mview !== 'pl'; });
    drawMarket(p);
    if (p.mview === 'hmda') drawYears(p);
    drawPrivate(p);
  }

  vx.hooks.market.push(drawWholeMarket);
  vx.redraw();
})();
