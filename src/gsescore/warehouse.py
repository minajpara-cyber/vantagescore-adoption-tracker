"""DuckDB views over the parquet warehouse.

  loan_records      every ingested loan row, typed, with out-of-range sentinels (9999, 7777, 999) as NULL
  loans             one row per (agency, loan_id): the at-issuance view used for analysis
  security_records  every ingested security row, typed
  securities        one row per (agency, security_id)

The key derived field is loans.score_model, the credit score model that priced the loan:
  C = Classic FICO, V = VantageScore 4.0, N = Fannie Score, R = Freddie Score (the portal's code list
  for the Pricing Indicator includes N and R, though only C and V are approved for pricing today),
  B = both scores disclosed and no Pricing Indicator (ambiguous; only before Oct 19, 2026),
  X = no valid score disclosed.
From Oct 19, 2026 the GSEs disclose a Pricing Indicator, which wins when present. Before that the
model is inferred from which score field is populated (lenders could not mix models on a loan).
"""
from pathlib import Path

import duckdb

from . import paths

LOAN_COLS = [
    "loan_id", "loan_correction", "prefix", "security_id", "cusip", "orig_loan_amt", "issuance_upb",
    "current_upb", "amort_type", "orig_rate", "issuance_rate", "issuance_net_rate", "first_pay_date",
    "maturity_date", "loan_term", "loan_age", "ltv", "cltv", "dti", "classic_fico", "vs4", "num_borrowers",
    "fthb", "purpose", "occupancy", "units", "property_type", "channel", "state", "seller", "servicer",
    "mi_pct", "io_flag", "valuation_method", "special_program", "pricing_indicator", "fannie_score",
    "freddie_score", "seller_city", "seller_state",
]
SECURITY_COLS = [
    "prefix", "security_id", "cusip", "factor_date", "issuer", "issue_date", "issuance_upb", "loan_count",
    "seller", "servicer", "wa_classic_fico", "wa_vs4", "description", "correction",
]
META_COLS = ["agency", "kind", "file_date", "file_seq", "source_file"]

# Rules the loans view applies to a loan's best record, shared with the as-of rebuild in aggregate.py,
# which applies them to every intraday record: the model that priced the loan, and an intraday
# record's issue month (r = the record, with first_intraday_date; s = its security).
SCORE_MODEL_SQL = """CASE
        WHEN pricing_indicator IS NOT NULL THEN pricing_indicator
        WHEN vs4 IS NOT NULL AND classic_fico IS NULL THEN 'V'
        WHEN classic_fico IS NOT NULL AND vs4 IS NULL THEN 'C'
        WHEN classic_fico IS NOT NULL AND vs4 IS NOT NULL THEN 'B'
        ELSE 'X'
      END"""
INTRADAY_ISSUE_MONTH_SQL = """COALESCE(date_trunc('month', s.issue_date)::DATE,
                      date_add(r.first_pay_date, to_months(r.loan_age - 1))::DATE,
                      date_trunc('month', r.first_intraday_date)::DATE)"""


def _glob(level: str) -> str:
    return str(paths.WAREHOUSE / level / "*" / "*" / "*.parquet")


def _present(con, level: str) -> set[str]:
    if not list((paths.WAREHOUSE / level).glob("*/*/*.parquet")):
        return set()
    rows = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{_glob(level)}', union_by_name=true)").fetchall()
    return {r[0] for r in rows}


def _source(con, level: str, cols: list[str]) -> str:
    present = _present(con, level)
    if not present:
        return "SELECT " + ", ".join(f"NULL::VARCHAR AS {c}" for c in META_COLS + cols) + " WHERE false"
    sel = [c if c in present else f"NULL::VARCHAR AS {c}" for c in META_COLS + cols]
    return f"SELECT {', '.join(sel)} FROM read_parquet('{_glob(level)}', union_by_name=true)"


def _num(col: str, lo: float, hi: float, typ: str = "DOUBLE") -> str:
    """Cast and null out anything outside the valid range (covers 9999 / 7777 / 999 sentinels)."""
    return f"CASE WHEN TRY_CAST({col} AS {typ}) BETWEEN {lo} AND {hi} THEN TRY_CAST({col} AS {typ}) END AS {col}"


