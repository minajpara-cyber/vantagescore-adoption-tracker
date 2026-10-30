"""Outlook: where VS4's share could go from here, lender by lender.

Everything starts from the loans the ceiling uses (scores.py) that are disclosed with every score delivered (records
that carry the Pricing Indicator) and issued in the latest WINDOW_MONTHS issue months, both GSEs. For each seller
there: w, its share of those loans; d, its VS4 share; c, its ceiling (the share of its loans that would be priced on
VS4 if it did so whenever VS4 lands in a better fee bucket, scp.p_better); and its depth, d / c.

Deep lenders are sellers with DEEP_MIN_N+ such loans and a depth of DEEP_DEPTH or more; q is their depth together
(their VS4 loans over the sum of their ceilings), or 1 while there is none. A seller "as deep as the deep lenders"
is at max(d, q x c). Users are sellers with a VS4 loan disclosed since lender_start (LENDER_START in aggregate.py).

  outlook  view lender  the LENDER_TOP largest sellers and every other user with MIN_N+ loans, then one row for the
                        rest: w, d, c, the share at the deep lenders' depth and what that would add to the market
                        share, what its ceiling would add, its loans with both scores, how often it prices on VS4
                        when VS4 is better (MIN_N+ such loans), and its status: deep, using, stopped (VS4 loans
                        earlier but none since lender_start) or none
           view ladder  VS4's share today; with every user as deep as the deep lenders; also the NEXT_N largest
                        sellers not using VS4; every seller; every seller at its ceiling
           view ramp    each deep lender's depth by months since its first VS4 month, and together over the months
                        with RAMP_MIN_LENDERS+ of them: r, the path a lender that goes deep is assumed to follow,
                        never falls and levels off at q
           view pace    by issue month from lender_start, loans from sellers delivering their first VS4 loan as a
                        share of loans from sellers that had not delivered one before; key all pools the months
           view path    the actual share by issue month from PATH_START, then three cases for HORIZON months: hold
                        (no seller changes), users (every user starts going deep next month) and pace (as users, and
                        each month the pooled pace of the other sellers' loans starts too, each going deep)
           view params  the window, q and the deep lenders, the pace, and the users' share of loans
Every value has a balance version (_upb). These are scenarios, not a forecast: they rest on the ceiling's estimate
and on how a few lenders have behaved so far.
"""
from datetime import date

PATH_START = "2026-05-01"  # the limited rollout, when VS4 deliveries begin
WINDOW_MONTHS = 2
LENDER_TOP = 40
MIN_N = 20
NEXT_N = 10
DEEP_MIN_N = 100
DEEP_DEPTH = 0.5
RAMP_MIN_LENDERS = 2
HORIZON = 12
KEYS = ["view", "key", "case", "id", "short", "ticker", "label", "order", "month", "m", "rank", "status", "next",
        "value", "value_upb", "final", "lenders", "sellers", "loans", "share", "share_upb", "vs4_share", "vs4_upb_share",
        "ceiling", "ceiling_upb", "depth", "deep", "deep_upb", "adds_deep", "adds_deep_upb", "adds_full",
        "adds_full_upb", "both_share", "better_loans", "better_vs4", "first_vs4", "q", "q_upb", "r", "r_upb",
        "new_sellers", "new_share", "new_share_upb", "pool_share", "pool_share_upb", "rate", "rate_upb", "window_from", "window_to", "end_month",
        "deep_names", "deep_count", "pace", "pace_upb", "horizon", "next_n", "users", "user_share", "user_share_upb"]


def _month(d: date, k: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + k, 12)
    return date(y, m + 1, 1)


def _div(a, b):
    return a / b if b else None


