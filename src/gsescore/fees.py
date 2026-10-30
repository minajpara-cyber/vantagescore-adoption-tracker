"""What the GSEs' upfront fee grid is worth to a lender that can pick a score.

The grid is reference/llpa.csv: Freddie Mac Guide Exhibit 19 (Bulletin 2026-K, settlement dates from Oct 1, 2026), base grids by
purpose, credit score bucket and LTV bucket, in percent of balance. It applies to Classic FICO and VS4 alike. Fannie Mae's LLPA
matrix is taken to match it. Loans in HFA, HomeReady / Home Possible and RefiNow / Refi Possible programs (FEE_WAIVED) are counted
as paying no base fee, since credit fee caps generally cover them; first-time buyers' income caps cannot be seen in these files.

From records that carry the Pricing Indicator with loan terms over 15 years, issued in the latest month with HEADLINE_MIN+ such loans.
For a loan with both scores: saved is the fee at its Classic FICO less the fee at its VS4 score. For a loan with only a Classic FICO:
what picking the better score would be worth on loans with both scores in its grid x score bucket x LTV bucket x GSE cell (or
coarser, MIN_CELL+ loans).

  fees  view lender (the LENDER_TOP sellers by potential fee saving and every seller with MIN_N+ VS4-priced loans with both scores):
        priced loans; how many save a fee, what they save on average in bp and dollars; dollars taken, on loans with both
        scores priced on FICO though VS4 was better, and estimated on loans with only a Classic FICO; the whole as bp of balance.
        view market: the same over all sellers, with the month's balance. Taken counts VS4-priced loans with both scores only,
        grossed up for VS4-priced loans that show one score in taken_all_usd. annual_upb is the GSE's balance a year at the pace of
        its final months, and taken_annual_usd and option_annual_usd scale the month's figures to it.
        view gse: the GSE's own score (Fannie Score, Freddie Score), VS4-priced minus FICO-priced, within the same seller, GSE and fee
        bucket, by bucket band, all lenders and each of the two largest VS4 sellers.
        view lift: the GSE's own score, VS4 in a better bucket minus VS4 in the same bucket, within the same GSE and FICO bucket.
Each lender's numbers rest on one month's loans. Grid fees are what the GSE charges, not what a borrower sees.
"""
from .fee_grid import FEE_WAIVED, load_grid
from .pricing import LTV_CUTS, SCORE_CUTS

HEADLINE_MIN = 20000
LENDER_TOP = 40
MIN_N = 20
MIN_CELL = 30
BANDS = [("a", "Below 700", 0, 3), ("b", "700-739", 4, 5), ("c", "740-779", 6, 7), ("d", "780 and over", 8, 8)]


def _bucket(col: str, cuts, closed_right=False) -> str:
    op = "<=" if closed_right else "<"
    return "CASE " + " ".join(f"WHEN {col} {op} {c} THEN {i}" for i, c in enumerate(cuts)) + f" ELSE {len(cuts)} END"


