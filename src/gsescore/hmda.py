"""Which credit score lenders say they relied on across the whole mortgage market, from the federal HMDA record.

Fannie Mae and Freddie Mac are only part of the market. HMDA covers nearly every lender's applications whatever becomes of the loan, and names the score
model relied on for the credit decision. It is annual: the public file for a year arrives about the following June.

A loan's score fields cover its applicant and co-applicant, and a lender can name the model in either. A named model is a fact. "More than one model" and "other model" name nothing
further, and "not applicable" or "exempt" says nothing at all, so none of those count as FICO or VantageScore: what is named is a floor.

  whole_market  view meta: the year, the file's date, its records, loans made and lenders.
                view segment: loans made by segment (+ first-lien and all), with loans, usd_bn and shares by what the lender named: classic, fico_new (FICO 8, 9, 10, 10T), vs4,
                vs_old (VantageScore 2.0, 3.0), multi (more than one model), other, none (not applicable or exempt), and the sums fico, vs, unnamed (multi + other) and unknown (unnamed + none).
                view lender: the same for the LENDER_TOP biggest lenders in each scope: all, first (first-lien), equity (home equity), vs (by VantageScore loans) and fico_new (by newer FICO loans),
                each lender with at least LENDER_MIN loans in the scope.
                view model: each named model's loans, the share of them in home equity and its MODEL_TOP biggest users.
                view apps: applications per loan made, by kind of loan, where the unfunded ones can be sorted.
                view trend: the segment rows for every year loaded. view lender_year: the same lenders as view lender, each year they made at least LENDER_YEAR_MIN loans in the scope, going by legal entity.
                view model_year: each named model's loans and share of that year's loans, which shows when the filing form began to list it.
                Every view but the last three is the latest year.
"""
import csv
import io
import re
import shutil
import zipfile
from pathlib import Path

import duckdb

from . import paths

YEAR_FILES = {2025: "2026-06-02"}  # the date of each year's public file
LENDER_TOP = 25
LENDER_MIN = 500
LENDER_YEAR_MIN = 20
MODEL_TOP = 3
CLASSIC, FICO_NEW, VS_OLD = (1, 2, 3, 4), (11, 12, 13, 14), (5, 6)
VS4, MULTI, OTHER, NA, NO_CO, EXEMPT = 15, 7, 8, 9, 10, 1111
MODEL_NAMES = {1: "Equifax Beacon 5.0", 2: "Experian Fair Isaac v2", 3: "TransUnion FICO Classic 04", 4: "TransUnion FICO Classic 98", 12: "FICO 8", 11: "FICO 9", 13: "FICO 10", 14: "FICO 10T",
               15: "VantageScore 4.0", 6: "VantageScore 3.0", 5: "VantageScore 2.0", 7: "More than one model", 8: "Other model"}
MODEL_FAMILY = {**dict.fromkeys(CLASSIC, "classic"), **dict.fromkeys(FICO_NEW, "fico_new"), 15: "vs4", **dict.fromkeys(VS_OLD, "vs_old"), 7: "multi", 8: "other"}
SHARES = ("classic", "fico_new", "vs4", "vs_old", "multi", "other", "none")
# Tried in order; a loan with two named models counts under the first that applies, so a named VantageScore is never hidden.
_IN = lambda codes: f"(applicant_credit_score_type IN {codes} OR co_applicant_credit_score_type IN {codes})"  # noqa: E731
MODEL_SQL = f"""CASE WHEN applicant_credit_score_type = {EXEMPT} OR co_applicant_credit_score_type = {EXEMPT} THEN 'none'
    WHEN {_IN((VS4, VS4))} THEN 'vs4' WHEN {_IN(VS_OLD)} THEN 'vs_old' WHEN {_IN(FICO_NEW)} THEN 'fico_new' WHEN {_IN(CLASSIC)} THEN 'classic'
    WHEN {_IN((MULTI, MULTI))} THEN 'multi' WHEN {_IN((OTHER, OTHER))} THEN 'other' ELSE 'none' END"""
