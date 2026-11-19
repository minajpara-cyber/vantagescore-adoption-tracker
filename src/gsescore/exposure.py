"""Inputs for the FICO exposure calculator: reference/assumptions.csv, and what the loan files say.

  assumptions  one row per input: key, label, value, unit (usd, usd_m, count, share), kind (data, source or judgment), note, source,
               url and date. Prices and FICO's reported revenue are sourced; the bureaus and credit pulls per funded loan are judgment
               and cannot be seen in these files.
"""
import csv
import json
from math import isfinite

from . import paths

ASSUMPTIONS_CSV = paths.REPO / "reference" / "assumptions.csv"
BORROWER_MONTHS = 3
PULL_CASES = (4, 5, 6)  # credit pulls per funded loan: the calculator's input, the middle case, the outer case


def usd_price(v: float) -> str:
    """A price or a fee as it is quoted: whole dollars with no cents, anything else to the cent."""
    return f"${v:,.0f}" if float(v).is_integer() else f"${v:,.2f}"


def _number(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _last_good() -> dict:
    """The last build's values by key, for a row typed wrong this time."""
    try:
        return {r["key"]: r["value"] for r in json.loads((paths.SITE_DATA / "assumptions.json").read_text())["rows"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def assumption_slips() -> list[str]:
    """The hand-kept file's rows whose value is not a number, for the weekly report. Never raises."""
    try:
        with ASSUMPTIONS_CSV.open(newline="") as f:
            return [f"assumptions: {r['key']} in reference/assumptions.csv is not a number, so the last build's value stands" for r in csv.DictReader(f) if _number(r.get("value")) is None]
    except Exception as e:
        return [f"assumptions: could not read reference/assumptions.csv: {e!r}"]


def fico_per_loan(bureaus: float, borrowers: float, pulls: float, price: float, fee: float = 0.0) -> float:
    """FICO's revenue on one funded loan: bureaus x borrowers x (pulls x price + the fee on a funded loan). tools.js and the workbook's formulas write this same sum."""
    return bureaus * borrowers * (pulls * price + fee)


def fico_dollars(loans: float, share: float, a: dict, pulls: float | None = None, price: float | None = None) -> float:
    """FICO's revenue a year on `share` of `loans`, with the assumptions `a` by key (bureaus, borrowers_per_loan, pulls_per_loan, price_per_score, closing_fee)."""
    return loans * share * fico_per_loan(a["bureaus"], a["borrowers_per_loan"], a["pulls_per_loan"] if pulls is None else pulls, a["price_per_score"] if price is None else price, a["closing_fee"])


def build_datasets(con, score_mix: list[dict]) -> dict[str, list[dict]]:
    """Needs monthly and loans on this connection, and score_mix (scores.py)."""
    last = _last_good()
    with ASSUMPTIONS_CSV.open(newline="") as f:  # a value typed wrong keeps the last build's, so a slip stops nothing: assumption_slips says so
        rows = [{**{k: v or None for k, v in r.items()}, "value": _number(r["value"]) if _number(r["value"]) is not None else last.get(r["key"])} for r in csv.DictReader(f)]

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
            from .front import shows_second  # front imports this module
            fannie = next((r for r in score_mix if r["view"] == "month" and r["agency"] == "FNMA" and r.get("headline")), head)
            add(f"no_fico_{agency.lower()}", f"Loans with no Classic FICO, {name}", head["vs_only_share"] if shows_second(fannie) else last.get(f"no_fico_{agency.lower()}", head["vs_only_share"]), "share",
                f"Issued in the latest full-enough month ({head['start'][:7]}). Some lenders show fewer of their scores at Freddie Mac, so Fannie Mae's share says more about lenders.")
    keys = ["key", "label", "value", "unit", "kind", "note", "source", "url", "date"]
    return {"assumptions": [{k: r.get(k) for k in keys} for r in rows]}
