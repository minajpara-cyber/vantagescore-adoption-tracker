// Stand-in for the claude.ai Dashboard `dash` API, so the dashboard page (site/dashboard/index.html)
// runs as a plain static site. Each dataset id loads from data/<id>.json ({"rows": [...]}); filters
// live in memory; dash.colors are theme variables defined in the page template.
(function () {
  const DEFAULTS = { agency: 'All', measure: 'loans', dim: 'pricing_score', seller: 'rocket-mortgage', adopt: 'any', period: 'month', top: 25 };
  const sources = {};
  const listeners = [];
  let params = { ...DEFAULTS };

  const notify = () => listeners.forEach((fn) => {
    try { fn(); } catch (err) { console.error(err); }
  });

  function load(id) {
    if (!sources[id]) {
      sources[id] = { status: 'loading', data: [] };
      fetch(`data/${id}.json`, { cache: 'no-cache' })
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((json) => { sources[id] = { status: 'ok', data: Array.isArray(json) ? json : json.rows || [] }; })
        .catch((err) => { sources[id] = { status: 'error', data: [], message: String(err) }; })
        .finally(notify);
    }
    return sources[id];
  }

  window.dash = {
    data(id) {
      const s = load(id);
      return { status: s.status, data: s.data, columns: s.data.length ? Object.keys(s.data[0]) : [], message: s.message, refreshing: false, meta: [] };
    },
    onData(fn) {
      listeners.push(fn);
      fn();
    },
    params: () => ({ ...params }),
    setParams(next) {
      params = { ...params, ...next };
      notify();
    },
    resetParams() {
      params = { ...DEFAULTS };
      notify();
    },
    setLink(name) { history.replaceState(null, '', `#${name}`); },
    refresh() {},
    colors: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => `var(--series-${i})`),
  };

  let width = window.innerWidth;
  window.addEventListener('resize', () => {
    if (window.innerWidth === width) return;
    width = window.innerWidth;
    notify();
  });
})();
