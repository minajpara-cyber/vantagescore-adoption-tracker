(() => {
  const root = document.querySelector('.vx');
  const AGENCIES = ['All', 'FNMA', 'FHLMC'];
  const AG_NAME = { All: 'Both GSEs', FNMA: 'Fannie Mae', FHLMC: 'Freddie Mac' };
  const AG_NOUN = { All: 'GSE', FNMA: 'Fannie Mae', FHLMC: 'Freddie Mac' };
  const TABS = ['overview', 'pricing', 'outlook', 'lenders', 'scores', 'borrowers', 'market', 'method'];
  // The tab reads Rates and its id stays pricing, so a link to #rates opens it as well.
  const tabOf = (name) => (name === 'rates' ? 'pricing' : name);
  const DEF_FIRST = { any: 'first_vs4_month', ten: 'first_10_month', pct5: 'first_5pct_month' };
  // Months drawn on the adoption and seller charts: VS4 deliveries begin in April 2026.
  const ADOPT_FROM = '2026-04-01';
  const CHANGE_FROM = '2026-05-01';
  const RECENT_FROM = '2026-05-01';
  const DEFAULTS = { agency: 'All', measure: 'loans', dim: 'fico', seller: 'rocket-mortgage', adopt: 'any', period: 'month', top: 25, mapmonth: '', cover: 'both', cscope: 'All', cperiod: 'week', lsort: 'share', ccohort: 'all' };
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
  const rangeDash = (s) => String(s).replace(/(\d[kKmM]?)-(\$?\d)/g, '$1–\u2060$2');  // the data files write ranges with a hyphen; the word joiner keeps a range on one line
  const enc = (s) => String(s).replace(/%/g, '%25').replace(/&/g, '%26').replace(/=/g, '%3D');
  const col = (i) => dash.colors[i % dash.colors.length];
  const agencyColor = (a) => col(Math.max(0, AGENCIES.indexOf(a)));
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
    if (!['all', 'both', 'vs4only'].includes(p.cover)) p.cover = DEFAULTS.cover;
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
    dash.setLink(t === 'pricing' ? 'rates' : t);
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

  const TOP_SHORT = { 'ROCKET MORTGAGE, LLC': 'Rocket', 'UNITED WHOLESALE MORTGAGE, LLC': 'UWM' };
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
    // It names the two largest where the file's two have short names here, and any other two stay unnamed.
    const topNames = String(both.top2_sellers ?? '').split(' and ').map((name) => TOP_SHORT[name]);
    root.querySelectorAll('.h-top2').forEach((el) => { el.textContent = topNames.length === 2 && topNames.every(Boolean) ? topNames.join(' and ') : 'Two lenders'; });
    // Between a month's final file and the next month joining the series, the latest month is the final one: nothing is "so far".
    root.querySelectorAll('.h-so-far').forEach((el) => { el.hidden = !!both.final_month && both.current_month === both.final_month; });
    root.querySelectorAll('.s-so-far').forEach((el) => { el.hidden = !!mine.final_month && mine.current_month === mine.final_month; });
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

  function textWidth(svg, labels, size = null) {
    const t = svg.append('text').attr('visibility', 'hidden').style('font-size', size);
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
      if (!color) {  // words alone, with no swatch
        item.append(label);
        return item;
      }
      const sw = document.createElement('span');
      sw.className = kind === 'line' || kind === 'diamond' || kind === 'dot' || kind === 'outline' || kind === 'hollow' ? `vx-sw vx-sw-${kind}` : 'vx-sw';
      if (kind === 'diamond' || kind === 'outline') sw.style.borderColor = color;
      else if (kind === 'hollow') sw.style.color = color;
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
          r.append(value == null ? label : `${label}: ${value}`);  // a line can be plain words, with no value
          return r;
        }));
        const [px, py] = d3.pointer(event, box);
        const w = tip.offsetWidth, h2 = tip.offsetHeight;
        tip.style.left = `${px + 14 + w > box.clientWidth ? Math.max(0, px - 14 - w) : px + 14}px`;
        const top = Math.max(0, Math.min(py - h2 / 2, box.clientHeight - h2)), r = box.getBoundingClientRect();
        tip.style.top = `${Math.max(-r.top + 4, Math.min(top, innerHeight - r.top - h2 - 4))}px`;
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

  // VS4 share over issue months, one line per GSE, the picked one drawn strongest.
  function agencyLines(box, status, rows, f, countKey, p, label, finalOf) {
    if (!prep(box, status)) return;
    const data = rows.filter((r) => r[f] != null)
      .map((r) => ({ ...r, final: finalOf ? finalOf(r) : r.final, mid: new Date(parse(r.month).getTime() + 14.5 * DAY) }));
    if (!data.length) return;
    const W = box.clientWidth, H = 260;
    const m = { top: 40, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, label);
    const top = d3.max(data, (r) => r[f]) || 0.01;
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
    for (const a of AGENCIES.filter((a) => a !== p.agency).concat(p.agency)) {
      partialLine(svg, data.filter((r) => r.agency === a), xf, (r) => r[f], y, agencyColor(a), 'final', a === p.agency);
    }

    const tip = tooltip(box);
    const rule = svg.append('line').attr('y1', m.top).attr('y2', H - m.bottom)
      .attr('stroke', 'var(--cds-chart-axis)').attr('opacity', 0);
    const mids = [...new Set(data.map((r) => r.month))].map((mo) => ({ mo, t: parse(mo).getTime() + 14.5 * DAY }));
    svg.append('rect').attr('x', m.left).attr('y', m.top).attr('width', Math.max(0, W - m.left - m.right))
      .attr('height', H - m.top - m.bottom).attr('fill', 'transparent')
      .on('pointermove', (event) => {
        const t = x.invert(d3.pointer(event)[0]).getTime();
        const near = d3.least(mids, (d) => Math.abs(d.t - t));
        if (!near) return;
        rule.attr('x1', x(near.t)).attr('x2', x(near.t)).attr('opacity', 1);
        const rs = AGENCIES.map((a) => data.find((r) => r.agency === a && r.month === near.mo)).filter(Boolean);
        tip.show(event, `${monthYear(near.mo)}${rs.every((r) => r.final) ? '' : ' (partial)'}`,
          rs.map((r) => [agencyColor(r.agency), AG_NAME[r.agency], `${pct1(r[f])}${f.includes('upb') ? '' : ` of ${int(r[countKey])} loans`}`]));
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
    document.getElementById('monthly-base').textContent = upb ? 'Share of balance on loans' : 'Share of loans';
    legend(document.getElementById('monthly-legend'), AGENCIES.map((a) => [agencyColor(a), AG_NAME[a], 'line', a === p.agency]));
    agencyLines(box, statusOf('monthly', 'events'), rowsOf('monthly'), upb ? 'vs4_upb_share' : 'vs4_share',
      'scored_loans', p, 'VS4 share by issue month', null);
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
    const lines = [[`actual${k}`, 'Actual', C_VS4], [`higher${k}`, 'Wherever the VS4 score is higher', col(2)]];
    legend(document.getElementById('ceiling-legend'), lines.map(([, l, c], i) => [c, l, 'line', i === 0]));
    if (!prep(box, dash.data('ceiling').status)) return;
    const data = rowsOf('ceiling').filter((r) => r.view === 'month' && r.agency === p.agency).sort((a, b) => (a.start < b.start ? -1 : 1));
    if (!data.length) return;
    const W = box.clientWidth, H = 240, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'VS4 share by issue month, actual and wherever its score is higher');
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
      [[rangeDash(r.label), 'vx-l'], [pct1(r.loan_share)], [r.measured ? pct1(r.higher) : '—'], [int(r.measured), 'vx-opt'], [pct1(r.adds_higher)]]
        .forEach(([text, cls]) => {
          const td = tr.insertCell();
          td.textContent = text;
          if (cls) td.className = cls;
        });
    }
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
    ['users', 'Every lender using VS4 does', col(4)]];
  const OL_RULE = 'higher';  // the one what-if rule the page reads: VS4 whenever its score is higher
  const olPicked = new Set();
  const olRows = (v) => rowsOf('outlook').filter((r) => r.view === v);
  const olName = (r, name = r.short) => (r.ticker && !new RegExp(`\\b${r.ticker}\\b`).test(name) ? `${name} (${r.ticker})` : name);
  const olPct = (v) => (v > 0 && v < 0.0005 ? '<0.1%' : pct1(v));
  const orDash = (fmt) => (v) => (v == null ? '—' : fmt(v));
  const olRung = (key) => olRows('ladder').find((r) => r.key === key && (r.rule == null || r.rule === OL_RULE));
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
    const pr = olRows('params')[0] || {};
    const path = olRows('path').filter((r) => r.case === 'actual' || (r.rule === OL_RULE && r.case !== 'pace'));
    const pw = 'view=params';
    const val = (r, f, fmt) => (r && r[f] != null ? fmt(r[f]) : null);
    const f = `value${k}`;
    root.querySelectorAll('.ol-unit').forEach((el) => { el.textContent = k ? 'balances' : 'loans'; });
    mark('.ol-window', 'window_from', pw, st, pr.window_from
      ? (pr.window_from === pr.window_to ? monthYear(pr.window_to) : `${monthShortYear(pr.window_from)} to ${monthShortYear(pr.window_to)}`) : null);
    mark('.ol-heavy-names', 'heavy_names', pw, st, pr.heavy_names || null);
    mark('.ol-users', 'users', pw, st, val(pr, 'users', int));
    mark('.ol-user-share', `user_share${k}`, pw, st, val(pr, `user_share${k}`, pct1));
    drawOutlookRecent(p);
    for (const [cls, key] of [['ol-today', 'today'], ['ol-heavy-v', 'heavy'], ['ol-all', 'all']]) {
      const r = olRung(key);
      mark(`.${cls}`, f, r ? olWhere(r) : null, st, val(r, f, pct1));
    }
    // The first month the heavy users' case comes within 0.05 points of where it settles.
    const goal = (olRung('heavy') || {})[f];
    const by = goal == null ? null : path.filter((r) => r.case === 'heavy' && r[f] >= goal - 0.0005).sort((a, b) => (a.month < b.month ? -1 : 1))[0];
    mark('.ol-heavy-by', 'month', by ? `view=path&case=heavy&rule=${OL_RULE}&month=${enc(by.month)}` : null, st, by ? monthShortYear(by.month) : null);
    const next = root.querySelector('#ol-pick [data-pick="next"]');
    if (next && pr.next_n) next.textContent = `Plus the ${pr.next_n} largest`;
    drawOutlookPaths(st, k, path, pr);
    drawOutlookLadder(st, k, pr);
    drawOutlookRamp(st, k);
    drawOutlookTable(p);
    drawOutlookPace(st, k);
  }

  function drawOutlookPaths(st, k, path, pr) {
    const box = document.getElementById('ol-path-chart');
    const f = `value${k}`;
    legend(document.getElementById('ol-path-legend'), [[C_VS4, 'Actual', 'line', true]].concat(OL_CASES.map(([, l, c]) => [c, l, 'line'])));
    if (!prep(box, st) || !path.length) return;
    const refs = [['all', 'Every lender', col(3)]]
      .map(([key, label, color]) => ({ label, color, v: (olRung(key) || {})[f] })).filter((r) => r.v != null);
    const months = [...new Set(path.map((r) => r.month))].sort();
    const W = box.clientWidth, H = 300, m = { top: 12, right: 10, bottom: 26, left: 0 };
    const svg = svgFor(box, W, H, 'VS4 share by issue month, actual and three cases');
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

  function drawOutlookLadder(st, k, pr) {
    const box = document.getElementById('ol-ladder-chart');
    if (!prep(box, st)) return;
    const f = `value${k}`;
    const names = { today: 'Today', recent: 'Latest two weeks', heavy: 'The biggest users', users: 'Every lender using VS4',
      next: `And the ${pr.next_n ?? ''} largest not using it`, all: 'Every lender' };
    const items = ['today', 'recent', 'heavy', 'users', 'next', 'all'].map((key) => olRung(key)).filter((r) => r && r[f] != null);
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
    const g = svg.append('g').selectAll('g').data(items).join('g');
    g.append('text').attr('x', narrow ? m.left + 4 : m.left - 10).attr('y', (r) => (narrow ? yb(r.key) + 7 : cy(r))).attr('dy', '0.35em')
      .attr('text-anchor', narrow ? 'start' : 'end').style('fill', 'var(--color-fg)').text((r) => names[r.key])
      .each(function () { clip(this, narrow ? W - m.left : m.left - 14); });
    g.append('rect').attr('x', m.left).attr('width', (r) => Math.max(1, x(r[f]) - m.left)).attr('y', top)
      .attr('height', bh).attr('rx', 3).attr('fill', C_VS4).attr('fill-opacity', (r) => (r.key === 'today' ? 1 : 0.7));
    // Each step is taken between the printed levels, so the labels add up.
    const printed = (r) => parseFloat(pct1(r[f])) / 100;
    g.append('text').attr('x', (r) => x(r[f]) + 6).attr('y', cy).attr('dy', '0.35em').style('fill', 'var(--color-fg)')
      .text((r, i) => (i ? `${pct1(r[f])} (${pts(printed(r) - printed(items[i - 1]))})` : pct1(r[f])));
    const tip = tooltip(box);
    g.append('rect').attr('x', 0).attr('width', W).attr('y', (r) => yb(r.key) - 3).attr('height', yb.bandwidth() + 6)
      .attr('fill', 'transparent')
      .on('pointermove', (event, r) => tip.show(event, names[r.key], [[C_VS4, 'VS4 share', pct1(r[f])]]
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
    const upb = p.measure === 'upb', k = upb ? '_upb' : '';
    const cols = [['name', 'short', (v, r) => (r.id === 'other' ? 'All other lenders' : olName(r))],
      ['status', 'status', (v, r) => (v === 'other' ? `${int(r.sellers)} lenders` : OL_STATUS[v] || v)],
      ['share', `share${k}`, olPct], ['vs4', upb ? 'vs4_upb_share' : 'vs4_share', pct1], ['recent', upb ? 'recent_upb_share' : 'recent_share', pct1],
      ['uses', 'higher_vs4', pct1], ['both', 'both_share', pct1], ['on', `on_${OL_RULE}${k}`, pct1],
      ['adds', `adds_${OL_RULE}${k}`, (v) => (v > 0 && v < 0.0005 ? '<0.1' : fixed(1)(v * 100))]];
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
    const add = d3.sum(picked, (r) => r[`adds_${OL_RULE}${k}`] || 0);
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
      return `${pct1(l.vs4_share)} priced on VS4, ${l.recent_share == null ? '—' : pct1(l.recent_share)} in the latest weeks; both scores on ${pct1(l.both_share)}; VS4 used on ${l.uses_higher == null ? '—' : pct1(l.uses_higher)} of loans where it is higher.`;
    }
    const mix = rowsOf('score_mix');
    const head = mix.find((d) => d.view === 'month' && d.agency === 'All' && d.headline) || {};
    const fn = mix.find((d) => d.view === 'month' && d.agency === 'FNMA' && d.start === head.start) || {};
    if (r.check === 'fico') {
      if (head.fico_share == null) return '—';
      return `At least ${pct1(head.fico_share)} of loans have a Classic FICO (${pct1(fn.fico_share)} at Fannie Mae); at most ${pct1(head.vs_only_share)} have only VS4 (${pct1(fn.vs_only_share)}).`;
    }
    if (r.check === 'lenders') {
      const pr = olRows('params')[0] || {};
      const using = d3.sum(whyRows('stage').filter((d) => d.key === 'pricing' || d.key === 'some'), (d) => d.lenders);
      return `${pr.users == null ? '—' : int(pr.users)} lenders have delivered a VS4 loan to the GSEs since September, and ${int(using)} price on it regularly. At most ${head.vs_only_share == null ? '—' : pct1(head.vs_only_share)} of loans have only VS4. This covers GSE loans only.`;
    }
    if (r.check === 'pricing') return (rateRows(rowsOf('rates')).find((d) => d.view === 'meta') || {}).said_check || '—';
    if (r.check === 'fees') {
      const fm = rowsOf('fees').find((d) => d.view === 'market' && d.key === 'All') || {};
      return fm.taken_annual_usd == null ? '—' : `On the grid, ${aboutUsd(fm.taken_annual_usd).replace('About', 'about')} a year in LLPAs not paid at today's use.`;
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
  const bpTick = (v) => (v === 0 ? '0' : d3.format('+')(v));

  function drawMix(p) {
    const box = document.getElementById('mix-chart');
    const dimSel = document.getElementById('mix-dim');
    const all = rowsOf('borrowers').filter((r) => r.cover === p.cover);
    const dims = [...new Map(all.filter((r) => r.dim !== 'pricing_score').map((r) => [r.dim, r.dim_label])).entries()];
    const sig = `${p.cover}:${dims.map(([d]) => d).join(',')}`;
    if (dimSel.dataset.sig !== sig) {
      dimSel.replaceChildren(...dims.map(([v, l]) => new Option(l, v)));
      dimSel.dataset.sig = sig;
    }
    // The param can hold a breakdown no longer offered, from the shim's defaults or the store. Then the page's own default leads, or, where that has
    // one side only (Classic FICO shows on FICO-priced loans alone outside Both scores), the first breakdown with both sides.
    const twoSided = (d) => new Set(all.filter((r) => r.dim === d).map((r) => r.grp)).size > 1;
    const picked = (dash.params() || {}).dim;
    const dim = dims.some(([v]) => v === picked) ? picked : (dims.find(([v]) => v === DEFAULTS.dim && twoSided(v)) || dims.find(([v]) => twoSided(v)) || dims[0] || [null])[0];
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

  const PROFILE_FMT = { loans: int, wa_fico: fixed(0), wa_vs4: fixed(0), avg_gap: ptsSigned,
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

  // ---- Rates ----
  const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
  const bpText = (v) => (Math.abs(v) < 0.05 ? '0' : d3.format('+.1~f')(v));
  const TOO_FEW = 'Too few to compare';
  const bpFigure = (v) => (!isNum(v) ? TOO_FEW : Math.abs(v) < 0.05 ? 'about 0' : `${bpText(v)} bp`);
  const bpSpan = (a, b) => `${bpText(a)} to ${bpText(b)} bp`;
  const spanLine = (color, label, a, b) => (isNum(a) && isNum(b) ? [[color, label, bpSpan(a, b)]] : []);
  const rateName = (r) => [r.title, r.sub].filter(Boolean).join(', ');
  const nearBp = (v) => Math.sign(v) * Math.floor(Math.abs(v) * 2 + 0.5) / 2;  // a figure the file keeps in decimals, on the printed rule's half points
  const thinText = (r) => bpSpan(Math.floor(r.tl * 2) / 2, Math.ceil(r.th * 2) / 2);  // a 95% range prints outward at half points, as the sentences do
  const readText = (dot, lo, hi) => (!isNum(dot) ? '—' : `${bpText(dot)}${isNum(lo) && isNum(hi) ? ` (${bpText(lo)} to ${bpText(hi)})` : ''}`);
  const score = fixed(0);
  const pct0 = d3.format('.0%');
  const termSpan = (term, text) => {
    const el = document.createElement('span');
    el.dataset.term = term;
    el.textContent = text;
    return el;
  };
  const keyWords = (before, term, text, after) => {
    const el = document.createElement('span');
    el.append(before, termSpan(term, text), after);
    return el;
  };
  const methodsWords = (before, after) => keyWords(before, 'methods', '3 methods', after);
  const C_DOT = 'var(--color-fg)', C_THIN = 'var(--color-fg-muted)';
  // The same legend words on every chart.
  const rateKey = () => [[C_DOT, 'Dot: estimate', 'dot'], [C_VS4, methodsWords('Bar: how far the ', ' disagree, not a margin of error'), 'box'], [C_THIN, keyWords('Thin line: ', 'range95', '95% range', ', approximate'), 'line']];
  const SAME_MARKS = [null, 'Dot and bar as above.'];
  const roughKey = [C_VS4, 'Outlined bar: few weeks of loans.', 'outline'];
  const RANGE_WORDS = 'How far the 3 methods disagree', THIN_WORDS = '95% range, approximate';
  const weeksWords = (weeks, rough) => (isNum(weeks) ? (weeks < 8 ? `few lender-weeks (${int(weeks)})` : `${int(weeks)} lender-weeks`) : rough ? 'few lender-weeks' : null);
  // How many of a row's loans the two exact-match methods reached.
  const comparedLine = (r, count) => {
    if (!isNum(r.read5) || !isNum(r.read_tier) || !isNum(r.n)) return [];
    const [a, b] = [count(Math.min(r.read5, r.read_tier)), count(Math.max(r.read5, r.read_tier))];
    return [[null, `Compared: ${a === b ? a : `${a} to ${b}`} of ${count(isNum(r.pool) ? r.pool : r.n)} loans`]];
  };
  // A lead holds one sentence; what follows it sits under it in the body's style. It ends at the first full stop before a capital or a digit, and not at a name's own stop, as in U.S. Bank or Mr. Cooper.
  const leadSplit = (text) => {
    for (const hit of (text || '').matchAll(/\.\s+[A-Z0-9]/g)) {
      if (!/\b(?:U\.S|Mr)$/.test(text.slice(0, hit.index))) return [text.slice(0, hit.index + 1), text.slice(hit.index + 1).trim()];
    }
    return [text, null];
  };

  // The page and its data upload apart, so a file in any other shape than this page's says it failed and prints none of its words. Move this with the engine's RATES_SHAPE.
  const RATES_SHAPE = 2;
  const rateRows = (rows) => (rows.length && (rows.find((r) => r.view === 'meta') || {}).shape !== RATES_SHAPE ? [] : rows);
  // What every Rates draw reads. Every finding comes from rates; a row or field it lacks is left out, never drawn as zero.
  const rateRead = () => {
    const rows = rowsOf('rates'), all = rateRows(rows);
    return { st: all === rows ? dash.data('rates').status : 'error', all, meta: all.find((r) => r.view === 'meta') || {}, limitOf: (key) => (all.find((r) => r.view === 'limit' && r.key === key) || {}).text };
  };
  // The first use of each term in a run of sentences is dotted, and the map remembers which are left.
  const TERM_WORDS = [['samefico', /\bsame FICO\b/i], ['bp', /\bbp\b/], ['samenumber', /\bsame score number\b/i], ['vs4loan', /\bVS4 loans?\b/], ['llpa', /\bLLPA\b/], ['range95', /\b95% range\b/], ['ficoloan', /\bFICO loans?\b/], ['dates', /\bweek first disclosed\b/], ['oldrule', /\bthe old rule\b/], ['switchpoint', /\bswitch point\b/]];
  function termParts(text, left) {
    const parts = [text];
    for (const [term, word] of left) {
      const at = parts.findIndex((p) => typeof p === 'string' && word.test(p));
      if (at < 0) continue;
      const hit = parts[at].match(word);
      parts.splice(at, 1, parts[at].slice(0, hit.index), termSpan(term, hit[0]), parts[at].slice(hit.index + hit[0].length));
      left.delete(term);
    }
    return parts;
  }
  // A list sentence may open with a short head ending in a colon or question mark. The head prints in bold, term dots and all, and the rest follows; words in brackets before the colon stay out of the bold.
  const RUN_IN = /^((?:[^:.?(]|\.(?=\d)){2,85})(\s\([^)]*\))?([:?]) /;
  // A number keeps its unit on its line, in all but What to quote, whose words are there to be pasted.
  const bpTogether = (s) => s.replace(/(\d) bp\b/g, '$1 bp');
  function runIn(line, left) {
    const text = bpTogether(line);
    const hit = text.match(RUN_IN);
    if (!hit) return termParts(text, left);
    const head = document.createElement('b');
    head.className = 'ra-head';
    head.append(...termParts(hit[2] ? hit[1] : `${hit[1]}${hit[3]}`, left));
    return [head, ...termParts(`${hit[2] ? `${hit[2]}${hit[3]}` : ''} ${text.slice(hit[0].length)}`, left)];
  }
  function rateText(id, st, text, left = new Map(), parts = termParts) {
    const el = document.getElementById(id);
    const shown = text ? bpTogether(rangeDash(text)) : text;
    el.hidden = st !== 'loading' && !text;
    fill(el, st, shown);
    if (st === 'ok' && text) el.replaceChildren(...parts(shown, left));
  }
  const rateLine = (id, field, read) => rateText(id, read.st, read.meta[field]);
  // A line is its text, or { text, field, where } where it names its row. heads: the lines may open with a run-in head.
  function rateList(id, st, lines, left = new Map(), heads = false) {
    const list = document.getElementById(id);
    list.classList.toggle('dash-skeleton', st === 'loading');
    const textOf = (line) => (line && line.field ? line.text : line);
    list.replaceChildren(...lines.filter(textOf).map((line) => {
      const li = document.createElement('li');
      if (line.field) Object.assign(li.dataset, { source: 'rates', field: line.field, where: line.where });
      li.append(...(heads ? runIn : termParts)(rangeDash(textOf(line)), left));
      return li;
    }));
    list.hidden = st !== 'loading' && !list.children.length;
    return list.children.length;
  }
  // A tap has no pointer left to leave, so a chart's tip stays until the next tap off its marks.
  const tapOff = (box, name, hide) => d3.select(document).on(`click.${name}`, (event) => { if (!box.contains(event.target) || !event.target.closest('.rt-hit')) hide(); });
  const hits = (sel, show, hide) => sel.attr('class', 'rt-hit').attr('fill', 'transparent').on('pointermove', show).on('click', show).on('pointerleave', hide);
  function wrapLines(svg, text, max) {
    return String(text).split(' ').reduce((lines, word) => {
      const next = lines.length ? `${lines[lines.length - 1]} ${word}` : word;
      if (lines.length && textWidth(svg, [next]) <= max) lines[lines.length - 1] = next;
      else lines.push(word);
      return lines;
    }, []);
  }
  const textLines = (svg, lines, x, mid, anchor = 'start') => lines.map((s, i) => svg.append('text').attr('x', x).attr('y', mid + (i - (lines.length - 1) / 2) * 15).attr('dy', '0.35em').attr('text-anchor', anchor).text(s));
  // A dot keeps its ring on a wide bar; on a narrow bar it shrinks, and under 10 px it loses the ring, so the bar still shows.
  const dotFor = (w, r, ring = 4) => (w == null || w >= 20 ? { size: r, ring } : w >= 10 ? { size: 3, ring: 3 } : { size: 2.5, ring: 0 });
  // The range across the methods with the estimate on it: an outline where few lender-weeks stand behind it.
  function estimateMark(svg, x, mid, c, barH, r) {
    const barred = isNum(c.lo) && isNum(c.hi);
    const w = barred ? Math.max(4, Math.abs(x(c.hi) - x(c.lo))) : null;
    if (barred) {
      const bar = svg.append('rect').attr('x', (x(c.lo) + x(c.hi) - w) / 2).attr('y', mid - barH / 2).attr('width', w).attr('height', barH).attr('rx', 3);
      if (c.rough) bar.attr('x', (x(c.lo) + x(c.hi) - w) / 2 + 0.75).attr('y', mid - barH / 2 + 0.75).attr('width', w - 1.5).attr('height', barH - 1.5).attr('fill', 'none').attr('stroke', C_VS4).attr('stroke-width', 1.5);
      else bar.attr('fill', C_VS4);
    }
    const { size, ring } = dotFor(w, r);
    svg.append('circle').attr('cx', x(c.dot)).attr('cy', mid).attr('r', size).attr('fill', C_DOT).attr('stroke', 'var(--color-panel)').attr('stroke-width', ring).style('paint-order', 'stroke');
  }

  // The answer: its lead line above the chart, the chart's caption and then the same-FICO lines as a list under it, which is the order their terms are read in. The same-number line opens the second card.
  function answerLine(tag, cls, row, left) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    el.dataset.source = 'rates';
    el.dataset.field = 'text';
    el.dataset.where = `view=answer&key=${row.key}`;
    el.append(...runIn(rangeDash(row.text), left));
    return el;
  }
  function drawAnswer({ st, all, meta }, left) {
    const box = document.getElementById('ra-answer');
    const points = document.getElementById('ra-points');
    box.classList.toggle('dash-skeleton', st === 'loading');
    points.classList.toggle('dash-skeleton', st === 'loading');
    const lines = all.filter((r) => r.view === 'answer' && r.text).sort((a, b) => a.order - b.order);
    const opening = lines.filter((r) => r.key === 'lead').map((r) => answerLine('p', 'ra-lead', r, left));
    box.hidden = !!lines.length && !opening.length;
    rateText('ra-stamp', st, meta.stamp, left);
    points.replaceChildren(...lines.filter((r) => ['same_fico', 'same_llpa'].includes(r.key)).map((r) => answerLine('li', null, r, left)));
    points.hidden = st !== 'loading' && !points.children.length;
    if (!lines.length) {
      const only = document.createElement('p');
      if (st === 'ok' && meta.answer) {  // every answer line run together is body text, not a lead
        only.dataset.source = 'rates';
        only.dataset.field = 'answer';
        only.dataset.where = 'view=meta';
      } else only.className = 'ra-lead';
      // A chart can stand with no answer rows, so the line about no figures prints only where nothing is drawn.
      only.textContent = st === 'loading' ? '' : st !== 'ok' ? 'Failed to load' : meta.answer || (all.some((r) => r.view === 'row') ? '' : 'No rate figures in this build.');
      box.hidden = st === 'ok' && !only.textContent;
      return box.replaceChildren(only);
    }
    box.replaceChildren(...opening);
  }

  // What the controls do to the gap, rung by rung. A bar is square at zero and rounded at its value.
  const STEP_RUNGS = [['raw', 'Raw gap, by loan'], ['time', 'Same week and closing month'], ['lender', 'Plus lender, channel, purpose'], ['traits', 'Plus GSE and LTV range'], ['traits_under', 'VS4 under 820 only'], ['number', 'Plus the same score number']];
  const stepBp = (v) => bpText(Math.abs(v) < 10 ? nearBp(v) : Math.round(v));
  const hBar = (x0, x1, top, h) => {
    const s = x1 < x0 ? -1 : 1, c = Math.min(4, Math.abs(x1 - x0), h / 2);
    return `M${x0},${top}H${x1 - s * c}Q${x1},${top} ${x1},${top + c}V${top + h - c}Q${x1},${top + h} ${x1 - s * c},${top + h}H${x0}Z`;
  };
  function drawRateSteps({ st, all }) {
    const rungs = STEP_RUNGS.map(([key, label]) => ({ ...(all.find((r) => r.view === 'steps' && r.key === key) || {}), key, label })).filter((r) => isNum(r.gap));
    const wrap = document.getElementById('ra-steps-wrap');
    wrap.hidden = st === 'ok' && rungs.length < 3;
    const gapOf = (key) => (rungs.find((r) => r.key === key) || {}).gap;
    const raw = gapOf('raw'), mixed = gapOf('lender');
    document.getElementById('ra-steps-h').textContent = isNum(raw) && raw > 0 && isNum(mixed) && Math.abs(mixed) < raw / 2 ? `Most of the raw ${d3.format('.0f')(raw)} bp gap is timing and lender mix` : 'What the controls do to the raw gap';
    const lead = all.find((r) => r.view === 'row' && r.key === 'same_number') || {};
    const last = rungs[rungs.length - 1];
    const parted = !!last && last.key === 'number' && isNum(lead.dot) && stepBp(last.gap) !== bpText(lead.dot);
    const note = document.getElementById('ra-steps-note');
    note.hidden = st !== 'ok' || wrap.hidden;
    note.textContent = `VS4 minus FICO, bp. Both sides issued from Oct 1${parted ? `, so it ends at ${stepBp(last.gap)}, not ${bpText(lead.dot) === '0' ? 'the same-number figure' : `the ${bpText(lead.dot)}`} above, which goes back to Jul 20` : ''}.`;
    const box = document.getElementById('ra-steps');
    if (wrap.hidden || !document.getElementById('ra-firm').open || !prep(box, st)) return rungs.length >= 3;  // a chart in a closed fold has no width, and the fold's toggle draws it
    // Under about 520 px a rung's label takes its own line above its bar, as on the first chart.
    const W = box.clientWidth, narrow = W < 520, rowH = narrow ? 34 : 25, barH = narrow ? 10 : 14;
    const H = rungs.length * rowH;
    box.style.minHeight = `${H}px`;
    const svg = svgFor(box, W, H, `The gap between VS4 and FICO loans as controls are added, bp of note rate, both sides issued from Oct 1. ${rungs.map((r) => `${r.label}: ${stepBp(r.gap)}`).join('. ')}.`);
    const valueW = Math.ceil(textWidth(svg, rungs.map((r) => stepBp(r.gap))));
    const left = narrow ? 0 : Math.min(Math.ceil(textWidth(svg, rungs.map((r) => r.label))) + 12, Math.floor(W * 0.5));
    // Tiny gaps stay tiny bars: the scale reaches at least 1 bp each way a bar runs.
    const lo = Math.min(rungs.some((r) => r.gap < 0) ? -1 : 0, d3.min(rungs, (r) => r.gap)), hi = Math.max(1, d3.max(rungs, (r) => r.gap));
    const x = d3.scaleLinear([lo, hi], [left + (lo < 0 ? valueW + 6 : 0), W - valueW - 6]);
    const end = (r) => (Math.abs(x(r.gap) - x(0)) < 2 ? x(0) + (r.gap < 0 ? -2 : 2) : x(r.gap));
    const fillOf = (r) => (r === last ? C_DOT : 'var(--cds-chart-muted)');
    const barTop = narrow ? 18 : (rowH - barH) / 2;
    const g = svg.append('g').selectAll('g').data(rungs).join('g').attr('transform', (r, i) => `translate(0,${i * rowH})`);
    g.append('text').attr('x', 0).attr('y', narrow ? 8 : rowH / 2).attr('dy', '0.35em').style('fill', 'var(--color-fg)').text((r) => r.label).each(function () { clip(this, narrow ? W : left - 8); });
    g.append('path').attr('d', (r) => hBar(x(0), end(r), barTop, barH)).attr('fill', fillOf);
    g.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', barTop - 2).attr('y2', barTop + barH + 2).attr('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 1.5);
    g.append('text').attr('x', (r) => end(r) + (r.gap < 0 ? -6 : 6)).attr('y', barTop + barH / 2).attr('dy', '0.35em').attr('text-anchor', (r) => (r.gap < 0 ? 'end' : 'start')).style('fill', 'var(--color-fg)').text((r) => stepBp(r.gap));
    const tip = tooltip(box);
    const show = (event, r) => tip.show(event, r.label, [[fillOf(r), 'Gap', `${stepBp(r.gap)} bp`], ...(isNum(r.read) && isNum(r.pool) ? [[null, `Compared: ${int(r.read)} of ${int(r.pool)} VS4 loans`]] : [])]);
    hits(g.append('rect').attr('width', W).attr('height', rowH), show, () => tip.hide());
    tapOff(box, 'ratessteps', () => tip.hide());
    return true;
  }

  // The question, the answer, its chart and its limits.
  function drawRateAnswer() {
    const read = rateRead();
    const { st, all, meta, limitOf } = read;
    const left = new Map(TERM_WORDS);
    drawAnswer(read, left);
    rateText('ra-selected', st === 'loading' ? 'ok' : st, limitOf('selected'), new Map(), runIn);
    document.getElementById('ra-offset').hidden = st !== 'loading' && !all.length;
    document.getElementById('ra-offset-tail').textContent = st === 'ok' && meta.offset_tail ? meta.offset_tail : '';
    rateLine('ra-dated', 'dated', read);
    rateList('ra-limits', st, [limitOf('note_rate'), limitOf('rests_on')], left, true);
    const follows = all.find((r) => r.view === 'follows_score' && r.scope === 'all' && r.sentence);
    // Each fold is read on its own, so the first use of a term in each one gets its dot.
    document.getElementById('ra-score').hidden = !rateList('ra-score-list', st, [meta.score_lead, meta.score_lead && limitOf('ranges'), meta.expected, meta.rule_at_lock, limitOf('past'), follows && follows.sentence, limitOf('same_loans'), meta.test_line, limitOf('line')], new Map(left), true) && st !== 'loading';
    const firm = rateList('ra-firm-list', st, [limitOf('ranges'), limitOf('left_out'), limitOf('method'), limitOf('thin'), limitOf('match'), limitOf('book'), meta.equivalent_more, limitOf('rebuilt')], new Map(left), true);
    const ladder = drawRateSteps(read);
    document.getElementById('ra-firm').hidden = !firm && !ladder && st !== 'loading';
    const box = document.getElementById('ra-chart');
    const key = document.getElementById('ra-legend');
    const items = all.filter((r) => r.view === 'row').sort((a, b) => a.order - b.order);
    const vals = items.filter((r) => isNum(r.dot)).flatMap((r) => [r.tl, r.th, r.lo, r.hi, r.dot]).filter(isNum);
    legend(key, rateKey());
    const wordsLink = document.createElement('button');
    wordsLink.type = 'button';
    wordsLink.className = 'vx-link';
    wordsLink.dataset.go = 'method';
    wordsLink.textContent = 'What the words mean';
    key.append(wordsLink);
    key.hidden = st !== 'loading' && !vals.length;
    box.hidden = st === 'ok' && !vals.length;
    if (box.hidden || !prep(box, st)) return;
    const W = box.clientWidth;
    const m = { top: 2, right: 8, bottom: 46, left: 8 };
    const svg = svgFor(box, W, 10, `VS4 minus FICO, bp of note rate. ${items.map((r) => `${rateName(r)}: ${[isNum(r.dot) ? `estimate ${bpFigure(r.dot)}` : 'too few to compare', ...(isNum(r.dot) && isNum(r.lo) && isNum(r.hi) ? [`how far the 3 methods disagree ${bpSpan(r.lo, r.hi)}`] : []), ...(isNum(r.dot) && isNum(r.tl) && isNum(r.th) ? [`95% range, approximate, ${thinText(r)}`] : [])].join(', ')}`).join('. ')}.`);
    const indent = (r) => (r.strong ? 0 : r.key === 'same_llpa_low' ? 24 : 12);  // a part of a part sits one step further in
    const heavy = 1.08;  // the medium weight runs wider than the text it is measured in
    const figureW = Math.ceil(textWidth(svg, items.map((r) => bpFigure(r.dot))) * heavy);
    const widest = d3.max(items, (r) => indent(r) + Math.max(textWidth(svg, [r.title ?? '']) * heavy, textWidth(svg, [r.sub ?? ''])));
    // Where the labels would take over half the chart, the title and sub take their own lines above the row's plot, and the figure ends the title's line.
    const narrow = W < 520 || widest + 16 > W * 0.5;
    const titles = new Map(items.map((r) => [r, narrow && r.title ? wrapLines(svg, r.title, (W - figureW - 10 - indent(r)) / heavy) : [r.title ?? '']]));
    const subs = new Map(items.map((r) => [r, narrow && r.sub ? wrapLines(svg, r.sub, W - indent(r)) : [r.sub ?? '']]));
    const titleMore = (r) => 15 * (titles.get(r).length - 1);
    const extra = (r) => titleMore(r) + 15 * (subs.get(r).length - 1);
    const rowOf = (r) => (narrow ? 62 + extra(r) : 46);
    const tops = new Map();
    let H = m.top;
    for (const r of items) { tops.set(r, H); H += rowOf(r); }
    H += m.bottom;
    svg.attr('viewBox', `0 0 ${W} ${H}`);
    box.style.minHeight = `${H}px`;
    if (!narrow) {
      m.left = Math.ceil(widest) + 16;
      m.right = figureW + 16;
    }
    const x = d3.scaleLinear([Math.min(0, d3.min(vals)) - 1, Math.max(0, d3.max(vals)) + 1], [m.left, W - m.right]);
    const ticks = x.ticks(Math.max(3, Math.min(9, Math.floor((W - m.left - m.right) / 44))));
    if (narrow) {  // a tick label at the edge of the plot stays inside the chart
      m.left = m.right = Math.max(m.left, Math.ceil(textWidth(svg, ticks.map(bpTick)) / 2) + 1);
      x.range([m.left, W - m.right]);
    }
    const titleY = narrow ? 8 : 15, subY = narrow ? 23 : 31, cyOf = (r) => (narrow ? 45 + extra(r) : 23);
    // Where labels sit above each plot, the grid runs only beside the plots, so no line crosses a label.
    for (const [y1, y2] of narrow ? items.map((r) => [tops.get(r) + cyOf(r) - 11, tops.get(r) + cyOf(r) + 11]) : [[m.top, H - m.bottom]]) {
      svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', (v) => x(v)).attr('x2', (v) => x(v))
        .attr('y1', y1).attr('y2', y2).attr('stroke', 'var(--cds-chart-grid)');
      svg.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', y1).attr('y2', y2)
        .attr('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 1.5);
    }
    svg.append('g').attr('transform', `translate(0,${H - m.bottom + 8})`)
      .call(d3.axisBottom(x).tickValues(ticks).tickFormat(bpTick).tickSize(0)).call(styleAxis);
    const axisWords = 'VS4 minus FICO rate, bp (left of 0: VS4 lower)';
    svg.append('text').attr('x', (m.left + W - m.right) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text(textWidth(svg, [axisWords]) < W ? axisWords : axisWords.replace(' rate,', ','));
    const g = svg.append('g').selectAll('g').data(items).join('g').attr('transform', (r) => `translate(0,${tops.get(r)})`);
    const weight = (r) => (r.strong ? 'var(--cds-font-weight-medium)' : null);
    g.each(function (r) {
      titles.get(r).forEach((line, i) => d3.select(this).append('text').attr('x', indent(r)).attr('y', titleY + 15 * i).attr('dy', '0.35em').style('fill', 'var(--color-fg)').style('font-weight', weight(r)).text(line));
      subs.get(r).forEach((line, i) => d3.select(this).append('text').attr('x', indent(r)).attr('y', subY + titleMore(r) + 15 * i).attr('dy', '0.35em').text(line));
    });
    g.append('text').attr('x', W).attr('y', (r) => (narrow ? titleY : cyOf(r))).attr('dy', '0.35em').attr('text-anchor', 'end').style('fill', 'var(--color-fg)').style('font-weight', weight)
      .text((r) => bpFigure(r.dot));
    const drawn = g.filter((r) => isNum(r.dot));
    const range = drawn.filter((r) => isNum(r.tl) && isNum(r.th));
    range.append('line').attr('x1', (r) => x(r.tl)).attr('x2', (r) => x(r.th)).attr('y1', cyOf).attr('y2', cyOf).attr('stroke', C_THIN).attr('stroke-width', 1.5);
    for (const k of ['tl', 'th']) {
      range.append('line').attr('x1', (r) => x(r[k])).attr('x2', (r) => x(r[k])).attr('y1', (r) => cyOf(r) - 4).attr('y2', (r) => cyOf(r) + 4).attr('stroke', C_THIN).attr('stroke-width', 1.5);
    }
    const barred = (r) => isNum(r.lo) && isNum(r.hi);
    const barW = (r) => Math.max(4, Math.abs(x(r.hi) - x(r.lo)));
    drawn.filter(barred).append('rect').attr('x', (r) => (x(r.lo) + x(r.hi) - barW(r)) / 2).attr('width', barW)
      .attr('y', (r) => cyOf(r) - 6).attr('height', 12).attr('rx', 3).attr('fill', C_VS4);
    const dotOf = (r) => dotFor(barred(r) ? barW(r) : null, narrow ? 3.5 : 6, narrow ? 3 : 4);
    drawn.append('circle').attr('cx', (r) => x(r.dot)).attr('cy', cyOf).attr('r', (r) => dotOf(r).size)
      .attr('fill', C_DOT).attr('stroke', 'var(--color-panel)').attr('stroke-width', (r) => dotOf(r).ring).style('paint-order', 'stroke');
    const tip = tooltip(box);
    const showTip = (event, r) => tip.show(event, r.title ?? '', isNum(r.dot) ? [[C_DOT, 'Estimate', bpFigure(r.dot)], ...spanLine(C_VS4, RANGE_WORDS, r.lo, r.hi), ...(isNum(r.tl) && isNum(r.th) ? [[C_THIN, THIN_WORDS, thinText(r)]] : [])] : [[null, TOO_FEW]]);
    hits(g.append('rect').attr('width', W).attr('height', rowOf), showTip, () => tip.hide());
    tapOff(box, 'rates', () => tip.hide());
  }

  // Same score number by closing month: each line is the midpoint of the two exact-match methods, each bar the range across all three. A month with under half its loans in, or few lender-weeks, is drawn hollow, and only firm months set the axis.
  const NUMBER_LINES = [['stake', col(2), 'Old rule would raise LLPA'], ['no_stake', col(3), 'Old rule would not']];
  const GRID_NOTE = { month: '2026-09-01', text: 'Sep 29: one LLPA grid for both scores announced' };
  const FIRM_IN = 0.5, HOLLOW_NEAR = 5;
  function drawRateNumber() {
    const read = rateRead();
    const { st, all } = read;
    const lead = all.find((r) => r.view === 'row' && r.key === 'same_number') || {};
    const fade = all.find((r) => r.view === 'same_number' && r.scope === 'fade') || {};
    const rows = all.filter((r) => r.view === 'same_number' && r.scope === 'month' && r.close && isNum(r.dot_raw) && NUMBER_LINES.some(([g]) => g === r.group));
    // The answer's same-number line leads, and without it the row's own figure does.
    const answer = all.find((r) => r.view === 'answer' && r.key === 'same_number' && r.text);
    const [statLead, statRest] = leadSplit(answer && answer.text);
    const left = new Map(TERM_WORDS);
    Object.assign(document.getElementById('rn-stat').dataset, answer ? { field: 'text', where: 'view=answer&key=same_number' } : { field: 'dot', where: 'view=row&key=same_number' });
    rateText('rn-stat', st, answer ? statLead.replace(' at the same score number', '') : isNum(lead.dot) ? `${bpText(lead.dot)} bp on VS4 loans under 820` : null, left);
    rateText('rn-rest', st === 'loading' ? 'ok' : st, statRest, left);
    const metaNote = (field) => ({ text: read.meta[field], field, where: 'view=meta' });
    rateList('rn-notes', st, [...(rows.length ? [metaNote('number_blend'), metaNote('number_why'), { text: fade.text, field: 'text', where: 'view=same_number&scope=fade' }] : []), metaNote('number_bands')], left, true);
    const statement = rowsOf('statements').find((r) => r.who === 'Milliman' && r.check === 'pricing' && r.date && !Number.isNaN(parse(r.date).getTime()) && r.statement);
    const said = document.getElementById('rn-said');
    said.hidden = !statement;
    said.replaceChildren();
    if (statement && statement.url) {
      const a = document.createElement('a');
      a.className = 'vx-link';
      a.href = statement.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = statement.who;
      said.append(a);
    } else if (statement) said.append(statement.who);
    if (statement) said.append(`, ${longDay(statement.date)}: ${statement.statement}`);
    rateLine('rn-line', 'milliman_line', read);
    document.getElementById('rn-more').hidden = !statement && !read.meta.milliman_line;
    const saidBp = statement && statement.statement.match(/(\d+(?:\.\d+)?) bp above/);
    document.getElementById('rn-more-h').textContent = saidBp && isNum(lead.dot) && bpText(lead.dot) !== '0' ? `Milliman's +${saidBp[1]} bp beside this ${bpText(lead.dot)}` : 'Milliman\'s figure beside this one';

    const hollow = (r) => !!r.thin || (isNum(r.in_share) && r.in_share < FIRM_IN);
    const months = [...new Set(rows.map((r) => r.close))].sort();
    const latest = months[months.length - 1];
    const lines = NUMBER_LINES.filter(([g]) => rows.some((r) => r.group === g)).map(([g, color, label]) => ({ color, label, pts: months.map((c) => rows.find((r) => r.group === g && r.close === c) || { close: c }) }));
    const shareOf = (c) => (rows.find((r) => r.close === c && isNum(r.in_share)) || {}).in_share;
    const tagOf = (c) => (window.vx.inLabel ? window.vx.inLabel(shareOf(c)) : null);
    const key = document.getElementById('rn-legend');
    // Two lines keep a legend beside their end labels, so color never has to name them alone. The marks are the first chart's, and a month's % in is said once.
    legend(key, [...lines.map((l) => [l.color, l.label, 'line']), SAME_MARKS, ...(rows.some(hollow) ? [[C_THIN, `Hollow, dashed: under half the month's loans are in this chart${rows.some((r) => r.thin) ? ', or few weeks of loans' : ''}. It starts with loans first disclosed Jul 20, and a recent month is not all in yet.`, 'hollow']] : months.some(tagOf) ? [[null, '% in: how much of the month\'s loans are in this chart. It starts with loans first disclosed Jul 20, and a recent month is not all in yet.']] : [])]);
    key.hidden = !rows.length;
    const box = document.getElementById('rn-chart');
    box.hidden = st === 'ok' && !rows.length;
    const sub = document.getElementById('rn-sub');
    sub.hidden = !rows.length;
    sub.textContent = rangeDash(isNum(lead.dot) && bpText(lead.dot) !== '0' && lines.length === 2 ? `VS4 640-819: the ${bpText(lead.dot)} as two kinds of loan.` : 'VS4 640-819, by the month each loan closed.');
    document.getElementById('rate-number').hidden = st === 'ok' && !all.length;
    if (box.hidden || !prep(box, st)) return;
    const partial = [...months.filter(tagOf).map((c) => `${monthShort(c)} ${tagOf(c)}`), ...[...new Set(rows.filter((r) => r.thin).map((r) => r.close))].map((c) => `${monthShort(c)} few lender-weeks`)];
    const W = box.clientWidth, H = 330;
    const m = { top: 26, right: 12, bottom: 64, left: 0 };
    const svg = svgFor(box, W, H, `VS4 minus FICO at the same score number, VS4 640 to 819, bp of note rate, by closing month. ${lines.map((l) => `${l.label}: ${l.pts.filter((r) => isNum(r.dot_raw)).map((r) => `${monthShort(r.close)} ${readText(r.dot, r.spread_lo, r.spread_hi)}`).join(', ')}`).join('. ')}.${partial.length ? ` Partial months: ${partial.join(', ')}.` : ''}`);
    const firm = rows.filter((r) => !hollow(r));
    const marksOf = (list) => list.flatMap((r) => [r.dot_raw, r.lo_raw, r.hi_raw]).filter(isNum);
    const firmExt = marksOf(firm.length ? firm : rows);
    // A hollow month widens the axis only when its marks sit near the firm months'; one far off stays at the edge and says its figure.
    const ext = [...firmExt, ...marksOf(rows.filter(hollow)).filter((v) => v >= d3.min(firmExt) - HOLLOW_NEAR && v <= d3.max(firmExt) + HOLLOW_NEAR)];
    const y = d3.scaleLinear([Math.min(0, d3.min(ext)), Math.max(0, d3.max(ext))], [H - m.bottom, m.top]).nice(6);
    const [yLo, yHi] = y.domain();
    const yAt = (v) => y(Math.max(yLo, Math.min(yHi, v)));
    const yVals = y.ticks(4);
    const yTick = (v) => (v === yVals[yVals.length - 1] ? `${bpTick(v)} bp` : bpTick(v));
    m.left = Math.ceil(textWidth(svg, yVals.map(yTick))) + 10;
    const tagSize = W < 300 ? '9px' : W < 420 ? '10px' : null;
    const tagW = textWidth(svg, months.map(tagOf).filter(Boolean), tagSize);
    const ends = lines.map((l) => wrapLines(svg, l.label, W < 420 ? 60 : 160));
    m.right = Math.max(Math.ceil(textWidth(svg, ends.flat())) + 14, Math.ceil(Math.max(textWidth(svg, [monthShort(latest)]), tagW) / 2) + 2);
    const x = d3.scalePoint(months, [m.left + 14, W - m.right]);
    const tickOf = (c) => (c === latest || x.step() < 72 ? monthShort(c) : monthLabel(months)(c));
    const every = Math.max(1, Math.ceil(Math.max(textWidth(svg, months.map(tickOf)) + (W < 420 ? 6 : 10), tagW + 4) / x.step()));
    const shown = months.filter((c, i) => (months.length - 1 - i) % every === 0);
    const at = months.indexOf(GRID_NOTE.month);
    const noteX = at >= 0 && at < months.length - 1 ? (x(months[at]) + x(months[at + 1])) / 2 : null;
    const note = noteX == null ? [] : wrapLines(svg, GRID_NOTE.text, noteX - 6);
    m.top = 12 + Math.max(1, note.length) * 15;
    y.range([H - m.bottom, m.top]);
    yAxis(svg, y, yTick, m.left, W - m.right, yVals);
    svg.append('line').attr('x1', m.left).attr('x2', W - m.right).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 1.5);
    if (noteX != null) {
      svg.append('line').attr('x1', noteX).attr('x2', noteX).attr('y1', 4).attr('y2', H - m.bottom).attr('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '3 3');
      textLines(svg, note, noteX - 5, 4 + (note.length * 15) / 2, 'end');
    }
    const xf = (r) => x(r.close);
    lines.forEach((l, i) => {
      const off = lines.length > 1 ? (i ? 4 : -4) : 0;
      for (const r of l.pts.filter((d) => isNum(d.dot_raw) && isNum(d.lo_raw) && isNum(d.hi_raw))) {
        const h = Math.max(3, yAt(r.lo_raw) - yAt(r.hi_raw));
        const bar = svg.append('rect').attr('y', (yAt(r.lo_raw) + yAt(r.hi_raw) - h) / 2).attr('height', h).attr('rx', 3);
        if (hollow(r)) bar.attr('x', xf(r) + off - 2.5).attr('width', 5).attr('fill', 'none').attr('stroke', l.color).attr('stroke-width', 1);
        else bar.attr('x', xf(r) + off - 3).attr('width', 6).attr('fill', l.color).attr('fill-opacity', 0.55);
      }
    });
    for (const l of lines) {
      l.pts.forEach((r, i) => {
        const a = l.pts[i - 1];
        if (!a || !isNum(a.dot_raw) || !isNum(r.dot_raw)) return;
        const dashed = hollow(r) || hollow(a);
        svg.append('line').attr('x1', xf(a)).attr('y1', yAt(a.dot_raw)).attr('x2', xf(r)).attr('y2', yAt(r.dot_raw)).attr('stroke', l.color).attr('stroke-width', 2)
          .attr('stroke-linecap', dashed ? 'butt' : 'round').attr('stroke-dasharray', dashed ? '4 4' : null);
      });
    }
    for (const l of lines) {
      const pts = l.pts.filter((r) => isNum(r.dot_raw));
      svg.append('g').selectAll('circle').data(pts).join('circle').attr('cx', xf).attr('cy', (r) => yAt(r.dot_raw)).attr('r', 5)
        .attr('fill', (r) => (hollow(r) ? 'var(--color-panel)' : l.color)).attr('stroke', 'var(--color-panel)').attr('stroke-width', 2);
      svg.append('g').selectAll('circle').data(pts.filter(hollow)).join('circle').attr('cx', xf).attr('cy', (r) => yAt(r.dot_raw)).attr('r', 3.5)
        .attr('fill', 'var(--color-panel)').attr('stroke', l.color).attr('stroke-width', 2);
    }
    // A hollow month off the firm months' scale sits at the edge and says its figure, stepping in from the edge where both lines are off it, and left of the point at the end labels. A bar end cut at the edge says its figure the same way.
    months.forEach((c) => {
      for (const sign of [1, -1]) {
        const past = (v) => isNum(v) && (sign > 0 ? v > yHi : v < yLo);
        lines.map((l) => l.pts.find((r) => r.close === c)).map((r) => (past(r.dot_raw) ? r.dot_raw : past(sign > 0 ? r.hi_raw : r.lo_raw) ? (sign > 0 ? r.hi_raw : r.lo_raw) : null)).filter(isNum).forEach((v, i) => {
          svg.append('text').attr('class', 'ra-halo').attr('x', x(c) + (c === latest ? -10 : 10)).attr('y', yAt(v) + sign * i * 15).attr('dy', '0.35em').attr('text-anchor', c === latest ? 'end' : 'start').text(bpText(nearBp(v)));
        });
      }
    });
    // End labels name the lines by group. Two that would meet move apart, with a leader back to each line.
    const lastAt = lines.map((l) => [...l.pts].reverse().find((r) => isNum(r.dot_raw)));
    const spots = lines.map((l, i) => ({ i, from: yAt(lastAt[i].dot_raw), h: ends[i].length * 15 })).sort((a, b) => a.from - b.from);
    spots.forEach((s) => { s.to = s.from; });
    if (spots.length === 2 && spots[1].from - spots[0].from < (spots[0].h + spots[1].h) / 2 + 2) {
      const mid = (spots[0].from + spots[1].from) / 2, half = (spots[0].h + spots[1].h) / 4 + 1;
      spots[0].to = mid - half;
      spots[1].to = mid + half;
    }
    const nudge = Math.max(0, m.top + spots[0].h / 2 - spots[0].to) - Math.max(0, spots[spots.length - 1].to + spots[spots.length - 1].h / 2 - (H - m.bottom));
    for (const s of spots) {
      s.to += nudge;
      const px = xf(lastAt[s.i]), labelX = x(latest) + 14;
      if (Math.abs(s.to - s.from) > 3 || px !== x(latest)) svg.append('line').attr('x1', px + 8).attr('y1', s.from).attr('x2', labelX - 2).attr('y2', s.to).attr('stroke', 'var(--cds-chart-reference)');
      textLines(svg, ends[s.i], labelX, s.to);
    }
    svg.append('g').attr('transform', `translate(0,${H - m.bottom + 8})`).call(d3.axisBottom(x).tickValues(shown).tickFormat(tickOf).tickSize(0)).call(styleAxis);
    for (const c of shown.filter(tagOf)) svg.append('text').attr('x', x(c)).attr('y', H - 24).attr('text-anchor', 'middle').style('font-size', tagSize).text(tagOf(c));
    svg.append('text').attr('x', (m.left + W - m.right) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text('VS4 minus FICO, by closing month');
    const tip = tooltip(box);
    const rule = svg.append('line').attr('y1', m.top).attr('y2', H - m.bottom).attr('stroke', 'var(--cds-chart-axis)').attr('opacity', 0);
    const hide = () => { rule.attr('opacity', 0); tip.hide(); };
    const show = (event) => {
      const px = d3.pointer(event, svg.node())[0];
      const near = d3.least(months, (c) => Math.abs(x(c) - px));
      const tag = tagOf(near);
      rule.attr('x1', x(near)).attr('x2', x(near)).attr('opacity', 1);
      tip.show(event, monthYear(near), [...(tag ? [[null, `${tag.startsWith('under') ? 'Under' : 'About'} ${tag.replace(/^under /, '').replace(' in', '')} of the month's loans are in this chart`]] : []),
        ...lines.map((l) => [l, l.pts.find((r) => r.close === near)]).filter(([, r]) => isNum(r.dot_raw))
          .map(([l, r]) => [l.color, l.label, [isNum(r.dot) ? bpText(r.dot) : '—', isNum(r.spread_lo) && isNum(r.spread_hi) ? `3 methods ${bpText(r.spread_lo)} to ${bpText(r.spread_hi)}` : null, isNum(r.n) ? `${int(r.n)} loans` : null, r.thin ? 'few lender-weeks' : null].filter(Boolean).join(', ')])]);
    };
    hits(svg.append('rect').attr('x', m.left).attr('y', m.top).attr('width', W - m.left).attr('height', H - m.top - m.bottom), show, hide);
    tapOff(box, 'ratesnumber', hide);
  }

  // Which FICO has paid the same rate as a VS4 score: a dumbbell from the VS4 number to the FICO that pays the same rate, with the FICO these borrowers show apart from it.
  const EQ_COLOR = col(1), EQ_SHOWN = 'var(--color-fg)';
  function drawRateEqual() {
    const read = rateRead();
    const { st, all, meta } = read;
    const [statLead, statRest] = leadSplit(meta.equivalent_stat);
    rateText('re-stat', st, statLead);
    rateText('re-stat-rest', st === 'loading' ? 'ok' : st, statRest, new Map(TERM_WORDS));
    rateLine('re-caption', 'equivalent_caption', read);
    const items = all.filter((r) => r.view === 'equivalent' && r.band && isNum(r.vs_mean)).sort((a, b) => a.order - b.order);
    const key = document.getElementById('re-legend');
    legend(key, [[EQ_SHOWN, 'FICO these borrowers show', 'diamond'], [EQ_COLOR, 'FICO that pays the same rate (line: does not resample lenders, so too narrow)', 'box'], [C_VS4, 'VS4 number', 'dot']]);
    key.hidden = st !== 'loading' && !items.length;
    const box = document.getElementById('re-chart');
    box.hidden = st === 'ok' && !items.length;
    document.getElementById('rate-equal').hidden = box.hidden;
    if (box.hidden || !prep(box, st)) return;
    const W = box.clientWidth, rowH = 30, narrow = W < 520, tiny = W < 300;
    const m = { top: 22, right: 14, bottom: 42, left: 0 };
    const eqAt = (r) => !r.use_bp && isNum(r.eq);
    const eqSpan = (r) => (isNum(r.eq_lo) && isNum(r.eq_hi) ? ` (${score(r.eq_lo)} to ${score(r.eq_hi)})` : '');
    const pointsText = (r) => `${int(r.points)} ${Math.abs(r.points) === 1 ? 'point' : 'points'}`;
    const FLAT = 'rate barely moves with score here';
    const svg = svgFor(box, W, 10, `Which FICO has paid the same rate as a VS4 score, by VS4 band. ${items.map((r) => `${rangeDash(r.band)}: ${[`VS4 number ${score(r.vs_mean)}`, r.use_bp ? FLAT : isNum(r.eq) ? `the FICO that pays the same rate ${score(r.eq)}${eqSpan(r)}` : null, isNum(r.fico_mean) ? `the FICO these borrowers show ${score(r.fico_mean)}` : null, isNum(r.points) ? `VS4 ${pointsText(r)} above that FICO` : null].filter(Boolean).join(', ')}`).join('. ')}.`);
    m.left = Math.ceil(textWidth(svg, [...items.map((r) => rangeDash(r.band)), 'VS4 band'])) + 12;
    const H = m.top + items.length * rowH + m.bottom;
    svg.attr('viewBox', `0 0 ${W} ${H}`);
    box.style.minHeight = `${H}px`;
    const vals = items.flatMap((r) => [r.vs_mean, r.fico_mean, ...(eqAt(r) ? [r.eq, r.eq_lo, r.eq_hi] : [])]).filter(isNum);
    const x = d3.scaleLinear([d3.min(vals), d3.max(vals)], [m.left + 8, W - m.right - 8]).nice();
    const ticks = x.ticks(Math.max(3, Math.min(10, Math.floor((W - m.left - m.right) / 60))));
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', (v) => x(v)).attr('x2', (v) => x(v)).attr('y1', m.top).attr('y2', H - m.bottom).attr('stroke', 'var(--cds-chart-grid)');
    svg.append('g').attr('transform', `translate(0,${H - m.bottom + 6})`).call(d3.axisBottom(x).tickValues(ticks.filter((v, i) => i % 2 === 0)).tickFormat(score).tickSize(0)).call(styleAxis);
    svg.append('text').attr('x', (x.range()[0] + x.range()[1]) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text('Credit score');
    textLines(svg, ['VS4 band'], 0, (m.top - 6) / 2);
    const g = svg.append('g').selectAll('g').data(items).join('g').attr('transform', (r, i) => `translate(0,${m.top + i * rowH})`);
    const cy = rowH / 2;
    const dr = narrow ? 5.5 : 7, sq = tiny ? 3 : narrow ? 4 : 5, vr = tiny ? 4 : narrow ? 5 : 6, ring = tiny ? 2 : 4;
    const diamond = (sel) => sel.append('path').attr('d', `M0,${-dr}L${dr},0L0,${dr}L${-dr},0Z`).attr('transform', (r) => `translate(${x(r.fico_mean)},${cy})`).attr('stroke', EQ_SHOWN).attr('stroke-width', 1.5);
    g.append('text').attr('x', 0).attr('y', cy).attr('dy', '0.35em').style('fill', 'var(--color-fg)').text((r) => rangeDash(r.band));
    g.filter(eqAt).append('line').attr('x1', (r) => x(r.vs_mean)).attr('x2', (r) => x(r.eq)).attr('y1', cy).attr('y2', cy).attr('stroke', 'var(--cds-chart-axis)');
    const span = g.filter((r) => eqAt(r) && isNum(r.eq_lo) && isNum(r.eq_hi));
    span.append('line').attr('x1', (r) => x(r.eq_lo)).attr('x2', (r) => x(r.eq_hi)).attr('y1', cy).attr('y2', cy).attr('stroke', EQ_COLOR).attr('stroke-width', 1.5);
    if (!narrow) for (const k of ['eq_lo', 'eq_hi']) span.append('line').attr('x1', (r) => x(r[k])).attr('x2', (r) => x(r[k])).attr('y1', cy - 4).attr('y2', cy + 4).attr('stroke', EQ_COLOR).attr('stroke-width', 1.5);
    const shown = g.filter((r) => isNum(r.fico_mean));
    diamond(shown).attr('fill', 'var(--color-panel)');
    g.filter(eqAt).append('rect').attr('x', (r) => x(r.eq) - sq).attr('y', cy - sq).attr('width', 2 * sq).attr('height', 2 * sq).attr('rx', 2).attr('fill', EQ_COLOR).attr('stroke', 'var(--color-panel)').attr('stroke-width', narrow ? 1 : 2);
    diamond(shown).attr('fill', 'none');
    g.append('circle').attr('cx', (r) => x(r.vs_mean)).attr('cy', cy).attr('r', vr).attr('fill', C_VS4).attr('stroke', 'var(--color-panel)').attr('stroke-width', ring).style('paint-order', 'stroke');
    // Where the rate barely moves there is no FICO to mark, and the row says so left of its marks, or right of them where the left has no room.
    g.filter((r) => r.use_bp).each(function (r) {
      const ends = [r.vs_mean, r.fico_mean].filter(isNum).map((v) => x(v));
      const words = narrow ? 'rate barely moves' : FLAT;
      const leftRoom = Math.min(...ends) - dr - 6 - m.left, rightRoom = W - Math.max(...ends) - dr - 6;
      const toLeft = leftRoom >= rightRoom;
      textLines(d3.select(this), wrapLines(svg, words, Math.max(leftRoom, rightRoom)), toLeft ? Math.min(...ends) - dr - 6 : Math.max(...ends) + dr + 6, cy, toLeft ? 'end' : 'start').forEach((t) => t.attr('class', 'ra-halo'));
    });
    const tip = tooltip(box);
    const show = (event, r) => tip.show(event, `VS4 ${rangeDash(r.band)}`, [
      [C_VS4, 'VS4 number', score(r.vs_mean)],
      ...(r.use_bp ? [[null, 'Rate barely moves with score here']] : isNum(r.eq) ? [[EQ_COLOR, 'FICO that pays the same rate', `${score(r.eq)}${eqSpan(r)}`]] : []),
      ...(isNum(r.fico_mean) ? [[EQ_SHOWN, 'FICO these borrowers show, where shown', score(r.fico_mean)]] : []),
      ...(isNum(r.fico_rare) ? [[null, 'At lenders that rarely use VS4, FICO', `${score(r.fico_rare)}${isNum(r.fico_rare_n) ? ` on ${int(r.fico_rare_n)} loans` : ''}`]] : []),
      ...(isNum(r.n) ? [[null, 'Loans', int(r.n)]] : [])]);
    hits(g.append('rect').attr('width', W).attr('height', rowH), show, () => tip.hide());
    tapOff(box, 'ratesequal', () => tip.hide());
  }

  // Each lender's three figures in rows, with one scale across the columns. A row that does not compare like for like is left out of the panels and gets a line of its own under them.
  const LENDER_READS = [['same_fico', 'Same FICO'], ['same_llpa', 'Same FICO, same LLPA'], ['same_number', 'Same score number under 820']];
  const lenderCell = (r, k) => ({ r, dot: r[`${k}_dot`], lo: r[`${k}_lo`], hi: r[`${k}_hi`], rough: r[`${k}_rough`], n: r[`${k}_n`], weeks: r[`${k}_weeks`], read5: r[`${k}_read5`], read_tier: r[`${k}_read_tier`] });
  const lenderWords = (c) => (isNum(c.dot) ? readText(c.dot, c.lo, c.hi) : TOO_FEW);
  // When each lender prices on VS4, from its own loans: a lead while one keeps to a switch point and the other uses VS4 almost whenever it is higher, then the shares: the 20+ share over every week with the indicator, both GSEs; the 1 to 19 share in the latest weeks; and, where it shows both on few of its loans, how few.
  const BOTH_FEW = 0.75;
  const keepsSwitch = (l) => isNum(l.above) && isNum(l.below_late) && l.above >= 0.9 && l.below_late < 0.2;
  const usesWhenever = (l) => isNum(l.above) && isNum(l.below_late) && l.above >= 0.75 && l.below_late >= 0.75;
  function lenderRules() {
    const stages = rowsOf('lender_stage').filter((r) => r.view === 'lender');
    const read = ['rocket-mortgage', 'united-wholesale-mortgage'].map((id) => stages.find((r) => r.id === id)).filter((l) => l && l.short && (isNum(l.above) || isNum(l.below_late)));
    if (!read.length) return [];
    const out = [];
    const keeper = read.find(keepsSwitch), user = read.find(usesWhenever);
    if (keeper && user) {
      const first = document.createElement('p');
      first.className = 'ra-lead';
      first.append(`They differ in when they use VS4: ${keeper.short} at 20+ points above FICO${keeper.rule === 'moving' ? ', starting to dip below 20 on its newest loans' : ''}; ${user.short} almost whenever it is higher.`);
      out.push(first);
    }
    const above = read.filter((l) => isNum(l.above)), below = read.filter((l) => isNum(l.below_late));
    const shares = (list, field) => list.map((l) => `${l.short} ${pct0(l[field])}`).join(', ');
    const body = document.createElement('p');
    body.className = 'vx-sub';
    body.append(above.length ? `Share priced on VS4, on loans showing both scores: at 20+ above FICO, ${shares(above, 'above')}${below.length ? `; at 1 to 19 above, in the latest weeks, ${shares(below, 'below_late')}` : ''}.` : `Share priced on VS4, on loans showing both scores, at 1 to 19 above FICO, in the latest weeks: ${shares(below, 'below_late')}.`);
    for (const l of read) if (isNum(l.both_late) && l.both_late < BOTH_FEW) body.append(` ${l.short}'s rests on the ${pct0(l.both_late)} of its latest${l.both_at === 'FNMA' ? ' Fannie' : ''} loans showing both; the rest's VS4 is unknown.`);
    out.push(body);
    return out;
  }
  function drawRateLender() {
    const read = rateRead();
    const { st, all, meta } = read;
    document.getElementById('rl-rules').replaceChildren(...lenderRules());
    rateText('rl-rates', st === 'loading' ? 'ok' : st, meta.lender_rates);
    const rows = all.filter((r) => r.view === 'lender' && r.scope === 'group' && r.label).sort((a, b) => a.order - b.order);
    const like = rows.filter((r) => !r.not_like_for_like), apart = rows.filter((r) => r.not_like_for_like);
    const anyRough = like.some((r) => LENDER_READS.some(([k]) => { const c = lenderCell(r, k); return c.rough && isNum(c.dot); }));
    const key = document.getElementById('rl-legend');
    legend(key, [SAME_MARKS, ...(anyRough ? [roughKey] : [])]);
    key.hidden = st !== 'loading' && !like.some((r) => LENDER_READS.some(([k]) => isNum(lenderCell(r, k).dot)));
    document.getElementById('rate-lender').hidden = st === 'ok' && !rows.length;
    rateText('rl-apart', st, apart.map((r) => `${r.label} is left out as not like for like${meta.rc_reason ? ` (${meta.rc_reason})` : ''}${isNum(r.same_number_dot) ? `: ${bpText(r.same_number_dot)} at the same score number` : ''}.`).join(' '));
    document.getElementById('rl-note').hidden = st !== 'ok' || !like.length;
    document.getElementById('rl-few').hidden = !anyRough || !!meta.lender_rates;
    const box = document.getElementById('rl-chart');
    box.hidden = st === 'ok' && !like.length;
    if (box.hidden || !prep(box, st)) return;
    const W = box.clientWidth;
    const svg = svgFor(box, W, 10, `VS4 minus FICO by lender and channel, bp of note rate. ${like.map((r) => `${r.label}: ${LENDER_READS.map(([k, title]) => { const c = lenderCell(r, k); return `${title} ${lenderWords(c)}${c.rough && isNum(c.dot) ? ', few lender-weeks' : ''}`; }).join(', ')}`).join('. ')}.`);
    const vals = like.flatMap((r) => LENDER_READS.flatMap(([k]) => { const c = lenderCell(r, k); return isNum(c.dot) ? [c.dot, c.lo, c.hi] : []; })).filter(isNum);
    const dom = d3.scaleLinear(vals.length ? [Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))] : [-1, 1], [0, 1]).nice(4).domain();
    const allLabel = Math.ceil(textWidth(svg, like.map((r) => r.label))) + 12;
    const gap = 18, edge = Math.max(8, Math.ceil(textWidth(svg, [bpTick(dom[1])]) / 2) + 1);
    const cw = (W - allLabel - 2 * gap) / 3;
    // Where three columns will not fit they stack, and as on the first chart each row's label takes its own line above its plot, with the grid only beside the plots.
    const stack = cw < 130 || textWidth(svg, like.filter((r) => !isNum(r.same_fico_dot) && isNum(r.same_fico_n)).map((r) => `${TOO_FEW} (${int(r.same_fico_n)})`)) > cw + gap - 2;
    const axisNote = 'VS4 minus FICO, bp';
    const rowH = stack ? 42 : 28, tickH = stack ? 40 : 24;
    // The first column's figures carry its loans, as More cuts does. The other two columns' bases differ, and their tips say so.
    const inLoans = (k) => k === LENDER_READS[0][0];
    const heads = LENDER_READS.map(([k, title]) => {
      const head = inLoans(k) ? `${title}: ${FOREST_HEAD}` : title;
      return stack ? [head] : wrapLines(svg, head, cw / 1.08);  // the medium weight runs wider than the text it is measured in
    });
    const noteLines = stack ? [] : wrapLines(svg, axisNote, allLabel - 8);
    const headH = 15 * Math.max(noteLines.length, d3.max(heads, (h) => h.length)) + 6;
    const panelH = headH + like.length * rowH + (like.length ? tickH : 0);
    const H = stack ? 3 * panelH + 2 * 16 : panelH;
    svg.attr('viewBox', `0 0 ${W} ${H}`);
    box.style.minHeight = `${H}px`;
    textLines(svg, noteLines, 0, headH / 2 - 3);
    const tip = tooltip(box);
    const lift = (event, c, title) => {
      const compared = comparedLine(c, int);
      const counts = [!compared.length && isNum(c.n) ? `${int(c.n)} loans` : null, weeksWords(c.weeks, c.rough && isNum(c.dot))].filter(Boolean).join(', ');
      tip.show(event, `${c.r.label}: ${title}`, [
        ...(isNum(c.dot) ? [[C_DOT, 'Estimate', bpFigure(c.dot)], ...spanLine(C_VS4, RANGE_WORDS, c.lo, c.hi)] : [[null, TOO_FEW]]),
        ...compared, ...(counts ? [[null, counts]] : [])]);
    };
    LENDER_READS.forEach(([k, title], j) => {
      const oy = stack ? j * (panelH + 16) : 0;
      const pl = stack ? 0 : allLabel + j * (cw + gap);
      const pw = stack ? W : cw;
      const px = d3.scaleLinear(dom, stack ? [Math.max(12, edge), W - Math.max(12, edge)] : [pl + 8, pl + pw - edge]);
      const ticks = px.ticks(Math.max(2, Math.floor((px.range()[1] - px.range()[0]) / 44)));
      // A column's estimates sit past the bar's right end, leaning into the gap beside it if need be, or past its left end where they would run off the column or onto the zero line.
      const room = stack ? W : pl + pw + (j < 2 ? gap - 4 : 0);
      textLines(svg, heads[j], stack ? 0 : pl, oy + headH / 2 - 3).forEach((t) => t.style('fill', 'var(--color-fg)').style('font-weight', 'var(--cds-font-weight-medium)'));
      like.forEach((r, i) => {
        const c = lenderCell(r, k), top = oy + headH + i * rowH, plotTop = stack ? top + 16 : top, plotEnd = stack ? top + 34 : top + rowH;
        const mid = (plotTop + plotEnd) / 2, labelY = stack ? top + 8 : mid;
        const label = r.label, loans = inLoans(k) && isNum(c.n) ? ` (${int(c.n)})` : '';
        if (stack || j === 0) svg.append('text').attr('x', 0).attr('y', labelY).attr('dy', '0.35em').style('fill', 'var(--color-fg)').text(label);
        if (isNum(c.dot)) {
          svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', (v) => px(v)).attr('x2', (v) => px(v)).attr('y1', plotTop).attr('y2', plotEnd).attr('stroke', 'var(--cds-chart-grid)');
          svg.append('line').attr('x1', px(0)).attr('x2', px(0)).attr('y1', plotTop).attr('y2', plotEnd).attr('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 1.5);
          estimateMark(svg, px, mid, c, 10, 4.5);
          const ends = [c.dot, c.lo, c.hi].filter(isNum), value = `${bpText(c.dot)}${loans}`, w = textWidth(svg, [value]);
          const right = px(d3.max(ends)) + 7, left = px(d3.min(ends)) - 7;
          const onZero = right < px(0) && right + w > px(0) - 2;
          const leftFits = left - w >= (stack || j ? pl : textWidth(svg, [label]) + 6);
          const start = onZero ? px(0) + 5 : right;  // with no room left of the bar, it starts clear of the zero line
          const fits = start + w <= room;
          const toLeft = leftFits && (onZero || !fits);
          svg.append('text').attr('class', 'ra-halo').attr('x', toLeft ? left : fits ? start : room).attr('y', mid).attr('dy', '0.35em').attr('text-anchor', toLeft || !fits ? 'end' : 'start').style('fill', 'var(--color-fg)').text(value);
        } else if (stack) {
          const words = `${TOO_FEW}${loans}`;  // beside the label, or on the plot's line where it will not fit
          svg.append('text').attr('x', W).attr('y', textWidth(svg, [label]) + 8 + textWidth(svg, [words]) > W ? mid : labelY).attr('dy', '0.35em').attr('text-anchor', 'end').text(words);
        } else {
          svg.append('text').attr('x', pl + 8).attr('y', mid).attr('dy', '0.35em').text(`${TOO_FEW}${loans}`);
        }
        hits(svg.append('rect').attr('x', stack ? 0 : pl).attr('y', top).attr('width', stack ? W : pw).attr('height', rowH), (event) => lift(event, c, title), () => tip.hide());
      });
      const axisY = oy + headH + like.length * rowH + 4;
      if (like.some((r) => isNum(lenderCell(r, k).dot))) {
        svg.append('g').attr('transform', `translate(0,${axisY})`).call(d3.axisBottom(px).tickValues(px.ticks(2)).tickFormat(bpTick).tickSize(0)).call(styleAxis);
        if (stack) svg.append('text').attr('x', (px.range()[0] + px.range()[1]) / 2).attr('y', axisY + 32).attr('text-anchor', 'middle').text(axisNote);
      }
    });
    tapOff(box, 'rateslender', () => tip.hide());
  }

  // The first chart's grammar for the description rows, with the figure and its loans at the right of each row. The figures in a fold share one scale, one left column and one right column; a thin line past the axis stops at its edge with an arrow.
  const forestMarked = (r) => isNum(r.dot) && !r.text;
  const forestVals = (r) => [r.dot, r.spread_lo, r.spread_hi, r.tl, r.th].filter(isNum);
  const forestIndent = (r) => (r.dim === 'purpose' && (r.key === 'C' || r.key === 'R') ? 12 : 0);
  const forestWords = (r) => r.text || (isNum(r.dot) ? readText(r.dot, r.spread_lo, r.spread_hi) : TOO_FEW);
  const forestLoans = (r) => (isNum(r.pool) ? r.pool : r.n);  // every loan in the row, where the row also counts those with a model figure
  const forestFigure = (r) => [forestMarked(r) ? bpText(r.dot) : null, isNum(forestLoans(r)) ? `(${int(forestLoans(r))})` : null].filter(Boolean).join(' ');
  const FOREST_REACH = 20, FOREST_HEAD = 'bp (loans)';
  const forestDomain = (vals) => d3.scaleLinear(vals.length ? [Math.max(-FOREST_REACH, Math.min(0, d3.min(vals))), Math.min(FOREST_REACH, Math.max(0, d3.max(vals)))] : [-1, 1], [0, 1]).nice(6).domain();
  function forestLabel(r) {
    const label = String(r.label);
    if (r.dim === 'ltv') return label.replace(/^(\d+) or less$/, '$1% or less').replace(/^(\d+)(?:\.\d+)?-(\d+)$/, '$1–$2%').replace(/^Over (\d+)$/, 'Over $1%');
    if (r.view === 'fico_gap' || r.scope === 'gapband') return label.replace(/^VS4 /, '').replace(/ FICO$/, '');
    return rangeDash(label);
  }
  function drawForest(box, st, blocks, frame, aria) {
    if (box.hidden || !prep(box, st)) return;
    // Under about 520 px a row's label and figure take a line above its plot, as on the first chart.
    const W = box.clientWidth, narrow = W < 520, rowH = 22, plotH = narrow ? 38 : rowH, headH = 26;
    const ariaOf = (r) => `${forestLabel(r)}: ${forestWords(r).replace(/\.$/, '')}${forestMarked(r) && isNum(r.tl) && isNum(r.th) ? `, 95% range, approximate, ${thinText(r)}` : ''}${r.thin && isNum(r.dot) ? ', few lender-weeks' : ''}${isNum(forestLoans(r)) ? `, ${int(forestLoans(r))} loans` : ''}`;
    const svg = svgFor(box, W, 10, `${aria} ${blocks.flatMap((b) => b.rows.map((r) => `${b.head ? `${b.head}, ` : ''}${ariaOf(r)}`)).join('. ')}.`);
    const figureW = Math.ceil(textWidth(svg, [...frame.rows.map(forestFigure), FOREST_HEAD]));
    const left = narrow ? 0 : Math.ceil(d3.max(frame.rows, (r) => forestIndent(r) + textWidth(svg, [forestLabel(r)]))) + 12;
    const [dLo, dHi] = forestDomain(frame.vals);
    const x = d3.scaleLinear([dLo, dHi], narrow ? [12, W - 12] : [left + 8, W - figureW - 16]);
    const inside = (v) => x(Math.max(dLo, Math.min(dHi, v)));
    const ticks = x.ticks(Math.max(3, Math.min(5, Math.floor((x.range()[1] - x.range()[0]) / 52))));
    const stride = ticks.length > 1 ? Math.ceil((textWidth(svg, ticks.map(bpTick)) + 6) / (x(ticks[1]) - x(ticks[0]))) : 1;
    const labelled = ticks.filter((v, i) => (i - ticks.indexOf(0)) % stride === 0);
    const tip = tooltip(box);
    const show = (event, r, head) => {
      const compared = isNum(r.dot) && !r.text ? comparedLine(r, int) : [];
      const counts = [!compared.length && isNum(forestLoans(r)) ? `${int(forestLoans(r))} loans` : null, weeksWords(r.lender_weeks, r.thin)].filter(Boolean).join(', ');
      tip.show(event, `${head ? `${head}: ` : ''}${forestLabel(r)}`, [
        ...(r.text ? [[null, r.text]] : !isNum(r.dot) ? [[null, TOO_FEW]] : [[C_DOT, 'Estimate', bpFigure(r.dot)], ...spanLine(C_VS4, RANGE_WORDS, r.spread_lo, r.spread_hi), ...(isNum(r.tl) && isNum(r.th) ? [[C_THIN, THIN_WORDS, thinText(r)]] : [])]),
        ...compared, ...(counts ? [[null, counts]] : [])]);
    };
    const hide = () => tip.hide();
    tapOff(box, box.id, hide);
    const figureAt = (y, text) => svg.append('text').attr('x', W).attr('y', y).attr('dy', '0.35em').attr('text-anchor', 'end').text(text);
    let at = 0;
    blocks.forEach((b, i) => {
      if (b.head) {
        svg.append('text').attr('x', 0).attr('y', at + headH - 8).style('fill', 'var(--color-fg)').style('font-weight', 'var(--cds-font-weight-medium)').text(b.head);
        if (!i) svg.append('text').attr('x', W).attr('y', at + headH - 8).attr('text-anchor', 'end').text(FOREST_HEAD);
        at += headH;
      }
      for (const r of b.rows) {
        const indent = forestIndent(r), marked = forestMarked(r), label = forestLabel(r), figure = forestFigure(r);
        const labelEnd = indent + textWidth(svg, [label]);
        const labelY = at + rowH / 2;
        let h = marked ? plotH : rowH;
        svg.append('text').attr('x', indent).attr('y', labelY).attr('dy', '0.35em').style('fill', 'var(--color-fg)').text(label).each(function () { clip(this, narrow ? W - figureW - 8 - indent : left - 6 - indent); });
        if (marked) {
          figureAt(labelY, figure);
          const mid = narrow ? at + 28 : labelY, top = narrow ? at + 18 : at, end = at + plotH;
          svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', (v) => x(v)).attr('x2', (v) => x(v)).attr('y1', top).attr('y2', end).attr('stroke', 'var(--cds-chart-grid)');
          svg.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', top).attr('y2', end).attr('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 1.5);
          if (isNum(r.tl) && isNum(r.th)) {
            svg.append('line').attr('x1', inside(r.tl)).attr('x2', inside(r.th)).attr('y1', mid).attr('y2', mid).attr('stroke', C_THIN).attr('stroke-width', 1.5);
            for (const v of [r.tl, r.th]) {
              if (v >= dLo && v <= dHi) svg.append('line').attr('x1', x(v)).attr('x2', x(v)).attr('y1', mid - 3).attr('y2', mid + 3).attr('stroke', C_THIN).attr('stroke-width', 1.5);
              else svg.append('path').attr('class', 'ra-past').attr('d', `M${inside(v) - (v > dHi ? 5 : -5)},${mid - 4}L${inside(v)},${mid}L${inside(v) - (v > dHi ? 5 : -5)},${mid + 4}`).attr('fill', 'none').attr('stroke', C_THIN).attr('stroke-width', 1.5);
            }
          }
          estimateMark(svg, inside, mid, { dot: r.dot, lo: r.spread_lo, hi: r.spread_hi, rough: r.thin }, 10, 4);
        } else {
          // Words take the plot's place, or a line of their own under the label where they will not fit.
          const words = forestWords(r);
          if (narrow) {
            const line = `${words} ${figure}`.trim();
            const alone = labelEnd + 8 + textWidth(svg, [line]) > W;
            if (alone) svg.append('text').attr('x', indent).attr('y', labelY + rowH - 4).attr('dy', '0.35em').text(line);
            else figureAt(labelY, line);
            h = alone ? 2 * rowH - 4 : rowH;
          } else {
            const alone = left + 8 + textWidth(svg, [words]) > W - figureW - 16;
            svg.append('text').attr('x', alone ? indent : left + 8).attr('y', alone ? labelY + rowH - 4 : labelY).attr('dy', '0.35em').text(words);
            figureAt(labelY, figure);
            h = alone ? 2 * rowH - 4 : rowH;
          }
        }
        hits(svg.append('rect').attr('x', 0).attr('y', at).attr('width', W).attr('height', h), (event) => show(event, r, b.head), hide);
        at += h;
      }
    });
    svg.append('g').attr('transform', `translate(0,${at + 4})`).call(d3.axisBottom(x).tickValues(labelled).tickFormat(bpTick).tickSize(0)).call(styleAxis);
    at += 24;
    svg.append('text').attr('x', (x.range()[0] + x.range()[1]) / 2).attr('y', at + 8).attr('text-anchor', 'middle').text('VS4 minus FICO, bp');
    at += 16;
    const H = Math.ceil(at) + 2;
    svg.attr('viewBox', `0 0 ${W} ${H}`);
    box.style.minHeight = `${H}px`;
  }

  const CUT_BLOCKS = [['ltv', 'LTV'], ['size', 'Loan size'], ['fico', 'FICO band'], ['purpose', 'Purpose']];
  function drawRateFolds() {
    const read = rateRead();
    const { st, all } = read;
    const byOrder = (a, b) => a.order - b.order;
    rateLine('rq-dated', 'dated', read);
    document.getElementById('rq-dated-line').hidden = !read.meta.dated;
    document.getElementById('rate-quote').hidden = !rateList('rq-list', st, all.filter((r) => r.view === 'quote').sort(byOrder).map((r) => r.text)) && st !== 'loading';
    const cuts = all.filter((r) => r.view === 'cut' && r.label && !r.not_like_for_like).sort(byOrder);
    const ficoGaps = all.filter((r) => r.view === 'fico_gap' && r.label).sort(byOrder);
    const gaps = all.filter((r) => r.view === 'same_number' && r.scope === 'gapband' && r.label).sort(byOrder);
    const blocks = CUT_BLOCKS.map(([dim, head]) => ({ head, rows: cuts.filter((r) => r.dim === dim) })).filter((b) => b.rows.length);
    const gapBlocks = [{ head: 'Same FICO', rows: ficoGaps }, { head: 'Same score number', rows: gaps }].filter((b) => b.rows.some(forestMarked));
    const firstRows = blocks.flatMap((b) => b.rows), gapRows = gapBlocks.flatMap((b) => b.rows);
    const anyFirst = firstRows.some(forestMarked), anyGaps = gapRows.length > 0;
    const fold = document.getElementById('rate-cuts');
    fold.hidden = st === 'ok' && !anyFirst && !anyGaps;
    if (fold.open) {  // a chart in a closed fold has no width, and the fold's toggle draws it
      const firstBox = document.getElementById('rc-chart'), gapBox = document.getElementById('rc-gap');
      const key = document.getElementById('rc-legend');
      legend(key, [[null, 'Dot, bar and thin line as above.'], ...(firstRows.concat(gapRows).some((r) => r.thin && forestMarked(r)) ? [roughKey] : [])]);
      key.hidden = st !== 'loading' && !anyFirst && !anyGaps;
      (st === 'ok' && !anyFirst ? gapBox : firstBox).before(key);  // the legend goes with the figure left to read it
      for (const id of ['rc-first-h', 'rc-note']) document.getElementById(id).hidden = st === 'ok' && !anyFirst;
      firstBox.hidden = st === 'ok' && !anyFirst;
      gapBox.hidden = document.getElementById('rc-gap-h').hidden = st === 'ok' && !anyGaps;
      rateText('rc-gap-line', st, anyGaps ? leadSplit(read.meta.gap_line)[0] : null);
      rateText('rc-gap-note', st === 'loading' ? 'ok' : st, gapBlocks.some((b) => b.rows === gaps) ? 'Same number: VS4 loans under 820 showing a FICO.' : null);
      const frame = { rows: [...(anyFirst ? firstRows : []), ...gapRows], vals: [...firstRows, ...gapRows].filter(forestMarked).flatMap(forestVals) };
      drawForest(firstBox, st, blocks, frame, 'Same FICO, same LLPA, VS4 minus FICO in bp of note rate, by loan type, as description.');
      drawForest(gapBox, st, gapBlocks, frame, 'VS4 minus FICO in bp of note rate, by how far VS4 sits above FICO, same FICO and same score number.');
    }
    const rate = all.filter((r) => r.view === 'llpa_rate' && r.label && (isNum(r.lower_dot) || isNum(r.same_dot))).sort(byOrder);
    const table = document.getElementById('llpa-rate-table');
    document.getElementById('llpa-rate-card').hidden = document.getElementById('llpa-first').hidden = st !== 'loading' && !rate.length;
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const body = table.tBodies[0];
    body.replaceChildren();
    const bpLoans = (v, n) => (isNum(v) ? `${bpText(v)}${isNum(n) ? ` (${int(n)})` : ''}` : TOO_FEW);
    for (const r of rate) {
      const tr = body.insertRow();
      tr.dataset.key = ['llpa_rate', r.key].map(keyPart).join(',');
      [[`${r.label}${r.not_like_for_like ? ', not like for like' : ''}`, 'vx-l vx-name'], [r.purpose ?? '', 'vx-l'], [bpLoans(r.lower_dot, r.lower_n)], [bpLoans(r.same_dot, r.same_n)]].forEach(([text, cls]) => {
        const td = tr.insertCell();
        td.textContent = text;
        if (cls) td.className = cls;
      });
    }
    // Every cell here is a midpoint on few lender-weeks, so the caption says so once, rather than each row.
    const rough = rate.flatMap((r) => [...(isNum(r.lower_dot) ? [!!r.lower_rough] : []), ...(isNum(r.same_dot) ? [!!r.same_rough] : [])]);
    const note = document.getElementById('llpa-rate-note');
    note.replaceChildren(...(rough.some(Boolean) ? [`${rough.every(Boolean) ? 'All' : 'Some'} rows are `, termSpan('thin', 'rough'), '. '] : []), 'Rows do not add: each is a midpoint on the loans that find a match.');
    rateLine('llpa-sum', 'llpa_sum', read);
    rateLine('llpa-share', 'llpa_share', read);
  }

  // The build's checks, listed on Method: they warn and stop nothing. Beside them, why Rocket correspondent has its own line and what this tab replaced.
  function drawRateChecks() {
    const read = rateRead();
    const { st, all, meta } = read;
    rateLine('ra-changed', 'changed', read);
    rateText('ra-rc-reason', st, meta.rc_reason);
    document.getElementById('ra-rc-wrap').hidden = !meta.rc_reason;
    rateLine('ra-sample', 'sample', read);
    const rows = all.filter((r) => r.view === 'check').sort((a, b) => a.order - b.order);
    const passed = rows.filter((r) => r.pass === true).length;
    rateText('ra-check-head', st, rows.length ? `This build: ${int(passed)} of ${int(rows.length)} checks passed.${passed === rows.length ? ' They show the methods agree within a few bp on the rows they test, not that the estimates are right.' : ''}` : null);
    const state = (r) => (r.pass === true ? '' : r.pass === false ? ', missed' : ', could not be read');
    // A miss prints past its limit, so the line cannot read as its own contradiction.
    const shown = (r) => (r.pass === false && Math.abs(nearBp(r.value)) <= r.limit ? Math.sign(r.value) * Math.ceil(Math.abs(r.value) * 2) / 2 : nearBp(r.value));
    const inLoans = (r) => r.unit === 'loans';
    rateList('ra-checks', st, rows.filter((r) => r.label).map((r) => [`${r.label}: ${!isNum(r.value) ? '—' : inLoans(r) ? int(r.value) : bpFigure(shown(r))}${isNum(r.limit) ? `, limit ${d3.format('~g')(r.limit)}${inLoans(r) ? '' : ' bp'}` : ''}${state(r)}.`, r.detail].filter(Boolean).join(' ')));
  }

  // Dollars at any size: $0, $420, $48k, $2.1m, $3.4bn, $2.1tn. Under $100k it reads in thousands, so a small amount never shows as $0.0m.
  const usdM = (v) => {
    const a = Math.abs(v), one = d3.format('.1f');
    const text = a >= 999.95e9 ? `$${one(a / 1e12)}tn` : a >= 999.95e6 ? `$${one(a / 1e9)}bn` : a >= 1e5 ? `$${one(a / 1e6)}m` : a >= 1e3 ? `$${d3.format('.0f')(a / 1e3)}k` : money(a);
    return v <= -0.5 ? `−${text}` : text;
  };
  // A yearly figure scaled up from one part month reads no finer than it is: to the nearest $50m from $100m, the nearest $10m under that. Under $10m, or from $1bn, it reads as any other.
  const aboutUsd = (v) => {
    if (v < 1e7 || v >= 1e9) return `About ${usdM(v)}`;
    const step = v >= 1e8 ? 5e7 : 1e7, near = Math.round(v / step) * step;
    return `About ${near < 1e9 ? `$${int(near / 1e6)}m` : usdM(near)}`;
  };

  function drawFees() {
    const st = dash.data('fees').status;
    document.getElementById('fee-sec').hidden = st !== 'ok' && st !== 'loading';
    document.getElementById('fee-fail').hidden = st === 'ok' || st === 'loading';
    const rows = rowsOf('fees');
    const m = rows.find((r) => r.view === 'market' && r.key === 'All') || {};
    const mw = 'view=market&key=All';
    const val = (f, fmt) => (m[f] == null ? null : fmt(m[f]));
    mark('.fe-month', 'month', mw, st, val('month', monthYear));
    mark('.fe-month-s', 'month', mw, st, val('month', monthShort));
    mark('.fe-avg', 'saving_avg_usd', mw, st, val('saving_avg_usd', money));
    mark('.fe-share', 'saving_share', mw, st, val('saving_share', pct1));
    mark('.fe-taken', 'taken_annual_usd', mw, st, val('taken_annual_usd', aboutUsd));
    mark('.fe-taken-m', 'taken_usd', mw, st, val('taken_usd', usdM));
    mark('.fe-scale', null, null, st, isNum(m.taken_annual_usd) && m.taken_usd > 0 ? `scaled about ${int(Math.round(m.taken_annual_usd / m.taken_usd))} times` : 'scaled up');
    const aei = rowsOf('statements').find((r) => r.check === 'fees' && String(r.who).includes('AEI') && r.statement);
    const aeiLine = document.getElementById('fe-aei');
    aeiLine.replaceChildren();
    if (aei) aeiLine.append(` ${aei.statement.split('. ')[0]}. `);
    if (aei && aei.url) {
      const a = document.createElement('a');
      a.className = 'vx-link';
      a.href = aei.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = aei.source;
      aeiLine.append('Source: ', a, '.');
    }
    const lenders = rows.filter((r) => r.view === 'lender' && r.priced_loans >= 20).sort((a, b) => b.taken_usd - a.taken_usd);
    const table = document.getElementById('fee-table');
    table.closest('.vx-tablebox').classList.toggle('dash-skeleton', st === 'loading');
    const heads = table.tHead.rows[0].cells;
    const body = table.tBodies[0];
    body.replaceChildren();
    const orDashL = (fmt) => (v) => (v == null ? '—' : fmt(v));
    for (const r of lenders) {
      const tr = body.insertRow();
      tr.dataset.key = ['lender', r.id].map(keyPart).join(',');
      [olName(r), int(r.priced_loans), orDashL(pct1)(r.saving_share), orDashL(money)(r.saving_avg_usd), usdM(r.taken_usd)].forEach((text, i) => {
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
    gh.replaceChildren(...['Score band'].concat(scopes.map(([, l]) => l), ['VS4 a tier better, same FICO tier']).map((text, i) => {
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
      drawRateAnswer();
      drawRateNumber();
      drawRateEqual();
      drawRateLender();
      drawRateFolds();
      drawFees();
    } else if (current === 'method') {
      drawRateChecks();
    }
    (window.vx.hooks[current] || []).forEach((fn) => fn(p));
    window.vx.after.forEach((fn) => fn());
  }
  window.vx = { root, rowsOf, rateRows, statusOf, int, pct1, money, usdM, ptsSigned, readText, LENDER_READS, inkOn, olName, olPct, openSeller, entityOf, monthShort, monthYear, monthLabel, shortDay, prep, svgFor, bandFrame, yAxis, bandAxis, bandHover, legend, tooltip, textWidth,
    MIX_GROUPS, ADOPT_FROM, AG_NAME, show, col, mark, redraw: draw, after: [], hooks: { overview: [], outlook: [], lenders: [], scores: [], borrowers: [], pricing: [], market: [], method: [] } };

  // A link names a page (#lenders) or a seller (#seller-rocket-mortgage); the page opens it as it loads.
  const named = tabOf(decodeURIComponent(location.hash.slice(1)));
  if (named.startsWith('seller-')) {
    dash.setParams({ seller: named.slice('seller-'.length) });
    place('lenders');
  } else if (TABS.includes(named)) {
    place(named);
  } else {
    place('overview');
  }
  window.addEventListener('hashchange', () => {
    const h = tabOf(decodeURIComponent(location.hash.slice(1)));
    if (h.startsWith('seller-') && !(current === 'lenders' && params().seller === h.slice('seller-'.length))) openSeller(h.slice('seller-'.length));
    else if (TABS.includes(h) && h !== current) { place(h); draw(); }
  });
  // The words link leaves its tab's name on the entry it leaves, so one Back returns there on a host whose setLink leaves this frame's URL alone. A host that moves the URL needs no more than the hash.
  window.addEventListener('popstate', (event) => { if (event.state && event.state.tab && event.state.tab !== current) show(event.state.tab); });
  // A fold of plain text has nothing to measure, so opening it leaves a selection or a focused term alone.
  root.addEventListener('toggle', (event) => { if (event.target.matches('details.vx-more') && event.target.querySelector('.vx-chart, table, .vx-note, .vx-sec-h')) draw(); }, true);
  // A chart is drawn for the width it has, so a print draws at a page's width and then back. The width goes on the page's own box, which is there on any host.
  window.addEventListener('beforeprint', () => { root.style.width = '680px'; draw(); });
  window.addEventListener('afterprint', () => { root.style.width = ''; draw(); });
  dash.onData(draw);
})();
