"""Loans by the month they closed, as near as the files allow, since issue month and first disclosure both lag by an amount that differs by lender.

The files give no closing date. A loan's first payment usually falls in the second month after it closes, so a loan's closing month here is its
first payment month less two. A month's loans keep arriving for months after it, the fastest deliverers first, so a recent month's market figure would
mostly be theirs: the market rows keep each lender at a fixed weight, and every row carries an estimate of how much of its loans have arrived.

  closing  view lender: the lenders on lender_stage, by GSE (+ All) and closing month from CLOSE_FROM: loans (n), priced on VS4 (v); among records that
           carry the Pricing Indicator (every): Classic FICO only (fo), both priced on FICO (bf), both priced on VS4 (bv), VS4 only (vo); arrived.
           view market: by GSE (+ All) and closing month: loans (n), VS4's share as delivered (delivered), and at fixed weights priced on VS4 (priced) and the
           split (fico_only, both_fico, both_vs, vs_only); every_share, the share of the month's loans in records that carry the Pricing Indicator; arrived; through.
           Weights: each lender's share of loans issued from CLOSE_FROM to the end of the last complete issue month. A lender's month under MIN_N loans keeps its
           rate from the last month it had that many (or that month's own rate before then); under MIN_N records with the Pricing Indicator, its rate over all months.
           arrived: the share of the month's loans issued by the end of the data, going by how the lender's closing months from REF_FROM, at least REF_AGE months
           old, spread over issue months (all lenders' where it has under REF_MIN such loans). The issue month in progress counts pro rata to the day.
"""
from calendar import monthrange
from collections import defaultdict
from datetime import date

CLOSE_FROM = "2026-03-01"
REF_FROM = "2026-01-01"
REF_AGE = 5
REF_MIN = 300
MIN_N = 20
SPLIT = ("fico_only", "both_fico", "both_vs", "vs_only")