def build_datasets(con) -> dict[str, list[dict]]:
    """Needs seller_map and entity_names (lenders.py)."""
    con.execute("CREATE OR REPLACE TEMP TABLE llpa (grid VARCHAR, sb INT, lb INT, fee DOUBLE)")
    con.executemany("INSERT INTO llpa VALUES (?, ?, ?, ?)", [(g, s, l, v) for (g, s, l), v in load_grid().items()])
    waived = ", ".join(f"'{c}'" for c in FEE_WAIVED)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE fw AS
        SELECT l.agency, l.issue_month AS month, coalesce(l.upb, 0)::DOUBLE AS upb, l.score_model = 'V' AS is_v, m.id AS seller_id,
               l.classic_fico IS NOT NULL AS has_fico, l.vs4 IS NOT NULL AS has_vs4, coalesce(l.special_program, '7') IN ({waived}) AS waived,
               CASE WHEN l.purpose = 'P' THEN 'purchase' WHEN l.purpose = 'C' THEN 'cash_out' ELSE 'rate_term' END AS grid,
               {_bucket('l.classic_fico', SCORE_CUTS)} AS fb, {_bucket('l.vs4', SCORE_CUTS)} AS vb,
               {_bucket('l.ltv', LTV_CUTS, True)} AS lb, coalesce(l.fannie_score, l.freddie_score) AS gse
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.score_model IN ('V', 'C') AND l.pricing_indicator IS NOT NULL AND l.ltv IS NOT NULL AND coalesce(l.loan_term, 360) > 180
          AND l.issue_month <= date_trunc('month', current_date)""")
    months = con.execute("SELECT month, count(*) FROM fw GROUP BY 1 ORDER BY 1").fetchall()
    if not months:
        return {"fees": []}
    enough = [m for m, n in months if n >= HEADLINE_MIN] or [months[-1][0]]
    month = max(enough)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE fp AS
        WITH a AS (SELECT * FROM fw WHERE month = DATE '{month}'),
        f AS (SELECT a.*, CASE WHEN a.waived THEN 0 ELSE lf.fee END AS fee_f, CASE WHEN a.waived THEN 0 ELSE lv.fee END AS fee_v
              FROM a LEFT JOIN llpa lf ON lf.grid = a.grid AND lf.sb = a.fb AND lf.lb = least(a.lb, CASE a.grid WHEN 'cash_out' THEN 4 ELSE 8 END)
                     LEFT JOIN llpa lv ON lv.grid = a.grid AND lv.sb = a.vb AND lv.lb = least(a.lb, CASE a.grid WHEN 'cash_out' THEN 4 ELSE 8 END)),
        b AS (SELECT *, fee_f - fee_v AS saved FROM f),
        o AS (SELECT grid, fb, lb, agency, waived, greatest(saved, 0) AS opt FROM b WHERE has_fico AND has_vs4),
        c1 AS (SELECT grid, fb, lb, agency, waived, count(*) AS n, avg(opt) AS v FROM o GROUP BY ALL),
        c2 AS (SELECT grid, fb, waived, count(*) AS n, avg(opt) AS v FROM o GROUP BY ALL),
        c3 AS (SELECT fb, avg(opt) AS v FROM o GROUP BY ALL)
        SELECT b.*, CASE WHEN b.waived THEN 0 ELSE coalesce(CASE WHEN c1.n >= {MIN_CELL} THEN c1.v END, CASE WHEN c2.n >= {MIN_CELL} THEN c2.v END, c3.v, 0) END AS cell_opt
        FROM b LEFT JOIN c1 ON c1.grid = b.grid AND c1.fb = b.fb AND c1.lb = b.lb AND c1.agency = b.agency AND c1.waived = b.waived
               LEFT JOIN c2 ON c2.grid = b.grid AND c2.fb = b.fb AND c2.waived = b.waived
               LEFT JOIN c3 ON c3.fb = b.fb""")
    both, vb = "has_fico AND has_vs4", "has_fico AND has_vs4 AND is_v"
    measures = f"""count(*) AS n, sum(upb) AS u, count(*) FILTER (WHERE is_v) AS v_all, coalesce(sum(upb) FILTER (WHERE is_v), 0) AS vu_all,
        count(*) FILTER (WHERE {vb}) AS priced, coalesce(sum(upb) FILTER (WHERE {vb}), 0) AS priced_u,
        count(*) FILTER (WHERE {vb} AND saved > 0) AS saving_n, coalesce(sum(upb * saved / 100) FILTER (WHERE {vb} AND saved > 0), 0) AS saving_usd,
        coalesce(sum(upb * saved) FILTER (WHERE {vb}), 0) AS saved_pct_u, coalesce(sum(upb * saved / 100) FILTER (WHERE {vb}), 0) AS taken_usd,
        count(*) FILTER (WHERE {both} AND NOT is_v AND saved > 0) AS left_n, coalesce(sum(upb * saved / 100) FILTER (WHERE {both} AND NOT is_v AND saved > 0), 0) AS left_usd,
        count(*) FILTER (WHERE has_fico AND NOT has_vs4) AS one_n, coalesce(sum(upb * cell_opt / 100) FILTER (WHERE has_fico AND NOT has_vs4), 0) AS est_usd"""

    def row(view, r, **extra):
        n, u, v_all, vu_all, priced, priced_u, saving_n, saving_usd, saved_pct_u, taken, left_n, left, one_n, est = r
        taken_all = taken * (vu_all / priced_u) if priced_u else 0.0
        return {"view": view, "month": month.isoformat(), "loans": n, "upb": u, "vs4_loans": v_all, "priced_loans": priced,
                "saving_share": saving_n / priced if priced else None, "saved_bp": saved_pct_u / priced_u * 100 if priced_u else None,
                "saving_avg_usd": saving_usd / saving_n if saving_n else None,
                "taken_usd": taken, "taken_all_usd": taken_all, "left_loans": left_n, "left_usd": left, "one_loans": one_n, "est_usd": est,
                "option_usd": taken_all + left + est, "option_bp": (taken_all + left + est) / u * 1e4 if u else None, **extra}

    def market(r, agency):
        m = row("market", r, key=agency, agency=agency)
        annual = con.execute(f"SELECT sum(scored_upb) / nullif(count(*), 0) * 12 FROM monthly WHERE agency = '{agency}' AND final").fetchone()[0]
        m["annual_upb"] = float(annual) if annual else None
        if annual and m["upb"]:
            m["taken_annual_usd"] = m["taken_all_usd"] / m["upb"] * float(annual)
            m["option_annual_usd"] = m["option_usd"] / m["upb"] * float(annual)
        return m

    out = [market(con.execute(f"SELECT {measures} FROM fp").fetchone(), "All")]
    for agency in ("FNMA", "FHLMC"):
        r = con.execute(f"SELECT {measures} FROM fp WHERE agency = '{agency}'").fetchone()
        if r[0]:
            out.append(market(r, agency))
    names = {i: (s, t) for i, s, t in con.execute("SELECT id, short, ticker FROM entity_names").fetchall()}
    rows = con.execute(f"SELECT seller_id, {measures} FROM fp GROUP BY 1").fetchall()
    built = [row("lender", r[1:], id=r[0], short=names[r[0]][0], ticker=names[r[0]][1]) for r in rows]
    built.sort(key=lambda r: (-r["option_usd"], r["id"]))
    for i, r in enumerate(built):
        if i < LENDER_TOP or r["priced_loans"] >= MIN_N:
            out.append({**r, "rank": i + 1})

    top2 = [x[0] for x in con.execute("SELECT seller_id FROM fw WHERE is_v GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 2").fetchall()]
    band = "CASE " + " ".join(f"WHEN pb BETWEEN {lo} AND {hi} THEN '{k}'" for k, _, lo, hi in BANDS) + " END"
    labels = {k: label for k, label, _, _ in BANDS}
    for scope, cond, label in [("All", "true", "All lenders")] + [(s, f"seller_id = '{s}'", names[s][0]) for s in top2]:
        for key, cells, vn, diff in con.execute(f"""
                WITH x AS (SELECT seller_id, agency, is_v, CASE WHEN is_v THEN vb ELSE fb END AS pb, gse FROM fw
                           WHERE gse IS NOT NULL AND (is_v AND has_vs4 OR NOT is_v AND has_fico) AND ({cond})),
                c AS (SELECT seller_id, agency, pb, count(*) FILTER (WHERE is_v) AS vn, count(*) FILTER (WHERE NOT is_v) AS fn,
                             avg(gse) FILTER (WHERE is_v) AS vg, avg(gse) FILTER (WHERE NOT is_v) AS fg FROM x GROUP BY ALL)
                SELECT {band} AS k, count(*), sum(vn), sum((vg - fg) * vn) / sum(vn) FROM c WHERE vn >= 5 AND fn >= 5 GROUP BY 1 ORDER BY 1""").fetchall():
            if vn >= MIN_N:
                out.append({"view": "gse", "scope": scope, "scope_label": label, "key": key, "label": labels[key], "loans": vn, "diff": diff})
    for key, vn, diff in con.execute(f"""
            WITH x AS (SELECT agency, fb, vb > fb AS better, vb = fb AS same, gse FROM fw WHERE gse IS NOT NULL AND has_fico AND has_vs4),
            c AS (SELECT agency, fb AS pb, count(*) FILTER (WHERE better) AS bn, count(*) FILTER (WHERE same) AS sn,
                         avg(gse) FILTER (WHERE better) AS bg, avg(gse) FILTER (WHERE same) AS sg FROM x GROUP BY ALL)
            SELECT {band} AS k, sum(bn), sum((bg - sg) * bn) / sum(bn) FROM c WHERE bn >= 5 AND sn >= 5 GROUP BY 1 ORDER BY 1""").fetchall():
        if vn >= MIN_N:
            out.append({"view": "lift", "scope": "All", "key": key, "label": labels[key], "loans": vn, "diff": diff})
    keys = sorted({k for r in out for k in r})
    return {"fees": [{k: (round(r.get(k), 4) if isinstance(r.get(k), float) else r.get(k)) for k in keys} for r in out]}
