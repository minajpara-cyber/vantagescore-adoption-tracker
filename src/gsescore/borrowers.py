"""Which scores each loan carries, and the borrower mix of VS4 vs Classic FICO loans by score group.

Score groups (the dashboard's toggle), each comparing VS4-priced with Classic FICO-priced loans:
  all      every loan issued from MIX_START
  both     loans first disclosed from BOTH_START that carry both scores
  vs4only  VS4-priced loans first disclosed from BOTH_START with no Classic FICO, against every
           FICO-priced loan disclosed then

  score_coverage    loans by GSE (+ All), week of first disclosure from BOTH_START (week "all": every week)
                    and pricing model, with how many carry both scores and how many only the one priced on
  borrowers         each group's share of loans in each bucket of each dimension in DIMS. For VS4,
                    "expected" is the share if its loans matched its own sellers' FICO-priced loans in the
                    same window (a seller with under MIN_N FICO loans counts at the market's mix), so
                    actual minus expected is who the lenders put on VS4, net of which lenders use it.
                    A group with under MIN_N loans in a dimension is left out.
  borrower_profile  balance-weighted averages and shares per score group and model
"""
from .pricing import BOTH_START

MIN_N = 20
_LLPA = [("639 or less", "< 640"), ("640-659", "< 660"), ("660-679", "< 680"), ("680-699", "< 700"),
         ("700-719", "< 720"), ("720-739", "< 740"), ("740-759", "< 760"), ("760-779", "< 780"), ("780+", ">= 780")]


def _score(col: str, known: str) -> list[tuple[str, str]]:
    return [(label, f"{known} AND {col} {cond}") for label, cond in _LLPA]


# (dim, label, [(bucket, SQL condition)], groups shown per score group). A loan matching no condition is
# left out of that dimension (an unknown value, or a score the loan does not carry).
_BOTH = {"all": ("vs4", "fico"), "both": ("vs4", "fico"), "vs4only": ("vs4", "fico")}
DIMS = [
    ("pricing_score", "Credit score used for pricing", _score("pricing_score", "TRUE"), _BOTH),
    ("fico", "Classic FICO", _score("classic_fico", "has_fico"), {"all": ("fico",), "both": ("vs4", "fico"), "vs4only": ("fico",)}),
    ("vs4", "VantageScore 4.0", _score("vs4", "has_vs4"), {"all": ("vs4",), "both": ("vs4", "fico"), "vs4only": ("vs4",)}),
    ("gap", "VS4 minus Classic FICO (points)",
     [("Under -20", "gap < -20"), ("-20 to -1", "gap < 0"), ("0 to 19", "gap < 20"), ("20 to 39", "gap < 40"),
      ("40 to 59", "gap < 60"), ("60+", "gap >= 60")], {"both": ("vs4", "fico")}),
    ("ltv", "Loan-to-value", [("30 or less", "ltv <= 30"), ("30.01-60", "ltv <= 60"), ("60.01-70", "ltv <= 70"),
                              ("70.01-75", "ltv <= 75"), ("75.01-80", "ltv <= 80"), ("80.01-85", "ltv <= 85"),
                              ("85.01-90", "ltv <= 90"), ("90.01-95", "ltv <= 95"), ("Over 95", "ltv > 95")], _BOTH),
    ("dti", "Debt-to-income", [("20 or less", "dti <= 20"), ("20.01-30", "dti <= 30"), ("30.01-36", "dti <= 36"),
                               ("36.01-40", "dti <= 40"), ("40.01-45", "dti <= 45"), ("45.01-50", "dti <= 50"),
                               ("Over 50", "dti > 50")], _BOTH),
    ("purpose", "Loan purpose", [("Purchase", "purpose = 'P'"), ("Cash-out refinance", "purpose = 'C'"),
                                 ("No cash-out refinance", "purpose IN ('N', 'R')")], _BOTH),
    ("fthb", "First-time homebuyer", [("Yes", "fthb = 'Y'"), ("No", "fthb = 'N'")], _BOTH),
    ("occupancy", "Occupancy", [("Primary residence", "occupancy = 'P'"), ("Second home", "occupancy = 'S'"),
                                ("Investor", "occupancy = 'I'")], _BOTH),
    ("loan_size", "Loan size", [("Under $100k", "upb < 100000"), ("$100k-150k", "upb < 150000"),
                                ("$150k-200k", "upb < 200000"), ("$200k-300k", "upb < 300000"),
                                ("$300k-400k", "upb < 400000"), ("$400k-500k", "upb < 500000"),
                                ("$500k-650k", "upb < 650000"), ("$650k+", "upb >= 650000")], _BOTH),
    ("channel", "Origination channel", [("Retail", "channel = 'R'"), ("Broker", "channel = 'B'"),
                                        ("Correspondent", "channel = 'C'")], _BOTH),
    ("num_borrowers", "Number of borrowers", [("One", "num_borrowers = 1"), ("Two or more", "num_borrowers >= 2")], _BOTH),
    ("mi", "Mortgage insurance", [("With MI", "mi_pct > 0"), ("Without MI", "coalesce(mi_pct, 0) = 0")], _BOTH),
    ("term", "Loan term", [("30-year", "loan_term = 360"), ("20-year", "loan_term = 240"), ("15-year", "loan_term = 180"),
                           ("Other", "loan_term IS NOT NULL")], _BOTH),
    ("property", "Property type", [("Single-family", "property_type = 'SF'"), ("PUD", "property_type = 'PU'"),
                                   ("Condo", "property_type = 'CO'"), ("Manufactured", "property_type = 'MH'"),
                                   ("Co-op", "property_type = 'CP'")], _BOTH),
    ("units", "Units", [("1 unit", "units = 1"), ("2-4 units", "units >= 2")], _BOTH),
    ("rate", "Note rate, 30-year fixed", [(label, f"fixed30 AND orig_rate {cond}") for label, cond in [
        ("Under 5.5%", "< 5.5"), ("5.5-5.99%", "< 6"), ("6.0-6.24%", "< 6.25"), ("6.25-6.49%", "< 6.5"),
        ("6.5-6.74%", "< 6.75"), ("6.75-6.99%", "< 7"), ("7.0% and over", ">= 7")]], _BOTH),
    ("agency", "GSE", [("Fannie Mae", "agency = 'FNMA'"), ("Freddie Mac", "agency = 'FHLMC'")], _BOTH),
]
TOP_STATES = 15


