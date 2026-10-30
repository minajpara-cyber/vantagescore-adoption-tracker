// The whole market, from HMDA: which score lenders named on every kind of loan, which lenders named what, who uses each model, and applications per loan.
// Runs after the other scripts; what they share is on window.vx.
(() => {
  const vx = window.vx;
  const { root, rowsOf, statusOf, int, pct1, prep, legend, tooltip, mark, col } = vx;
  const compact = d3.format('.3~s');
  const two = d3.format('.2f');
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
  const OPTIONAL = new Set(['usd_bn', 'vs_old', 'multi', 'other', 'equity_share']);
  const CHART_LENDERS = 15;

  function bars(box, rows, status, labelOf, cls) {
    if (!box || !prep(box, status)) return;
    box.replaceChildren();
    const tip = tooltip(box);
    rows.forEach((r, i) => {
      const row = node('div', `mk-row ${cls ? cls(r, i) : ''}`);
      const name = node('div', 'mk-l', labelOf(r));
      name.append(node('span', 'mk-n', `${compact(r.n)} loans`));
      const val = node('div', 'mk-v');
      val.append('FICO', node('b', null, pct1(r.fico)), ' ', 'VantageScore', node('b', null, pct1(r.vs)));
      const track = node('div', 'mk-t');
      track.setAttribute('role', 'img');
      track.setAttribute('aria-label', `${labelOf(r)}: ${GROUPS.map(([k, l]) => `${l} ${pct1(r[k])}`).join(', ')}`);
      GROUPS.forEach(([k, , color]) => {
        if (r[k] < 0.0005) return;
        const part = node('span');
        part.style.flex = `${r[k]} 1 0`;
        part.style.background = color;
        track.append(part);
      });
      row.append(name, val, track);
      row.addEventListener('pointermove', (event) => tip.show(event, `${labelOf(r)}, ${int(r.n)} loans`, [[CLASSIC, 'Classic FICO', pct1(r.classic)], [NEWER, 'Newer FICO', pct1(r.fico_new)], [VS, 'VS4', pct1(r.vs4)], [VS, 'VantageScore 2.0, 3.0', pct1(r.vs_old)],
        [UNNAMED, 'More than one model', pct1(r.multi)], [UNNAMED, 'Other model', pct1(r.other)], [NONE, 'No score reported', pct1(r.none)]]));
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
    table('mk-model-table', models, (r) => `model,${r.code}`, (r) => [['name', r.name, true], ['n', int(r.n)], ['equity_share', r.equity_share == null ? '—' : pct1(r.equity_share)], ['users', r.users, true]]);
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

  vx.hooks.market.push(drawMarket);
  vx.redraw();
})();
