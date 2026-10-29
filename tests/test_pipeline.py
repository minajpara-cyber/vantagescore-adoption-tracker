"""End-to-end check on synthetic files: ingest -> views -> score_model -> aggregates -> seller datasets -> as-of
-> score groups and borrower mix -> score choice and ceiling -> outlook, plus the outlook and the rate engine on
planted data.

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
# Fannie Mae September 2026, final: Aug 10 discloses 2 VS4 and 3 FICO loans; Sep 15 deletes one of the FICO
# loans and adds 2 more; the month-end file drops one VS4 loan (pulled) and adds a FICO loan never disclosed.
# October 2026 is still open: UWM 1 VS4, Test Bank 2 FICO and Small Credit Union 1 FICO loan, disclosed Oct 15.
fn, sep, octo = home / "data" / "raw" / "FNMA", {"First Payment Date": "102026"}, {"First Payment Date": "112026"}
bank = lambda i, fico, vs4, extra=sep: loan_row(i, "CA0001", fico, vs4, seller="TEST BANK", extra=extra)  # noqa: E731
write_zip(fn / "intraday" / "FNM_ILLD_20260810_1.zip", "FNM_ILLD_20260810_1.txt",
          [hdr, bank(500, 9999, 720), bank(507, 9999, 730)] + [bank(501 + i, 700, 9999) for i in range(3)])
write_zip(fn / "intraday" / "FNM_ILLD_20260915_1.zip", "FNM_ILLD_20260915_1.txt",
          [hdr, bank(504, 700, 9999), bank(505, 700, 9999), bank(503, 700, 9999, {**sep, "Loan Correction Indicator": "D"})])
write_zip(fn / "monthend" / "FNM_ILLD_202609.zip", "FNM_ILLD_202609.txt",
          [hdr, bank(500, 9999, 720)] + [bank(i, 700, 9999) for i in (501, 502, 504, 505, 506)])
write_zip(fn / "intraday" / "FNM_ILLD_20261015_1.zip", "FNM_ILLD_20261015_1.txt",
          [hdr, loan_row(510, "CA0002", 9999, 700, seller="UWM", extra=octo), bank(511, 700, 9999, octo), bank(512, 700, 9999, octo),
           loan_row(513, "CA0002", 700, 9999, seller="SMALL CREDIT UNION", extra=octo)])

from gsescore.aggregate import build  # noqa: E402
from gsescore.ingest import ingest_paths  # noqa: E402
from gsescore.warehouse import connect  # noqa: E402

res = ingest_paths([home / "data" / "raw"])
assert sum(r["status"] == "ingested" for r in res) == 9, res
assert all(r["status"] == "skipped" for r in ingest_paths([home / "data" / "raw"])), "manifest should dedupe"

con = connect()
got = dict(con.execute("SELECT score_model, count(*) FROM loans GROUP BY 1").fetchall())
assert got == {"C": 32, "V": 8, "N": 1, "X": 1}, got  # 8 C + 1 V (inferred); 3 V + 7 C + 1 N (indicator); 5 C Fannie headerless; 1 no score; Aug 2 V + 4 C; Sep 1 V + 5 C; Oct 1 V + 3 C
basis = dict(con.execute("SELECT score_model_basis, count(*) FROM loans GROUP BY 1").fetchall())
assert basis == {"inferred": 9 + 5 + 1 + 6 + 6 + 4, "pricing_indicator": 11}, basis
assert con.execute("SELECT count(*) FROM loans WHERE agency='FNMA' AND first_intraday_date = DATE '2026-06-02'").fetchone()[0] == 5
assert con.execute("SELECT pricing_score FROM loans WHERE loan_id = 'L000000100'").fetchone()[0] == 781
assert con.execute("SELECT pricing_score FROM loans WHERE loan_id = 'L000000210'").fetchone()[0] == 812

assert con.execute("SELECT DISTINCT issue_month FROM loans ORDER BY 1").fetchall() == [(date(2026, m, 1),) for m in (7, 8, 9, 10)]

from gsescore.lenders import KEY_SQL  # noqa: E402

con.execute(f"CREATE TEMP MACRO seller_key(s) AS {KEY_SQL}")
for name, key in [("JPMORGAN CHASE BANK, NATIONAL ASSOCIATION", "JPMORGAN CHASE BANK"), ("A&D MORTGAGE LLC", "A AND D MORTGAGE"),
                  ("PROVIDENT FUNDING ASSOCIATES, L.P.", "PROVIDENT FUNDING ASSOCIATES"), (None, "")]:
    assert con.execute("SELECT seller_key(?)", [name]).fetchone()[0] == key, name

import gsescore.lenders  # noqa: E402

gsescore.lenders.SELLER_TOP = 3  # the 3 largest sellers plus every VS4 seller, so Small Credit Union is left out
import gsescore.borrowers  # noqa: E402

gsescore.borrowers.MIN_N = 1  # show every group, however small, so the shares below can be checked
import gsescore.scores  # noqa: E402

gsescore.scores.MIN_N = gsescore.scores.MIN_CHOICE = 1
meta = build(home / "site" / "data")
daily = json.loads((home / "site" / "data" / "daily.json").read_text())
assert meta["loans"] == 42 and len(daily["rows"]) == 14, (meta, daily)  # 7 days x (one GSE + All)
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
# First month over each threshold, by GSE: UWM at Freddie in July and Fannie in October; Wells Fargo only at Freddie.
firsts = {(r["id"], r["agency"]): r for r in rows("adopters")}
assert {k: r["first_any"] for k, r in firsts.items() if k[0] in ("uwm", "wells-fargo")} == {
    ("uwm", "All"): "2026-07-01", ("uwm", "FHLMC"): "2026-07-01", ("uwm", "FNMA"): "2026-10-01",
    ("wells-fargo", "All"): "2026-08-01", ("wells-fargo", "FHLMC"): "2026-08-01"}, firsts
assert firsts[("uwm", "All")]["first_ten"] is None and not any(r["first_pct5"] for r in firsts.values()), firsts
# October at Fannie: Small Credit Union, outside the seller list, is the rest; the listed sellers' shares and it add up to 1.
octf = next(r for r in rows("adoption") if r["agency"] == "FNMA" and r["month"] == "2026-10-01")
listed = sum(r["mkt_share"] for r in rows("seller_monthly") if r["level"] == "seller" and r["agency"] == "FNMA" and r["month"] == "2026-10-01")
assert (octf["rest_sellers"], octf["rest_share"], listed) == (1, 0.25, 0.75), (octf, listed)
assert "small-credit-union" not in sellers and not any(r["id"] == "small-credit-union" for r in rows("sellers")), sellers

# As-of: Fannie's September by day, from the intraday files published by then, against its month-end file (1 VS4 of 6).
asof = rows("asof")
past = {r["day"]: r for r in asof if r["kind"] == "past"}
assert len(past) == 31 and {(r["agency"], r["month"]) for r in asof if r["kind"] == "past"} == {("FNMA", "2026-09-01")}, asof
for day, as_of, n, share, seen in [(14, "2026-09-14", 5, 2 / 5, 3 / 6), (15, "2026-09-15", 6, 2 / 6, 5 / 6),
                                   (31, "2026-09-30", 6, 2 / 6, 5 / 6)]:
    r = past[day]
    assert (r["as_of"], r["scored_loans"]) == (as_of, n), r
    for k, want in [("vs4_share", share), ("final_vs4_share", 1 / 6), ("gap", 1 / 6 - share), ("final_seen_share", seen)]:
        assert abs(r[k] - want) < 1e-6, (day, k, r[k], want)
# October is open at day 20 (data through Oct 20); September moved -1/6 from its day 20, so 1/4 would reach 1/12.
(o,) = [r for r in asof if r["kind"] == "open"]
assert (o["agency"], o["month"], o["day"], o["months"], o["first_month"], o["last_month"]) == (
    "FNMA", "2026-10-01", 20, 1, "2026-09-01", "2026-09-01"), o
for k, want in [("vs4_share", 1 / 4), ("vs4_share_lo", 1 / 12), ("vs4_share_hi", 1 / 12), ("vs4_upb_share_hi", 1 / 12)]:
    assert abs(o[k] - want) < 1e-6, (k, o[k], want)
# Score groups: only UWM's Oct 20 loans are disclosed from Oct 19; every one carries both scores (FICO 745, VS4 765).
cov = {(r["agency"], r["week"], r["model"]): r for r in rows("score_coverage")}
assert (cov[("All", "all", "vs4")]["loans"], cov[("All", "all", "vs4")]["both_share"], cov[("All", "all", "fico")]["loans"]) == (3, 1.0, 7), cov
assert not any(k[0] == "FNMA" for k in cov), cov
mix = {(r["dim"], r["cover"], r["grp"], r["bucket"]): r for r in rows("borrowers")}
assert mix[("gap", "both", "vs4", "20 to 39")]["share"] == 1.0 and mix[("gap", "both", "fico", "20 to 39")]["share"] == 1.0, mix
assert not any(k[1] == "vs4only" and k[2] == "vs4" for k in mix), "no VS4 loan lacks a Classic FICO from Oct 19"
# VS4 by GSE, all loans: 6 of 8 at Freddie. Expected from each seller's own FICO loans: Rocket (1 VS4) and UWM (4) all
# Freddie, Wells Fargo (2) 2 of 7 Freddie, Test Bank (1) all Fannie: (1 + 4 + 2 * 2/7) / 8 = 39/56.
fre = mix[("agency", "all", "vs4", "Freddie Mac")]
assert abs(fre["share"] - 0.75) < 1e-6 and abs(fre["expected"] - 39 / 56) < 1e-6, fre
prof = {(r["cover"], r["grp"]): r for r in rows("borrower_profile")}
assert (prof[("both", "vs4")]["loans"], prof[("both", "vs4")]["wa_fico"], prof[("both", "vs4")]["avg_gap"]) == (3, 745, 20), prof
assert rows("pricing") == [], "too few FICO loans here to fit the rate model"

# Score choice: UWM's Oct 20 loans carry FICO 745 (bucket 740-759) and VS4 765 (760-779), one bucket better; 3 of 10 priced on VS4.
rule = {(r["scope"], r["agency"], r["key"]): r for r in rows("choice") if r["view"] == "rule"}
assert set(rule) == {("All", "All", "1"), ("All", "FHLMC", "1"), ("uwm", "All", "1")}, rule
assert (rule[("All", "All", "1")]["loans"], rule[("All", "All", "1")]["vs4_share"]) == (10, 0.3), rule
pull = {r["scope"]: r for r in rows("choice") if r["view"] == "pull"}
assert set(pull) == {"uwm"} and (pull["uwm"]["loans"], pull["uwm"]["both_share"]) == (10, 1.0), pull
# Ceiling: those 10 count as observed (VS4 better on all); VS4-only loans count as VS4; FICO-only loans take the rate
# measured on loans with both scores, here the overall one (no FICO bucket other than 740-759 has any): all better.
ceil = {(r["view"], r["agency"], r["start"], r["key"]): r for r in rows("ceiling")}
both = ceil[("both", "All", "2026-10-19", None)]
assert (both["loans"], both["actual"], both["better"], both["observed_share"]) == (10, 0.3, 1.0, 1.0), both
jul = ceil[("month", "All", "2026-07-01", None)]
assert (jul["loans"], jul["better"]) == (24, 1.0) and abs(jul["actual"] - 4 / 24) < 1e-6, jul
bands = [r for r in rows("ceiling") if r["view"] == "band"]
assert abs(sum(r["adds_better"] for r in bands if r["key"] != "all") - next(r for r in bands if r["key"] == "all")["adds_better"]) < 1e-6, bands
# Outlook: the same 10 loans, all UWM's; with no deep lender yet (under 100 loans), "as deep" is the ceiling itself.
ol = rows("outlook")
lad = {r["key"]: r for r in ol if r["view"] == "ladder"}
assert (lad["today"]["value"], lad["users"]["value"], lad["all_deep"]["value"], lad["all_full"]["value"]) == (0.3, 1.0, 1.0, 1.0), lad
uwm = next(r for r in ol if r["view"] == "lender" and r["id"] == "uwm")
assert (uwm["status"], uwm["loans"], uwm["vs4_share"], uwm["ceiling"], uwm["adds_deep"]) == ("using", 10, 0.3, 1.0, 0.7), uwm

# Outlook on planted tables, October 2026: A and B are deep (VS4 on 40 and 30 of 100 loans, ceilings of 50 each, so
# together they reach 70/100 = 0.7 of their ceilings); C uses VS4 lightly; D and E not at all. Shares are of 550 loans.
import duckdb  # noqa: E402

from gsescore import outlook  # noqa: E402

o = duckdb.connect()
o.execute("""CREATE TABLE scp (month DATE, upb DOUBLE, is_v BOOLEAN, seller_id VARCHAR, has_fico BOOLEAN, has_vs4 BOOLEAN,
             fb INT, vb INT, p_better DOUBLE, win_both BOOLEAN)""")
planted = {"a": (100, 40, 0.5), "b": (100, 30, 0.5), "c": (100, 2, 0.4), "d": (200, 0, 0.3), "e": (50, 0, 0.5)}
for sid, (n, v, c) in planted.items():  # A's first 30 loans carry both scores, VS4 a bucket better, all priced on VS4
    o.executemany("INSERT INTO scp VALUES (DATE '2026-10-01', 100000, ?, ?, true, ?, 5, ?, ?, true)",
                  [(i < v, sid, sid == "a" and i < 30, 6 if sid == "a" and i < 30 else None, c) for i in range(n)])
o.execute("""CREATE TABLE ls AS SELECT * FROM (VALUES ('a', DATE '2026-07-01', DATE '2026-07-10', true),
             ('a', DATE '2026-10-01', DATE '2026-10-02', true), ('b', DATE '2026-09-01', DATE '2026-09-15', true),
             ('c', DATE '2026-09-01', DATE '2026-09-20', true)) t(id, month, first_date, is_v)""")
o.execute("CREATE TABLE adopt_sm (id VARCHAR, month DATE, agency VARCHAR, n BIGINT, v BIGINT, u DOUBLE, vu DOUBLE)")
monthly_v = {"a": [(7, 10), (8, 30), (9, 40), (10, 40)], "b": [(8, 5), (9, 25), (10, 30)], "c": [(9, 1), (10, 2)],
             "d": [(9, 0), (10, 0)], "e": [(9, 0), (10, 0)]}
o.executemany("INSERT INTO adopt_sm VALUES (?, ?, 'All', ?, ?, ?, ?)",
              [(sid, date(2026, mo, 1), planted[sid][0], v, planted[sid][0] * 1e5, v * 1e5) for sid, ms in monthly_v.items() for mo, v in ms])
o.execute("""CREATE TABLE adopt_f AS SELECT * FROM (VALUES ('a', 'All', DATE '2026-07-01'), ('b', 'All', DATE '2026-08-01'),
             ('c', 'All', DATE '2026-09-01'), ('d', 'All', NULL::DATE), ('e', 'All', NULL::DATE)) t(id, agency, f_any)""")
o.execute("CREATE TABLE entity_names AS SELECT id, upper(id) AS short, NULL::VARCHAR AS ticker FROM (VALUES ('a'), ('b'), ('c'), ('d'), ('e')) t(id)")
o.execute("CREATE TABLE monthly AS SELECT DATE '2026-10-01' AS month, 'All' AS agency, 72 / 550 AS vs4_share, 72 / 550 AS vs4_upb_share, false AS final")
outlook.LENDER_TOP, outlook.NEXT_N = 3, 1
res = outlook.build_datasets(o, "2026-09-01")["outlook"]
by = lambda view: [r for r in res if r["view"] == view]  # noqa: E731
pr = by("params")[0]
assert (pr["q"], pr["deep_names"], pr["users"], pr["window_to"]) == (0.7, "A and B", 3, "2026-10-01") and abs(pr["pace"] - 1 / 6) < 1e-6, pr
lad = {r["key"]: r["value"] for r in by("ladder")}  # users: B to 0.35 and C to 0.28; next: D to 0.21; all: E to 0.35
for key, want in [("today", 72), ("users", 103), ("next", 145), ("all_deep", 162.5), ("all_full", 225)]:
    assert abs(lad[key] - want / 550) < 1e-6, (key, lad[key], want / 550)
# The path a deep lender follows: A's and B's VS4 loans over their ceilings in their first three months (B has no fourth).
assert [r["r"] for r in by("ramp") if r["id"] is None] == [0.15, 0.55, 0.7], by("ramp")
path = {(r["case"], r["month"]): r["value"] for r in by("path")}
# Users start next month: C at 0.4 x 0.15, then 0.4 x 0.55, then 0.28; B rises to 0.35 in the third month.
for month, want in [("2026-10-01", 72), ("2026-11-01", 76), ("2026-12-01", 92), ("2027-01-01", 103), ("2027-10-01", 103)]:
    assert abs(path[("users", month)] - want / 550) < 1e-6 and abs(path[("hold", month)] - 72 / 550) < 1e-6, (month, path)
# Pace: C's start in September was 100 of the 350 loans of sellers not yet using VS4, none of 250 in October: 1/6 a month.
# In November a sixth of D's and E's loans start, at 0.15 of their ceilings: 0.025 x (0.3 x 200 + 0.5 x 50) more.
assert abs(path[("pace", "2026-11-01")] - (76 + 2.125) / 550) < 1e-6, path
lenders = {r["id"]: r for r in by("lender")}
assert list(lenders) == ["d", "a", "b", "c", "other"], lenders  # the 3 largest, C as a user, E in the rest
assert abs(lenders["c"]["adds_deep"] - 26 / 550) < 1e-6 and lenders["c"]["status"] == "using" and lenders["d"]["next"], lenders
assert (lenders["a"]["status"], lenders["a"]["better_loans"], lenders["a"]["better_vs4"], lenders["a"]["both_share"]) == ("deep", 30, 1.0, 0.3), lenders
assert abs(sum(r["adds_deep"] for r in lenders.values()) - (162.5 - 72) / 550) < 1e-6, lenders

# Rate engine on planted data: rates are the sum of two factors' effects plus noise, and VS4 loans carry +25 bp.
import numpy as np  # noqa: E402

from gsescore import pricing  # noqa: E402

rng = np.random.default_rng(0)
a, b = rng.integers(0, 4, 4000), rng.integers(0, 3, 4000)
vs4 = rng.random(4000) < 0.2
y = 6 + np.array([0, 0.1, 0.2, 0.3])[a] + np.array([0, -0.05, 0.05])[b] + rng.normal(0, 0.01, 4000) + np.where(vs4, 0.25, 0)
mu, eff = pricing._fit(y, {"a": a, "b": b}, {"a": 4, "b": 3}, ~vs4)
premium = ((y - pricing._predict(mu, eff, {"a": a, "b": b})) * 100)[vs4].mean()
assert abs(premium - 25) < 1, premium
print("ok:", home)