def _mmyyyy(col: str) -> str:
    return f"TRY_CAST(TRY_STRPTIME('01' || {col}, '%d%m%Y') AS DATE) AS {col}"


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path) if db_path else ":memory:")
    create_views(con)
    return con


def create_views(con) -> None:
    loan_src = _source(con, "loan", LOAN_COLS)
    sec_src = _source(con, "security", SECURITY_COLS)
    con.execute(f"""
    CREATE OR REPLACE VIEW loan_records AS
    SELECT
      agency, kind, CAST(file_date AS DATE) AS file_date, CAST(file_seq AS INT) AS file_seq, source_file,
      trim(loan_id) AS loan_id, nullif(trim(loan_correction), '') AS loan_correction, trim(prefix) AS prefix,
      trim(security_id) AS security_id, trim(cusip) AS cusip,
      TRY_CAST(orig_loan_amt AS DOUBLE) AS orig_loan_amt,
      TRY_CAST(issuance_upb AS DOUBLE) AS issuance_upb,
      TRY_CAST(current_upb AS DOUBLE) AS current_upb,
      nullif(trim(amort_type), '') AS amort_type,
      TRY_CAST(orig_rate AS DOUBLE) AS orig_rate,
      TRY_CAST(issuance_rate AS DOUBLE) AS issuance_rate,
      TRY_CAST(issuance_net_rate AS DOUBLE) AS issuance_net_rate,
      {_mmyyyy('first_pay_date')}, {_mmyyyy('maturity_date')},
      TRY_CAST(loan_term AS INT) AS loan_term, TRY_CAST(loan_age AS INT) AS loan_age,
      {_num('ltv', 1, 998, 'INT')}, {_num('cltv', 1, 998, 'INT')}, {_num('dti', 1, 65, 'INT')},
      {_num('classic_fico', 300, 850, 'INT')}, {_num('vs4', 300, 850, 'INT')},
      TRY_CAST(classic_fico AS INT) AS classic_fico_code, TRY_CAST(vs4 AS INT) AS vs4_code,
      {_num('num_borrowers', 1, 98, 'INT')},
      nullif(trim(fthb), '') AS fthb, nullif(trim(purpose), '') AS purpose,
      nullif(trim(occupancy), '') AS occupancy, {_num('units', 1, 4, 'INT')},
      nullif(trim(property_type), '') AS property_type, nullif(trim(channel), '') AS channel,
      nullif(trim(state), '') AS state, nullif(trim(seller), '') AS seller, nullif(trim(servicer), '') AS servicer,
      {_num('mi_pct', 0, 55)},
      nullif(trim(io_flag), '') AS io_flag, nullif(trim(valuation_method), '') AS valuation_method,
      nullif(trim(special_program), '') AS special_program,
      CASE WHEN upper(trim(pricing_indicator)) IN ('C', 'V', 'N', 'R') THEN upper(trim(pricing_indicator)) END AS pricing_indicator,
      {_num('fannie_score', 400, 950, 'INT')}, {_num('freddie_score', 1, 999, 'INT')},
      nullif(trim(seller_city), '') AS seller_city, nullif(trim(seller_state), '') AS seller_state
    FROM ({loan_src})
    """)

    con.execute(f"""
    CREATE OR REPLACE VIEW security_records AS
    SELECT
      agency, kind, CAST(file_date AS DATE) AS file_date, CAST(file_seq AS INT) AS file_seq, source_file,
      trim(prefix) AS prefix, trim(security_id) AS security_id, trim(cusip) AS cusip,
      {_mmyyyy('factor_date')}, nullif(trim(issuer), '') AS issuer,
      TRY_CAST(TRY_STRPTIME(issue_date, '%m%d%Y') AS DATE) AS issue_date,
      TRY_CAST(issuance_upb AS DOUBLE) AS issuance_upb, TRY_CAST(loan_count AS INT) AS loan_count,
      nullif(trim(seller), '') AS seller, nullif(trim(servicer), '') AS servicer,
      {_num('wa_classic_fico', 300, 850)}, {_num('wa_vs4', 300, 850)},
      nullif(trim(description), '') AS description, nullif(trim(correction), '') AS correction
    FROM ({sec_src})
    """)

    con.execute("""
    CREATE OR REPLACE VIEW securities AS
    SELECT * EXCLUDE (rn) FROM (
      SELECT *, row_number() OVER (PARTITION BY agency, security_id
                                   ORDER BY file_date DESC, file_seq DESC) AS rn
      FROM security_records
    ) WHERE rn = 1
    """)

    # One row per loan. A loan can be republished in many intraday files and can move between pools
    # before issuance, so the key is (agency, loan_id). Base attributes come from the best record:
    # month-end issuance (the official list for its month), else the latest intraday record (an add
    # beats a delete within one file), else monthly. Score fields are coalesced across records because
    # the Pricing Indicator was back-filled for October 2026 pools issued before Oct 19.
    #
    # issue_month: the month-end file's month when the loan is in one, else the security's issue date,
    # else first payment date + (loan age - 1) months, which reproduces the month-end month for every
    # loan in the Dec 2025 - Sep 2026 files. Intraday-only loans whose issue month has a month-end file
    # are dropped: that file is the official list (they were pulled or re-pooled).
    con.execute(f"""
    CREATE OR REPLACE VIEW loans AS
    WITH ranked AS (
      SELECT *,
        min(file_date) FILTER (WHERE kind = 'intraday') OVER w AS first_intraday_date,
        max(pricing_indicator) OVER w AS any_pricing_indicator,
        max(fannie_score) OVER w AS any_fannie_score,
        max(freddie_score) OVER w AS any_freddie_score,
        row_number() OVER (PARTITION BY agency, loan_id
          ORDER BY CASE kind WHEN 'monthend' THEN 3 WHEN 'intraday' THEN 2 ELSE 1 END DESC,
                   file_date DESC, file_seq DESC, coalesce(loan_correction, '') = 'D') AS rn
      FROM loan_records
      WHERE loan_id IS NOT NULL AND loan_id <> ''
      WINDOW w AS (PARTITION BY agency, loan_id)
    ),
    monthend_months AS (SELECT DISTINCT agency, file_date AS month FROM loan_records WHERE kind = 'monthend'),
    base AS (
      SELECT r.* EXCLUDE (rn, pricing_indicator, fannie_score, freddie_score, any_pricing_indicator,
                          any_fannie_score, any_freddie_score),
             r.any_pricing_indicator AS pricing_indicator, r.any_fannie_score AS fannie_score,
             r.any_freddie_score AS freddie_score,
             s.issue_date AS security_issue_date,
             COALESCE(CASE WHEN r.kind = 'monthend' THEN r.file_date END,
                      {INTRADAY_ISSUE_MONTH_SQL}) AS issue_month
      FROM ranked r
      LEFT JOIN securities s USING (agency, security_id)
      WHERE r.rn = 1 AND NOT (r.kind = 'intraday' AND coalesce(r.loan_correction, '') = 'D')
    )
    SELECT *,
      {SCORE_MODEL_SQL} AS score_model,
      CASE WHEN pricing_indicator IS NOT NULL THEN 'pricing_indicator' ELSE 'inferred' END AS score_model_basis,
      CASE
        WHEN pricing_indicator = 'V' OR (pricing_indicator IS NULL AND vs4 IS NOT NULL AND classic_fico IS NULL) THEN vs4
        WHEN pricing_indicator = 'N' THEN fannie_score
        WHEN pricing_indicator = 'R' THEN freddie_score
        ELSE classic_fico
      END AS pricing_score,
      COALESCE(issuance_upb, orig_loan_amt) AS upb
    FROM base b
    WHERE b.kind = 'monthend' OR (b.agency, b.issue_month) NOT IN (SELECT (agency, month) FROM monthend_months)
    """)


def refresh_db() -> Path:
    """Write a persistent DuckDB file with the views, for ad-hoc querying (duckdb data/gse.duckdb)."""
    paths.DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(paths.DB))
    create_views(con)
    con.close()
    return paths.DB
