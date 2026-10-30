"""Inputs for the FICO exposure calculator: reference/assumptions.csv, and what the loan files say.

  assumptions  one row per input: key, label, value, unit (usd, usd_m, count, share), kind (data, source or judgment), note, source,
               url and date. Prices and FICO's reported revenue are sourced; the bureaus and credit pulls per funded loan are judgment
               and cannot be seen in these files.
"""
import csv

from . import paths

ASSUMPTIONS_CSV = paths.REPO / "reference" / "assumptions.csv"
BORROWER_MONTHS = 3


def build_datasets(con, score_mix: list[dict]) -> dict[str, list[dict]]:
    """Needs monthly and loans on this connection, and score_mix (scores.py)."""
    with ASSUMPTIONS_CSV.open(newline="") as f:
        rows = [{**{k: v or None for k, v in r.items()}, "value": float(r["value"])} for r in csv.DictReader(f)]

    def add(key, label, value, unit, note):
        rows.append({"key": key, "label": label, "value": round(float(value or 0), 6), "unit": unit, "kind": "data", "note": note, "source": None, "url": None, "date": None})

    year = con.execute("SELECT avg(scored_loans) * 12 FROM monthly WHERE agency = 'All' AND final").fetchone()[0]
    add("gse_loans_year", "GSE loans a year", year, "count", "Both GSEs: the average month with a month-end file, times 12.")
    borrowers = con.execute(f"""
        SELECT avg(num_borrowers) FROM loans WHERE issue_month IN
            (SELECT month FROM monthly WHERE agency = 'All' AND final ORDER BY month DESC LIMIT {BORROWER_MONTHS})""").fetchone()[0]
    add("borrowers_per_loan", "Borrowers per loan", borrowers, "count", f"The latest {BORROWER_MONTHS} months with a month-end file.")
    for agency, name in (("FNMA", "at Fannie Mae"), ("All", "both GSEs")):
        head = next((r for r in score_mix if r["view"] == "month" and r["agency"] == agency and r.get("headline")), None)
        if head:
            add(f"no_fico_{agency.lower()}", f"Loans with no Classic FICO, {name}", head["vs_only_share"], "share",
                f"Issued in the latest full-enough month ({head['start'][:7]}). Some lenders show fewer of their scores at Freddie Mac, so Fannie Mae is the cleaner read.")
    keys = ["key", "label", "value", "unit", "kind", "note", "source", "url", "date"]
    return {"assumptions": [{k: r.get(k) for k in keys} for r in rows]}