# (key, label); tried in this order, so a home equity loan or a loan sold to a GSE is never also counted below. Loans not in a listed segment (multifamily, reverse) are left out.
SEGMENTS = [("gse", "Sold to Fannie or Freddie"), ("fha", "FHA"), ("va", "VA"), ("usda", "USDA"), ("jumbo", "Jumbo"), ("private", "Conforming size, sold to a private securitizer"),
            ("other_buyer", "Conforming size, sold to another buyer"), ("not_sold", "Conforming size, not sold that year"), ("business", "Business purpose"), ("equity", "Home equity and second liens")]
_BIZ = "business_or_commercial_purpose = 1"
SEGMENT_SQL = f"""CASE WHEN open_end_line_of_credit = 1 OR lien_status = 2 THEN 'equity'
    WHEN reverse_mortgage = 1 OR derived_dwelling_category LIKE 'Multifamily%' THEN NULL
    WHEN loan_type = 2 THEN 'fha' WHEN loan_type = 3 THEN 'va' WHEN loan_type = 4 THEN 'usda'
    WHEN purchaser_type IN (1, 3) THEN 'gse' WHEN {_BIZ} THEN 'business'
    WHEN conforming_loan_limit = 'NC' THEN 'jumbo' WHEN purchaser_type = 5 THEN 'private' WHEN purchaser_type = 0 THEN 'not_sold' ELSE 'other_buyer' END"""
# Kinds of loan that can be told apart before anyone buys it, for applications that never funded.
KIND_SQL = f"""CASE WHEN open_end_line_of_credit = 1 OR lien_status = 2 THEN 'equity' WHEN reverse_mortgage = 1 OR derived_dwelling_category LIKE 'Multifamily%' THEN NULL
    WHEN loan_type = 2 THEN 'fha' WHEN loan_type = 3 THEN 'va' WHEN loan_type = 4 THEN 'usda' WHEN {_BIZ} THEN 'business' WHEN conforming_loan_limit = 'NC' THEN 'jumbo' ELSE 'conforming' END"""
KINDS = [("conforming", "Conforming size"), ("jumbo", "Jumbo"), ("fha", "FHA"), ("va", "VA"), ("usda", "USDA"), ("business", "Business purpose"), ("equity", "Home equity and second liens")]

# The fields kept from the public file (99 columns, about 5 GB); applications for loans the lender bought are left out, since the seller's record counts them.
KEEP_INT = ["action_taken", "purchaser_type", "loan_type", "loan_purpose", "lien_status", "reverse_mortgage", "open_end_line_of_credit", "business_or_commercial_purpose", "loan_amount",
            "occupancy_type", "applicant_credit_score_type", "co_applicant_credit_score_type", "submission_of_application", "initially_payable_to_institution", "aus_1"]
KEEP_TEXT = ["lei", "conforming_loan_limit", "derived_dwelling_category"]
PURCHASED = 6
COUNT_GAP = 0.0001  # the 2018 file is a few hundred records short of its lenders' filings, out of 15 million


def _member(z: zipfile.ZipFile) -> str:
    """The zip's one table; some years' zips also carry a Mac folder."""
    names = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt")) and "__MACOSX" not in n]
    if len(names) != 1:
        raise ValueError(f"expected one table in the zip: {z.namelist()}")
    return names[0]


def _column(name: str) -> str:
    """Early years' files spell the same fields with hyphens (co-applicant_credit_score_type)."""
    return name.strip().lower().replace("-", "_")


def lender_names(ts_zip: Path) -> dict[str, tuple[str, int]]:
    """lei -> (name, how many records it filed), from the Transmittal Sheet file."""
    with zipfile.ZipFile(ts_zip) as z, z.open(_member(z)) as f:
        rows = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))
        rows.fieldnames = [_column(n) for n in rows.fieldnames]
        return {r["lei"]: (r["respondent_name"].strip(), int(r["lar_count"])) for r in rows}


