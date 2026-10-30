"""Rate engine: the note rate a Classic FICO-priced loan like each VS4 loan would carry.

Model: a 30-year fixed, FICO-priced loan's note rate is a sum of effects, one per level of each factor
in FACTORS: week of first disclosure, GSE, seller x channel, seller x channel x week, seller x purpose, LLPA
credit score bucket x LTV bucket x purpose, occupancy, units, property type, loan size, DTI, mortgage insurance,
state, first-time buyer and number of borrowers. It is fitted by backfitting, each level's effect
shrunk toward zero as if it had LAMBDA more loans at zero. It trains on FICO-priced loans first
disclosed from WEEKLY_START, except one in five (by loan id) held out to check it: their actual minus
expected rate should average zero overall and in every cell shown.

Each VS4 loan's rate is compared with what the model gives a FICO-priced loan like it:
  headline  in the same fee tier: the VS4 score stands in for Classic FICO, less VS_OFFSET points for loans issued
            before GRID_CHANGE, when FICO's fee tiers applied to VS4 at that many points higher
  own_fico  with the borrower's own Classic FICO, for VS4 loans that disclose both (from BOTH_START)

Groups (the dashboard's score toggle): all (VS4 loans first disclosed from WEEKLY_START), both (VS4
loans that also carry a Classic FICO) and vs4only (VS4 loans with no Classic FICO), the last two among
loans disclosed with every score delivered (records from BOTH_START on, which carry the Pricing
Indicator). Each is checked against the held-out FICO loans of the same group of records.

  pricing   view x cover x basis x key: n, premium_bp (mean actual minus expected rate, basis points),
            se_bp, median_bp, check_n / check_bp for the held-out FICO loans in the same cell, and
            net_bp = premium_bp - check_bp.
            view fit (one row: loans trained and held out, RMSE, R2), overall, week, seller (MIN_N+
            VS4 loans), segment (dim = purpose, score, ltv, channel, size) and hist (share of loans by
            actual-minus-expected bin, VS4 vs held-out FICO). Cells under MIN_N loans are left out.
            view value (cover both, basis own_fico; key: same = VS4-priced in the same fee bucket as its own FICO,
            better = VS4-priced in a better one, 1 / 2 / 3 = that many better, fico_better = FICO-priced with VS4 in
            a better one; for all lenders and each seller with MIN_N+ such loans): the rate against the model at
            the borrower's own FICO, net of the model's miss on held-out FICO loans (net_bp); what the VS4 bucket is
            worth on FICO loans' rates (worth_bp); and reaches, the share of that worth seen in the rate.
"""
import numpy as np

BOTH_START = "2026-10-19"  # the Pricing Indicator, and both scores, are disclosed from here
GRID_CHANGE = "2026-10-01"  # MBS issued from here pay one fee grid whichever score priced the loan
VS_OFFSET = 20  # before that, FICO's fee tiers applied to VS4 at this many points higher
LAMBDA = 10.0
MIN_N = 20
MIN_SELLER_LOANS = 300  # sellers with fewer FICO loans to learn from share an "other" level per channel
PASSES = 40
SCORE_CUTS = [640, 660, 680, 700, 720, 740, 760, 780]  # LLPA credit score buckets
SCORE_LABELS = ["639 or less", "640-659", "660-679", "680-699", "700-719", "720-739", "740-759", "760-779", "780+"]
LTV_CUTS = [30, 60, 70, 75, 80, 85, 90, 95]  # LLPA LTV buckets; each cut is the top of its bucket
LTV_LABELS = ["30 or less", "30.01-60", "60.01-70", "70.01-75", "75.01-80", "80.01-85", "85.01-90", "90.01-95", "Over 95"]
SIZE_CUTS = [100e3, 150e3, 200e3, 250e3, 300e3, 350e3, 400e3, 450e3, 500e3, 600e3, 700e3, 806.5e3]
DTI_CUTS = [20, 30, 36, 40, 45, 50]
SEGMENT_SIZE = ([150e3, 250e3, 400e3, 600e3], ["Under $150k", "$150k-250k", "$250k-400k", "$400k-600k", "$600k+"])
PURPOSE_LABELS = {"P": "Purchase", "C": "Cash-out refinance", "R": "No cash-out refinance"}
CHANNEL_LABELS = {"R": "Retail", "B": "Broker", "C": "Correspondent"}
HIST_EDGES = np.arange(-150.0, 150.1, 12.5)  # basis points; the end bins take everything beyond
FACTORS = ["week", "agency", "seller", "seller_week", "seller_purpose", "grid", "occupancy", "units", "ptype", "size", "dti",
           "mi", "state", "fthb", "borrowers"]


