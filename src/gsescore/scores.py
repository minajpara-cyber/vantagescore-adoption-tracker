"""Score choice: which scores loans carry, when lenders price on VS4, and how high its share could go.

The GSEs' upfront fees step at fixed credit score buckets (SCORE_CUTS in pricing.py: 639 or less,
640-659, ... 760-779, 780+). A loan's bucket gap is its VS4 bucket minus its Classic FICO bucket on the
single grid in force for MBS issued from Oct 1, 2026. Before that the FICO buckets applied to VS4 at 20
points higher, so a lender's rule shows up in score points (VS4 minus Classic FICO), not in buckets.

  rules      view curve: loans with both scores by point gap and the share priced on VS4, for all lenders and
             each seller with MIN_CHOICE+ such loans (cells of MIN_N+ loans), for loans first disclosed in the
             latest RECENT_WEEKS weeks and before them. All records that carry the Pricing Indicator, including
             loans for issue months after the current one, since the newest loans show a rule moving.
             view week: the same scopes by week first disclosed from WEEK_FROM and GSE (+ All): the share with
             both scores, the share priced on VS4, and the share priced on VS4 among loans with VS4 1-19 points
             above Classic FICO and 20 or more above it (MIN_N+ loans).
  score_mix  which scores loans carry, among records with every score delivered: Classic FICO only, both priced
             on FICO, both priced on VS4, VS4 only, with the share carrying each score and the share priced on VS4,
             count and balance. view month (headline marks the latest with HEADLINE_MIN+ loans), week, recent (the
             latest RECENT_WEEKS weeks) and all, each by GSE (+ All). view quarter: VS4's share priced by calendar
             quarter from the monthly view. view vs_only: the sellers with the most VS4-only loans, by GSE.

  choice   view rule: loans that carry both scores (only records from BOTH_START on can), by bucket gap (3+
           lower ... 3+ higher, the same bucket split into below 780 and both 780+): loans and the share
           priced on VS4. Scope All (agency All, FNMA, FHLMC) and each seller with MIN_CHOICE+ such loans (cells
           of MIN_N+ loans; scope_loans is the scope's total).
           view pull: each seller with MIN_N+ loans disclosed with every score delivered (records that
           carry the Pricing Indicator), and the share of them that carry both scores.
  ceiling  VS4's share if every lender priced on VS4 whenever it lands in a better bucket ("better") or
           whenever it is no worse ("not_worse"), next to the actual share. A loan with both scores counts
           as it is; a loan priced on VS4 with no Classic FICO counts as better; a loan with only a Classic
           FICO takes the rate measured on loans with both scores in its cell (Classic FICO bucket x purpose
           x channel x GSE, else bucket x GSE, else bucket, whichever first has MIN_CELL loans, else the rate
           over every loan with both scores).
           Records without the Pricing Indicator show only the score that priced the loan, so those rules would
           overstate a lender already choosing between scores: every VS4 loan would count as better, and its FICO
           loans would take a rate that ignores it had passed on VS4. A loan in such a record, at a seller with a
           VS4-priced loan that month, takes instead that seller's rate over records with every score delivered,
           in its GSE, else both GSEs (MIN_CELL+ loans), else the rate over VS4-priced such records if priced on
           VS4, else the rules above. A month made up mostly of such records is marked estimated.
           "higher" is the share if every lender priced on VS4 whenever its score is above the Classic FICO.
           view month: by issue month from MIX_START and GSE (+ All). view both: loans disclosed with every
           score delivered, by GSE (+ All). view band: those same loans by Classic FICO bucket, both GSEs, with
           each bucket's contribution to the ceiling, and key all: every such loan (the contributions add up to
           its value).
The loans with both scores are the ones whose lenders chose to order both, not a random sample: matching
on the cell corrects for loan mix, not for which lenders those are.
"""
from datetime import timedelta

from .pricing import BOTH_START, SCORE_CUTS, SCORE_LABELS

MIN_N = 20
MIN_CHOICE = 50
MIN_CELL = 30
RECENT_WEEKS = 2
WEEK_FROM = "2026-09-28"  # earlier weeks hold too few records with the Pricing Indicator to read
HEADLINE_MIN = 20000
POINT_BINS = [("lt0", "Below FICO", None, -1), ("0_4", "0-4", 0, 4), ("5_9", "5-9", 5, 9), ("10_14", "10-14", 10, 14),
              ("15_19", "15-19", 15, 19), ("20_24", "20-24", 20, 24), ("25_29", "25-29", 25, 29), ("30_39", "30-39", 30, 39),
              ("40up", "40+", 40, None)]