def ingest(year: int, raw_dir: Path | None = None) -> dict:
    """The year's zips -> data/hmda/{year}.parquet and lenders_{year}.parquet; deletes the raw files once the record count ties to the lenders' own filings, within COUNT_GAP."""
    raw_dir = raw_dir or paths.HMDA / "raw" / str(year)
    lar_zip, ts_zip = raw_dir / f"{year}_public_lar_csv.zip", raw_dir / f"{year}_public_ts_csv.zip"
    names = lender_names(ts_zip)
    filed = sum(n for _, n in names.values())
    csv_path = raw_dir / f"{year}_public_lar.csv"
    out, lenders = paths.HMDA / f"{year}.parquet", paths.HMDA / f"lenders_{year}.parquet"
    try:
        with zipfile.ZipFile(lar_zip) as z, z.open(_member(z)) as src, open(csv_path, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 22)
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            spelled = {_column(c): c for c in next(csv.reader(f))}
        con = duckdb.connect()
        src = f"read_csv('{csv_path}', header=true, all_varchar=true)"
        rows = con.execute(f"SELECT count(*) FROM {src}").fetchone()[0]
        if abs(rows - filed) > filed * COUNT_GAP:
            raise ValueError(f"{rows:,} records in the file against {filed:,} on the lenders' filings")
        cols = ", ".join([*(f'"{spelled[c]}" AS {c}' for c in KEEP_TEXT), *(f'try_cast("{spelled[c]}" AS INTEGER) AS {c}' for c in KEEP_INT)])
        part = out.with_suffix(".part")  # a finished year only: a stopped load leaves nothing that reads as one
        con.execute(f"""COPY (SELECT {cols} FROM {src} WHERE "{spelled['action_taken']}" <> '{PURCHASED}') TO '{part}' (FORMAT parquet, COMPRESSION zstd)""")
        part.replace(out)
        con.execute("CREATE TABLE l (lei VARCHAR, name VARCHAR, records BIGINT)")
        con.executemany("INSERT INTO l VALUES (?, ?, ?)", [(k, v[0], v[1]) for k, v in names.items()])
        con.execute(f"COPY l TO '{lenders}' (FORMAT parquet, COMPRESSION zstd)")
        kept = con.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]
        con.close()
    finally:
        csv_path.unlink(missing_ok=True)  # about 5 GB
    lar_zip.unlink()
    ts_zip.unlink()
    for folder in (raw_dir, raw_dir.parent):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return {"year": year, "records": rows, "filed": filed, "kept": kept, "lenders": len(names), "parquet_mb": round(out.stat().st_size / 1e6, 1)}


_AS_IS = {w.upper(): w for w in ("US", "USA", "NFM", "CMG", "PNC", "UMB", "TD", "BMO", "M&T", "ESL", "UW", "DHI", "NBKC", "USAA", "HSBC", "BOKF", "iQ", "OCMBC", "CrossCountry", "PennyMac", "AmeriSave", "AmeriHome", "CommunityAmerica", "HomeBridge", "loanDepot.com")}
_CUT_NAMES = {"Fairway Independent Mort": "Fairway Independent Mortgage", "Jovia Financial Federal Credit": "Jovia Financial Federal Credit Union"}  # as filed, cut short
_ENDING = re.compile(r"[,\s]+(LLC|L\.L\.C\.?|Inc\.?|Corp\.?|Corporation|Ltd\.?|N\.A\.?|NA|National Association|FSB|LP|L\.P\.?|Company)\.?$", re.I)


def short_name(name: str) -> str:
    """A filed name as a chart label: no all-capitals, legal endings or filing numbers."""
    out = re.sub(r"\s*\(\d+\)\s*$", "", name.strip())
    if out == out.upper():
        words = [_AS_IS.get(w, w.capitalize()) for w in out.split()]
        out = " ".join(w if i == 0 or w not in ("Of", "And", "The", "For") else w.lower() for i, w in enumerate(words))
    for _ in range(2):  # "Company, Inc." has two endings
        out = _ENDING.sub("", out)
    out = " ".join(_AS_IS.get(w.upper(), w) for w in out.strip(" ,.").split()) or name.strip()
    return _CUT_NAMES.get(out, out)


def _r(v):
    return None if v is None else round(v, 6)


def _shares(cur_cols: list[str]) -> str:
    return ", ".join(f"count(*) FILTER (WHERE m = '{k}') AS {k}_n" for k in cur_cols)