def _load(con, weekly_start: str, in_range: str):
    # Needs seller_map and seller_key from lenders.py on this connection. Ordered so the fit is repeatable.
    return con.execute(f"""
        SELECT l.agency, date_trunc('week', l.first_intraday_date)::DATE::VARCHAR AS week,
               l.pricing_indicator IS NOT NULL AS both_era, m.id AS seller_id,
               coalesce(l.channel, '?') AS channel,
               CASE WHEN l.purpose = 'P' THEN 'P' WHEN l.purpose = 'C' THEN 'C' ELSE 'R' END AS purpose,
               coalesce(l.occupancy, '?') AS occupancy, least(coalesce(l.units, 1), 2) AS units,
               coalesce(l.property_type, '?') AS ptype, coalesce(l.orig_loan_amt, 0) AS amount,
               coalesce(l.dti, -1) AS dti, coalesce(l.mi_pct, 0) > 0 AS mi, coalesce(l.state, '?') AS state,
               coalesce(l.fthb, '?') AS fthb, least(coalesce(l.num_borrowers, 1), 2) AS borrowers,
               l.score_model = 'V' AS is_vs4, l.pricing_score,
               CASE WHEN l.classic_fico BETWEEN 300 AND 850 THEN l.classic_fico ELSE -1 END AS fico,
               CASE WHEN l.vs4 BETWEEN 300 AND 850 THEN l.vs4 ELSE -1 END AS vs,
               l.issue_month < DATE '{GRID_CHANGE}' AS old_grid,
               l.ltv, l.orig_rate, hash(l.agency || l.loan_id) % 5 = 0 AS holdout
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.loan_term = 360 AND l.amort_type = 'FRM' AND l.score_model IN ('C', 'V') AND l.orig_rate > 0
          AND l.first_intraday_date >= DATE '{weekly_start}' AND ({in_range})
          AND l.pricing_score IS NOT NULL AND l.ltv IS NOT NULL
        ORDER BY l.agency, l.loan_id""").fetchnumpy()


def _codes(values):
    levels, inv = np.unique(np.asarray(values).astype(str), return_inverse=True)
    return inv, {lv: i for i, lv in enumerate(levels)}


def _fit(y, codes, sizes, train):
    """Backfitting: each factor's effects are the shrunk mean of what the other factors leave."""
    mu = y[train].mean()
    eff = {f: np.zeros(sizes[f]) for f in codes}
    r = y[train] - mu
    for _ in range(PASSES):
        moved = 0.0
        for f, c in codes.items():
            ct = c[train]
            partial = r + eff[f][ct]
            new = np.bincount(ct, weights=partial, minlength=sizes[f]) / (np.bincount(ct, minlength=sizes[f]) + LAMBDA)
            moved = max(moved, float(np.abs(new - eff[f]).max()))
            r = partial - new[ct]
            eff[f] = new
        if moved < 1e-7:
            break
    return mu, eff


def _predict(mu, eff, codes):
    out = np.full(len(next(iter(codes.values()))), mu)
    for f, c in codes.items():
        out += np.where(c >= 0, eff[f][np.clip(c, 0, None)], 0.0)
    return out


def _cell(prem, check):
    """net_bp: the VS4 loans' gap less the held-out FICO loans' gap in the same cell (what the model misses)."""
    if len(prem) < MIN_N:
        return None
    check_bp = float(check.mean()) if len(check) >= MIN_N else None
    return {"n": int(len(prem)), "premium_bp": round(float(prem.mean()), 2),
            "se_bp": round(float(prem.std(ddof=1) / np.sqrt(len(prem))), 2),
            "median_bp": round(float(np.median(prem)), 2), "check_n": int(len(check)),
            "check_bp": None if check_bp is None else round(check_bp, 2),
            "net_bp": None if check_bp is None else round(float(prem.mean()) - check_bp, 2)}