def closing_month(col: str) -> str:
    """The month a loan closed, estimated from its first payment date."""
    return f"(date_trunc('month', {col}) - INTERVAL 2 MONTH)::DATE"


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def _month_back(d: date, n: int) -> date:
    i = d.year * 12 + d.month - 1 - n
    return date(i // 12, i % 12 + 1, 1)


def _curves(con, through: date) -> dict:
    """Each lender's, and all lenders' (key None), share of a closing month's loans by months from closing to issue."""
    counts, overall = defaultdict(dict), defaultdict(int)
    for sid, k, n in con.execute(f"""
            SELECT seller_id, greatest(date_diff('month', cm, issue_month), 0), count(*) FROM cl
            WHERE cm >= DATE '{REF_FROM}' AND cm <= DATE '{_month_back(through, REF_AGE)}' GROUP BY 1, 2""").fetchall():
        counts[sid][k] = n
        overall[k] += n
    out = {sid: {k: n / sum(c.values()) for k, n in c.items()} for sid, c in counts.items() if sum(c.values()) >= REF_MIN}
    if overall:
        out[None] = {k: n / sum(overall.values()) for k, n in overall.items()}
    return out


def _arrived(curve, month: date, through: date):
    if not curve:
        return None
    k = _months(month, through)
    if k < 0:
        return 0.0
    part = through.day / monthrange(through.year, through.month)[1]
    return min(1.0, sum(v for i, v in curve.items() if i < k) + part * curve.get(k, 0.0))


def _r(v):
    return None if v is None else round(v, 6)


def build_datasets(con, lender_stage: list[dict]) -> dict[str, list[dict]]:
    """Needs seller_map and seller_key (lenders.py) on this connection."""
    through = con.execute("SELECT max(first_intraday_date) FROM loans").fetchone()[0]
    if through is None:
        return {"closing": []}
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE cl AS
        SELECT l.agency, {closing_month('l.first_pay_date')} AS cm, l.issue_month, m.id AS seller_id, l.score_model = 'V' AS is_v,
               l.pricing_indicator IS NOT NULL AS every, coalesce(l.classic_fico BETWEEN 300 AND 850, false) AS has_fico, coalesce(l.vs4 BETWEEN 300 AND 850, false) AS has_vs4
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.score_model IN ('V', 'C') AND l.first_pay_date IS NOT NULL""")
    curves = _curves(con, through)
    curve = lambda sid: curves.get(sid) or curves.get(None)  # noqa: E731
    now = through.replace(day=1)
    cells = defaultdict(dict)
    for agency, sid, cm, n, v, e, fo, bf, bv, vo in con.execute(f"""
            SELECT coalesce(agency, 'All'), seller_id, cm, count(*), count(*) FILTER (WHERE is_v), count(*) FILTER (WHERE every),
                   count(*) FILTER (WHERE every AND has_fico AND NOT has_vs4), count(*) FILTER (WHERE every AND has_fico AND has_vs4 AND NOT is_v),
                   count(*) FILTER (WHERE every AND has_fico AND has_vs4 AND is_v), count(*) FILTER (WHERE every AND has_vs4 AND NOT has_fico)
            FROM cl WHERE cm >= DATE '{CLOSE_FROM}' AND cm <= DATE '{now}' GROUP BY seller_id, cm, ROLLUP(agency) ORDER BY 1, 2, 3""").fetchall():
        cells[agency].setdefault(sid, {})[cm] = {"n": n, "v": v, "e": e, "fo_": fo, "bf": bf, "bv": bv, "vo": vo}
    weights = defaultdict(dict)
    for agency, sid, n in con.execute(f"""
            SELECT coalesce(agency, 'All'), seller_id, count(*) FROM cl WHERE issue_month >= DATE '{CLOSE_FROM}' AND issue_month < DATE '{now}'
            GROUP BY seller_id, ROLLUP(agency)""").fetchall():
        weights[agency][sid] = n
    out = []
    listed = {r["id"] for r in lender_stage if r.get("view") == "lender"}
    for agency, lenders in cells.items():
        for sid in sorted(listed & set(lenders)):
            for cm, c in sorted(lenders[sid].items()):
                out.append({"view": "lender", "id": sid, "agency": agency, "start": cm.isoformat(), "n": c["n"], "v": c["v"], "every": c["e"], "fo": c["fo_"], "bf": c["bf"], "bv": c["bv"], "vo": c["vo"],
                            "arrived": _r(_arrived(curve(sid), cm, through))})
        months = sorted({cm for c in lenders.values() for cm in c})
        wt = weights[agency] or {sid: sum(c["n"] for c in cs.values()) for sid, cs in lenders.items()}
        total = sum(wt.values())
        priced, parts, arrive = defaultdict(float), defaultdict(lambda: dict.fromkeys(SPLIT, 0.0)), defaultdict(float)
        for sid, n_w in wt.items():
            w = n_w / total
            mine = lenders.get(sid, {})
            e_all = sum(c["e"] for c in mine.values())
            whole = {k: sum(c[f] for c in mine.values()) / e_all for k, f in zip(SPLIT, ("fo_", "bf", "bv", "vo"))} if e_all else dict(zip(SPLIT, (1.0, 0.0, 0.0, 0.0)))
            last = None
            for cm in months:
                c = mine.get(cm)
                if c and c["n"] >= MIN_N:
                    last = c["v"] / c["n"]
                rate = last if last is not None else c["v"] / c["n"] if c else 0.0
                priced[cm] += w * rate
                got = {k: c[f] / c["e"] for k, f in zip(SPLIT, ("fo_", "bf", "bv", "vo"))} if c and c["e"] >= MIN_N else whole
                for k in SPLIT:
                    parts[cm][k] += w * got[k]
                arrive[cm] += w * (_arrived(curve(sid), cm, through) or 0.0)
        for cm in months:
            all_cells = [cs[cm] for cs in lenders.values() if cm in cs]
            n = sum(c["n"] for c in all_cells)
            out.append({"view": "market", "agency": agency, "start": cm.isoformat(), "n": n, "delivered": _r(sum(c["v"] for c in all_cells) / n), "priced": _r(priced[cm]),
                        **{k: _r(parts[cm][k]) for k in SPLIT}, "every_share": _r(sum(c["e"] for c in all_cells) / n), "arrived": _r(arrive[cm]) if curves else None, "through": through.isoformat()})
    out.sort(key=lambda r: (r["view"], r["agency"], r.get("id") or "", r["start"]))
    keys = sorted({k for r in out for k in r})
    return {"closing": [{k: r.get(k) for k in keys} for r in out]}
