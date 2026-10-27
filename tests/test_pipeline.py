"""End-to-end check on synthetic files: ingest -> views -> score_model -> aggregates.

Run: .venv/bin/python -I tests/test_pipeline.py
"""
import io
import json
import os
import random
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

home = Path(tempfile.mkdtemp(prefix="gsescore-test-"))
os.environ["GSESCORE_HOME"] = str(home)

from gsescore.layout import LOAN_FIELDS  # noqa: E402

HEADER = [name for _, name, _, _ in LOAN_FIELDS]
HEADER = ["Classic FICO" if h == "Classic FICO" else "VS4" if h == "VantageScore 4.0" else h for h in HEADER]


def loan_row(i, pool, fico, vs4, pricing="", seller="ROCKET MORTGAGE, LLC", extra=None):
    vals = {h: "" for h in HEADER}
    vals.update({
        "Loan Identifier": f"L{i:09d}", "Loan Correction Indicator": "N", "Prefix": "QD",
        "Security Identifier": pool, "CUSIP": "3132XXXXX", "Mortgage Loan Amount": "350000",
        "Issuance Investor Loan UPB": "349500.00", "Original Interest Rate": "6.375",
        "First Payment Date": "082026", "Loan Term": "360", "Loan Age": "0",  # issue month Jul 2026
        "Loan-To-Value (LTV)": str(random.choice([60, 80, 95])), "Debt-To-Income (DTI)": "38",
        "Classic FICO": str(fico), "VS4": str(vs4), "Number of Borrowers": "1",
        "First Time Home Buyer Indicator": "Y", "Loan Purpose": "P", "Occupancy Status": "P",
        "Number of Units": "1", "Property Type": "SF", "Channel": "R", "Property State": "TX",
        "Seller Name": seller, "Pricing Indicator": pricing,
    })
    vals.update(extra or {})
    return "|".join(vals[h] for h in HEADER)


def write_zip(path: Path, member: str, lines: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, "\n".join(lines) + "\n")


raw = home / "data" / "raw" / "FHLMC" / "intraday"
hdr = "|".join(HEADER)
write_zip(raw / "fl260601.zip", "fl260601.txt",
          [hdr] + [loan_row(i, "QD0001", 760, 7777) for i in range(8)] + [loan_row(100, "QD0001", 9999, 781)])
write_zip(raw / "fl260601_2.zip", "fl260601_2.txt", [hdr])  # empty intraday file
write_zip(raw / "fl261020.zip", "fl261020.txt",
          [hdr] + [loan_row(200 + i, "QD0002", 745, 765, pricing="V" if i < 3 else "C", seller="UWM")
                   for i in range(10)]
          + [loan_row(210, "QD0002", 745, 765, pricing="N", seller="UWM", extra={"Fannie Score": "812"}),
             loan_row(211, "QD0002", 9999, 9999, pricing="9", seller="UWM")])  # Fannie Score priced; no score
# headerless file, positional mapping
write_zip(home / "data" / "raw" / "FNMA" / "intraday" / "FNM_ILLD_20260602_1.zip", "FNM_ILLD_20260602_1.txt",
          [loan_row(300 + i, "BX0001", 700, 9999, seller="WELLS FARGO") for i in range(5)])

from gsescore.aggregate import build  # noqa: E402
from gsescore.ingest import ingest_paths  # noqa: E402
from gsescore.warehouse import connect  # noqa: E402

res = ingest_paths([home / "data" / "raw"])
assert sum(r["status"] == "ingested" for r in res) == 4, res
assert all(r["status"] == "skipped" for r in ingest_paths([home / "data" / "raw"])), "manifest should dedupe"

con = connect()
got = dict(con.execute("SELECT score_model, count(*) FROM loans GROUP BY 1").fetchall())
assert got == {"C": 20, "V": 4, "N": 1, "X": 1}, got  # 8 C + 1 V (inferred); 3 V + 7 C + 1 N (indicator); 5 C Fannie headerless; 1 no score
basis = dict(con.execute("SELECT score_model_basis, count(*) FROM loans GROUP BY 1").fetchall())
assert basis == {"inferred": 9 + 5 + 1, "pricing_indicator": 11}, basis
assert con.execute("SELECT count(*) FROM loans WHERE agency='FNMA' AND first_intraday_date = DATE '2026-06-02'").fetchone()[0] == 5
assert con.execute("SELECT pricing_score FROM loans WHERE loan_id = 'L000000100'").fetchone()[0] == 781
assert con.execute("SELECT pricing_score FROM loans WHERE loan_id = 'L000000210'").fetchone()[0] == 812

assert con.execute("SELECT DISTINCT issue_month FROM loans").fetchall() == [(date(2026, 7, 1),)]

meta = build(home / "site" / "data")
daily = json.loads((home / "site" / "data" / "daily.json").read_text())
assert meta["loans"] == 26 and len(daily["rows"]) == 6, (meta, daily)  # 3 days x (one GSE + All)
monthly = json.loads((home / "site" / "data" / "monthly.json").read_text())["rows"]
everyone = next(r for r in monthly if r["agency"] == "All")
assert (everyone["scored_loans"], everyone["vs4_loans"], everyone["final"]) == (25, 4, False), everyone
assert abs(everyone["vs4_share"] - 4 / 25) < 1e-9, everyone
print("ok:", home)