def build_pricing(con, weekly_start: str, in_range: str) -> list[dict]:
    d = _load(con, weekly_start, in_range)
    y = d["orig_rate"].astype(float)
    is_vs4 = d["is_vs4"].astype(bool)
    holdout = d["holdout"].astype(bool)
    train = ~is_vs4 & ~holdout
    check = ~is_vs4 & holdout
    if train.sum() < MIN_N or check.sum() < MIN_N:
        return []  # too few FICO loans to fit or check a model
    both_era = d["both_era"].astype(bool)
    fico = d["fico"].astype(int)
    has_fico = fico > 0
    # The fee tier a loan paid: a VS4 loan issued under the old grid is priced as if its score were VS_OFFSET lower.
    priced = d["pricing_score"].astype(int)
    fee_score = np.where(is_vs4 & d["old_grid"].astype(bool), priced - VS_OFFSET, priced)
    score_b = np.searchsorted(SCORE_CUTS, fee_score, side="right")
    vs = d["vs"].astype(int)
    vs_b = np.where(vs > 0, np.searchsorted(SCORE_CUTS, vs, side="right"), -1)
    fico_b = np.where(has_fico, np.searchsorted(SCORE_CUTS, fico, side="right"), -1)
    ltv_b = np.searchsorted(LTV_CUTS, d["ltv"].astype(float), side="left")
    seller = d["seller_id"].astype(str)
    learned = np.unique(seller[train], return_counts=True)
    big = set(learned[0][learned[1] >= MIN_SELLER_LOANS])
    week = d["week"].astype(str)
    purpose = d["purpose"].astype(str)
    seller_g = [(s if s in big else "other") + "|" + ch for s, ch in zip(seller, d["channel"].astype(str))]
    raw = {
        "week": week, "agency": d["agency"], "seller": seller_g,
        "seller_week": [g + "|" + w for g, w in zip(seller_g, week)],
        "seller_purpose": [g + "|" + p for g, p in zip(seller_g, purpose)],
        "grid": [f"{s}|{l}|{p}" for s, l, p in zip(score_b, ltv_b, purpose)],
        "occupancy": d["occupancy"], "units": d["units"], "ptype": d["ptype"],
        "size": np.searchsorted(SIZE_CUTS, d["amount"].astype(float), side="right"),
        "dti": np.where(d["dti"] < 0, -1, np.searchsorted(DTI_CUTS, d["dti"].astype(float), side="left")),
        "mi": d["mi"], "state": d["state"], "fthb": d["fthb"], "borrowers": d["borrowers"],
    }
    codes, vocab = {}, {}
    for f in FACTORS:
        codes[f], vocab[f] = _codes(raw[f])
    mu, eff = _fit(y, codes, {f: len(vocab[f]) for f in FACTORS}, train)
    res = (y - _predict(mu, eff, codes)) * 100
    own = dict(codes, grid=np.array([vocab["grid"].get(f"{s}|{l}|{p}", -1) for s, l, p in zip(fico_b, ltv_b, purpose)]))
    res_own = (y - _predict(mu, eff, own)) * 100

    yc = y[check]
    rows = [{"view": "fit", "cover": None, "basis": None, "dim": None, "key": None, "label": None, "order": 0,
             "since": weekly_start, "n": int(check.sum()), "n_train": int(train.sum()),
             "rmse_bp": round(float(np.sqrt((res[check] ** 2).mean())), 2),
             "r2": round(float(1 - ((res[check] / 100) ** 2).sum() / ((yc - yc.mean()) ** 2).sum()), 4),
             "check_bp": round(float(res[check].mean()), 2), "sd_bp": round(float(yc.std() * 100), 2)}]
    names = dict(con.execute("SELECT id, short FROM entity_names").fetchall())
    size_b = np.searchsorted(SEGMENT_SIZE[0], d["amount"].astype(float), side="right")
    segments = {
        "purpose": (purpose, {k: (v, i) for i, (k, v) in enumerate(PURPOSE_LABELS.items())}),
        "channel": (d["channel"].astype(str), {k: (v, i) for i, (k, v) in enumerate(CHANNEL_LABELS.items())}),
        "score": (score_b, {i: (lab, i) for i, lab in enumerate(SCORE_LABELS)}),
        "ltv": (ltv_b, {i: (lab, i) for i, lab in enumerate(LTV_LABELS)}),
        "size": (size_b, {i: (lab, i) for i, lab in enumerate(SEGMENT_SIZE[1])}),
    }
    groups = [("all", "headline", is_vs4, np.ones(len(y), bool), weekly_start),
              ("both", "headline", is_vs4 & both_era & has_fico, both_era, BOTH_START),
              ("both", "own_fico", is_vs4 & both_era & has_fico, both_era, BOTH_START),
              ("vs4only", "headline", is_vs4 & both_era & ~has_fico, both_era, BOTH_START)]
    for cover, basis, vmask, window, since in groups:
        prem = res_own if basis == "own_fico" else res
        cmask = check & window
        base = {"view": None, "cover": cover, "basis": basis, "dim": None, "key": None, "label": None, "order": 0,
                "since": since}

        def add(view, sel_v, sel_c, **extra):
            c = _cell(prem[vmask & sel_v], res[cmask & sel_c])
            if c:
                rows.append({**base, "view": view, **extra, **c})

        add("overall", True, True)
        for i, w in enumerate(sorted(set(week[vmask]))):
            add("week", week == w, week == w, dim="week", key=w, label=w, order=i)
        sellers = sorted(set(seller[vmask]), key=lambda s: -int((seller[vmask] == s).sum()))
        for i, s in enumerate(sellers):
            add("seller", seller == s, seller == s, dim="seller", key=s, label=names.get(s, s), order=i)
        for dim, (values, labels) in segments.items():
            for k, (label, order) in labels.items():
                add("segment", values == k, values == k, dim=dim, key=str(k), label=label, order=order)
        v, c = prem[vmask], res[cmask]
        if len(v) >= MIN_N:
            hv = np.bincount(np.searchsorted(HIST_EDGES, v, side="right"), minlength=len(HIST_EDGES) + 1) / len(v)
            hc = np.bincount(np.searchsorted(HIST_EDGES, c, side="right"), minlength=len(HIST_EDGES) + 1) / max(len(c), 1)
            for i in range(len(HIST_EDGES) + 1):
                lo = None if i == 0 else float(HIST_EDGES[i - 1])
                rows.append({**base, "view": "hist", "dim": "hist", "key": str(i), "order": i,
                             "label": f"{'below' if lo is None else lo}", "bin_lo": lo,
                             "bin_hi": None if i == len(HIST_EDGES) else float(HIST_EDGES[i]),
                             "share": round(float(hv[i]), 6), "check_share": round(float(hc[i]), 6),
                             "n": int(len(v)), "check_n": int(len(c))})
    # What a better fee tier is worth on FICO loans' rates, and how much of that shows in the rate at the borrower's own FICO.
    at_vs = dict(codes, grid=np.array([vocab["grid"].get(f"{s}|{l}|{p}", -1) for s, l, p in zip(vs_b, ltv_b, purpose)]))
    worth = ((_predict(mu, eff, own) - _predict(mu, eff, at_vs)) * 100)
    both = both_era & has_fico & (vs > 0)
    miss = float(res[check & both_era].mean()) if (check & both_era).sum() >= MIN_N else 0.0
    gap = vs_b - fico_b
    groups_v = {"same": is_vs4 & both & (gap == 0), "better": is_vs4 & both & (gap > 0), "1": is_vs4 & both & (gap == 1), "2": is_vs4 & both & (gap == 2),
                "3": is_vs4 & both & (gap >= 3), "fico_better": ~is_vs4 & both & (gap > 0)}
    order = {k: i for i, k in enumerate(groups_v)}
    v_any = is_vs4 & both
    scopes = ["All"] + sorted(set(seller[v_any]), key=lambda s: (-int((seller[v_any] == s).sum()), s))
    for rank, scope in enumerate(scopes):
        in_scope = np.ones(len(y), bool) if scope == "All" else seller == scope
        for key, mask in groups_v.items():
            m = mask & in_scope
            n = int(m.sum())
            if n < MIN_N:
                continue
            prem = res_own[m]
            net, w = float(prem.mean()) - miss, float(worth[m].mean())
            rows.append({"view": "value", "cover": "both", "basis": "own_fico", "dim": "value", "key": key, "order": order[key], "scope": scope,
                         "scope_rank": rank, "label": "All lenders" if scope == "All" else names.get(scope, scope), "since": BOTH_START, "n": n,
                         "net_bp": round(net, 2), "se_bp": round(float(prem.std(ddof=1) / np.sqrt(n)), 2), "worth_bp": round(w, 2),
                         "reaches": round(-net / w, 4) if w >= 1 else None})
    keys = sorted({k for r in rows for k in r})
    return [{k: r.get(k) for k in keys} for r in rows]
