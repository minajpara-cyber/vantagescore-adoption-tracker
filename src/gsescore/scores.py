"""Score choice: when lenders price on VS4, and how high VS4's share could go.

The GSEs' upfront fees step at fixed credit score buckets (SCORE_CUTS in pricing.py: 639 or less,
640-659, ... 760-779, 780+). A loan's bucket gap is its VS4 bucket minus its Classic FICO bucket.

  choice   view rule: loans that carry both scores (only records from BOTH_START on can), by bucket gap (3+
           lower ... 3+ higher, the same bucket split into below 780 and both 780+): loans and the share
           priced on VS4. Scope All (agency All, FNMA, FHLMC) and each seller with MIN_CHOICE+ such loans.
           view pull: each seller with MIN_N+ loans disclosed with every score delivered (records that
           carry the Pricing Indicator), and the share of them that carry both scores.
  ceiling  VS4's share if every lender priced on VS4 whenever it lands in a better bucket ("better") or
           whenever it is no worse ("not_worse"), next to the actual share. A loan with both scores counts
           as it is; a loan priced on VS4 with no Classic FICO counts as better; a loan with only a Classic
           FICO takes the rate measured on loans with both scores in its cell (Classic FICO bucket x purpose
           x channel x GSE, else bucket x GSE, else bucket, whichever first has MIN_CELL loans, else the rate
           over every loan with both scores).
           view month: by issue month from MIX_START and GSE (+ All). view both: loans disclosed with every
           score delivered, by GSE (+ All). view band: by Classic FICO bucket, both GSEs, issue months from
           MIX_START, with each bucket's contribution to the ceiling, and key all: every loan (the
           contributions add up to its value).
The loans with both scores are the ones whose lenders chose to order both, not a random sample: matching
on the cell corrects for loan mix, not for which lenders those are.
"""
from .pricing import BOTH_START, SCORE_CUTS, SCORE_LABELS