MIX_GROUPS = {"fico_only": "has_fico AND NOT has_vs4", "both_fico": "has_fico AND has_vs4 AND NOT is_v",
              "both_vs": "has_fico AND has_vs4 AND is_v", "vs_only": "has_vs4 AND NOT has_fico"}
GAPS = [("-3", "VS4 3+ buckets lower"), ("-2", "VS4 2 buckets lower"), ("-1", "VS4 1 bucket lower"),
        ("0", "Same bucket, below 780"), ("0top", "Both 780+"), ("1", "VS4 1 bucket higher"),
        ("2", "VS4 2 buckets higher"), ("3", "VS4 3+ buckets higher")]


def _bucket(col: str) -> str:
    return "CASE " + " ".join(f"WHEN {col} < {c} THEN {i}" for i, c in enumerate(SCORE_CUTS)) + f" ELSE {len(SCORE_CUTS)} END"


def build_datasets(con, in_range: str, mix_start: str, rows) -> dict[str, list[dict]]:
    """Needs seller_map, seller_key, entity_names (lenders.py) and the monthly view (aggregate.py)."""
    top = len(SCORE_CUTS)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE sc AS
        SELECT l.agency, l.issue_month AS month, coalesce(l.upb, 0) AS upb, l.score_model = 'V' AS is_v, m.id AS seller_id,
               CASE WHEN l.purpose = 'P' THEN 'P' WHEN l.purpose = 'C' THEN 'C' ELSE 'R' END AS purpose,
               coalesce(l.channel, '?') AS channel,
               coalesce(l.classic_fico BETWEEN 300 AND 850, false) AS has_fico,
               coalesce(l.vs4 BETWEEN 300 AND 850, false) AS has_vs4,
               CASE WHEN l.classic_fico BETWEEN 300 AND 850 THEN {_bucket('l.classic_fico')} END AS fb,
               CASE WHEN l.vs4 BETWEEN 300 AND 850 THEN {_bucket('l.vs4')} END AS vb,
               CASE WHEN l.classic_fico BETWEEN 300 AND 850 THEN l.classic_fico END AS fico,
               CASE WHEN l.vs4 BETWEEN 300 AND 850 THEN l.vs4 END AS vs,
               l.pricing_indicator IS NOT NULL AS win_both,  -- the record carries every score delivered
               l.issue_month >= DATE '{mix_start}' AS win_all
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.score_model IN ('V', 'C') AND ({in_range})""")
    gap_key = (f"CASE WHEN vb - fb <= -3 THEN '-3' WHEN vb - fb = -2 THEN '-2' WHEN vb - fb = -1 THEN '-1' "
               f"WHEN vb = fb AND fb = {top} THEN '0top' WHEN vb = fb THEN '0' WHEN vb - fb = 1 THEN '1' "
               f"WHEN vb - fb = 2 THEN '2' ELSE '3' END")
    labels = {k: (label, i) for i, (k, label) in enumerate(GAPS)}
    names = dict(con.execute("SELECT id, short FROM entity_names").fetchall())

    choice = []
    rule = con.execute(f"""
        WITH b AS (SELECT *, {gap_key} AS gkey FROM sc WHERE has_fico AND has_vs4),
        big AS (SELECT seller_id FROM b GROUP BY 1 HAVING count(*) >= {MIN_CHOICE})
        SELECT 'All' AS scope, COALESCE(agency, 'All') AS agency, gkey, count(*), count(*) FILTER (WHERE is_v)
        FROM b GROUP BY GROUPING SETS ((agency, gkey), (gkey))
        UNION ALL
        SELECT seller_id, 'All', gkey, count(*), count(*) FILTER (WHERE is_v)
        FROM b WHERE seller_id IN (SELECT seller_id FROM big) GROUP BY seller_id, gkey""").fetchall()
    totals: dict[tuple, int] = {}
    for scope, agency, _, loans, _ in rule:
        totals[scope, agency] = totals.get((scope, agency), 0) + loans
    for scope, agency, gkey, loans, vs4 in rule:
        if scope != "All" and loans < MIN_N:  # too few to read a seller's rate from
            continue
        label, order = labels[gkey]
        choice.append({"view": "rule", "scope": scope, "scope_label": "All lenders" if scope == "All" else names.get(scope, scope),
                       "agency": agency, "key": gkey, "label": label, "order": order, "loans": loans,
                       "scope_loans": totals[scope, agency], "vs4_loans": vs4, "vs4_share": round(vs4 / loans, 6), "both_share": None})
    for seller_id, loans, both in con.execute(f"""
            SELECT seller_id, count(*), count(*) FILTER (WHERE has_fico AND has_vs4) FROM sc WHERE win_both
            GROUP BY 1 HAVING count(*) >= {MIN_N} ORDER BY 2 DESC, 1""").fetchall():
        choice.append({"view": "pull", "scope": seller_id, "scope_label": names.get(seller_id, seller_id), "agency": "All",
                       "key": None, "label": None, "order": None, "loans": loans, "scope_loans": None, "vs4_loans": None,
                       "vs4_share": None, "both_share": round(both / loans, 6)})
    choice.sort(key=lambda r: (r["view"] != "rule", r["scope"] != "All", r["scope"], r["agency"], r["order"] or 0))

    # Each loan's chance VS4 is in a better (or no worse) bucket: observed where both scores are disclosed.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE scp AS
        WITH b AS (SELECT agency, fb, purpose, channel, (vb > fb)::INT AS better, (vb >= fb)::INT AS nw, (vs > fico)::INT AS hi
                   FROM sc WHERE has_fico AND has_vs4),
        c1 AS (SELECT agency, fb, purpose, channel, count(*) AS n, avg(better) AS pb, avg(nw) AS pn, avg(hi) AS ph FROM b GROUP BY ALL),
        c2 AS (SELECT agency, fb, count(*) AS n, avg(better) AS pb, avg(nw) AS pn, avg(hi) AS ph FROM b GROUP BY ALL),
        c3 AS (SELECT fb, count(*) AS n, avg(better) AS pb, avg(nw) AS pn, avg(hi) AS ph FROM b GROUP BY ALL),
        c4 AS (SELECT avg(better) AS pb, avg(nw) AS pn, avg(hi) AS ph FROM b),
        p AS (
        SELECT sc.*,
          CASE WHEN has_fico AND has_vs4 THEN (sc.vb > sc.fb)::DOUBLE
               WHEN is_v THEN 1.0
               WHEN has_fico THEN coalesce(CASE WHEN c1.n >= {MIN_CELL} THEN c1.pb END,
                                           CASE WHEN c2.n >= {MIN_CELL} THEN c2.pb END, c3.pb, c4.pb) END AS p_better,
          CASE WHEN has_fico AND has_vs4 THEN (sc.vb >= sc.fb)::DOUBLE
               WHEN is_v THEN 1.0
               WHEN has_fico THEN coalesce(CASE WHEN c1.n >= {MIN_CELL} THEN c1.pn END,
                                           CASE WHEN c2.n >= {MIN_CELL} THEN c2.pn END, c3.pn, c4.pn) END AS p_nw,
          CASE WHEN has_fico AND has_vs4 THEN (sc.vs > sc.fico)::DOUBLE
               WHEN is_v THEN 1.0
               WHEN has_fico THEN coalesce(CASE WHEN c1.n >= {MIN_CELL} THEN c1.ph END,
                                           CASE WHEN c2.n >= {MIN_CELL} THEN c2.ph END, c3.ph, c4.ph) END AS p_higher
        FROM sc
        LEFT JOIN c1 ON c1.agency = sc.agency AND c1.fb = sc.fb AND c1.purpose = sc.purpose AND c1.channel = sc.channel
        LEFT JOIN c2 ON c2.agency = sc.agency AND c2.fb = sc.fb
        LEFT JOIN c3 ON c3.fb = sc.fb
        CROSS JOIN c4),
        e AS (SELECT * FROM p WHERE win_both AND p_better IS NOT NULL),
        sa AS (SELECT seller_id, agency, count(*) AS n, avg(p_better) AS pb, avg(p_nw) AS pn, avg(p_higher) AS ph FROM e GROUP BY ALL),
        sr AS (SELECT seller_id, count(*) AS n, avg(p_better) AS pb, avg(p_nw) AS pn, avg(p_higher) AS ph FROM e GROUP BY ALL),
        vr AS (SELECT avg(p_better) AS pb, avg(p_nw) AS pn, avg(p_higher) AS ph FROM e WHERE is_v),
        um AS (SELECT DISTINCT seller_id, month FROM p WHERE is_v)
        SELECT p.* REPLACE (
          CASE WHEN win_both OR um.seller_id IS NULL OR p.p_better IS NULL THEN p.p_better
               ELSE coalesce(CASE WHEN sa.n >= {MIN_CELL} THEN sa.pb END, CASE WHEN sr.n >= {MIN_CELL} THEN sr.pb END,
                             CASE WHEN is_v THEN vr.pb END, p.p_better) END AS p_better,
          CASE WHEN win_both OR um.seller_id IS NULL OR p.p_better IS NULL THEN p.p_nw
               ELSE coalesce(CASE WHEN sa.n >= {MIN_CELL} THEN sa.pn END, CASE WHEN sr.n >= {MIN_CELL} THEN sr.pn END,
                             CASE WHEN is_v THEN vr.pn END, p.p_nw) END AS p_nw,
          CASE WHEN win_both OR um.seller_id IS NULL OR p.p_better IS NULL THEN p.p_higher
               ELSE coalesce(CASE WHEN sa.n >= {MIN_CELL} THEN sa.ph END, CASE WHEN sr.n >= {MIN_CELL} THEN sr.ph END,
                             CASE WHEN is_v THEN vr.ph END, p.p_higher) END AS p_higher)
        FROM p
        LEFT JOIN um ON um.seller_id = p.seller_id AND um.month = p.month
        LEFT JOIN sa ON sa.seller_id = p.seller_id AND sa.agency = p.agency
        LEFT JOIN sr ON sr.seller_id = p.seller_id
        CROSS JOIN vr""")
    measures = """count(*) AS loans, avg(is_v::INT) AS actual, avg(p_better) AS better, avg(p_higher) AS higher, avg(p_nw) AS not_worse,
               sum(upb * is_v::INT) / sum(upb) AS actual_upb, sum(upb * p_better) / sum(upb) AS better_upb,
               sum(upb * p_higher) / sum(upb) AS higher_upb, sum(upb * p_nw) / sum(upb) AS not_worse_upb, avg((has_fico AND has_vs4)::INT) AS observed_share,
               avg(win_both::INT) < 0.5 AS estimated"""
    band_labels = ", ".join(f"({i}, '{label}')" for i, label in enumerate(SCORE_LABELS))
    ceiling = rows(con, f"""
        WITH m AS (
          SELECT 'month' AS view, month AS start, COALESCE(agency, 'All') AS agency, {measures}
          FROM scp WHERE win_all AND p_better IS NOT NULL GROUP BY GROUPING SETS ((month, agency), (month))),
        w AS (
          SELECT 'both' AS view, DATE '{BOTH_START}' AS start, COALESCE(agency, 'All') AS agency, {measures}
          FROM scp WHERE win_both AND p_better IS NOT NULL GROUP BY GROUPING SETS ((agency), ())),
        labels(fb, label) AS (VALUES {band_labels}),
        bands AS (
          SELECT 'band' AS view, DATE '{BOTH_START}' AS start, 'All' AS agency,
                 coalesce(scp.fb::VARCHAR, 'vs4only') AS key, coalesce(labels.label, 'No Classic FICO (VS4 only)') AS label,
                 coalesce(scp.fb, -1) AS "order", count(*) AS loans,
                 count(*) / sum(count(*)) OVER () AS loan_share, avg(p_better) AS better, avg(p_higher) AS higher, avg(p_nw) AS not_worse,
                 sum(p_better) / sum(count(*)) OVER () AS adds_better, sum(p_higher) / sum(count(*)) OVER () AS adds_higher,
                 sum(p_nw) / sum(count(*)) OVER () AS adds_not_worse,
                 count(*) FILTER (WHERE has_fico AND has_vs4) AS measured
          FROM scp LEFT JOIN labels ON labels.fb = scp.fb
          WHERE win_both AND p_better IS NOT NULL GROUP BY scp.fb, labels.label),
        total AS (
          SELECT 'band' AS view, DATE '{BOTH_START}' AS start, 'All' AS agency, 'all' AS key, 'All loans' AS label,
                 99 AS "order", count(*) AS loans, 1.0 AS loan_share, avg(p_better) AS better, avg(p_higher) AS higher, avg(p_nw) AS not_worse,
                 avg(p_better) AS adds_better, avg(p_higher) AS adds_higher, avg(p_nw) AS adds_not_worse,
                 count(*) FILTER (WHERE has_fico AND has_vs4) AS measured
          FROM scp WHERE win_both AND p_better IS NOT NULL)
        SELECT m.*, NULL AS key, NULL AS label, NULL AS "order", NULL AS loan_share, NULL AS adds_better,
               NULL AS adds_higher, NULL AS adds_not_worse, NULL AS measured, t.final
        FROM m LEFT JOIN monthly t ON t.month = m.start AND t.agency = m.agency
        UNION ALL BY NAME
        SELECT *, NULL AS final FROM w
        UNION ALL BY NAME
        SELECT * FROM bands
        UNION ALL BY NAME
        SELECT * FROM total
        ORDER BY view, start, CASE agency WHEN 'All' THEN 0 WHEN 'FNMA' THEN 1 ELSE 2 END, "order" """)
    return {"choice": choice, "ceiling": ceiling, **_every_score(con, names, rows)}