def _out(row: dict) -> dict:
    out = {}
    for k in KEYS:
        v = row.get(k)
        out[k] = v.isoformat() if isinstance(v, date) else round(v, 6) if isinstance(v, float) else v
    return out


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def build_datasets(con, lender_start: str) -> dict[str, list[dict]]:
    """Needs scp (scores.py); ls, adopt_sm, adopt_f and entity_names (lenders.py); the monthly view (aggregate.py)."""
    t0 = con.execute("SELECT max(month) FROM scp WHERE win_both AND p_better IS NOT NULL").fetchone()[0]
    if t0 is None:
        return {"outlook": []}
    w0 = _month(t0, 1 - WINDOW_MONTHS)
    cur = con.execute(f"""
        WITH w AS (SELECT * FROM scp WHERE win_both AND p_better IS NOT NULL AND month >= DATE '{w0}'),
        fv AS (SELECT id, min(coalesce(first_date, month)) AS first_vs4,
                      bool_or(coalesce(first_date, month) >= DATE '{lender_start}') AS user
               FROM ls WHERE is_v GROUP BY id)
        SELECT w.seller_id AS id, e.short, e.ticker, count(*) AS n, sum(w.upb)::DOUBLE AS u,
               count(*) FILTER (WHERE w.is_v) AS v, coalesce(sum(w.upb) FILTER (WHERE w.is_v), 0)::DOUBLE AS vu,
               sum(w.p_better) AS cb, sum(w.upb * w.p_better)::DOUBLE AS cbu,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4) AS both_n,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4 AND w.vb > w.fb) AS better_n,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4 AND w.vb > w.fb AND w.is_v) AS better_v,
               coalesce(fv.user, false) AS user, fv.first_vs4
        FROM w JOIN entity_names e ON e.id = w.seller_id LEFT JOIN fv ON fv.id = w.seller_id
        GROUP BY ALL ORDER BY n DESC, id""")
    cols = [c[0] for c in cur.description]
    sellers = [dict(zip(cols, r)) for r in cur.fetchall()]
    n_all, u_all = sum(s["n"] for s in sellers), sum(s["u"] for s in sellers)
    for s in sellers:
        s["w"], s["wu"] = s["n"] / n_all, _div(s["u"], u_all) or 0.0
        s["d"], s["du"] = s["v"] / s["n"], _div(s["vu"], s["u"]) or 0.0
        s["c"], s["cu"] = s["cb"] / s["n"], _div(s["cbu"], s["u"]) or 0.0
        s["is_deep"] = s["n"] >= DEEP_MIN_N and s["c"] > 0 and s["d"] >= DEEP_DEPTH * s["c"]
    deep = [s for s in sellers if s["is_deep"]]
    q = sum(s["v"] for s in deep) / sum(s["cb"] for s in deep) if deep else 1.0
    qu = (_div(sum(s["vu"] for s in deep), sum(s["cbu"] for s in deep)) or 1.0) if deep else 1.0
    users = [s for s in sellers if s["user"]]
    nxt = {s["id"] for s in [s for s in sellers if not s["user"]][:NEXT_N]}

    # A seller's VS4 share when it moves: how = None (as today), 'deep' (as deep as the deep lenders) or 'full'.
    def level(s, how, upb):
        d, c, qq = (s["du"], s["cu"], qu) if upb else (s["d"], s["c"], q)
        return d if how is None else max(d, qq * c) if how == "deep" else max(d, c)

    def market(rule, upb):
        return sum((s["wu"] if upb else s["w"]) * level(s, rule(s), upb) for s in sellers)

    out = []
    for i, (key, label, rule, moved) in enumerate([
            ("today", "Today", lambda s: None, 0),
            ("users", "Lenders using VS4 go as deep as the deep lenders", lambda s: "deep" if s["user"] else None, len(users)),
            ("next", f"And the {NEXT_N} largest lenders not using it", lambda s: "deep" if s["user"] or s["id"] in nxt else None,
             len(users) + len(nxt)),
            ("all_deep", "Every lender as deep as the deep lenders", lambda s: "deep", len(sellers)),
            ("all_full", "Every lender at its ceiling", lambda s: "full", len(sellers))]):
        out.append({"view": "ladder", "key": key, "label": label, "order": i, "value": market(rule, False),
                    "value_upb": market(rule, True), "lenders": moved})

    def group_row(group: list[dict], **extra) -> dict:
        n, u, v = sum(s["n"] for s in group), sum(s["u"] for s in group), sum(s["v"] for s in group)
        better_n, better_v = sum(s["better_n"] for s in group), sum(s["better_v"] for s in group)
        row = {"view": "lender", "loans": n, "share": n / n_all, "share_upb": _div(u, u_all),
               "vs4_share": v / n, "vs4_upb_share": _div(sum(s["vu"] for s in group), u),
               "ceiling": sum(s["cb"] for s in group) / n, "ceiling_upb": _div(sum(s["cbu"] for s in group), u),
               "both_share": sum(s["both_n"] for s in group) / n, "better_loans": better_n,
               "better_vs4": better_v / better_n if better_n >= MIN_N else None}
        for upb, w in ((False, "w"), (True, "wu")):
            sfx = "_upb" if upb else ""
            weight = sum(s[w] for s in group)
            row[f"deep{sfx}"] = _div(sum(s[w] * level(s, "deep", upb) for s in group), weight)
            row[f"adds_deep{sfx}"] = sum(s[w] * (level(s, "deep", upb) - level(s, None, upb)) for s in group)
            row[f"adds_full{sfx}"] = sum(s[w] * (level(s, "full", upb) - level(s, None, upb)) for s in group)
        row["depth"] = _div(row["vs4_share"], row["ceiling"])
        return row | extra

    rest = []
    for i, s in enumerate(sellers):
        if i < LENDER_TOP or (s["user"] and s["n"] >= MIN_N):
            out.append(group_row([s], id=s["id"], short=s["short"], ticker=s["ticker"], rank=i + 1,
                                 status="deep" if s["is_deep"] else "using" if s["user"] else "stopped" if s["first_vs4"] else "none",
                                 next=s["id"] in nxt, first_vs4=s["first_vs4"], sellers=1))
        else:
            rest.append(s)
    if rest:
        out.append(group_row(rest, id="other", short="All other sellers", status="other", next=False, sellers=len(rest),
                             lenders=sum(s["user"] for s in rest)))

    # How the deep lenders got there, month by month from their first VS4 month.
    curve, curve_u = [], []
    if deep:
        by_id = {s["id"]: s for s in deep}
        pooled: dict[int, list] = {}
        for sid, m, n, v, u, vu in con.execute(f"""
                SELECT sm.id, date_diff('month', f.f_any, sm.month) AS m, sm.n, sm.v, sm.u::DOUBLE, sm.vu::DOUBLE
                FROM adopt_sm sm JOIN adopt_f f USING (id, agency)
                WHERE sm.agency = 'All' AND sm.month >= f.f_any AND list_contains(?::VARCHAR[], sm.id)
                ORDER BY m, sm.id""", [sorted(by_id)]).fetchall():
            s = by_id[sid]
            out.append({"view": "ramp", "id": sid, "short": s["short"], "m": m, "q": v / n / s["c"],
                        "q_upb": _div(_div(vu, u), s["cu"])})
            g = pooled.setdefault(m, [0, 0.0, 0.0, 0.0, 0])
            g[0] += v
            g[1] += n * s["c"]
            g[2] += vu
            g[3] += u * s["cu"]
            g[4] += 1
        for m in sorted(pooled):
            v, nc, vu, uc, k = pooled[m]
            if k < RAMP_MIN_LENDERS or m != len(curve):
                break
            curve.append(min(q, max(curve[-1] if curve else 0.0, v / nc)))
            curve_u.append(min(qu, max(curve_u[-1] if curve_u else 0.0, _div(vu, uc) or 0.0)))
            out.append({"view": "ramp", "m": m, "lenders": k, "q": v / nc, "q_upb": _div(vu, uc), "r": curve[-1],
                        "r_upb": curve_u[-1]})

    # The pace at which sellers have started since VS4 opened to all of them.
    starts = con.execute(f"""
        SELECT sm.month, count(*) FILTER (WHERE f.f_any = sm.month) AS new_sellers,
               coalesce(sum(sm.n) FILTER (WHERE f.f_any = sm.month), 0) AS new_n,
               coalesce(sum(sm.u) FILTER (WHERE f.f_any = sm.month), 0)::DOUBLE AS new_u,
               coalesce(sum(sm.n) FILTER (WHERE f.f_any IS NULL OR f.f_any >= sm.month), 0) AS pool_n,
               coalesce(sum(sm.u) FILTER (WHERE f.f_any IS NULL OR f.f_any >= sm.month), 0)::DOUBLE AS pool_u,
               sum(sm.n) AS n, sum(sm.u)::DOUBLE AS u
        FROM adopt_sm sm JOIN adopt_f f USING (id, agency)
        WHERE sm.agency = 'All' AND sm.month >= DATE '{lender_start}' AND sm.month <= DATE '{t0}'
        GROUP BY sm.month ORDER BY sm.month""").fetchall()
    pooled_starts = [sum(r[i] for r in starts) for i in range(1, 8)]
    for month, *vals in starts + [("all", *pooled_starts)]:
        new_sellers, new_n, new_u, pool_n, pool_u, n, u = vals
        out.append({"view": "pace", "key": month, "month": None if month == "all" else month, "new_sellers": new_sellers,
                    "new_share": _div(new_n, n), "new_share_upb": _div(new_u, u), "pool_share": _div(pool_n, n),
                    "pool_share_upb": _div(pool_u, u), "rate": _div(new_n, pool_n), "rate_upb": _div(new_u, pool_u)})
    h = _div(pooled_starts[1], pooled_starts[3]) or 0.0
    hu = _div(pooled_starts[2], pooled_starts[4]) or 0.0

    # Paths: users start going deep next month along the curve; the pace case adds starts among the other sellers.
    def ramp_at(m, cv, qq):
        return 0.0 if m < 0 else cv[m] if m < len(cv) else qq

    for month, share, share_upb, final in con.execute(f"""
            SELECT month, vs4_share, vs4_upb_share, final FROM monthly
            WHERE agency = 'All' AND month >= DATE '{PATH_START}' ORDER BY month""").fetchall():
        out.append({"view": "path", "case": "actual", "month": month, "value": share, "value_upb": share_upb, "final": final})
    for k in range(HORIZON + 1):
        vals = {}
        for upb in (False, True):
            cv, qq, hh, wk = (curve_u, qu, hu, "wu") if upb else (curve, q, h, "w")
            d_of = lambda s: level(s, None, upb)  # noqa: E731
            c_of = lambda s: s["cu"] if upb else s["c"]  # noqa: E731
            started = sum(hh * (1 - hh) ** (j - 1) * ramp_at(k - j, cv, qq) for j in range(1, k + 1))
            hold = sum(s[wk] * d_of(s) for s in sellers)
            moved = sum(s[wk] * (max(d_of(s), c_of(s) * ramp_at(k - 1, cv, qq)) - d_of(s)) for s in users)
            joined = sum(s[wk] * (max(d_of(s), c_of(s) * started) - d_of(s)) for s in sellers if not s["user"])
            vals[upb] = (hold, hold + moved, hold + moved + joined)
        for i, case in enumerate(("hold", "users", "pace")):
            out.append({"view": "path", "case": case, "month": _month(t0, k), "value": vals[False][i],
                        "value_upb": vals[True][i]})

    out.append({"view": "params", "window_from": w0, "window_to": t0, "end_month": _month(t0, HORIZON), "loans": n_all,
                "q": q, "q_upb": qu, "deep_names": _names([s["short"] for s in deep]), "deep_count": len(deep),
                "pace": h, "pace_upb": hu, "horizon": HORIZON, "next_n": NEXT_N, "users": len(users),
                "user_share": sum(s["w"] for s in users), "user_share_upb": sum(s["wu"] for s in users)})
    return {"outlook": [_out(r) for r in out]}