def build_datasets() -> dict[str, list[dict]]:
    years = sorted(int(p.stem) for p in paths.HMDA.glob("*.parquet") if p.stem.isdigit()) if paths.HMDA.exists() else []
    if not years:
        return {"whole_market": []}
    year = years[-1]
    con = duckdb.connect()
    files = [str(paths.HMDA / f"{y}.parquet") for y in years]
    con.execute(f"""CREATE VIEW every_year AS SELECT regexp_extract(filename, '(\\d{{4}})\\.parquet$', 1)::INTEGER AS year, * EXCLUDE (filename) FROM read_parquet({files}, filename=true)""")
    con.execute(f"CREATE VIEW h AS SELECT * FROM '{paths.HMDA / f'{year}.parquet'}'")
    con.execute(f"CREATE VIEW n AS SELECT * FROM '{paths.HMDA / f'lenders_{year}.parquet'}'")
    con.execute(f"""CREATE TEMP TABLE o AS SELECT lei, coalesce(loan_amount, 0) AS amt, {MODEL_SQL} AS m, {SEGMENT_SQL} AS seg, applicant_credit_score_type AS a, co_applicant_credit_score_type AS c
                    FROM h WHERE action_taken = 1""")
    count = _shares(SHARES)

    def row(values: list, total_i: int) -> dict:
        n = values[total_i]
        s = {k: _r(values[total_i + 2 + i] / n) if n else None for i, k in enumerate(SHARES)}
        if not n:
            return s | dict.fromkeys(("fico", "vs", "unnamed", "unknown"))
        return s | {"fico": _r(s["classic"] + s["fico_new"]), "vs": _r(s["vs4"] + s["vs_old"]), "unnamed": _r(s["multi"] + s["other"]), "unknown": _r(s["multi"] + s["other"] + s["none"])}

    out = []
    records = sum(r[0] for r in con.execute("SELECT records FROM n").fetchall())
    out.append({"view": "meta", "year": year, "first_year": years[0], "file_date": YEAR_FILES.get(year), "records": records, "n": con.execute("SELECT count(*) FROM o").fetchone()[0],
                "lenders": con.execute("SELECT count(DISTINCT lei) FROM o").fetchone()[0]})
    by_seg = {r[0]: r for r in con.execute(f"SELECT seg, count(*), sum(amt), {count} FROM o WHERE seg IS NOT NULL GROUP BY 1").fetchall()}
    first_keys = [k for k, _ in SEGMENTS if k != "equity"]
    first = con.execute(f"SELECT 'first', count(*), sum(amt), {count} FROM o WHERE seg IS NOT NULL AND seg <> 'equity'").fetchone()
    whole = con.execute(f"SELECT 'all', count(*), sum(amt), {count} FROM o WHERE seg IS NOT NULL").fetchone()
    listed = [("all", "All home loans", whole), ("first", "All first-lien home loans", first)] + [(k, label, by_seg[k]) for k, label in SEGMENTS if k in by_seg]
    for order, (key, label, r) in enumerate(listed):
        out.append({"view": "segment", "key": key, "label": label, "order": order, "first_lien": key in first_keys, "n": r[1], "usd_bn": round(r[2] / 1e9, 1), **row(list(r), 1)})
    scopes = {"all": ("seg IS NOT NULL", "n"), "first": ("seg IS NOT NULL AND seg <> 'equity'", "n"), "equity": ("seg = 'equity'", "n"),
              "vs": ("seg IS NOT NULL", "vs4_n + vs_old_n"), "fico_new": ("seg IS NOT NULL", "fico_new_n")}
    con.execute(f"""CREATE TEMP TABLE y AS SELECT year, lei, coalesce(loan_amount, 0) AS amt, {MODEL_SQL} AS m, {SEGMENT_SQL} AS seg, applicant_credit_score_type AS a, co_applicant_credit_score_type AS c
                    FROM every_year WHERE action_taken = 1""")
    for scope, (where, rank) in scopes.items():
        rows = con.execute(f"""
            WITH t AS (SELECT lei, count(*) AS n, sum(amt) AS amt, {count}, count(*) FILTER (WHERE seg = 'equity') AS equity_n FROM o WHERE {where} GROUP BY 1)
            SELECT coalesce(l.name, t.lei), t.n, t.amt, {", ".join(f"t.{k}_n" for k in SHARES)}, t.equity_n, t.lei
            FROM t LEFT JOIN n l USING (lei) WHERE t.n >= {LENDER_MIN} ORDER BY {rank} DESC, t.n DESC, t.lei LIMIT {LENDER_TOP}""").fetchall()
        for i, r in enumerate(rows):
            out.append({"view": "lender", "scope": scope, "rank": i + 1, "name": short_name(r[0]), "n": r[1], "usd_bn": round(r[2] / 1e9, 2), **row(list(r), 1), "equity_share": _r(r[-2] / r[1])})
        ranks = {r[-1]: (i + 1, short_name(r[0])) for i, r in enumerate(rows)}
        leis = ", ".join(f"'{k}'" for k in ranks) or "''"
        for r in con.execute(f"SELECT year, lei, count(*), sum(amt), {count} FROM y WHERE {where} AND lei IN ({leis}) GROUP BY 1, 2 HAVING count(*) >= {LENDER_YEAR_MIN} ORDER BY 1, 2").fetchall():
            out.append({"view": "lender_year", "scope": scope, "rank": ranks[r[1]][0], "name": ranks[r[1]][1], "year": r[0], "n": r[2], **row(list(r[1:]), 1)})
    by_year = {}
    for r in con.execute(f"SELECT year, seg, count(*), sum(amt), {count} FROM y WHERE seg IS NOT NULL GROUP BY 1, 2").fetchall():
        by_year.setdefault(r[0], {})[r[1]] = list(r[1:])
    labels = {"all": "All home loans", "first": "All first-lien home loans", **dict(SEGMENTS)}
    for y, parts in sorted(by_year.items()):
        add = lambda keys: [None] + [sum(parts[k][i] for k in keys if k in parts) for i in range(1, len(next(iter(parts.values()))))]  # noqa: E731
        firsts = [k for k in parts if k != "equity"]
        for order, (key, values) in enumerate([("all", add(list(parts))), ("first", add(firsts))] + [(k, parts[k]) for k, _ in SEGMENTS if k in parts]):
            out.append({"view": "trend", "key": key, "label": labels[key], "order": order, "year": y, "n": values[1], "usd_bn": round(values[2] / 1e9, 1), **row(values, 1)})
    totals = {y: sum(v[1] for v in parts.values()) for y, parts in by_year.items()}
    for code, name in MODEL_NAMES.items():
        for y, n in con.execute(f"SELECT year, count(*) FROM y WHERE seg IS NOT NULL AND (a = {code} OR c = {code}) GROUP BY 1 ORDER BY 1").fetchall():
            out.append({"view": "model_year", "code": code, "name": name, "family": MODEL_FAMILY[code], "year": y, "n": n, "share": _r(n / totals[y])})
    for code, name in MODEL_NAMES.items():
        hit = f"(a = {code} OR c = {code})"
        n, eq = con.execute(f"SELECT count(*), count(*) FILTER (WHERE seg = 'equity') FROM o WHERE seg IS NOT NULL AND {hit}").fetchone()
        tops = con.execute(f"SELECT coalesce(l.name, o.lei), count(*) FROM o LEFT JOIN n l USING (lei) WHERE seg IS NOT NULL AND {hit} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {MODEL_TOP}").fetchall()
        out.append({"view": "model", "code": code, "name": name, "family": MODEL_FAMILY[code], "n": n, "equity_share": _r(eq / n) if n else None, "users": "; ".join(f"{short_name(t[0])} ({t[1]:,})" for t in tops)})
    apps = {r[0]: r[1:] for r in con.execute(f"""SELECT {KIND_SQL} AS k, count(*) FILTER (WHERE action_taken = 1), count(*) FROM h GROUP BY 1""").fetchall() if r[0]}
    for key, label in KINDS:
        if key in apps and apps[key][0]:
            out.append({"view": "apps", "key": key, "label": label, "n": apps[key][0], "apps": apps[key][1], "per_loan": _r(apps[key][1] / apps[key][0])})
    con.close()
    keys = sorted({k for r in out for k in r})
    return {"whole_market": [{k: r.get(k) for k in keys} for r in out]}
