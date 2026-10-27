"""End-to-end check on synthetic files: ingest -> views -> score_model -> aggregates -> seller datasets.

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
# issue month Aug 2026: Wells Fargo's first VS4 loans (2 of 4), Rocket with FICO only (2)
aug = {"First Payment Date": "092026"}
write_zip(raw / "fl260903.zip", "fl260903.txt",
          [hdr] + [loan_row(400 + i, "QD0003", 9999, 740, seller="WELLS FARGO", extra=aug) for i in range(2)]
          + [loan_row(402 + i, "QD0003", 700, 9999, seller="WELLS FARGO", extra=aug) for i in range(2)]
          + [loan_row(404 + i, "QD0003", 760, 7777, extra=aug) for i in range(2)])

from gsescore.aggregate import build  # noqa: E402
from gsescore.ingest import ingest_paths  # noqa: E402
from gsescore.warehouse import connect  # noqa: E402

res = ingest_paths([home / "data" / "raw"])
assert sum(r["status"] == "ingested" for r in res) == 5, res
assert all(r["status"] == "skipped" for r in ingest_paths([home / "data" / "raw"])), "manifest should dedupe"

con = connect()
got = dict(con.execute("SELECT score_model, count(*) FROM loans GROUP BY 1").fetchall())
assert got == {"C": 24, "V": 6, "N": 1, "X": 1}, got  # 8 C + 1 V (inferred); 3 V + 7 C + 1 N (indicator); 5 C Fannie headerless; 1 no score; Aug 2 V + 4 C
basis = dict(con.execute("SELECT score_model_basis, count(*) FROM loans GROUP BY 1").fetchall())
assert basis == {"inferred": 9 + 5 + 1 + 6, "pricing_indicator": 11}, basis
assert con.execute("SELECT count(*) FROM loans WHERE agency='FNMA' AND first_intraday_date = DATE '2026-06-02'").fetchone()[0] == 5
assert con.execute("SELECT pricing_score FROM loans WHERE loan_id = 'L000000100'").fetchone()[0] == 781
assert con.execute("SELECT pricing_score FROM loans WHERE loan_id = 'L000000210'").fetchone()[0] == 812

assert con.execute("SELECT DISTINCT issue_month FROM loans ORDER BY 1").fetchall() == [(date(2026, 7, 1),), (date(2026, 8, 1),)]

from gsescore.lenders import KEY_SQL  # noqa: E402

con.execute(f"CREATE TEMP MACRO seller_key(s) AS {KEY_SQL}")
for name, key in [("JPMORGAN CHASE BANK, NATIONAL ASSOCIATION", "JPMORGAN CHASE BANK"), ("A&D MORTGAGE LLC", "A AND D MORTGAGE"),
                  ("PROVIDENT FUNDING ASSOCIATES, L.P.", "PROVIDENT FUNDING ASSOCIATES"), (None, "")]:
    assert con.execute("SELECT seller_key(?)", [name]).fetchone()[0] == key, name

meta = build(home / "site" / "data")
daily = json.loads((home / "site" / "data" / "daily.json").read_text())
assert meta["loans"] == 32 and len(daily["rows"]) == 8, (meta, daily)  # 4 days x (one GSE + All)
monthly = json.loads((home / "site" / "data" / "monthly.json").read_text())["rows"]
everyone = next(r for r in monthly if r["agency"] == "All" and r["month"] == "2026-07-01")
assert (everyone["scored_loans"], everyone["vs4_loans"], everyone["final"]) == (25, 4, False), everyone
assert abs(everyone["vs4_share"] - 4 / 25) < 1e-9, everyone

# Seller datasets. July: Rocket 1 VS4 of 9, UWM 3 of 11, Wells Fargo 0 of 5; August: Wells 2 of 4, Rocket 0 of 2.
rows = lambda name: json.loads((home / "site" / "data" / f"{name}.json").read_text())["rows"]  # noqa: E731
sellers = {r["id"]: r for r in rows("sellers")}
rocket, wells = sellers["rocket-mortgage"], sellers["wells-fargo"]
assert (rocket["name"], rocket["ticker"], rocket["parent"], rocket["vs4_loans"], rocket["first_vs4_month"]) == (
    "Rocket Mortgage", "RKT", "Rocket Companies", 1, "2026-07-01"), rocket
assert (wells["first_vs4_month"], wells["first_vs4_date"], wells["vs4_loans"]) == ("2026-08-01", "2026-09-03", 2), wells
assert not any(r["level"] == "parent" for r in sellers.values())  # Rocket Companies' other sellers are absent
ad = next(r for r in rows("adoption") if r["agency"] == "All" and r["month"] == "2026-08-01")
assert (ad["adopters_any"], ad["new_any"], ad["active_sellers"], ad["adopters_ten"]) == (3, 1, 1, 0), ad
assert abs(ad["adopters_share_any"] - 1) < 1e-6 and abs(ad["vs4_within_any"] - 2 / 6) < 1e-6, ad  # files round to 6 places
within = (2 / 6 + 9 / 25) / 2 * (0 - 1 / 9)  # Rocket's own VS4 use fell
mix = (1 / 9) / 2 * (2 / 6 - 9 / 25) + 3 / 11 * (0 - 11 / 25)  # Rocket's volume fell; UWM delivered nothing
for k, want in [("d_total", 2 / 6 - 4 / 25), ("d_new", 2 / 6), ("d_within", within), ("d_mix", mix)]:
    assert abs(ad[k] - want) < 1e-6, (k, ad[k], want)
jul = next(r for r in rows("series") if r["period"] == "month" and r["agency"] == "All" and r["start"] == "2026-07-01")
assert abs(jul["actual"] - 4 / 25) < 1e-6 and abs(jul["ex_top2"] - 1 / 9) < 1e-6, jul  # without UWM and Wells
h = rows("highlights")[0]
assert (h["data_through"], h["new_7d"], h["new_30d"], "mover_id" in h) == ("2026-10-20", 1, 1, False), h
print("ok:", home)