def _case(buckets) -> tuple[str, str]:
    label = "CASE " + " ".join(f"WHEN {c} THEN '{b}'" for b, c in buckets) + " END"
    order = "CASE " + " ".join(f"WHEN {c} THEN {i}" for i, (_, c) in enumerate(buckets)) + " END"
    return label, order


def build_datasets(con, in_range: str, mix_start: str, rows) -> dict[str, list[dict]]:
    """Needs seller_map and seller_key from lenders.py on this connection."""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE bw AS
        SELECT l.agency, l.score_model, l.pricing_score, l.classic_fico, l.vs4, l.ltv, l.dti, l.purpose, l.fthb,
               l.occupancy, l.upb, l.channel, l.num_borrowers, l.mi_pct, l.loan_term, l.property_type, l.units,
               l.orig_rate, l.state, m.id AS seller_id, date_trunc('week', l.first_intraday_date)::DATE AS week,
               coalesce(l.classic_fico BETWEEN 300 AND 850, false) AS has_fico,
               coalesce(l.vs4 BETWEEN 300 AND 850, false) AS has_vs4,
               l.vs4 - l.classic_fico AS gap,
               coalesce(l.loan_term = 360 AND l.amort_type = 'FRM', false) AS fixed30,
               l.issue_month >= DATE '{mix_start}' AS win_all,
               coalesce(l.first_intraday_date >= DATE '{BOTH_START}', false) AS win_both
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.score_model IN ('V', 'C') AND ({in_range})""")
    # Each score group's two sides, and the FICO-priced loans its VS4 side is held up against.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE bg AS
        SELECT 'all' AS cover, CASE score_model WHEN 'V' THEN 'vs4' ELSE 'fico' END AS grp, * FROM bw WHERE win_all
        UNION ALL
        SELECT 'both', CASE score_model WHEN 'V' THEN 'vs4' ELSE 'fico' END, * FROM bw WHERE win_both AND has_fico AND has_vs4
        UNION ALL
        SELECT 'vs4only', CASE score_model WHEN 'V' THEN 'vs4' ELSE 'fico' END, * FROM bw
        WHERE win_both AND (score_model = 'C' OR NOT has_fico)""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE bref AS
        SELECT 'all' AS cover, * FROM bw WHERE score_model = 'C' AND win_all
        UNION ALL SELECT 'both', * FROM bw WHERE score_model = 'C' AND win_both
        UNION ALL SELECT 'vs4only', * FROM bw WHERE score_model = 'C' AND win_both""")
    states = [s for (s,) in con.execute(f"""
        SELECT state FROM bw WHERE win_all AND state IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT {TOP_STATES}""").fetchall()]
    dims = DIMS + [("state", "State", [(s, f"state = '{s}'") for s in states] + [("Other states", "state IS NOT NULL")], _BOTH)]

    out = []
    for dim, dim_label, buckets, shown in dims:
        label, order = _case(buckets)
        counts = con.execute(f"""
            SELECT cover, grp, {label} AS bucket, {order} AS bucket_order, count(*) AS loans
            FROM bg WHERE {label} IS NOT NULL GROUP BY ALL""").fetchall()
        expected = {}
        if dim not in ("fico", "vs4", "gap"):
            expected = {(c, b): e for c, b, e in con.execute(f"""
                WITH fs AS (SELECT cover, seller_id, {label} AS bucket, count(*) AS n FROM bref
                            WHERE {label} IS NOT NULL GROUP BY ALL),
                ft AS (SELECT cover, seller_id, sum(n) AS tot FROM fs GROUP BY ALL),
                fb AS (SELECT cover, bucket, sum(n) AS n FROM fs GROUP BY cover, bucket),
                fm AS (SELECT cover, bucket, n / sum(n) OVER (PARTITION BY cover) AS mshare FROM fb),
                v AS (SELECT cover, seller_id, count(*) AS vn FROM bg WHERE grp = 'vs4' AND {label} IS NOT NULL GROUP BY ALL),
                sb AS (SELECT v.cover, v.vn, fm.bucket,
                              CASE WHEN coalesce(ft.tot, 0) >= {MIN_N} THEN coalesce(fs.n, 0) / ft.tot ELSE fm.mshare END AS s
                       FROM v JOIN fm ON fm.cover = v.cover
                       LEFT JOIN ft ON ft.cover = v.cover AND ft.seller_id = v.seller_id
                       LEFT JOIN fs ON fs.cover = v.cover AND fs.seller_id = v.seller_id AND fs.bucket = fm.bucket)
                SELECT cover, bucket, sum(vn * s) / sum(vn) FROM sb GROUP BY ALL""").fetchall()}
        tally = {}
        for cover, grp, bucket, bucket_order, loans in counts:
            tally.setdefault((cover, grp), {})[(bucket_order, bucket)] = loans
        for cover, groups in shown.items():
            for grp in groups:
                cells = tally.get((cover, grp), {})
                total = sum(cells.values())
                if total < MIN_N:
                    continue
                for i, (b, _) in enumerate(buckets):
                    n = cells.get((i, b), 0)
                    e = expected.get((cover, b)) if grp == "vs4" else None
                    out.append({"dim": dim, "dim_label": dim_label, "cover": cover, "grp": grp, "bucket": b,
                                "bucket_order": i, "loans": n, "group_loans": total, "share": n / total,
                                "expected": e})
    keys = ["dim", "dim_label", "cover", "grp", "bucket", "bucket_order", "loans", "group_loans", "share", "expected"]
    borrowers = [{k: (round(r[k], 6) if isinstance(r[k], float) else r[k]) for k in keys} for r in out]

    profile = rows(con, f"""
        SELECT cover, grp, count(*) AS loans,
               sum(pricing_score * upb) / sum(upb) AS wa_score,
               sum(classic_fico * upb) FILTER (WHERE has_fico) / sum(upb) FILTER (WHERE has_fico) AS wa_fico,
               sum(vs4 * upb) FILTER (WHERE has_vs4) / sum(upb) FILTER (WHERE has_vs4) AS wa_vs4,
               avg(gap) FILTER (WHERE has_fico AND has_vs4) AS avg_gap,
               sum(ltv * upb) FILTER (WHERE ltv IS NOT NULL) / sum(upb) FILTER (WHERE ltv IS NOT NULL) AS wa_ltv,
               sum(dti * upb) FILTER (WHERE dti IS NOT NULL) / sum(upb) FILTER (WHERE dti IS NOT NULL) AS wa_dti,
               sum(orig_rate * upb) FILTER (WHERE fixed30) / sum(upb) FILTER (WHERE fixed30) AS wa_rate_30,
               avg(upb) AS avg_loan,
               avg((purpose = 'P')::INT) AS purchase_share, avg((purpose = 'C')::INT) AS cashout_share,
               avg((fthb = 'Y')::INT) AS fthb_share, avg((occupancy = 'I')::INT) AS investor_share,
               avg((channel = 'B')::INT) AS broker_share, avg((coalesce(mi_pct, 0) > 0)::INT) AS mi_share,
               avg(fixed30::INT) AS fixed30_share,
               CASE cover WHEN 'all' THEN DATE '{mix_start}' ELSE DATE '{BOTH_START}' END AS since
        FROM bg GROUP BY cover, grp HAVING count(*) >= {MIN_N}
        ORDER BY CASE cover WHEN 'all' THEN 0 WHEN 'both' THEN 1 ELSE 2 END, grp DESC""")
    coverage = rows(con, f"""
        SELECT COALESCE(agency, 'All') AS agency, coalesce(week::VARCHAR, 'all') AS week,
               CASE score_model WHEN 'V' THEN 'vs4' ELSE 'fico' END AS model,
               count(*) AS loans, count(*) FILTER (WHERE has_fico AND has_vs4) AS both_scores,
               count(*) FILTER (WHERE NOT (has_fico AND has_vs4)) AS one_score,
               count(*) FILTER (WHERE has_fico AND has_vs4) / count(*) AS both_share,
               count(*) FILTER (WHERE NOT (has_fico AND has_vs4)) / count(*) AS one_share,
               week + 7 <= current_date AS complete
        FROM bw WHERE win_both
        GROUP BY GROUPING SETS ((agency, week, score_model), (week, score_model), (agency, score_model), (score_model))
        ORDER BY week NULLS FIRST, CASE COALESCE(agency, 'All') WHEN 'All' THEN 0 WHEN 'FNMA' THEN 1 ELSE 2 END, model DESC""")
    return {"score_coverage": coverage, "borrowers": borrowers, "borrower_profile": profile}
