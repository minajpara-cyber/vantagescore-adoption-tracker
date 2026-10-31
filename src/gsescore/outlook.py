"""Outlook: where VS4's share could go from here, lender by lender, on the single fee grid in force from Oct 1, 2026.

Everything starts from the loans the ceiling uses (scores.py) that are disclosed with every score delivered (records
that carry the Pricing Indicator) and issued in the latest WINDOW_MONTHS issue months, both GSEs. For each seller
there: w, its share of those loans; d, its VS4 share; and the share of its loans where VS4 wins under each rule:
  better  VS4 lands in a better fee bucket, so it saves an upfront fee (scp.p_better)
  higher  the VS4 score is above the Classic FICO (scp.p_higher)
e is its VS4 share on loans first disclosed in the latest RECENT_WEEKS weeks, whatever their issue month, or d with
fewer than RECENT_MIN_N such loans: what the latest loans show, since lenders are still reacting to the new grid.

A seller "on a rule" orders both scores on every loan and prices on VS4 wherever the rule says, or keeps e if that is
higher. Heavy users are sellers with HEAVY_MIN_N+ such loans and a VS4 share of at least HEAVY_DEPTH of their better
share. Users are sellers with a VS4 loan disclosed since lender_start (LENDER_START in aggregate.py).

  outlook  view lender  the LENDER_TOP largest sellers and every other user with MIN_N+ loans, then one row for the
                        rest: w, d, e, each rule's share, the share on the rule and what that adds to the market's
                        share from e, its loans with both scores, how often it prices on VS4 when VS4 is better and
                        when it is higher (MIN_N+ such loans), and its status: heavy, using, stopped (VS4 loans
                        earlier but none since lender_start) or none
           view ladder  for each rule: VS4's share with the heavy users on it, then every user, then the NEXT_N
                        largest sellers not using VS4, then every seller; and, whatever the rule, today (d), the
                        latest weeks (e), and every loan where VS4 is no worse (not_worse)
           view ramp    each heavy user's VS4 share by months since its first VS4 month, as a share of e, and together
                        over the months with RAMP_MIN_LENDERS+ of them: r, the path a lender that moves is assumed to
                        follow from e to its share on the rule, never falling and reaching 1 after the last such month
           view pace    by issue month from lender_start, loans from sellers delivering their first VS4 loan as a
                        share of loans from sellers that had not delivered one before; key all pools the months
           view path    the actual share by issue month from PATH_START, then, for each rule, four cases for HORIZON
                        months: recent (every seller at e), heavy (the heavy users move to the rule from next month),
                        users (every user does) and pace (and each month the pooled pace of the other sellers' loans
                        starts moving too)
           view params  the window, the heavy users, the pace, and the users' share of loans
Every value has a balance version (_upb). These are scenarios, not a forecast: they rest on estimates for loans that
show one score, and on how a few lenders have behaved so far.
"""
from datetime import date, timedelta

