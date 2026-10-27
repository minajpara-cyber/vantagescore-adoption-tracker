"""Build the dashboard datasets (site/data/*.json) from the loans view.

Each file is {"rows": [{column: value, ...}, ...]}, the row-object shape the dashboard reads.
Shares are of loans with a valid score: loans with no score disclosed (score_model X, mostly
re-performing pools such as Fannie Mae prefix I4) are left out of every denominator.
Loan-level data never leaves the local warehouse; only these aggregates are published.

  monthly      VS4 / Classic FICO share by issue month and GSE (+ All); final once a month-end file exists
  weekly       the same by week of first intraday disclosure, from WEEKLY_START
  daily        the same by day of first disclosure (local only; too noisy to chart)
  lenders      sellers that delivered VS4 loans since LENDER_START, with their adoption rate
  composition  borrower mix of VS4 vs Classic FICO loans since MIX_START, one row per dim x bucket x model
  profile      averages for VS4 vs Classic FICO loans since MIX_START
  summary      headline figures per GSE (+ All)
  events       policy dates drawn on the charts
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .warehouse import connect

# VS4 fields went live Nov 17, 2025; the first month-end file on the portal is December 2025.
SERIES_START = "2025-11-01"
# The portal's intraday history starts Jul 1, 2026, and a loan is republished for up to ~3 weeks
# (90th percentile 20 days), so weeks before this would count June disclosures as new.
WEEKLY_START = "2026-07-20"
# Broad availability began Sep 8-10, 2026: lender table counts loans issued from September.
LENDER_START = "2026-09-01"
# Borrower-mix window: issue months with meaningful VS4 volume (>4% from July 2026).
MIX_START = "2026-07-01"

EVENTS = [
    ("2026-05-01", "Limited VS4 rollout"),
    ("2026-09-08", "VS4 open to all sellers"),
    ("2026-10-01", "Aligned pricing for VS4"),
    ("2026-10-19", "Pricing Indicator disclosed"),
]

# (dim, label, [(bucket, SQL condition)]) in display order; loans matching no condition are 'Not available'.
_SCORE = [("<660", "pricing_score < 660"), ("660-699", "pricing_score < 700"), ("700-739", "pricing_score < 740"),
          ("740-779", "pricing_score < 780"), ("780+", "pricing_score >= 780")]
DIMS = [
    ("pricing_score", "Credit score used for pricing", _SCORE),
    ("ltv", "Loan-to-value", [("60 or less", "ltv <= 60"), ("61-80", "ltv <= 80"), ("81-90", "ltv <= 90"),
                              ("91-95", "ltv <= 95"), ("Over 95", "ltv > 95")]),
    ("dti", "Debt-to-income", [("30 or less", "dti <= 30"), ("31-36", "dti <= 36"), ("37-43", "dti <= 43"),
                               ("44-50", "dti <= 50"), ("Over 50", "dti > 50")]),
    ("purpose", "Loan purpose", [("Purchase", "purpose = 'P'"), ("Cash-out refinance", "purpose = 'C'"),
                                 ("No cash-out refinance", "purpose IN ('N', 'R')")]),
    ("fthb", "First-time homebuyer", [("Yes", "fthb = 'Y'"), ("No", "fthb = 'N'")]),
    ("occupancy", "Occupancy", [("Primary residence", "occupancy = 'P'"), ("Second home", "occupancy = 'S'"),
                                ("Investor", "occupancy = 'I'")]),
    ("loan_size", "Loan size", [("Under $150k", "upb < 150000"), ("$150k-250k", "upb < 250000"),
                                ("$250k-400k", "upb < 400000"), ("$400k-600k", "upb < 600000"),
                                ("$600k+", "upb >= 600000")]),
    ("channel", "Origination channel", [("Retail", "channel = 'R'"), ("Broker", "channel = 'B'"),
                                        ("Correspondent", "channel = 'C'")]),
    ("num_borrowers", "Number of borrowers", [("One", "num_borrowers = 1"), ("Two or more", "num_borrowers >= 2")]),
]


def _round(v: float) -> float:
    # Parallel float sums differ in the last bits from run to run; rounding keeps unchanged data
    # byte-identical (balances to the cent, shares and averages to 6 decimals).
    return round(v, 2) if abs(v) >= 1000 else round(v, 6)


def _rows(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [{c: v.isoformat() if hasattr(v, "isoformat") else (_round(v) if isinstance(v, float) else v)
             for c, v in zip(cols, r)} for r in cur.fetchall()]


def _bucket_case(buckets) -> tuple[str, str]:
    label = "CASE " + " ".join(f"WHEN {cond} THEN '{b}'" for b, cond in buckets) + " ELSE 'Not available' END"
    order = "CASE " + " ".join(f"WHEN {cond} THEN {i}" for i, (_, cond) in enumerate(buckets)) + f" ELSE {len(buckets)} END"
    return label, order


# Counts every share needs, for a GROUP BY over `loans` rows.
_COUNTS = """
    count(*) AS loans,
    count(*) FILTER (WHERE score_model <> 'X') AS scored_loans,
    count(*) FILTER (WHERE score_model = 'V') AS vs4_loans,
    count(*) FILTER (WHERE score_model = 'C') AS fico_loans,
    count(*) FILTER (WHERE score_model = 'B') AS unresolved_loans,
    count(*) FILTER (WHERE score_model = 'X') AS no_score_loans,
    coalesce(sum(upb) FILTER (WHERE score_model <> 'X'), 0) AS scored_upb,
    coalesce(sum(upb) FILTER (WHERE score_model = 'V'), 0) AS vs4_upb,
    coalesce(sum(upb) FILTER (WHERE score_model = 'C'), 0) AS fico_upb"""
_SHARES = """
    vs4_loans / nullif(scored_loans, 0) AS vs4_share,
    fico_loans / nullif(scored_loans, 0) AS fico_share,
    vs4_upb / nullif(scored_upb, 0) AS vs4_upb_share,
    fico_upb / nullif(scored_upb, 0) AS fico_upb_share"""


def build(out_dir: Path = paths.SITE_DATA) -> dict:
    con = connect()
    out_dir.mkdir(parents=True, exist_ok=True)
    in_range = f"issue_month >= DATE '{SERIES_START}' AND issue_month <= date_trunc('month', current_date)"

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW monthly AS
        WITH g AS (
          SELECT issue_month AS month, COALESCE(agency, 'All') AS agency, {_COUNTS}
          FROM loans WHERE {in_range}
          GROUP BY GROUPING SETS ((issue_month, agency), (issue_month))
        ),
        fin AS (SELECT DISTINCT agency, file_date AS month FROM loan_records WHERE kind = 'monthend')
        SELECT g.*, {_SHARES},
          CASE WHEN g.agency = 'All' THEN (SELECT count(*) FROM fin WHERE fin.month = g.month) = 2
               ELSE EXISTS (SELECT 1 FROM fin WHERE fin.month = g.month AND fin.agency = g.agency) END AS final
        FROM g""")

    datasets = {
        "monthly": "SELECT * FROM monthly ORDER BY month, agency",
        "weekly": f"""
            WITH g AS (
              SELECT date_trunc('week', first_intraday_date)::DATE AS week, COALESCE(agency, 'All') AS agency,
                     max(first_intraday_date) AS last_day, {_COUNTS}
              FROM loans WHERE first_intraday_date >= DATE '{WEEKLY_START}'
              GROUP BY GROUPING SETS ((date_trunc('week', first_intraday_date), agency), (date_trunc('week', first_intraday_date)))
            )
            SELECT g.*, {_SHARES},
              CASE WHEN count(*) OVER w4 = 4 THEN sum(vs4_loans) OVER w4 / sum(scored_loans) OVER w4 END AS vs4_share_4wk,
              CASE WHEN count(*) OVER w4 = 4 THEN sum(vs4_upb) OVER w4 / sum(scored_upb) OVER w4 END AS vs4_upb_share_4wk,
              week + 7 <= current_date AS complete
            FROM g WINDOW w4 AS (PARTITION BY agency ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
            ORDER BY week, agency""",
        "daily": f"""
            SELECT first_intraday_date AS day, COALESCE(agency, 'All') AS agency, {_COUNTS}
            FROM loans WHERE first_intraday_date IS NOT NULL
            GROUP BY GROUPING SETS ((first_intraday_date, agency), (first_intraday_date)) ORDER BY 1, 2""",
        "lenders": f"""
            WITH s AS (
              SELECT seller, {_COUNTS},
                     count(*) FILTER (WHERE score_model = 'V' AND agency = 'FNMA') AS vs4_loans_fnma,
                     count(*) FILTER (WHERE score_model = 'V' AND agency = 'FHLMC') AS vs4_loans_fhlmc
              FROM loans WHERE issue_month >= DATE '{LENDER_START}' AND {in_range} AND seller IS NOT NULL
              GROUP BY seller
            )
            SELECT seller, loans, vs4_loans, vs4_loans_fnma, vs4_loans_fhlmc, DATE '{LENDER_START}' AS since,
                   vs4_loans / nullif(scored_loans, 0) AS vs4_share_of_seller,
                   vs4_loans / sum(vs4_loans) OVER () AS share_of_all_vs4
            FROM s WHERE vs4_loans > 0 ORDER BY vs4_loans DESC, seller""",
        "composition": "SELECT *, loans / sum(loans) OVER (PARTITION BY dim, model) AS share FROM ("
            + " UNION ALL ".join(
                f"""SELECT '{dim}' AS dim, '{label}' AS dim_label, {case} AS bucket, {order} AS bucket_order,
                           CASE score_model WHEN 'V' THEN 'VantageScore 4.0' ELSE 'Classic FICO' END AS model,
                           count(*) AS loans, DATE '{MIX_START}' AS since
                    FROM loans WHERE score_model IN ('V', 'C') AND issue_month >= DATE '{MIX_START}' AND {in_range}
                    GROUP BY ALL"""
                for dim, label, buckets in DIMS for case, order in [_bucket_case(buckets)])
            + ") ORDER BY dim, bucket_order, model",
        "profile": f"""
            SELECT CASE score_model WHEN 'V' THEN 'VantageScore 4.0' ELSE 'Classic FICO' END AS model,
                   count(*) AS loans, sum(upb) AS upb, DATE '{MIX_START}' AS since,
                   sum(pricing_score * upb) / sum(upb) FILTER (WHERE pricing_score IS NOT NULL) AS wa_score,
                   sum(ltv * upb) / sum(upb) FILTER (WHERE ltv IS NOT NULL) AS wa_ltv,
                   sum(dti * upb) / sum(upb) FILTER (WHERE dti IS NOT NULL) AS wa_dti,
                   sum(orig_rate * upb) / sum(upb) FILTER (WHERE orig_rate IS NOT NULL) AS wa_rate,
                   avg(upb) AS avg_loan,
                   avg(CASE WHEN purpose = 'P' THEN 1.0 ELSE 0 END) AS purchase_share,
                   avg(CASE WHEN purpose = 'C' THEN 1.0 ELSE 0 END) AS cashout_share,
                   avg(CASE WHEN fthb = 'Y' THEN 1.0 ELSE 0 END) AS fthb_share,
                   avg(CASE WHEN occupancy = 'I' THEN 1.0 ELSE 0 END) AS investor_share,
                   avg(CASE WHEN channel = 'B' THEN 1.0 ELSE 0 END) AS broker_share
            FROM loans WHERE score_model IN ('V', 'C') AND issue_month >= DATE '{MIX_START}' AND {in_range}
            GROUP BY ALL ORDER BY model DESC""",
        "summary": f"""
            WITH m AS (SELECT * FROM monthly),
            lf AS (SELECT agency, max(month) FILTER (WHERE final) AS final_month, max(month) AS last_month FROM m GROUP BY agency),
            sel AS (SELECT seller, count(*) FILTER (WHERE score_model = 'V') AS v FROM loans
                    WHERE issue_month >= DATE '{LENDER_START}' AND {in_range} AND seller IS NOT NULL GROUP BY seller),
            top2 AS (SELECT sum(v) AS v, string_agg(seller, ' and ' ORDER BY v DESC) AS names
                     FROM (SELECT * FROM sel ORDER BY v DESC LIMIT 2))
            SELECT lf.agency,
                   lf.final_month, f.vs4_share AS final_vs4_share, f.vs4_upb_share AS final_vs4_upb_share,
                   f.fico_share AS final_fico_share, f.fico_upb_share AS final_fico_upb_share,
                   f.scored_loans AS final_scored_loans,
                   p.month AS prior_month, p.vs4_share AS prior_vs4_share, p.vs4_upb_share AS prior_vs4_upb_share,
                   f.vs4_share - p.vs4_share AS vs4_share_change,
                   f.vs4_upb_share - p.vs4_upb_share AS vs4_upb_share_change,
                   l.month AS current_month, l.vs4_share AS current_vs4_share,
                   l.vs4_upb_share AS current_vs4_upb_share, l.scored_loans AS current_scored_loans,
                   (SELECT count(*) FROM sel) AS sellers, DATE '{LENDER_START}' AS sellers_since, (SELECT count(*) FILTER (WHERE v > 0) FROM sel) AS sellers_with_vs4,
                   (SELECT top2.v FROM top2) / (SELECT sum(v) FROM sel) AS top2_share_of_vs4,
                   (SELECT names FROM top2) AS top2_sellers,
                   (SELECT max(first_intraday_date) FROM loans) AS data_through
            FROM lf
            JOIN m f ON f.agency = lf.agency AND f.month = lf.final_month
            LEFT JOIN m p ON p.agency = lf.agency AND p.month = (lf.final_month - INTERVAL 1 MONTH)::DATE
            JOIN m l ON l.agency = lf.agency AND l.month = lf.last_month
            ORDER BY CASE lf.agency WHEN 'All' THEN 0 ELSE 1 END, lf.agency""",
    }
    written = {}
    for name, sql in datasets.items():
        rows = _rows(con, sql)
        (out_dir / f"{name}.json").write_text(json.dumps({"rows": rows}, separators=(",", ":")))
        written[name] = len(rows)
    (out_dir / "events.json").write_text(json.dumps({"rows": [{"date": d, "label": t} for d, t in EVENTS]}))
    written["events"] = len(EVENTS)

    coverage = _rows(con, """
        SELECT agency, kind, min(file_date) AS first_file, max(file_date) AS last_file,
               count(DISTINCT source_file) AS files, count(*) AS records
        FROM loan_records GROUP BY ALL ORDER BY ALL""")
    totals = con.execute(f"""
        SELECT count(*), sum(upb), min(issue_month), max(issue_month), min(first_intraday_date),
               max(first_intraday_date) FROM loans WHERE {in_range}""").fetchone()
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "series_start": SERIES_START,
        "coverage": coverage,
        "loans": totals[0], "upb": totals[1],
        "first_issue_month": iso(totals[2]), "last_issue_month": iso(totals[3]),
        "first_disclosed": iso(totals[4]), "last_disclosed": iso(totals[5]),
        "datasets": written,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta
