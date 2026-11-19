// The visual summaries: the first screen and the VS4-only card, out of every 100 loans, why the weeks jump, where every lender stands,
// how lenders decide, plus plain-word definitions of the terms the page uses.
// Runs after the main script and tools.js; what they share is on window.vx.
(() => {
  const vx = window.vx;
  const { root, rowsOf, statusOf, int, pct1, inkOn, olName, openSeller, shortDay, prep, svgFor, bandFrame, yAxis, bandAxis, bandHover, legend, tooltip, textWidth, MIX_GROUPS, AG_NAME, show, col, mark, monthYear } = vx;
  const pct0 = d3.format('.0%');
  const node = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const group = (k) => MIX_GROUPS.find((g) => g[0] === k);
  const asc = (f) => (a, b) => (a[f] < b[f] ? -1 : 1);
  const CELL_MIN = 20;

  // A column with a rounded top, from the baseline up.
  const capped = (x, y, w, h, r = 4) => {
    const c = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + c}Q${x},${y} ${x + c},${y}H${x + w - c}Q${x + w},${y} ${x + w},${y + c}V${y + h}Z`;
  };

  // ---- Out of every 100 loans ----
  const ORDER = ['both_vs', 'vs_only', 'both_fico', 'fico_only'];

  // Whole squares for each group that add up to 100, largest remainders first.
  function seats(shares) {
    const raw = shares.map((v) => v * 100);
    const out = raw.map(Math.floor);
    const left = Math.round(100 - d3.sum(out));
    raw.map((v, i) => [v - out[i], i]).sort((a, b) => b[0] - a[0]).slice(0, Math.max(0, left)).forEach(([, i]) => { out[i] += 1; });
    return out;
  }

  function drawWaffles(p) {
    const box = document.getElementById('wf-row');
    if (!box) return;
    const st = dash.data('score_mix').status;
    box.classList.toggle('dash-skeleton', st === 'loading');
    const rows = rowsOf('score_mix');
    const k = p.measure === 'upb' ? '_upb' : '';
    const head = rows.find((r) => r.view === 'month' && r.agency === 'All' && r.headline);
    const title = document.getElementById('score-mix-h');
    title.textContent = k ? 'Out of every $100 of loans, which scores does the file show?' : 'Out of every 100 loans, which scores does the file show?';
    document.getElementById('score-mix-square').textContent = k ? 'Each square is $1 in every $100 of balance.' : 'Each square is one loan in 100.';
    if (!head) return box.replaceChildren();
    box.replaceChildren(...['All', 'FNMA', 'FHLMC'].map((a) => {
      const r = rows.find((d) => d.view === 'month' && d.agency === a && d.start === head.start);
      const wrap = node('div', 'wf');
      wrap.append(node('h3', null, AG_NAME[a]));
      if (!r) return wrap;
      const shares = ORDER.map((g) => r[`${g}${k}_share`] || 0);
      const counts = seats(shares);
      const grid = node('div', 'wf-grid');
      grid.setAttribute('role', 'img');
      grid.setAttribute('aria-label', ORDER.map((g, i) => `${group(g)[1]} ${pct1(shares[i])}`).join(', '));
      ORDER.forEach((g, i) => {
        for (let n = 0; n < counts[i]; n += 1) {
          const cell = node('span');
          cell.style.background = group(g)[2];
          grid.append(cell);
        }
      });
      const list = node('ul', 'wf-list');
      ORDER.forEach((g, i) => {
        const li = node('li');
        const sw = node('span', 'vx-sw');
        sw.style.background = group(g)[2];
        li.append(sw, node('b', null, pct1(shares[i])), `${group(g)[1]}${g === 'fico_only' ? ', at most' : ''}`);
        list.append(li);
      });
      const sum = (label, v) => {
        const li = node('li', 'wf-sum');
        li.append(node('b', null, pct1(v)), label);
        return li;
      };
      list.append(sum('Shows Classic FICO, at least', r[`fico${k}_share`] || 0), sum('Shows VS4, at least', r[`vs${k}_share`] || 0), sum('Priced on VS4, exact', r[`vs4_priced${k}_share`] || 0));
      wrap.append(grid, list);
      return wrap;
    }));
  }

  // ---- Why the weeks jump ----
  function topUsers() {
    const rows = rowsOf('lender_mix').filter((r) => r.view === 'week' && r.agency === 'All');
    return d3.rollups(rows, (v) => d3.sum(v, (r) => r.bv + r.vo), (r) => r.id).sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, 2).map((d) => d[0]);
  }

  function drawWho(p) {
    const box = document.getElementById('who-chart');
    if (!box) return;
    const st = statusOf('lender_mix', 'score_mix', 'weekly');
    const covered = vx.coveredWeek(p.agency), open = vx.openWeek(p.agency);
    const weeks = rowsOf('score_mix').filter((r) => r.view === 'week' && r.agency === p.agency && covered(r)).sort(asc('start'));
    const top = topUsers();
    const names = new Map(rowsOf('lender_stage').filter((r) => r.view === 'lender').map((r) => [r.id, r.short]));
    const label = top.map((id) => names.get(id) || id).join(' and ');
    const note = document.getElementById('who-note');
    note.textContent = top.length ? `${label}'s share of each week's loans. When they deliver more, the market number jumps, even if no lender changed what it does.${weeks.some((w) => open(w.start)) ? ' Fainter: week not over.' : ''}` : '';
    if (!prep(box, st) || !weeks.length) return;
    const mix = rowsOf('lender_mix').filter((r) => r.view === 'week' && r.agency === p.agency && top.includes(r.id));
    const data = weeks.map((w) => ({ key: w.start, v: d3.sum(mix.filter((r) => r.start === w.start), (r) => r.n) / (w.loans || 1), loans: w.loans }));
    const W = box.clientWidth, H = 120, m = { top: 18, right: 6, bottom: 24, left: 6 };
    const svg = svgFor(box, W, H, `${label}'s share of each week's loans`);
    const x = d3.scaleBand(data.map((d) => d.key), [m.left, W - m.right]).paddingInner(0.35).paddingOuter(0.15);
    const y = d3.scaleLinear([0, Math.max(d3.max(data, (d) => d.v) || 0.01, 0.01)], [H - m.bottom, m.top]);
    const bw = Math.min(24, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.append('line').attr('x1', m.left).attr('x2', W - m.right).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', 'var(--cds-chart-axis)');
    for (const d of data) {
      const h = Math.max(0, y(0) - y(d.v));
      svg.append('path').attr('d', capped(x(d.key) + off, y(d.v), bw, h)).attr('fill', 'var(--cds-chart-muted)').attr('fill-opacity', open(d.key) ? vx.OPEN_FILL : 1);
      svg.append('text').attr('x', x(d.key) + x.bandwidth() / 2).attr('y', y(d.v) - 4).attr('text-anchor', 'middle').text(pct0(d.v));
      svg.append('text').attr('x', x(d.key) + x.bandwidth() / 2).attr('y', H - 6).attr('text-anchor', 'middle').text(shortDay(d.key));
    }
    bandHover(svg, box, x, data, 'key', m, H, (d) => [`Week of ${shortDay(d.key)}${open(d.key) ? ' so far' : ''}, ${int(d.loans)} loans`, [['var(--cds-chart-muted)', label, pct1(d.v)]]]);
  }

  function drawFrozen(p) {
    const box = document.getElementById('frozen-chart');
    if (!box) return;
    const st = statusOf('score_mix', 'weekly');
    const priced = col(0), onFico = group('both_fico')[2];
    const ghost = 'color-mix(in srgb, var(--color-fg) 30%, transparent)';
    const covered = vx.coveredWeek(p.agency), open = vx.openWeek(p.agency);
    const weeks = rowsOf('score_mix').filter((r) => r.view === 'week' && r.agency === p.agency && r.steady_carrying != null && covered(r)).sort(asc('start'));
    legend(document.getElementById('frozen-legend'), [[priced, 'Priced on VS4', 'box'], [onFico, 'Carrying VS4, priced on FICO', 'box'], [ghost, 'As delivered', 'box'], ...(weeks.some((r) => open(r.start)) ? [[vx.OPEN_KEY, 'Fainter: week not over', 'box']] : [])]);
    if (!prep(box, st)) return;
    if (!weeks.length) return;
    const W = box.clientWidth, H = 150, m = { top: 18, right: 6, bottom: 24, left: 6 };
    const svg = svgFor(box, W, H, 'Loans carrying VS4 each week with the lender mix frozen, against the weeks as delivered');
    const x = d3.scaleBand(weeks.map((r) => r.start), [m.left, W - m.right]).paddingInner(0.35).paddingOuter(0.15);
    const y = d3.scaleLinear([0, Math.max(d3.max(weeks, (r) => Math.max(r.vs_share || 0, r.steady_carrying)) || 0.01, 0.01)], [H - m.bottom, m.top]);
    const bw = Math.min(24, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.append('line').attr('x1', m.left).attr('x2', W - m.right).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', 'var(--cds-chart-axis)');
    for (const r of weeks) {
      const bx = x(r.start) + off;
      svg.append('path').attr('d', capped(bx - 3, y(r.vs_share || 0), bw + 6, Math.max(0, y(0) - y(r.vs_share || 0)))).attr('fill', ghost);
      const low = r.steady_priced || 0, topV = r.steady_carrying;
      const lowH = Math.max(0, y(0) - y(low));
      const faint = open(r.start) ? vx.OPEN_FILL : 1;
      svg.append('rect').attr('x', bx).attr('width', bw).attr('y', y(low)).attr('height', lowH).attr('fill', priced).attr('fill-opacity', faint);
      const upH = Math.max(0, y(low) - y(topV) - 2);
      svg.append('path').attr('d', capped(bx, y(topV), bw, upH)).attr('fill', onFico).attr('fill-opacity', faint);
      svg.append('text').attr('x', bx + bw / 2).attr('y', y(topV) - 4).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(pct0(topV));
      svg.append('text').attr('x', bx + bw / 2).attr('y', H - 6).attr('text-anchor', 'middle').text(shortDay(r.start));
    }
    bandHover(svg, box, x, weeks, 'start', m, H, (r) => [`Week of ${shortDay(r.start)}${open(r.start) ? ' so far' : ''}`, [[onFico, 'Carrying VS4, lender mix frozen', pct1(r.steady_carrying)], [priced, 'Priced on VS4, lender mix frozen', pct1(r.steady_priced)],
      [ghost, 'Carrying VS4, as delivered', pct1(r.vs_share || 0)]]]);
  }

  // ---- The first screen ----
  // Five rows, each one number, one line and one small picture, and the card on loans that show VS4 only. Every sentence and figure comes from the front and vs4_only datasets; here is only the drawing.
  const inOrder = (rows) => rows.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const frontOf = (view) => inOrder(rowsOf('front').filter((r) => r.view === view));
  const voOf = (view) => inOrder(rowsOf('vs4_only').filter((r) => r.view === view));
  const voSaid = (key) => (voOf('sentence').find((r) => r.key === key) || {}).text;
  const picOf = (key) => frontOf('pic').filter((r) => r.key === key);
  const vsOnly = () => group('vs_only')[2];
  const FR_H = 78, OPEN = 0.6;  // a row's picture; how strongly a month or a week not over is drawn, as on the main charts
  const SHORT = { tu_pull_share: 'TransUnion pulls', du_app_share: 'DU applications', shows: 'Shows VS4', priced: 'Priced on VS4', vs_only: 'Shows VS4 only', gse: 'GSEs', rest: 'Other' };

  // The header, on every tab.
  function drawFrontLine() {
    const m = frontOf('meta')[0] || {}, st = dash.data('front').status, text = [m.line, m.dated].filter(Boolean).join(' ');
    mark('#front-line', 'line', 'view=meta', st, text);
    if (st !== 'loading' && !text) document.getElementById('front-line').textContent = '';  // no dash under the title
  }

  // Share priced on VS4 by issue month, each bar's figure on it, with everyone outside the two largest VS4 lenders beside it in grey.
  function frMonths(box, st, rows) {
    if (!box || !prep(box, st) || !rows.length) return;
    const W = box.clientWidth, H = FR_H, last = rows[rows.length - 1];
    const side = W >= 240 && last.outside != null ? 74 : 0;
    const m = { top: 16, right: 1 + side, bottom: 17, left: 1 };
    const svg = svgFor(box, W, H, `${rows.map((r) => `${r.label} ${r.text}`).join(', ')}${last.outside != null ? `; everyone else ${pct1(last.outside)}` : ''}`);
    const x = d3.scaleBand(rows.map((r) => r.x), [m.left, W - m.right]).paddingInner(0.2);
    const y = d3.scaleLinear([0, d3.max(rows, (r) => r.v) || 0.01], [H - m.bottom, m.top]);
    const bw = Math.min(18, x.bandwidth() * 0.6), tw = 5;
    svg.append('line').attr('x1', m.left).attr('x2', W - m.right).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', 'var(--cds-chart-axis)');
    for (const r of rows) {
      const x0 = x(r.x) + (x.bandwidth() - bw - tw - 2) / 2, cx = x0 + bw / 2;
      svg.append('path').attr('d', capped(x0, y(r.v), bw, Math.max(0, y(0) - y(r.v)))).attr('fill', col(0)).attr('fill-opacity', r.open ? OPEN : 1);
      if (r.outside != null) svg.append('rect').attr('x', x0 + bw + 2).attr('width', tw).attr('y', y(r.outside)).attr('height', Math.max(1, y(0) - y(r.outside))).attr('fill', 'var(--cds-chart-muted)');
      svg.append('text').attr('x', cx).attr('y', y(r.v) - 4).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(r.text);
      const month = svg.append('text').attr('x', cx).attr('y', H - 4).attr('text-anchor', 'middle').text(r.open ? `${r.label} so far` : r.label);
      if (month.node().getComputedTextLength() > x.step()) month.text(r.label);
    }
    if (side) {
      svg.append('rect').attr('x', W - side + 6).attr('y', y(0) - 26).attr('width', 8).attr('height', 8).attr('rx', 2).attr('fill', 'var(--cds-chart-muted)');
      svg.append('text').attr('x', W - side + 18).attr('y', y(0) - 18).text('Everyone');
      svg.append('text').attr('x', W - side + 6).attr('y', y(0) - 4).text(`else ${pct1(last.outside)}`);
    }
  }

  // From credit pull to loan: one bar a row, each on its own base.
  function frFunnel(box, st, rows) {
    if (!box || !prep(box, st) || !rows.length) return;
    const W = box.clientWidth, H = FR_H, rowH = (H - 2) / rows.length, barH = Math.min(9, rowH - 4);
    const name = (r) => r.short || SHORT[r.x] || r.label;
    const svg = svgFor(box, W, H, rows.map((r) => `${r.label} ${r.text}`).join(', '));
    const left = Math.ceil(textWidth(svg, rows.map(name))) + 6, right = Math.ceil(textWidth(svg, rows.map((r) => r.text))) + 6;
    const x = d3.scaleLinear([0, d3.max(rows, (r) => r.v) || 1], [left, Math.max(left + 8, W - right)]);
    rows.forEach((r, i) => {
      const cy = 1 + rowH * i + rowH / 2;
      svg.append('text').attr('x', 0).attr('y', cy).attr('dy', '0.35em').style('fill', r.only ? 'var(--color-fg)' : null).text(name(r));
      svg.append('rect').attr('x', left).attr('width', Math.max(1.5, x(r.v) - left)).attr('y', cy - barH / 2).attr('height', barH).attr('rx', 2).attr('fill', r.only ? vsOnly() : col(0));
      svg.append('text').attr('x', W).attr('y', cy).attr('dy', '0.35em').attr('text-anchor', 'end').style('fill', r.only ? 'var(--color-fg)' : null).text(r.text);
    });
  }

  // One bar of 100: each piece named above it and sized below it, where the words fit.
  function frShare(box, st, rows) {
    if (!box || !prep(box, st) || !rows.length) return;
    const W = box.clientWidth, H = FR_H, top = 22, h = 24;
    const svg = svgFor(box, W, H, rows.map((r) => `${r.label} ${r.text}`).join(', '));
    const fills = vx.PIECE_FILL || {}, tones = [col(0), col(2), col(3)];  // the Rest of market tab's colors, once market.js has loaded
    const x = d3.scaleLinear([0, d3.sum(rows, (r) => r.v) || 1], [0, W]);
    let at = 0;
    rows.forEach((r, i) => {
      const x0 = x(at), w = x(at + r.v) - x0;
      at += r.v;
      svg.append('rect').attr('x', x0).attr('width', Math.max(0, w - 2)).attr('y', top).attr('height', h).attr('rx', 2).attr('fill', fills[r.x] || tones[i] || 'var(--cds-chart-muted)');
      const fit = (t) => t.node().getComputedTextLength() <= w - 2;
      const piece = svg.append('text').attr('x', x0).attr('y', top - 6).text(r.label);
      if (!fit(piece) && SHORT[r.x]) piece.text(SHORT[r.x]);
      if (!fit(piece)) piece.remove();
      const size = svg.append('text').attr('x', x0).attr('y', top + h + 15).style('fill', 'var(--color-fg)').text(r.text);
      if (!fit(size)) size.text(pct0(r.v));
      if (!fit(size)) size.remove();
    });
  }

  // A dot and its 95% range about a zero line, one row each.
  function frDots(box, st, rows) {
    if (!box || !prep(box, st) || !rows.length) return;
    const W = box.clientWidth, H = FR_H, rowH = 22, top = 13;
    const svg = svgFor(box, W, H, rows.map((r) => `${r.label} ${r.text}`).join(', '));
    const left = Math.ceil(textWidth(svg, rows.map((r) => r.label))) + 8, right = Math.ceil(textWidth(svg, rows.map((r) => r.text))) + 8;
    const far = d3.max(rows, (r) => Math.max(Math.abs(r.dot), Math.abs(r.tl ?? r.dot), Math.abs(r.th ?? r.dot))) || 1;
    const x = d3.scaleLinear([-far, far], [left, Math.max(left + 8, W - right)]);
    const base = top + rows.length * rowH - 8;
    svg.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', base).attr('stroke', 'var(--cds-chart-axis)');
    rows.forEach((r, i) => {
      const cy = top + i * rowH;
      svg.append('text').attr('x', 0).attr('y', cy).attr('dy', '0.35em').text(r.label);
      if (r.tl != null && r.th != null) svg.append('line').attr('x1', x(r.tl)).attr('x2', x(r.th)).attr('y1', cy).attr('y2', cy).attr('stroke', 'var(--color-fg-muted)').attr('stroke-width', 1.5);
      svg.append('circle').attr('cx', x(r.dot)).attr('cy', cy).attr('r', 4).attr('fill', col(0));
      svg.append('text').attr('x', W).attr('y', cy).attr('dy', '0.35em').attr('text-anchor', 'end').style('fill', 'var(--color-fg)').text(r.text);
    });
    const y = base + 13;
    svg.append('text').attr('x', x(0)).attr('y', y).attr('text-anchor', 'middle').text('0');
    if (x(0) - left >= 64) {
      svg.append('text').attr('x', x(0) - 10).attr('y', y).attr('text-anchor', 'end').text('VS4 lower');
      svg.append('text').attr('x', x(0) + 10).attr('y', y).text('VS4 higher');
    }
  }

  // A number line of FICO's price: today's above it, the most keeping FICO pays at each number of pulls below it.
  function frPrice(box, st, rows) {
    const marks = rows.filter((r) => !r.ref), ref = rows.find((r) => r.ref);
    if (!box || !prep(box, st) || !marks.length) return;
    const W = box.clientWidth, H = FR_H, axis = 28;
    const svg = svgFor(box, W, H, rows.map((r) => `${r.label} ${r.text}`).join(', '));
    const vals = rows.map((r) => r.v), lo = d3.min(vals), hi = d3.max(vals), pad = (hi - lo) * 0.12 || 1;
    const x = d3.scaleLinear([lo - pad, hi + pad], [0, W]);
    const place = (t, at) => {
      const w = t.node().getComputedTextLength();
      t.attr('x', Math.max(w / 2, Math.min(W - w / 2, at)));
    };
    svg.append('line').attr('x1', 0).attr('x2', W).attr('y1', axis).attr('y2', axis).attr('stroke', 'var(--cds-chart-axis)');
    for (const r of marks) {
      svg.append('line').attr('x1', x(r.v)).attr('x2', x(r.v)).attr('y1', axis - 5).attr('y2', axis + 5).attr('stroke', col(0)).attr('stroke-width', 2);
      place(svg.append('text').attr('y', axis + 19).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(r.text), x(r.v));
      place(svg.append('text').attr('y', axis + 34).attr('text-anchor', 'middle').text(r.label), x(r.v));
    }
    if (ref) {
      svg.append('line').attr('x1', x(ref.v)).attr('x2', x(ref.v)).attr('y1', axis - 9).attr('y2', axis + 5).attr('stroke', col(1)).attr('stroke-width', 2);
      place(svg.append('text').attr('y', axis - 13).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(ref.text), x(ref.v));
    }
  }

  function drawFront() {
    const st = dash.data('front').status;
    root.querySelectorAll('.fr[data-key]').forEach((el) => {
      const key = el.dataset.key, r = frontOf('row').find((d) => d.key === key) || {};
      if (r.go) el.dataset.go = r.go;
      if (r.label) el.querySelector('.fr-l').textContent = r.label;
      for (const [cls, field] of [['fr-n', 'number'], ['fr-what', 'what'], ['fr-line', 'line'], ['fr-cap', 'cap']]) mark(`.fr[data-key="${key}"] .${cls}`, field, `view=row&key=${key}`, st, r[field]);
      if (st !== 'loading') for (const [cls, field] of [['fr-what', 'what'], ['fr-line', 'line'], ['fr-cap', 'cap']]) if (!r[field]) el.querySelector(`.${cls}`).textContent = '';  // words whose guard failed leave their place empty, with no dash
      const num = el.querySelector('.fr-n');  // a screen reader can skip an arrow, so the row's name says it in a word
      if (st === 'ok' && String(r.number ?? '').includes('→')) {
        num.setAttribute('role', 'img');
        num.setAttribute('aria-label', String(r.number).replace(/\s*→\s*/, ' then '));
      } else {
        num.removeAttribute('role');
        num.removeAttribute('aria-label');
      }
    });
    frMonths(document.getElementById('fr-pic-adoption'), st, picOf('adoption'));
    frFunnel(document.getElementById('fr-pic-vs4_only'), st, picOf('vs4_only'));
    frShare(document.getElementById('fr-pic-market'), st, picOf('market'));
    frDots(document.getElementById('fr-pic-rate'), st, picOf('rate'));
    frPrice(document.getElementById('fr-pic-price'), st, picOf('price'));
    // More in words, row by row. The one line of LLPA dollars has its own place on the Rate tab.
    const said = document.getElementById('front-said');
    said.replaceChildren(...frontOf('row').flatMap((r) => {
      const lines = frontOf('sentence').filter((s) => s.row === r.key && !s.place);
      if (!lines.length) return [];
      const list = node('ul', 'vx-list');
      list.append(...lines.map((s) => node('li', null, s.text)));
      return [node('h3', null, r.label), list];
    }));
  }

  // The one line of LLPA dollars, in the labelled place on the Rate tab.
  function drawFrontLlpa() {
    const el = document.getElementById('llpa-working');
    if (!el) return;
    const said = frontOf('sentence').find((s) => s.place === 'rate');
    el.textContent = said ? said.text : '';
    el.hidden = !said;
  }

  // ---- Shows VS4 only, at most: the card at the top of VS4 only and outlook ----
  // Counts by week first disclosed. The first week most loans could show both scores stands apart, in grey; a week not over is fainter. Each chart has its own scale.
  function voBars(box, st, rows, f, label, hover) {
    if (!box || !prep(box, st) || !rows.length) return;
    const W = box.clientWidth, H = 150;
    const svg = svgFor(box, W, H, `${label}: ${rows.map((r) => `${r.label} ${int(f(r))}`).join(', ')}`);
    const half = Math.ceil(textWidth(svg, rows.map((r) => r.label)) / 2);
    const m = { top: 16, right: Math.max(1, half - 2), bottom: 18, left: Math.max(1, half - 2) };
    const keys = rows.flatMap((r, i) => (r.first && i + 1 < rows.length ? [r.week, 'apart'] : [r.week]));
    const x = d3.scaleBand(keys, [m.left, W - m.right]).paddingInner(0.3);
    const y = d3.scaleLinear([0, Math.max(d3.max(rows, f), 1)], [H - m.bottom, m.top]);
    const bw = Math.min(30, x.bandwidth());
    const room = x.step() >= textWidth(svg, [int(d3.max(rows, f))]) + 6;
    svg.append('line').attr('x1', m.left).attr('x2', W - m.right).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', 'var(--cds-chart-axis)');
    let right = -Infinity;
    rows.forEach((r, i) => {
      const cx = x(r.week) + x.bandwidth() / 2, v = f(r);
      svg.append('path').attr('d', capped(cx - bw / 2, y(v), bw, Math.max(0, y(0) - y(v)))).attr('fill', r.first ? 'var(--cds-chart-muted)' : vsOnly()).attr('fill-opacity', r.partial ? OPEN : 1);
      if (room || i === 0 || i === rows.length - 1) svg.append('text').attr('x', cx).attr('y', y(v) - 4).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(int(v));
      const t = svg.append('text').attr('x', cx).attr('y', H - 4).attr('text-anchor', 'middle').text(r.label);
      const w = t.node().getComputedTextLength();
      if (cx - w / 2 < right + 6) t.remove();
      else right = cx + w / 2;
    });
    bandHover(svg, box, x, rows, 'week', m, H, hover);
  }

  function drawVoCard() {
    if (!document.getElementById('vo-card')) return;
    const st = dash.data('vs4_only').status;
    const meta = voOf('meta')[0] || {}, lead = meta.lead_label || 'the small lender', noLead = st !== 'loading' && !meta.lead_label;
    const gse = voOf('gse'), freddie = gse.find((r) => r.key === 'fhlmc') || {};
    mark('#vo-lead', 'text', 'view=sentence&key=lead', st, voSaid('lead'));
    if (st !== 'loading' && !voSaid('lead')) document.getElementById('vo-lead').textContent = '';  // a sentence whose guard failed leaves its place empty
    for (const [id, key] of [['vo-allowed', 'allowed'], ['vo-rare-text', 'why_rare'], ['vo-pull-text', 'pull'], ['vo-lender-note', 'lenders'], ['vo-band-note', 'bands']]) {
      const el = document.getElementById(id), text = voSaid(key);
      el.textContent = text || '';
      el.hidden = !text;
    }
    document.getElementById('vo-rare').hidden = !voSaid('why_rare');
    // Whichever month the data's headline is, the card's tables say so. Freddie Mac's column has its own month-end file, so it says so itself.
    const issued = meta.month ? `, loans issued in ${monthYear(meta.month)}${meta.final === false ? ' so far' : ''}` : '';
    document.getElementById('vo-lender-h').textContent = `By lender, Fannie Mae${issued}`;
    document.getElementById('vo-band-h').textContent = `Shows VS4 only, at most, by VS4 score, Fannie Mae${issued}`;
    // Fannie Mae first, then Freddie Mac beside it, labelled.
    const tops = document.getElementById('vo-gse');
    tops.classList.toggle('dash-skeleton', st === 'loading');
    tops.replaceChildren(...gse.map((r) => {
      const c = node('div');
      c.append(node('div', 'vx-lbl', r.label), node('div', 'nc-v', r.number), node('div', 'nc-d', r.tag ? `${r.what}. ${r.tag}` : r.what));
      return c;
    }));
    // Where a figure in the pull-to-loan line came from.
    const sources = document.getElementById('vo-pull-from');
    sources.replaceChildren(...voOf('funnel').filter((r) => r.url && voSaid('pull')).flatMap((r, i) => {
      const a = node('a', 'vx-link', r.source || 'Source');
      a.href = r.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      return i ? [', ', a] : ['Sources: ', a];
    }));
    // By week: with and without the one lender, and Freddie Mac beside them.
    const fn = voOf('week').filter((r) => r.agency === 'FNMA'), fh = voOf('week').filter((r) => r.agency === 'FHLMC');
    legend(document.getElementById('vo-week-legend'), !fn.length && !fh.length ? [] : [...(fn.concat(fh).some((r) => r.first) ? [['var(--cds-chart-muted)', voSaid('first') || 'First week most loans could show both scores', 'box']] : []), [vsOnly(), 'Weeks after it', 'box'],
      ...(fn.concat(fh).some((r) => r.partial) ? [[`color-mix(in srgb, ${vsOnly()} ${OPEN * 100}%, transparent)`, 'Fainter: week not over', 'box']] : [])]);
    document.getElementById('vo-week-ex-h').textContent = `Fannie Mae, without ${lead}`;
    document.getElementById('vo-week-ex').parentElement.hidden = noLead;  // with no lender set apart, this chart would repeat the one beside it
    const tag = document.getElementById('vo-fh-tag');
    tag.textContent = freddie.tag || meta.fh_tag || '';
    tag.hidden = !tag.textContent;
    const tip = (f, n, part) => (r) => [`Week of ${r.label}${r.partial ? ', so far' : ''}`, [[null, 'Shows VS4 only, at most', int(f(r))], [null, 'Loans that could show both scores', int(n(r))], [null, 'Share of those loans', d3.format('.2%')(part(r))]]];
    voBars(document.getElementById('vo-week-fn'), st, fn, (r) => r.vo, 'Fannie Mae, loans a week that show VS4 and no FICO', tip((r) => r.vo, (r) => r.n, (r) => r.share));
    if (!noLead) voBars(document.getElementById('vo-week-ex'), st, fn, (r) => r.vo_without, `Fannie Mae without ${lead}, loans a week that show VS4 and no FICO`, tip((r) => r.vo_without, (r) => r.n - r.n_lead, (r) => r.share_without));
    voBars(document.getElementById('vo-week-fh'), st, fh, (r) => r.vo, 'Freddie Mac, loans a week that show VS4 and no FICO', tip((r) => r.vo, (r) => r.n, (r) => r.share));
    const notes = document.getElementById('vo-notes');
    notes.classList.toggle('dash-skeleton', st === 'loading');
    notes.replaceChildren(...['weeks', 'trend', 'freddie', 'ties'].map(voSaid).filter(Boolean).map((text) => node('li', null, text)));
    // By lender. A row that is one lender opens it on FHFA adoption.
    const lenders = document.getElementById('vo-lenders');
    lenders.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    lenders.tHead.rows[0].cells[6].textContent = `Freddie Mac: shows VS4 only, share of its loans${meta.final_fh === false ? ' so far' : ''}`;
    const openable = new Set(rowsOf('sellers').map((s) => s.id));
    const pctOr = (v) => (v == null ? '—' : pct1(v));
    const lbody = lenders.tBodies[0];
    lbody.replaceChildren();
    for (const r of voOf('lender')) {
      const tr = lbody.insertRow();
      if (r.total) tr.className = 'lm-all';
      if (r.total || r.rest) tr.dataset.pin = '';
      if (openable.has(r.id)) {
        tr.dataset.key = r.id;
        tr.tabIndex = 0;
      }
      [[r.short, 'vx-l vx-name'], [int(r.fn_n), 'vx-opt'], [int(r.fn_priced), 'vx-opt'], [int(r.fn_vo)], [pctOr(r.fn_own_share)], [pctOr(r.fn_fico_share), 'vx-opt'], [pctOr(r.fh_own_share)]].forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
    }
    // By VS4 score, in counts, the one lender's part fainter.
    const bands = voOf('band'), most = d3.max(bands, (r) => r.vo) || 1;
    const faint = `color-mix(in srgb, ${vsOnly()} 40%, transparent)`;
    legend(document.getElementById('vo-band-legend'), bands.length && !noLead ? [[vsOnly(), `Without ${lead}`, 'box'], [faint, lead, 'box']] : []);
    const btable = document.getElementById('vo-bands');
    btable.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    btable.tHead.rows[0].cells[3].textContent = `Without ${lead}`;
    btable.tHead.rows[0].cells[3].hidden = noLead;
    const bbody = btable.tBodies[0];
    bbody.replaceChildren();
    for (const r of bands) {
      const tr = bbody.insertRow();
      const name = tr.insertCell();
      name.className = 'vx-l';
      name.textContent = String(r.label).replace(/(\d)-(\d)/, '$1–$2');
      const bar = node('div', 'lm-bar');
      [[r.vo_without, vsOnly()], [r.vo_lead, faint]].forEach(([v, color]) => {
        const seg = node('span');
        seg.style.width = `${(v / most) * 100}%`;
        seg.style.background = color;
        bar.append(seg);
      });
      const cell = tr.insertCell();
      cell.className = 'vx-l';
      cell.append(bar);
      for (const v of [r.vo, r.vo_without, r.vo_fthb]) tr.insertCell().textContent = int(v);
      tr.cells[3].hidden = noLead;
    }
  }

  // ---- Where every lender stands ----
  function drawMap(p) {
    const box = document.getElementById('map-chart');
    if (!box) return;
    const st = statusOf('lender_stage');
    const kinds = [['Nonbank', col(0)], ['Bank', col(1)], ['Other', 'var(--cds-chart-muted)']];
    legend(document.getElementById('map-legend'), kinds.map(([k, c]) => [c, k === 'Other' ? 'Builder, credit union or housing agency' : k, 'box']));
    if (!prep(box, st)) return;
    const pre = { All: 'mix', FNMA: 'fnma', FHLMC: 'fhlmc' }[p.agency];
    const nf = { All: 'loans', FNMA: 'fnma_loans', FHLMC: 'fhlmc_loans' }[p.agency];
    const data = rowsOf('lender_stage').filter((r) => r.view === 'lender' && r[`${pre}_fico_only`] != null).map((r) => ({
      id: r.id, name: olName(r), short: r.short, kind: r.kind, n: r[nf], priced: r[`${pre}_both_vs`] + r[`${pre}_vs_only`], carrying: r[`${pre}_both_fico`] + r[`${pre}_both_vs`] + r[`${pre}_vs_only`], only: r[`${pre}_vs_only`],
    })).sort((a, b) => b.n - a.n);
    if (!data.length) return;
    const W = box.clientWidth, H = Math.max(320, Math.min(480, W * 0.55)), m = { top: 14, right: 18, bottom: 40, left: 50 };
    const svg = svgFor(box, W, H, 'Every lender by the share of its loans carrying VS4 and the share priced on VS4');
    const topY = Math.min(1, Math.max(0.5, (d3.max(data, (d) => d.priced) || 0) + 0.14));
    const x = d3.scaleLinear([-0.035, 1.02], [m.left, W - m.right]);
    const y = d3.scaleLinear([-0.05, topY], [H - m.bottom, m.top]);
    const r = d3.scaleSqrt([0, d3.max(data, (d) => d.n)], [2.5, Math.min(24, W / 30)]);
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      svg.append('line').attr('x1', x(t)).attr('x2', x(t)).attr('y1', y(-0.05)).attr('y2', y(topY)).attr('stroke', 'var(--cds-chart-grid)');
      svg.append('text').attr('x', x(t)).attr('y', H - m.bottom + 16).attr('text-anchor', 'middle').text(pct0(t));
      if (t <= topY) {
        svg.append('line').attr('x1', x(-0.035)).attr('x2', x(1.02)).attr('y1', y(t)).attr('y2', y(t)).attr('stroke', 'var(--cds-chart-grid)');
        svg.append('text').attr('x', m.left - 6).attr('y', y(t)).attr('dy', '0.32em').attr('text-anchor', 'end').text(pct0(t));
      }
    }
    svg.append('text').attr('x', (x(0) + x(1)) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text(W < 260 ? 'Loans showing VS4, a floor' : 'Share of its loans showing VS4, a floor');
    svg.append('text').attr('transform', `translate(11,${(y(0) + y(topY)) / 2}) rotate(-90)`).attr('text-anchor', 'middle').text('Share priced on VS4');
    svg.append('line').attr('x1', x(0)).attr('y1', y(0)).attr('x2', x(topY)).attr('y2', y(topY)).attr('stroke', 'var(--cds-chart-reference)');
    const taken = [];
    const zone = (text, zx, zy, anchor) => {
      const t = svg.append('text').attr('x', zx).attr('y', zy).attr('text-anchor', anchor).text(text);
      const w = t.node().getComputedTextLength();
      taken.push({ x: anchor === 'end' ? zx - w : zx, y: zy - 12, w, h: 16 });
    };
    if (W >= 520) {
      zone('Priced on VS4 whenever it shows', x(topY) - 34, y(topY) + 12, 'end');
      zone('Shows VS4, rarely priced on it', x(0.84), y(0.1), 'end');
      zone('Shows FICO only', x(0.01), y(0.01 + 110 / (x(1) - x(0))), 'start');
    }
    const drawn = data.slice().reverse();
    svg.append('g').selectAll('circle').data(drawn).join('circle').attr('cx', (d) => x(d.carrying)).attr('cy', (d) => y(d.priced)).attr('r', (d) => r(d.n))
      .attr('fill', (d) => (kinds.find((k) => k[0] === d.kind) || kinds[2])[1]).attr('fill-opacity', 0.8).attr('stroke', 'var(--color-panel)').attr('stroke-width', 1.5);
    // Name the lenders away from the crowd at the origin, largest first, wherever the name fits and clears every bubble.
    for (const d of data) {
      const rad = r(d.n);
      taken.push({ x: x(d.carrying) - rad, y: y(d.priced) - rad, w: 2 * rad, h: 2 * rad });
    }
    const clears = (b, self) => !taken.some((t) => t !== self && b.x < t.x + t.w && b.x + b.w > t.x && b.y < t.y + t.h && b.y + b.h > t.y);
    const named = data.filter((d) => d.carrying >= 0.12 || d.priced >= 0.03);
    for (const d of named.slice(0, W < 520 ? 7 : 14)) {
      const cx = x(d.carrying), cy = y(d.priced), rad = r(d.n);
      const probe = svg.append('text').text(d.short);
      const w = probe.node().getComputedTextLength();
      const spots = [[cx + rad + 4, cy + 4, 'start'], [cx - rad - 4 - w, cy + 4, 'start'], [cx - w / 2, cy - rad - 4, 'start'], [cx - w / 2, cy + rad + 12, 'start']];
      const self = taken.find((t) => t.x === cx - rad && t.y === cy - rad);
      const spot = spots.find(([sx, sy]) => sx >= m.left && sx + w <= W - 2 && sy - 12 >= 0 && sy <= H - m.bottom - 2 && clears({ x: sx, y: sy - 11, w, h: 14 }, self));
      if (spot) {
        probe.attr('x', spot[0]).attr('y', spot[1]).style('fill', 'var(--color-fg)');
        taken.push({ x: spot[0] - 6, y: spot[1] - 11, w: w + 12, h: 14 });
      } else {
        probe.remove();
      }
    }
    const tip = tooltip(box);
    const openable = new Set(rowsOf('sellers').map((s) => s.id));
    const near = d3.Delaunay.from(data, (d) => x(d.carrying), (d) => y(d.priced));
    const pick = (event) => {
      const [mx, my] = d3.pointer(event, svg.node());
      const d = data[near.find(mx, my)];
      return Math.hypot(x(d.carrying) - mx, y(d.priced) - my) <= Math.max(24, r(d.n) + 6) ? d : null;
    };
    svg.append('rect').attr('x', m.left).attr('y', m.top).attr('width', W - m.left - m.right).attr('height', H - m.top - m.bottom).attr('fill', 'transparent')
      .on('pointermove', (event) => {
        const d = pick(event);
        event.currentTarget.style.cursor = d && openable.has(d.id) ? 'pointer' : null;
        if (!d) return tip.hide();
        tip.show(event, d.name, [[null, 'Carrying VS4', pct1(d.carrying)], [null, 'Priced on VS4', pct1(d.priced)], [null, 'Shows VS4 only, at most', pct1(d.only)], [null, 'Loans', int(d.n)]]);
      })
      .on('pointerleave', () => tip.hide())
      .on('click', (event) => {
        const d = pick(event);
        if (d && openable.has(d.id)) openSeller(d.id);
      });
  }

  // ---- How lenders decide ----
  const SCORE_BANDS = [['down20', '20+ lower'], ['down1', '1–19 lower'], ['equal', 'Same'], ['up1', '1–19 higher'], ['up20', '20+ higher']];
  const FEES = [['higher', 'Higher'], ['same', 'Same'], ['lower', 'Lower']];
  // Shading only, to show what each motive would look like: share of the darkest shade by column, score bands then fee.
  const PATTERNS = [['Wanted the cheapest score', [1, 1, 1, 1, 1, 1, 1, 1]], ['Wanted the lowest fee', [0, 0, 0, 0.5, 0.5, 0, 0, 1]], ['Wanted the higher score', [0, 0, 0.3, 1, 1, 0, 0.5, 1]]];

  function heatCell(tr, v, text) {
    const td = tr.insertCell();
    td.className = 'dc-cell';
    td.textContent = text;
    if (v != null) {
      const fill = `color-mix(in srgb, ${col(0)} ${Math.round(v * 100)}%, transparent)`;
      td.style.background = fill;
      td.style.color = inkOn(fill);
    }
  }

  function drawDecide(p) {
    const table = document.getElementById('decide-table');
    if (!table) return;
    const st = dash.data('fees').status;
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const rows = rowsOf('fees').filter((r) => r.view === 'choice' && r.cohort === p.ccohort);
    const scopes = [...new Map(rows.slice().sort((a, b) => a.scope_rank - b.scope_rank).map((r) => [r.scope, r.scope_label])).entries()]
      .filter(([s]) => rows.filter((r) => r.scope === s && r.loans >= CELL_MIN).length >= 4);
    const head = table.tHead;
    head.replaceChildren();
    const h1 = head.insertRow();
    const blank = node('th', 'vx-l');
    h1.append(blank);
    const a = node('th', 'dc-group', "VS4's score against FICO's");
    a.colSpan = SCORE_BANDS.length;
    const b = node('th', 'dc-group', "VS4's fee against FICO's");
    b.colSpan = FEES.length;
    h1.append(a, b);
    const h2 = head.insertRow();
    h2.append(node('th', 'vx-l', 'Share priced on VS4'), ...SCORE_BANDS.map(([, l]) => node('th', 'dc-head', l)), ...FEES.map(([, l]) => node('th', 'dc-head', l)));
    const body = table.tBodies[0];
    body.replaceChildren();
    const share = (scope, keys) => {
      const use = rows.filter((r) => r.scope === scope && keys.includes(r.key));
      const n = d3.sum(use, (r) => r.loans);
      return n >= CELL_MIN ? d3.sum(use, (r) => r.vs4_share * r.loans) / n : null;
    };
    for (const [scope, label] of scopes) {
      const tr = body.insertRow();
      const c = tr.insertCell();
      c.className = 'vx-l';
      c.textContent = label;
      for (const [band] of SCORE_BANDS) {
        const v = share(scope, ['lower', 'same', 'higher'].map((o) => `${o}|${band}`));
        heatCell(tr, v, v == null ? '—' : pct0(v));
      }
      for (const [fee] of FEES) {
        const v = share(scope, [`${fee}|all`]);
        heatCell(tr, v, v == null ? '—' : pct0(v));
      }
    }
    const sep = body.insertRow();
    const cap = sep.insertCell();
    cap.colSpan = 1 + SCORE_BANDS.length + FEES.length;
    cap.className = 'vx-l dc-cap';
    cap.textContent = 'What each motive would look like';
    for (const [label, shades] of PATTERNS) {
      const tr = body.insertRow();
      const c = tr.insertCell();
      c.className = 'vx-l';
      c.textContent = label;
      shades.forEach((v) => heatCell(tr, v, ''));
    }
  }

  // ---- Words ----
  const TERMS = [
    ['gse', 'GSE', 'Fannie Mae or Freddie Mac. This site covers loans they put into mortgage-backed securities.'],
    ['vs4', 'VS4', 'VantageScore 4.0, the credit score the GSEs began accepting alongside Classic FICO.'],
    ['priced', 'Priced on VS4', 'VS4 was the score that set the loan\'s LLPA. On records from Oct 19, 2026, which reach back to loans first disclosed in late September, the GSEs state this; before that it comes from the one score shown.'],
    ['carrying', 'Carrying VS4', 'The loan shows a VS4 score, whichever score priced it. A lender can carry VS4 and still price on FICO. The share is a floor: a loan can have a VS4 that does not show.'],
    ['both', 'Both scores', 'The GSE file shows both a Classic FICO and a VS4 on the loan. One of them priced it.'],
    ['only', 'Shows VS4 only, at most', 'The file shows a VS4 and no Classic FICO, and the same way round for shows FICO only. That does not mean the other score was never pulled: lenders deliver one score, and at Freddie Mac some lenders\' loans often show only the one that priced them. So the share is the most it can be: loans that really have only that score are at most this many. A thin-file borrower may have had no FICO to buy, and a lender can cut FICO pulls early and still show a FICO at funding.'],
    ['floor', 'Floor, ceiling, exact', 'A score that does not show is unknown, not absent. So the share showing a score is a floor on loans that have it: the true share is at least this. The share showing only one score is a ceiling on loans that have only that one: the true share is at most this. The share priced on VS4 is exact: the GSEs state it on records with the Pricing Indicator, and before that the one score shown names it.'],
    ['every', 'Records that show every score', 'Since Oct 19, 2026 the GSE files show every score the GSE has on a loan and which one priced it. Before that they showed only the score that priced the loan, so older bars are a floor.'],
    ['frozen', 'Lender mix frozen', 'Each week different lenders deliver different amounts. Freezing the mix gives each lender a fixed weight, its share of all the weeks shown, so only changes in what lenders do can move the number.'],
    ['llpa', 'LLPA', 'The GSEs\' upfront charge on a loan, by its credit score, LTV and purpose. It has been one grid for both scores since Oct 1, 2026, and that grid matches Fannie Mae\'s matrix of Sep 30, 2026.'],
    ['fee', 'Upfront fee', 'The same charge as the LLPA, under the name some tabs still use.'],
    ['rule', 'A lender\'s rule', 'When it chooses VS4. A 20-point rule means using VS4 only when its score beats FICO by 20 or more points, which matched the LLPA grid before Oct 1, 2026.'],
    ['stage', 'Stage', 'How far a lender has gone: FICO only, a few VS4 loans, both scores shown, using VS4 some of the time, or most of the time its score is higher.'],
    ['channel', 'Channel', 'How the lender got the loan: retail (its own), broker, or correspondent (bought from another lender).'],
    ['week', 'By week', 'Loans by the week they first appeared in the GSEs\' intraday files, ahead of the month their pool is issued.'],
    ['issue', 'Issue month', 'The month the loan\'s mortgage-backed security was issued. The latest month is partial until its month-end file arrives.'],
    ['closing', 'Closing month', 'The month the loan closed, as near as the files allow: its first payment month less two. A recent month is still arriving, so a label such as "60% in" estimates how much of it has come through so far.'],
    ['lender', 'Lender', 'The company that delivered the loan to the GSE. It is not always the one that made the loan.'],
    ['bp', 'bp', 'Basis point, a hundredth of a percentage point. A pt is a full percentage point.'],
    ['note', 'Note rate', 'The interest rate written on the loan. Discount points and lender credits sit outside it, and these files do not show them.'],
    ['samefico', 'Same FICO', 'A VS4 loan that shows a FICO, set against FICO loans at that FICO, with the lender, channel, timing, GSE, purpose and LTV held equal.'],
    ['samenumber', 'Same score number', 'A VS4 loan\'s VS4 number, set against FICO loans whose FICO is that same number, with the same things held equal. The loan need not show a FICO.'],
    ['vs4loan', 'VS4 loan', 'A loan priced on VS4: the Pricing Indicator says so or, on records before the indicator, VS4 is the only score shown.'],
    ['ficoloan', 'FICO loan', 'A loan priced on Classic FICO. It may also carry a VS4.'],
    ['oldrule', 'The old rule', 'For MBS issued before Oct 1, 2026, the LLPA grid counted a VS4 score as 20 points lower. From Oct 1 both scores use one grid.'],
    ['switchpoint', 'Switch point', 'The point where a lender moves from FICO to VS4, by how far VS4 sits above FICO.'],
    ['dates', 'The dates', 'In order: rate set (not disclosed), loan closes, first disclosed in a GSE file, issued into an MBS.'],
    ['range95', '95% range', 'An approximate range for the estimate, from resampling lender and channel groups, or weeks inside them on Which FICO. At the switch point it comes from that fit\'s own error. Ends in the text are rounded outward. It does not cover points, credits or lock dates.'],
    ['lenderweek', 'Lender-week', 'One lender\'s loans first disclosed in one week. Figures on under 8 of them are marked rough, outlined or hollow.'],
    ['thin', 'Rough', 'A figure resting on few lender-weeks, one lender\'s loans in one week, with at least 5 loans.'],
    ['methods', 'The 3 methods', 'Exact match with a 5-point score band sets each VS4 loan against FICO loans with the same lender, channel, timing, GSE, purpose and LTV range, in the same 5-point score band. Exact match with one LLPA tier does the same with one LLPA tier as the band (20 points under 640), so more loans find a match. A model fitted on FICO loans gives each VS4 loan the rate it predicts at that score, controlling for loan traits too. On the charts, the estimate is the midpoint of the two exact matches and the range spans all three.'],
    ['hmda', 'HMDA', 'The Home Mortgage Disclosure Act record: a yearly federal filing by nearly every mortgage lender, covering each application whatever became of it. It names the score model the lender relied on for the credit decision.'],
    ['fullsignal', 'Would reach 830 if all on VS4', 'How many of a group of VA loans would reach 830 if every loan showed VS4, from the odds at each Classic score on Fannie loans showing both scores. It sizes what a full move would look like at the top of the score range.'],
    ['abs15g', 'Form ABS-15G', 'Where a mortgage deal to be rated, registered or not, files its due diligence findings with the SEC, at least five business days before first sale. Some of these reports list each loan and the score model on it.'],
    ['classic', 'Classic FICO', 'The older FICO versions the GSEs have long required: Equifax Beacon 5.0, Experian Fair Isaac v2 and TransUnion FICO Classic 04 or 98.'],
    ['ficonew', 'Newer FICO', 'FICO 8, FICO 9, FICO 10 and FICO 10T. Still FICO, but not the versions the GSEs have long required.'],
    ['unnamed', 'Model not named', 'The lender said it relied on more than one model, or on another model, without saying which. It could be FICO or VantageScore, so it counts as neither.'],
    ['firstlien', 'First-lien', 'The loan with first claim on the home. Lines of credit and second liens count apart as home equity, and multifamily and reverse mortgages are left out.'],
    ['othconf', 'Other conforming size', 'Loans under the conforming limit that are not FHA, VA, USDA or business purpose and do not reach Fannie or Freddie: bank and credit union portfolio loans, private label and others. It is what is left of HMDA\'s conforming-size rows after the GSEs\' own count, so it is an estimate.'],
    ['follow', 'If FHA and VA follow', 'An assumption: FHA and VA reach the same level of VS4 only as the GSEs. No file can show VS4 only on FHA or VA.'],
    ['noscore', 'No score reported', 'The lender marked the field not applicable, or it is exempt from reporting it. Some loans, such as streamlined refinances, may use no score at all. It does not mean FICO.'],
  ];
  const termOf = new Map(TERMS.map((t) => [t[0], t]));

  function drawGlossary() {
    const box = document.getElementById('glossary');
    if (!box || box.childElementCount) return;
    box.append(...TERMS.map(([, term, text]) => {
      const div = node('div', 'gl-item');
      div.append(node('dt', null, term), node('dd', null, text));
      return div;
    }));
  }

  // A term on the page opens its definition on hover, focus or tap.
  const pop = node('div', 'vx-pop');
  pop.hidden = true;
  root.append(pop);
  let popFor = null;
  const hidePop = () => {
    pop.hidden = true;
    popFor = null;
  };
  const showPop = (el) => {
    const t = termOf.get(el.dataset.term);
    if (!t) return;
    popFor = el;
    pop.replaceChildren(node('b', null, t[1]), document.createTextNode(` ${t[2]}`));
    pop.hidden = false;
    const hostBox = root.getBoundingClientRect(), box = el.getBoundingClientRect();
    const left = Math.max(0, Math.min(box.left - hostBox.left, hostBox.width - pop.offsetWidth - 4));
    pop.style.left = `${left}px`;
    // It opens above its term where below would leave the viewport and above would not.
    const h = pop.offsetHeight, up = box.bottom + 6 + h > innerHeight && box.top - 6 - h >= 0;
    pop.style.top = `${up ? box.top - hostBox.top - h - 6 : box.bottom - hostBox.top + 6}px`;
  };
  root.addEventListener('pointerover', (event) => {
    const dragged = event.pointerType === 'mouse' && event.buttons;  // a mouse drag selects, so it opens nothing, and one that began on the definition keeps it
    const el = event.target.closest('[data-term]');
    if (el) { if (!dragged) showPop(el); }
    else if (popFor && !(dragged ? pop.contains(getSelection().anchorNode) : event.target.closest('.vx-pop'))) hidePop();  // a pointer on the definition, or crossing the gap to it, keeps it, to read; a drag keeps it only if it began on it
  });
  root.addEventListener('focusin', (event) => {
    const el = event.target.closest('[data-term]');
    if (el) showPop(el);
  });
  root.addEventListener('focusout', (event) => {
    if (event.target.closest('[data-term]') && !pop.matches(':hover')) hidePop();  // a press on the definition takes the focus from its term and keeps it
  });
  // A mouse leaving the page closes it, unless its term has the focus. A tap has no pointer left to leave.
  root.addEventListener('pointerleave', (event) => {
    if (popFor && event.pointerType !== 'touch' && document.activeElement !== popFor) hidePop();
  });
  document.addEventListener('keydown', (event) => {  // on the document, as a term under a mouse has no focus
    if (event.key === 'Escape' && popFor) hidePop();
  });
  root.addEventListener('click', (event) => {
    const el = event.target.closest('[data-term]');
    if (el) return showPop(el);
    if (popFor && !(event.target.closest('.vx-pop') && String(getSelection()))) hidePop();  // a tap on it closes it, as anywhere; a drag that selected its words does not
    const go = event.target.closest('[data-go]');
    if (go && !(go.classList.contains('fr') && event.detail && String(getSelection()))) {  // a drag across a row's words selects them and opens nothing. A link reads as a link, so Back comes back here, whether or not a host's setLink moves this frame's URL. A host can refuse the entries.
      try {
        history.replaceState({ tab: root.querySelector('.vx-tabs [aria-selected="true"]').dataset.tab }, '', location.href);
        history.pushState({ tab: go.dataset.go }, '', location.href);
      } catch {}
      show(go.dataset.go);
      window.scrollTo(0, 0);
      const goTab = document.getElementById(`tab-${go.dataset.go}`);  // the keyboard goes on from the tab it landed on, not from the top of the page
      const goCard = go.dataset.at && document.getElementById(go.dataset.at);  // or from the card a row lands on
      if (goCard) goCard.focus({ preventScroll: true });
      else if (goTab) goTab.focus({ preventScroll: true });
      landing = go.dataset.at || null;  // a row can open its tab at one card
      land();
    }
    const more = event.target.closest('.vx-more-note');
    if (more) {
      const note = more.previousElementSibling;
      const open = note.classList.toggle('vx-clamp');
      more.textContent = open ? 'More' : 'Less';
    }
    const all = event.target.closest('.vx-show');
    if (all) {
      const box = all.previousElementSibling, showing = box.dataset.all === '1';
      box.dataset.all = showing ? '' : '1';
      capRows(box.querySelector('table'));
      if (showing) all.scrollIntoView({ block: 'end' });
    }
  });

  // The tab's data may still be on its way, and the card moves down as it arrives, so the page lands again until nothing shown is waiting, or the reader moves first.
  let landing = null;
  function land() {
    const at = landing && document.getElementById(landing);
    if (!at) return;
    at.scrollIntoView({ block: 'start' });
    if (![...root.querySelectorAll('.vx-panel:not([hidden]) .dash-skeleton')].some((e) => e.getClientRects().length)) landing = null;
  }
  for (const type of ['wheel', 'touchstart', 'pointerdown', 'keydown']) window.addEventListener(type, () => { landing = null; }, { passive: true, capture: true });
  root.addEventListener('keydown', (event) => {  // a row on the first screen opens by Enter, as a link does
    if (event.key === 'Enter' && event.target.matches('.fr[data-go]')) event.target.click();
  });

  // Long notes show two lines, with the rest a tap away. A More costs a line, so a note that would hide only one line shows in full.
  // A note's text can change with a toggle, so each draw measures it again, once its numbers have arrived.
  function clampNote(note) {
    if (note.dataset.clamp === '0' || !note.offsetParent || [...note.querySelectorAll('[data-source]')].some((s) => s.textContent.trim() === '—')) return;
    const next = note.nextElementSibling;
    const more = next && next.classList.contains('vx-more-note') ? next : null;
    const open = !!more && more.textContent === 'Less';
    note.classList.add('vx-clamp');
    const long = note.scrollHeight - note.clientHeight > (parseFloat(getComputedStyle(note).lineHeight) || 18) + 2;
    note.classList.toggle('vx-clamp', long && !open);
    if (!long && more) more.remove();
    if (long && !more) {
      const link = node('button', 'vx-more-note', 'More');
      link.type = 'button';
      note.after(link);
    }
  }

  // A long table shows its first rows, plus any row pinned to stay, and a button for the rest, so no row is cut at the edge of a box. The choice sits on the box, so it survives a redraw.
  const ROWS_WHOLE = 18, ROWS_FIRST = 15;
  function capRows(table) {
    const box = table.closest('.vx-tablebox'), rows = [...table.tBodies[0].rows];
    const long = rows.length > ROWS_WHOLE, showing = box.dataset.all === '1';
    rows.forEach((r, i) => { r.hidden = long && !showing && i >= ROWS_FIRST && !('pin' in r.dataset); });
    // A table wider than its box has to scroll sideways, and on a phone says so once more than a cell's padding is cut. One that fits can let go of the scroll, so its header sticks to the page once all its rows show. A box out of sight keeps its last reading.
    const over = box.scrollWidth - box.clientWidth;
    if (box.clientWidth) {
      box.classList.toggle('vx-sideways', over > 1);
      box.classList.toggle('vx-swipe', over > 8);
    }
    let btn = box.nextElementSibling;
    if (!btn || !btn.classList.contains('vx-show')) {
      if (!long) return;
      btn = node('button', 'vx-show');
      btn.type = 'button';
      box.after(btn);
    }
    btn.hidden = !long;
    btn.textContent = showing ? 'Show fewer' : `Show all ${int(rows.length)}`;
  }
  // A sort, a filter or a preset redraws one table without a full draw.
  const rowWatch = new MutationObserver((changes) => new Set(changes.map((c) => c.target.closest('table'))).forEach((table) => capRows(table)));

  function tidy() {
    root.querySelectorAll('[data-term]:not([tabindex])').forEach((el) => {
      el.tabIndex = 0;
      el.classList.add('vx-term');
    });
    root.querySelectorAll('.vx-panel:not([hidden]) .vx-note, .vx-panel:not([hidden]) .vx-sec-h > p').forEach((note) => clampNote(note));
    root.querySelectorAll('.vx-table').forEach((table) => {
      capRows(table);
      rowWatch.observe(table.tBodies[0], { childList: true });
    });
  }

  vx.hooks.overview.push(drawFront, drawWaffles, drawWho, drawFrozen);
  vx.hooks.outlook.push(drawVoCard);
  vx.hooks.pricing.push(drawFrontLlpa);
  vx.hooks.scores.push(drawMap, drawDecide);
  vx.hooks.method.push(drawGlossary);
  vx.after.push(drawFrontLine, tidy, land);
  vx.redraw();
})();