def _every_score(con, names: dict, rows) -> dict[str, list[dict]]:
    """rules and score_mix, from every record that carries the Pricing Indicator, whatever its issue month."""
    con.execute("""
        CREATE OR REPLACE TEMP TABLE scw AS
        SELECT l.agency, l.issue_month AS month, date_trunc('week', l.first_intraday_date)::DATE AS week, coalesce(l.upb, 0) AS upb,
               l.score_model = 'V' AS is_v, m.id AS seller_id,
               coalesce(l.classic_fico BETWEEN 300 AND 850, false) AS has_fico, coalesce(l.vs4 BETWEEN 300 AND 850, false) AS has_vs4,
               l.vs4 - l.classic_fico AS gap
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.score_model IN ('V', 'C') AND l.pricing_indicator IS NOT NULL AND l.first_intraday_date IS NOT NULL""")
    last = con.execute("SELECT max(week) FROM scw").fetchone()[0]
    if last is None:
        return {"rules": [], "score_mix": []}
    latest_from = last - timedelta(days=7 * (RECENT_WEEKS - 1))
    bins = {k: (label, i) for i, (k, label, _, _) in enumerate(POINT_BINS)}
    case = "CASE " + " ".join(
        "WHEN " + " AND ".join(c for c in (f"gap >= {lo}" if lo is not None else "", f"gap <= {hi}" if hi is not None else "") if c) + f" THEN '{k}'"
        for k, _, lo, hi in POINT_BINS) + " END"
    big = f"(SELECT seller_id FROM scw WHERE has_fico AND has_vs4 GROUP BY 1 HAVING count(*) >= {MIN_CHOICE})"
    label = lambda scope: "All lenders" if scope == "All" else names.get(scope, scope)  # noqa: E731
    out = []
    for scope, latest, key, loans, vs4 in con.execute(f"""
            WITH b AS (SELECT *, {case} AS pkey, week >= DATE '{latest_from}' AS latest FROM scw WHERE has_fico AND has_vs4)
            SELECT 'All', latest, pkey, count(*), count(*) FILTER (WHERE is_v) FROM b GROUP BY 2, 3
            UNION ALL
            SELECT seller_id, latest, pkey, count(*), count(*) FILTER (WHERE is_v) FROM b WHERE seller_id IN {big} GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3""").fetchall():
        if scope == "All" or loans >= MIN_N:
            out.append({"view": "curve", "scope": scope, "scope_label": label(scope), "agency": "All", "cohort": "latest" if latest else "earlier",
                        "key": key, "label": bins[key][0], "order": bins[key][1], "loans": loans, "vs4_share": round(vs4 / loans, 6),
                        "latest_from": latest_from.isoformat()})
    for scope, agency, week, n, both, v, un, uv, on, ov in con.execute(f"""
            WITH base AS (SELECT 'All' AS scope, * FROM scw UNION ALL SELECT seller_id AS scope, * FROM scw WHERE seller_id IN {big})
            SELECT scope, COALESCE(agency, 'All') AS agency, week, count(*), count(*) FILTER (WHERE has_fico AND has_vs4), count(*) FILTER (WHERE is_v),
                   count(*) FILTER (WHERE gap BETWEEN 1 AND 19), count(*) FILTER (WHERE gap BETWEEN 1 AND 19 AND is_v),
                   count(*) FILTER (WHERE gap >= 20), count(*) FILTER (WHERE gap >= 20 AND is_v)
            FROM base WHERE week >= DATE '{WEEK_FROM}'
            GROUP BY GROUPING SETS ((scope, agency, week), (scope, week)) ORDER BY 1, 2, 3""").fetchall():
        if scope == "All" or n >= MIN_N:
            out.append({"view": "week", "scope": scope, "scope_label": label(scope), "agency": agency, "week": week.isoformat(), "loans": n,
                        "both_share": round(both / n, 6), "vs4_share": round(v / n, 6), "under20_loans": un,
                        "under20_share": round(uv / un, 6) if un >= MIN_N else None, "over20_loans": on,
                        "over20_share": round(ov / on, 6) if on >= MIN_N else None})
    keys = sorted({k for r in out for k in r})
    out = [{k: r.get(k) for k in keys} for r in out]

    measures = "count(*) AS loans, sum(upb) AS upb, " + ", ".join(
        f"count(*) FILTER (WHERE {c}) / count(*) AS {k}_share, coalesce(sum(upb) FILTER (WHERE {c}), 0) / nullif(sum(upb), 0) AS {k}_upb_share"
        for k, c in {**MIX_GROUPS, "fico": "has_fico", "vs": "has_vs4", "vs4_priced": "is_v"}.items())
    start = {"month": "month", "week": "week", "recent": f"DATE '{latest_from}'", "all": f"DATE '{BOTH_START}'"}
    where = {"month": "true", "week": f"week >= DATE '{WEEK_FROM}'", "recent": f"week >= DATE '{latest_from}'", "all": "true"}
    mix = rows(con, " UNION ALL BY NAME ".join(
        f"""SELECT '{view}' AS view, {st} AS start, COALESCE(agency, 'All') AS agency, {measures} FROM scw WHERE {where[view]}
            GROUP BY GROUPING SETS (({st}, agency), ({st}))""" for view, st in start.items()) + """
        ORDER BY view, start, CASE agency WHEN 'All' THEN 0 WHEN 'FNMA' THEN 1 ELSE 2 END""")
    current = con.execute("SELECT max(month) FROM monthly").fetchone()[0]
    months = [r for r in mix if r["view"] == "month" and r["agency"] == "All" and r["start"] <= current.isoformat()]
    enough = [r["start"] for r in months if r["loans"] >= HEADLINE_MIN] or [r["start"] for r in months]
    headline = max(enough) if enough else None
    for r in mix:
        r["headline"] = r["view"] == "month" and r["start"] == headline
        r["through"] = last.isoformat()
    quarter = rows(con, """
        SELECT 'quarter' AS view, date_trunc('quarter', month)::DATE AS start, agency, sum(scored_loans) AS loans, sum(scored_upb) AS upb,
               sum(vs4_loans) / sum(scored_loans) AS vs4_priced_share, sum(vs4_upb) / sum(scored_upb) AS vs4_priced_upb_share,
               bool_and(final) AS complete, count(*) AS months
        FROM monthly GROUP BY 1, 2, 3 ORDER BY 2, CASE agency WHEN 'All' THEN 0 WHEN 'FNMA' THEN 1 ELSE 2 END""")
    vs_only = rows(con, f"""
        WITH s AS (SELECT agency, seller_id, count(*) FILTER (WHERE {MIX_GROUPS['vs_only']}) AS vs_only_loans, count(*) AS loans FROM scw GROUP BY ALL)
        SELECT 'vs_only' AS view, agency, seller_id, vs_only_loans AS loans, vs_only_loans / sum(vs_only_loans) OVER (PARTITION BY agency) AS of_vs_only,
               vs_only_loans / loans AS vs_only_share FROM s WHERE vs_only_loans > 0
        QUALIFY row_number() OVER (PARTITION BY agency ORDER BY vs_only_loans DESC, seller_id) <= 5 ORDER BY 2, 4 DESC, 3""")
    for r in vs_only:
        r["scope_label"] = names.get(r["seller_id"], r["seller_id"])
    all_rows = mix + quarter + vs_only
    keys = sorted({k for r in all_rows for k in r})
    return {"rules": out, "score_mix": [{k: r.get(k) for k in keys} for r in all_rows]}