MIN_N = 20
MIN_CHOICE = 50
MIN_CELL = 30
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
    for scope, agency, gkey, loans, vs4 in rule:
        label, order = labels[gkey]
        choice.append({"view": "rule", "scope": scope, "scope_label": "All lenders" if scope == "All" else names.get(scope, scope),
                       "agency": agency, "key": gkey, "label": label, "order": order, "loans": loans,
                       "vs4_loans": vs4, "vs4_share": round(vs4 / loans, 6), "both_share": None})
    for seller_id, loans, both in con.execute(f"""
            SELECT seller_id, count(*), count(*) FILTER (WHERE has_fico AND has_vs4) FROM sc WHERE win_both
            GROUP BY 1 HAVING count(*) >= {MIN_N} ORDER BY 2 DESC, 1""").fetchall():
        choice.append({"view": "pull", "scope": seller_id, "scope_label": names.get(seller_id, seller_id), "agency": "All",
                       "key": None, "label": None, "order": None, "loans": loans, "vs4_loans": None, "vs4_share": None,
                       "both_share": round(both / loans, 6)})
    choice.sort(key=lambda r: (r["view"] != "rule", r["scope"] != "All", r["scope"], r["agency"], r["order"] or 0))

    # Each loan's chance VS4 is in a better (or no worse) bucket: observed where both scores are disclosed.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE scp AS
        WITH b AS (SELECT agency, fb, purpose, channel, (vb > fb)::INT AS better, (vb >= fb)::INT AS nw
                   FROM sc WHERE has_fico AND has_vs4),
        c1 AS (SELECT agency, fb, purpose, channel, count(*) AS n, avg(better) AS pb, avg(nw) AS pn FROM b GROUP BY ALL),
        c2 AS (SELECT agency, fb, count(*) AS n, avg(better) AS pb, avg(nw) AS pn FROM b GROUP BY ALL),
        c3 AS (SELECT fb, count(*) AS n, avg(better) AS pb, avg(nw) AS pn FROM b GROUP BY ALL),
        c4 AS (SELECT avg(better) AS pb, avg(nw) AS pn FROM b)
        SELECT sc.*,
          CASE WHEN has_fico AND has_vs4 THEN (sc.vb > sc.fb)::DOUBLE
               WHEN is_v THEN 1.0
               WHEN has_fico THEN coalesce(CASE WHEN c1.n >= {MIN_CELL} THEN c1.pb END,
                                           CASE WHEN c2.n >= {MIN_CELL} THEN c2.pb END, c3.pb, c4.pb) END AS p_better,
          CASE WHEN has_fico AND has_vs4 THEN (sc.vb >= sc.fb)::DOUBLE
               WHEN is_v THEN 1.0
               WHEN has_fico THEN coalesce(CASE WHEN c1.n >= {MIN_CELL} THEN c1.pn END,
                                           CASE WHEN c2.n >= {MIN_CELL} THEN c2.pn END, c3.pn, c4.pn) END AS p_nw
        FROM sc
        LEFT JOIN c1 ON c1.agency = sc.agency AND c1.fb = sc.fb AND c1.purpose = sc.purpose AND c1.channel = sc.channel
        LEFT JOIN c2 ON c2.agency = sc.agency AND c2.fb = sc.fb
        LEFT JOIN c3 ON c3.fb = sc.fb
        CROSS JOIN c4""")
    measures = """count(*) AS loans, avg(is_v::INT) AS actual, avg(p_better) AS better, avg(p_nw) AS not_worse,
               sum(upb * is_v::INT) / sum(upb) AS actual_upb, sum(upb * p_better) / sum(upb) AS better_upb,
               sum(upb * p_nw) / sum(upb) AS not_worse_upb, avg((has_fico AND has_vs4)::INT) AS observed_share"""
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
          SELECT 'band' AS view, DATE '{mix_start}' AS start, 'All' AS agency,
                 coalesce(scp.fb::VARCHAR, 'vs4only') AS key, coalesce(labels.label, 'No Classic FICO (VS4 only)') AS label,
                 coalesce(scp.fb, -1) AS "order", count(*) AS loans,
                 count(*) / sum(count(*)) OVER () AS loan_share, avg(p_better) AS better, avg(p_nw) AS not_worse,
                 sum(p_better) / sum(count(*)) OVER () AS adds_better, sum(p_nw) / sum(count(*)) OVER () AS adds_not_worse,
                 count(*) FILTER (WHERE has_fico AND has_vs4) AS measured
          FROM scp LEFT JOIN labels ON labels.fb = scp.fb
          WHERE win_all AND p_better IS NOT NULL GROUP BY scp.fb, labels.label),
        total AS (
          SELECT 'band' AS view, DATE '{mix_start}' AS start, 'All' AS agency, 'all' AS key, 'All loans' AS label,
                 99 AS "order", count(*) AS loans, 1.0 AS loan_share, avg(p_better) AS better, avg(p_nw) AS not_worse,
                 avg(p_better) AS adds_better, avg(p_nw) AS adds_not_worse,
                 count(*) FILTER (WHERE has_fico AND has_vs4) AS measured
          FROM scp WHERE win_all AND p_better IS NOT NULL)
        SELECT m.*, NULL AS key, NULL AS label, NULL AS "order", NULL AS loan_share, NULL AS adds_better,
               NULL AS adds_not_worse, NULL AS measured, t.final
        FROM m LEFT JOIN monthly t ON t.month = m.start AND t.agency = m.agency
        UNION ALL BY NAME
        SELECT *, NULL AS final FROM w
        UNION ALL BY NAME
        SELECT * FROM bands
        UNION ALL BY NAME
        SELECT * FROM total
        ORDER BY view, start, CASE agency WHEN 'All' THEN 0 WHEN 'FNMA' THEN 1 ELSE 2 END, "order" """)
    return {"choice": choice, "ceiling": ceiling}
