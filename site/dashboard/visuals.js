// The visual summaries: out of every 100 loans, why the weeks jump, how far VS4 could go, where every lender stands,
// how lenders decide, where the fee saving goes, plus plain-word definitions of the terms the page uses.
// Runs after the main script and tools.js; what they share is on window.vx.
(() => {
  const vx = window.vx;
  const { root, rowsOf, statusOf, int, pct1, olName, openSeller, shortDay, prep, svgFor, bandFrame, yAxis, bandAxis, bandHover, legend, tooltip, textWidth, MIX_GROUPS, AG_NAME, show, col } = vx;
  const pct0 = d3.format('.0%');
  const one = d3.format('.1f');
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
        li.append(sw, node('b', null, pct1(shares[i])), `${group(g)[1]}${g === 'fico_only' || g === 'vs_only' ? ', a ceiling' : ''}`);
        list.append(li);
      });
      const sum = (label, v) => {
        const li = node('li', 'wf-sum');
        li.append(node('b', null, pct1(v)), label);
        return li;
      };
      list.append(sum('show Classic FICO, a floor', r[`fico${k}_share`] || 0), sum('show VS4, a floor', r[`vs${k}_share`] || 0), sum('are priced on VS4, exact', r[`vs4_priced${k}_share`] || 0));
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
    const st = statusOf('lender_mix', 'score_mix');
    const weeks = rowsOf('score_mix').filter((r) => r.view === 'week' && r.agency === p.agency).sort(asc('start'));
    const top = topUsers();
    const names = new Map(rowsOf('lender_stage').filter((r) => r.view === 'lender').map((r) => [r.id, r.short]));
    const label = top.map((id) => names.get(id) || id).join(' and ');
    const note = document.getElementById('who-note');
    note.textContent = top.length ? `${label}'s share of each week's loans. When they deliver more, the market number jumps, even if no lender changed what it does.` : '';
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
      svg.append('path').attr('d', capped(x(d.key) + off, y(d.v), bw, h)).attr('fill', 'var(--cds-chart-muted)');
      svg.append('text').attr('x', x(d.key) + x.bandwidth() / 2).attr('y', y(d.v) - 4).attr('text-anchor', 'middle').text(pct0(d.v));
      svg.append('text').attr('x', x(d.key) + x.bandwidth() / 2).attr('y', H - 6).attr('text-anchor', 'middle').text(shortDay(d.key));
    }
    bandHover(svg, box, x, data, 'key', m, H, (d) => [`Week of ${shortDay(d.key)}, ${int(d.loans)} loans`, [['var(--cds-chart-muted)', label, pct1(d.v)]]]);
  }

  function drawFrozen(p) {
    const box = document.getElementById('frozen-chart');
    if (!box) return;
    const st = dash.data('score_mix').status;
    const priced = col(0), onFico = group('both_fico')[2];
    const ghost = 'color-mix(in srgb, var(--color-fg) 13%, transparent)';
    legend(document.getElementById('frozen-legend'), [[priced, 'Priced on VS4', 'box'], [onFico, 'Carrying VS4, priced on FICO', 'box'], [ghost, 'As delivered', 'box']]);
    if (!prep(box, st)) return;
    const weeks = rowsOf('score_mix').filter((r) => r.view === 'week' && r.agency === p.agency && r.steady_carrying != null).sort(asc('start'));
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
      svg.append('rect').attr('x', bx).attr('width', bw).attr('y', y(low)).attr('height', lowH).attr('fill', priced);
      const upH = Math.max(0, y(low) - y(topV) - 2);
      svg.append('path').attr('d', capped(bx, y(topV), bw, upH)).attr('fill', onFico);
      svg.append('text').attr('x', bx + bw / 2).attr('y', y(topV) - 4).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text(pct0(topV));
      svg.append('text').attr('x', bx + bw / 2).attr('y', H - 6).attr('text-anchor', 'middle').text(shortDay(r.start));
    }
    bandHover(svg, box, x, weeks, 'start', m, H, (r) => [`Week of ${shortDay(r.start)}`, [[onFico, 'Carrying VS4, lender mix frozen', pct1(r.steady_carrying)], [priced, 'Priced on VS4, lender mix frozen', pct1(r.steady_priced)],
      [ghost, 'Carrying VS4, as delivered', pct1(r.vs_share || 0)]]]);
  }

  // ---- How far could it go ----
  function drawReach() {
    const box = document.getElementById('reach-bars');
    if (!box) return;
    box.classList.toggle('dash-skeleton', statusOf('outlook') === 'loading');
    const ladder = rowsOf('outlook').filter((r) => r.view === 'ladder');
    const rung = (key, rule) => ladder.find((r) => r.key === key && (!rule || r.rule === rule));
    const items = [['Priced on VS4 today', rung('today'), true], ['Latest two weeks, lender mix frozen', rung('recent'), true], ['If every lender used VS4 wherever it saves a fee', rung('all', 'better')],
      ['... wherever its score is higher', rung('all', 'higher')], ['... wherever it is no worse', rung('not_worse')]].filter((d) => d[1]);
    box.replaceChildren(...items.map(([label, r, actual]) => {
      const row = node('div', 'hb');
      row.append(node('div', 'hb-l', label), node('div', 'hb-v', pct1(r.value)));
      const track = node('div', 'hb-t');
      const fill = node('span');
      fill.style.width = `${Math.min(100, r.value * 100)}%`;
      fill.style.background = actual ? col(0) : `color-mix(in srgb, ${col(0)} 40%, transparent)`;
      track.append(fill);
      row.append(track);
      return row;
    }));
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
    const W = box.clientWidth, H = Math.max(320, Math.min(480, W * 0.55)), m = { top: 14, right: 18, bottom: 40, left: 46 };
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
    svg.append('text').attr('x', (x(0) + x(1)) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text('Share of its loans showing VS4, a floor');
    svg.append('text').attr('transform', `translate(11,${(y(0) + y(topY)) / 2}) rotate(-90)`).attr('text-anchor', 'middle').text('Share priced on VS4');
    svg.append('line').attr('x1', x(0)).attr('y1', y(0)).attr('x2', x(topY)).attr('y2', y(topY)).attr('stroke', 'var(--cds-chart-reference)');
    const taken = [];
    const zone = (text, zx, zy, anchor) => {
      const t = svg.append('text').attr('x', zx).attr('y', zy).attr('text-anchor', anchor).text(text);
      const w = t.node().getComputedTextLength();
      taken.push({ x: anchor === 'end' ? zx - w : zx, y: zy - 12, w, h: 16 });
    };
    if (W >= 520) {
      zone('Priced on VS4 whenever it shows', x(topY) - 8, y(topY) + 12, 'end');
      zone('Shows VS4, rarely priced on it', x(0.84), y(0.1), 'end');
      zone('Shows FICO only', x(0.01), y(0.1), 'start');
    }
    const drawn = data.slice().reverse();
    svg.append('g').selectAll('circle').data(drawn).join('circle').attr('cx', (d) => x(d.carrying)).attr('cy', (d) => y(d.priced)).attr('r', (d) => r(d.n))
      .attr('fill', (d) => (kinds.find((k) => k[0] === d.kind) || kinds[2])[1]).attr('fill-opacity', 0.8).attr('stroke', 'var(--color-panel)').attr('stroke-width', 1.5);
    // Name the lenders away from the crowd at the origin, largest first, wherever the name fits and clears the larger bubbles.
    for (const d of data) {
      const rad = r(d.n);
      if (rad >= 5) taken.push({ x: x(d.carrying) - rad, y: y(d.priced) - rad, w: 2 * rad, h: 2 * rad });
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
        taken.push({ x: spot[0], y: spot[1] - 11, w, h: 14 });
      } else {
        probe.remove();
      }
    }
    const tip = tooltip(box);
    const near = d3.Delaunay.from(data, (d) => x(d.carrying), (d) => y(d.priced));
    const pick = (event) => {
      const [mx, my] = d3.pointer(event, svg.node());
      const d = data[near.find(mx, my)];
      return Math.hypot(x(d.carrying) - mx, y(d.priced) - my) <= Math.max(24, r(d.n) + 6) ? d : null;
    };
    svg.append('rect').attr('x', m.left).attr('y', m.top).attr('width', W - m.left - m.right).attr('height', H - m.top - m.bottom).attr('fill', 'transparent').style('cursor', 'pointer')
      .on('pointermove', (event) => {
        const d = pick(event);
        if (!d) return tip.hide();
        tip.show(event, d.name, [[null, 'Carrying VS4', pct1(d.carrying)], [null, 'Priced on VS4', pct1(d.priced)], [null, 'Shows VS4 only', pct1(d.only)], [null, 'Loans', int(d.n)]]);
      })
      .on('pointerleave', () => tip.hide())
      .on('click', (event) => {
        const d = pick(event);
        if (d) openSeller(d.id);
      });
  }

  // ---- How lenders decide ----
  const SCORE_BANDS = [['down20', '20+ lower'], ['down1', '1-19 lower'], ['equal', 'Same'], ['up1', '1-19 higher'], ['up20', '20+ higher']];
  const FEES = [['higher', 'Higher'], ['same', 'Same'], ['lower', 'Lower']];
  // Shading only, to show what each motive would look like: share of the darkest shade by column, score bands then fee.
  const PATTERNS = [['Wanted the cheapest score', [1, 1, 1, 1, 1, 1, 1, 1]], ['Wanted the lowest fee', [0, 0, 0, 0.5, 0.5, 0, 0, 1]], ['Wanted the higher score', [0, 0, 0.3, 1, 1, 0, 0.5, 1]]];

  function heatCell(tr, v, text) {
    const td = tr.insertCell();
    td.className = 'dc-cell';
    td.textContent = text;
    if (v != null) {
      td.style.background = `color-mix(in srgb, ${col(0)} ${Math.round(v * 100)}%, transparent)`;
      if (v >= 0.6) td.style.color = '#fff';
    }
  }

  function drawDecide(p) {
    const table = document.getElementById('decide-table');
    if (!table) return;
    const st = dash.data('fees').status;
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const rows = rowsOf('fees').filter((r) => r.view === 'choice' && r.cohort === p.ccohort);
    const scopes = [...new Map(rows.slice().sort((a, b) => a.scope_rank - b.scope_rank).map((r) => [r.scope, r.scope_label])).entries()];
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

  // ---- Where the fee saving goes ----
  function drawSaving() {
    const box = document.getElementById('saving-chart');
    if (!box) return;
    const st = dash.data('pricing').status;
    const fee = 'var(--cds-chart-muted)', rate = col(0);
    legend(document.getElementById('saving-legend'), [[fee, 'Fee saved, in rate terms', 'box'], [rate, 'How much lower the note rate is', 'box']]);
    if (!prep(box, st)) return;
    const rows = rowsOf('pricing').filter((r) => r.view === 'value' && r.key === 'better' && r.n >= 300);
    const picks = rows.filter((r) => r.scope === 'All' || r.channel).sort((a, b) => a.scope_rank - b.scope_rank);
    if (!picks.length) return;
    const W = box.clientWidth, rowH = 58, m = { top: 4, right: 100, bottom: 6, left: 4 };
    const H = m.top + m.bottom + picks.length * rowH;
    const svg = svgFor(box, W, H, 'Fee saved, in rate terms, against how much lower the note rate is, by lender and channel');
    const lows = d3.min(picks, (r) => -r.net_bp - 2 * (r.se_bp || 0));
    const highs = d3.max(picks, (r) => Math.max(r.fee_rate_bp, -r.net_bp + 2 * (r.se_bp || 0)));
    const x = d3.scaleLinear([Math.min(0, lows), highs], [m.left, W - m.right]);
    const zero = x(0);
    svg.append('line').attr('x1', zero).attr('x2', zero).attr('y1', m.top).attr('y2', H - m.bottom).attr('stroke', 'var(--cds-chart-axis)');
    picks.forEach((r, i) => {
      const top = m.top + i * rowH;
      svg.append('text').attr('x', m.left).attr('y', top + 12).text(`${r.label}, ${int(r.n)} loans`).style('fill', 'var(--color-fg)');
      const feeY = top + 18, rateY = top + 32, h = 11;
      svg.append('rect').attr('x', zero).attr('y', feeY).attr('width', Math.max(0, x(r.fee_rate_bp) - zero)).attr('height', h).attr('rx', 2).attr('fill', fee);
      svg.append('text').attr('x', x(r.fee_rate_bp) + 5).attr('y', feeY + h - 1).text(`${one(r.fee_rate_bp)} bp`);
      const fall = -r.net_bp;
      const x0 = Math.min(zero, x(fall)), w = Math.abs(x(fall) - zero);
      svg.append('rect').attr('x', x0).attr('y', rateY).attr('width', Math.max(1, w)).attr('height', h).attr('rx', 2).attr('fill', rate);
      const lo = x(fall - 2 * (r.se_bp || 0)), hi = x(fall + 2 * (r.se_bp || 0));
      svg.append('line').attr('x1', lo).attr('x2', hi).attr('y1', rateY + h / 2).attr('y2', rateY + h / 2).attr('stroke', 'var(--color-fg)').attr('stroke-width', 1);
      const text = Math.abs(fall) < 0.5 ? 'about the same' : fall > 0 ? `${one(fall)} bp lower` : `${one(-fall)} bp higher`;
      svg.append('text').attr('x', Math.max(zero, x(fall), hi) + 5).attr('y', rateY + h - 1).text(text);
    });
    const tip = tooltip(box);
    svg.append('rect').attr('width', W).attr('height', H).attr('fill', 'transparent')
      .on('pointermove', (event) => {
        const [, my] = d3.pointer(event, svg.node());
        const r = picks[Math.floor((my - m.top) / rowH)];
        if (!r) return tip.hide();
        tip.show(event, r.label, [[null, 'Loans', int(r.n)], [null, 'Fee saved', `${one(r.fee_bp)} bp of balance`], [fee, 'In rate terms, at 5 to 1', `${one(r.fee_rate_bp)} bp`], [rate, 'Rate against its own FICO loans', `${d3.format('+.1f')(r.net_bp)} bp, ± ${one(2 * (r.se_bp || 0))}`]]);
      })
      .on('pointerleave', () => tip.hide());
  }

  // ---- Words ----
  const TERMS = [
    ['gse', 'GSE', 'Fannie Mae or Freddie Mac. This site covers loans they put into mortgage-backed securities.'],
    ['vs4', 'VS4', 'VantageScore 4.0, the credit score the GSEs began accepting alongside Classic FICO.'],
    ['priced', 'Priced on VS4', 'VS4 was the score that set the loan\'s upfront fee. The GSEs disclose which score did this on each loan.'],
    ['carrying', 'Carrying VS4', 'The loan shows a VS4 score, whichever score priced it. A lender can carry VS4 and still price on FICO. The share is a floor: a loan can have a VS4 that does not show.'],
    ['both', 'Both scores', 'The GSE file shows both a Classic FICO and a VS4 on the loan. One of them priced it.'],
    ['only', 'FICO only, VS4 only', 'The file shows just that one score. That does not mean the other was never pulled: lenders deliver one score, and at Freddie Mac some lenders\' loans often show only the one that priced them. So these shares are ceilings on loans with only one score.'],
    ['floor', 'Floor, ceiling, exact', 'A score that does not show is unknown, not absent. So the share showing a score is a floor on loans that have it: the true share is at least this. The share showing only one score is a ceiling on loans that have only that one: the true share is at most this. The share priced on VS4 is exact, because the GSEs state it for every loan.'],
    ['every', 'Records that show every score', 'Since October 19, 2026 the GSE files show every score the GSE has on a loan and which one priced it. Before that they showed only the score that priced the loan, so older bars are a floor.'],
    ['frozen', 'Lender mix frozen', 'Each week different lenders deliver different amounts. Freezing the mix gives each lender a fixed weight, its share of all the weeks shown, so only changes in what lenders do can move the number.'],
    ['fee', 'Upfront fee', 'The one-time fee the GSEs charge on a loan, set by its credit score, LTV and purpose. Also called an LLPA. Since October 1, 2026 one fee grid covers both scores.'],
    ['rateterms', 'Fee in rate terms', 'Upfront fees and note rates are different units. The rule of thumb used here is that 5 bp of upfront fee is worth about 1 bp of rate.'],
    ['ownfico', 'Against its own FICO loans', 'The note rate compared with what a model says the same loan would carry on FICO, less the same gap on that lender and channel\'s FICO-priced loans with both scores.'],
    ['rule', 'A lender\'s rule', 'When it chooses VS4. A 20-point rule means using VS4 only when its score beats FICO by 20 or more points, which matched the fees before October 1.'],
    ['stage', 'Stage', 'How far a lender has gone: FICO only, a few VS4 loans, both scores shown, using VS4 some of the time, or most of the time its score is higher.'],
    ['channel', 'Channel', 'How the lender got the loan: retail (its own), broker, or correspondent (bought from another lender).'],
    ['week', 'By week', 'Loans by the week they first appeared in the GSEs\' intraday files, ahead of the month their pool is issued.'],
    ['issue', 'Issue month', 'The month the loan\'s mortgage-backed security was issued. The latest month is partial until its month-end file arrives.'],
    ['closing', 'Closing month', 'The month the loan closed, as near as the files allow: its first payment month less two. A recent month is still arriving, so a label such as 60% in estimates how much of it has come through so far.'],
    ['lender', 'Lender', 'The company that delivered the loan to the GSE. It is not always the one that made the loan.'],
    ['bp', 'bp', 'Basis point, a hundredth of a percentage point. A pt is a full percentage point.'],
    ['hmda', 'HMDA', 'The Home Mortgage Disclosure Act record: a yearly federal filing by nearly every mortgage lender, covering each application whatever became of it. It names the score model the lender relied on for the credit decision.'],
    ['abs15g', 'Form ABS-15G', 'Where a mortgage deal to be rated, registered or not, files its due diligence findings with the SEC, at least five business days before first sale. Some of these reports list each loan and the score model on it.'],
    ['classic', 'Classic FICO', 'The older FICO versions the GSEs have long required: Equifax Beacon 5.0, Experian Fair Isaac v2 and TransUnion FICO Classic 04 or 98.'],
    ['ficonew', 'Newer FICO', 'FICO 8, FICO 9, FICO 10 and FICO 10T. Still FICO, but not the versions the GSEs have long required.'],
    ['unnamed', 'Model not named', 'The lender said it relied on more than one model, or on another model, without saying which. It could be FICO or VantageScore, so it counts as neither.'],
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
    pop.style.top = `${box.bottom - hostBox.top + 6}px`;
  };
  root.addEventListener('pointerover', (event) => {
    const el = event.target.closest('[data-term]');
    if (el) showPop(el);
    else if (popFor) hidePop();
  });
  root.addEventListener('focusin', (event) => {
    const el = event.target.closest('[data-term]');
    if (el) showPop(el);
  });
  root.addEventListener('focusout', (event) => {
    if (event.target.closest('[data-term]')) hidePop();
  });
  root.addEventListener('click', (event) => {
    const el = event.target.closest('[data-term]');
    if (el) return showPop(el);
    if (popFor) hidePop();
    const go = event.target.closest('[data-go]');
    if (go) show(go.dataset.go);
    const more = event.target.closest('.vx-more-note');
    if (more) {
      const note = more.previousElementSibling;
      const open = note.classList.toggle('vx-clamp');
      more.textContent = open ? 'More' : 'Less';
    }
  });

  // Long notes show two lines, with the rest a tap away.
  function tidy() {
    root.querySelectorAll('[data-term]:not([tabindex])').forEach((el) => {
      el.tabIndex = 0;
      el.classList.add('vx-term');
    });
    root.querySelectorAll('.vx-panel:not([hidden]) .vx-note:not([data-clamp]), .vx-panel:not([hidden]) .vx-sec-h > p:not([data-clamp])').forEach((note) => {
      if (!note.offsetParent || note.hidden) return;
      note.dataset.clamp = '1';
      note.classList.add('vx-clamp');
      if (note.scrollHeight <= note.clientHeight + 2) {
        note.classList.remove('vx-clamp');
        return;
      }
      const more = node('button', 'vx-more-note', 'More');
      more.type = 'button';
      note.after(more);
    });
  }

  vx.hooks.overview.push(drawWaffles, drawWho, drawFrozen, drawReach);
  vx.hooks.scores.push(drawMap, drawDecide);
  vx.hooks.pricing.push(drawSaving);
  vx.hooks.method.push(drawGlossary);
  vx.after.push(tidy);
  vx.redraw();
})();