PATH_START = "2026-05-01"  # the limited rollout, when VS4 deliveries begin
WINDOW_MONTHS = 2
LENDER_TOP = 40
MIN_N = 20
NEXT_N = 10
HEAVY_MIN_N = 100
HEAVY_DEPTH = 0.5
RAMP_MIN_LENDERS = 2
RECENT_WEEKS = 2
RECENT_MIN_N = 50
HORIZON = 12
RULES = ("higher", "better")
KEYS = ["view", "key", "rule", "case", "id", "short", "ticker", "label", "order", "month", "m", "rank", "status", "next",
        "value", "value_upb", "final", "lenders", "sellers", "loans", "share", "share_upb", "vs4_share", "vs4_upb_share",
        "recent_share", "recent_upb_share", "recent_loans", "better_share", "better_upb_share", "higher_share",
        "higher_upb_share", "on_better", "on_better_upb", "on_higher", "on_higher_upb", "adds_better", "adds_better_upb",
        "adds_higher", "adds_higher_upb", "both_share", "better_loans", "better_vs4", "higher_loans", "higher_vs4",
        "first_vs4", "q", "q_upb", "r", "r_upb", "new_sellers", "new_share", "new_share_upb", "pool_share", "pool_share_upb",
        "rate", "rate_upb", "window_from", "window_to", "recent_from", "recent_to", "end_month", "heavy_names", "heavy_count",
        "pace", "pace_upb", "horizon", "next_n", "users", "user_share", "user_share_upb"]


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
    """Needs scp and scw (scores.py); ls, adopt_sm, adopt_f and entity_names (lenders.py); the monthly view (aggregate.py)."""
    t0 = con.execute("SELECT max(month) FROM scp WHERE win_both AND p_better IS NOT NULL").fetchone()[0]
    last_week = con.execute("SELECT max(week) FROM scw").fetchone()[0]
    if t0 is None or last_week is None:
        return {"outlook": []}
    w0 = _month(t0, 1 - WINDOW_MONTHS)
    recent_from = last_week - timedelta(days=7 * (RECENT_WEEKS - 1))
    cur = con.execute(f"""
        WITH w AS (SELECT * FROM scp WHERE win_both AND p_better IS NOT NULL AND month >= DATE '{w0}'),
        fv AS (SELECT id, min(coalesce(first_date, month)) AS first_vs4,
                      bool_or(coalesce(first_date, month) >= DATE '{lender_start}') AS user
               FROM ls WHERE is_v GROUP BY id),
        rc AS (SELECT seller_id, count(*) AS n2, count(*) FILTER (WHERE is_v) AS v2, sum(upb)::DOUBLE AS u2,
                      coalesce(sum(upb) FILTER (WHERE is_v), 0)::DOUBLE AS vu2
               FROM scw WHERE week >= DATE '{recent_from}' GROUP BY 1)
        SELECT w.seller_id AS id, e.short, e.ticker, count(*) AS n, sum(w.upb)::DOUBLE AS u,
               count(*) FILTER (WHERE w.is_v) AS v, coalesce(sum(w.upb) FILTER (WHERE w.is_v), 0)::DOUBLE AS vu,
               sum(w.p_better) AS cb, sum(w.upb * w.p_better)::DOUBLE AS cbu,
               sum(w.p_higher) AS ch, sum(w.upb * w.p_higher)::DOUBLE AS chu,
               sum(w.p_nw) AS cn, sum(w.upb * w.p_nw)::DOUBLE AS cnu,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4) AS both_n,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4 AND w.vb > w.fb) AS better_n,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4 AND w.vb > w.fb AND w.is_v) AS better_v,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4 AND w.vs > w.fico) AS higher_n,
               count(*) FILTER (WHERE w.has_fico AND w.has_vs4 AND w.vs > w.fico AND w.is_v) AS higher_v,
               coalesce(fv.user, false) AS user, fv.first_vs4,
               coalesce(rc.n2, 0) AS n2, coalesce(rc.v2, 0) AS v2, coalesce(rc.u2, 0) AS u2, coalesce(rc.vu2, 0) AS vu2
        FROM w JOIN entity_names e ON e.id = w.seller_id LEFT JOIN fv ON fv.id = w.seller_id LEFT JOIN rc ON rc.seller_id = w.seller_id
        GROUP BY ALL ORDER BY n DESC, id""")
    cols = [c[0] for c in cur.description]
    sellers = [dict(zip(cols, r)) for r in cur.fetchall()]
    n_all, u_all = sum(s["n"] for s in sellers), sum(s["u"] for s in sellers)
    for s in sellers:
        s["w"], s["wu"] = s["n"] / n_all, _div(s["u"], u_all) or 0.0
        s["d"], s["du"] = s["v"] / s["n"], _div(s["vu"], s["u"]) or 0.0
        s["better"], s["better_u"] = s["cb"] / s["n"], _div(s["cbu"], s["u"]) or 0.0
        s["higher"], s["higher_u"] = s["ch"] / s["n"], _div(s["chu"], s["u"]) or 0.0
        s["nw"], s["nw_u"] = s["cn"] / s["n"], _div(s["cnu"], s["u"]) or 0.0
        enough = s["n2"] >= RECENT_MIN_N
        s["e"] = s["v2"] / s["n2"] if enough else s["d"]
        s["eu"] = (_div(s["vu2"], s["u2"]) or 0.0) if enough else s["du"]
        s["is_heavy"] = s["n"] >= HEAVY_MIN_N and s["better"] > 0 and s["d"] >= HEAVY_DEPTH * s["better"]
    heavy = [s for s in sellers if s["is_heavy"]]
    users = [s for s in sellers if s["user"]]
    nxt = {s["id"] for s in [s for s in sellers if not s["user"]][:NEXT_N]}

    # A seller's VS4 share: as it is today (how = 'today'), in the latest weeks ('recent') or on a rule.
    def level(s, how, upb):
        sfx = "_u" if upb else ""
        e = s["eu"] if upb else s["e"]
        if how == "today":
            return s["du"] if upb else s["d"]
        return e if how == "recent" else max(e, s[f"{how}{sfx}"])

    def market(rule, upb):
        return sum((s["wu"] if upb else s["w"]) * level(s, rule(s), upb) for s in sellers)

    out = [{"view": "ladder", "key": "today", "label": "Today", "order": 0, "value": market(lambda s: "today", False),
            "value_upb": market(lambda s: "today", True), "lenders": 0},
           {"view": "ladder", "key": "recent", "label": "Latest weeks", "order": 1, "value": market(lambda s: "recent", False),
            "value_upb": market(lambda s: "recent", True), "lenders": 0},
           {"view": "ladder", "key": "not_worse", "label": "Every loan where VS4 is no worse", "order": 9,
            "value": sum(s["w"] * max(s["e"], s["nw"]) for s in sellers), "value_upb": sum(s["wu"] * max(s["eu"], s["nw_u"]) for s in sellers),
            "lenders": len(sellers)}]
    for rule in RULES:
        groups = [("heavy", "The biggest users", lambda s: s["is_heavy"], len(heavy)),
                  ("users", "Every lender using VS4", lambda s: s["user"], len(users)),
                  ("next", f"And the {NEXT_N} largest not using it", lambda s: s["user"] or s["id"] in nxt, len(users) + len(nxt)),
                  ("all", "Every lender", lambda s: True, len(sellers))]
        for i, (key, label, moved, count) in enumerate(groups):
            pick = lambda s, m=moved: rule if m(s) else "recent"  # noqa: E731
            out.append({"view": "ladder", "key": key, "rule": rule, "label": label, "order": i + 2, "value": market(pick, False),
                        "value_upb": market(pick, True), "lenders": count})

    def group_row(group: list[dict], **extra) -> dict:
        n, u, v = sum(s["n"] for s in group), sum(s["u"] for s in group), sum(s["v"] for s in group)
        n2 = sum(s["n2"] for s in group)
        better_n, better_v = sum(s["better_n"] for s in group), sum(s["better_v"] for s in group)
        higher_n, higher_v = sum(s["higher_n"] for s in group), sum(s["higher_v"] for s in group)
        row = {"view": "lender", "loans": n, "share": n / n_all, "share_upb": _div(u, u_all),
               "vs4_share": v / n, "vs4_upb_share": _div(sum(s["vu"] for s in group), u), "recent_loans": n2,
               "recent_share": sum(s["w"] * s["e"] for s in group) / (n / n_all),
               "recent_upb_share": _div(sum(s["wu"] * s["eu"] for s in group), _div(u, u_all)),
               "better_share": sum(s["cb"] for s in group) / n, "better_upb_share": _div(sum(s["cbu"] for s in group), u),
               "higher_share": sum(s["ch"] for s in group) / n, "higher_upb_share": _div(sum(s["chu"] for s in group), u),
               "both_share": sum(s["both_n"] for s in group) / n, "better_loans": better_n,
               "better_vs4": better_v / better_n if better_n >= MIN_N else None, "higher_loans": higher_n,
               "higher_vs4": higher_v / higher_n if higher_n >= MIN_N else None}
        for rule in RULES:
            for upb, w in ((False, "w"), (True, "wu")):
                sfx = "_upb" if upb else ""
                weight = sum(s[w] for s in group)
                row[f"on_{rule}{sfx}"] = _div(sum(s[w] * level(s, rule, upb) for s in group), weight)
                row[f"adds_{rule}{sfx}"] = sum(s[w] * (level(s, rule, upb) - level(s, "recent", upb)) for s in group)
        return row | extra

    rest = []
    for i, s in enumerate(sellers):
        if i < LENDER_TOP or (s["user"] and s["n"] >= MIN_N):
            out.append(group_row([s], id=s["id"], short=s["short"], ticker=s["ticker"], rank=i + 1,
                                 status="heavy" if s["is_heavy"] else "using" if s["user"] else "stopped" if s["first_vs4"] else "none",
                                 next=s["id"] in nxt, first_vs4=s["first_vs4"], sellers=1))
        else:
            rest.append(s)
    if rest:
        out.append(group_row(rest, id="other", short="All other lenders", status="other", next=False, sellers=len(rest),
                             lenders=sum(s["user"] for s in rest)))

    # How the heavy users got to where they are, month by month from their first VS4 month.
    curve, curve_u = [], []
    if heavy:
        by_id = {s["id"]: s for s in heavy}
        pooled: dict[int, list] = {}
        for sid, m, n, v, u, vu in con.execute("""
                SELECT sm.id, date_diff('month', f.f_any, sm.month) AS m, sm.n, sm.v, sm.u::DOUBLE, sm.vu::DOUBLE
                FROM adopt_sm sm JOIN adopt_f f USING (id, agency)
                WHERE sm.agency = 'All' AND sm.month >= f.f_any AND list_contains(?::VARCHAR[], sm.id)
                ORDER BY m, sm.id""", [sorted(by_id)]).fetchall():
            s = by_id[sid]
            out.append({"view": "ramp", "id": sid, "short": s["short"], "m": m, "q": _div(v / n, s["e"]),
                        "q_upb": _div(_div(vu, u) or 0.0, s["eu"])})
            g = pooled.setdefault(m, [0, 0.0, 0.0, 0.0, 0])
            g[0] += v
            g[1] += n * s["e"]
            g[2] += vu
            g[3] += u * s["eu"]
            g[4] += 1
        for m in sorted(pooled):
            v, ne, vu, ue, k = pooled[m]
            if k < RAMP_MIN_LENDERS or m != len(curve):
                break
            curve.append(min(1.0, max(curve[-1] if curve else 0.0, _div(v, ne) or 0.0)))
            curve_u.append(min(1.0, max(curve_u[-1] if curve_u else 0.0, _div(vu, ue) or 0.0)))
            out.append({"view": "ramp", "m": m, "lenders": k, "q": _div(v, ne), "q_upb": _div(vu, ue), "r": curve[-1],
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

    # Paths: from next month a seller that moves goes from e toward its share on the rule along the curve.
    def ramp_at(m, cv):
        return 0.0 if m < 0 else cv[m] if m < len(cv) else 1.0

    for month, share, share_upb, final in con.execute(f"""
            SELECT month, vs4_share, vs4_upb_share, final FROM monthly
            WHERE agency = 'All' AND month >= DATE '{PATH_START}' ORDER BY month""").fetchall():
        out.append({"view": "path", "case": "actual", "month": month, "value": share, "value_upb": share_upb, "final": final})
    for k in range(HORIZON + 1):
        for rule in RULES:
            vals = {}
            for upb in (False, True):
                cv, hh, wk = (curve_u, hu, "wu") if upb else (curve, h, "w")
                if k == 0:
                    today = market(lambda s: "today", upb)
                    vals[upb] = (today, today, today, today)
                    continue
                start = lambda s: level(s, "recent", upb)  # noqa: E731
                gain = lambda s: level(s, rule, upb) - start(s)  # noqa: E731
                ramp = ramp_at(k - 1, cv)
                begun = sum(hh * (1 - hh) ** (j - 1) * ramp_at(k - j, cv) for j in range(1, k + 1))
                recent = sum(s[wk] * start(s) for s in sellers)
                moved_heavy = sum(s[wk] * gain(s) * ramp for s in heavy)
                moved_users = sum(s[wk] * gain(s) * ramp for s in users)
                joined = sum(s[wk] * gain(s) * begun for s in sellers if not s["user"])
                vals[upb] = (recent, recent + moved_heavy, recent + moved_users, recent + moved_users + joined)
            for i, case in enumerate(("recent", "heavy", "users", "pace")):
                out.append({"view": "path", "case": case, "rule": rule, "month": _month(t0, k), "value": vals[False][i],
                            "value_upb": vals[True][i]})

    out.append({"view": "params", "window_from": w0, "window_to": t0, "end_month": _month(t0, HORIZON), "loans": n_all,
                "recent_from": recent_from, "recent_to": last_week + timedelta(days=6),
                "heavy_names": _names([s["short"] for s in heavy]), "heavy_count": len(heavy),
                "pace": h, "pace_upb": hu, "horizon": HORIZON, "next_n": NEXT_N, "users": len(users),
                "user_share": sum(s["w"] for s in users), "user_share_upb": sum(s["wu"] for s in users)})
    return {"outlook": [_out(r) for r in out]}
