(() => {
  const root = document.querySelector('.vx');
  const AGENCIES = ['All', 'FNMA', 'FHLMC'];
  const AG_NAME = { All: 'Both GSEs', FNMA: 'Fannie Mae', FHLMC: 'Freddie Mac' };
  const AG_NOUN = { All: 'GSE', FNMA: 'Fannie Mae', FHLMC: 'Freddie Mac' };
  const MODELS = ['VantageScore 4.0', 'Classic FICO'];
  const TABS = ['overview', 'outlook', 'lenders', 'scores', 'borrowers', 'pricing', 'market', 'method'];
  const DEF_FIRST = { any: 'first_vs4_month', ten: 'first_10_month', pct5: 'first_5pct_month' };
  // Months drawn on the adoption and seller charts: VS4 deliveries begin in April 2026.
  const ADOPT_FROM = '2026-04-01';
  const CHANGE_FROM = '2026-05-01';
  const RECENT_FROM = '2026-05-01';
  const DEFAULTS = { agency: 'All', measure: 'loans', dim: 'pricing_score', seller: 'rocket-mortgage', adopt: 'any', period: 'month', top: 25, mapmonth: '', cover: 'all', basis: 'headline', pdim: 'purpose', cscope: 'All', orule: 'higher', cperiod: 'week', lsort: 'share', ccohort: 'all' };
  const DAY = 864e5;
  const pct1 = d3.format('.1%');
  const ptsSigned = (v) => (Math.abs(v) < 0.05 ? '0.0' : d3.format('+.1f')(v));
  const int = d3.format(',');
  const money = d3.format('$,.0f');
  const fixed = (n) => d3.format(`.${n}f`);
  const parse = (s) => new Date(String(s).slice(0, 10) + 'T00:00:00Z');
  const monthYear = (s) => d3.utcFormat('%B %Y')(parse(s));
  const monthShortYear = (s) => d3.utcFormat('%b %Y')(parse(s));
  const monthShort = (s) => d3.utcFormat('%b')(parse(s));
  const longDay = (s) => d3.utcFormat('%b %-d, %Y')(parse(s));
  const shortDay = (s) => d3.utcFormat('%b %-d')(parse(s));
  const pts = (v) => `${ptsSigned(v * 100)} pts`;
  const rangeDash = (s) => String(s).replace(/(\d[kKmM]?)-(\$?\d)/g, '$1–$2');  // the data files write ranges with a hyphen
  const enc = (s) => String(s).replace(/%/g, '%25').replace(/&/g, '%26').replace(/=/g, '%3D');
  const col = (i) => dash.colors[i % dash.colors.length];
  const agencyColor = (a) => col(Math.max(0, AGENCIES.indexOf(a)));
  const shade = (a) => `color-mix(in srgb, ${agencyColor(a)} 30%, transparent)`;
  const C_VS4 = col(0), C_WITHIN = col(2), C_FIXED = col(1), C_EX = col(3), C_NEW = col(2), C_DEEP = col(0), C_MIX = col(1);
  const PARTIAL = 0.6;  // how strongly a part-month or part-week bar is drawn

  // A color as the browser works it out, vars and mixes included.
  const probe = document.createElement('span');
  probe.hidden = true;
  root.append(probe);
  const cssColor = (value) => {
    probe.style.color = value;
    return getComputedStyle(probe).color;
  };
  // Whichever of the page's two text colors reads better on a fill, by measured contrast. The fill is painted over the panel and read back.
  const paint = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const luminance = (fill) => {
    for (const c of ['var(--color-panel)', fill]) {
      paint.fillStyle = cssColor(c);
      paint.fillRect(0, 0, 1, 1);
    }
    const [r, g, b] = [...paint.getImageData(0, 0, 1, 1).data].map((c) => (c / 255 <= 0.03928 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const inkOn = (fill) => {
    const l = luminance(fill);
    const contrast = (ink) => {
      const k = luminance(ink);
      return (Math.max(l, k) + 0.05) / (Math.min(l, k) + 0.05);
    };
    return contrast('var(--color-fg)') >= contrast('var(--color-panel)') ? 'var(--color-fg)' : 'var(--color-panel)';
  };
  const params = () => {
    const set = Object.fromEntries(Object.entries(dash.params() || {}).filter(([, v]) => v != null && v !== ''));
    const p = Object.assign({}, DEFAULTS, set);
    p.top = Number(p.top) === 50 ? 50 : 25;
    if (!DEF_FIRST[p.adopt]) p.adopt = 'any';
    if (p.period !== 'week') p.period = 'month';
    if (!['all', 'both', 'vs4only'].includes(p.cover)) p.cover = 'all';
    if (p.cover !== 'both' || p.basis !== 'own_fico') p.basis = 'headline';
    if (p.orule !== 'better') p.orule = 'higher';
    if (!['month', 'close'].includes(p.cperiod)) p.cperiod = 'week';
    if (!['carrying', 'rising'].includes(p.lsort)) p.lsort = 'share';
    if (p.ccohort !== 'latest') p.ccohort = 'all';
    if (!['all', 'first', 'equity', 'vs', 'fico_new'].includes(p.mscope)) p.mscope = 'all';
    if (!['pl', 'va'].includes(p.mview)) p.mview = 'hmda';
    if (!['all', 'first', 'gse', 'fha', 'va', 'jumbo', 'equity'].includes(p.myseg)) p.myseg = 'all';
    if (!['classic', 'fico_new', 'vs'].includes(p.mmeasure)) p.mmeasure = 'classic';
    if (!['pulled', 'filed', 'kind'].includes(p.pbasis)) p.pbasis = 'pulled';
    return p;
  };
  const rowsOf = (id) => {
    const d = dash.data(id);
    if (d.status !== 'ok') return [];
    return Array.isArray(d.data) ? d.data : (d.data && (d.data.rows || d.data.data || d.data.results)) || [];
  };
  const statusOf = (...ids) => {
    const s = ids.map((id) => dash.data(id).status);
    return s.find((x) => x !== 'ok' && x !== 'loading') || (s.includes('loading') ? 'loading' : 'ok');
  };
  const finalMap = () => new Map(rowsOf('monthly').map((r) => [`${r.agency}|${r.month}`, r.final]));
  const monthLabel = (keys) => (k) => d3.utcFormat(k === keys[0] || parse(k).getUTCMonth() === 0 ? '%b %Y' : '%b')(parse(k));

  // Pages: the overview is in the document; the others are cloned from their templates when first shown.
  const panels = Object.fromEntries(TABS.map((t) => [t, document.getElementById(t)]));
  let current = 'overview';
  function ensure(t) {
    const panel = panels[t];
    if (panel.dataset.ready) return;
    const tpl = document.getElementById(`tpl-${t}`);
    if (tpl) panel.append(tpl.content.cloneNode(true));
    panel.dataset.ready = '1';
  }
  function place(t) {
    ensure(t);
    current = t;
    for (const k of TABS) {
      panels[k].hidden = k !== t;
      root.querySelector(`.vx-tabs [data-tab="${k}"]`).setAttribute('aria-selected', String(k === t));
    }
    document.getElementById('controls').hidden = t === 'borrowers' || t === 'pricing' || t === 'market' || t === 'method';
    document.getElementById('agency-seg').hidden = t === 'outlook';  // the outlook covers both GSEs together
  }
  function show(t) {
    if (!TABS.includes(t)) return;
    place(t);
    dash.setLink(t);
    draw();
  }
  function openSeller(id) {
    if (!id) return;
    if (current !== 'lenders') place('lenders');
    dash.setParams({ seller: id });
    dash.setLink(`seller-${id}`);
    draw();
    const card = document.getElementById('seller-card');
    if (card) card.scrollIntoView({ block: 'start' });
  }

  const sorts = { 'adopters-table': { col: 'loans', dir: 'descending' }, 'runway-table': { col: 'rank', dir: 'ascending' },
    'ol-table': { col: 'adds', dir: 'descending' }, 'why-table': { col: 'share', dir: 'descending' } };
  root.addEventListener('click', (event) => {
    const tab = event.target.closest('.vx-tabs [data-tab]');
    if (tab) return show(tab.dataset.tab);
    const seg = event.target.closest('.vx-seg[data-param] button[data-v]');
    if (seg) {
      const key = seg.parentElement.dataset.param;
      return dash.setParams({ [key]: key === 'top' ? Number(seg.dataset.v) : seg.dataset.v });
    }
    const th = event.target.closest('table[data-sort] th[data-col]');
    if (th) {
      const s = sorts[th.closest('table').id];
      const k = th.dataset.col;
      s.dir = k === s.col ? (s.dir === 'descending' ? 'ascending' : 'descending') : (th.dataset.type === 'text' ? 'ascending' : 'descending');
      s.col = k;
      const tid = th.closest('table').id;
      return tid === 'ol-table' ? drawOutlookTable(params()) : tid === 'why-table' ? drawWhyTable(params()) : drawTables(params());
    }
    const pick = event.target.closest('#ol-pick button[data-pick]');
    if (pick) return pickLenders(pick.dataset.pick);
    const row = event.target.closest('table.vx-pickable tbody tr[data-key]');
    if (row) return openSeller(row.dataset.key);
    const link = event.target.closest('[data-open-seller]');
    if (link) openSeller(link.dataset.openSeller);
  });
  root.addEventListener('keydown', (event) => {
    const row = event.target.closest('table.vx-pickable tbody tr[data-key]');
    if (row && event.key === 'Enter') openSeller(row.dataset.key);
  });
  root.addEventListener('change', (event) => {
    if (event.target.classList.contains('ol-check')) {
      if (event.target.checked) olPicked.add(event.target.value);
      else olPicked.delete(event.target.value);
      return drawOutlookPick(params());
    }
    if (event.target.id === 'why-stage') return drawWhyTable(params());
    if (event.target.id === 'seller-pick') openSeller(event.target.value);
    else if (event.target.id === 'mix-dim') dash.setParams({ dim: event.target.value });
    else if (event.target.id === 'pricing-dim') dash.setParams({ pdim: event.target.value });
    else if (event.target.id === 'choice-scope') dash.setParams({ cscope: event.target.value });
    else if (event.target.id === 'market-month') dash.setParams({ mapmonth: event.target.value });
  });
  root.addEventListener('input', (event) => {
    if (event.target.id === 'adopters-q') drawAdopters(params());
  });

  function fill(el, status, text) {
    el.classList.toggle('dash-skeleton', status === 'loading');
    el.textContent = status === 'ok' && text != null && text !== '' ? text : '—';
  }

  // Points a set of marks at one value: the column shown and, where it comes from one row, which row.
  function mark(sel, field, where, status, text) {
    root.querySelectorAll(sel).forEach((el) => {
      if (field) el.setAttribute('data-field', field);
      if (where != null) el.setAttribute('data-where', where);
      fill(el, status, text);
    });
  }

  function drawSummary(p) {
    const status = dash.data('summary').status;
    const all = rowsOf('summary');
    const mine = all.find((r) => r.agency === p.agency) || {};
    const both = all.find((r) => r.agency === 'All') || {};
    const upb = p.measure === 'upb';
    const put = (cls, field, fmt, row, agency) => mark(`.${cls}`, field, `agency=${agency}`, status, row[field] == null ? null : fmt(row[field]));
    put('s-final-month', 'final_month', monthYear, mine, p.agency);
    put('s-prior-month', 'prior_month', monthYear, mine, p.agency);
    put('s-cur-month', 'current_month', monthYear, mine, p.agency);
    put('s-final-share', upb ? 'final_vs4_upb_share' : 'final_vs4_share', pct1, mine, p.agency);
    put('s-change', upb ? 'vs4_upb_share_change_pts' : 'vs4_share_change_pts', ptsSigned, mine, p.agency);
    put('s-cur-share', upb ? 'current_vs4_upb_share' : 'current_vs4_share', pct1, mine, p.agency);
    put('s-fico', upb ? 'final_fico_upb_share' : 'final_fico_share', pct1, mine, p.agency);
    put('s-through', 'data_through', longDay, both, 'All');
    put('s-top2', 'top2_share_of_vs4', pct1, both, 'All');
    // The page header always reads both GSEs and share of loans; the filters move the tiles, not this sentence.
    put('h-final-month', 'final_month', monthYear, both, 'All');
    put('h-cur-month', 'current_month', monthYear, both, 'All');
    put('h-final-share', 'final_vs4_share', pct1, both, 'All');
    put('h-cur-share', 'current_vs4_share', pct1, both, 'All');
  }

  function drawTiles(p) {
    const upb = p.measure === 'upb';
    const sum = rowsOf('summary').find((r) => r.agency === p.agency) || {};
    const ad = rowsOf('adoption').find((r) => r.agency === p.agency && r.month === sum.current_month) || {};
    const where = `agency=${enc(p.agency)}&month=${enc(sum.current_month ?? '')}`;
    const as = statusOf('adoption', 'summary');
    const af = upb ? 'active_upb_share' : 'active_share';
    mark('.a-active', 'active_sellers', where, as, ad.active_sellers == null ? null : int(ad.active_sellers));
    mark('.a-active-share', af, where, as, ad[af] == null ? null : pct1(ad[af]));
    root.querySelectorAll('.a-active-unit').forEach((el) => { el.textContent = upb ? 'balance' : 'loans'; });
    // Where the current month would end if it moved as past months did from the same day.
    const rg = rowsOf('asof').find((r) => r.kind === 'open' && r.agency === p.agency && r.month === sum.current_month);
    const rs = statusOf('asof', 'summary');
    const rw = `kind=open&agency=${enc(p.agency)}&month=${enc(sum.current_month ?? '')}`;
    const lo = upb ? 'vs4_upb_share_lo' : 'vs4_share_lo', hi = upb ? 'vs4_upb_share_hi' : 'vs4_share_hi';
    document.getElementById('range-line').hidden = rs !== 'loading' && !rg;
    mark('.r-lo', lo, rw, rs, rg && rg[lo] != null ? pct1(rg[lo]) : null);
    mark('.r-hi', hi, rw, rs, rg && rg[hi] != null ? pct1(rg[hi]) : null);
    mark('.r-from', 'first_month', rw, rs, rg ? monthShort(rg.first_month) : null);
    mark('.r-to', 'last_month', rw, rs, rg ? monthShort(rg.last_month) : null);
    mark('.r-day', 'day', rw, rs, rg ? String(rg.day) : null);
    root.querySelector('.r-to-part').hidden = !rg || rg.first_month === rg.last_month;
    root.querySelector('.r-day-part').hidden = !!rg && rg.day === 31;
    root.querySelector('.r-end-part').hidden = !rg || rg.day !== 31;
  }

  function prep(box, status) {
    box.querySelectorAll(':scope > svg, :scope > .vx-tip, :scope > .vx-fail').forEach((n) => n.remove());
    box.classList.toggle('dash-skeleton', status === 'loading');
    if (status === 'ok') return box.clientWidth > 0;
    if (status !== 'loading') {
      const f = document.createElement('div');
      f.className = 'vx-fail';
      f.textContent = 'Failed to load';
      box.append(f);
    }
    return false;
  }

  const svgFor = (box, W, H, label) => d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`)
    .attr('role', 'img').attr('aria-label', label);

  function textWidth(svg, labels) {
    const t = svg.append('text').attr('visibility', 'hidden');
    let w = 0;
    for (const s of labels) w = Math.max(w, t.text(s).node().getComputedTextLength());
    t.remove();
    return w;
  }

  // Shortens an SVG label to fit, ending it with an ellipsis.
  function clip(node, max) {
    let s = node.textContent;
    while (s.length > 1 && node.getComputedTextLength() > max) {
      s = s.slice(0, -1);
      node.textContent = `${s.trimEnd()}…`;
    }
  }

  function styleAxis(g) {
    g.attr('font-size', null).attr('font-family', null);
    g.select('.domain').remove();
  }

  function legend(el, items) {
    if (!el) return;
    el.replaceChildren(...items.map(([color, label, kind, strong]) => {
      const item = document.createElement('span');
      const sw = document.createElement('span');
      sw.className = kind === 'line' ? 'vx-sw vx-sw-line' : kind === 'diamond' ? 'vx-sw vx-sw-diamond' : 'vx-sw';
      if (kind === 'diamond') sw.style.borderColor = color;
      else sw.style.background = color;
      item.append(sw, label);
      if (strong) item.style.color = 'var(--color-fg)';
      return item;
    }));
  }

  function tooltip(box) {
    const tip = document.createElement('div');
    tip.className = 'vx-tip';
    box.append(tip);
    return {
      show(event, header, lines) {
        const h = document.createElement('div');
        h.className = 'vx-tip-h';
        h.textContent = header;
        tip.replaceChildren(h, ...lines.map(([color, label, value]) => {
          const r = document.createElement('div');
          r.className = 'vx-tip-r';
          if (color) {
            const sw = document.createElement('span');
            sw.className = 'vx-sw';
            sw.style.background = color;
            r.append(sw);
          }
          r.append(`${label}: ${value}`);
          return r;
        }));
        const [px, py] = d3.pointer(event, box);
        const w = tip.offsetWidth, h2 = tip.offsetHeight;
        tip.style.left = `${px + 14 + w > box.clientWidth ? Math.max(0, px - 14 - w) : px + 14}px`;
        tip.style.top = `${Math.max(0, Math.min(py - h2 / 2, box.clientHeight - h2))}px`;
        tip.style.opacity = 1;
      },
      hide() { tip.style.opacity = 0; },
    };
  }

  // Numbered markers for policy dates; the number matches the key-dates list.
  function eventMarks(svg, events, xOf, top, bottom) {
    let lastX = -Infinity, row = 0;
    events.forEach((e, i) => {
      const x = xOf(e);
      if (x == null) return;
      row = x - lastX < 18 ? 1 - row : 0;
      lastX = x;
      const cy = top - 10 - row * 16;
      svg.append('line').attr('x1', x).attr('x2', x).attr('y1', cy + 7.5).attr('y2', bottom)
        .attr('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '3 3');
      svg.append('circle').attr('cx', x).attr('cy', cy).attr('r', 7.5)
        .attr('fill', 'var(--color-panel)').attr('stroke', 'var(--cds-chart-reference)');
      svg.append('text').attr('x', x).attr('y', cy).attr('dy', '0.35em').attr('text-anchor', 'middle')
        .style('font-size', '.68rem').style('fill', 'var(--color-fg)').text(i + 1);
    });
  }

  function yAxis(svg, y, yf, left, right, ticks = 5) {
    const vals = Array.isArray(ticks) ? ticks : y.ticks(ticks);
    svg.append('g').selectAll('line').data(vals).join('line')
      .attr('x1', left).attr('x2', right).attr('y1', (v) => y(v)).attr('y2', (v) => y(v))
      .attr('stroke', (v) => (Math.abs(v) < 1e-12 ? 'var(--cds-chart-axis)' : 'var(--cds-chart-grid)'));
    svg.append('g').attr('transform', `translate(${left - 6},0)`)
      .call(d3.axisLeft(y).tickValues(vals).tickFormat(yf).tickSize(0)).call(styleAxis);
  }

  // A band axis of months or weeks, thinned so labels never meet.
  function bandAxis(svg, x, keys, lab, widest, y0) {
    const every = Math.max(1, Math.ceil((widest + 10) / x.step()));
    svg.append('g').attr('transform', `translate(0,${y0})`)
      .call(d3.axisBottom(x).tickValues(keys.filter((_, i) => i % every === 0)).tickFormat(lab).tickSize(0)).call(styleAxis);
  }

  // Margins and band scale for a chart of periods: left from the widest tick label, right from half the widest period label.
  function bandFrame(svg, keys, lab, y, yf, ticks, W, m) {
    const vals = Array.isArray(ticks) ? ticks : y.ticks(ticks);
    m.left = Math.ceil(textWidth(svg, vals.map(yf))) + 10;
    const widest = textWidth(svg, keys.map(lab));
    m.right = Math.max(m.right, Math.ceil(widest / 2));
    const x = d3.scaleBand(keys, [m.left, W - m.right]).paddingInner(0.3).paddingOuter(0.15);
    return { x, widest };
  }

  // A line over periods: solid through complete periods, dashed into partial ones.
  function partialLine(svg, rows, xf, vf, y, color, doneKey, strong = true) {
    const ok = rows.filter((r) => vf(r) != null);
    const done = ok.filter((r) => r[doneKey]), open = ok.filter((r) => !r[doneKey]);
    const line = d3.line().x(xf).y((r) => y(vf(r)));
    const style = (path) => path.attr('fill', 'none').attr('stroke', color).attr('stroke-width', strong ? 2 : 1.5)
      .attr('stroke-opacity', strong ? 1 : 0.55).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    if (done.length > 1) style(svg.append('path').attr('d', line(done)));
    if (open.length) style(svg.append('path').attr('d', line(done.slice(-1).concat(open)))).attr('stroke-dasharray', '4 4');
    if (strong) {
      svg.append('g').selectAll('circle').data(ok).join('circle')
        .attr('cx', xf).attr('cy', (r) => y(vf(r))).attr('r', 2.5)
        .attr('fill', (r) => (r[doneKey] ? color : 'var(--color-panel)')).attr('stroke', color).attr('stroke-width', 1.5);
    }
  }

  function bandHover(svg, box, x, items, key, m, H, content) {
    const tip = tooltip(box);
    svg.append('g').selectAll('rect').data(items).join('rect')
      .attr('x', (r) => x(r[key]) - (x.step() - x.bandwidth()) / 2).attr('width', x.step())
      .attr('y', m.top).attr('height', H - m.top - m.bottom).attr('fill', 'transparent')
      .on('pointermove', (event, r) => {
        const c = content(r);
        if (c) tip.show(event, c[0], c[1]);
      })
      .on('pointerleave', () => tip.hide());
  }

  // VS4 share over issue months, one line per GSE, the picked one drawn strongest. Each of `ranges`
  // ({month, lo, hi, label}) shades where the picked GSE's month would end if it moved as `label` did.
  function agencyLines(box, status, rows, f, countKey, p, label, finalOf, ranges = []) {
    if (!prep(box, status)) return;
    const data = rows.filter((r) => r[f] != null)
      .map((r) => ({ ...r, final: finalOf ? finalOf(r) : r.final, mid: new Date(parse(r.month).getTime() + 14.5 * DAY) }));
    if (!data.length) return;
    const W = box.clientWidth, H = 260;
    const m = { top: 40, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, label);
    const top = Math.max(d3.max(data, (r) => r[f]) || 0, d3.max(ranges, (r) => r.hi) || 0) || 0.01;
    const y = d3.scaleLinear([0, top * 1.1], [H - m.bottom, m.top]).nice(5);
    const yf = y.tickFormat(5, '%');
    m.left = Math.ceil(textWidth(svg, y.ticks(5).map(yf))) + 10;
    const first = d3.min(data, (r) => parse(r.month));
    const last = d3.utcMonth.offset(d3.max(data, (r) => parse(r.month)), 1);
    const x = d3.scaleUtc([first, last], [m.left, W - m.right]);
    yAxis(svg, y, yf, m.left, W - m.right);

    const months = d3.utcMonths(first, last);
    const lab = (d, i) => d3.utcFormat(i === 0 || d.getUTCMonth() === 0 ? '%b %Y' : '%b')(d);
    const widest = textWidth(svg, months.map(lab));
    const step = Math.max(1, Math.ceil(months.length / Math.max(2, Math.floor((W - m.left - m.right) / (widest + 12)))));
    const ticks = months.filter((_, i) => i % step === 0);
    svg.append('g').attr('transform', `translate(0,${H - m.bottom + 8})`)
      .call(d3.axisBottom(x).tickValues(ticks.map((d) => new Date(d.getTime() + 14.5 * DAY)))
        .tickFormat((d, i) => lab(d3.utcMonth.floor(d), i)).tickSize(0)).call(styleAxis);

    eventMarks(svg, rowsOf('events'), (e) => {
      const t = parse(e.date);
      return t >= first && t < last ? x(t) : null;
    }, m.top, H - m.bottom);

    const xf = (r) => x(r.mid);
    const shown = ranges.filter((r) => r.lo != null && r.hi != null && parse(r.month) >= first && parse(r.month) < last);
    const rx = (r) => x(new Date(parse(r.month).getTime() + 14.5 * DAY));
    const bars = svg.append('g').selectAll('g').data(shown).join('g');
    bars.append('rect').attr('x', (r) => rx(r) - 7).attr('width', 14)
      .attr('y', (r) => y(r.hi)).attr('height', (r) => Math.max(2, y(r.lo) - y(r.hi))).attr('rx', 2)
      .attr('fill', agencyColor(p.agency)).attr('fill-opacity', 0.3);
    for (const k of ['lo', 'hi']) {  // caps, so a narrow range still shows around the point
      bars.append('line').attr('x1', (r) => rx(r) - 7).attr('x2', (r) => rx(r) + 7).attr('y1', (r) => y(r[k])).attr('y2', (r) => y(r[k]))
        .attr('stroke', agencyColor(p.agency)).attr('stroke-width', 1.5);
    }
    for (const a of AGENCIES.filter((a) => a !== p.agency).concat(p.agency)) {
      partialLine(svg, data.filter((r) => r.agency === a), xf, (r) => r[f], y, agencyColor(a), 'final', a === p.agency);
    }

    const tip = tooltip(box);
    const rule = svg.append('line').attr('y1', m.top).attr('y2', H - m.bottom)
      .attr('stroke', 'var(--cds-chart-axis)').attr('opacity', 0);
    const mids = [...new Set(data.map((r) => r.month))].map((mo) => ({ mo, t: parse(mo).getTime() + 14.5 * DAY }));
    svg.append('rect').attr('x', m.left).attr('y', m.top).attr('width', W - m.left - m.right)
      .attr('height', H - m.top - m.bottom).attr('fill', 'transparent')
      .on('pointermove', (event) => {
        const t = x.invert(d3.pointer(event)[0]).getTime();
        const near = d3.least(mids, (d) => Math.abs(d.t - t));
        if (!near) return;
        rule.attr('x1', x(near.t)).attr('x2', x(near.t)).attr('opacity', 1);
        const rs = AGENCIES.map((a) => data.find((r) => r.agency === a && r.month === near.mo)).filter(Boolean);
        const rg = shown.find((r) => r.month === near.mo);
        tip.show(event, `${monthYear(near.mo)}${rs.every((r) => r.final) ? '' : ' (partial)'}`,
          rs.map((r) => [agencyColor(r.agency), AG_NAME[r.agency], `${pct1(r[f])}${f.includes('upb') ? '' : ` of ${int(r[countKey])} loans`}`])
            .concat(rg ? [[shade(p.agency), `${AG_NAME[p.agency]} if it moves as ${rg.label} did`, `${pct1(rg.lo)} to ${pct1(rg.hi)}`]] : []));
      })
      .on('pointerleave', () => { rule.attr('opacity', 0); tip.hide(); });
  }

  // Weekly share as bars with a four-week rolling line.
  function weeklyBars(box, status, data, f, f4, color, countKey, label, withEvents) {
    if (!prep(box, status)) return;
    data = data.filter((r) => r[f] != null);
    if (!data.length) return;
    const W = box.clientWidth, H = 260;
    const m = { top: withEvents ? 40 : 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, label);
    const y = d3.scaleLinear([0, (d3.max(data, (r) => Math.max(r[f], r[f4] ?? 0)) || 0.01) * 1.08], [H - m.bottom, m.top]).nice(5);
    const yf = y.tickFormat(5, '%');
    const keys = data.map((r) => r.week);
    const { x, widest } = bandFrame(svg, keys, shortDay, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    const bw = Math.min(32, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.append('g').selectAll('rect').data(data).join('rect')
      .attr('x', (r) => x(r.week) + off).attr('width', bw)
      .attr('y', (r) => y(r[f])).attr('height', (r) => Math.max(0, y(0) - y(r[f]))).attr('rx', 3)
      .attr('fill', 'var(--cds-chart-muted)').attr('fill-opacity', (r) => (r.complete ? 1 : PARTIAL));
    const cx = (r) => x(r.week) + x.bandwidth() / 2;
    svg.append('path').attr('d', d3.line().defined((r) => r[f4] != null).x(cx).y((r) => y(r[f4]))(data))
      .attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    svg.append('g').selectAll('circle').data(data.filter((r) => r[f4] != null)).join('circle')
      .attr('cx', cx).attr('cy', (r) => y(r[f4])).attr('r', 2.5).attr('fill', color);
    bandAxis(svg, x, keys, shortDay, widest, H - m.bottom + 8);
    if (withEvents) {
      const weekOf = (t) => data.find((r) => t >= parse(r.week).getTime() && t < parse(r.week).getTime() + 7 * DAY);
      eventMarks(svg, rowsOf('events'), (e) => {
        const t = parse(e.date).getTime();
        const wk = weekOf(t);
        return wk ? x(wk.week) + x.bandwidth() * ((t - parse(wk.week).getTime()) / (7 * DAY)) : null;
      }, m.top, H - m.bottom);
    }
    bandHover(svg, box, x, data, 'week', m, H, (r) => [`Week of ${shortDay(r.week)}${r.complete ? '' : ' (partial)'}`, [
      ['var(--cds-chart-muted)', 'Weekly share', `${pct1(r[f])}${f.includes('upb') ? '' : ` of ${int(r[countKey])} loans`}`],
      [color, 'Four-week share', r[f4] == null ? 'not enough weeks' : pct1(r[f4])],
    ]]);
  }

  function drawMonthly(p) {
    const box = document.getElementById('monthly-chart');
    const upb = p.measure === 'upb';
    const ranges = rowsOf('asof').filter((r) => r.kind === 'open' && r.agency === p.agency).map((r) => ({
      month: r.month, lo: r[upb ? 'vs4_upb_share_lo' : 'vs4_share_lo'], hi: r[upb ? 'vs4_upb_share_hi' : 'vs4_share_hi'],
      label: r.first_month === r.last_month ? monthShort(r.first_month) : `${monthShort(r.first_month)}–${monthShort(r.last_month)}`,
    }));
    document.getElementById('monthly-base').textContent = upb ? 'Share of balance on loans' : 'Share of loans';
    legend(document.getElementById('monthly-legend'), AGENCIES.map((a) => [agencyColor(a), AG_NAME[a], 'line', a === p.agency])
      .concat(ranges.length ? [[shade(p.agency), 'If it moves as past months did', 'box']] : []));
    agencyLines(box, statusOf('monthly', 'events'), rowsOf('monthly'), upb ? 'vs4_upb_share' : 'vs4_share',
      'scored_loans', p, 'VS4 share by issue month', null, ranges);
  }

  function drawWeekly(p) {
    const box = document.getElementById('weekly-chart');
    const color = agencyColor(p.agency);
    legend(document.getElementById('weekly-legend'), [['var(--cds-chart-muted)', 'Weekly share', 'box'], [color, `Four-week rolling share, ${p.agency === 'All' ? 'both GSEs' : AG_NAME[p.agency]}`, 'line', true]]);
    const upb = p.measure === 'upb';
    weeklyBars(box, statusOf('weekly', 'events'), rowsOf('weekly').filter((r) => r.agency === p.agency),
      upb ? 'vs4_upb_share' : 'vs4_share', upb ? 'vs4_upb_share_4wk' : 'vs4_share_4wk', color, 'scored_loans',
      'VS4 share by week of first disclosure', true);
  }

  function drawEventList() {
    root.querySelectorAll('#events-list, .sx-events').forEach((el) => {
      el.classList.toggle('dash-skeleton', dash.data('events').status === 'loading');
      el.replaceChildren(...rowsOf('events').map((e, i) => {
        const item = document.createElement('span');
        const badge = document.createElement('span');
        badge.className = 'vx-badge';
        badge.textContent = String(i + 1);
        item.append(badge, `${longDay(e.date)}: ${e.label}`);
        return item;
      }));
    });
  }

  function drawBreadth(p) {
    const box = document.getElementById('breadth-chart');
    const d = p.adopt, upb = p.measure === 'upb';
    const fShare = upb ? `adopters_upb_share_${d}` : `adopters_share_${d}`;
    const fWithin = upb ? `vs4_within_upb_${d}` : `vs4_within_${d}`;
    const fAll = upb ? 'vs4_upb_share' : 'vs4_share';
    legend(document.getElementById('breadth-legend'), [
      ['var(--cds-chart-muted)', `Lenders using VS4, share of ${AG_NOUN[p.agency]} ${upb ? 'balance' : 'loans'}`, 'box'],
      [C_WITHIN, 'How much they use VS4', 'line'],
      [C_VS4, `VS4 share of all ${upb ? 'balance' : 'loans'}`, 'line', true],
    ]);
    if (!prep(box, dash.data('adoption').status)) return;
    const data = rowsOf('adoption').filter((r) => r.agency === p.agency && r.month >= ADOPT_FROM);
    if (!data.length) return;
    const W = box.clientWidth, H = 260, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'Share of loans from lenders using VS4, and how much they use it, by issue month');
    const top = d3.max(data, (r) => Math.max(r[fShare] ?? 0, r[fWithin] ?? 0, r[fAll] ?? 0)) || 0.01;
    const y = d3.scaleLinear([0, top * 1.08], [H - m.bottom, m.top]).nice(5);
    const yf = y.tickFormat(5, '%');
    const keys = data.map((r) => r.month), lab = monthLabel(keys);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const bw = Math.min(32, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.append('g').selectAll('rect').data(data).join('rect')
      .attr('x', (r) => x(r.month) + off).attr('width', bw).attr('y', (r) => y(r[fShare] ?? 0))
      .attr('height', (r) => Math.max(0, y(0) - y(r[fShare] ?? 0))).attr('rx', 3)
      .attr('fill', 'var(--cds-chart-muted)').attr('fill-opacity', (r) => (r.final ? 1 : PARTIAL));
    const xc = (r) => x(r.month) + x.bandwidth() / 2;
    partialLine(svg, data, xc, (r) => r[fWithin], y, C_WITHIN, 'final');
    partialLine(svg, data, xc, (r) => r[fAll], y, C_VS4, 'final');
    bandHover(svg, box, x, data, 'month', m, H, (r) => [`${monthYear(r.month)}${r.final ? '' : ' (partial)'}`, [
      ['var(--cds-chart-muted)', 'Lenders using VS4', `${int(r[`adopters_${d}`])} lenders, ${pct1(r[fShare] ?? 0)} of ${upb ? 'balance' : 'loans'}`],
      [C_WITHIN, `VS4 share of their ${upb ? 'balance' : 'loans'}`, r[fWithin] == null ? '—' : pct1(r[fWithin])],
      [C_VS4, `VS4 share of all ${upb ? 'balance' : 'loans'}`, pct1(r[fAll])],
    ]]);
  }

  function drawDrivers(p) {
    const box = document.getElementById('drivers-chart');
    const k = p.measure === 'upb' ? '_upb' : '';
    const parts = [[`d_within${k}`, 'Lenders already using VS4', C_DEEP], [`d_new${k}`, 'Lenders new to VS4', C_NEW], [`d_mix${k}`, 'Loans moving between lenders', C_MIX]];
    legend(document.getElementById('drivers-legend'), parts.map(([, l, c]) => [c, l, 'box']).concat([['var(--color-fg)', 'Net change', 'line', true]]));
    if (!prep(box, dash.data('adoption').status)) return;
    const data = rowsOf('adoption').filter((r) => r.agency === p.agency && r.month >= CHANGE_FROM && r[`d_total${k}`] != null);
    if (!data.length) return;
    const segs = data.flatMap((r) => {
      let pos = 0, neg = 0;
      return parts.map(([f, l, c]) => {
        const v = r[f] || 0;
        let lo, hi;
        if (v >= 0) { lo = pos; hi = pos + v; pos = hi; } else { hi = neg; lo = neg + v; neg = lo; }
        return { r, l, c, v, lo, hi };
      });
    });
    const W = box.clientWidth, H = 260, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'Change in VS4 share by issue month, split into its sources');
    const totals = data.map((r) => r[`d_total${k}`]);
    const lo = Math.min(0, d3.min(segs, (s) => s.lo), d3.min(totals));
    const hi = Math.max(0, d3.max(segs, (s) => s.hi), d3.max(totals));
    const pad = (hi - lo) * 0.08 || 0.0005;
    const y = d3.scaleLinear([lo - pad, hi + pad], [H - m.bottom, m.top]).nice(5);
    const prec = d3.precisionFixed(d3.tickStep(y.domain()[0], y.domain()[1], 5) * 100);
    const yf = (v) => (Math.abs(v) < 1e-12 ? '0' : d3.format(`+.${prec}f`)(v * 100));
    const keys = data.map((r) => r.month), lab = monthLabel(keys);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const bw = Math.min(32, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.append('g').selectAll('rect').data(segs.filter((s) => s.hi - s.lo > 0)).join('rect')
      .attr('x', (s) => x(s.r.month) + off).attr('width', bw).attr('y', (s) => y(s.hi))
      .attr('height', (s) => Math.max(0, y(s.lo) - y(s.hi))).attr('fill', (s) => s.c)
      .attr('fill-opacity', (s) => (s.r.final ? 1 : PARTIAL));
    const net = svg.append('g').selectAll('g').data(data).join('g');
    net.append('line').attr('x1', (r) => x(r.month) + off - 3).attr('x2', (r) => x(r.month) + off + bw + 3)
      .attr('y1', (r) => y(r[`d_total${k}`])).attr('y2', (r) => y(r[`d_total${k}`]))
      .attr('stroke', 'var(--color-fg)').attr('stroke-width', 2).attr('stroke-linecap', 'round');
    bandHover(svg, box, x, data, 'month', m, H, (r) => [`${monthYear(r.month)}${r.final ? '' : ' (partial)'}, from the month before`,
      parts.map(([f, l, c]) => [c, l, pts(r[f] || 0)]).concat([['var(--color-fg)', 'Net change', pts(r[`d_total${k}`])]])]);
  }

  function seriesChart(box, status, data, lines, period, label) {
    if (!box || !prep(box, status)) return;
    const rows = data.filter((r) => lines.some(([f]) => r[f] != null));
    if (!rows.length) return;
    const W = box.clientWidth, H = 220, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, label);
    const top = d3.max(rows, (r) => d3.max(lines, ([f]) => r[f] ?? 0)) || 0.001;
    const y = d3.scaleLinear([0, top * 1.1], [H - m.bottom, m.top]).nice(5);
    const yf = y.tickFormat(5, '%');
    const keys = rows.map((r) => r.start);
    const lab = period === 'week' ? shortDay : monthLabel(keys);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const xc = (r) => x(r.start) + x.bandwidth() / 2;
    for (const [f, , c] of lines) partialLine(svg, rows, xc, (r) => r[f], y, c, 'complete');
    bandHover(svg, box, x, rows, 'start', m, H, (r) => [
      `${period === 'week' ? `Week of ${shortDay(r.start)}` : monthYear(r.start)}${r.complete ? '' : ' (partial)'}`,
      lines.map(([f, l, c]) => [c, l, r[f] == null ? '—' : pct1(r[f])])]);
  }

  function drawClean(p) {
    const k = p.measure === 'upb' ? '_upb' : '';
    const st = dash.data('series').status;
    const rows = rowsOf('series').filter((r) => r.period === p.period && r.agency === p.agency && (p.period === 'week' || r.start >= RECENT_FROM));
    const without = rows.length && rows[0].excluded ? `Without ${rows[0].excluded}` : 'Without the two largest VS4 sellers';
    const unit = p.period === 'week' ? 'week of first disclosure' : 'issue month';
    legend(document.getElementById('clean-a-legend'), [[C_VS4, 'Actual', 'line', true], [C_FIXED, 'Lender mix held at Jan–Jun 2026', 'line', true]]);
    legend(document.getElementById('clean-b-legend'), [[C_EX, without, 'line', true]]);
    seriesChart(document.getElementById('clean-a-chart'), st, rows, [[`actual${k}`, 'Actual', C_VS4], [`fixed${k}`, 'Fixed lender mix', C_FIXED]],
      p.period, `VS4 share by ${unit}, actual and at a fixed lender mix`);
    seriesChart(document.getElementById('clean-b-chart'), st, rows, [[`ex_top2${k}`, without, C_EX]], p.period, `VS4 share by ${unit}, ${without.toLowerCase()}`);
  }

  // ---- Lenders ----
  function entityOf(p) {
    const all = rowsOf('sellers');
    return all.find((r) => r.id === p.seller) || all.find((r) => r.level === 'seller') || null;
  }
  const withTicker = (r) => olName(r, r.name);

  function drawPicker(e) {
    const sel = document.getElementById('seller-pick');
    const all = rowsOf('sellers');
    const sig = `${all.length}:${all.map((r) => r.id).join(',').length}`;
    if (sel.dataset.sig !== sig) {
      const groups = [
        ['Parent companies', all.filter((r) => r.level === 'parent')],
        ['Lenders using VS4', all.filter((r) => r.level === 'seller' && r.vs4_loans > 0).sort((a, b) => b.vs4_loans - a.vs4_loans)],
        ['Largest lenders without VS4', all.filter((r) => r.level === 'seller' && !r.vs4_loans).sort((a, b) => a.rank - b.rank)],
      ];
      sel.replaceChildren(...groups.filter(([, rs]) => rs.length).map(([label, rs]) => {
        const g = document.createElement('optgroup');
        g.label = label;
        g.append(...rs.map((r) => new Option(withTicker(r), r.id)));
        return g;
      }));
      sel.dataset.sig = sig;
    }
    sel.classList.toggle('dash-skeleton', dash.data('sellers').status === 'loading');
    if (e) sel.value = e.id;
  }

  function drawExplorer(p) {
    const e = entityOf(p);
    drawPicker(e);
    const st = dash.data('sellers').status, upb = p.measure === 'upb';
    const where = e ? `id=${enc(e.id)}` : '';
    const v = (f, fmt) => (e && e[f] != null ? fmt(e[f]) : null);
    mark('.sx-name', 'name', where, st, v('name', String));
    root.querySelector('.sx-ticker').hidden = !(e && e.ticker);
    mark('.sx-ticker', 'ticker', where, st, v('ticker', String));
    root.querySelector('.sx-members-line').hidden = !(e && e.members);
    mark('.sx-members', 'members', where, st, v('members', String));
    mark('#seller-card .sx-from', 'recent_from', where, st, v('recent_from', monthShortYear));
    mark('#seller-card .sx-to', 'recent_to', where, st, v('recent_to', monthShortYear));
    const mf = upb ? 'mkt_share_upb_recent' : 'mkt_share_recent', vf = upb ? 'vs4_upb_share_recent' : 'vs4_share_recent';
    mark('.sx-mkt', mf, where, st, v(mf, pct1));
    mark('.sx-vs4', vf, where, st, upb && e && e.vs4_share_recent === 0 ? pct1(0) : v(vf, pct1));
    mark('.sx-loans', 'vs4_loans', where, st, v('vs4_loans', int));
    mark('.sx-ofall', 'share_of_all_vs4', where, st, v('share_of_all_vs4', pct1));
    // A first loan can come before any of its issue months are counted, so its first date stands in.
    const firstField = e && !e.first_vs4_month && e.first_vs4_date ? 'first_vs4_date' : 'first_vs4_month';
    mark('.sx-first', firstField, where, st, e && !e[firstField] ? 'None yet' : v(firstField, monthShortYear));
    mark('.sx-corr', 'corr_share_recent', where, st, v('corr_share_recent', pct1));
    const pull = e ? rowsOf('choice').find((r) => r.view === 'pull' && r.scope === e.id) : null;
    mark('.sx-pull', 'both_share', e ? `view=pull&scope=${enc(e.id)}` : '', dash.data('choice').status, pull ? pct1(pull.both_share) : null);
    root.querySelector('.sx-pull').parentElement.hidden = dash.data('choice').status === 'ok' && !pull;

    const fin = finalMap();
    const mine = e ? rowsOf('seller_monthly').filter((r) => r.id === e.id && r.level === e.level) : [];
    const volume = mine.filter((r) => r.agency === p.agency).map((r) => ({ ...r, final: fin.get(`${r.agency}|${r.month}`) }));
    // Blocks with nothing to show hide first, since the charts left widen and each measures its width as it draws.
    const noVs4 = !!e && st === 'ok' && !e.vs4_loans;
    document.getElementById('sx-share').hidden = noVs4;
    root.querySelectorAll('.sx-events').forEach((el) => { el.hidden = noVs4; });
    document.getElementById('sx-volume').hidden = statusOf('seller_monthly', 'monthly') === 'ok' && !volume.length;
    drawSellerWeekly(p, e);
    const f = upb ? 'vs4_upb_share' : 'vs4_share';
    legend(document.getElementById('sx-share-legend'), AGENCIES.map((a) => [agencyColor(a), AG_NAME[a], 'line', a === p.agency]));
    agencyLines(document.getElementById('sx-share-chart'), statusOf('seller_monthly', 'monthly', 'events'), mine, f, 'scored', p,
      `VS4 share by issue month, ${e ? e.name : ''}`, (r) => fin.get(`${r.agency}|${r.month}`));
    drawSellerVolume(p, e, volume);
    drawSplits(e);
  }

  function drawSellerVolume(p, e, data) {
    const box = document.getElementById('sx-volume-chart');
    legend(document.getElementById('sx-volume-legend'), [['var(--cds-chart-muted)', `Loans with a credit score, ${AG_NAME[p.agency].replace('Both', 'both')}`, 'box'], [C_VS4, 'VS4 loans', 'box', true]]);
    if (!prep(box, statusOf('seller_monthly', 'monthly')) || !data.length) return;
    const W = box.clientWidth, H = 260, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, `Loans by issue month, ${e ? e.name : ''}`);
    const y = d3.scaleLinear([0, (d3.max(data, (r) => r.scored) || 1) * 1.08], [H - m.bottom, m.top]).nice(5);
    const yf = d3.format('~s');
    const keys = data.map((r) => r.month), lab = monthLabel(keys);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const bw = Math.min(32, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    for (const [f, color] of [['scored', 'var(--cds-chart-muted)'], ['vs4', C_VS4]]) {
      svg.append('g').selectAll('rect').data(data).join('rect')
        .attr('x', (r) => x(r.month) + off).attr('width', bw).attr('y', (r) => y(r[f]))
        .attr('height', (r) => Math.max(0, y(0) - y(r[f]))).attr('rx', 3).attr('fill', color)
        .attr('fill-opacity', (r) => (r.final ? 1 : PARTIAL));
    }
    bandHover(svg, box, x, data, 'month', m, H, (r) => [`${monthYear(r.month)}${r.final ? '' : ' (partial)'}`, [
      ['var(--cds-chart-muted)', 'Loans with a score', int(r.scored)],
      [C_VS4, 'VS4 loans', `${int(r.vs4)} (${pct1(r.vs4_share)})`],
      [null, `Share of ${AG_NOUN[p.agency]} loans`, pct1(r.mkt_share)],
    ]]);
  }

  function drawSellerWeekly(p, e) {
    const box = document.getElementById('sx-weekly-chart');
    const lg = document.getElementById('sx-weekly-legend');
    const st = dash.data('seller_weekly').status;
    const rows = e ? rowsOf('seller_weekly').filter((r) => r.id === e.id && r.level === e.level) : [];
    const none = st === 'ok' && !rows.length;
    document.getElementById('sx-weekly').hidden = none;
    if (none) return;
    legend(lg, [['var(--cds-chart-muted)', 'Weekly share, both GSEs', 'box'], [C_VS4, 'Four-week rolling share', 'line', true]]);
    const upb = p.measure === 'upb';
    weeklyBars(box, st, rows, upb ? 'vs4_upb_share' : 'vs4_share', upb ? 'vs4_upb_share_4wk' : 'vs4_share_4wk', C_VS4, 'scored',
      `VS4 share by week of first disclosure, ${e ? e.name : ''}`, false);
  }

  function drawSplits(e) {
    const st = dash.data('seller_splits').status;
    const fin = finalMap();
    const rows = e ? rowsOf('seller_splits').filter((r) => r.id === e.id && r.level === e.level && r.month >= RECENT_FROM) : [];
    const none = st === 'ok' && !rows.some((r) => r.vs4_share > 0);
    document.getElementById('sx-splits').hidden = none;
    if (none) return;
    for (const [dim, offset, noun] of [['channel', 0, 'channel'], ['purpose', 3, 'loan purpose']]) {
      const box = document.getElementById(`sx-${dim}-chart`), lg = document.getElementById(`sx-${dim}-legend`);
      const data = rows.filter((r) => r.dim === dim).map((r) => ({ ...r, final: fin.get(`All|${r.month}`) }));
      const buckets = [...new Map(data.map((r) => [r.bucket, r.bucket_order])).entries()].sort((a, b) => a[1] - b[1]).map(([b]) => b);
      const color = (b) => col(offset + buckets.indexOf(b));
      legend(lg, buckets.map((b) => [color(b), b, 'line']));
      if (!prep(box, statusOf('seller_splits', 'monthly')) || !data.length) continue;
      const keys = [...new Set(data.map((r) => r.month))].sort();
      const W = box.clientWidth, H = 180, m = { top: 10, right: 10, bottom: 26, left: 0 };
      const svg = svgFor(box, W, H, `VS4 share by ${noun}, ${e.name}`);
      const y = d3.scaleLinear([0, (d3.max(data, (r) => r.vs4_share) || 0.01) * 1.1], [H - m.bottom, m.top]).nice(4);
      const yf = y.tickFormat(4, '%');
      const lab = monthLabel(keys);
      const { x, widest } = bandFrame(svg, keys, lab, y, yf, 4, W, m);
      yAxis(svg, y, yf, m.left, W - m.right, 4);
      bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
      const xc = (r) => x(r.month) + x.bandwidth() / 2;
      for (const b of buckets) partialLine(svg, data.filter((r) => r.bucket === b), xc, (r) => r.vs4_share, y, color(b), 'final');
      bandHover(svg, box, x, keys.map((k) => ({ month: k })), 'month', m, H, (o) => [
        `${monthYear(o.month)}${fin.get(`All|${o.month}`) ? '' : ' (partial)'}, both GSEs`,
        buckets.map((b) => {
          const r = data.find((d) => d.bucket === b && d.month === o.month);
          return [color(b), b, r ? `${pct1(r.vs4_share)} of ${int(r.scored)}` : 'no loans'];
        })]);
    }
  }

  function drawHeat(p) {
    const box = document.getElementById('heat-chart');
    if (!prep(box, statusOf('sellers', 'seller_monthly', 'monthly'))) return;
    const upb = p.measure === 'upb', f = upb ? 'vs4_upb_share' : 'vs4_share';
    const mf = upb ? 'mkt_share_upb_recent' : 'mkt_share_recent';
    const sellers = rowsOf('sellers').filter((r) => r.level === 'seller' && r.rank != null).sort((a, b) => a.rank - b.rank).slice(0, p.top);
    const fin = finalMap();
    const months = [...new Set(rowsOf('monthly').filter((r) => r.agency === p.agency && r.month >= RECENT_FROM).map((r) => r.month))].sort();
    if (!sellers.length || !months.length) return;
    const cells = new Map(rowsOf('seller_monthly').filter((r) => r.level === 'seller' && r.agency === p.agency).map((r) => [`${r.id}|${r.month}`, r]));
    const W = box.clientWidth, rowH = 24, headH = 26;
    const H = headH + sellers.length * rowH + 2;
    box.style.minHeight = `${H}px`;
    const svg = svgFor(box, W, H, 'VS4 share by issue month for the largest sellers');
    const label = (r) => (W < 640 ? r.short : olName(r));
    const shareW = Math.ceil(textWidth(svg, sellers.map((r) => (r[mf] == null ? '—' : pct1(r[mf]))).concat(['Share']))) + 18;
    const labelW = Math.min(Math.ceil(textWidth(svg, sellers.map(label))) + 14, Math.max(96, Math.floor(W * 0.36)));
    const textW = textWidth(svg, ['00.0%']) + 10;
    const avail = W - labelW - shareW;
    const shown = months.slice(-Math.max(1, Math.floor(avail / Math.max(32, Math.min(textW, 48)))));
    const cw = avail / shown.length;
    const withText = cw >= textW;
    const ramp = d3.interpolateRgb(cssColor('var(--color-panel)'), cssColor(C_VS4));
    const vmax = Math.max(0.05, d3.max(shown, (mo) => d3.max(sellers, (s) => (cells.get(`${s.id}|${mo}`) || {})[f] ?? 0)) || 0);
    const t = d3.scaleSqrt([0, vmax], [0, 1]).clamp(true);
    const x0 = (i) => labelW + shareW + i * cw;
    svg.append('text').attr('x', labelW + shareW - 10).attr('y', headH / 2).attr('dy', '0.35em').attr('text-anchor', 'end').text('Share');
    svg.append('g').selectAll('text').data(shown).join('text')
      .attr('x', (mo, i) => x0(i) + cw / 2).attr('y', headH / 2).attr('dy', '0.35em').attr('text-anchor', 'middle')
      .style('font-style', (mo) => (fin.get(`${p.agency}|${mo}`) ? null : 'italic')).text(monthShort);
    const tip = tooltip(box);
    const rows = svg.append('g').selectAll('g').data(sellers).join('g')
      .attr('transform', (r, i) => `translate(0,${headH + i * rowH})`).style('cursor', 'pointer')
      .on('click', (event, r) => openSeller(r.id));
    rows.append('rect').attr('width', W).attr('height', rowH)
      .attr('fill', (r) => (r.id === p.seller ? 'var(--cds-chart-grid)' : 'transparent'));
    rows.append('text').attr('y', rowH / 2).attr('dy', '0.35em').style('fill', 'var(--color-fg)').text(label)
      .each(function () { clip(this, labelW - 12); });
    rows.append('text').attr('x', labelW + shareW - 10).attr('y', rowH / 2).attr('dy', '0.35em').attr('text-anchor', 'end')
      .text((r) => (r[mf] == null ? '—' : pct1(r[mf])));
    shown.forEach((mo, i) => {
      const cell = (r) => cells.get(`${r.id}|${mo}`);
      rows.append('rect').attr('x', x0(i) + 1).attr('y', 1).attr('width', Math.max(0, cw - 2)).attr('height', rowH - 2).attr('rx', 3)
        .attr('fill', (r) => (cell(r) && cell(r)[f] != null ? ramp(t(cell(r)[f])) : 'transparent'))
        .attr('stroke', 'var(--color-border-line)')
        .on('pointermove', (event, r) => {
          const c = cell(r);
          tip.show(event, `${r.name}, ${monthYear(mo)}${fin.get(`${p.agency}|${mo}`) ? '' : ' (partial)'}`, c
            ? [[null, upb ? 'VS4 share of its balance' : 'VS4 share', `${c[f] == null ? '—' : pct1(c[f])}${upb ? '' : ` of ${int(c.scored)} loans`}`], [null, `Share of ${AG_NOUN[p.agency]} ${upb ? 'balance' : 'loans'}`, pct1(upb ? c.mkt_share_upb : c.mkt_share)]]
            : [[null, 'Loans', 'none this month']]);
        })
        .on('pointerleave', () => tip.hide());
      if (withText) {
        rows.append('text').attr('x', x0(i) + cw / 2).attr('y', rowH / 2).attr('dy', '0.35em').attr('text-anchor', 'middle')
          .style('pointer-events', 'none')
          .style('fill', (r) => inkOn(ramp(t((cell(r) || {})[f] ?? 0))))
          .text((r) => {
            const c = cell(r);
            if (!c || c[f] == null) return '';
            return c[f] === 0 ? '·' : c[f] < 0.0005 ? '<0.1%' : pct1(c[f]);
          });
      }
    });
  }

  function drawNewAdopters(p) {
    const box = document.getElementById('newadopt-chart');
    if (!prep(box, statusOf('adoption', 'sellers'))) return;
    const d = p.adopt, upb = p.measure === 'upb', first = DEF_FIRST[d];
    const data = rowsOf('adoption').filter((r) => r.agency === p.agency && r.month >= ADOPT_FROM);
    if (!data.length) return;
    const fNew = `new_${d}`, fShare = upb ? `new_upb_share_${d}` : `new_share_${d}`;
    const beside = document.getElementById('runway-table').closest('.vx-tablebox');
    const sideBySide = beside.getBoundingClientRect().left >= box.getBoundingClientRect().right;
    const W = box.clientWidth, H = sideBySide ? Math.max(240, Math.min(480, beside.offsetHeight)) : 240, m = { top: 22, right: 10, bottom: 26, left: 0 };
    box.style.minHeight = `${H}px`;
    const svg = svgFor(box, W, H, 'Lenders starting to use VS4, by issue month');
    const y = d3.scaleLinear([0, Math.max(4, d3.max(data, (r) => r[fNew]) || 0)], [H - m.bottom, m.top]).nice(4);
    const ticks = y.ticks(4).filter(Number.isInteger);
    const yf = d3.format('d');
    const keys = data.map((r) => r.month), lab = monthLabel(keys);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, ticks, W, m);
    yAxis(svg, y, yf, m.left, W - m.right, ticks);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const bw = Math.min(32, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.append('g').selectAll('rect').data(data).join('rect')
      .attr('x', (r) => x(r.month) + off).attr('width', bw).attr('y', (r) => y(r[fNew]))
      .attr('height', (r) => Math.max(0, y(0) - y(r[fNew]))).attr('rx', 3).attr('fill', C_NEW)
      .attr('fill-opacity', (r) => (r.final ? 1 : PARTIAL));
    svg.append('g').selectAll('text').data(data.filter((r) => r[fNew] > 0)).join('text')
      .attr('x', (r) => x(r.month) + x.bandwidth() / 2).attr('y', (r) => y(r[fNew]) - 6).attr('text-anchor', 'middle')
      .style('fill', 'var(--color-fg)').text((r) => int(r[fNew]));
    const sellers = rowsOf('sellers').filter((s) => s.level === 'seller');
    bandHover(svg, box, x, data, 'month', m, H, (r) => {
      const names = p.agency === 'All' ? sellers.filter((s) => s[first] === r.month)
        .sort((a, b) => (b.mkt_share_recent ?? 0) - (a.mkt_share_recent ?? 0)).map((s) => s.short) : [];
      const who = names.slice(0, 3).join(', ') + (names.length > 3 ? ` and ${names.length - 3} more` : '');
      return [`${monthYear(r.month)}${r.final ? '' : ' (partial)'}`, [
        [C_NEW, 'Lenders', int(r[fNew])],
        [null, `Their share of ${AG_NOUN[p.agency]} ${upb ? 'balance' : 'loans'}`, pct1(r[fShare])],
      ].concat(names.length ? [[null, 'Largest', who]] : [])];
    });
  }

  // Sellers by their share of loans. firstMonths: each seller's first month over the threshold picked, at the
  // GSE picked. The largest of those sellers get a color of their own in both charts; the rest share one.
  const C_REST = 'var(--cds-chart-muted)';
  function firstMonths(p) {
    const f = `first_${p.adopt}`;
    return new Map(rowsOf('adopters').filter((r) => r.agency === p.agency && r[f]).map((r) => [r.id, r[f]]));
  }
  function adopterColors(p, firsts) {
    const f = p.measure === 'upb' ? 'mkt_share_upb_recent' : 'mkt_share_recent';
    const top = rowsOf('sellers').filter((r) => r.level === 'seller' && firsts.has(r.id))
      .sort((a, b) => (b[f] ?? 0) - (a[f] ?? 0)).slice(0, 6);
    return new Map(top.map((r, i) => [r.id, col(i)]));
  }
  const sellerIndex = () => new Map(rowsOf('sellers').filter((r) => r.level === 'seller').map((r) => [r.id, r]));
  const fullName = (s) => olName(s, s.name);

  function drawCoverage(p) {
    const box = document.getElementById('coverage-chart');
    const upb = p.measure === 'upb', d = p.adopt;
    const firsts = firstMonths(p), colors = adopterColors(p, firsts), names = sellerIndex();
    legend(document.getElementById('coverage-legend'), [...colors].map(([id, c]) => [c, (names.get(id) || {}).short || id, 'box'])
      .concat([[C_REST, 'Other lenders using VS4', 'box'], ['var(--color-fg)', `VS4 share of all ${upb ? 'balance' : 'loans'}`, 'line']]));
    if (!prep(box, statusOf('adopters', 'seller_monthly', 'adoption', 'sellers'))) return;
    const months = rowsOf('adoption').filter((r) => r.agency === p.agency && r.month >= ADOPT_FROM).sort((a, b) => d3.ascending(a.month, b.month));
    if (!months.length) return;
    const mf = upb ? 'mkt_share_upb' : 'mkt_share', vf = upb ? 'vs4_upb_share' : 'vs4_share';
    const tf = upb ? `adopters_upb_share_${d}` : `adopters_share_${d}`;
    const size = (id) => (names.get(id) || {})[upb ? 'mkt_share_upb_recent' : 'mkt_share_recent'] ?? 0;
    const byMonth = d3.group(rowsOf('seller_monthly').filter((r) => r.level === 'seller' && r.agency === p.agency
      && firsts.has(r.id) && r.month >= firsts.get(r.id) && r[mf] > 0), (r) => r.month);
    const segs = [];
    for (const mo of months) {
      let y0 = 0;
      const rs = (byMonth.get(mo.month) || []).sort((a, b) => d3.ascending(firsts.get(a.id), firsts.get(b.id)) || size(b.id) - size(a.id));
      for (const r of rs) {
        segs.push({ ...r, y0, y1: y0 + r[mf], final: mo.final });
        y0 += r[mf];
      }
    }
    const W = box.clientWidth, H = 300, m = { top: 22, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'Share of GSE loans from lenders using VS4, by lender and issue month');
    const y = d3.scaleLinear([0, 1], [H - m.bottom, m.top]);
    const yf = d3.format('.0%'), ticks = [0, 0.25, 0.5, 0.75, 1];
    const keys = months.map((r) => r.month), lab = monthLabel(keys);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, ticks, W, m);
    yAxis(svg, y, yf, m.left, W - m.right, ticks);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const bw = Math.min(56, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.append('g').selectAll('rect').data(months).join('rect')
      .attr('x', (r) => x(r.month) + off).attr('width', bw).attr('y', y(1)).attr('height', y(0) - y(1)).attr('rx', 3)
      .attr('fill', 'var(--cds-chart-grid)').attr('fill-opacity', 0.5);
    const tip = tooltip(box);
    svg.append('g').selectAll('rect').data(segs).join('rect')
      .attr('x', (r) => x(r.month) + off).attr('width', bw).attr('y', (r) => y(r.y1)).attr('height', (r) => Math.max(0, y(r.y0) - y(r.y1)))
      .attr('fill', (r) => colors.get(r.id) || C_REST).attr('fill-opacity', (r) => (r.final ? 1 : PARTIAL))
      .attr('stroke', 'var(--color-panel)').attr('stroke-width', 0.5).style('cursor', 'pointer')
      .on('pointermove', (event, r) => {
        const s = names.get(r.id) || { name: r.id };
        tip.show(event, `${fullName(s)}, ${monthYear(r.month)}${r.final ? '' : ' (partial)'}`, [
          [colors.get(r.id) || C_REST, `Share of ${AG_NOUN[p.agency]} ${upb ? 'balance' : 'loans'}`, pct1(r[mf])],
          [null, `VS4 share of its ${upb ? 'balance' : 'loans'}`, r[vf] == null ? '—' : pct1(r[vf])],
          [null, 'Using VS4 since', monthShortYear(firsts.get(r.id))],
        ]);
      })
      .on('pointerleave', () => tip.hide())
      .on('click', (event, r) => openSeller(r.id));
    const tl = x.step() >= textWidth(svg, ['00.0%']) + 8 ? pct1 : d3.format('.0%');  // whole percents when bars are narrow
    svg.append('g').selectAll('text').data(months.filter((r) => r[tf] > 0)).join('text')
      .attr('x', (r) => x(r.month) + x.bandwidth() / 2).attr('y', (r) => y(r[tf]) - 6).attr('text-anchor', 'middle')
      .style('fill', 'var(--color-fg)').style('pointer-events', 'none').text((r) => tl(r[tf]));
    const cx = (r) => x(r.month) + x.bandwidth() / 2;
    svg.append('path').attr('d', d3.line().defined((r) => r[vf] != null).x(cx).y((r) => y(r[vf]))(months))
      .attr('fill', 'none').attr('stroke', 'var(--color-fg)').attr('stroke-width', 1.5).style('pointer-events', 'none');
    svg.append('g').selectAll('circle').data(months.filter((r) => r[vf] != null)).join('circle')
      .attr('cx', cx).attr('cy', (r) => y(r[vf])).attr('r', 2.5).attr('fill', 'var(--color-fg)').style('pointer-events', 'none');
  }

  function drawMarket(p) {
    const box = document.getElementById('market-chart');
    const upb = p.measure === 'upb', d = p.adopt;
    const months = rowsOf('adoption').filter((r) => r.agency === p.agency && r.month >= ADOPT_FROM).sort((a, b) => d3.ascending(a.month, b.month));
    const t = months.find((r) => r.month === p.mapmonth) || months[months.length - 1];
    const sel = document.getElementById('market-month');
    sel.classList.toggle('dash-skeleton', dash.data('adoption').status === 'loading');
    sel.replaceChildren(...months.slice().reverse().map((r) => {
      const o = document.createElement('option');
      o.value = r.month;
      o.textContent = `${monthYear(r.month)}${r.final ? '' : ' (partial)'}`;
      o.selected = r === t;
      return o;
    }));
    const af = upb ? `adopters_upb_share_${d}` : `adopters_share_${d}`, df = upb ? `vs4_within_upb_${d}` : `vs4_within_${d}`;
    const hf = upb ? 'vs4_upb_share' : 'vs4_share', wf = upb ? 'mkt_share_upb' : 'mkt_share';
    const where = t ? `agency=${enc(p.agency)}&month=${enc(t.month)}` : '';
    const as = dash.data('adoption').status;
    mark('.mk-ad', af, where, as, t && t[af] != null ? pct1(t[af]) : null);
    mark('.mk-depth', df, where, as, t && t[df] != null ? pct1(t[df]) : null);
    mark('.mk-vs4', hf, where, as, t && t[hf] != null ? pct1(t[hf]) : null);
    mark('.mk-month', 'month', where, as, t ? monthYear(t.month) : null);
    if (!prep(box, statusOf('seller_monthly', 'adoption', 'sellers', 'adopters')) || !t) return;
    const firsts = firstMonths(p), colors = adopterColors(p, firsts), names = sellerIndex();
    const over = (r) => firsts.has(r.id) && firsts.get(r.id) <= r.month;
    const cols = rowsOf('seller_monthly').filter((r) => r.level === 'seller' && r.agency === p.agency && r.month === t.month && r[wf] > 0)
      .sort((a, b) => ((names.get(a.id) || {}).rank ?? Infinity) - ((names.get(b.id) || {}).rank ?? Infinity));
    const rest = t[upb ? 'rest_upb_share' : 'rest_share'] || 0, depth = t[df];
    let at = 0;
    const blocks = cols.map((r) => ({ ...r, x0: at, x1: (at += r[wf]) })).concat(rest > 0 ? [{ rest: true, x0: at, x1: at + rest }] : []);
    const W = box.clientWidth, H = 360, m = { top: 14, right: 10, bottom: 116, left: 0 };
    const svg = svgFor(box, W, H, `Lenders by share of ${AG_NOUN[p.agency]} loans and VS4 share of their loans, ${monthYear(t.month)}`);
    // The scale follows sellers with at least 0.25% of loans; a narrower, taller column is cut at the top.
    const wide = cols.filter((r) => r[wf] >= 0.0025);
    const y = d3.scaleLinear([0, Math.max(d3.max(wide, (r) => r[hf] ?? 0) || 0, depth || 0, 0.05) * 1.12], [H - m.bottom, m.top]).nice(5).clamp(true);
    const yf = y.tickFormat(5, '%');
    m.left = Math.ceil(textWidth(svg, y.ticks(5).map(yf))) + 10;
    yAxis(svg, y, yf, m.left, W - m.right);
    const x = d3.scaleLinear([0, Math.max(1, at + rest)], [m.left, W - m.right]);
    const bx = (b) => x(b.x0), bwd = (b) => Math.max(0.5, x(b.x1) - x(b.x0) - (x(b.x1) - x(b.x0) > 3 ? 1 : 0));
    const tip = tooltip(box);
    const g = svg.append('g').selectAll('g').data(blocks).join('g').style('cursor', (b) => (b.rest ? null : 'pointer'))
      .on('pointermove', (event, b) => {
        if (b.rest) {
          return tip.show(event, `${int(t.rest_sellers)} other lenders, ${monthYear(t.month)}`, [
            [null, `Share of ${AG_NOUN[p.agency]} ${upb ? 'balance' : 'loans'}`, pct1(rest)], [null, 'VS4 loans', 'none to date']]);
        }
        const s = names.get(b.id) || { name: b.id };
        tip.show(event, `${fullName(s)}, ${monthYear(b.month)}${t.final ? '' : ' (partial)'}`, [
          [null, `Share of ${AG_NOUN[p.agency]} ${upb ? 'balance' : 'loans'}`, pct1(b[wf])],
          [colors.get(b.id) || C_REST, `VS4 share of its ${upb ? 'balance' : 'loans'}`, `${pct1(b[hf] ?? 0)}${upb ? '' : ` of ${int(b.scored)} loans`}`],
          [null, 'Threshold', over(b) ? `met in ${monthShortYear(firsts.get(b.id))}` : 'not met'],
        ]);
      })
      .on('pointerleave', () => tip.hide())
      .on('click', (event, b) => { if (!b.rest) openSeller(b.id); });
    g.append('rect').attr('x', bx).attr('width', bwd).attr('y', m.top).attr('height', H - m.bottom - m.top)
      .attr('fill', 'var(--cds-chart-grid)').attr('fill-opacity', (b) => (b.rest ? 0.9 : 0.45));
    g.filter((b) => !b.rest && b[hf] > 0).append('rect').attr('x', bx).attr('width', bwd)
      .attr('y', (b) => y(b[hf])).attr('height', (b) => Math.max(0, y(0) - y(b[hf])))
      .attr('fill', (b) => colors.get(b.id) || C_REST).attr('fill-opacity', (b) => (over(b) ? 1 : 0.4));
    g.filter((b) => x(b.x1) - x(b.x0) >= 16).append('text')
      .attr('transform', (b) => `translate(${(x(b.x0) + x(b.x1)) / 2},${H - m.bottom + 6}) rotate(-90)`)
      .attr('dy', '0.35em').attr('text-anchor', 'end').style('pointer-events', 'none')
      .text((b) => (b.rest ? 'Other lenders' : (names.get(b.id) || {}).short || b.id)).each(function () { clip(this, m.bottom - 10); });
    if (depth != null) {
      svg.append('line').attr('x1', m.left).attr('x2', W - m.right).attr('y1', y(depth)).attr('y2', y(depth))
        .attr('stroke', 'var(--color-fg)').attr('stroke-dasharray', '4 3').style('pointer-events', 'none');
      svg.append('text').attr('x', W - m.right).attr('y', y(depth) - 6).attr('text-anchor', 'end').style('fill', 'var(--color-fg)')
        .style('pointer-events', 'none').text(`VS4 share of their ${upb ? 'balance' : 'loans'}: ${pct1(depth)}`);
    }
  }

  // Tables: columns are [id, dataset column, format]; the id stays put while the column follows the measure.
  function renderTable(table, rows, cols, status) {
    const s = sorts[table.id];
    table.querySelectorAll('th[data-col]').forEach((th) => {
      const c = cols.find((x) => x[0] === th.dataset.col);
      if (c) th.setAttribute('data-field', c[1]);
      if (th.dataset.col === s.col) th.setAttribute('aria-sort', s.dir);
      else th.removeAttribute('aria-sort');
    });
    const sc = cols.find((x) => x[0] === s.col) || cols[0];
    const sorted = rows.slice().sort((a, b) => {
      const va = a[sc[1]], vb = b[sc[1]];
      if (va == null || vb == null) return (va == null) - (vb == null);
      const c = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return s.dir === 'ascending' ? c : -c;
    });
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', status === 'loading');
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of sorted) {
      const tr = body.insertRow();
      tr.dataset.key = r.id;
      tr.tabIndex = 0;
      cols.forEach(([id, f, fmt], i) => {
        const td = tr.insertCell();
        td.textContent = r[f] == null ? '—' : fmt(r[f]);
        const th = table.tHead.rows[0].cells[i];
        if (th) td.className = th.className;
      });
    }
  }

  function drawRunway(p) {
    const table = document.getElementById('runway-table');
    const d = p.adopt, upb = p.measure === 'upb', first = DEF_FIRST[d];
    const rows = rowsOf('sellers').filter((r) => r.level === 'seller' && r.rank != null && !r[first]).sort((a, b) => a.rank - b.rank).slice(0, 15);
    renderTable(table, rows, [['rank', 'rank', int], ['name', 'name', String], ['ticker', 'ticker', String],
      ['share', upb ? 'mkt_share_upb_recent' : 'mkt_share_recent', pct1], ['corr', 'corr_share_recent', pct1]],
      dash.data('sellers').status);
    const ad = rowsOf('adoption').filter((r) => r.agency === p.agency);
    const last = ad.length ? ad.reduce((a, b) => (a.month > b.month ? a : b)) : null;
    const f = upb ? `nonadopters_upb_share_${d}` : `nonadopters_share_${d}`;
    const where = last ? `agency=${enc(p.agency)}&month=${enc(last.month)}` : '';
    const as = dash.data('adoption').status;
    mark('.rw-share', f, where, as, last && last[f] != null ? pct1(last[f]) : null);
    mark('.rw-month', 'month', where, as, last ? monthYear(last.month) : null);
    root.querySelectorAll('.rw-partial').forEach((el) => { el.hidden = !last || last.final; });
  }

  function drawAdopters(p) {
    const table = document.getElementById('adopters-table');
    if (!table) return;
    const d = p.adopt, upb = p.measure === 'upb', first = DEF_FIRST[d];
    const q = (document.getElementById('adopters-q').value || '').trim().toLowerCase();
    const rows = rowsOf('sellers').filter((r) => r.level === 'seller' && r[first]
      && (!q || `${r.name} ${r.short} ${r.ticker || ''} ${r.parent || ''}`.toLowerCase().includes(q)))
      .map((r) => (r.vs4_upb_share_recent == null && r.vs4_share_recent === 0 ? { ...r, vs4_upb_share_recent: 0 } : r));
    const small = (v) => (v > 0 && v < 0.0005 ? '<0.1%' : pct1(v));
    renderTable(table, rows, [['name', 'name', String], ['ticker', 'ticker', String], ['first', 'first_vs4_month', monthShortYear],
      ['ten', 'first_10_month', monthShortYear], ['pct5', 'first_5pct_month', monthShortYear],
      ['vs4', upb ? 'vs4_upb_share_recent' : 'vs4_share_recent', small], ['share', upb ? 'mkt_share_upb_recent' : 'mkt_share_recent', small],
      ['loans', 'vs4_loans', int], ['ofall', 'share_of_all_vs4', small]], dash.data('sellers').status);
    if (!rows.length && dash.data('sellers').status === 'ok') {
      const td = table.tBodies[0].insertRow().insertCell();
      td.colSpan = table.tHead.rows[0].cells.length;
      td.className = 'vx-l';
      td.textContent = 'No lender matches.';
    }
    const ad = rowsOf('adoption').filter((r) => r.agency === 'All');
    const last = ad.length ? ad.reduce((a, b) => (a.month > b.month ? a : b)) : null;
    const where = last ? `agency=All&month=${enc(last.month)}` : '';
    const as = dash.data('adoption').status;
    mark('.ad-count', `adopters_${d}`, where, as, last ? int(last[`adopters_${d}`]) : null);
    mark('.ad-month', 'month', where, as, last ? monthYear(last.month) : null);
  }

  function drawTables(p) {
    if (current !== 'lenders') return;
    drawRunway(p);
    drawAdopters(p);
  }

  function drawWindow() {
    const r = rowsOf('sellers')[0];
    const st = dash.data('sellers').status;
    root.querySelectorAll('.sx-from[data-row], .sx-to[data-row]').forEach((el) => {
      const f = el.classList.contains('sx-from') ? 'recent_from' : 'recent_to';
      fill(el, st, r && r[f] ? monthShortYear(r[f]) : null);
    });
  }

  // ---- Score choice ----
  const GAP_TICK = { '-3': '−3 or less', '-2': '−2', '-1': '−1', 0: '0', '0top': '0 (780+)', 1: '+1', 2: '+2', 3: '+3 or more' };

  function drawChoice(p) {
    const st = dash.data('choice').status;
    const rule = rowsOf('choice').filter((r) => r.view === 'rule');
    const sel = document.getElementById('choice-scope');
    const totals = new Map(rule.filter((r) => r.agency === 'All').map((r) => [r.scope, r.scope_loans]));
    // A lender with too few loans for three bars would only draw empty charts, so it stays off the picker.
    const bars = d3.rollup(rule.filter((r) => r.agency === 'All'), (v) => v.length, (r) => r.scope);
    const scopes = [...new Map(rule.filter((r) => r.agency === 'All' && (r.scope === 'All' || bars.get(r.scope) >= 3)).map((r) => [r.scope, r.scope_label])).entries()]
      .sort((a, b) => (a[0] === 'All' ? -1 : b[0] === 'All' ? 1 : totals.get(b[0]) - totals.get(a[0])));
    const sig = scopes.map(([v]) => v).join(',');
    if (sel.dataset.sig !== sig) {
      sel.replaceChildren(...scopes.map(([v, l]) => new Option(v === 'All' ? l : `${l}: ${int(totals.get(v))} loans`, v)));
      sel.dataset.sig = sig;
    }
    const scope = scopes.some(([v]) => v === p.cscope) ? p.cscope : 'All';
    sel.value = scope;
    const agency = scope === 'All' ? p.agency : 'All';
    const data = rule.filter((r) => r.scope === scope && r.agency === agency).sort((a, b) => a.order - b.order);
    const ref = new Map(scope === 'All' ? [] : rule.filter((r) => r.scope === 'All' && r.agency === 'All').map((r) => [r.key, r]));
    const name = scope === 'All' ? (agency === 'All' ? 'All lenders' : `All lenders, ${AG_NAME[agency]}`) : (data[0] ? data[0].scope_label : '');
    legend(document.getElementById('choice-legend'), [[C_VS4, `Share priced on VS4: ${name}`, 'box']]
      .concat(ref.size ? [['var(--color-fg)', 'All lenders', 'diamond']] : []));
    const box = document.getElementById('choice-chart');
    if (!prep(box, st) || !data.length) return;
    const W = box.clientWidth, H = 270, m = { top: 22, right: 10, bottom: 46, left: 0 };
    const svg = svgFor(box, W, H, 'Share of loans with both scores priced on VS4, by bucket gap');
    const keys = [...new Set(rule.filter((r) => r.scope === 'All').sort((a, b) => a.order - b.order).map((r) => r.key))];
    const lab = (k) => GAP_TICK[k] ?? k;
    const y = d3.scaleLinear([0, 1], [H - m.bottom, m.top]);
    const yf = d3.format('.0%');
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    svg.append('text').attr('x', (m.left + W - m.right) / 2).attr('y', H - 4).attr('text-anchor', 'middle')
      .text('VS4 score bucket minus Classic FICO bucket');
    const bw = Math.min(40, x.bandwidth()), off = (x.bandwidth() - bw) / 2, cx = (r) => x(r.key) + x.bandwidth() / 2;
    svg.append('g').selectAll('rect').data(data).join('rect')
      .attr('x', (r) => x(r.key) + off).attr('width', bw).attr('y', (r) => y(r.vs4_share))
      .attr('height', (r) => Math.max(0, y(0) - y(r.vs4_share))).attr('rx', 3).attr('fill', C_VS4);
    if (bw >= textWidth(svg, ['100%']) + 2) {
      svg.append('g').selectAll('text').data(data).join('text').attr('x', cx)
        .attr('y', (r) => { const top = y(r.vs4_share), d = ref.has(r.key) ? y(ref.get(r.key).vs4_share) : Infinity; return d < top && top - d < 16 ? d - 9 : top - 6; })
        .attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').text((r) => d3.format('.0%')(r.vs4_share));
    }
    svg.append('g').selectAll('path').data(data.filter((r) => ref.has(r.key))).join('path')
      .attr('d', d3.symbol(d3.symbolDiamond, 44)).attr('transform', (r) => `translate(${cx(r)},${y(ref.get(r.key).vs4_share)})`)
      .attr('fill', 'var(--color-panel)').attr('stroke', 'var(--color-fg)');
    bandHover(svg, box, x, data, 'key', m, H, (r) => [r.label, [[C_VS4, name, `${pct1(r.vs4_share)} of ${int(r.loans)} loans`]]
      .concat(ref.has(r.key) ? [['var(--color-fg)', 'All lenders', `${pct1(ref.get(r.key).vs4_share)} of ${int(ref.get(r.key).loans)}`]] : [])]);
  }

  function drawCeiling(p) {
    const box = document.getElementById('ceiling-chart');
    const k = p.measure === 'upb' ? '_upb' : '';
    const lines = [[`actual${k}`, 'Actual', C_VS4], [`better${k}`, 'Wherever VS4 saves a fee', col(1)],
      [`higher${k}`, 'Wherever the VS4 score is higher', col(2)], [`not_worse${k}`, 'Wherever VS4 is no worse', col(3)]];
    legend(document.getElementById('ceiling-legend'), lines.map(([, l, c], i) => [c, l, 'line', i === 0]));
    if (!prep(box, dash.data('ceiling').status)) return;
    const data = rowsOf('ceiling').filter((r) => r.view === 'month' && r.agency === p.agency).sort((a, b) => (a.start < b.start ? -1 : 1));
    if (!data.length) return;
    const W = box.clientWidth, H = 240, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'VS4 share by issue month against its ceiling');
    const y = d3.scaleLinear([0, (d3.max(data, (r) => d3.max(lines, ([f]) => r[f] ?? 0)) || 0.01) * 1.08], [H - m.bottom, m.top]).nice(5);
    const yf = y.tickFormat(5, '%');
    const keys = data.map((r) => r.start), lab = monthLabel(keys);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    const xc = (r) => x(r.start) + x.bandwidth() / 2;
    lines.slice(1).forEach(([f, , c]) => estimateLine(svg, data, xc, (r) => r[f], y, c));
    partialLine(svg, data, xc, (r) => r[lines[0][0]], y, lines[0][2], 'final');
    bandHover(svg, box, x, data, 'start', m, H, (r) => [`${monthYear(r.start)}${r.final ? '' : ' (partial)'}`,
      lines.map(([f, l, c], i) => [c, i && r.estimated ? `${l} (estimate)` : l, pct1(r[f])]).concat([[null, 'Loans', int(r.loans)]])]);
  }

  // A line whose early periods are estimates: dashed with hollow points up to the first measured period.
  function estimateLine(svg, rows, xf, vf, y, color) {
    const ok = rows.filter((r) => vf(r) != null);
    const firm = ok.filter((r) => !r.estimated), est = ok.filter((r) => r.estimated);
    const line = d3.line().x(xf).y((r) => y(vf(r)));
    const style = (path) => path.attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2)
      .attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    if (firm.length > 1) style(svg.append('path').attr('d', line(firm)));
    if (est.length) style(svg.append('path').attr('d', line(est.concat(firm.slice(0, 1))))).attr('stroke-dasharray', '4 4');
    svg.append('g').selectAll('circle').data(ok).join('circle')
      .attr('cx', xf).attr('cy', (r) => y(vf(r))).attr('r', 2.5)
      .attr('fill', (r) => (r.estimated ? 'var(--color-panel)' : color)).attr('stroke', color).attr('stroke-width', 1.5);
  }

  function drawBands() {
    const table = document.getElementById('band-table');
    const st = dash.data('ceiling').status;
    const rows = rowsOf('ceiling').filter((r) => r.view === 'band').sort((a, b) => a.order - b.order);
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of rows) {
      const tr = body.insertRow();
      tr.dataset.key = [r.view, r.key].map(keyPart).join(',');
      [[rangeDash(r.label), 'vx-l'], [pct1(r.loan_share)], [pct1(r.better)], [pct1(r.higher)], [pct1(r.not_worse), 'vx-opt'], [int(r.measured), 'vx-opt'], [pct1(r.adds_better)]]
        .forEach(([text, cls]) => {
          const td = tr.insertCell();
          td.textContent = text;
          if (cls) td.className = cls;
        });
    }
  }

  function drawCeilingTile(p) {
    const st = dash.data('ceiling').status;
    const k = p.measure === 'upb' ? '_upb' : '';
    const r = rowsOf('ceiling').find((d) => d.view === 'both' && d.agency === p.agency) || {};
    const where = `view=both&agency=${enc(p.agency)}`;
    mark('.ce-better', `better${k}`, where, st, r[`better${k}`] == null ? null : pct1(r[`better${k}`]));
    mark('.ce-higher', `higher${k}`, where, st, r[`higher${k}`] == null ? null : pct1(r[`higher${k}`]));
    mark('.ce-actual', `actual${k}`, where, st, r[`actual${k}`] == null ? null : pct1(r[`actual${k}`]));
  }

  // A lender's rule in score points: the curve by point gap, and the 20-point line by week.
  function drawRules(p) {
    const st = dash.data('rules').status;
    const rows = rowsOf('rules');
    const scope = document.getElementById('choice-scope').value || 'All';
    const curve = rows.filter((r) => r.view === 'curve');
    const from = (curve[0] || {}).latest_from;
    const cohorts = [['earlier', from ? `First disclosed before ${shortDay(from)}` : 'Earlier', 'var(--color-fg-muted)'], ['latest', from ? `From ${shortDay(from)}` : 'Latest', C_VS4]];
    legend(document.getElementById('rule-curve-legend'), cohorts.map(([c, l, color]) => [color, l, 'line', c === 'latest']));
    const box = document.getElementById('rule-curve-chart');
    if (prep(box, st) && curve.length) {
      const bins = [...new Map(curve.slice().sort((a, b) => a.order - b.order).map((r) => [r.key, rangeDash(r.label)])).entries()];
      const mine = curve.filter((r) => r.scope === scope);
      const W = box.clientWidth, H = 260, m = { top: 14, right: 10, bottom: 44, left: 0 };
      const svg = svgFor(box, W, H, 'Share of loans with both scores priced on VS4, by points above Classic FICO');
      const keys = bins.map(([k]) => k), name = new Map(bins), lab = (k) => name.get(k);
      const y = d3.scaleLinear([0, 1], [H - m.bottom, m.top]);
      const yf = d3.format('.0%');
      const { x } = bandFrame(svg, keys, lab, y, yf, 5, W, m);
      yAxis(svg, y, yf, m.left, W - m.right);
      // Thinned by the point ranges: the one wide label, Below FICO, comes first and has room.
      bandAxis(svg, x, keys, lab, textWidth(svg, keys.slice(1).map(lab)), H - m.bottom + 8);
      svg.append('text').attr('x', (m.left + W - m.right) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text('VS4 minus Classic FICO (points)');
      const xc = (r) => x(r.key) + x.bandwidth() / 2;
      if (x('20_24') != null) {
        const lx = x('20_24') - (x.step() - x.bandwidth()) / 2;
        svg.append('line').attr('x1', lx).attr('x2', lx).attr('y1', m.top).attr('y2', H - m.bottom).attr('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '3 3');
        svg.append('text').attr('x', lx + 4).attr('y', H - m.bottom - 6).text('20 points');
      }
      // A bin with too few loans breaks the line, so it never reads as a measured point.
      for (const [c, , color] of cohorts) {
        const line = mine.filter((r) => r.cohort === c).sort((a, b) => a.order - b.order);
        line.reduce((runs, r, i) => {
          if (i && r.order !== line[i - 1].order + 1) runs.push([]);
          runs[runs.length - 1].push(r);
          return runs;
        }, [[]]).forEach((run) => estimateLine(svg, run, xc, (r) => r.vs4_share, y, color));
      }
      bandHover(svg, box, x, keys.map((key) => ({ key })), 'key', m, H, (r) => [`VS4 ${lab(r.key)}${r.key === 'lt0' ? '' : ' points above Classic FICO'}`,
        cohorts.map(([c, l, color]) => {
          const d = mine.find((e) => e.cohort === c && e.key === r.key);
          return [color, l, d ? `${pct1(d.vs4_share)} of ${int(d.loans)}` : 'too few loans'];
        })]);
    }
    const agency = scope === 'All' ? p.agency : 'All';
    const weeks = rows.filter((r) => r.view === 'week' && r.scope === scope && r.agency === agency).sort((a, b) => (a.week < b.week ? -1 : 1));
    const lines = [['under20_share', 'under20_loans', 'VS4 1–19 points above Classic FICO', C_VS4], ['over20_share', 'over20_loans', 'VS4 20 or more above', col(1)]];
    legend(document.getElementById('rule-week-legend'), lines.map(([, , l, c], i) => [c, l, 'line', i === 0]));
    const wbox = document.getElementById('rule-week-chart');
    if (!prep(wbox, st) || !weeks.length) return;
    const W = wbox.clientWidth, H = 260, m = { top: 14, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(wbox, W, H, 'Share priced on VS4 by week first disclosed, below and above the 20-point line');
    const y = d3.scaleLinear([0, 1], [H - m.bottom, m.top]);
    const yf = d3.format('.0%');
    const keys = weeks.map((r) => r.week);
    const { x, widest } = bandFrame(svg, keys, shortDay, y, yf, 5, W, m);
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, keys, shortDay, widest, H - m.bottom + 8);
    const xc = (r) => x(r.week) + x.bandwidth() / 2;
    for (const [f, , , c] of lines) estimateLine(svg, weeks, xc, (r) => r[f], y, c);
    bandHover(svg, wbox, x, weeks, 'week', m, H, (r) => [`Week of ${shortDay(r.week)}`,
      lines.map(([f, n, l, c]) => [c, l, r[f] == null ? `too few loans (${int(r[n])})` : `${pct1(r[f])} of ${int(r[n])}`])]);
  }

  // ---- Outlook ----
  const OL_STATUS = { heavy: 'Biggest user', using: 'Started', stopped: 'Stopped', none: 'Not yet' };
  const OL_CASES = [['recent', 'Nothing changes', 'var(--color-fg-muted)'], ['heavy', 'Biggest users go all the way', col(2)],
    ['users', 'Every lender using VS4 does', col(4)], ['pace', 'Other lenders start too', col(5)]];
  const olPicked = new Set();
  const olRows = (v) => rowsOf('outlook').filter((r) => r.view === v);
  const olName = (r, name = r.short) => (r.ticker && !new RegExp(`\\b${r.ticker}\\b`).test(name) ? `${name} (${r.ticker})` : name);
  const olPct = (v) => (v > 0 && v < 0.0005 ? '<0.1%' : pct1(v));
  const orDash = (fmt) => (v) => (v == null ? '—' : fmt(v));
  const olRung = (key, rule) => olRows('ladder').find((r) => r.key === key && (r.rule == null || r.rule === rule));
  const olWhere = (r) => `view=ladder&key=${r.key}${r.rule ? `&rule=${r.rule}` : ''}`;

  function drawOutlookRecent(p) {
    const st = dash.data('outlook').status;
    const k = p.measure === 'upb' ? '_upb' : '';
    const r = olRung('recent');
    const pr = olRows('params')[0] || {};
    mark('.ol-recent', `value${k}`, 'view=ladder&key=recent', st, r && r[`value${k}`] != null ? pct1(r[`value${k}`]) : null);
    mark('.ol-recent-from', 'recent_from', 'view=params', st, pr.recent_from ? shortDay(pr.recent_from) : null);
  }

  function drawOutlook(p) {
    const st = dash.data('outlook').status;
    const k = p.measure === 'upb' ? '_upb' : '';
    const rule = p.orule;
    const pr = olRows('params')[0] || {};
    const path = olRows('path').filter((r) => r.case === 'actual' || r.rule === rule);
    const pw = 'view=params';
    const val = (r, f, fmt) => (r && r[f] != null ? fmt(r[f]) : null);
    const f = `value${k}`;
    root.querySelectorAll('.ol-unit').forEach((el) => { el.textContent = k ? 'balances' : 'loans'; });
    mark('.ol-window', 'window_from', pw, st, pr.window_from
      ? (pr.window_from === pr.window_to ? monthYear(pr.window_to) : `${monthShortYear(pr.window_from)} to ${monthShortYear(pr.window_to)}`) : null);
    mark('.ol-heavy-names', 'heavy_names', pw, st, pr.heavy_names || null);
    mark('.ol-users', 'users', pw, st, val(pr, 'users', int));
    mark('.ol-user-share', `user_share${k}`, pw, st, val(pr, `user_share${k}`, pct1));
    mark('.ol-pace', `pace${k}`, pw, st, val(pr, `pace${k}`, pct1));
    mark('.ol-end', 'end_month', pw, st, val(pr, 'end_month', monthShortYear));
    drawOutlookRecent(p);
    for (const [cls, key] of [['ol-today', 'today'], ['ol-heavy-v', 'heavy'], ['ol-all', 'all'], ['ol-nw', 'not_worse']]) {
      const r = olRung(key, rule);
      mark(`.${cls}`, f, r ? olWhere(r) : null, st, val(r, f, pct1));
    }
    const end = path.find((r) => r.case === 'pace' && r.month === pr.end_month);
    mark('.ol-pace-v', f, `view=path&case=pace&rule=${rule}&month=${enc(pr.end_month ?? '')}`, st, val(end, f, pct1));
    // The first month the heavy users' case comes within 0.05 points of where it settles.
    const goal = (olRung('heavy', rule) || {})[f];
    const by = goal == null ? null : path.filter((r) => r.case === 'heavy' && r[f] >= goal - 0.0005).sort((a, b) => (a.month < b.month ? -1 : 1))[0];
    mark('.ol-heavy-by', 'month', by ? `view=path&case=heavy&rule=${rule}&month=${enc(by.month)}` : null, st, by ? monthShortYear(by.month) : null);
    const next = root.querySelector('#ol-pick [data-pick="next"]');
    if (next && pr.next_n) next.textContent = `Plus the ${pr.next_n} largest`;
    drawOutlookPaths(st, k, rule, path, pr);
    drawOutlookLadder(st, k, rule, pr);
    drawOutlookRamp(st, k);
    drawOutlookTable(p);
    drawOutlookPace(st, k);
  }

  function drawOutlookPaths(st, k, rule, path, pr) {
    const box = document.getElementById('ol-path-chart');
    const f = `value${k}`;
    legend(document.getElementById('ol-path-legend'), [[C_VS4, 'Actual', 'line', true]].concat(OL_CASES.map(([, l, c]) => [c, l, 'line'])));
    if (!prep(box, st) || !path.length) return;
    const refs = [['all', 'Every lender', col(3)]].concat(rule === 'better' ? [] : [['not_worse', 'Wherever VS4 is no worse', col(1)]])
      .map(([key, label, color]) => ({ label, color, v: (olRung(key, rule) || {})[f] })).filter((r) => r.v != null);
    const months = [...new Set(path.map((r) => r.month))].sort();
    const W = box.clientWidth, H = 300, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'VS4 share by issue month, actual and four cases');
    const top = Math.max(d3.max(path, (r) => r[f] ?? 0), d3.max(refs, (r) => r.v) ?? 0) || 0.01;
    const y = d3.scaleLinear([0, top * 1.08], [H - m.bottom, m.top]).nice(5);
    const yf = y.tickFormat(5, '%');
    const lab = monthLabel(months);
    const { x, widest } = bandFrame(svg, months, lab, y, yf, 5, W, m);
    const xc = (mo) => x(mo) + x.bandwidth() / 2;
    if (pr.window_to && x(pr.window_to) != null) {
      const x0 = xc(pr.window_to);
      svg.append('rect').attr('x', x0).attr('width', Math.max(0, W - m.right - x0)).attr('y', m.top)
        .attr('height', H - m.top - m.bottom).attr('fill', 'var(--cds-chart-grid)').attr('fill-opacity', 0.6);
    }
    yAxis(svg, y, yf, m.left, W - m.right);
    bandAxis(svg, x, months, lab, widest, H - m.bottom + 8);
    for (const r of refs) {
      svg.append('line').attr('x1', m.left).attr('x2', W - m.right).attr('y1', y(r.v)).attr('y2', y(r.v))
        .attr('stroke', r.color).attr('stroke-width', 1.5).attr('stroke-dasharray', '5 4');
      svg.append('text').attr('x', m.left + 6).attr('y', y(r.v) - 6).text(`${r.label}: ${pct1(r.v)}`);
    }
    const line = d3.line().x((r) => xc(r.month)).y((r) => y(r[f]));
    for (const [c, , color] of OL_CASES) {
      svg.append('path').attr('d', line(path.filter((r) => r.case === c && r[f] != null))).attr('fill', 'none')
        .attr('stroke', color).attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    }
    partialLine(svg, path.filter((r) => r.case === 'actual'), (r) => xc(r.month), (r) => r[f], y, C_VS4, 'final');
    bandHover(svg, box, x, months.map((month) => ({ month })), 'month', m, H, (r) => {
      const at = new Map(path.filter((d) => d.month === r.month && d[f] != null).map((d) => [d.case, d]));
      const lines = at.has('actual') ? [[C_VS4, at.get('actual').final ? 'Actual' : 'Actual so far', pct1(at.get('actual')[f])]] : [];
      for (const [c, l, color] of OL_CASES) if (at.has(c)) lines.push([color, l, pct1(at.get(c)[f])]);
      return [monthYear(r.month), lines];
    });
  }

  function drawOutlookLadder(st, k, rule, pr) {
    const box = document.getElementById('ol-ladder-chart');
    if (!prep(box, st)) return;
    const f = `value${k}`;
    const names = { today: 'Today', recent: 'Latest two weeks', heavy: 'The biggest users', users: 'Every lender using VS4',
      next: `And the ${pr.next_n ?? ''} largest not using it`, all: 'Every lender', not_worse: 'Wherever VS4 is no worse' };
    const items = ['today', 'recent', 'heavy', 'users', 'next', 'all', 'not_worse'].map((key) => olRung(key, rule)).filter((r) => r && r[f] != null);
    if (!items.length) return;
    // Labels sit left of the bars, or above them where the card is narrow.
    const W = box.clientWidth, narrow = W < 480, rowH = narrow ? 48 : 34, m = { top: 4, right: 12, bottom: 24, left: 0 };
    const H = m.top + m.bottom + items.length * rowH;
    box.style.minHeight = `${H}px`;
    const svg = svgFor(box, W, H, "VS4's share once each group of lenders is on the rule");
    m.left = narrow ? Math.ceil(textWidth(svg, ['0%']) / 2) + 2
      : Math.min(Math.ceil(textWidth(svg, items.map((r) => names[r.key]))) + 14, Math.max(120, Math.floor(W * 0.45)));
    const tail = Math.ceil(textWidth(svg, ['00.0% (+00.0 pts)'])) + 8;
    const x = d3.scaleLinear([0, d3.max(items, (r) => r[f])], [m.left, Math.max(m.left + 40, W - m.right - tail)]).nice(4);
    const ticks = x.ticks(Math.max(2, Math.min(4, Math.floor((x.range()[1] - m.left) / 48))));
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', (v) => x(v)).attr('x2', (v) => x(v))
      .attr('y1', m.top).attr('y2', H - m.bottom).attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-axis)' : 'var(--cds-chart-grid)'));
    svg.append('g').attr('transform', `translate(0,${H - m.bottom + 8})`)
      .call(d3.axisBottom(x).tickValues(ticks).tickFormat(d3.format('.0%')).tickSize(0)).call(styleAxis);
    const yb = d3.scaleBand(items.map((r) => r.key), [m.top, H - m.bottom]).paddingInner(0.3);
    const top = (r) => yb(r.key) + (narrow ? 18 : 0), bh = narrow ? yb.bandwidth() - 18 : yb.bandwidth();
    const cy = (r) => top(r) + bh / 2;
    const color = (r) => (r.key === 'not_worse' ? col(1) : C_VS4);
    const g = svg.append('g').selectAll('g').data(items).join('g');
    g.append('text').attr('x', narrow ? m.left + 4 : m.left - 10).attr('y', (r) => (narrow ? yb(r.key) + 7 : cy(r))).attr('dy', '0.35em')
      .attr('text-anchor', narrow ? 'start' : 'end').style('fill', 'var(--color-fg)').text((r) => names[r.key])
      .each(function () { clip(this, narrow ? W - m.left : m.left - 14); });
    g.append('rect').attr('x', m.left).attr('width', (r) => Math.max(1, x(r[f]) - m.left)).attr('y', top)
      .attr('height', bh).attr('rx', 3).attr('fill', color).attr('fill-opacity', (r) => (r.key === 'today' ? 1 : 0.7));
    // Each step is taken between the printed levels, so the labels add up.
    const printed = (r) => parseFloat(pct1(r[f])) / 100;
    g.append('text').attr('x', (r) => x(r[f]) + 6).attr('y', cy).attr('dy', '0.35em').style('fill', 'var(--color-fg)')
      .text((r, i) => (i && r.key !== 'not_worse' ? `${pct1(r[f])} (${pts(printed(r) - printed(items[i - 1]))})` : pct1(r[f])));
    const tip = tooltip(box);
    g.append('rect').attr('x', 0).attr('width', W).attr('y', (r) => yb(r.key) - 3).attr('height', yb.bandwidth() + 6)
      .attr('fill', 'transparent')
      .on('pointermove', (event, r) => tip.show(event, names[r.key], [[color(r), 'VS4 share', pct1(r[f])]]
        .concat(r.lenders ? [[null, 'Lenders moved', int(r.lenders)]] : [])))
      .on('pointerleave', () => tip.hide());
  }

  function drawOutlookRamp(st, k) {
    const box = document.getElementById('ol-ramp-chart');
    const ramp = olRows('ramp');
    const each = ramp.filter((r) => r.id != null), pooled = ramp.filter((r) => r.id == null).sort((a, b) => a.m - b.m);
    const ids = [...new Map(each.map((r) => [r.id, r.short])).entries()];
    const colorOf = new Map(ids.map(([id], i) => [id, col(i + 5)]));
    legend(document.getElementById('ol-ramp-legend'), ids.map(([id, s]) => [colorOf.get(id), s, 'line'])
      .concat([['var(--color-fg)', 'Path the cases use', 'line', true]]));
    if (!prep(box, st) || !ramp.length) return;
    const qf = `q${k}`;
    const pathAt = (mm) => (mm < pooled.length ? pooled[mm][`r${k}`] : 1);
    const keys = d3.range(0, Math.max(d3.max(each, (r) => r.m) ?? 0, pooled.length) + 2);
    const W = box.clientWidth, H = 210, m = { top: 12, right: 10, bottom: 40, left: 0 };
    const svg = svgFor(box, W, H, "Heavy users' VS4 share as a share of their level in the latest two weeks, by months since their first VS4 loan");
    const y = d3.scaleLinear([0, Math.max(1, d3.max(each, (r) => r[qf] ?? 0) ?? 0)], [H - m.bottom, m.top]).nice(4);
    const yf = d3.format('.0%');
    const lab = (mm) => String(mm);
    const { x, widest } = bandFrame(svg, keys, lab, y, yf, 4, W, m);
    yAxis(svg, y, yf, m.left, W - m.right, 4);
    bandAxis(svg, x, keys, lab, widest, H - m.bottom + 8);
    svg.append('text').attr('x', (m.left + W - m.right) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text('Months since first VS4 loan');
    const xc = (mm) => x(mm) + x.bandwidth() / 2;
    for (const [id] of ids) {
      const rows = each.filter((r) => r.id === id && r[qf] != null).sort((a, b) => a.m - b.m);
      svg.append('path').attr('d', d3.line().x((r) => xc(r.m)).y((r) => y(r[qf]))(rows)).attr('fill', 'none')
        .attr('stroke', colorOf.get(id)).attr('stroke-width', 1.5);
    }
    svg.append('path').attr('d', d3.line()(keys.map((mm) => [xc(mm), y(pathAt(mm))]))).attr('fill', 'none')
      .attr('stroke', 'var(--color-fg)').attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    bandHover(svg, box, x, keys.map((mm) => ({ mm })), 'mm', m, H, (r) => [
      r.mm === 0 ? 'First VS4 month' : `${r.mm} month${r.mm === 1 ? '' : 's'} on`,
      ids.map(([id, s]) => [colorOf.get(id), s, (each.find((d) => d.id === id && d.m === r.mm) || {})[qf]])
        .filter((l) => l[2] != null).map(([c, s, v]) => [c, s, pct1(v)])
        .concat([['var(--color-fg)', 'Path the cases use', pct1(pathAt(r.mm))]])]);
  }

  function drawOutlookTable(p) {
    const table = document.getElementById('ol-table');
    if (!table) return;
    const st = dash.data('outlook').status;
    const upb = p.measure === 'upb', k = upb ? '_upb' : '', rule = p.orule;
    const cols = [['name', 'short', (v, r) => (r.id === 'other' ? 'All other lenders' : olName(r))],
      ['status', 'status', (v, r) => (v === 'other' ? `${int(r.sellers)} lenders` : OL_STATUS[v] || v)],
      ['share', `share${k}`, olPct], ['vs4', upb ? 'vs4_upb_share' : 'vs4_share', pct1], ['recent', upb ? 'recent_upb_share' : 'recent_share', pct1],
      ['uses', 'higher_vs4', pct1], ['both', 'both_share', pct1], ['on', `on_${rule}${k}`, pct1],
      ['adds', `adds_${rule}${k}`, (v) => (v > 0 && v < 0.0005 ? '<0.1' : fixed(1)(v * 100))]];
    table.querySelector('th[data-col="share"] button').textContent = upb ? 'Share of balance' : 'Share of loans';
    const s = sorts['ol-table'];
    table.querySelectorAll('th[data-col]').forEach((th) => {
      const c = cols.find((x) => x[0] === th.dataset.col);
      if (c) th.setAttribute('data-field', c[1]);
      if (th.dataset.col === s.col) th.setAttribute('aria-sort', s.dir);
      else th.removeAttribute('aria-sort');
    });
    const sc = cols.find((x) => x[0] === s.col) || cols[cols.length - 1];
    const rows = olRows('lender');
    const sorted = rows.filter((r) => r.id !== 'other').sort((a, b) => {
      const va = a[sc[1]], vb = b[sc[1]];
      if (va == null || vb == null) return (va == null) - (vb == null) || a.rank - b.rank;
      const c = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return (s.dir === 'ascending' ? c : -c) || a.rank - b.rank;
    }).concat(rows.filter((r) => r.id === 'other'));
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const heads = table.tHead.rows[0].cells;
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of sorted) {
      const tr = body.insertRow();
      tr.dataset.key = ['lender', r.id].map(keyPart).join(',');
      if (r.id === 'other') tr.dataset.pin = '';
      const cell = tr.insertCell();
      cell.className = heads[0].className;
      const tick = document.createElement('input');
      tick.type = 'checkbox';
      tick.className = 'ol-check';
      tick.value = r.id;
      tick.checked = olPicked.has(r.id);
      tick.setAttribute('aria-label', `Pick ${olName(r)}`);
      cell.append(tick);
      cols.forEach(([, f, fmt], i) => {
        const td = tr.insertCell();
        td.textContent = r[f] == null ? '—' : fmt(r[f], r);
        td.className = heads[i + 1].className;
      });
    }
    document.getElementById('ol-table-foot').textContent = rows.length ? `A dash: fewer than 20 loans show both scores with VS4 higher.${upb ? ' Both scores and Uses VS4 when higher stay on loans.' : ''}` : '';
    drawOutlookPick(p);
  }

  // The picked lenders on the rule, everyone else at the latest weeks' share.
  function drawOutlookPick(p) {
    if (!root.querySelector('.ol-pick-line')) return;
    const k = p.measure === 'upb' ? '_upb' : '';
    const base = (olRung('recent') || {})[`value${k}`];
    const picked = olRows('lender').filter((r) => olPicked.has(r.id));
    const add = d3.sum(picked, (r) => r[`adds_${p.orule}${k}`] || 0);
    const n = d3.sum(picked, (r) => r.sellers || 1);
    root.querySelector('.ol-pick-n').textContent = `${int(n)} lender${n === 1 ? '' : 's'}`;
    root.querySelector('.ol-pick-v').textContent = base == null ? '—' : pct1(base + add);
    root.querySelector('.ol-pick-d').textContent = picked.length ? `(${pts(add)} from the latest weeks)` : '';
  }

  function pickLenders(how) {
    olPicked.clear();
    for (const r of olRows('lender')) {
      const using = r.status === 'heavy' || r.status === 'using';
      if (how === 'all' || ((how === 'users' || how === 'next') && using) || (how === 'next' && r.next)) olPicked.add(r.id);
    }
    drawOutlookTable(params());
  }

  function drawOutlookPace(st, k) {
    const table = document.getElementById('ol-pace-table');
    if (!table) return;
    const rows = olRows('pace').sort((a, b) => (a.key === 'all') - (b.key === 'all') || (a.month < b.month ? -1 : 1));
    const fields = ['month', 'new_sellers', `new_share${k}`, `pool_share${k}`, `rate${k}`];
    const heads = table.tHead.rows[0].cells;
    heads[2].textContent = k ? 'Their share of balance' : 'Their share of loans';
    fields.forEach((f, i) => heads[i].setAttribute('data-field', f));
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of rows) {
      const tr = body.insertRow();
      tr.dataset.key = ['pace', r.key].map(keyPart).join(',');
      [r.key === 'all' ? 'All months' : monthYear(r.month), orDash(int)(r.new_sellers), orDash(pct1)(r[fields[2]]),
        orDash(pct1)(r[fields[3]]), orDash(pct1)(r[fields[4]])].forEach((text, i) => {
        const td = tr.insertCell();
        td.textContent = text;
        td.className = heads[i].className;
      });
    }
  }

  // ---- Why lenders choose ----
  const STAGE_COLOR = { pricing: C_VS4, some: col(2), both: col(1), trace: col(3), fico: 'var(--cds-chart-muted)' };
  const STAGE_SHORT = { pricing: 'Prices on VS4', some: 'Sometimes', both: 'Shows both', trace: 'A few on VS4', fico: 'None on VS4' };
  const RULE_TEXT = { whenever: 'Whenever VS4 is higher', moving: '20-point rule, moving', line: '20-point rule', some: 'Some loans', rare: 'Rarely' };
  const whyRows = (v) => rowsOf('lender_stage').filter((r) => r.view === v);
  const shareHead = (k) => (k ? 'Share of balance' : 'Share of loans');

  function drawWhy(p) {
    const st = dash.data('lender_stage').status;
    const k = p.measure === 'upb' ? '_upb' : '';
    const stages = whyRows('stage').sort((a, b) => a.order - b.order);
    const f = `share${k}`;
    const box = document.getElementById('stage-chart');
    if (prep(box, st) && stages.length) {
      const W = box.clientWidth, H = 36;
      const svg = svgFor(box, W, H, `${shareHead(k)} by stage`);
      const x = d3.scaleLinear([0, 1], [0, W]);
      let at = 0;
      const tip = tooltip(box);
      for (const r of stages) {
        const v = r[f] || 0;
        svg.append('rect').attr('x', x(at)).attr('y', 4).attr('width', Math.max(0, x(v) - 1)).attr('height', 26).attr('fill', STAGE_COLOR[r.key])
          .on('pointermove', (event) => tip.show(event, r.label, [[STAGE_COLOR[r.key], shareHead(k), pct1(v)], [null, 'Lenders', int(r.lenders)]]))
          .on('pointerleave', () => tip.hide());
        if (x(v) > 54) svg.append('text').attr('x', x(at) + 6).attr('y', 17).attr('dy', '0.35em').style('fill', inkOn(STAGE_COLOR[r.key])).style('pointer-events', 'none').text(pct1(v));
        at += v;
      }
    }
    const table = document.getElementById('stage-table');
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    table.tHead.rows[0].cells[2].setAttribute('data-field', f);
    table.tHead.rows[0].cells[2].textContent = shareHead(k);
    table.tHead.rows[0].cells[4].setAttribute('data-field', `vs4${k}_share`);
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of stages) {
      const tr = body.insertRow();
      tr.dataset.key = ['stage', r.key].map(keyPart).join(',');
      const name = tr.insertCell();
      name.className = 'vx-l';
      const sw = document.createElement('span');
      sw.className = 'mx-swatch';
      sw.style.background = STAGE_COLOR[r.key];
      name.append(sw, r.label);
      [int(r.lenders), pct1(r[f]), pct1(r.both_share), pct1(r[`vs4${k}_share`])].forEach((text) => { tr.insertCell().textContent = text; });
    }
    const sel = document.getElementById('why-stage');
    if (sel.options.length !== stages.length + 1) {
      const keep = sel.value;
      sel.replaceChildren(new Option('All stages', 'all'), ...stages.map((r) => new Option(r.label, r.key)));
      sel.value = keep || 'all';
    }
    drawWhyTable(p);
    drawWarnings(p, st);
    drawGoes(p, st);
    drawTraits(st);
    drawSaid();
  }

  function drawWhyTable(p) {
    const table = document.getElementById('why-table');
    if (!table) return;
    const st = dash.data('lender_stage').status;
    const k = p.measure === 'upb' ? '_upb' : '';
    const stage = document.getElementById('why-stage').value || 'all';
    const rows = whyRows('lender').filter((r) => stage === 'all' || r.stage === stage);
    const cols = [['name', 'short', (v, r) => olName(r)], ['kind', 'kind', String], ['lead', 'lead', String], ['stage', 'order', (v, r) => STAGE_SHORT[r.stage]],
      ['share', `share${k}`, pct1], ['both', 'both_share', pct1], ['uses', 'uses_higher', pct1], ['rule', 'rule', (v) => RULE_TEXT[v] || v],
      ['vs4', `vs4${k}_share`, pct1], ['recent', 'recent_share', pct1]];
    const s = sorts['why-table'];
    table.querySelectorAll('th[data-col]').forEach((th) => {
      const c = cols.find((x) => x[0] === th.dataset.col);
      if (c) th.setAttribute('data-field', c[1]);
      if (th.dataset.col === 'share') th.querySelector('button').textContent = shareHead(k);
      if (th.dataset.col === s.col) th.setAttribute('aria-sort', s.dir);
      else th.removeAttribute('aria-sort');
    });
    const sc = cols.find((x) => x[0] === s.col) || cols[4];
    const sorted = rows.slice().sort((a, b) => {
      const va = a[sc[1]], vb = b[sc[1]];
      if (va == null || vb == null) return (va == null) - (vb == null) || a.rank - b.rank;
      const c = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return (s.dir === 'ascending' ? c : -c) || a.rank - b.rank;
    });
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const heads = table.tHead.rows[0].cells;
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of sorted) {
      const tr = body.insertRow();
      tr.dataset.key = ['lender', r.id].map(keyPart).join(',');
      cols.forEach(([, f, fmt], i) => {
        const td = tr.insertCell();
        td.textContent = r[f] == null ? (f === 'rule' && r.uses_higher != null ? 'Too few loans' : '—') : fmt(r[f], r);
        td.className = heads[i].className;
      });
    }
  }

  function drawWarnings(p, st) {
    const table = document.getElementById('warning-table');
    const k = p.measure === 'upb' ? '_upb' : '';
    const rows = whyRows('lender').filter((r) => r.stage !== 'pricing' && r.both_early != null && r.both_late != null && r.both_late - r.both_early >= 0.02)
      .sort((a, b) => (b.both_late - b.both_early) - (a.both_late - a.both_early)).slice(0, 12);
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const heads = table.tHead.rows[0].cells;
    heads[1].setAttribute('data-field', `share${k}`);
    heads[1].textContent = shareHead(k);
    heads[4].setAttribute('data-field', `vs4${k}_share`);
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of rows) {
      const tr = body.insertRow();
      tr.dataset.key = ['lender', r.id].map(keyPart).join(',');
      [olName(r), pct1(r[`share${k}`]), pct1(r.both_early), pct1(r.both_late), pct1(r[`vs4${k}_share`])].forEach((text, i) => {
        const td = tr.insertCell();
        td.textContent = text;
        td.className = heads[i].className;
      });
    }
  }

  function drawGoes(p, st) {
    const table = document.getElementById('goes-table');
    const k = p.measure === 'upb' ? '_upb' : '';
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    table.tHead.rows[0].cells[3].textContent = shareHead(k);
    const body = table.tBodies[0];
    body.replaceChildren();
    const add = (r, label) => {
      const tr = body.insertRow();
      tr.dataset.key = [r.view, r.key].map(keyPart).join(',');
      // The channel rows have no balance figures.
      const shares = r.view === 'channel' ? (k ? '—' : pct1(r.share)) : pct1(r[`share${k}`]);
      const vs = r.view === 'channel' ? (k ? '—' : pct1(r.vs4_share)) : pct1(r[`vs4${k}_share`]);
      [[label, 'vx-l'], [r.lenders == null ? '—' : int(r.lenders), 'vx-opt'], [r.using == null ? '—' : int(r.using)], [shares], [pct1(r.both_share)], [vs]].forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
    };
    for (const r of whyRows('kind').sort((a, b) => a.order - b.order)) add(r, r.label);
    for (const r of whyRows('lead').sort((a, b) => a.order - b.order)) add(r, r.label);
    const top = (rowsOf('summary').find((r) => r.agency === 'All') || {}).top2_sellers ? 'two largest' : 'largest';
    for (const r of whyRows('channel').sort((a, b) => a.order - b.order)) add(r, `${r.label}, ${r.scope === 'top' ? top : 'other lenders'}`);
  }

  function drawTraits(st) {
    const table = document.getElementById('trait-table');
    const rows = whyRows('trait');
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const scopes = [...new Map(rows.map((r) => [r.scope, r.label])).entries()];
    const order = ['All'].concat(scopes.map(([s]) => s).filter((s) => s !== 'All' && s !== 'rest'), ['rest']).filter((s) => scopes.some(([x]) => x === s));
    const name = new Map(scopes);
    const head = table.tHead.rows[0];
    head.replaceChildren();
    const th0 = document.createElement('th');
    th0.scope = 'col';
    th0.className = 'vx-l';
    th0.textContent = 'Loan trait';
    head.append(th0);
    for (const s of order) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.setAttribute('data-field', 'vs4_share');
      th.textContent = name.get(s);
      head.append(th);
    }
    const body = table.tBodies[0];
    body.replaceChildren();
    const dimOrder = { mi: 0, purpose: 1, channel: 2, ltv: 3, program: 4 };
    const keys = [...new Map(rows.map((r) => [`${r.dim}|${r.key}`, r])).values()].sort((a, b) => dimOrder[a.dim] - dimOrder[b.dim] || a.key.localeCompare(b.key));
    for (const t of keys) {
      const tr = body.insertRow();
      const td0 = tr.insertCell();
      td0.className = 'vx-l';
      td0.textContent = t.dim === 'ltv' ? `LTV ${rangeDash(t.key.toLowerCase())}` : t.key;
      for (const s of order) {
        const r = rows.find((d) => d.dim === t.dim && d.key === t.key && d.scope === s);
        const td = tr.insertCell();
        td.textContent = r ? d3.format('.0%')(r.vs4_share) : '—';
        if (r) td.title = `${int(r.loans)} loans`;
      }
    }
  }

  function saidCheck(r) {
    if (r.check === 'seller') {
      const l = whyRows('lender').find((d) => d.id === r.seller_id);
      if (!l) return '—';
      const fe = rowsOf('fees').find((d) => d.view === 'lender' && d.id === r.seller_id);
      return `${pct1(l.vs4_share)} priced on VS4, ${l.recent_share == null ? '—' : pct1(l.recent_share)} in the latest weeks; both scores on ${pct1(l.both_share)}; VS4 used on ${l.uses_higher == null ? '—' : pct1(l.uses_higher)} of loans where it is higher.${fe && fe.saving_avg_usd != null ? ` VS4 loans that save a fee save ${money(fe.saving_avg_usd)} on average.` : ''}`;
    }
    const mix = rowsOf('score_mix');
    const head = mix.find((d) => d.view === 'month' && d.agency === 'All' && d.headline) || {};
    const fn = mix.find((d) => d.view === 'month' && d.agency === 'FNMA' && d.start === head.start) || {};
    if (r.check === 'fico') {
      if (head.fico_share == null) return '—';
      const all = rowsOf('outlook').find((d) => d.view === 'ladder' && d.key === 'all' && d.rule === 'better');
      return `At least ${pct1(head.fico_share)} of loans have a Classic FICO (${pct1(fn.fico_share)} at Fannie Mae); at most ${pct1(head.vs_only_share)} have only VS4 (${pct1(fn.vs_only_share)}).${all ? ` Priced on VS4 wherever it saves a fee, VS4 would reach about ${d3.format('.0%')(all.value)}.` : ''}`;
    }
    if (r.check === 'lenders') {
      const pr = olRows('params')[0] || {};
      const using = d3.sum(whyRows('stage').filter((d) => d.key === 'pricing' || d.key === 'some'), (d) => d.lenders);
      return `${pr.users == null ? '—' : int(pr.users)} lenders have delivered a VS4 loan to the GSEs since September, and ${int(using)} price on it regularly. At most ${head.vs_only_share == null ? '—' : pct1(head.vs_only_share)} of loans have only VS4. This covers GSE loans only.`;
    }
    if (r.check === 'pricing') {
      const o = rowsOf('pricing').find((d) => d.view === 'overall' && d.cover === 'all' && d.basis === 'headline');
      return o ? `${bpSigned(o.net_bp)} bp in the same fee tier, on loans first disclosed from July 20, net of the model's miss.` : '—';
    }
    if (r.check === 'fees') {
      const fm = rowsOf('fees').find((d) => d.view === 'market' && d.key === 'All') || {};
      return fm.option_annual_usd == null ? '—' : `On the grid, ${usdM(fm.taken_annual_usd)} a year in fees not paid at today's use, ${usdM(fm.option_annual_usd)} if every lender took the lower fee.`;
    }
    if (r.check === 'august') {
      const a = rowsOf('monthly').find((d) => d.agency === 'All' && d.month === '2026-08-01');
      return a ? `${pct1(a.vs4_share)} in August here.` : '—';
    }
    return 'No loan-data check';
  }

  function drawSaid() {
    const table = document.getElementById('said-table');
    const st = dash.data('statements').status;
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of rowsOf('statements').slice().sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : a.order - b.order))) {
      const tr = body.insertRow();
      tr.dataset.key = [r.date, r.who, r.source].map(keyPart).join(',');
      const cells = [[shortDay(r.date), 'vx-l'], [r.who, 'vx-l'], [r.statement, 'vx-l vx-wrap'], [saidCheck(r), 'vx-l vx-opt vx-wrap']];
      for (const [text, cls] of cells) {
        const td = tr.insertCell();
        td.textContent = text;
        td.className = cls;
      }
      const link = tr.insertCell();
      link.className = 'vx-l';
      const a = document.createElement('a');
      a.className = 'vx-link';
      a.href = r.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = r.source;
      link.append(a);
    }
  }

  // ---- Score mix, on the Overview ----
  const MIX_GROUPS = [['fico_only', 'Shows Classic FICO only', 'var(--cds-chart-muted)'], ['both_fico', 'Shows both, priced on Classic FICO', col(1)],
    ['both_vs', 'Shows both, priced on VS4', C_VS4], ['vs_only', 'Shows VS4 only', col(4)]];

  function drawScoreMix(p) {
    const st = dash.data('score_mix').status;
    const rows = rowsOf('score_mix');
    const k = p.measure === 'upb' ? '_upb' : '';
    const head = rows.find((r) => r.view === 'month' && r.agency === 'All' && r.headline) || {};
    const month = (a) => rows.find((r) => r.view === 'month' && r.agency === a && r.start === head.start);
    const where = (a) => `view=month&start=${enc(head.start ?? '')}&agency=${a}`;
    mark('.mx-month', 'start', where('All'), st, head.start ? monthYear(head.start) : null);
    const fico = `fico${k}_share`;
    root.querySelector('.mx-fico-lbl').textContent = k ? 'Balance' : 'Loans';
    root.querySelector('.mx-fico-unit').textContent = k ? 'the balance of loans' : 'loans';
    mark('.mx-fico-tile', fico, where('All'), st, head[fico] == null ? null : pct1(head[fico]));
    mark('.h-fico', 'fico_share', where('All'), st, head.fico_share == null ? null : pct1(head.fico_share));
    const fn = month('FNMA') || {};
    mark('.mx-fico-fn', fico, where('FNMA'), st, fn[fico] == null ? null : pct1(fn[fico]));
    const top = rows.filter((r) => r.view === 'vs_only' && r.agency === 'FNMA').sort((a, b) => b.loans - a.loans)[0] || {};
    const tw = `view=vs_only&agency=FNMA&seller_id=${enc(top.seller_id ?? '')}`;
    mark('.mx-top-name', 'scope_label', tw, st, top.scope_label || null);
    mark('.mx-top-share', 'of_vs_only', tw, st, top.of_vs_only == null ? null : pct1(top.of_vs_only));
  }

  function drawQuarters(p) {
    const table = document.getElementById('quarter-table');
    const st = dash.data('score_mix').status;
    const k = p.measure === 'upb' ? '_upb' : '';
    const rows = rowsOf('score_mix').filter((r) => r.view === 'quarter' && r.agency === p.agency && r.vs4_priced_share >= 0.0005).sort((a, b) => (a.start < b.start ? 1 : -1));
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    table.tHead.rows[0].cells[3].setAttribute('data-field', `vs4_priced${k}_share`);
    const qName = (s) => { const d = parse(s); return `Q${Math.floor(d.getUTCMonth() / 3) + 1} ${d.getUTCFullYear()}`; };
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const r of rows) {
      const tr = body.insertRow();
      tr.dataset.key = ['quarter', r.start, r.agency].map(keyPart).join(',');
      [[`${qName(r.start)}${r.complete && r.months === 3 ? '' : ' so far'}`, 'vx-l'], [int(r.loans)], [usdM(r.upb)], [pct1(r[`vs4_priced${k}_share`])]].forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
    }
  }

  // ---- Borrowers ----
  const GRP_NAME = { vs4: 'Priced on VS4', fico: 'Priced on FICO' };
  const COVER_NOTE = {
    both: 'Loans disclosed with every score (records since Oct 19, 2026) that show both scores: priced on VS4 against priced on Classic FICO.',
    vs4only: 'VS4-priced loans that show no Classic FICO among loans disclosed with every score (records since Oct 19, 2026), against every FICO-priced loan disclosed that way. Read with care: a loan can have a FICO that does not show, so this group mixes loans with one score and loans with a hidden FICO. Fannie Mae\'s few such loans are the cleaner read.',
  };
  const keyPart = (v) => encodeURIComponent(String(v));
  const bpSigned = ptsSigned;
  const bpTick = (v) => (v === 0 ? '0' : d3.format('+')(v));

  function drawMix(p) {
    const box = document.getElementById('mix-chart');
    const dimSel = document.getElementById('mix-dim');
    const all = rowsOf('borrowers').filter((r) => r.cover === p.cover);
    const dims = [...new Map(all.map((r) => [r.dim, r.dim_label])).entries()];
    const sig = `${p.cover}:${dims.map(([d]) => d).join(',')}`;
    if (dimSel.dataset.sig !== sig) {
      dimSel.replaceChildren(...dims.map(([v, l]) => new Option(l, v)));
      dimSel.dataset.sig = sig;
    }
    const dim = dims.some(([v]) => v === p.dim) ? p.dim : dims.length ? dims[0][0] : null;
    if (dim) dimSel.value = dim;
    const data = all.filter((r) => r.dim === dim).sort((a, b) => a.bucket_order - b.bucket_order);
    const grps = ['vs4', 'fico'].filter((g) => data.some((r) => r.grp === g));
    const hasExp = data.some((r) => r.grp === 'vs4' && r.expected != null);
    const color = (g) => (g === 'vs4' ? C_VS4 : 'var(--cds-chart-muted)');
    const groupN = (g) => {
      const n = data.find((r) => r.grp === g).group_loans;
      const whole = (rowsOf('borrower_profile').find((r) => r.cover === p.cover && r.grp === g) || {}).loans;
      return whole && whole - n < 0.001 * whole ? whole : n;  // a few blank fields; the rate view's 30-year fixed subset keeps its own count
    };
    legend(document.getElementById('mix-legend'), grps.map((g) => [color(g), `${GRP_NAME[g]}, ${int(groupN(g))} loans`, 'box'])
      .concat(hasExp ? [['var(--color-fg)', 'VS4 if it matched its lenders’ FICO loans', 'line']] : []));
    if (!prep(box, dash.data('borrowers').status)) return;
    document.getElementById('mix-tick-note').hidden = !hasExp;
    const buckets = [...new Set(data.map((r) => r.bucket))];
    if (!buckets.length) return;
    const W = box.clientWidth, barH = 11, gap = 14;
    const groupH = grps.length * barH + 4;
    const m = { top: 4, right: 0, bottom: 4, left: 0 };
    const H = m.top + m.bottom + buckets.length * (groupH + gap);
    box.style.minHeight = `${H}px`;
    const svg = svgFor(box, W, H, 'Borrower mix of VS4 and Classic FICO loans');
    m.left = Math.ceil(textWidth(svg, buckets.map(rangeDash))) + 10;
    m.right = Math.ceil(textWidth(svg, data.map((r) => pct1(r.share)))) + 8;
    const x = d3.scaleLinear([0, d3.max(data, (r) => Math.max(r.share, r.expected ?? 0)) || 1], [m.left, W - m.right]);
    const yb = d3.scaleBand(buckets, [m.top, H - m.bottom]).paddingInner(gap / (groupH + gap));
    const yi = d3.scaleBand(grps, [0, yb.bandwidth()]).paddingInner(0.2);
    svg.append('g').selectAll('text').data(buckets).join('text')
      .attr('x', m.left - 10).attr('y', (b) => yb(b) + yb.bandwidth() / 2).attr('dy', '0.35em')
      .attr('text-anchor', 'end').style('fill', 'var(--color-fg)').text(rangeDash);
    svg.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', m.top).attr('y2', H - m.bottom).attr('stroke', 'var(--cds-chart-axis)');
    const tip = tooltip(box);
    const g = svg.append('g').selectAll('g').data(data).join('g');
    const top = (r) => yb(r.bucket) + yi(r.grp);
    g.append('rect').attr('x', x(0)).attr('y', top).attr('height', yi.bandwidth())
      .attr('width', (r) => Math.max(0, x(r.share) - x(0))).attr('rx', 3).attr('fill', (r) => color(r.grp));
    g.filter((r) => r.grp === 'vs4' && r.expected != null).append('line')
      .attr('x1', (r) => x(r.expected)).attr('x2', (r) => x(r.expected))
      .attr('y1', (r) => top(r) - 3).attr('y2', (r) => top(r) + yi.bandwidth() + 3)
      .attr('stroke', 'var(--color-fg)').attr('stroke-width', 2);
    // The percentage belongs to the bar, so it sits at the bar's end, past the tick only when the tick would run through it.
    const labelW = m.right - 8;  // the widest percentage
    const labelX = (r) => {
      const end = x(r.share) + 5, t = r.grp === 'vs4' && r.expected != null ? x(r.expected) : -1;
      return t >= end - 2 && t <= end + labelW + 2 ? t + 5 : end;
    };
    g.append('text').attr('x', labelX)
      .attr('y', (r) => top(r) + yi.bandwidth() / 2).attr('dy', '0.35em').text((r) => pct1(r.share));
    g.append('rect').attr('x', 0).attr('width', W).attr('y', top).attr('height', yi.bandwidth()).attr('fill', 'transparent')
      .on('pointermove', (event, r) => tip.show(event, `${r.dim_label}: ${rangeDash(r.bucket)}`, [
        [color(r.grp), GRP_NAME[r.grp], `${pct1(r.share)} (${int(r.loans)} of ${int(groupN(r.grp))})`],
      ].concat(r.grp === 'vs4' && r.expected != null ? [['var(--color-fg)', 'If it matched its lenders’ FICO loans', pct1(r.expected)]] : [])))
      .on('pointerleave', () => tip.hide());
  }

  const PROFILE_FMT = { loans: int, wa_score: fixed(0), wa_fico: fixed(0), wa_vs4: fixed(0), avg_gap: ptsSigned,
    wa_ltv: (v) => `${fixed(1)(v)}%`, wa_dti: (v) => `${fixed(1)(v)}%`, wa_rate_30: (v) => `${fixed(2)(v)}%`, avg_loan: money, purchase_share: pct1, cashout_share: pct1,
    fthb_share: pct1, investor_share: pct1, broker_share: pct1, mi_share: pct1, fixed30_share: pct1 };
  function drawProfile(p) {
    const status = dash.data('borrower_profile').status;
    const data = rowsOf('borrower_profile');
    root.querySelectorAll('#profile-grid [data-covers]').forEach((el) => { el.hidden = el.dataset.covers !== p.cover; });
    root.querySelectorAll('#profile-grid [data-field]').forEach((el) => {
      const grp = el.dataset.grp, k = el.getAttribute('data-field');
      el.setAttribute('data-where', `cover=${p.cover}&grp=${grp}`);
      const r = data.find((d) => d.cover === p.cover && d.grp === grp);
      fill(el, status, r && r[k] != null ? PROFILE_FMT[k](r[k]) : null);
    });
  }

  // ---- Pricing ----
  const PDIMS = { purpose: 'Loan purpose', score: 'Fee tier', ltv: 'Loan-to-value', channel: 'Origination channel', size: 'Loan size' };
  const BASIS_TEXT = { headline: 'in the same fee tier', own_fico: 'at the borrower’s own Classic FICO' };

  function drawPricing(p) {
    drawFees();
    const st = dash.data('pricing').status;
    const rows = rowsOf('pricing');
    const mine = (r) => r.cover === p.cover && r.basis === p.basis;
    const o = rows.find((r) => r.view === 'overall' && mine(r)) || {};
    const fit = rows.find((r) => r.view === 'fit') || {};
    const where = `view=overall&cover=${p.cover}&basis=${p.basis}`;
    const one = d3.format('.1f');
    mark('.pr-net', 'net_bp', where, st, o.net_bp == null ? null : bpSigned(o.net_bp));
    mark('.pr-check', 'check_bp', where, st, o.check_bp == null ? null : bpSigned(o.check_bp));
    mark('.pr-premium', 'premium_bp', where, st, o.premium_bp == null ? null : bpSigned(o.premium_bp));
    mark('.pr-se', 'se_bp', where, st, o.se_bp == null ? null : one(o.se_bp));
    mark('.pr-median', 'median_bp', where, st, o.median_bp == null ? null : bpSigned(o.median_bp));
    mark('.pr-n', 'n', where, st, o.n == null ? null : int(o.n));
    mark('.pr-since', 'since', where, st, o.since ? longDay(o.since) : null);
    mark('.pr-rmse', null, null, st, fit.rmse_bp == null ? null : one(fit.rmse_bp));
    mark('.pr-r2', null, null, st, fit.r2 == null ? null : d3.format('.2f')(fit.r2));
    mark('.pr-held', null, null, st, fit.n == null ? null : int(fit.n));
    mark('.pr-trained', null, null, st, fit.n_train == null ? null : int(fit.n_train));
    document.getElementById('basis-seg').hidden = p.cover !== 'both';
    root.querySelectorAll('.pr-window').forEach((el) => { el.textContent = p.cover === 'all' ? 'first disclosed' : 'disclosed with every score'; });
    root.querySelectorAll('.pricing-basis').forEach((el) => { el.textContent = BASIS_TEXT[p.basis]; });
    const weeks = rows.filter((r) => r.view === 'week' && mine(r)).sort((a, b) => a.order - b.order);
    root.querySelectorAll('.pr-first').forEach((el) => { el.textContent = p.cover === 'all' || !weeks.length ? '' : `; first disclosed from ${shortDay(weeks[0].key)}`; });
    drawValue(st, rows);
    legend(document.getElementById('pricing-seller-legend'), BP_KEY);
    legend(document.getElementById('pricing-segment-legend'), BP_KEY);
    drawPricingWeeks(st, weeks);
    hbarsBp(document.getElementById('pricing-seller-chart'), st, rows.filter((r) => r.view === 'seller' && mine(r)).sort((a, b) => a.order - b.order).slice(0, 12),
      'VS4 rate against the model by lender');
    const sel = document.getElementById('pricing-dim');
    if (sel.options.length !== Object.keys(PDIMS).length) sel.replaceChildren(...Object.entries(PDIMS).map(([v, l]) => new Option(l, v)));
    sel.value = PDIMS[p.pdim] ? p.pdim : 'purpose';
    hbarsBp(document.getElementById('pricing-segment-chart'), st,
      rows.filter((r) => r.view === 'segment' && mine(r) && r.dim === sel.value).sort((a, b) => a.order - b.order),
      'VS4 rate against the model by type of loan');
    drawPricingHist(st, rows.filter((r) => r.view === 'hist' && mine(r)).sort((a, b) => a.order - b.order));
  }

  // Dollars at any size: $0, $420, $48k, $2.1m, $1.0bn, $2.1tn. Under $100k it reads in thousands, so a small amount never shows as $0.0m.
  const usdM = (v) => {
    const a = Math.abs(v), one = d3.format('.1f');
    const text = a >= 999.95e9 ? `$${one(a / 1e12)}tn` : a >= 999.95e6 ? `$${one(a / 1e9)}bn` : a >= 1e5 ? `$${one(a / 1e6)}m` : a >= 1e3 ? `$${d3.format('.0f')(a / 1e3)}k` : money(a);
    return v <= -0.5 ? `−${text}` : text;
  };

  function drawFees() {
    const st = dash.data('fees').status;
    const rows = rowsOf('fees');
    const m = rows.find((r) => r.view === 'market' && r.key === 'All') || {};
    const mw = 'view=market&key=All';
    const val = (f, fmt) => (m[f] == null ? null : fmt(m[f]));
    mark('.fe-month', 'month', mw, st, val('month', monthYear));
    mark('.fe-month-s', 'month', mw, st, val('month', monthShort));
    mark('.fe-avg', 'saving_avg_usd', mw, st, val('saving_avg_usd', money));
    mark('.fe-share', 'saving_share', mw, st, val('saving_share', pct1));
    mark('.fe-taken', 'taken_annual_usd', mw, st, val('taken_annual_usd', usdM));
    mark('.fe-taken-m', 'taken_all_usd', mw, st, val('taken_all_usd', usdM));
    mark('.fe-option', 'option_annual_usd', mw, st, val('option_annual_usd', usdM));
    mark('.fe-option-bp', 'option_bp', mw, st, val('option_bp', d3.format('.1f')));
    mark('.fe-left', 'left_usd', mw, st, val('left_usd', usdM));
    mark('.fe-left-n', 'left_loans', mw, st, val('left_loans', int));
    const lenders = rows.filter((r) => r.view === 'lender').sort((a, b) => a.rank - b.rank);
    const topLeft = lenders.slice().sort((a, b) => b.left_usd - a.left_usd)[0];
    mark('.fe-left-top', 'short', topLeft ? `view=lender&id=${enc(topLeft.id)}` : null, st, topLeft ? topLeft.short : null);
    const table = document.getElementById('fee-table');
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const heads = table.tHead.rows[0].cells;
    const body = table.tBodies[0];
    body.replaceChildren();
    const orDashL = (fmt) => (v) => (v == null ? '—' : fmt(v));
    for (const r of lenders) {
      const tr = body.insertRow();
      tr.dataset.key = ['lender', r.id].map(keyPart).join(',');
      [olName(r), int(r.priced_loans), r.priced_loans >= 20 ? orDashL(pct1)(r.saving_share) : '—', r.priced_loans >= 20 ? orDashL(money)(r.saving_avg_usd) : '—',
        r.priced_loans ? usdM(r.taken_usd) : '—', r.left_loans ? usdM(r.left_usd) : '—', r.one_loans ? usdM(r.est_usd) : '—', orDashL(d3.format('.1f'))(r.option_bp)].forEach((text, i) => {
        const td = tr.insertCell();
        td.textContent = text;
        td.className = heads[i].className;
      });
    }
    const gse = rows.filter((r) => r.view === 'gse');
    const lift = rows.filter((r) => r.view === 'lift');
    const scopes = [...new Map(gse.map((r) => [r.scope, r.scope_label])).entries()];
    const gt = document.getElementById('gse-score-table');
    const gh = gt.tHead.rows[0];
    gh.replaceChildren(...['Fee bucket'].concat(scopes.map(([, l]) => l), ['Better VS4, same FICO']).map((text, i) => {
      const th = document.createElement('th');
      th.scope = 'col';
      if (!i) th.className = 'vx-l';
      th.textContent = text;
      return th;
    }));
    const gb = gt.tBodies[0];
    gb.replaceChildren();
    for (const key of [...new Set(gse.map((r) => r.key))].sort()) {
      const tr = gb.insertRow();
      const c0 = tr.insertCell();
      c0.className = 'vx-l';
      c0.textContent = rangeDash(gse.find((r) => r.key === key).label);
      for (const [s] of scopes) {
        const r = gse.find((d) => d.key === key && d.scope === s);
        const td = tr.insertCell();
        td.textContent = r ? ptsSigned(r.diff) : '—';
        if (r) td.title = `${int(r.loans)} VS4-priced loans`;
      }
      const l = lift.find((d) => d.key === key);
      tr.insertCell().textContent = l ? ptsSigned(l.diff) : '—';
    }
  }

  // The fall in rate over the fee at 5 to 1. Sampling noise can put it past either end.
  const reachText = (v) => (v == null ? '—' : v >= 0.95 ? 'About all' : v <= 0.05 ? 'None visible' : d3.format('.0%')(v));

  function drawValue(st, rows) {
    const table = document.getElementById('value-table');
    const all = rows.filter((r) => r.view === 'value');
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const one = d3.format('.1f');
    const body = table.tBodies[0];
    body.replaceChildren();
    const addRow = (label, r, same) => {
      const tr = body.insertRow();
      tr.dataset.key = ['value', r.scope, r.key].map(keyPart).join(',');
      [[label, 'vx-l'], [int(r.n)], [r.fee_bp == null ? '—' : one(r.fee_bp), 'vx-opt'], [r.fee_rate_bp == null ? '—' : one(r.fee_rate_bp), 'vx-opt'], [bpSigned(r.net_bp)], [r.n < 50 ? '—' : reachText(r.reaches_fee)],
        [same ? int(same.n) : '—', 'vx-opt'], [same ? bpSigned(same.net_bp) : '—', 'vx-opt']].forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
    };
    const scopes = all.filter((r) => r.key === 'better' && r.n >= 100).sort((a, b) => a.scope_rank - b.scope_rank);
    for (const r of scopes) addRow(r.label, r, all.find((d) => d.scope === r.scope && d.key === 'same'));
    const bands = { to25: 'fee saved up to 25 bp', to50: 'fee saved 25 to 50 bp', to100: 'fee saved 50 to 100 bp', over100: 'fee saved over 100 bp' };
    const first = all.filter((r) => r.channel).sort((a, b) => a.scope_rank - b.scope_rank).find((r) => r.channel === 'R' && r.key === 'better' && r.n >= 100);
    const uwm = all.filter((r) => r.channel === 'B' && r.key === 'better' && r.n >= 100).map((r) => r.scope);
    for (const scope of [...new Set([first && first.scope, ...uwm].filter(Boolean))]) {
      for (const [key, label] of Object.entries(bands)) {
        const r = all.find((d) => d.scope === scope && d.key === key);
        if (r && r.n >= 50) addRow(`${r.label}, ${label}`, r);
      }
    }
    const left = all.find((d) => d.scope === 'All' && d.key === 'fico_better');
    document.getElementById('value-left').textContent = left ? `For comparison: ${int(left.n)} 30-year fixed loans priced on FICO though VS4 had the lower fee. Rate against the lender's own FICO loans: ${bpSigned(left.net_bp)} bp. Fee they could have saved: ${one(left.fee_bp)} bp (${one(left.fee_rate_bp)} bp in rate terms).` : '';
  }

  function pricingTip(r) {
    return [
      [C_VS4, 'VS4 loans', `${bpSigned(r.premium_bp)} bp (± ${d3.format('.1f')(2 * (r.se_bp || 0))}) on ${int(r.n)}`],
      ['var(--color-fg)', 'FICO loans the model did not see', r.check_bp == null ? 'too few to show' : `${bpSigned(r.check_bp)} bp on ${int(r.check_n)}`],
      [null, 'Net', r.net_bp == null ? '—' : `${bpSigned(r.net_bp)} bp`],
    ];
  }

  const BP_KEY = [[C_VS4, 'VS4 loans', 'box'], ['var(--color-fg)', 'FICO loans the model did not see', 'diamond'], ['var(--color-fg)', 'Margin of error', 'line']];

  function drawPricingWeeks(st, data) {
    const box = document.getElementById('pricing-week-chart');
    legend(document.getElementById('pricing-week-legend'), BP_KEY);
    if (!prep(box, st) || !data.length) return;
    const W = box.clientWidth, H = 240, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'VS4 rate against the model by week of first disclosure');
    const lo = Math.min(0, d3.min(data, (r) => r.premium_bp - 2 * (r.se_bp || 0)), d3.min(data, (r) => r.check_bp ?? 0));
    const hi = Math.max(0, d3.max(data, (r) => r.premium_bp + 2 * (r.se_bp || 0)), d3.max(data, (r) => r.check_bp ?? 0));
    const y = d3.scaleLinear([lo, hi], [H - m.bottom, m.top]).nice(5);
    const keys = data.map((r) => r.key);
    const { x, widest } = bandFrame(svg, keys, shortDay, y, bpTick, 5, W, m);
    yAxis(svg, y, bpTick, m.left, W - m.right);
    bandAxis(svg, x, keys, shortDay, widest, H - m.bottom + 8);
    const bw = Math.min(28, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    const cx = (r) => x(r.key) + x.bandwidth() / 2;
    svg.append('g').selectAll('rect').data(data).join('rect')
      .attr('x', (r) => x(r.key) + off).attr('width', bw).attr('y', (r) => y(Math.max(0, r.premium_bp)))
      .attr('height', (r) => Math.abs(y(r.premium_bp) - y(0))).attr('rx', 3).attr('fill', C_VS4).attr('fill-opacity', 0.85);
    svg.append('g').selectAll('line').data(data.filter((r) => r.se_bp != null)).join('line')
      .attr('x1', cx).attr('x2', cx).attr('y1', (r) => y(r.premium_bp - 2 * r.se_bp)).attr('y2', (r) => y(r.premium_bp + 2 * r.se_bp))
      .attr('stroke', 'var(--color-fg)').attr('stroke-width', 1.5);
    svg.append('g').selectAll('path').data(data.filter((r) => r.check_bp != null)).join('path')
      .attr('d', d3.symbol(d3.symbolDiamond, 40)).attr('transform', (r) => `translate(${cx(r)},${y(r.check_bp)})`)
      .attr('fill', 'var(--color-panel)').attr('stroke', 'var(--color-fg)');
    bandHover(svg, box, x, data, 'key', m, H, (r) => [`Week of ${shortDay(r.key)}`, pricingTip(r)]);
  }

  function hbarsBp(box, st, items, label) {
    if (!prep(box, st)) return;
    if (!items.length) return;
    const W = box.clientWidth, rowH = W > 360 ? Math.max(26, 208 / items.length) : 26;  // on a wide card a short list fills the height of the charts around it
    const m = { top: 6, right: 12, bottom: 26, left: 0 };
    const H = m.top + m.bottom + items.length * rowH;
    box.style.minHeight = `${H}px`;
    const svg = svgFor(box, W, H, label);
    const text = (r) => `${rangeDash(r.label).replace(/ \([A-Z]+\)$/, '').replace(/ refinance$/, ' refi')} · ${int(r.n)}`;  // short names, so the count always fits; the tooltip has the full one
    m.left = Math.min(Math.ceil(textWidth(svg, items.map(text))) + 14, Math.max(160, Math.floor(W * 0.5)));
    const lo = Math.min(0, d3.min(items, (r) => r.premium_bp - 2 * (r.se_bp || 0)), d3.min(items, (r) => r.check_bp ?? 0));
    const hi = Math.max(0, d3.max(items, (r) => r.premium_bp + 2 * (r.se_bp || 0)), d3.max(items, (r) => r.check_bp ?? 0));
    const x = d3.scaleLinear([lo, hi], [m.left, W - m.right]).nice(5);
    const ticks = x.ticks(5);
    svg.append('g').selectAll('line').data(ticks).join('line')
      .attr('x1', (v) => x(v)).attr('x2', (v) => x(v)).attr('y1', m.top).attr('y2', H - m.bottom)
      .attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-axis)' : 'var(--cds-chart-grid)'));
    svg.append('g').attr('transform', `translate(0,${H - m.bottom + 8})`)
      .call(d3.axisBottom(x).tickValues(ticks).tickFormat(bpTick).tickSize(0)).call(styleAxis);
    const idx = new Map(items.map((r, i) => [r, i]));
    const yb = d3.scaleBand(d3.range(items.length), [m.top, H - m.bottom]).paddingInner(0.35);
    const cy = (r) => yb(idx.get(r)) + yb.bandwidth() / 2;
    const bh = Math.min(28, yb.bandwidth());
    const g = svg.append('g').selectAll('g').data(items).join('g');
    g.append('text').attr('x', m.left - 10).attr('y', cy).attr('dy', '0.35em').attr('text-anchor', 'end')
      .style('fill', 'var(--color-fg)').text(text).each(function () { clip(this, m.left - 14); });
    g.append('rect').attr('x', (r) => x(Math.min(0, r.premium_bp))).attr('width', (r) => Math.abs(x(r.premium_bp) - x(0)))
      .attr('y', (r) => cy(r) - bh / 2).attr('height', bh).attr('rx', 3).attr('fill', C_VS4).attr('fill-opacity', 0.85);
    g.filter((r) => r.se_bp != null).append('line')
      .attr('x1', (r) => x(r.premium_bp - 2 * r.se_bp)).attr('x2', (r) => x(r.premium_bp + 2 * r.se_bp))
      .attr('y1', cy).attr('y2', cy).attr('stroke', 'var(--color-fg)').attr('stroke-width', 1.5);
    g.filter((r) => r.check_bp != null).append('path').attr('d', d3.symbol(d3.symbolDiamond, 40))
      .attr('transform', (r) => `translate(${x(r.check_bp)},${cy(r)})`).attr('fill', 'var(--color-panel)').attr('stroke', 'var(--color-fg)');
    const tip = tooltip(box);
    g.append('rect').attr('x', 0).attr('width', W).attr('y', (r) => yb(idx.get(r)) - 3).attr('height', yb.bandwidth() + 6)
      .attr('fill', 'transparent')
      .on('pointermove', (event, r) => tip.show(event, rangeDash(r.label), pricingTip(r)))
      .on('pointerleave', () => tip.hide());
  }

  function drawPricingHist(st, data) {
    const box = document.getElementById('pricing-hist-chart');
    legend(document.getElementById('pricing-hist-legend'), [[C_VS4, 'VS4 loans', 'box'], ['var(--color-fg-muted)', 'FICO loans the model did not see', 'line']]);
    if (!prep(box, st) || !data.length) return;
    const W = box.clientWidth, H = 220, m = { top: 10, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'Spread of VS4 and held-out FICO loans’ rates against the model');
    const width = data.find((r) => r.bin_lo != null && r.bin_hi != null);
    const step = width ? width.bin_hi - width.bin_lo : 1;
    const lo = (r) => (r.bin_lo == null ? r.bin_hi - step : r.bin_lo);
    const hi = (r) => (r.bin_hi == null ? r.bin_lo + step : r.bin_hi);
    const y = d3.scaleLinear([0, (d3.max(data, (r) => Math.max(r.share, r.check_share)) || 0.01) * 1.1], [H - m.bottom, m.top]).nice(4);
    const yf = d3.format('.0%');
    m.left = Math.ceil(textWidth(svg, y.ticks(4).map(yf))) + 10;
    const x = d3.scaleLinear([d3.min(data, lo), d3.max(data, hi)], [m.left, W - m.right]);
    yAxis(svg, y, yf, m.left, W - m.right, 4);
    svg.append('g').attr('transform', `translate(0,${H - m.bottom + 8})`)
      .call(d3.axisBottom(x).ticks(6).tickFormat(bpTick).tickSize(0)).call(styleAxis);
    svg.append('g').selectAll('rect').data(data).join('rect')
      .attr('x', (r) => x(lo(r)) + 1).attr('width', (r) => Math.max(0, x(hi(r)) - x(lo(r)) - 2))
      .attr('y', (r) => y(r.share)).attr('height', (r) => Math.max(0, y(0) - y(r.share))).attr('fill', C_VS4).attr('fill-opacity', 0.8);
    const last = data[data.length - 1];
    svg.append('path').attr('d', d3.line().curve(d3.curveStepAfter)(data.map((r) => [x(lo(r)), y(r.check_share)]).concat([[x(hi(last)), y(last.check_share)]])))
      .attr('fill', 'none').attr('stroke', 'var(--color-fg-muted)').attr('stroke-width', 2);
    const tip = tooltip(box);
    svg.append('g').selectAll('rect').data(data).join('rect')
      .attr('x', (r) => x(lo(r))).attr('width', (r) => Math.max(0, x(hi(r)) - x(lo(r)))).attr('y', m.top)
      .attr('height', H - m.top - m.bottom).attr('fill', 'transparent')
      .on('pointermove', (event, r) => tip.show(event,
        r.bin_lo == null ? `Below ${bpSigned(r.bin_hi)} bp` : r.bin_hi == null ? `${bpSigned(r.bin_lo)} bp and above` : `${bpSigned(r.bin_lo)} to ${bpSigned(r.bin_hi)} bp`,
        [[C_VS4, 'VS4 loans', `${pct1(r.share)} of ${int(r.n)}`], ['var(--color-fg-muted)', 'FICO loans the model did not see', `${pct1(r.check_share)} of ${int(r.check_n)}`]]))
      .on('pointerleave', () => tip.hide());
  }

  function draw() {
    const p = params();
    root.querySelectorAll('.vx-seg[data-param]').forEach((seg) => {
      const v = String(p[seg.dataset.param]);
      seg.querySelectorAll('button[data-v]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === v)));
    });
    drawSummary(p);
    drawScoreMix(p);  // the header reads it on every page
    if (current === 'overview') {
      drawTiles(p);
      drawOutlookRecent(p);
      drawCeilingTile(p);
      drawQuarters(p);
      drawMonthly(p);
      drawWeekly(p);
      drawEventList();
      drawBreadth(p);
      drawDrivers(p);
      drawClean(p);
    } else if (current === 'outlook') {
      drawOutlook(p);
    } else if (current === 'lenders') {
      drawWindow();
      drawEventList();
      root.querySelectorAll('[data-unit]').forEach((el) => { el.textContent = p.measure === 'upb' ? 'balance' : 'loans'; });
      root.querySelectorAll('.mk-them').forEach((el) => { el.textContent = p.measure === 'upb' ? 'it' : 'them'; });
      drawExplorer(p);
      drawHeat(p);
      if (document.getElementById('adoption-more').open) {
        drawCoverage(p);
        drawMarket(p);
        drawNewAdopters(p);
        drawTables(p);
      }
    } else if (current === 'scores') {
      drawWhy(p);
      drawChoice(p);
      drawRules(p);
      if (document.getElementById('ceiling-more').open) {
        drawCeiling(p);
        drawBands();
      }
    } else if (current === 'borrowers') {
      root.querySelectorAll('.cover-note').forEach((el) => { el.textContent = p.cover === 'all' ? 'Every VS4-priced and Classic FICO-priced loan issued since July 2026.' : COVER_NOTE[p.cover]; });
      drawMix(p);
      drawProfile(p);
    } else if (current === 'pricing') {
      root.querySelectorAll('.cover-note').forEach((el) => { el.textContent = p.cover === 'all' ? 'Every VS4-priced and Classic FICO-priced 30-year fixed loan first disclosed since July 20, 2026.' : COVER_NOTE[p.cover]; });
      drawPricing(p);
    }
    (window.vx.hooks[current] || []).forEach((fn) => fn(p));
    window.vx.after.forEach((fn) => fn());
  }
  window.vx = { root, rowsOf, statusOf, int, pct1, money, usdM, ptsSigned, inkOn, olName, olPct, openSeller, entityOf, monthShort, monthYear, monthLabel, shortDay, reachText, prep, svgFor, bandFrame, yAxis, bandAxis, bandHover, legend, tooltip, textWidth,
    MIX_GROUPS, ADOPT_FROM, AG_NAME, show, col, mark, redraw: draw, after: [], hooks: { overview: [], outlook: [], lenders: [], scores: [], borrowers: [], pricing: [], market: [], method: [] } };

  // A link names a page (#lenders) or a seller (#seller-rocket-mortgage); the page opens it as it loads.
  const named = decodeURIComponent(location.hash.slice(1));
  if (named.startsWith('seller-')) {
    dash.setParams({ seller: named.slice('seller-'.length) });
    place('lenders');
  } else if (TABS.includes(named)) {
    place(named);
  } else {
    place('overview');
  }
  window.addEventListener('hashchange', () => {
    const h = decodeURIComponent(location.hash.slice(1));
    if (h.startsWith('seller-') && !(current === 'lenders' && params().seller === h.slice('seller-'.length))) openSeller(h.slice('seller-'.length));
    else if (TABS.includes(h) && h !== current) { place(h); draw(); }
  });
  root.addEventListener('toggle', (event) => { if (event.target.matches('details.vx-more')) draw(); }, true);
  dash.onData(draw);
})();
