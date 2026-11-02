"""End-to-end check on synthetic files: ingest -> views -> score_model -> aggregates -> seller datasets -> as-of
-> score groups and borrower mix -> score choice and ceiling -> outlook, plus the outlook and the rate engine on
planted data, the public contract, the public build, the weekly report's warnings and what the page sources must not say.

Run: .venv/bin/python -I tests/test_pipeline.py
"""
import copy
import html
import io
import json
import os
import random
import re
import shutil
import subprocess
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
mix = {(r["dim"], r["cover"], r["grp"], r["bucket"]): r for r in rows("borrowers")}
assert mix[("gap", "both", "vs4", "20 to 39")]["share"] == 1.0 and mix[("gap", "both", "fico", "20 to 39")]["share"] == 1.0, mix
assert not any(k[1] == "vs4only" and k[2] == "vs4" for k in mix), "no VS4 loan lacks a Classic FICO from Oct 19"
# VS4 by GSE, all loans: 6 of 8 at Freddie. Expected from each seller's own FICO loans: Rocket (1 VS4) and UWM (4) all
# Freddie, Wells Fargo (2) 2 of 7 Freddie, Test Bank (1) all Fannie: (1 + 4 + 2 * 2/7) / 8 = 39/56.
fre = mix[("agency", "all", "vs4", "Freddie Mac")]
assert abs(fre["share"] - 0.75) < 1e-6 and abs(fre["expected"] - 39 / 56) < 1e-6, fre
prof = {(r["cover"], r["grp"]): r for r in rows("borrower_profile")}
assert (prof[("both", "vs4")]["loans"], prof[("both", "vs4")]["wa_fico"], prof[("both", "vs4")]["avg_gap"]) == (3, 745, 20), prof
assert rows("rates") == [] and not (home / "site" / "data" / "pricing.json").exists(), "too few FICO loans here to fit the rate model, and the old rate file is no longer written"

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
# Outlook: the same 10 loans, all UWM's; VS4 is better and higher on all of them. No heavy user yet (under 100 loans).
ol = rows("outlook")
lad = {(r["key"], r["rule"]): r for r in ol if r["view"] == "ladder"}
assert (lad[("today", None)]["value"], lad[("recent", None)]["value"], lad[("users", "higher")]["value"], lad[("all", "better")]["value"]) == (0.3, 0.3, 1.0, 1.0), lad
uwm = next(r for r in ol if r["view"] == "lender" and r["id"] == "uwm")
assert (uwm["status"], uwm["loans"], uwm["vs4_share"], uwm["higher_share"], uwm["adds_higher"], uwm["higher_vs4"]) == ("using", 10, 0.3, 1.0, 0.7, None), uwm
# Rules and score mix: the 20-point gap on those loans sits on the line; 3 of 10 priced on VS4.
wk = next(r for r in rows("rules") if r["view"] == "week" and r["scope"] == "uwm" and r["agency"] == "All")
assert (wk["week"], wk["loans"], wk["both_share"], wk["vs4_share"], wk["over20_loans"], wk["over20_share"], wk["under20_loans"]) == ("2026-10-19", 10, 1.0, 0.3, 10, 0.3, 0), wk
cur = {(r["cohort"], r["key"]): r for r in rows("rules") if r["view"] == "curve" and r["scope"] == "uwm"}
assert set(cur) == {("latest", "20_24")} and cur[("latest", "20_24")]["vs4_share"] == 0.3, cur
mx = {(r["view"], r["agency"]): r for r in rows("score_mix") if r["view"] in ("all", "recent")}
m = mx[("all", "All")]
assert (m["loans"], m["fico_only_share"], m["both_fico_share"], m["both_vs_share"], m["vs_only_share"], m["fico_share"], m["vs_share"], m["vs4_priced_share"]) == (10, 0.0, 0.7, 0.3, 0.0, 1.0, 1.0, 0.3), m
assert any(r["view"] == "month" and r["headline"] and r["start"] == "2026-07-01" for r in rows("score_mix")), "July is the only month with such records"
qs = {(r["start"], r["agency"]): r for r in rows("score_mix") if r["view"] == "quarter"}
assert (qs[("2026-07-01", "All")]["months"], qs[("2026-10-01", "All")]["complete"]) == (3, False), qs

# Lender stages: UWM's 10 loans all carry both scores, with VS4 20 points higher; 3 are priced on VS4. Too few to read a rule.
ls2 = rows("lender_stage")
st = next(r for r in ls2 if r["view"] == "lender" and r["id"] == "uwm")
assert (st["stage"], st["both_share"], st["uses_higher"], st["rule"], st["kind"], st["lead"]) == ("both", 1.0, None, None, "Nonbank", "Retail"), st
stg = {r["key"]: r for r in ls2 if r["view"] == "stage"}
assert set(stg) == {"both"} and (stg["both"]["lenders"], stg["both"]["share"], stg["both"]["vs4_share"]) == (1, 1.0, 0.3), stg
assert rows("statements") and all(r["url"].startswith("https://") and r["statement"] and r["date"] for r in rows("statements")), "every statement has a date and a link"

# Fees on the same loans carry through the build (planted answers below).
mk = next(r for r in rows("fees") if r["view"] == "market" and r["key"] == "All")
assert mk["priced_loans"] == 3, mk
from gsescore.fee_grid import load_grid  # noqa: E402

g = load_grid()
assert (g[("purchase", 8, 4)], g[("purchase", 4, 5)], g[("cash_out", 0, 4)], g[("rate_term", 2, 5)], len(g)) == (0.375, 1.5, 5.125, 3.0, 9 * 9 + 9 * 9 + 9 * 5), g

# Outlook on planted tables, October 2026: VS4 on 40, 30, 2, 0 and 0 loans of 100, 100, 100, 200 and 50 (550). VS4 saves a fee
# on 50%, 50%, 40%, 30% and 50% of them and is higher on 70%, 60%, 60%, 60% and 80%. A's latest two weeks show 30 of 60 on VS4;
# B's show too few to count. A and B are heavy (VS4 at half or more of the fee-saving share), C is a light user, D stopped in April.
import duckdb  # noqa: E402

from gsescore import outlook  # noqa: E402

o = duckdb.connect()
o.execute("""CREATE TABLE scp (month DATE, upb DOUBLE, is_v BOOLEAN, seller_id VARCHAR, has_fico BOOLEAN, has_vs4 BOOLEAN,
             fb INT, vb INT, fico INT, vs INT, p_better DOUBLE, p_higher DOUBLE, p_nw DOUBLE, win_both BOOLEAN)""")
planted = {"a": (100, 40, 0.5, 0.7), "b": (100, 30, 0.5, 0.6), "c": (100, 2, 0.4, 0.6), "d": (200, 0, 0.3, 0.6), "e": (50, 0, 0.5, 0.8)}
for sid, (n, v, c, hi) in planted.items():  # A's first 30 loans carry both scores, VS4 a bucket better and higher, all priced on VS4
    o.executemany("INSERT INTO scp VALUES (DATE '2026-10-01', 100000, ?, ?, true, ?, 5, ?, 700, ?, ?, ?, 0.9, true)",
                  [(i < v, sid, sid == "a" and i < 30, 6 if sid == "a" and i < 30 else None, 720 if sid == "a" and i < 30 else None, c, hi) for i in range(n)])
o.execute("CREATE TABLE scw (seller_id VARCHAR, week DATE, is_v BOOLEAN, upb DOUBLE)")
o.executemany("INSERT INTO scw VALUES ('a', DATE '2026-10-26', ?, 100000)", [(i < 30,) for i in range(60)])
o.executemany("INSERT INTO scw VALUES ('b', DATE '2026-10-26', ?, 100000)", [(i < 9,) for i in range(10)])
o.execute("""CREATE TABLE ls AS SELECT * FROM (VALUES ('a', DATE '2026-07-01', DATE '2026-07-10', true),
             ('a', DATE '2026-10-01', DATE '2026-10-02', true), ('b', DATE '2026-09-01', DATE '2026-09-15', true),
             ('c', DATE '2026-09-01', DATE '2026-09-20', true), ('d', DATE '2026-04-01', NULL, true)) t(id, month, first_date, is_v)""")
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
assert (pr["heavy_names"], pr["users"], pr["window_to"], pr["recent_from"]) == ("A and B", 3, "2026-10-01", "2026-10-19") and abs(pr["pace"] - 1 / 6) < 1e-6, pr
lad = {(r["key"], r["rule"]): r["value"] for r in by("ladder")}
for key, want in [(("today", None), 72), (("recent", None), 82), (("not_worse", None), 495), (("heavy", "higher"), 132), (("users", "higher"), 190), (("next", "higher"), 310),
                  (("all", "higher"), 350), (("heavy", "better"), 102), (("users", "better"), 140), (("next", "better"), 200), (("all", "better"), 225)]:
    assert abs(lad[key] - want / 550) < 1e-6, (key, lad[key], want / 550)
# How fast the heavy users moved: VS4 loans over loans at their latest share (A 0.5, B 0.3), first three months (B has no fourth).
assert [r["r"] for r in by("ramp") if r["id"] is None] == [0.1875, 0.6875, 0.875], by("ramp")
path = {(r["case"], r["rule"], r["month"]): r["value"] for r in by("path")}
for case, month, want in [("recent", "2026-10-01", 72), ("recent", "2026-11-01", 82), ("heavy", "2026-11-01", 82 + 0.1875 * 50), ("users", "2026-11-01", 82 + 0.1875 * 108),
                          ("heavy", "2027-10-01", 132), ("users", "2027-10-01", 190)]:
    assert abs(path[(case, "higher", month)] - want / 550) < 1e-6, (case, month, path[(case, "higher", month)], want / 550)
# Pace: C's start in September was 100 of the 350 loans of sellers not yet using VS4, none of 250 in October: 1/6 a month.
# In November a sixth of D's and E's loans start, 0.1875 of the way to their shares on the rule: 0.03125 x (120 + 40) more.
assert abs(path[("pace", "higher", "2026-11-01")] - (82 + 0.1875 * 108 + 5) / 550) < 1e-6, path
lenders = {r["id"]: r for r in by("lender")}
assert list(lenders) == ["d", "a", "b", "c", "other"], lenders  # the 3 largest, C as a user, E in the rest
assert abs(lenders["c"]["adds_higher"] - 58 / 550) < 1e-6 and lenders["c"]["status"] == "using" and lenders["d"]["next"], lenders
assert (lenders["a"]["status"], lenders["a"]["recent_share"], lenders["a"]["better_loans"], lenders["a"]["better_vs4"], lenders["a"]["higher_vs4"], lenders["a"]["both_share"]) == ("heavy", 0.5, 30, 1.0, 1.0, 0.3), lenders
assert abs(sum(r["adds_higher"] for r in lenders.values()) - (350 - 82) / 550) < 1e-6, lenders
assert lenders["d"]["status"] == "stopped" and lenders["b"]["status"] == "heavy", lenders  # D's one VS4 loan was in April

# Ceiling on planted loans, one GSE. October's records carry every score: R has 100 loans with both scores in Classic FICO
# bucket 700-719, 50 with VS4 a bucket better (30 priced on VS4) and 50 in the same bucket (10 on VS4); N has 100 with only a
# Classic FICO, taking R's 50/100 rate. September's show one score: R 100 (30 on VS4), N 100 (none), M 40 (10), M absent in October.
c2 = duckdb.connect()
c2.execute("CREATE MACRO seller_key(x) AS x")
c2.execute("CREATE TABLE seller_map AS SELECT * FROM (VALUES ('R', 'r'), ('N', 'n'), ('M', 'm')) t(key, id)")
c2.execute("CREATE TABLE entity_names AS SELECT id, upper(id) AS short FROM seller_map")
c2.execute("""CREATE TABLE monthly AS SELECT *, 100 AS scored_loans, 1000000.0 AS scored_upb, 10 AS vs4_loans, 100000.0 AS vs4_upb FROM (VALUES (DATE '2026-09-01', 'All', true),
              (DATE '2026-09-01', 'FHLMC', true), (DATE '2026-10-01', 'All', false), (DATE '2026-10-01', 'FHLMC', false)) t(month, agency, final)""")
c2.execute("""CREATE TABLE loans (agency VARCHAR, issue_month DATE, upb DOUBLE, score_model VARCHAR, seller VARCHAR, purpose VARCHAR,
              channel VARCHAR, classic_fico INT, vs4 INT, pricing_indicator VARCHAR, first_intraday_date DATE, ltv INT, mi_pct DOUBLE, special_program VARCHAR)""")
planted_loans = [("2026-10-01", "R", "V", 700, 720, 30), ("2026-10-01", "R", "C", 700, 720, 20), ("2026-10-01", "R", "V", 700, 705, 10),
                 ("2026-10-01", "R", "C", 700, 705, 40), ("2026-10-01", "N", "C", 700, None, 100), ("2026-09-01", "R", "V", None, 720, 30),
                 ("2026-09-01", "R", "C", 700, None, 70), ("2026-09-01", "N", "C", 700, None, 100), ("2026-09-01", "M", "V", None, 720, 10),
                 ("2026-09-01", "M", "C", 700, None, 30)]
c2.executemany("INSERT INTO loans VALUES ('FHLMC', ?, 100000, ?, ?, 'P', 'R', ?, ?, ?, '2026-10-20', 80, 0, '7')",
               [(day, model, seller, fico, vs, model if day == "2026-10-01" else None)
                for day, seller, model, fico, vs, k in planted_loans for _ in range(k)])
from gsescore.aggregate import _rows  # noqa: E402

built2 = gsescore.scores.build_datasets(c2, "true", "2026-09-01", _rows)
ceil2 = built2["ceiling"]
months = {r["start"]: r for r in ceil2 if r["view"] == "month" and r["agency"] == "All"}
assert (months["2026-10-01"]["loans"], months["2026-10-01"]["actual"], months["2026-10-01"]["better"], months["2026-10-01"]["estimated"]) == (200, 0.2, 0.5, False), months
# September: R takes its own October rate on every loan (50 of 100), N the rate for its bucket (50), and M, with no October
# records, the rate over October's VS4-priced loans on its VS4 loans (30 of 40) and the bucket's on the rest: 7.5 + 15.
# Counting every VS4 loan as better would read 140 of 240.
sep = months["2026-09-01"]
assert sep["loans"] == 240 and sep["estimated"] is True and abs(sep["better"] - 122.5 / 240) < 1e-6 and abs(sep["actual"] - 40 / 240) < 1e-6, sep
assert (months["2026-10-01"]["higher"], sep["higher"]) == (1.0, 1.0), months  # VS4's score is above FICO on all R's loans
mix2 = next(r for r in built2["score_mix"] if r["view"] == "month" and r["agency"] == "All" and r["start"] == "2026-10-01")
assert (mix2["headline"], mix2["fico_only_share"], mix2["both_fico_share"], mix2["both_vs_share"], mix2["vs_only_share"], mix2["vs_share"]) == (True, 0.5, 0.3, 0.2, 0.0, 0.5), mix2
curve2 = {(r["key"]): r["vs4_share"] for r in built2["rules"] if r["view"] == "curve" and r["scope"] == "r"}
assert curve2 == {"5_9": 0.2, "20_24": 0.6}, curve2  # R's rule in points: 10 of 50 at 5 points, 30 of 50 at 20
bands2 = {r["key"]: r for r in ceil2 if r["view"] == "band"}  # October's every-score loans only, with the same total
assert (bands2["all"]["loans"], bands2["all"]["better"], bands2["4"]["loans"], bands2["4"]["adds_better"]) == (200, 0.5, 200, 0.5), bands2
# A seller's rule hides cells under MIN_N loans but keeps its total: R's two cells hold 50 loans each.
gsescore.scores.MIN_N = 60
rule2 = [r for r in gsescore.scores.build_datasets(c2, "true", "2026-09-01", _rows)["choice"] if r["view"] == "rule" and r["agency"] == "All"]
assert {r["scope"] for r in rule2} == {"All"} and {r["scope_loans"] for r in rule2} == {100}, rule2
gsescore.scores.MIN_N = 1
assert {(r["key"], r["scope_loans"]) for r in gsescore.scores.build_datasets(c2, "true", "2026-09-01", _rows)["choice"]
        if r["view"] == "rule" and r["scope"] == "r"} == {("0", 100), ("1", 100)}

# Fees on planted loans: $100,000 purchases at 80 LTV, FICO 700 (fee 1.375%), VS4 720 (1.25%) or 705 (same bucket). R has 20 priced
# on VS4 a bucket better, which save $125 each, 20 priced on VS4 in the same bucket, and 20 priced on FICO though VS4 was better. N has
# 80 with only a Classic FICO and 20 in a waived program, M has 20 with only VS4, and one FICO-priced 15-year loan is left out.
# A new month joins the series once the files reach the 15th of it or its month-end file is in, whatever the calendar says.
from gsescore.aggregate import series_end  # noqa: E402

c4 = duckdb.connect()
c4.execute("CREATE TABLE loans (first_intraday_date DATE)")
c4.execute("CREATE TABLE loan_records (kind VARCHAR, file_date DATE)")
for through, monthend, want in (("2026-10-14", None, "2026-09-01"), ("2026-10-15", None, "2026-10-01"), ("2026-10-27", "2026-09-01", "2026-10-01"), ("2026-10-03", "2026-08-01", "2026-09-01"), ("2026-10-03", "2026-10-01", "2026-10-01")):
    c4.execute("DELETE FROM loans")
    c4.execute("DELETE FROM loan_records")
    c4.execute("INSERT INTO loans VALUES (?)", [through])
    if monthend:
        c4.execute("INSERT INTO loan_records VALUES ('monthend', ?)", [monthend])
    assert series_end(c4).isoformat() == want, (through, monthend, series_end(c4))

from gsescore import fees  # noqa: E402

c3 = duckdb.connect()
c3.execute("CREATE MACRO seller_key(x) AS x")
c3.execute("CREATE TABLE seller_map AS SELECT * FROM (VALUES ('R', 'r'), ('N', 'n'), ('M', 'm')) t(key, id)")
c3.execute("CREATE TABLE entity_names AS SELECT id, upper(id) AS short, NULL::VARCHAR AS ticker FROM seller_map")
c3.execute("""CREATE TABLE monthly AS SELECT * FROM (VALUES ('All', true, 1000000.0), ('All', true, 1000000.0), ('All', false, 5.0),
              ('FHLMC', true, 1000000.0), ('FHLMC', true, 1000000.0)) t(agency, final, scored_upb)""")
c3.execute("""CREATE TABLE loans (agency VARCHAR, issue_month DATE, upb DOUBLE, score_model VARCHAR, seller VARCHAR, purpose VARCHAR, classic_fico INT,
              vs4 INT, pricing_indicator VARCHAR, ltv INT, loan_term INT, special_program VARCHAR, fannie_score INT, freddie_score INT, first_intraday_date DATE)""")
planted_fees = [("R", "V", 700, 720, 360, "7", 730, 20), ("R", "V", 700, 705, 360, "7", 700, 20), ("R", "C", 700, 720, 360, "7", 720, 20),
                ("N", "C", 700, None, 360, "7", None, 80), ("N", "C", 700, 720, 360, "H", 710, 20), ("M", "V", None, 720, 360, "7", None, 20),
                ("N", "C", 700, 720, 180, "7", None, 1)]
c3.executemany("INSERT INTO loans VALUES ('FHLMC', '2026-10-01', 100000, ?, ?, 'P', ?, ?, ?, 80, ?, ?, NULL, ?, '2026-10-20')",
               [(model, seller, fico, vs, model, term, program, gse) for seller, model, fico, vs, term, program, gse, k in planted_fees for _ in range(k)])
fee = fees.build_datasets(c3, "2026-10-01")["fees"]
fm = next(r for r in fee if r["view"] == "market" and r["key"] == "All")
assert (fm["loans"], fm["vs4_loans"], fm["priced_loans"], fm["saving_share"], fm["saved_bp"], fm["saving_avg_usd"]) == (180, 60, 40, 0.5, 6.25, 125.0), fm
assert (fm["taken_usd"], fm["taken_all_usd"], fm["left_loans"], fm["left_usd"], fm["one_loans"]) == (2500.0, 3750.0, 20, 2500.0, 80), fm
# Estimated: the rate of saving over R's 60 unwaived loans with both scores (40 of them at 0.125%), on 80 loans.
assert abs(fm["est_usd"] - 80 * 1000 / 12) < 1 and abs(fm["option_usd"] - (3750 + 2500 + 80 * 1000 / 12)) < 1, fm
assert abs(fm["option_bp"] - fm["option_usd"] / 18e6 * 1e4) < 1e-3, fm
assert fm["annual_upb"] == 12e6 and fm["taken_annual_usd"] == 2500 and abs(fm["option_annual_usd"] - fm["option_usd"] * 2 / 3) < 1, fm
fl = {r["id"]: r for r in fee if r["view"] == "lender"}
assert [fl[x]["rank"] for x in "nrm"] == [1, 2, 3], fl
assert (fl["r"]["taken_usd"], fl["r"]["left_usd"], fl["r"]["est_usd"], fl["n"]["priced_loans"], fl["n"]["left_usd"], fl["m"]["vs4_loans"], fl["m"]["priced_loans"]) == (2500.0, 2500.0, 0.0, 0, 0.0, 20, 0), fl
# The GSE's own score: R's VS4-priced loans in the 700-719 bucket read 700 against 720 for FICO-priced loans there; at the same FICO, a better VS4 reads (730 + 720 + 710) / 3 against 700.
assert {(r["scope"], r["key"], r["loans"], r["diff"]) for r in fee if r["view"] == "gse"} == {("All", "b", 20, -20.0), ("r", "b", 20, -20.0)}, fee
assert [(r["key"], r["loans"], r["diff"]) for r in fee if r["view"] == "lift"] == [("b", 60, 20.0)], fee

# What lenders pick, on the same loans with both scores: 40 where VS4's fee is lower, half priced on it; 20 at the same fee with VS4 5 points higher, all priced on it;
# 20 waived, so the same fee, with VS4 20 points higher, all on FICO. The fee on all 80: 103.125 bp on FICO, 96.875 on VS4 or the lower of the two, 100 as priced.
pick = {(r["scope"], r["key"]): r for r in fee if r["view"] == "choice" and r["cohort"] == "all"}
assert (pick[("All", "lower|up20")]["loans"], pick[("All", "lower|up20")]["vs4_share"], pick[("All", "same|up1")]["vs4_share"], pick[("All", "same|up20")]["vs4_share"], pick[("All", "same|all")]["vs4_share"], pick[("r", "lower|all")]["vs4_share"]) == (40, 0.5, 1.0, 0.0, 0.5, 0.5), pick
opt = next(r for r in fee if r["view"] == "option" and r["scope"] == "All")
assert (opt["loans"], opt["fee_fico_bp"], opt["fee_vs_bp"], opt["fee_best_bp"], opt["fee_actual_bp"], opt["lower_share"], opt["same_share"], opt["higher_share"]) == (80, 103.125, 96.875, 96.875, 100.0, 0.5, 0.5, 0.0), opt

# A steady mix on planted weeks: S has 100 loans a week, 50 then 100 carrying VS4. T has 5 then 195, with 39 carrying in the second week, so in the first it takes its rate over all weeks, 39 of 200.
from gsescore import scores as scores_mod  # noqa: E402

c6 = duckdb.connect()
c6.execute("CREATE TABLE scw (agency VARCHAR, week DATE, is_v BOOLEAN, seller_id VARCHAR, has_fico BOOLEAN, has_vs4 BOOLEAN)")
c6.executemany("INSERT INTO scw VALUES ('FNMA', ?, ?, ?, true, ?)", [("2026-10-05", i < 10, "s", i < 50) for i in range(100)] + [("2026-10-12", i < 20, "s", True) for i in range(100)]
               + [("2026-10-05", False, "t", False) for _ in range(5)] + [("2026-10-12", False, "t", i < 39) for i in range(195)])
stead = scores_mod._steady(c6)
assert stead[("All", "2026-10-05")] == (round(0.5 * 0.5 + 0.5 * 0.195, 6), round(0.5 * 0.1, 6)) and stead[("FNMA", "2026-10-12")] == (round(0.5 * 1 + 0.5 * 0.2, 6), round(0.5 * 0.2, 6)), stead

# The closing month on planted loans, data through Oct 15 (15 of 31 days). Jan closings, the reference: S's 400 reach issue months Feb and Mar 300 and 100, T's 100 and 300. Aug closings, issued Sep: S 100 with 40 on VS4,
# T 100 with none. Sep closings (first payment Nov), issued Oct: S 50 with 25 on VS4, all in records that show every score (10 FICO only, 15 both on FICO, 20 both on VS4, 5 VS4 only); T 10 on FICO, too few to count, so it keeps Aug's rate.
# Weights from loans issued Mar to Sep: S 100 + 100, T 300 + 100, so 1/3 and 2/3.
from gsescore import closing  # noqa: E402

c7 = duckdb.connect()
c7.execute("CREATE MACRO seller_key(x) AS x")
c7.execute("CREATE TABLE seller_map AS SELECT * FROM (VALUES ('S', 's'), ('T', 't')) t(key, id)")
c7.execute("CREATE TABLE loans (agency VARCHAR, seller VARCHAR, score_model VARCHAR, pricing_indicator VARCHAR, classic_fico INT, vs4 INT, first_pay_date DATE, issue_month DATE, first_intraday_date DATE)")
def plant7(seller, n, model, indicator, fico, vs, first_pay, issue):
    c7.executemany("INSERT INTO loans VALUES ('FNMA', ?, ?, ?, ?, ?, ?, ?, DATE '2026-10-15')", [(seller, model, indicator, fico, vs, first_pay, issue)] * n)
for seller, feb, mar in (("S", 300, 100), ("T", 100, 300)):
    plant7(seller, feb, "C", None, 700, None, "2026-03-01", "2026-02-01")
    plant7(seller, mar, "C", None, 700, None, "2026-03-01", "2026-03-01")
plant7("S", 40, "V", None, None, 720, "2026-10-01", "2026-09-01")
plant7("S", 60, "C", None, 700, None, "2026-10-01", "2026-09-01")
plant7("T", 100, "C", None, 700, None, "2026-10-01", "2026-09-01")
plant7("S", 10, "C", "C", 700, 9999, "2026-11-01", "2026-10-01")
plant7("S", 15, "C", "C", 700, 720, "2026-11-01", "2026-10-01")
plant7("S", 20, "V", "V", 700, 720, "2026-11-01", "2026-10-01")
plant7("S", 5, "V", "V", 9999, 720, "2026-11-01", "2026-10-01")
plant7("T", 10, "C", None, 700, None, "2026-11-01", "2026-10-01")
cl7 = closing.build_datasets(c7, [{"view": "lender", "id": "s"}])["closing"]
assert c7.execute(f"SELECT {closing.closing_month('DATE ' + chr(39) + '2026-11-01' + chr(39))}").fetchone()[0] == date(2026, 9, 1)
m7 = {(r["agency"], r["start"]): r for r in cl7 if r["view"] == "market"}
part = 15 / 31
sep7, aug7 = m7[("All", "2026-09-01")], m7[("FNMA", "2026-08-01")]
assert aug7["n"] == 200 and aug7["delivered"] == 0.2 and abs(aug7["priced"] - 0.4 / 3) < 1e-5 and aug7["every_share"] == 0.0, aug7
assert abs(aug7["arrived"] - ((0.75 + part * 0.25) / 3 + (0.25 + part * 0.75) * 2 / 3)) < 1e-5, aug7
assert sep7["n"] == 60 and abs(sep7["delivered"] - 25 / 60) < 1e-5 and abs(sep7["priced"] - 0.5 / 3) < 1e-5 and abs(sep7["every_share"] - 50 / 60) < 1e-5, sep7  # T keeps Aug's 0%, it has too few loans in Sep
assert abs(sep7["fico_only"] - (0.2 / 3 + 2 / 3)) < 1e-5 and abs(sep7["both_fico"] - 0.1) < 1e-5 and abs(sep7["both_vs"] - 0.4 / 3) < 1e-5 and abs(sep7["vs_only"] - 0.1 / 3) < 1e-5, sep7  # T shows nothing else, so it counts as FICO only
assert abs(sep7["arrived"] - (part * 0.75 / 3 + part * 0.25 * 2 / 3)) < 1e-5, sep7
s7 = next(r for r in cl7 if r["view"] == "lender" and r["id"] == "s" and r["agency"] == "All" and r["start"] == "2026-09-01")
assert (s7["n"], s7["v"], s7["every"], s7["fo"], s7["bf"], s7["bv"], s7["vo"]) == (50, 25, 50, 10, 15, 20, 5) and abs(s7["arrived"] - part * 0.75) < 1e-5, s7
assert not any(r["view"] == "lender" and r["id"] == "t" for r in cl7), "only listed lenders get rows"

# The weekly note on planted loans. R goes from 10 of 100 to 30 of 100 priced on VS4, all with both scores and VS4 5 points higher. N, all at
# Fannie Mae like R, goes from 50 with only a Classic FICO to 50 with both. The files stop on Oct 14, so the second week is partial.
from gsescore import notes  # noqa: E402

c4 = duckdb.connect()
c4.execute("CREATE MACRO seller_key(x) AS x")
c4.execute("CREATE TABLE seller_map AS SELECT * FROM (VALUES ('R', 'r'), ('N', 'n')) t(key, id)")
c4.execute("CREATE TABLE entity_names AS SELECT id, upper(id) AS short, upper(id) AS name, NULL::VARCHAR AS ticker FROM seller_map")
c4.execute("CREATE TABLE loans AS SELECT * FROM (VALUES ('R', 'V', DATE '2026-10-06', DATE '2026-10-01'), ('N', 'C', DATE '2026-10-14', DATE '2026-10-01')) t(seller, score_model, first_intraday_date, issue_month)")
c4.execute("""CREATE TABLE scw (agency VARCHAR, week DATE, is_v BOOLEAN, seller_id VARCHAR, has_fico BOOLEAN, has_vs4 BOOLEAN, gap INT, upb DOUBLE DEFAULT 100000,
              channel VARCHAR DEFAULT 'R', fico INT DEFAULT 700, ltv INT DEFAULT 80, purpose VARCHAR DEFAULT 'P', mi BOOLEAN DEFAULT false, program VARCHAR DEFAULT '7', month DATE DEFAULT DATE '2026-10-01')""")
for wk, v in (("2026-10-05", 10), ("2026-10-12", 30)):
    c4.executemany("INSERT INTO scw (agency, week, is_v, seller_id, has_fico, has_vs4, gap) VALUES ('FNMA', ?, ?, 'r', true, true, 5)", [(wk, i < v) for i in range(100)])
c4.executemany("INSERT INTO scw (agency, week, is_v, seller_id, has_fico, has_vs4, gap) VALUES ('FNMA', ?, false, 'n', true, ?, ?)", [("2026-10-05", False, None)] * 50 + [("2026-10-12", True, 0)] * 50)
said = [{"date": "2026-10-13", "who": "Z", "statement": "Said something.", "source": "Paper", "url": "https://example.com/z"}, {"date": "2026-01-01", "who": "Y", "statement": "Too old.", "source": None, "url": None}]
wn = notes.build_datasets(c4, said)["week_note"]
wk = {r["week"]: r for r in wn if r["view"] == "week"}
assert (wk["2026-10-05"]["partial"], wk["2026-10-05"]["latest"], wk["2026-10-12"]["partial"], wk["2026-10-12"]["latest"], wk["2026-10-12"]["label"]) == (False, True, True, False, "Oct 12 to Oct 14"), wk
lines = {r["kind"]: r for r in wn if r["view"] == "line" and r["week"] == "2026-10-12"}
mix_text = next(r["text"] for r in wn if r["view"] == "line" and r["week"] == "2026-10-12" and r["order"] == 0)
assert mix_text == "150 loans first disclosed Oct 12 to Oct 14, so far: priced on VS4 20.0% (6.7% the week before), both scores show on 100.0% (66.7% the week before), only VS4 shows on 0.0% (0.0% the week before).", mix_text
assert lines["movers"]["text"] == "VS4 share moved most at R 10.0% to 30.0%.", lines
assert lines["both"]["text"] == "Both scores at Fannie Mae moved most at N 0.0% to 100.0%.", lines
assert lines["rule"]["text"] == "Use of VS4 with its score 1 to 19 points above FICO moved at R 10.0% to 30.0%.", lines
assert not any(r["kind"] == "rate" for r in wn if r["view"] == "line"), wn  # the note's rate line is withdrawn
assert (lines["said"]["text"], lines["said"]["url"]) == ("Z: Said something.", "https://example.com/z") and "start" not in lines, lines
assert any(r["kind"] == "start" and r["text"] == "First VS4 loan: R." for r in wn if r["view"] == "line" and r["week"] == "2026-10-05"), wn
assert not any("Too old" in (r["text"] or "") for r in wn if r["view"] == "line"), wn
# Each lender's split of its loans, overall and at each GSE.
from gsescore import why  # noqa: E402

ls4 = {r["id"]: r for r in why.build_datasets(c4, "2026-12-01")["lender_stage"] if r["view"] == "lender"}
assert (ls4["r"]["mix_fico_only"], ls4["r"]["mix_both_fico"], ls4["r"]["mix_both_vs"], ls4["r"]["mix_vs_only"], ls4["r"]["fnma_both_vs"], ls4["r"]["fhlmc_both_vs"]) == (0.0, 0.8, 0.2, 0.0, 0.2, None), ls4["r"]
assert (ls4["n"]["mix_fico_only"], ls4["n"]["mix_both_fico"], ls4["n"]["fnma_fico_only"], ls4["n"]["fhlmc_loans"]) == (0.5, 0.5, 0.5, 0), ls4["n"]
split4_rows = why.build_datasets(c4, "2026-12-01")["lender_mix"]
assert split4_rows and not [r for r in why.build_datasets(c4, "2026-01-01")["lender_mix"] if r["view"] == "month"]  # months past the series end stay out
split4 = {(r["id"], r["agency"], r["start"]): r for r in split4_rows if r["view"] == "week"}
assert (split4[("r", "All", "2026-10-12")]["n"], split4[("r", "All", "2026-10-12")]["bv"], split4[("r", "FNMA", "2026-10-12")]["bf"], split4[("n", "All", "2026-10-05")]["fo"], split4[("n", "All", "2026-10-12")]["bf"]) == (100, 30, 70, 50, 50), split4

# The exposure inputs and the workbook, on the pipeline's own build. Every formula's stored value is what the formula gives.
import re  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

from gsescore.export import build_workbook  # noqa: E402

ass = {r["key"]: r for r in rows("assumptions")}
assert (ass["price_per_score"]["kind"], ass["bureaus"]["kind"], ass["gse_loans_year"]["kind"]) == ("source", "judgment", "data"), ass
planted_inputs = [{**r, "value": {"gse_loans_year": 1e6, "borrowers_per_loan": 1.5}.get(r["key"], r["value"])} for r in ass.values() if r["key"] != "no_fico_all"]
planted_inputs = [r for r in planted_inputs if r["key"] != "no_fico_fnma"] + [{**ass["gse_loans_year"], "key": "no_fico_fnma", "value": 0.01}]
(home / "site" / "data" / "assumptions.json").write_text(json.dumps({"rows": planted_inputs}))
assert all(r["url"].startswith("https://") for r in ass.values() if r["kind"] == "source"), ass
ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
values, formulas = {}, {}
with zipfile.ZipFile(build_workbook()) as z:
    names = [e.get("name") for e in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", ns)]
    assert names[:3] == ["Read me", "FICO exposure", "Your scenario"], names
    for i, name in enumerate(names):
        for c in ET.fromstring(z.read(f"xl/worksheets/sheet{i + 1}.xml")).iter(f"{{{ns['m']}}}c"):
            v, f = c.find("m:v", ns), c.find("m:f", ns)
            if v is not None and c.get("t") not in ("s", "str"):
                values[(name, c.get("r"))] = float(v.text)
            if f is not None:
                formulas[(name, c.get("r"))] = (f.text, c.get("t"), v.text if v is not None else None)


def sheet_eval(sheet, text):
    cell = lambda sh, ref: values.get((sh, ref), 0.0)  # noqa: E731
    span = lambda sh, col, lo, hi: [cell(sh, f"{col}{n}") for n in range(lo, hi + 1)]  # noqa: E731
    text = re.sub(r"^IF\((.+?>0),(.+),(\"n/a\")\)$", r"(\2 if \1 else \3)", text)  # the workbook's one IF, which guards a division
    py = re.sub(r"'([^']+)'!\$?([A-Z]+)\$?(\d+)", lambda m: f"cell({m[1]!r}, '{m[2]}{m[3]}')", text)
    py = re.sub(r"\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)", lambda m: f"span({sheet!r}, '{m[1]}', {m[2]}, {m[4]})", py)
    py = re.sub(r"(?<![\w'])\$?([A-Z]+)\$?(\d+)(?![\w'(])", lambda m: f"cell({sheet!r}, '{m[1]}{m[2]}')", py)
    return eval(py, {"cell": cell, "span": span, "MAX": max, "SUM": sum, "SUMPRODUCT": lambda a, b: sum(x * y for x, y in zip(a, b))})


assert len(formulas) >= 15, formulas
for (sheet, ref), (text, kind, stored) in formulas.items():
    got = sheet_eval(sheet, text)
    assert (kind == "str" and got == stored) or abs(got - float(stored)) < 1e-6, (sheet, ref, text, got, stored)
by_label = {}
with zipfile.ZipFile(build_workbook()) as z:
    strings = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    for c in ET.fromstring(z.read("xl/worksheets/sheet2.xml")).iter(f"{{{ns['m']}}}c"):
        if c.get("t") == "s" and c.get("r").startswith("A"):
            by_label[strings[int(c.find("m:v", ns).text)]] = values.get(("FICO exposure", "B" + c.get("r")[1:]))
# 3 bureaus x 1.5 borrowers x (4 pulls x $10): $180 a funded loan, on a million loans less the 1% with no Classic FICO.
assert abs(by_label["FICO's revenue per funded loan, today ($)"] - 180) < 1e-6 and abs(by_label["FICO's revenue on GSE loans, today ($m)"] - 178.2) < 1e-6, by_label
assert abs(by_label["A lender's saving per funded loan if it drops FICO ($)"] - 162) < 1e-6 and abs(by_label["Each point of GSE loans with no FICO ($m a year)"] - 1.8) < 1e-6, by_label
# The withdrawn labels stay out of the workbook, and the calculator reads the total of the column its name says. A statement is someone's own words, so it may say anything.
from gsescore.export import SCENARIO_NO_FICO  # noqa: E402

STATEMENTS = [r["statement"] for r in rows("statements")]
WORKBOOK_GONE = ("eaches the rate", "No FICO today", "Your no FICO", "Missed", "Potential", "Left", "Estimated", "Fees left", "Fees estimated", "saves a fee", "Saves a fee", "Standard error", "model's miss", "against the FICO model", "taken to match", "unchecked", "being rebuilt", "replacement comes next", "Shows in the rate", "single-grid", "no sign of", "Used VS4", "20-point line", "pick is worth", "Better VS4", "Blank under 100 VS4", "score has priced like")


def workbook_says(found):
    return [(label, t[:80]) for t in found if not any(said in t for said in STATEMENTS) for label in WORKBOOK_GONE if label in t.replace("Left out", "").replace("Left it the same", "")]  # a head on a limit and the old rule's words, not the old column


assert not workbook_says(strings), workbook_says(strings)
assert {"Shows no FICO, at most", "Lender drops FICO (your assumption)", "Of those, lower LLPA on VS4", "Saved, net, on all of those (bp of balance)", "Saved per loan with a lower LLPA ($)", "What the pick saves in LLPAs: the upfront fee as bp of balance"} <= set(strings), strings[:40]
assert {"Blue: inputs to change. Black: figures from the data, and formulas. Green: links to another sheet. Yellow fill: judgment calls these files cannot test.", "Cost or rate: what lenders pick when they hold both scores, by what VS4 would do to the fee, and what the pick saves in LLPAs."} <= set(strings), "the Read me's colours and what Cost or rate holds"
assert any(t.endswith("A year's figures scale the month's to the GSE's balance, an estimate from one part month.") for t in strings), "the year's figures are an estimate"
assert "Rates" not in names and not any("How the rate differs by LLPA" in t for t in strings) and "Same FICO: estimate" in strings, names  # too few loans here for a rate read: no sheet and no LLPA table, and the Lenders columns stay, blank
assert any(t.startswith("Rates: how a VS4 loan's note rate compares") for t in strings) and any(t.startswith("Lenders:") and "rate figures" in t for t in strings) and any(t.startswith("The Rates sheet is a like-for-like comparison, not a test of cause.") for t in strings), "the Read me says what the sheet is"
with zipfile.ZipFile(build_workbook()) as z:
    scenario_at = {strings[int(c.find("m:v", ns).text)]: c.get("r") for c in ET.fromstring(z.read("xl/worksheets/sheet3.xml")).iter(f"{{{ns['m']}}}c") if c.get("t") == "s"}
assert SCENARIO_NO_FICO == f"'Your scenario'!{scenario_at['Lender drops FICO (your assumption)'][0]}4", (SCENARIO_NO_FICO, scenario_at)
assert any(text == SCENARIO_NO_FICO for (sheet, _), (text, *_) in formulas.items() if sheet == "FICO exposure"), formulas
assert "SUMPRODUCT" in formulas[("Your scenario", SCENARIO_NO_FICO.split("!")[1])][0] and ",J" in formulas[("Your scenario", SCENARIO_NO_FICO.split("!")[1])][0], formulas

# Rate engine on planted data. Four lender-channels and one too small to fit alone, ten weeks, FICO 700 to 760 at 80 LTV on purchases: a FICO loan's rate is a week's, a lender's and a score's effect plus noise.
# Loans issued before October carry 100 bp more, so a read that let them in beside loans issued from October would show it. Every VS4 loan's other score sits in its FICO's 5-point band, so at the same FICO and the same number it reads the planted gap.
import csv  # noqa: E402

import numpy as np  # noqa: E402

from gsescore import pricing  # noqa: E402

RATE_WEEKS = [("2026-08-03", "2026-08-01", "2026-07-01"), ("2026-08-10", "2026-08-01", "2026-07-01"), ("2026-08-17", "2026-08-01", "2026-07-01"), ("2026-08-24", "2026-08-01", "2026-07-01"), ("2026-08-31", "2026-09-01", "2026-08-01"),
              ("2026-09-07", "2026-09-01", "2026-08-01"), ("2026-09-14", "2026-09-01", "2026-08-01"), ("2026-10-05", "2026-10-01", "2026-09-01"), ("2026-10-12", "2026-10-01", "2026-09-01"), ("2026-10-19", "2026-10-01", "2026-09-01")]
RATE_LENDERS = {"rocket-mortgage|R": 0.05, "united-wholesale-mortgage|B": -0.03, "rocket-mortgage|C": -0.40, "other-bank|R": 0.0, "small-bank|R": 0.02}
RATE_COLS = ["agency", "loan_id", "first_intraday_date", "first_pay_date", "seller", "channel", "purpose", "occupancy", "units", "property_type", "orig_loan_amt", "dti", "mi_pct", "state", "fthb", "num_borrowers",
             "score_model", "pricing_score", "classic_fico", "vs4", "issue_month", "special_program", "ltv", "cltv", "orig_rate", "loan_term", "amort_type"]


def rate_row(i, seller, channel, week, rate, model="C", fico=700, vs4=None, purpose="P", ltv=80, agency=None, program="7"):
    first, issue, close = week
    y, m = int(close[:4]), int(close[5:7]) + 2
    pay = f"{y + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}-01"
    return {"agency": agency or ("FNMA" if i % 2 else "FHLMC"), "loan_id": f"{model}{i:06d}", "first_intraday_date": first, "first_pay_date": pay, "seller": seller, "channel": channel, "purpose": purpose, "occupancy": "P", "units": 1, "property_type": "SF",
            "orig_loan_amt": 300000, "dti": 38, "mi_pct": 0, "state": "TX", "fthb": "N", "num_borrowers": 1, "score_model": model, "pricing_score": vs4 if model == "V" else fico, "classic_fico": fico if fico else "", "vs4": vs4 if vs4 else "", "issue_month": issue,
            "special_program": program, "ltv": ltv, "cltv": ltv, "orig_rate": round(rate, 3), "loan_term": 360, "amort_type": "FRM"}


def rate_rate(rng, key, w, score):
    return 6.5 + RATE_LENDERS[key] + 0.02 * w + (1.0 if RATE_WEEKS[w][1] < "2026-10-01" else 0.0) - 0.001 * (score - 700) + rng.uniform(-0.03, 0.03)


def rate_con(table, name):
    """A connection holding planted loans, with what build_rates reads beside them."""
    path = home / f"rate_{name}.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, RATE_COLS)
        w.writeheader()
        w.writerows(table)
    c = duckdb.connect()
    c.execute("CREATE MACRO seller_key(x) AS x")
    c.execute(f"CREATE TABLE loans AS SELECT * FROM read_csv('{path}', header=true, sample_size=-1, types={{'vs4': 'INTEGER', 'classic_fico': 'INTEGER', 'pricing_score': 'INTEGER', 'first_intraday_date': 'DATE', 'first_pay_date': 'DATE', 'issue_month': 'DATE'}})")
    c.execute("CREATE TABLE seller_map AS SELECT DISTINCT seller AS key, seller AS id FROM loans")
    c.execute("CREATE TABLE entity_names (id VARCHAR, short VARCHAR)")
    c.execute("INSERT INTO entity_names VALUES ('rocket-mortgage', 'Rocket'), ('united-wholesale-mortgage', 'UWM'), ('other-bank', 'Other Bank'), ('small-bank', 'Small Bank')")
    c.execute("CREATE TABLE loan_records AS SELECT 'intraday' AS kind, max(first_intraday_date) + 1 AS file_date FROM loans")
    return c


def rate_book(gap=0.0, lower=None, shock=0.0, fico_a_week=60, vs4_a_week=60, seed=1):
    """gap: bp on the VS4 loans. lower: bp on a like number of VS4 loans with VS4 a tier above FICO, so a lower LLPA. shock: bp on all a lender-week's VS4 loans, one sign or the other. Rocket correspondent's VS4 loans carry 60 bp more."""
    rng, out, i = random.Random(seed), [], 0
    for key, _ in RATE_LENDERS.items():
        seller, channel = key.split("|")
        for w, week in enumerate(RATE_WEEKS):
            sign = 1 if (w + len(seller)) % 2 else -1
            agency = "FNMA" if w % 2 else "FHLMC"  # a week's loans at one GSE, so a VS4 loan finds its comparators however the loans alternate
            for k in range(fico_a_week if key != "small-bank|R" else 5):
                f = 700 + 20 * (k % 4)
                out.append(rate_row(i, seller, channel, week, rate_rate(rng, key, w, f), "C", f, agency=agency))
                i += 1
            per = {"other-bank|R": 3, "small-bank|R": 1, "rocket-mortgage|C": 20}.get(key, vs4_a_week)
            for k in range(per):
                f = 700 + 20 * (k % 4)
                extra = (gap + sign * shock + (60 if key == "rocket-mortgage|C" else 0)) / 100
                out.append(rate_row(i, seller, channel, week, rate_rate(rng, key, w, f) + extra, "V", f, f + 1, agency=agency))
                i += 1
                if lower is not None:
                    out.append(rate_row(i, seller, channel, week, rate_rate(rng, key, w, f) + lower / 100, "V", f, f + 20, agency=agency))
                    i += 1
            for k in range(2 if key == "rocket-mortgage|R" else 0):  # VS4 loans showing no FICO, which is unknown, not absent; and two at 820+
                out.append(rate_row(i, seller, channel, week, rate_rate(rng, key, w, 720) + gap / 100, "V", None, 720))
                out.append(rate_row(i + 1, seller, channel, week, rate_rate(rng, key, w, 760) + gap / 100, "V", 790, 830))
                i += 2
    return out


def rate_views(built):
    keys = {tuple(sorted(r)) for r in built}
    assert len(keys) == 1, "every key on every row"
    return {v: [r for r in built if r["view"] == v] for v in ("meta", "row", "answer", "limit", "line", "past", "steps", "same_number", "fico_gap", "equivalent", "lender", "cut", "check", "milliman", "follows_score", "llpa_rate", "quote", "behind")}


# A same-LLPA gap reads back at the same FICO and at the same number, on all three methods; Rocket correspondent is out of every all-lender row and has its own, flagged, and a thin row stays blank.
rate_a = rate_con(rate_book(gap=4), "a")
built_a = pricing.build_rates(rate_a)
assert json.dumps({"rows": built_a}, separators=(",", ":")) == json.dumps({"rows": pricing.build_rates(rate_a)}, separators=(",", ":")), "two builds on the same data are byte-identical"
views = rate_views(built_a)
meta_a = views["meta"][0]
row_a = {r["key"]: r for r in views["row"]}
assert [r["key"] for r in views["row"]] == ["same_fico", "lower_llpa", "same_llpa", "same_llpa_low", "same_number"] and [r["order"] for r in views["row"]] == [0, 1, 2, 3, 4]
for key in ("same_fico", "same_llpa", "same_number"):
    r = row_a[key]
    for read in ("cell5", "tier", "model", "dot_raw", "fannie"):
        assert abs(r[read] - 4) < 0.6, (key, read, r)
    assert r["dot"] == 4 and r["sentence"] == "About 4 bp higher." and r["lo_raw"] <= r["dot_raw"] <= r["hi_raw"] and r["lender_weeks"] == 20, r  # Rocket's and UWM's ten weeks each; the other two lenders' few loans a week are not weeks of data
    assert r["tl"] > 3 and r["th"] < 5 and r["read5"] <= r["n"] and r["read_tier"] <= r["n"] and r["cell5_se"] > 0, r
assert row_a["same_fico"]["strong"] and row_a["same_number"]["strong"] and not row_a["same_llpa"]["strong"], row_a
assert row_a["same_number"]["money"] == "About $10 a month on $350,000" and row_a["same_fico"]["money"] is None and row_a["same_llpa"]["money"] is None, row_a  # money only at the same number; 4 bp at about 6.9%
assert row_a["lower_llpa"]["n"] == 0 and row_a["lower_llpa"]["dot"] is None and row_a["lower_llpa"]["sentence"] == "Too few to compare yet." and row_a["lower_llpa"]["sub"] is None and row_a["lower_llpa"]["loans"] is None, row_a
# The counts: every VS4 loan in the sample; those showing a FICO, which leaves out the ones showing none; those under 820. A row reads Rocket correspondent out.
n_rc = 200
n_shown = 600 + 600 + n_rc + 30 + 10 + 20  # Rocket retail, UWM broker, Rocket correspondent, the other two, and the 20 at 820+ showing a FICO; 20 more show none
assert (meta_a["n_vs4_fico"], meta_a["n_vs4"], meta_a["n_under_820"], meta_a["n_lender_channels"], meta_a["n_loans"]) == (n_shown, n_shown + 20, n_shown, 4, n_shown + 20 + 2450), meta_a
assert row_a["same_fico"]["n"] == n_shown - n_rc and row_a["same_number"]["n"] == n_shown - n_rc, row_a
assert row_a["same_fico"]["loans"] == f"About {round(row_a['same_fico']['n'], -2):,} loans" and row_a["same_fico"]["sub"] == f"about {pricing._hundred(row_a['same_fico']['n'])} showing a FICO" and row_a["same_number"]["sub"] == f"about {pricing._hundred(row_a['same_number']['n'])} VS4 loans under 820, from Aug 3" and row_a["same_llpa"]["sub"] == f"about {pricing._hundred(row_a['same_llpa']['n'])}", row_a
assert [r["title"] for r in views["row"]] == ["Same FICO", "of which VS4 has a lower LLPA on today's grid", "of which same LLPA on today's grid", "of those, FICO under 780", "Same score number"], views["row"]
assert pricing._matched(1240, 2360, 4120) == pricing._matched(2360, 1240, 4120) == "1,200 to 2,400 of about 4,100" and pricing._matched(0, 860, 940) == "up to 900 of about 900" and pricing._matched(0, 0, 40) == "none of about 40" and pricing._matched(610, 620, 940) == "600 of about 900" and pricing._matched(0, 0, 0) is None, "a row's counts in words, for the match limit, never a zero count"
assert meta_a["as_of"] == "2026-10-19" and meta_a["provisional_from"] == "2026-10-20" and meta_a["shape"] == pricing.RATES_SHAPE == 2 and not {"read_on", "weeks_same_fico"} & set(meta_a), meta_a
assert meta_a["dated"] == "Data through Oct 19, 2026." and meta_a["changed"] == "Replaces the rate figures shown here before Oct 31, which blended two comparisons, and restates the dated figures of Oct 31 with Rocket correspondent out of every all-lender row, the LLPA tier split under 640 and the 95% range on the estimate.", meta_a
assert meta_a["said_check"].startswith("Not the same comparison: Milliman takes 20 points off VS4 first") and "Same score number under 820 is about +4 bp, data through Oct 19." in meta_a["said_check"], meta_a
assert not any(said in json.dumps(built_a) for said in ("no sign of", "discount beyond", "single-grid", "NaN")), "withdrawn wording stays out, and every number is a number"
lender_a = {r["key"]: r for r in views["lender"] if r["scope"] == "group"}
rc_row = lender_a["rocket_correspondent"]
assert rc_row["not_like_for_like"] is True and rc_row["same_fico_n"] == n_rc and abs(rc_row["same_fico_dot"] - 64) < 2 and rc_row["same_fico_rough"] is False, rc_row
assert list(lender_a) == ["rocket_retail", "rocket_broker", "uwm_broker", "uwm_correspondent", "other", "rocket_correspondent"], lender_a
assert abs(lender_a["rocket_retail"]["same_llpa_dot"] - 4) <= 1 and lender_a["rocket_retail"]["not_like_for_like"] is None and lender_a["rocket_retail"]["same_llpa_se"] > 0, lender_a["rocket_retail"]
assert lender_a["rocket_broker"]["same_fico_n"] == 0 and lender_a["rocket_broker"]["same_fico_dot"] is None and lender_a["rocket_broker"]["same_fico_se"] is None, "under 100 VS4 loans stays blank"
assert lender_a["other"]["same_fico_n"] == 40 and lender_a["other"]["same_number_dot"] is None, lender_a["other"]
card = {r["key"]: r for r in views["lender"] if r["scope"] == "card"}
assert card["rocket-mortgage"]["correspondent_out"] is True and card["rocket-mortgage"]["same_number_n"] < meta_a["n_vs4"] and "other-bank" not in card and card["united-wholesale-mortgage"]["correspondent_out"] is None, card
assert any(r["dim"] == "rocket_correspondent" and r["not_like_for_like"] for r in views["cut"]) and all(r["description"] for r in views["cut"]), views["cut"]
assert all(r["gap"] is None for r in views["cut"] if r["n"] < 100) and next(r for r in views["cut"] if r["dim"] == "purpose" and r["key"] == "P")["n"] >= 1000, views["cut"]
assert re.fullmatch(r"The thin line: it resamples about \d+ lender and channel groups, about \d+ carrying most of the weight, so treat it as the minimum uncertainty\.", next(r for r in views["limit"] if r["key"] == "thin")["text"]), views["limit"]  # no lower-LLPA row here to give a second sentence
assert [r["key"] for r in views["limit"]] == ["selected", "note_rate", "rests_on", "ranges", "left_out", "grid", "method", "thin", "match", "rebuilt"], views["limit"]  # no lender and channel carries half of this gap: the gap is even across lenders; no loans around Rocket's switch point; and higher at both figures, so not on the same-loans line
limit_of_a = lambda key: next(r["text"] for r in views["limit"] if r["key"] == key)  # noqa: E731
assert views["limit"][0]["text"] == "Fee or score? These files cannot settle it: lenders can pick the score, sometimes after the rate is set, and lock dates do not show. So this shows where a gap sits, not what choosing VS4 is worth." and views["limit"][1]["text"] == "Note rate only: discount points, lender credits and lock dates are not disclosed. +4 bp is about 0.2 of a discount point." and limit_of_a("ranges") == "A range in bp with no label is the spread across the 3 methods, not a margin of error." and limit_of_a("rebuilt") == "The newest file is provisional.", views["limit"]
assert [(r["order"], r["key"]) for r in views["answer"]] == [(0, "same_fico"), (1, "same_llpa"), (2, "same_number")] and meta_a["answer"] == " ".join(r["text"] for r in views["answer"]), views["answer"]
assert views["answer"][0]["text"] == "Same FICO: about 4 bp higher." and views["answer"][1]["text"] == "Same LLPA: about +4." and views["answer"][2]["text"] == f"About 4 bp higher at the same score number under 820 (VS4 720 against FICO 720), at both Rocket retail and UWM broker. 95% range about {pricing._range(*pricing._out95(row_a['same_number']['tl'], row_a['same_number']['th']))}.", views["answer"]  # above zero at both figures, so nothing on what it does not say
assert [r["key"] for r in views["check"]] == ["lookalike", "cells", "rare_high_vs4", "rate_range"] and all(r["pass"] in (True, False, None) and r["label"] and r["detail"] for r in views["check"]), views["check"]
assert next(r for r in views["check"] if r["key"] == "lookalike")["pass"] and next(r for r in views["check"] if r["key"] == "cells")["pass"], views["check"]
assert [r["order"] for r in views["quote"]] == list(range(len(views["quote"]))) and views["quote"][0]["text"].startswith("At the same FICO, lender, channel, timing, purpose and LTV range, VS4 loans showing a FICO ran about 4 bp above FICO loans' note rates (95% range about ") and "not in this figure" in views["quote"][2]["text"] and "$" in views["quote"][2]["text"] and not any("$" in r["text"] for i, r in enumerate(views["quote"]) if i != 2), views["quote"]  # dollars only on the same-number line
assert {(r["group"], r["close"]) for r in views["same_number"] if r["scope"] == "month"} >= {("stake", "2026-07-01"), ("no_stake", "2026-09-01")} and all(r["close"] >= "2026-06-01" for r in views["same_number"] if r["scope"] == "month"), views["same_number"]
fade = next(r for r in views["same_number"] if r["scope"] == "fade")
assert fade["text"] == "Is the gap narrowing? Too early to say: rates on closings just after the Sep 29 announcement were mostly set before it." and fade["state"] == "early" and fade["label"] == "Where the old rule would raise the LLPA", fade
assert {r["key"] for r in views["same_number"] if r["scope"] == "period"} == {"before", "from_oct"} and {r["key"] for r in views["same_number"] if r["scope"] == "band"} == {"under640", "over820"}, views["same_number"]
assert next(r for r in views["same_number"] if r["key"] == "under640")["flag"] is None and {r["key"] for r in views["same_number"] if r["scope"] == "gapband"} == {"1-19", "20-39", "40+"}, views["same_number"]
assert [r["key"] for r in views["milliman"]] == ["window", "window_late", "from_oct", "window_plain"] and all(r["pool"] and r["read"] <= r["pool"] for r in views["milliman"]), views["milliman"]
assert {r["band"] for r in views["equivalent"]} == {f"{lo}-{lo + 19}" for lo in range(640, 800, 20)}, views["equivalent"]
under_floor = next(r for r in views["equivalent"] if r["band"] == "700-719")
assert 0 < under_floor["n"] < pricing.MIN_ROW and under_floor["eq"] is None and under_floor["eq_lo"] is None and under_floor["points"] is None, under_floor  # under 100 VS4 loans a band keeps only its counts
# The steps: the FICO side stays in the window, so 100 bp on loans issued before October does not reach it; the last rung is the same read as the same-number row's from Oct 1, on both sides; Rocket correspondent's far lower FICO rates stay out.
steps = {r["key"]: r for r in views["steps"]}
assert list(steps) == ["raw", "time", "lender", "traits", "traits_under", "number", "raw_fannie", "raw_freddie"], steps
assert abs(steps["raw"]["gap"] - 4) < 2 and steps["raw"]["read"] == steps["raw"]["pool"] > 0 and abs(steps["number"]["gap"] - 4) < 1 and steps["raw"]["se"] >= 0, steps
assert steps["number"]["gap"] == next(r for r in views["same_number"] if r["scope"] == "period" and r["key"] == "from_oct")["cell5"], steps
# A lower LLPA: the row reads its own loans, at their FICO, and the same-LLPA row holds. One book carries nothing here, so nothing names one.
built_b = pricing.build_rates(rate_con(rate_book(gap=0, lower=-8), "b"))
views_b = rate_views(built_b)
row_b = {r["key"]: r for r in views_b["row"]}
assert abs(row_b["lower_llpa"]["dot"] + 8) <= 1 and abs(row_b["same_llpa"]["dot"]) <= 0.5 and row_b["lower_llpa"]["sentence"] == "About 8 bp lower." and row_b["same_llpa"]["sentence"] == "No visible difference.", row_b
assert abs(row_b["same_fico"]["cell5"] + 4) < 1.5 and row_b["lower_llpa"]["n"] > 1000, row_b
answer_b = views_b["meta"][0]["answer"]
assert f"Same LLPA: {pricing._clause(row_b['same_llpa']['sentence'], row_b['same_llpa']['dot'])}, which does not show the LLPA caused the gap." in answer_b and "under the old rule" not in answer_b and len(answer_b.split()) <= pricing.ANSWER_WORDS, answer_b
assert re.search(r" With Rocket correspondent back, the lower-LLPA range reaches [+−][\d.]+\.$", next(r for r in views_b["limit"] if r["key"] == "thin")["text"]), views_b["limit"]
assert all(r["lower_n"] > 0 and r["lower_gap"] is not None and r["same_gap"] is not None for r in views_b["llpa_rate"] if r["purpose"] == "All" and r["key"] != "rocket-mortgage|C|all"), views_b["llpa_rate"]
assert {r["key"] for r in views_b["llpa_rate"] if r["purpose"] == "All"} >= {"rocket-mortgage|R|all", "united-wholesale-mortgage|B|all"}, views_b["llpa_rate"]
# A sign flip: the same book with the gap the other way reads the other way, in the row, the sentence and the answer.
views_c = rate_views(pricing.build_rates(rate_con(rate_book(gap=-9), "c")))
row_c = {r["key"]: r for r in views_c["row"]}
assert row_c["same_number"]["dot"] == -9 and row_c["same_number"]["sentence"] == "About 9 bp lower." and row_c["same_number"]["money"] == "About $21 a month on $350,000" and row_c["same_fico"]["money"] is None, row_c
assert views_c["answer"][0]["key"] == "same_fico" and views_c["answer"][0]["text"] == "Same FICO: about 9 bp lower." and "About 9 bp lower at the same score number under 820 (VS4 720 against FICO 720)" in views_c["meta"][0]["answer"] and "It says how far short" not in views_c["answer"][-1]["text"], views_c["meta"]  # lower at both, so not between the two scores; and not above its number
# A lender and channel carrying the gap on all three reads is named from the data, and a limit says what it reads and what the rest does; Fannie reading the other way goes in the answer.
book_rows = rate_book(gap=0)
for r in book_rows:
    if r["score_model"] == "V" and r["seller"] == "united-wholesale-mortgage":
        r["orig_rate"] = round(r["orig_rate"] - 0.12, 3)
views_d = rate_views(pricing.build_rates(rate_con(book_rows, "d")))
assert "UWM broker, about half these loans, carries most of it." in next(r for r in views_d["answer"] if r["key"] == "same_fico")["text"], views_d["answer"]
said = next(r for r in views_d["limit"] if r["key"] == "book")["text"]
assert re.fullmatch(r"Over time: UWM broker's gap (looks smaller on later loans|by closing month), on 10 weeks of loans: about [+−0-9.]+ to [+−0-9.]+ closed in \w+ and [+−0-9.]+ to [+−0-9.]+ closed in \w+\. All others: about [+−0-9.]+ to [+−0-9.]+\.", said), said
# On the model too: a lender's VS4 loans in LTV bands its FICO loans never reach are outside both cell reads and read on the model alone. With those carrying most of the gap there, no one lender and channel carries half of it on all three, so none is named.
d3_rows = rate_book(gap=0, vs4_a_week=120)
for r in d3_rows:
    if r["score_model"] == "V" and r["seller"] == "united-wholesale-mortgage":
        r["orig_rate"] = round(r["orig_rate"] - 0.12, 3)
    elif r["score_model"] == "V" and r["seller"] == "rocket-mortgage" and r["channel"] == "R":
        r.update(ltv=50, cltv=50, orig_rate=round(r["orig_rate"] - 0.2, 3))
views_d3 = rate_views(pricing.build_rates(rate_con(d3_rows, "d3")))
same_d3 = next(r for r in views_d3["row"] if r["key"] == "same_fico")
assert same_d3["read5"] < same_d3["n"] and same_d3["sentence"].startswith("About") and same_d3["model"] < same_d3["cell5"] and "carries most of it" not in views_d3["meta"][0]["answer"] and "book" not in {r["key"] for r in views_d3["limit"]}, (same_d3, views_d3["meta"][0]["answer"])
assert pricing._fannie_note({"dot_raw": -8.0, "fannie": 1.5, "sentence": "About 8 bp lower."}) == "At Fannie alone it reads +2." and pricing._fannie_note({"dot_raw": -8.0, "fannie": -0.5, "sentence": "About 8 bp lower."}) == "At Fannie alone it reads −1."
assert pricing._fannie_note({"dot_raw": -8.0, "fannie": -3.0, "sentence": "About 8 bp lower."}) is None and pricing._fannie_note({"dot_raw": -1.5, "fannie": -0.5, "sentence": "No visible difference."}) is None
# The answer's lines: the same FICO line says zero is not ruled out while the row's thin line holds it, and names a lender and channel while one carries the gap. Here the other large lender reads the other way, so the groups' draws reach both sides.
split_rows = rate_book(gap=0)
for r in split_rows:
    if r["score_model"] == "V":
        r["orig_rate"] = round(r["orig_rate"] + (-0.14 if r["seller"] == "united-wholesale-mortgage" else 0.06 if r["seller"] == "rocket-mortgage" and r["channel"] == "R" else 0.0), 3)
views_split = rate_views(pricing.build_rates(rate_con(split_rows, "split")))
same_split = next(r for r in views_split["row"] if r["key"] == "same_fico")
assert same_split["sentence"].startswith("About") and same_split["tl"] <= 0 <= same_split["th"], same_split
assert views_split["answer"][0]["text"] == f"Same FICO: about {abs(same_split['dot']):g} bp lower, though zero is not ruled out. UWM broker, about half these loans, carries most of it.", views_split["answer"]
# A VS4 loan priced between its two scores: below at its FICO and above at its number, on all three methods. A lead line says so, and goes with either side. The rate falls 6 bp per 20 points and VS4 sits 40 points above FICO, so a loan 6 bp under FICO loans at its FICO is 6 bp over them at its number.


def between_book(at_fico):
    rng, out, i = random.Random(13), [], 0
    rate = lambda lift, w, score: 6.5 + lift + 0.02 * w - 0.003 * (score - 700) + rng.uniform(-0.01, 0.01)  # noqa: E731
    for seller, channel, lift in (("rocket-mortgage", "R", 0.03), ("united-wholesale-mortgage", "B", -0.02)):
        for w, week in enumerate(RATE_WEEKS):
            agency = "FNMA" if w % 2 else "FHLMC"
            for k in range(160):
                f = 660 + 20 * (k % 8)
                out.append(rate_row(i, seller, channel, week, rate(lift, w, f), "C", f, agency=agency))
                i += 1
            for k in range(120):
                f = 660 + 20 * (k % 4)
                out.append(rate_row(i, seller, channel, week, rate(lift, w, f) + at_fico / 100, "V", f, f + 40, agency=agency))
                i += 1
    return out


views_between = rate_views(pricing.build_rates(rate_con(between_book(-6.0), "between")))
pinned_720 = next(r for r in rate_views(pricing.build_rates(rate_con(rate_book(gap=4, vs4_a_week=80), "eq_floor")))["equivalent"] if r["band"] == "700-719")
assert pinned_720["n"] >= pricing.MIN_ROW and pinned_720["eq"] is None and pinned_720["eq_lo"] is None and pinned_720["eq_hi"] is None and pinned_720["points"] is None and pinned_720["fico_mean"] is not None, pinned_720  # 4 bp is past the end of this book's curve: pinned there, so it says nothing
at_720 = next(r for r in rate_views(pricing.build_rates(rate_con(between_book(-6.0), "eq_at")))["equivalent"] if r["band"] == "700-719")
assert at_720["n"] >= pricing.MIN_ROW and at_720["fico_mean"] < 720 and at_720["eq_lo"] <= at_720["eq"] <= at_720["eq_hi"] and at_720["use_bp"] is (at_720["slope"] < 2) and (at_720["points"] is None if at_720["use_bp"] else at_720["points"] == pricing._points(at_720["vs_mean"], at_720["eq"])), at_720
lead_between = "About 6 bp lower at the same FICO and about 6 bp higher at the same score number (VS4 720 against FICO 720), so where both scores show, its rate has averaged between the rates of FICO loans at those two scores."
assert [r["key"] for r in views_between["answer"]] == ["lead", "same_llpa", "same_number"] and views_between["answer"][0]["text"] == lead_between and views_between["meta"][0]["answer"].startswith(lead_between), views_between["answer"]
between_rows = {r["key"]: r for r in views_between["row"]}
assert between_rows["same_fico"]["dot"] == -6 and between_rows["same_number"]["dot"] == 6, between_rows
for planted, name in ((1.0, "between_at"), (-14.0, "between_num")):
    views_out = rate_views(pricing.build_rates(rate_con(between_book(planted), name)))
    assert views_out["answer"][0]["key"] == "same_fico", (planted, views_out["answer"], [r["sentence"] for r in views_out["row"]])
answer_rows = {"same_fico": {"sentence": "About 6 bp lower.", "dot": -6.0, "dot_raw": -6.0, "fannie": -6.0, "tl": -9.0, "th": -1.0, "lo_raw": -8.3, "hi_raw": -4.2}, "lower_llpa": {"sentence": "About 9 bp lower.", "dot": -9.0}, "same_llpa": {"sentence": "No visible difference.", "dot": 1.5}, "same_llpa_low": {"sentence": "Not clearly different from zero.", "dot": -6.5, "lo": -9.0, "hi": 3.0}, "same_number": {"sentence": "About 7 bp higher.", "dot": 7.0, "tl": 3.0, "th": 11.0}}
answer_gaps = [{"dot": 2.5, "fannie": 2.0}, {"dot": -4.5, "fannie": -3.0}, {"dot": -8.5, "fannie": -9.0}]
answer_split = {"high": 3.5, "low": -6.5, "flat": True, "open": True, "share": 0.34}
answer_plain = (1.2, -1.4)
said_example = " (VS4 720 against FICO 720)"
said_number = " at the same score number under 820"
said_range = " 95% range about +3 to +11."
said_means = " It says a VS4 number has got the rate of a lower FICO, not that VS4 costs more."
said_lead = f"About 6 bp lower at the same FICO and about 7 bp higher at the same score number{said_example}, so where both scores show, its rate has averaged between the rates of FICO loans at those two scores."
said_cause = ", which does not show the LLPA caused the gap"
said_halves = "About 35% of these loans are FICO 780+, where rates stop falling with the score; below 780 it is about −6.5, with the methods running −9 to +3."
said_llpa, said_llpa_both = f"Same LLPA: about +1.5{said_cause}.", f"Same LLPA: about +1.5 overall{said_cause}. {said_halves}"
said_held, said_few = "about +1 to −8 depending on what is held equal", "from about +1 with few controls to about −8 on the tightest match"
zero_rows = {**answer_rows, "same_fico": {**answer_rows["same_fico"], "th": 0.0}}
book_half = {"label": "A book", "share": 0.5}
# The answer with the lead and without it: same FICO's four shapes, the book, the rest under their guards. With the lead the figure sits there; without it the figure prints on the same-FICO line.
for rows_in, book, clause, lead, gaps, split, plain, want in [
    (zero_rows, book_half, "at every lender group shown", True, [], answer_split, answer_plain, [said_lead, f"Same FICO: zero is not ruled out, and the figure runs {said_held}. A book, about half these loans, carries most of it.", said_llpa_both, f"About 7 bp higher{said_number}, at every lender group shown.{said_range}{said_means}"]),
    (answer_rows, {"label": "A book", "share": 0.62}, "at both A and B", True, [], {**answer_split, "flat": False, "open": False}, answer_plain, [said_lead, f"Same FICO: the figure runs {said_held}. A book, about 62% of these loans, carries most of it.", f"Same LLPA: about +1.5 overall{said_cause}. About 35% of these loans are FICO 780+; below 780 it is about −6.5, with the methods running −9 to +3.", f"About 7 bp higher{said_number}, at both A and B.{said_range}{said_means}"]),
    (zero_rows, None, None, True, [], None, (), [said_lead, "Same FICO: zero is not ruled out.", said_llpa, f"About 7 bp higher{said_number}.{said_range}{said_means}"]),
    (answer_rows, book_half, None, True, [], None, (), [said_lead, "Same FICO: A book, about half these loans, carries most of it.", said_llpa, f"About 7 bp higher{said_number}.{said_range}{said_means}"]),
    (answer_rows, None, None, True, answer_gaps, None, (), [said_lead, "Same FICO: it runs from about +2.5 at 1 to 19 above FICO to about −8.5 at 40+ above.", said_llpa, f"About 7 bp higher{said_number}.{said_range}{said_means}"]),
    (zero_rows, None, None, False, [], answer_split, answer_plain, [f"Same FICO: about 6 bp lower, though zero is not ruled out, and it runs {said_held}.", said_llpa_both, f"About 7 bp higher{said_number}{said_example}.{said_range}{said_means}"]),
    (answer_rows, None, None, False, [], None, answer_plain, [f"Same FICO: about 6 bp lower, and it runs {said_held}.", said_llpa, f"About 7 bp higher{said_number}{said_example}.{said_range}{said_means}"]),
    (zero_rows, None, None, False, [], None, (), ["Same FICO: about 6 bp lower, though zero is not ruled out.", said_llpa, f"About 7 bp higher{said_number}{said_example}.{said_range}{said_means}"]),
    ({**answer_rows, "lower_llpa": {"sentence": "Too few to compare yet.", "dot": None}, "same_number": {**answer_rows["same_number"], "tl": -1.0}}, None, None, True, answer_gaps[:2], {**answer_split, "high": None}, (), [said_lead, "Same LLPA: about +1.5.", f"About 7 bp higher{said_number}. 95% range about −1 to +11.{said_means}"]),
    ({**answer_rows, "same_llpa": {"sentence": "About 8.5 bp lower.", "dot": -8.5, "tl": -12.5, "th": -4.5}}, None, None, False, [dict(r, dot=-4.5) if i == 0 else r for i, r in enumerate(answer_gaps)], answer_split, (), ["Same FICO: about 6 bp lower.", f"Same LLPA: about −8.5 overall. {said_halves}", f"About 7 bp higher{said_number}{said_example}.{said_range}{said_means}"]),
    ({**answer_rows, "same_fico": {"sentence": "Too few to compare yet.", "dot": None, "dot_raw": None, "fannie": None, "tl": -9.0, "th": 1.0, "lo_raw": -8.3, "hi_raw": -4.2}, "same_llpa": {"sentence": "Not clearly different from zero.", "dot": -1.0}, "same_number": {"sentence": "No visible difference.", "dot": 1.0, "tl": -1.0, "th": 3.0}}, None, "at every lender group shown", True, answer_gaps, answer_split, answer_plain, ["Same FICO: too few to compare yet.", f"Same LLPA: not clearly different from zero overall{said_cause}. {said_halves}", f"No visible difference{said_number}{said_example}. 95% range about −1 to +3."]),
    ({**answer_rows, "same_fico": {**answer_rows["same_fico"], "fannie": 1.5}}, None, None, False, [{**answer_gaps[0], "fannie": -5.0}, *answer_gaps[1:]], None, (), ["Same FICO: about 6 bp lower. At Fannie alone it reads +2.", said_llpa, f"About 7 bp higher{said_number}{said_example}.{said_range}{said_means}"]),
    ({**answer_rows, "same_fico": {**answer_rows["same_fico"], "sentence": "About 6 bp higher.", "dot": 6.0, "dot_raw": 6.0, "fannie": 6.0, "tl": 1.0, "th": 9.0}}, None, None, True, [], None, (), ["Same FICO: about 6 bp higher.", said_llpa, f"About 7 bp higher{said_number}{said_example}.{said_range}"]),
    ({**answer_rows, "same_fico": {**answer_rows["same_fico"], "sentence": "No visible difference.", "dot": -1.5}, "lower_llpa": {"sentence": "Not clearly different from zero.", "dot": -2.0}}, None, None, False, [], answer_split, answer_plain, [f"Same FICO: no visible difference, and it runs {said_held}.", f"Same LLPA: about +1.5 overall. {said_halves}", f"About 7 bp higher{said_number}{said_example}.{said_range}{said_means}"])]:
    said = pricing._answer(rows_in, book, clause, lead, gaps, split, plain)
    assert [t for _, t in said] == want and [k for k, _ in said][-2:] == ["same_llpa", "same_number"], (said, want)
# Nothing to say on the same-FICO line with the lead above it: no such line, not a bare head.
assert [k for k, _ in pricing._answer(answer_rows, None, None, True)] == ["lead", "same_llpa", "same_number"], pricing._answer(answer_rows, None, None, True)
# The four reads printing as one figure, or fewer than four, say nothing on what is held equal; a row too few to compare says nothing of its range.
assert pricing._held(answer_rows["same_fico"], (-8.4, -4.6)) == "about −4 to −8 depending on what is held equal", pricing._held(answer_rows["same_fico"], (-8.4, -4.6))
assert pricing._held({**answer_rows["same_fico"], "lo_raw": -8.2, "hi_raw": -7.8}, (-8.4, -7.6)) is None and pricing._held(answer_rows["same_fico"], (float("nan"), -1.4)) is None and pricing._held({**answer_rows["same_fico"], "sentence": "Too few to compare yet."}, answer_plain) is None and pricing._held(answer_rows["same_fico"], (1.6, -1.4)) == "about +2 to −8 depending on what is held equal" and pricing._held({**answer_rows["same_fico"], "lo_raw": -6.4, "hi_raw": 4.9}, (0.2, -0.3)) == "about +5 to −6 depending on what is held equal", pricing._held(answer_rows["same_fico"], (1.6, -1.4))  # the span by low and high, the end nearer zero first, so an end of the other sign stays
# From few controls to the tightest match only while those two reads are the span's ends, each with its own label, whichever sits nearer zero.
held_cell = {**answer_rows["same_fico"], "cell5": -8.3}
assert pricing._held(held_cell, answer_plain) == said_few and pricing._held(held_cell, (-1.4, 1.2)) == said_held and pricing._held({**held_cell, "cell5": -6.1}, answer_plain) == said_held and pricing._held(answer_rows["same_fico"], answer_plain) == said_held, pricing._held(held_cell, answer_plain)
assert pricing._held({**held_cell, "lo_raw": -2.1, "hi_raw": -1.2, "cell5": -2.1}, (6.2, 1.1)) == "from about +6 with few controls to about −2 on the tightest match", "a plain read further from zero keeps its label"
assert pricing._answer({**zero_rows, "same_fico": {**zero_rows["same_fico"], "cell5": -8.3}}, None, None, True, plain=answer_plain)[1][1] == f"Same FICO: zero is not ruled out, and the figure runs {said_few}." and pricing._answer({**zero_rows, "same_fico": {**zero_rows["same_fico"], "cell5": -8.3}}, None, None, False, plain=answer_plain)[0][1] == f"Same FICO: about 6 bp lower, though zero is not ruled out, and it runs {said_few}.", "the two forms it sits in"
# Zero is tested on the printed ends: a top end that prints as 0 holds it, one that prints below does not.
assert "zero is not ruled out" in pricing._answer({**answer_rows, "same_fico": {**answer_rows["same_fico"], "th": -0.2}}, None, None, True)[1][1] and "zero is not ruled out" not in pricing._answer({**answer_rows, "same_fico": {**answer_rows["same_fico"], "th": -0.5}}, book_half, None, True)[1][1] and pricing._holds_zero({"tl": 0.3, "th": 6.0}) and not pricing._holds_zero({"tl": 0.5, "th": 6.0}) and not pricing._holds_zero({"tl": None, "th": None}), "as the range prints"
# Same LLPA, its four forms: about 0 or a small figure on no visible difference, a signed figure on a finding, the row's clause otherwise, and too few. Overall only with the second sentence; zero only on a finding whose printed range holds it; what it does not show only beside a lower-LLPA finding at least 3 bp below it.
llpa_line = lambda change=None, split=answer_split, **rows_change: pricing._same_llpa_line({**answer_rows, "same_llpa": {**answer_rows["same_llpa"], **(change or {})}, **rows_change}, split)  # noqa: E731
assert llpa_line() == said_llpa_both and llpa_line({"dot": 0.5}) == f"Same LLPA: about 0 overall{said_cause}. {said_halves}" and llpa_line({"sentence": "Too few to compare yet.", "dot": None}) == "Same LLPA: too few to compare yet." and llpa_line({"sentence": "Not clearly different from zero.", "dot": -1.0}, None) == f"Same LLPA: not clearly different from zero{said_cause}.", llpa_line()
assert llpa_line({"sentence": "About 3.5 bp higher.", "dot": 3.5, "tl": -0.4, "th": 7.5}, None) == f"Same LLPA: about +3.5, though zero is not ruled out{said_cause}." and llpa_line({"sentence": "About 3.5 bp higher.", "dot": 3.5, "tl": 0.5, "th": 7.5}, None) == f"Same LLPA: about +3.5{said_cause}." and llpa_line({"sentence": "About 3.5 bp higher.", "dot": 3.5, "tl": 0.2, "th": 7.5}, None) == f"Same LLPA: about +3.5, though zero is not ruled out{said_cause}." and llpa_line({"tl": -2.0, "th": 3.0}, None) == said_llpa, "zero on a finding, as the range prints"
assert llpa_line(None, None, lower_llpa={"sentence": "About 2 bp higher.", "dot": 2.0}) == "Same LLPA: about +1.5." and llpa_line({"sentence": "About 6 bp higher.", "dot": 6.0, "tl": 2.0, "th": 9.5}, None, lower_llpa={"sentence": "About 2 bp higher.", "dot": 2.0}) == "Same LLPA: about +6." and llpa_line(None, None, lower_llpa={"sentence": "Too few to compare yet.", "dot": None}) == "Same LLPA: about +1.5." and llpa_line({"sentence": "About 8 bp lower.", "dot": -8.0, "tl": -12.0, "th": -2.0}, None) == "Same LLPA: about −8." and llpa_line({"dot": -6.0}, None) == f"Same LLPA: about −6{said_cause}." and llpa_line({"dot": -6.5}, None) == "Same LLPA: about −6.5.", "only beside a lower-LLPA finding below zero, 3 bp or more below"
# The second sentence needs the split's two halves, its share and the row under 780; its clauses go under their own guards.
assert llpa_line(None, {**answer_split, "high": None}) == said_llpa and llpa_line(None, {**answer_split, "low": None}) == said_llpa and llpa_line(None, {k: v for k, v in answer_split.items() if k != "share"}) == said_llpa and llpa_line(same_llpa_low={"sentence": "Too few to compare yet.", "dot": None, "lo": None, "hi": None}) == said_llpa and pricing._same_llpa_line({k: v for k, v in answer_rows.items() if k != "same_llpa_low"}, answer_split) == said_llpa, "no second sentence, no overall"
assert llpa_line(same_llpa_low={"sentence": "Not clearly different from zero.", "dot": -6.5, "lo": None, "hi": None}) == f"Same LLPA: about +1.5 overall{said_cause}. About 35% of these loans are FICO 780+, where rates stop falling with the score; below 780 it is about −6.5." and said_llpa_both.count("−9 to +3") == 1, "the row's own printed ends, so words and chart agree"
# The answer has no line beyond these, whatever the split; the discount below 780 stays in the quote.
assert [k for k, _ in pricing._answer(zero_rows, None, None, True)] == ["lead", "same_fico", "same_llpa", "same_number"], pricing._answer(zero_rows, None, None, True)
# The clause on a discount below 780 stays in the quote: here the split leaves it open, and the answer does not print it. The row's printed ends go with it.
assert answer_split["open"] and "a discount" not in pricing._answer(answer_rows, None, None, False, split=answer_split)[1][1] and pricing._split_words(answer_split, answer_rows["same_llpa_low"]) == "about +3.5 bp at FICO 780+, where rates stop falling with the score, and about −6.5 bp below 780 (−9 to +3 across the methods), so this cannot tell a discount there from none", "the quote's clause, not the answer's"
assert pricing._split_words(answer_split) == "about +3.5 bp at FICO 780+, where rates stop falling with the score, and about −6.5 bp below 780, so this cannot tell a discount there from none" and pricing._split_words({**answer_split, "flat": False, "open": False}, answer_rows["same_llpa_low"]) == "about +3.5 bp at FICO 780+ and about −6.5 bp below 780 (−9 to +3 across the methods)" and pricing._split_words({**answer_split, "open": False}, {"lo": None, "hi": None}) == "about +3.5 bp at FICO 780+, where rates stop falling with the score, and about −6.5 bp below 780" and pricing._split_words({**answer_split, "low": None}) is None and pricing._split_words(None) is None, "each clause under its guard"
# The book's gap by how far VS4 sits above FICO, and each way that sentence fails: too few loans on either band and either read, either dot not below zero, no fall from one to the next, no book, a band missing; at Fannie, a rise where both bands read, nothing said where one does not.
band_mid = {"dot": -6.5, "read5": 150, "read_tier": 180, "fannie": -5.0, "fannie_read5": 120, "fannie_read_tier": 130}
band_top = {"dot": -13.5, "read5": 160, "read_tier": 190, "fannie": -9.0, "fannie_read5": 125, "fannie_read_tier": 135}
said_book = "A book, about half these loans, carries most of it"
said_grows = f"{said_book}, and there it grows with how far VS4 sits above FICO: about −6.5 at 20 to 39 above and about −13.5 at 40+."
assert pricing._book_words(book_half, [band_mid, band_top]) == said_grows, pricing._book_words(book_half, [band_mid, band_top])
for near_change, far_change, book_in, reason in [({"read5": 99}, {}, book_half, "first band under the floor"), ({"read_tier": 99}, {}, book_half, "first band, second read"), ({}, {"read5": 99}, book_half, "second band"), ({}, {"read_tier": 99}, book_half, "second band, second read"), ({"dot": None}, {}, book_half, "no figure"), ({"dot": 0.0}, {}, book_half, "first at zero"), ({"dot": 2.5}, {"dot": -3.5}, book_half, "first above zero, second below"),
                                              ({}, {"dot": -6.5}, book_half, "no fall"), ({"dot": -13.5}, {"dot": -6.5}, book_half, "the other way"), ({"fannie": -9.0}, {"fannie": -5.0}, book_half, "rises at Fannie"), ({"fannie": -5.0}, {"fannie": -5.0}, book_half, "level at Fannie")]:
    assert pricing._book_words(book_half, [{**band_mid, **near_change}, {**band_top, **far_change}]) == f"{said_book}.", (reason, pricing._book_words(book_half, [{**band_mid, **near_change}, {**band_top, **far_change}]))
assert pricing._book_words(None, [band_mid, band_top]) is None and not pricing._book_grows(None, [band_mid, band_top]) and not pricing._book_grows(book_half, [band_mid]) and pricing._book_words(book_half, []) == f"{said_book}.", "no book, or a band short"
for near_change, far_change in (({"fannie": -9.0, "fannie_read5": 99}, {"fannie": -5.0}), ({"fannie": -9.0}, {"fannie": -5.0, "fannie_read_tier": 99}), ({"fannie": None, "fannie_read5": 0, "fannie_read_tier": 0}, {"fannie": -5.0})):
    assert pricing._book_words(book_half, [{**band_mid, **near_change}, {**band_top, **far_change}]) == said_grows, "a band that cannot be compared at Fannie is not held against it"
# All three methods fall too, where a method reads; each that does not ends the sentence at the book.
for near_change, far_change, reason in (({"cell5": -7.1}, {"cell5": -6.9}, "5-point match rises"), ({"tier": -7.1}, {"tier": -7.1}, "one-tier match level"), ({"model": -8.6}, {"model": -7.7}, "the model rises")):
    assert pricing._book_words(book_half, [{**band_mid, "cell5": -6.9, "tier": -6.1, "model": -3.6, **near_change}, {**band_top, "cell5": -14.1, "tier": -12.9, "model": -11.2, **far_change}]) == f"{said_book}.", (reason, pricing._book_words(book_half, [{**band_mid, **near_change}, {**band_top, **far_change}]))
assert pricing._book_words(book_half, [{**band_mid, "cell5": -6.9, "tier": -6.1, "model": None}, {**band_top, "cell5": -14.1, "tier": -12.9, "model": -11.2}]) == said_grows, "a method with no read is not held against it"
# As the LLPA gap does: only while it rises on today's grid and on the old rule, and at Fannie too where each band has 100+ loans. No figure prints.
said_grows_llpa = said_grows.replace("and there it grows with", "and there it grows, as the LLPA gap does, with")
llpa_mid, llpa_top = {"llpa_gap": 0.11, "llpa_gap_old": 0.03, "fannie_n": 150, "fannie_llpa_gap": 0.13, "fannie_llpa_gap_old": 0.05}, {"llpa_gap": 0.52, "llpa_gap_old": 0.33, "fannie_n": 160, "fannie_llpa_gap": 0.48, "fannie_llpa_gap_old": 0.36}
assert pricing._book_words(book_half, [{**band_mid, **llpa_mid}, {**band_top, **llpa_top}]) == said_grows_llpa, pricing._book_words(book_half, [{**band_mid, **llpa_mid}, {**band_top, **llpa_top}])
for key in ("llpa_gap", "llpa_gap_old", "fannie_llpa_gap", "fannie_llpa_gap_old"):
    assert pricing._book_words(book_half, [{**band_mid, **llpa_mid}, {**band_top, **llpa_top, key: llpa_mid[key]}]) == said_grows and pricing._book_words(book_half, [{**band_mid, **llpa_mid}, {**band_top, **llpa_top, key: float("nan")}]) == said_grows, key
assert pricing._book_words(book_half, [{**band_mid, **llpa_mid, "fannie_n": 99}, {**band_top, **llpa_top, "fannie_llpa_gap": 0.05}]) == said_grows_llpa and pricing._book_words(book_half, [{**band_mid, **llpa_mid}, {**band_top, **llpa_top, "fannie_n": 99, "fannie_llpa_gap_old": 0.01}]) == said_grows_llpa, "a band with too few loans at Fannie is not held against it"
assert pricing._book_words(book_half, [{**band_mid, "dot": 1.0, **llpa_mid}, {**band_top, **llpa_top}]) == f"{said_book}." and not pricing._llpa_gap_rises([band_mid, band_top]), "only with the sentence it sits in, and only on what the bands carry"
# With the book's sentence the pooled one goes; without it the pooled one stays.
grows_rows = pricing._answer(answer_rows, book_half, None, True, answer_gaps, at_book=[band_mid, band_top])[1][1]
assert grows_rows == f"Same FICO: {said_grows}" and "It runs from" not in grows_rows, grows_rows
assert pricing._answer(answer_rows, book_half, None, False, answer_gaps, at_book=[{**band_mid, "dot": 1.0}, band_top])[0][1] == f"Same FICO: about 6 bp lower. It runs from about +2.5 at 1 to 19 above FICO to about −8.5 at 40+ above. {said_book}.", pricing._answer(answer_rows, book_half, None, False, answer_gaps, at_book=[{**band_mid, "dot": 1.0}, band_top])[0][1]
# Same score number: every sentence the row can read makes a sentence, with the lender clause, the range and the sentence on what it means only under their guards. No range on a row too few to compare; what it means only on a finding above zero.
for sentence, dot, tl, th, clause, want in [("Not clearly different from zero.", 1.0, -1.0, 3.0, "at every lender group shown", f"Not clearly different from zero{said_number}{said_example}. 95% range about −1 to +3."), ("Too few to compare yet.", None, -2.0, 3.0, "at every lender group shown", f"Too few to compare yet{said_number}{said_example}."), ("No visible difference.", 0.5, -1.0, 3.0, None, f"No visible difference{said_number}{said_example}. 95% range about −1 to +3."), ("About 6.5 bp lower.", -6.5, -11.0, -3.0, "at both A and B", f"About 6.5 bp lower{said_number}{said_example}, at both A and B. 95% range about −11 to −3."), ("About 6.5 bp higher.", 6.5, None, None, None, f"About 6.5 bp higher{said_number}{said_example}.{said_means}"), ("About 6.5 bp higher.", 6.5, 3.0, None, None, f"About 6.5 bp higher{said_number}{said_example}.{said_means}"), ("Not clearly different from zero.", 1.0, 0.5, 3.0, None, f"Not clearly different from zero{said_number}{said_example}."), ("No visible difference.", 1.5, 0.75, 2.5, None, f"No visible difference{said_number}{said_example}."), ("About 2.5 bp lower.", -2.5, -11.0, 3.0, None, f"About 2.5 bp lower{said_number}{said_example}. 95% range about −11 to +3.")]:
    assert pricing._answer({**answer_rows, "same_number": {"sentence": sentence, "dot": dot, "tl": tl, "th": th}}, None, clause, False)[-1][1] == want, (sentence, want, pricing._answer({**answer_rows, "same_number": {"sentence": sentence, "dot": dot, "tl": tl, "th": th}}, None, clause, False)[-1][1])
assert "firmest" not in " ".join(t for _, t in pricing._answer(zero_rows, None, None, False)), "the firm sentence is gone"
# The lender clause goes only if the whole passes the word limit; 'at every lender group shown' needs three lenders, not three channels of two, and each group at half the row's figure or more.
assert pricing.ANSWER_WORDS == 195, "set from what these sentences measure: raise it only with a reason"
pricing.ANSWER_WORDS, words_kept = 40, pricing.ANSWER_WORDS
assert pricing._answer(answer_rows, None, "at every lender group shown", True, answer_gaps, answer_split)[-1][1] == f"About 7 bp higher{said_number}.{said_range}{said_means}"
pricing.ANSWER_WORDS = words_kept


def clause_of(seller, channel, name, third=4.0, shown=()):
    """A third lender and channel beside Rocket retail and UWM broker, with loans enough to read, all three above zero."""
    book = rate_book(gap=4)
    for w, week in enumerate(RATE_WEEKS):
        rate = 6.5 + 0.02 * w + (1.0 if week[1] < "2026-10-01" else 0.0)
        book += [rate_row(700000 + 200 * w + 2 * k, seller, channel, week, rate, "C", 700, agency="FNMA") for k in range(30)] + [rate_row(700001 + 200 * w + 2 * k, seller, channel, week, rate + third / 100, "V", 700, 701, agency="FNMA") for k in range(30)]
    s_clause = pricing._sample(rate_con(book, name))
    pricing._fit_all(s_clause)
    return pricing._lender_clause(s_clause, {"rocket-mortgage": "Rocket", "united-wholesale-mortgage": "UWM"}, 4.0, shown)


assert clause_of("other-bank", "R", "clause_three") == "at every lender group shown" and clause_of("rocket-mortgage", "B", "clause_two") == "at both Rocket retail and UWM broker", "three lenders, not three channels of two"
assert clause_of("other-bank", "R", "clause_half", 1.5) == "at both Rocket retail and UWM broker" and clause_of("other-bank", "R", "clause_at_half", 2.5) == "at every lender group shown", "each group at half the row's figure or more"
assert clause_of("other-bank", "R", "clause_shown", shown=[{"same_number_dot": 6.5}, {"same_number_dot": None}]) == "at every lender group shown" and clause_of("other-bank", "R", "clause_against", shown=[{"same_number_dot": 6.5}, {"same_number_dot": -3.0}]) == "at both Rocket retail and UWM broker" and clause_of("other-bank", "R", "clause_zero", shown=[{"same_number_dot": 0.0}]) == "at both Rocket retail and UWM broker", "every figure on chart 4 keeps the row's sign, its pooled rows too"
# One of the two largest groups with nothing to read names neither.
clause_unread = [r for r in rate_book(gap=4) if not (r["seller"] == "united-wholesale-mortgage" and r["channel"] == "B" and r["score_model"] == "C")]
s_unread = pricing._sample(rate_con(clause_unread, "clause_unread"))
pricing._fit_all(s_unread)
assert pricing._lender_clause(s_unread, {"rocket-mortgage": "Rocket", "united-wholesale-mortgage": "UWM"}, 4.0) is None, "both must read"
# Too few to read: the floor is on the loans compared, not the pool. Here every VS4 number misses its comparators' 5-point band, so the row keeps its reads and prints nothing, and the lines beside it go too.
few_compared = rate_book(gap=4)
for r in few_compared:
    if r["score_model"] == "V" and r["vs4"] and r["vs4"] < 820:
        r["vs4"] = r["pricing_score"] = r["vs4"] + 6
views_few = rate_views(pricing.build_rates(rate_con(few_compared, "few_compared")))
few_row = {r["key"]: r for r in views_few["row"]}["same_number"]
assert few_row["n"] >= 1000 and few_row["read5"] == 0 and few_row["read_tier"] >= 1000 and few_row["sentence"] == "Too few to compare yet.", few_row
assert few_row["dot"] is None and few_row["lo"] is None and few_row["hi"] is None and few_row["money"] is None and few_row["tier"] is not None and few_row["dot_raw"] == few_row["tier"] and few_row["lo_raw"] is not None and few_row["model"] is not None, few_row
meta_few = views_few["meta"][0]
assert not any(r["text"].startswith(("At the same score number", "On average a VS4 number")) for r in views_few["quote"]) and any(r["text"].startswith("At the same FICO") for r in views_few["quote"]), views_few["quote"]
assert meta_few["said_check"] is None and meta_few["equivalent_stat"] is None and meta_few["equivalent_more"] is None and meta_few["number_caption"] is None and "firmest" not in meta_few["answer"], meta_few
assert meta_few["number_bands"] == "Left out: VS4 820+, about one VS4 loan in 64, has almost no FICO loans at its number.", meta_few["number_bands"]
assert views_few["answer"][-1]["text"] == "Too few to compare yet at the same score number under 820 (VS4 720 against FICO 720).", views_few["answer"]  # its thin line stays for the workbook, and prints nowhere here
# And at the same FICO: most VS4 loans here show no FICO, so the pool for the same number stays and the quote keeps only its line.
no_shown = rate_book(gap=4)
for i, r in enumerate(no_shown):
    if r["score_model"] == "V" and r["classic_fico"] and i % 20:
        r["classic_fico"] = ""
views_no_shown = rate_views(pricing.build_rates(rate_con(no_shown, "no_shown")))
row_no_shown = {r["key"]: r for r in views_no_shown["row"]}
assert row_no_shown["same_fico"]["n"] < 1000 and row_no_shown["same_fico"]["dot"] is None and row_no_shown["same_fico"]["money"] is None and row_no_shown["same_llpa"]["dot"] is None and row_no_shown["same_number"]["dot"] == 4, row_no_shown
assert not any(r["text"].startswith("At the same FICO") for r in views_no_shown["quote"]) and views_no_shown["quote"][0]["text"].startswith("At the same score number under 820 (VS4 720 against FICO 720), VS4 loans first disclosed from Aug 3 ran about 4 bp above FICO loans' note rates ") and views_no_shown["answer"][0]["text"] == "Same FICO: too few to compare yet.", (views_no_shown["quote"], views_no_shown["answer"])
# The quote's lines: the 95% range with its name, on half points rounded outward, the clauses under their guards, and 820+ only while it has loans. No dollars.
views_b_quote = views_b["quote"]
assert re.fullmatch(r"At the same FICO, where both scores carry the same LLPA on the Oct 1 grid, VS4 loans ran about level with FICO loans' note rates \(95% range about [+−0-9.]+ to [+−0-9.]+\)\. Most of these rates were likely set earlier, when the LLPA grid counted VS4 as 20 points lower\. Rocket correspondent is left out; with it the top of the range is [+−0-9.]+\.", views_b_quote[1]["text"]), views_b_quote[1]
assert re.fullmatch(r"At the same FICO, lender, channel, timing, purpose and LTV range, VS4 loans showing a FICO ran about [\d.]+ bp below FICO loans' note rates \(95% range about [+−0-9.]+ to [+−0-9.]+\), before points and lender credits, which do not show\. Most of these rates were likely set before the Sep 29 announcement of one LLPA grid for both scores\. Across lenders the gap is about [+−0-9.]+ where VS4 has the lower LLPA on the Oct 1 grid and about level where the LLPA is the same(?: \(about [+−0-9.]+ below FICO 780, where all the lower-LLPA loans sit; [+−0-9.]+ to [+−0-9.]+ across the methods\))?, which does not show the LLPA caused it\. Lenders can pick the score, so this shows where a gap sits, not what choosing VS4 is worth\. Rocket correspondent is left out; with it the top of the range is [+−0-9.]+\.", views_b_quote[0]["text"]), views_b_quote[0]  # not every loan here was issued from Oct 1, no one lender carries it, and what is held equal does not move it past a whole point
no_high = rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=4) if not r["vs4"] or r["vs4"] < 820], "no_high")))["quote"][2]["text"]
assert no_high.endswith("The 4 bp is about $10 a month on $350,000, before points and lender credits, which do not show.") and "820+" not in no_high and " VS4 loans first disclosed from Aug 3 ran about 4 bp above FICO loans' note rates " in no_high and ", higher at both Rocket retail and UWM broker, with Rocket correspondent left out." in no_high, no_high
# Nothing to read but Rocket correspondent's loans: every row blank, and the build still ends.
only_rc = rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=4) if (r["seller"], r["channel"]) == ("rocket-mortgage", "C")], "only_rc")))
assert "held-out" not in next(r for r in only_rc["check"] if r["key"] == "lookalike")["detail"], "none held out, so no count of them"
assert only_rc["meta"][0]["score_lead"] is None and views_between["meta"][0]["score_lead"] == "Each test below stops short." and views["meta"][0]["score_lead"] is None, (only_rc["meta"][0]["score_lead"], views["meta"][0]["score_lead"])
assert all(r["n"] == 0 and r["sub"] is None and r["loans"] is None for r in only_rc["row"]) and only_rc["meta"][0]["number_bands"] is None and only_rc["meta"][0]["rule_at_lock"] is None and only_rc["meta"][0]["sample"] is None and next(r for r in only_rc["cut"] if r["dim"] == "rocket_correspondent")["n"] == 200, only_rc["row"]
assert all(np.isnan(v[0]) for v in pricing._regress(np.zeros(0), [np.zeros(0)], [np.zeros(0, dtype=np.int64)], np.zeros(0, dtype=np.int64))), "an empty mask reads as nothing"
# A lender-week needs five loans to count: here one lender has 4 VS4 loans a week and another 5.
s_weeks = pricing._sample(rate_con([rate_row(i, "rocket-mortgage", "R", RATE_WEEKS[i % 2], 6.5, "V", 700, 701) for i in range(8)] + [rate_row(100 + i, "united-wholesale-mortgage", "B", RATE_WEEKS[i % 2], 6.5, "V", 700, 701) for i in range(10)], "weeks"))
assert pricing._weeks(s_weeks, s_weeks.seller == "rocket-mortgage") == 0 and pricing._weeks(s_weeks, s_weeks.seller == "united-wholesale-mortgage") == 2 and pricing._weeks(s_weeks, np.zeros(s_weeks.n, bool)) == 0, s_weeks.n
assert pricing._span([-3.0, -6.4]) == "−6.5 to −3" and pricing._span([-0.2, 3.2]) == "−0.5 to +3.5" and pricing._count(1, "loan") == "1 loan" and pricing._count(1200, "loan") == "1,200 loans" and pricing._plural(1, "week") == "week", pricing._span([-3.0, -6.4])
assert pricing._one_in(0.13, "VS4 loan") == "about one VS4 loan in eight" and pricing._one_in(0.0, "loan") == "about 0% of loans" and pricing._one_in(0.7, "loan") == "about 70% of loans" and pricing._one_in(0.4, "loan") == "about 40% of loans" and pricing._one_in(0.6, "loan") == "about 60% of loans" and pricing._one_in(0.5, "loan") == "about one loan in two" and pricing._half_of(0.55) == "about half" and pricing._half_of(0.56) == "about 56%" and pricing._hundred(1234) == "1,200" and pricing._hundred(40) == "40"
assert pricing._out95(-6.31, 2.01) == (-6.5, 2.5) and pricing._out95(-6.5, 2.5) == (-6.5, 2.5) and pricing._half_span([-6.31, 2.01, -0.5]) == "−6.5 to +2.5" and pricing._five(13.2) == 15 and pricing._five(12.4) == 10, "a 95% range and side reads round outward, to half points"
assert list(pricing._tier_band(np.array([599, 600, 639, 640, 659, 660, 790]))) == [129, 130, 131, 1, 1, 2, 8], "one LLPA tier as the band, but 20 points under 640"
assert pricing._t975(6) == 2.447 and abs(pricing._t975(60) - 2.0) < 0.001 and np.isnan(pricing._t975(0)), "t at 97.5%, no table past 30"
# Rocket's switch point: where the pick flips and little else does. A loan sits on VS4 from 20 points above FICO, in a waived program so no LLPA is at stake. A step planted at it reads back; the same test at lines where nothing switches reads a step only where one is planted.
LINE_NAMES = {"rocket-mortgage": "Rocket"}


def line_book(step=0.0, kink=0.0, a_lift=9, below_on_vs4=0.0, program="H"):
    """a_lift loans at each lift from 35 below FICO to 69 above, in ten weeks and at both GSEs. step: bp from the line up. kink: bp from 10 below FICO up, on FICO loans. below_on_vs4: the share on VS4 below the line."""
    rng, out, i = random.Random(17), [], 0
    for w, week in enumerate(RATE_WEEKS):
        for lift in range(-35, 70):
            for k in range(a_lift):
                f = 700 + (i * 7) % 60
                on_v = lift >= 20 or rng.random() < below_on_vs4
                rate = 6.5 + 0.02 * w - 0.001 * (f - 700) + (step / 100 if lift >= 20 else 0.0) + (kink / 100 if -10 <= lift < 20 else 0.0) + rng.uniform(-0.03, 0.03)
                out.append(rate_row(i, "rocket-mortgage", "R", week, rate, "V" if on_v else "C", f, f + lift, program=program))
                i += 1
    return out


def line_read(name, **change):
    return pricing._rocket_line(pricing._sample(rate_con(line_book(**change), name)), LINE_NAMES)


LINE_KEYS = ["main", "fannie", "lower", "all", "false|-20", "false|-10", "false|0", "false|5", "false|35", "false|45", "false|55", "scan"]
flat_rows, flat_said = line_read("line_flat")
flat = {r["key"]: r for r in flat_rows}
assert list(flat) == LINE_KEYS and [r["order"] for r in flat_rows] == list(range(12)), flat_rows
assert flat["main"]["use_below"] == 0 and flat["main"]["use_above"] == 1 and "use_below" not in flat["fannie"] and abs(flat["main"]["est"]) < 2 and flat["main"]["lo"] <= 0 <= flat["main"]["hi"] and flat["main"]["n"] == 2700 and flat["main"]["above"] == 1350 and flat["main"]["lender_weeks"] == 10 and flat["fannie"]["n"] < flat["main"]["n"], flat["main"]
assert flat["lower"]["n"] == 0 and flat["lower"]["est"] is None and flat["all"]["n"] == flat["main"]["n"] and abs(flat["main"]["hi"] - (flat["main"]["est"] + pricing._t975(9) * flat["main"]["se"])) < 0.02 and abs(flat["main"]["lo"] - (flat["main"]["est"] - pricing._t975(9) * flat["main"]["se"])) < 0.02, flat["lower"]
assert flat["scan"]["lines"] == 73 and flat["scan"]["p2_5"] <= flat["scan"]["p97_5"] and flat["scan"]["min"] <= flat["scan"]["p2_5"] and flat["scan"]["max"] >= flat["scan"]["p97_5"] and 0 <= flat["scan"]["miss_share"] <= 1 and flat["scan"]["abs_p90"] < 5, flat["scan"]
line_shape = r"At Rocket's switch point \(20 points above FICO\): where the LLPA would not change, the rate {} about [+−0-9.]+ \(95% range about [+−0-9.]+ to [+−0-9.]+\)\. The same test at about \d+ other cut-offs where nothing switches swings about [+−0-9]+ to [+−0-9]+, so it cannot see a step under about \d+ bp\."
assert re.fullmatch(line_shape.format("moves"), flat_said) and f"(95% range about {pricing._range(*pricing._out95(flat['main']['lo'], flat['main']['hi']))})" in flat_said and "closings" not in flat_said, flat_said
assert f"swings about {pricing._range(float(np.floor(flat['scan']['p2_5'])), float(np.ceil(flat['scan']['p97_5'])))}, so it" in flat_said, (flat_said, flat["scan"])  # its ends outward, in whole points
# A step that shows: the sentence says it steps, and the range misses zero on t(G - 1), not 1.96.
step_rows, step_said = line_read("line_step", step=30.0)
step_est = {r["key"]: r for r in step_rows}["main"]
assert abs(step_est["est"] - 30) < 3 and step_est["lo"] > 0 and re.fullmatch(line_shape.format("steps"), step_said), step_said
# On few weeks of loans the range says so.
few_weeks_said = pricing._rocket_line(pricing._sample(rate_con([r for r in line_book() if r["first_intraday_date"] < RATE_WEEKS[6][0]], "x_line_weeks")), LINE_NAMES)[1]
assert "(95% range about " in few_weeks_said and ", on few weeks of loans)." in few_weeks_said, few_weeks_said
# A kink only at the other lines moves the scan, which then says what the test cannot see.
kink_rows, kink_said = line_read("line_kink", kink=20.0)
kink_scan = {r["key"]: r for r in kink_rows}["scan"]
assert kink_scan["max"] > 15 and kink_scan["abs_p90"] > flat["scan"]["abs_p90"] and kink_said.endswith(f"so it cannot see a step under about {int(np.ceil(kink_scan['abs_p90'] / 5) * 5)} bp."), (kink_said, kink_scan)
# A line with loans on one side only has no figure; nor a handful on one side.
one_side = {r["key"]: r for r in pricing._rocket_line(pricing._sample(rate_con([r for r in line_book() if r["vs4"] - r["classic_fico"] < 20], "line_side")), LINE_NAMES)[0]}
assert one_side["main"]["n"] >= 500 and one_side["main"]["above"] == 0 and one_side["main"]["est"] is None and one_side["main"]["lo"] is None and one_side["false|0"]["est"] is not None, one_side["main"]
few_side = {r["key"]: r for r in pricing._rocket_line(pricing._sample(rate_con([r for i, r in enumerate(line_book()) if r["vs4"] - r["classic_fico"] < 20 or i % 400 == 0], "x_side")), LINE_NAMES)[0]}
assert 0 < few_side["main"]["above"] < pricing.MIN_N and few_side["main"]["est"] is None, few_side["main"]
# The sentence needs the switch itself and enough loans; the rows stay.
for change in ({"below_on_vs4": 0.25}, {"a_lift": 1}):
    rows_off, said_off = line_read("line_off", **change)
    assert said_off is None and len(rows_off) == 12, (change, said_off)
assert line_read("line_low", below_on_vs4=0.15)[1] is not None
# The first stage is read at 15 to 19 and at 20 to 24 and no wider, and most of the loans at 20 to 24 must sit on VS4.
stage_wide = line_book()
for r in stage_wide:
    if 5 <= r["vs4"] - r["classic_fico"] < 15:
        r.update(score_model="V", pricing_score=r["vs4"])
stage_read = pricing._rocket_line(pricing._sample(rate_con(stage_wide, "x_stage")), LINE_NAMES)
assert stage_read[0][0]["use_below"] == 0 and stage_read[1] is not None, "loans under 15 points above FICO are not the first stage"
stage_up = line_book()
for i, r in enumerate(stage_up):
    if 20 <= r["vs4"] - r["classic_fico"] < 25 and i % 5 < 2:
        r.update(score_model="C", pricing_score=r["classic_fico"])
stage_read = pricing._rocket_line(pricing._sample(rate_con(stage_up, "x_up")), LINE_NAMES)
assert stage_read[0][0]["use_above"] < 0.8 and stage_read[1] is None, stage_read[0][0]
# The first stage by closing date, each side with 100+ loans: the words go with the month, and under 1% says so.
stage_dated = line_book()
for r in stage_dated:
    if r["first_intraday_date"] >= "2026-10-05":
        r["first_pay_date"] = "2026-12-01"
dated_read = pricing._rocket_line(pricing._sample(rate_con(stage_dated, "x_dated")), LINE_NAMES)
assert dated_read[0][0]["use_below_early"] == 0 and dated_read[0][0]["use_below_early_n"] == 315 and dated_read[0][0]["use_below_late"] == 0 and dated_read[0][0]["use_below_late_n"] == 135, dated_read[0][0]
assert "closings" not in dated_read[1] and "VS4 goes from" not in dated_read[1], dated_read[1]  # the shares stay in the rows, for the workbook
stage_late = line_book()
for r in stage_late:
    if r["first_intraday_date"] >= "2026-10-05":
        r["first_pay_date"] = "2026-12-01"
        if 15 <= r["vs4"] - r["classic_fico"] < 20 and r["loan_id"][-1] in "012":
            r.update(score_model="V", pricing_score=r["vs4"])
    elif 15 <= r["vs4"] - r["classic_fico"] < 20 and r["first_intraday_date"] == "2026-08-10" and r["loan_id"][-1] in "012":
        r.update(score_model="V", pricing_score=r["vs4"])
late_read = pricing._rocket_line(pricing._sample(rate_con(stage_late, "x_late")), LINE_NAMES)
assert "closings" not in late_read[1] and late_read[0][0]["use_below_late"] > late_read[0][0]["use_below_early"] > 0.01, late_read[0][0]
# (A book closing on one side of the announcement has no split: see flat_said above.)
# Fewer than 20 lines read: the scan clause goes and the rest stands.
few_lines = pricing._rocket_line(pricing._sample(rate_con([r for r in line_book() if 15 <= r["vs4"] - r["classic_fico"] <= 40], "x_fewlines")), LINE_NAMES)
assert few_lines[1] is not None and {r["key"]: r for r in few_lines[0]}["scan"]["lines"] < 20 and "The same test" not in few_lines[1] and few_lines[1].endswith(")."), few_lines[1]
# "Where the LLPA would not change" covers the whole window: no loan left in the main row has a lower LLPA on VS4, and the mask is on FICO up to 34 points.
fee_con = rate_con(line_book(program="7"), "line_fee")
s_fee = pricing._sample(fee_con)
fee_lift = s_fee.vs - s_fee.fico
line_fee = {r["key"]: r for r in pricing._rocket_line(s_fee, LINE_NAMES)[0]}
assert pricing.LINE_CLEAR == pricing.LINE_CUT + pricing.LINE_H - 1 and line_fee["lower"]["n"] > 0 and line_fee["main"]["n"] + line_fee["lower"]["n"] == line_fee["all"]["n"], line_fee["main"]
fee_main = s_fee.has_f & s_fee.has_v & (s_fee.fee_f == s_fee.fee_near) & (fee_lift >= 5) & (fee_lift < 35)
assert line_fee["main"]["n"] == int(fee_main.sum()) and not (s_fee.fee_v[fee_main] < s_fee.fee_f[fee_main]).any(), "the LLPA holds across the window"
assert line_fee["false|0"]["n"] == int((s_fee.has_f & s_fee.has_v & ~s_fee.is_v & (s_fee.fee_f == s_fee.fee_near) & (fee_lift >= -15) & (fee_lift < 15)).sum()), line_fee["false|0"]
# The main four rows run to convergence; the lines where nothing switches keep the fits' cap.
passes_seen, regress_kept = [], pricing._regress
pricing._regress = lambda *a, **k: (passes_seen.append(k.get("passes")), regress_kept(*a, **k))[1]
line_counted = {r["key"]: r for r in pricing._rocket_line(pricing._sample(rate_con(line_book(a_lift=3), "x_passes")), LINE_NAMES)[0]}
pricing._regress = regress_kept
assert passes_seen.count(pricing.LINE_PASSES) == sum(line_counted[k]["est"] is not None for k in ("main", "fannie", "lower", "all")) > 0 and set(passes_seen) == {pricing.LINE_PASSES, pricing.PASSES}, set(passes_seen)
# Through the build: a line row beside the others and the limit in place, the answer saying nothing of a step.
line_book_all = rate_book(gap=0, lower=None) + line_book()
views_line = rate_views(pricing.build_rates(rate_con([{**r, "loan_id": f"{r['loan_id']}{i}"} for i, r in enumerate(line_book_all)], "line_all")))
assert {r["key"] for r in views_line["line"]} == set(flat) and "line" in {r["key"] for r in views_line["limit"]} and not {r["key"] for r in views["line"]} - set(flat), [r["key"] for r in views_line["limit"]]
assert "step" not in views_line["meta"][0]["answer"], views_line["answer"]
assert all(r["n"] == 0 or r["est"] is None for r in views["line"]), views["line"]


# On the old rule in force at lock: 20 points off, whether it would have put the LLPA below its FICO's, by the same three methods, on loans closed by September while that is most of the same-FICO loans.
lock_rows, lock_rng, lock_i = [], random.Random(19), 0
for key in ("rocket-mortgage|R", "united-wholesale-mortgage|B"):
    seller, channel = key.split("|")
    for w, week in enumerate(RATE_WEEKS[:7]):
        agency = "FNMA" if w % 2 else "FHLMC"
        for k in range(30):
            f = 700 + 20 * (k % 4)
            lock_rows.append(rate_row(lock_i, seller, channel, week, rate_rate(lock_rng, key, w, f), "C", f, agency=agency))
            lock_rows.append(rate_row(lock_i + 1, seller, channel, week, rate_rate(lock_rng, key, w, f) - 0.12, "V", f, f + 40, agency=agency))
            lock_rows.append(rate_row(lock_i + 2, seller, channel, week, rate_rate(lock_rng, key, w, f) - 0.01, "V", f, f + 20, agency=agency))
            lock_i += 3
s_lock = pricing._sample(rate_con(lock_rows, "lock"))
pricing._fit_all(s_lock)
lock_said = pricing._rule_at_lock(s_lock, 0.51)
lock_read = re.fullmatch(r"On the old rule, in force when most of these rates were likely set: on loans closed by September, about ([+−0-9.]+) to ([+−0-9.]+) where it would have put the LLPA below its FICO's and about ([+−0-9.]+) to ([+−0-9.]+) where it would have matched it\.", lock_said)
lock_at = [float(v.replace("−", "-")) for v in lock_read.groups()]
assert all(abs(got - want) <= 2 for got, want in zip(lock_at, (-12, -12, -1, -1))) and lock_at[0] <= lock_at[1] and lock_at[2] <= lock_at[3], lock_said
assert pricing._rule_at_lock(s_lock, 0.5) is None and pricing._rule_at_lock(s_lock, float("nan")) is None, "most of these loans must have closed by then"
# Where it would have matched it, the one book and the rest, while each has 100+ matched loans on all three methods.
lock_book = {"label": "A book", "lc": int(s_lock.lc[s_lock.seller == "rocket-mortgage"][0])}
assert re.fullmatch(r".* Where it would have matched it: A book about [+−0-9.]+ to [+−0-9.]+, the rest about [+−0-9.]+ to [+−0-9.]+\.", pricing._rule_at_lock(s_lock, 0.51, lock_book)), pricing._rule_at_lock(s_lock, 0.51, lock_book)
assert "Where it would have matched it:" not in pricing._rule_at_lock(s_lock, 0.51, {**lock_book, "lc": -1}), "no book, no second sentence"
assert "Where it would have matched it:" not in pricing._rule_at_lock(s_lock, 0.51, None)
# So the split looks much the same: only while both splits sit 3+ bp apart, the old rule's on its midpoints and today's on its dots, and the two within 3 bp of each other.
lock_alike = ", so the split looks much the same."
lock_today = lambda lower, same: {"lower_llpa": {"dot": lower}, "same_llpa": {"dot": same}}  # noqa: E731
lock_mid = lambda r: (r["cell5"] + r["tier"]) / 2  # noqa: E731
lock_split = lock_mid(pricing._lock_reads(s_lock)["same"]) - lock_mid(pricing._lock_reads(s_lock)["lower"])
assert pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-2.0 - lock_split, -2.0)).endswith(f"where it would have matched it{lock_alike}") and pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-2.0 - lock_split + 2.5, -2.0)).endswith(f"where it would have matched it{lock_alike}"), pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-2.0 - lock_split, -2.0))
assert lock_alike not in pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-4.5, -2.0)) and lock_alike not in pricing._rule_at_lock(s_lock, 0.51, None, lock_today(None, -2.0)) and lock_alike not in pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-9.5, None)) and lock_alike not in pricing._rule_at_lock(s_lock, 0.51), "today's split"
lock_kept, lock_planted = pricing._lock_reads, lambda lower, same: (lambda s, book=None: {"lower": {"cell5": lower - 0.5, "tier": lower + 0.5, "model": lower, "n": 300, "read5": 150, "read_tier": 180}, "same": {"cell5": same - 0.5, "tier": same + 0.5, "model": same, "n": 300, "read5": 150, "read_tier": 180}, "book": None, "rest": None})  # noqa: E731
pricing._lock_reads = lock_planted(-6.5, -3.5)
lock_three = pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-5.5, -2.5))
pricing._lock_reads = lock_planted(-6.0, -3.5)
lock_under = pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-5.5, -2.5))
pricing._lock_reads = lock_planted(-6.5, -0.5)
lock_wide, lock_within, lock_over = pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-16.0, -1.0)), pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-10.0, -1.0)), pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-10.5, -1.0))
pricing._lock_reads = lock_planted(-17.0, -2.0)
lock_narrow = pricing._rule_at_lock(s_lock, 0.51, None, lock_today(-5.0, -2.0))
pricing._lock_reads = lambda s, book=None: {**lock_planted(-6.5, -0.5)(s), "book": {"cell5": -9.5, "tier": -7.5, "model": -8.5}, "rest": {"cell5": 2.5, "tier": 3.5, "model": 4.5}}
lock_two = pricing._rule_at_lock(s_lock, 0.51, lock_book)
pricing._lock_reads = lock_kept
assert lock_alike in lock_three and lock_alike not in lock_under and lock_alike not in lock_wide and lock_alike in lock_within and lock_alike not in lock_over and lock_alike not in lock_narrow, (lock_three, lock_under, lock_wide, lock_within, lock_over, lock_narrow)
assert lock_two.endswith(" Where it would have matched it: A book about −9.5 to −7.5, the rest about +2.5 to +4.5."), lock_two
# On loans closed by September only: a large gap on October closings moves nothing in it.
lock_october = lock_rows + [rate_row(lock_i + k, "rocket-mortgage", "R", ("2026-10-05", "2026-11-01", "2026-10-01"), 5.5 - 0.3 * (k % 2), "V" if k % 2 else "C", 700, 740 if k % 2 else None, agency="FNMA") for k in range(400)]
s_october = pricing._sample(rate_con(lock_october, "lock_october"))
pricing._fit_all(s_october)
for key in ("lower", "same"):
    assert {k: pricing._lock_reads(s_lock)[key][k] for k in ("cell5", "tier", "n", "read5", "read_tier")} == {k: pricing._lock_reads(s_october)[key][k] for k in ("cell5", "tier", "n", "read5", "read_tier")}, key
s_few_lock = pricing._sample(rate_con(lock_rows[:200], "lock_few"))
pricing._fit_all(s_few_lock)
assert pricing._rule_at_lock(s_few_lock, 0.51) is None, "100 loans each"
# More cuts: chart 4's grammar on every row, so the same label prints the same number; a row under 100 loans keeps its counts and nothing else; Rocket correspondent against its own FICO loans.
cut_b = {(r["dim"], r["key"]): r for r in views_b["cut"]}
cut_row = cut_b[("purpose", "P")]
same_b = {r["key"]: r for r in views_b["row"]}["same_llpa"]
assert cut_row["n"] == same_b["n"] and cut_row["dot"] == same_b["dot"] and (cut_row["spread_lo"], cut_row["spread_hi"]) == (same_b["lo"], same_b["hi"]) and (cut_row["tl"], cut_row["th"]) == (same_b["tl"], same_b["th"]) and cut_row["read5"] == same_b["read5"] and cut_row["read_tier"] == same_b["read_tier"] and cut_row["model_n"] == same_b["model_n"] and cut_row["model"] == cut_row["gap"] == same_b["model"], (cut_row, same_b)
assert cut_row["thin"] is False and cut_row["lo"] < cut_row["gap"] < cut_row["hi"] and cut_row["se"] > 0 and cut_row["text"] is None, cut_row
for r in views_b["cut"]:
    if r["n"] < 100:
        assert all(r[k] is None for k in ("gap", "se", "lo", "hi", "model", "cell5", "tier", "dot_raw", "lo_raw", "hi_raw", "dot", "spread_lo", "spread_hi", "tl", "th")), r
cut_rc = cut_b[("rocket_correspondent", "rocket_correspondent")]
lender_b_rc = {r["key"]: r for r in views_b["lender"] if r["scope"] == "group"}["rocket_correspondent"]
assert cut_rc["not_like_for_like"] is True and cut_rc["dot"] == lender_b_rc["same_llpa_dot"] and (cut_rc["spread_lo"], cut_rc["spread_hi"]) == (lender_b_rc["same_llpa_lo"], lender_b_rc["same_llpa_hi"]) and cut_rc["tl"] is None, "one group to redraw: no thin line"
# The thin line is the estimate's range: each draw's midpoint of the two cell reads, each on its own loans, using the other read where a draw has no loans on one, and a group in only one read still counts. Under two groups there is nothing to redraw.
thin_groups = np.array([1, 1, 2, 2])
thin_a, thin_b = {"g": np.array([10.0, 10.0, np.nan, np.nan])}, {"g": np.array([10.0, 10.0, 20.0, 20.0])}
assert pricing._thin_mid(thin_a, thin_b, thin_groups) == (10.0, 20.0) and pricing._thin_groups(thin_a, thin_b, thin_groups) == (2, 2.0), pricing._thin_mid(thin_a, thin_b, thin_groups)
assert np.isnan(pricing._thin_mid({"g": np.array([1.0, 2.0])}, {"g": np.array([np.nan, 2.0])}, np.array([3, 3]))[0]) and pricing._thin_groups({"g": np.array([np.nan])}, {"g": np.array([np.nan])}, np.array([3])) == (0, 0.0)
assert pricing._thin_mid({"g": np.array([0.0, 8.0])}, {"g": np.array([4.0, 12.0])}, np.array([1, 2])) == (2.0, 10.0), "the midpoint in each draw"
# The LLPA fold's rows: chart 4's reads on chart 4's masks, every row under 100 loans blank, its count staying.
llpa_b = {r["key"]: r for r in views_b["llpa_rate"]}
lender_b = {r["key"]: r for r in views_b["lender"] if r["scope"] == "group"}
for key, group in (("rocket-mortgage|R|all", "rocket_retail"), ("united-wholesale-mortgage|B|all", "uwm_broker"), ("rocket-mortgage|C|all", "rocket_correspondent")):
    r, g = llpa_b[key], lender_b[group]
    assert (r["same_dot"], r["same_lo"], r["same_hi"], r["same_n"], r["same_rough"]) == (g["same_llpa_dot"], g["same_llpa_lo"], g["same_llpa_hi"], g["same_llpa_n"], g["same_llpa_rough"]), (r, g)
    assert r["lower_dot"] is not None and r["lower_lo"] <= r["lower_dot"] <= r["lower_hi"] and r["lower_gap"] is not None and r["lower_se"] > 0 and r["same_gap"] is not None, r
small_llpa = rate_book(gap=0, lower=-8)
for i, r in enumerate(small_llpa):
    if r["score_model"] == "V" and r["seller"] == "rocket-mortgage" and r["channel"] == "R" and i % 20:
        r["purpose"] = "C"
llpa_small = {r["key"]: r for r in rate_views(pricing.build_rates(rate_con(small_llpa, "llpa_small")))["llpa_rate"]}["rocket-mortgage|R|P"]
assert 0 < llpa_small["same_n"] < 100 and llpa_small["same_dot"] is None and llpa_small["same_gap"] is None and llpa_small["same_se"] is None and llpa_small["same_lo"] is None and llpa_small["same_hi"] is None, llpa_small
# The build checks: each count is the one behind the value beside it, and a check read on nothing says so.
checks_b = {r["key"]: r for r in views_b["check"]}
assert checks_b["cells"]["n"] in (row_b["same_fico"]["n"], row_b["same_llpa"]["n"], row_b["same_number"]["n"]) and checks_b["lookalike"]["n"] > 0 and "About" in checks_b["lookalike"]["detail"], checks_b
checks_none = {r["key"]: r for r in rate_views(pricing.build_rates(rate_con(rate_book()[:40], "checks_none")))["check"]}
assert checks_none["lookalike"]["detail"].startswith("No figure weighted to all VS4 loans at their VS4 number; no figure weighted to VS4 loans showing a FICO at that FICO") and "0 of 0" not in checks_none["lookalike"]["detail"] and checks_none["lookalike"]["value"] is None and checks_none["lookalike"]["n"] == 0, checks_none["lookalike"]
assert checks_none["cells"]["value"] is None and checks_none["cells"]["n"] == 0 and checks_none["rare_high_vs4"]["detail"] == "Too few of these loans to test." and checks_none["rare_high_vs4"]["top_share"] is None, checks_none
# A thin book: the row stays blank in words, and nothing in the build breaks.
views_e = rate_views(pricing.build_rates(rate_con(rate_book(gap=4, vs4_a_week=4), "e")))
assert all(r["sentence"] == "Too few to compare yet." for r in views_e["row"]), views_e["row"]
assert "too few to compare yet" in views_e["meta"][0]["answer"] and len(views_e["meta"][0]["answer"].split()) <= pricing.ANSWER_WORDS, views_e["meta"]
assert pricing.build_rates(rate_con(rate_book()[:10], "f")) == [], "too few FICO loans to fit"
assert [r["n"] for r in rate_views(pricing.build_rates(rate_con(rate_book()[:40], "f2")))["row"]] == [0, 0, 0, 0, 0], "and with no VS4 loan, every row blank"
# A shock on a whole lender-week's VS4 loans: clustered errors see it, and sd over root n would not.
rate_g = rate_con(rate_book(gap=0, shock=12), "g")
row_g = {r["key"]: r for r in rate_views(pricing.build_rates(rate_g))["row"]}
s_g = pricing._sample(rate_g)
pricing._fit_all(s_g)
in_row = s_g.tv & ~np.isnan(s_g.gap_fico)
naive = s_g.gap_fico[in_row].std(ddof=1) / np.sqrt(in_row.sum())
assert row_g["same_fico"]["model_se"] > 3 * naive and row_g["same_fico"]["cell5_se"] > 3 * naive, (row_g["same_fico"], naive)
# The fade line waits for closings past Oct 15, by month, across 8+ lender-weeks; then the two lines' difference decides, and only when the fit and the cells agree; and a read that they closed needs a move at a fixed gap between the two scores. A waived program has no LLPA, so nothing at stake. With no read the early text stands.
FADE_WEEKS = [(f"2026-11-{d}", "2026-12-01", "2026-11-01") for d in ("02", "09", "16", "23")]
FADE_EARLY = [(f"2026-10-{d}", "2026-11-01", "2026-10-01") for d in ("05", "12", "19", "26")]


def fade_book(stake_gap, no_stake_gap, gap_before=None):
    """gap_before: bp on VS4 loans 25 points above their FICO that closed before the mark, with the same kind of loan at no_stake_gap after it."""
    out, rng, i = [], random.Random(5), 0
    for seller, channel in (("rocket-mortgage", "R"), ("united-wholesale-mortgage", "B")):
        for w, week in enumerate(FADE_WEEKS):
            agency = "FNMA" if w % 2 else "FHLMC"
            for program, gap in (("7", stake_gap), ("H", no_stake_gap)):
                for k in range(60):
                    out.append(rate_row(i, seller, channel, week, 6.5 + 0.02 * w + rng.uniform(-0.02, 0.02), "C", 700, program=program, agency=agency))
                    out.append(rate_row(i + 1, seller, channel, week, 6.5 + 0.02 * w + gap / 100 + rng.uniform(-0.02, 0.02), "V", 700, 701, program=program, agency=agency))
                    i += 2
        if gap_before is not None:
            for weeks, gap in ((FADE_EARLY, gap_before), (FADE_WEEKS, no_stake_gap)):
                for w, week in enumerate(weeks):
                    agency = "FNMA" if w % 2 else "FHLMC"
                    for k in range(40):
                        out.append(rate_row(i, seller, channel, week, 6.5 + 0.02 * w + rng.uniform(-0.02, 0.02), "C", 725, program="H", agency=agency))
                        out.append(rate_row(i + 1, seller, channel, week, 6.5 + 0.02 * w + gap / 100 + rng.uniform(-0.02, 0.02), "V", 700, 725, program="H", agency=agency))
                        i += 2
    return out


for planted_gaps, state, said in (((8, 0), "holds", "still differ on closings from November on: no clear narrowing yet."), ((8, 8), "no_move", "no longer clearly differ on closings from November on, but nothing has moved among loans with the same gap between VS4 and FICO: no clear narrowing yet."), ((8, 8, 8), "no_move", "but nothing has moved among loans with the same gap"), ((8, 8, 30), "fades", "no longer clearly differ on closings from November on.")):
    faded = next(r for r in rate_views(pricing.build_rates(rate_con(fade_book(*planted_gaps), "fade")))["same_number"] if r["scope"] == "fade")
    assert faded["state"] == state and said in faded["text"] and faded["text"].startswith("Is the gap narrowing? The two lines ") and faded["lender_weeks"] == 8 and "no sign" not in faded["text"] and "methods disagree" not in faded["text"] and "fixed gap" not in faded["text"], (planted_gaps, faded)
# The methods disagree only while one read says apart and the other does not: here stake loans the cells cannot reach pull the model's read level, and the cells' stays apart.
disagree = fade_book(8, 0)
for w, week in enumerate(FADE_WEEKS):
    for seller, channel in (("rocket-mortgage", "R"), ("united-wholesale-mortgage", "B")):
        disagree += [rate_row(993000 + 1000 * w + 2 * k + (seller[0] == "u") * 500, seller, channel, week, 6.5 + 0.02 * w - 0.08, "V", 700, 701, ltv=75, agency="FNMA" if w % 2 else "FHLMC") for k in range(60)]
faded = next(r for r in rate_views(pricing.build_rates(rate_con(disagree, "fade_disagree")))["same_number"] if r["scope"] == "fade")
assert faded["state"] == "unsettled" and faded["text"] == "Is the gap narrowing? The methods disagree on closings from November on: no clear narrowing yet.", faded
# Under 8 lender-weeks it stays early; a move only at the 1 to 19 band is not a move at a fixed gap past the old rule.
fade_one = next(r for r in rate_views(pricing.build_rates(rate_con([r for r in fade_book(8, 0) if r["seller"] == "rocket-mortgage"], "x_fade1")))["same_number"] if r["scope"] == "fade")
assert fade_one["state"] == "early" and fade_one["lender_weeks"] == 4, fade_one
fade_low, fade_i = fade_book(8, 8), 990000
for seller, channel in (("rocket-mortgage", "R"), ("united-wholesale-mortgage", "B")):
    for w, week in enumerate(FADE_EARLY):
        for k in range(40):
            fade_low.append(rate_row(fade_i, seller, channel, week, 6.5 + 0.02 * w, "C", 701, program="H", agency="FNMA" if w % 2 else "FHLMC"))
            fade_low.append(rate_row(fade_i + 1, seller, channel, week, 6.5 + 0.02 * w + 0.30, "V", 700, 701, program="H", agency="FNMA" if w % 2 else "FHLMC"))
            fade_i += 2
assert next(r for r in rate_views(pricing.build_rates(rate_con(fade_low, "x_fadelow")))["same_number"] if r["scope"] == "fade")["state"] == "no_move"
# A month with a few stray loans stays blank: no read travels out of it, in any scope, and its counts and flag stay. One lender-week here carries the only loans closed in that month, at a wild rate.
stray_book = rate_book(gap=4, lower=-8)
stray_week = ("2026-10-19", "2026-10-01", "2026-10-01")
stray_book += [rate_row(800000 + k, "rocket-mortgage", "R", stray_week, 3.0, "V", 700, 725) for k in range(8)] + [rate_row(800100 + k, "rocket-mortgage", "R", stray_week, 6.5, "C", 725) for k in range(8)]
stray_rows = rate_views(pricing.build_rates(rate_con(stray_book, "stray")))["same_number"]
stray_blank = ("gap", "se", "lo", "hi", "cell5", "tier", "dot_raw", "lo_raw", "hi_raw", "dot", "spread_lo", "spread_hi")
for r in (next(x for x in stray_rows if x["key"] == "stake|2026-10-01"), next(x for x in stray_rows if x["key"] == "20-39|2026-10-01")):
    assert all(r[k] is None for k in stray_blank) and r["n"] == r["pool"] == 8 and r["read"] == 8 and r["lender_weeks"] == 1 and r["thin"], r
assert next(x for x in stray_rows if x["key"] == "20-39")["dot"] is not None and next(x for x in stray_rows if x["key"] == "20-39")["tl"] is not None and next(x for x in stray_rows if x["key"] == "stake|2026-09-01")["dot"] is not None, stray_rows
assert all(x["tl"] is None and x["dot"] is None for x in stray_rows if x["scope"] == "gapband_month"), stray_rows
assert all(x["less20"] is None for x in rate_views(pricing.build_rates(rate_con(rate_book(gap=4, vs4_a_week=1), "stray_thin")))["same_number"] if x["scope"] == "period" and x["n"] < 100)
# A month's share in the chart: how much of it has arrived, from the closing dataset's lender rows weighted by each seller's share of the month's chart loans, with the market row for a seller with no row, times how much of its VS4 loans the sample keeps. Without an arrival for every seller, none.
late_seen = rate_book(gap=4)
late_seen += [rate_row(810000 + k, "rocket-mortgage", "R", ("2026-07-06", "2026-08-01", "2026-07-01"), 6.5, "V", 700, 701) for k in range(1200)] + [rate_row(812000 + k, "rocket-mortgage", "C", ("2026-07-06", "2026-08-01", "2026-07-01"), 6.5, "V", 700, 701) for k in range(5000)]
kept_all = sum(1 for r in late_seen if r["score_model"] == "V" and r["first_pay_date"] == "2026-09-01" and (r["seller"], r["channel"]) != ("rocket-mortgage", "C"))
kept_share = 1 - 1200 / kept_all
assert 0 < kept_share < 1 and abs(pricing._kept(rate_con(late_seen, "kept"))["2026-07-01"] - kept_share) < 1e-9, (kept_share, kept_all)  # Rocket correspondent left out of it
planted_closing = [{"view": "market", "agency": "All", "start": "2026-07-01", "arrived": 0.5}, {"view": "market", "agency": "FNMA", "start": "2026-07-01", "arrived": 0.1}, {"view": "lender", "agency": "All", "id": "rocket-mortgage", "start": "2026-07-01", "arrived": 0.8}, {"view": "lender", "agency": "All", "id": "united-wholesale-mortgage", "start": "2026-07-01", "arrived": 0.6}, {"view": "lender", "agency": "FNMA", "id": "rocket-mortgage", "start": "2026-07-01", "arrived": 0.05},
                   {"view": "market", "agency": "All", "start": "2026-08-01", "arrived": None}, {"view": "lender", "agency": "All", "id": "rocket-mortgage", "start": "2026-08-01", "arrived": 0.8}, {"view": "market", "agency": "All", "start": "2026-09-01", "arrived": 0.25}]
built_in = rate_views(pricing.build_rates(rate_con(late_seen, "kept2"), planted_closing))["same_number"]
july_arrived = (4 * 62 * 0.8 + 4 * 60 * 0.6 + 4 * 4 * 0.5) / (4 * 62 + 4 * 60 + 4 * 4)  # a week's chart loans: Rocket retail 60 and 2 showing no FICO, UWM broker 60, the other two 4, on the market's row; Rocket correspondent left out
assert {(r["close"], r["in_share"]) for r in built_in if r["scope"] == "month"} == {("2026-07-01", round(july_arrived * kept_share, 3)), ("2026-08-01", None), ("2026-09-01", 0.25)}, [(r["close"], r["in_share"]) for r in built_in if r["scope"] == "month"]
assert all(r["in_share"] is None for r in views["same_number"]) and all(r["in_share"] is None for r in rate_views(pricing.build_rates(rate_con(rate_book(gap=4), "kept3"), []))["same_number"]), "no closing rows, no share"
assert all(r["in_share"] is None for r in built_in if r["scope"] != "month"), built_in
# A shown score is a fact and a score not shown is unknown: a VS4 loan showing no FICO has no gap at its FICO, and still has one at its number.
s_a = pricing._sample(rate_a)
pricing._fit_all(s_a)
none_shown = s_a.is_v & (s_a.fico < 0)
assert none_shown.sum() == 20 and np.isnan(s_a.gap_fico[none_shown]).all() and not np.isnan(s_a.gap_number[none_shown]).any(), none_shown.sum()
assert not (s_a.same | s_a.lower)[none_shown].any() and np.nanmax(np.abs(s_a.gap_fico[s_a.is_v & ~s_a.rc & (s_a.vs < 820)])) < 15, "and no flag rests on it"
# Below an own fit's lowest FICO band with 5+ loans there is no comparison; above its highest that band stands in.
fit_a = next(f for f in pricing._fit_all(s_a) if s_a.seller[f.ix[0]] == "rocket-mortgage" and s_a.channel[f.ix[0]] == "R")
one = np.array([0])
assert np.isnan(fit_a.at(one, np.array([pricing._band5(600)]))).all() and fit_a.at(one, np.array([pricing._band5(845)]))[0] == fit_a.at(one, np.array([pricing._band5(760)]))[0], (fit_a.lo, fit_a.hi)
# The printed rule, one function: half points while the reads sit within 4 bp, whole past that; the dot to the nearest, lo down, hi up.
for raw, want in [((-3.3, -4.2, -2.4), (-3.5, -4.5, -2.0)), ((-11.13, -12.2, -10.0), (-11.0, -12.5, -10.0)), ((0.2, -1.1, 1.1), (0.0, -1.5, 1.5)), ((7.8, 7.7, 8.3), (8.0, 7.5, 8.5)), ((0.3, -2.5, 2.5), (0.0, -3.0, 3.0)),
                  ((1.0, -2.0, 2.0), (1.0, -2.0, 2.0)), ((-0.1, -0.1, -0.1), (0.0, -0.5, 0.0)), ((-2.5, -4.0, -0.01), (-2.5, -4.0, 0.0)), ((-2.5, -4.5, -0.5), (-3.0, -5.0, 0.0))]:
    assert pricing.printed(*raw) == want, (raw, pricing.printed(*raw), want)
# Each answer sentence.
for args, want in [((999, 40, -9.0, -7.0, -8.0), "Too few to compare yet."), ((5000, 7, -9.0, -7.0, -8.0), "Too few to compare yet."), ((5000, 40, None, None, None), "Too few to compare yet."), ((5000, 40, -2.5, 1.0, -0.5), "No visible difference."), ((1000, 8, -3.0, 3.0, 0.5), "No visible difference."),
                   ((5000, 40, -9.0, -7.0, -8.0), "About 8 bp lower."), ((5000, 40, 1.5, 3.5, 2.5), "About 2.5 bp higher."), ((5000, 40, -3.5, 2.0, -1.0), "Not clearly different from zero."), ((5000, 40, -1.0, 4.0, 1.5), "Not clearly different from zero.")]:
    assert pricing.answer_sentence(*args) == want, (args, pricing.answer_sentence(*args))
# Follows the score: a rate that depends only on the score used, with the two scores moving apart, reads back, and VS4's slope less FICO's with it. The sentence stands on refinances, with Fannie refinances leaning the same way; it says what those slopes come to with the LLPA of the score used held, and what purchases do, with what holds on purchases checked at Fannie alone. On thin data the guard fails and the sentence goes.
FOLLOW_WEEKS = [(f"2026-{m}-{d}", "2026-10-01" if m == "10" else "2026-11-01", "2026-09-01") for m, d in (("10", "05"), ("10", "12"), ("10", "19"), ("10", "26"), ("11", "02"), ("11", "09"), ("11", "16"), ("11", "23"))]
FOLLOW_SCOPES = ("all", "refi", "purchase", "fannie", "fannie_refi", "fannie_purchase", "rocket_retail", "rocket_broker", "uwm")


def follow_book(n=12000, **other):
    """other: bp per 20 points the unused score also moves the rate, on one kind of loan: other_fannie_refi; other_freddie_refi; other_refi; other_purchase_vs4 and other_purchase_fico, by the score used; other_fannie_purchase; other_uwm; other_rocket_broker. steps, steps_vs4, steps_fico: the used score moves the rate only by the LLPA tier, by that many bp a tier, on all loans or those priced on that score. Two in five loans are at Fannie and three in seven refinances. Rocket across eight weeks, UWM across two: enough lender-weeks for all lenders together, and not for UWM alone."""
    rng, out = random.Random(3), []
    for i in range(n):
        seller, channel, w = ("united-wholesale-mortgage", "B", (i // 2) % 2) if i % 3 == 0 else ("rocket-mortgage", "B" if i % 9 == 1 else "R", (i // 2) % 8)
        f, v = 640 + (i * 37) % 160, 640 + (i * 91) % 160
        used_vs4 = i % 2 == 0
        agency = "FNMA" if i % 5 < 2 else "FHLMC"
        refi = i % 7 < 3
        used, unused = (v, f) if used_vs4 else (f, v)
        bend = (other.get("other_fannie_refi", 0.0) if agency == "FNMA" and refi else 0.0) + (other.get("other_freddie_refi", 0.0) if agency != "FNMA" and refi else 0.0) + (other.get("other_refi", 0.0) if refi else 0.0) + (0.0 if refi else other.get("other_purchase_vs4" if used_vs4 else "other_purchase_fico", 0.0)) + (other.get("other_fannie_purchase", 0.0) if agency == "FNMA" and not refi else 0.0) + (other.get("other_uwm", 0.0) if seller != "rocket-mortgage" else (other.get("other_rocket_broker", 0.0) if channel == "B" else 0.0))
        steps = other.get("steps_vs4" if used_vs4 else "steps_fico", other.get("steps"))
        slope = steps / 100 * pricing._tier(np.array([used]))[0] if steps is not None else 0.075 * used / 20
        rate = 6.5 + RATE_LENDERS.get(f"{seller}|{channel}", 0.03) + 0.02 * w - slope + bend / 100 * (unused - 720) / 20 + rng.uniform(-0.01, 0.01)
        out.append(rate_row(i, seller, channel, FOLLOW_WEEKS[w], rate, "V" if used_vs4 else "C", f, v, agency=agency, purpose="C" if refi else "P"))
    return out


def follow_read(name, **change):
    c = rate_con(follow_book(**change), name)
    return {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c), dict(c.execute("SELECT id, short FROM entity_names").fetchall()))}


read = follow_read("follow")
assert {scope for scope, _ in read} == {*FOLLOW_SCOPES, "refi_llpa", "purchase_llpa"} and [r["label"] for (scope, group), r in read.items() if group == "vs4"][:4] == ["All lenders", "Refinances", "Refinances, LLPA of the score used held", "Purchases"] and read[("rocket_broker", "vs4")]["label"] == "Rocket broker", read.keys()
for scope in FOLLOW_SCOPES:
    assert abs(read[(scope, "vs4")]["on_vs4"] + 7.5) < 0.3 and abs(read[(scope, "vs4")]["on_fico"]) < 0.3 and abs(read[(scope, "fico")]["on_fico"] + 7.5) < 0.3 and abs(read[(scope, "fico")]["on_vs4"]) < 0.3 and read[(scope, "vs4")]["guard"] and read[(scope, "fico")]["guard"], (scope, read[(scope, "vs4")])
    assert abs(read[(scope, "vs4")]["diff"] - (read[(scope, "vs4")]["on_vs4"] - read[(scope, "vs4")]["on_fico"])) < 0.02 and read[(scope, "fico")]["diff"] > 0 and read[(scope, "fico")]["diff_se"] is not None, read[(scope, "vs4")]
follow_head = "Which score the rate tracks, per 20 points, on loans with both scores 640 to 799: on refinances, VS4 loans move about −7.5 bp on VS4 and 0 on FICO; FICO loans about −7.5 on FICO and 0 on VS4."
follow_held = " But the score used also sets the LLPA: hold that LLPA on refinances and they come to about −7.5 and 0 on VS4 loans and about −7.5 and 0 on FICO loans, so this cannot tell a view on credit from the LLPA."
follow_also = lambda bit: follow_held.replace(", so this", f", and on {bit}, so this")  # noqa: E731
assert read[("all", "vs4")]["sentence"] == read[("all", "fico")]["sentence"] == f"{follow_head} Purchases go the same way.{follow_also('purchases to about −7.5 and 0 on VS4 loans and about −7.5 and 0 on FICO loans')}", read[("all", "vs4")]
assert all(r["sentence"] is None and "clause" not in r and "tracks" not in r for (scope, _), r in read.items() if scope != "all") and read[("uwm", "vs4")]["lender_weeks"] == 2 and "clause" not in read[("all", "vs4")] and "tracks" not in read[("all", "vs4")], read
# With the LLPA of the score used held: the same two fits on the same loans, one more effect absorbed, stored with no guard to hold. A rate that moves only by the LLPA tier leaves no lean to see, so the lean goes; here it stays, so the figures print without that claim.
assert all(not read[("refi_llpa", g)]["guard"] and read[("refi_llpa", g)]["n"] == read[("refi", g)]["n"] and read[("refi_llpa", g)]["label"] == "Refinances, LLPA of the score used held" and read[("refi_llpa", g)]["key"] == f"refi_llpa|{g}" for g in ("vs4", "fico")) and abs(read[("refi_llpa", "vs4")]["on_vs4"] + 7.5) < 0.6 and abs(read[("refi_llpa", "fico")]["on_fico"] + 7.5) < 0.6 and abs(read[("refi_llpa", "vs4")]["diff"] - (read[("refi_llpa", "vs4")]["on_vs4"] - read[("refi_llpa", "vs4")]["on_fico"])) < 0.02, read[("refi_llpa", "vs4")]
read_steps = follow_read("follow_steps", steps=30.0)
assert read_steps[("refi", "vs4")]["guard"] and abs(read_steps[("refi_llpa", "vs4")]["on_vs4"]) < abs(read_steps[("refi", "vs4")]["on_vs4"]) / 3, (read_steps[("refi", "vs4")], read_steps[("refi_llpa", "vs4")])
assert " But the score used also sets the LLPA: hold that LLPA and the lean goes, on refinances (VS4 loans about " in read_steps[("all", "vs4")]["sentence"] and "; FICO loans about " in read_steps[("all", "vs4")]["sentence"] and ") and on purchases (VS4 loans about " in read_steps[("all", "vs4")]["sentence"] and "), so this cannot tell a view on credit from the LLPA." in read_steps[("all", "vs4")]["sentence"], read_steps[("all", "vs4")]["sentence"]
for one_side in ("steps_vs4", "steps_fico"):
    read_one = follow_read(f"follow_{one_side}", **{one_side: 30.0})
    assert " But the score used also sets the LLPA: hold that LLPA on refinances and they come to about " in read_one[("all", "vs4")]["sentence"], (one_side, read_one[("all", "vs4")]["sentence"], read_one[("refi_llpa", "vs4")], read_one[("refi_llpa", "fico")])
follow_regress = pricing._regress
pricing._regress = lambda y, xs, fes, *a, **k: ([float("nan")] * len(xs), [float("nan")] * len(xs)) if len(fes) > 14 else follow_regress(y, xs, fes, *a, **k)
read_unread = follow_read("follow_unread")
pricing._regress = follow_regress
assert read_unread[("all", "vs4")]["sentence"].startswith(follow_head) and read_unread[("all", "vs4")]["sentence"].endswith(" But the score used also sets the LLPA, so this cannot tell a view on credit from the LLPA.") and read_unread[("refi_llpa", "vs4")]["on_vs4"] is None, read_unread[("all", "vs4")]["sentence"]
# The held fits' figures in their own places: VS4 loans' first, each on the used score first. The lean goes only where neither fit still leans, however wide its error, on refinances and on any group the purchases line says follows its score.
def follow_held_read(name, vs4_fit, fico_fit, purchase_vs4=(-2.5, -3.5), purchase_fico=(-4.5, -2.0), se=9.0, **change):
    calls, kept = iter([vs4_fit, vs4_fit, fico_fit, fico_fit, purchase_vs4, purchase_vs4, purchase_fico, purchase_fico]), pricing._regress
    pricing._regress = lambda y, xs, fes, *a, **k: (list(next(calls)), [se, se]) if len(fes) > 14 else kept(y, xs, fes, *a, **k)
    try:
        return follow_read(name, **change)[("all", "vs4")]["sentence"]
    finally:
        pricing._regress = kept


follow_gone = "hold that LLPA and the lean goes, on refinances (VS4 loans about −2 and −3; FICO loans about −1.5 and −3.5) and on "
assert f"{follow_gone}purchases (VS4 loans about −2.5 and −3.5; FICO loans about −2 and −4.5), so this" in follow_held_read("follow_held_gone", (-2.0, -3.0), (-3.5, -1.5)), "the used score's slope first, in each fit"
assert "hold that LLPA and the lean goes on refinances (VS4 loans about −2 and −3; FICO loans about −1.5 and −3.5) but not on purchases (VS4 loans about −4 and −1; FICO loans about −2 and −4.5), so this" in follow_held_read("follow_held_buy", (-2.0, -3.0), (-3.5, -1.5), purchase_vs4=(-4.0, -1.0)), "a purchase slope still leaning"
assert "hold that LLPA on refinances and they come to about −4 and −1 on VS4 loans and about −1.5 and −3.5 on FICO loans, and on purchases to about −2.5 and −3.5 on VS4 loans and about −2 and −4.5 on FICO loans, so this" in follow_held_read("follow_held_lean", (-4.0, -1.0), (-3.5, -1.5)), "a refinance slope still leaning, with an error too wide to clear zero"
assert "hold that LLPA on refinances and they come to about −2 and −3 on VS4 loans and about −4 and −1.5 on FICO loans" in follow_held_read("follow_held_lean2", (-2.0, -3.0), (-1.5, -4.0)), "either fit"
assert "hold that LLPA and the lean goes, on refinances" in follow_held_read("follow_held_edge", (-2.9, -2.0), (-2.0, -2.9)) and "they come to" in follow_held_read("follow_held_edge2", (-3.0, -2.0), (-2.0, -2.9)) and "they come to" in follow_held_read("follow_held_edge3", (-2.9, -2.0), (-2.0, -3.0)), "by FOLLOWS_LEAN, on either fit"
assert "they come to" in follow_held_read("follow_held_clear", (-2.0, -3.0), (-3.5, -1.5), se=0.1), "slopes that still differ clearly"
assert f"{follow_gone}FICO loans' purchases (about +1.5 and −2.5), so this" in follow_held_read("follow_held_fico", (-2.0, -3.0), (-3.5, -1.5), purchase_fico=(-2.5, 1.5), other_purchase_vs4=-7.5) and f"{follow_gone}VS4 loans' purchases (about −2.5 and −3.5), so this" in follow_held_read("follow_held_vs4", (-2.0, -3.0), (-3.5, -1.5), other_purchase_fico=-7.5), "only the group the purchases line says follows"
assert "but not on FICO loans' purchases (about −4 and −1), so this" in follow_held_read("follow_held_fico2", (-2.0, -3.0), (-3.5, -1.5), purchase_fico=(-1.0, -4.0), other_purchase_vs4=-7.5) and ", and on VS4 loans' purchases to about −2.5 and −3.5, so this" in follow_held_read("follow_held_vs42", (-4.0, -1.0), (-3.5, -1.5), other_purchase_fico=-7.5), "the other forms, one group"
assert "hold that LLPA and the lean goes, on refinances (VS4 loans about −1 and −1; FICO loans about −0.5 and −2.5) and on FICO loans' purchases (about +1.5 and −2.5), so this" in follow_held_read("follow_held_other_way", (-1.0, -0.75), (-2.5, -0.6), purchase_fico=(-2.5, 1.5), se=0.1, other_purchase_vs4=-7.5), "slopes that part the other way: the lean has gone, not stayed"
assert "purchases (" not in follow_held_read("follow_held_none", (-2.0, -3.0), (-3.5, -1.5), other_purchase_vs4=-7.5, other_purchase_fico=-7.5).split("But the score")[1], "no group follows its score on purchases, so no purchase figure here"
assert "purchases" not in follow_held_read("follow_held_nan", (-2.0, -3.0), (-3.5, -1.5), purchase_fico=(float("nan"), -2.0)).split("But the score")[1], "a purchase fit that does not read"
# Purchases hold on one fit or neither, each in its own words: follow only where it also leans so at Fannie alone, the bracket only on enough Fannie loans of the other group.
read_mix = follow_read("follow_mix", other_purchase_vs4=-7.5)
assert not read_mix[("purchase", "vs4")]["guard"] and read_mix[("refi", "vs4")]["guard"] and read_mix[("all", "vs4")]["sentence"] == f"{follow_head} On purchases FICO loans still follow FICO (about −7.5 and 0); VS4 loans are less clear (about −7.5 and −7.5, and about −7.5 and −7.5 at Fannie alone).{follow_also("FICO loans' purchases to about −7.5 and 0")}", read_mix[("all", "vs4")]
read_mix = follow_read("follow_mix2", other_purchase_fico=-7.5)
assert read_mix[("all", "vs4")]["sentence"] == f"{follow_head} On purchases VS4 loans still follow VS4 (about −7.5 and 0); FICO loans are less clear (about −7.5 and −7.5, and about −7.5 and −7.5 at Fannie alone).{follow_also("VS4 loans' purchases to about −7.5 and 0")}", read_mix[("all", "vs4")]
read_mix = follow_read("follow_mix3", other_purchase_vs4=-7.5, other_purchase_fico=-7.5)
assert read_mix[("all", "vs4")]["sentence"] == f"{follow_head} On purchases VS4 loans move about −7.5 on VS4 and −7.5 on FICO; FICO loans about −7.5 on FICO and −7.5 on VS4.{follow_held}", read_mix[("all", "vs4")]
# The bracket at Fannie alone keeps its own two figures, in the order of those beside it.
read_mix = follow_read("follow_mix7", other_purchase_vs4=-9.0, other_fannie_purchase=3.0)
follow_near = lambda v: pricing._signed(pricing._near(v))  # noqa: E731
assert follow_near(read_mix[("fannie_purchase", "vs4")]["on_vs4"]) != follow_near(read_mix[("fannie_purchase", "vs4")]["on_fico"]) and f", and about {follow_near(read_mix[('fannie_purchase', 'vs4')]['on_vs4'])} and {follow_near(read_mix[('fannie_purchase', 'vs4')]['on_fico'])} at Fannie alone)." in read_mix[("all", "vs4")]["sentence"], (read_mix[("fannie_purchase", "vs4")], read_mix[("all", "vs4")]["sentence"])
# Both hold pooled but not at Fannie: no follow. One group holds pooled and leans the other way at Fannie: no follow either.
read_mix = follow_read("follow_mix4", other_fannie_purchase=-9.0)
assert read_mix[("purchase", "vs4")]["guard"] and read_mix[("purchase", "fico")]["guard"] and not read_mix[("fannie_purchase", "vs4")]["guard"] and " On purchases VS4 loans move about " in read_mix[("all", "vs4")]["sentence"] and " on FICO; FICO loans about " in read_mix[("all", "vs4")]["sentence"] and "follow" not in read_mix[("all", "vs4")]["sentence"], read_mix[("all", "vs4")]["sentence"]
read_mix = follow_read("follow_mix5", other_purchase_vs4=-7.5, other_fannie_purchase=-9.0)
assert not read_mix[("purchase", "vs4")]["guard"] and " On purchases VS4 loans move about " in read_mix[("all", "vs4")]["sentence"] and "follow" not in read_mix[("all", "vs4")]["sentence"], read_mix[("all", "vs4")]["sentence"]
read_mix = follow_read("follow_mix6", other_purchase_fico=-7.5, other_fannie_purchase=-9.0)
assert not read_mix[("purchase", "fico")]["guard"] and " On purchases VS4 loans move about " in read_mix[("all", "vs4")]["sentence"] and "follow" not in read_mix[("all", "vs4")]["sentence"], read_mix[("all", "vs4")]["sentence"]
# One group holds on purchases but runs the other way at Fannie alone: no "still follow", either way round.
for flip_group, flip_group_key, flip_slope, flip_other in (("C", "fico", "on_fico", {"other_purchase_vs4": -7.5}), ("V", "vs4", "on_vs4", {"other_purchase_fico": -7.5})):
    flip_book = follow_book(**flip_other)
    for r in flip_book:
        if r["purpose"] == "P" and r["score_model"] == flip_group and r["agency"] == "FNMA":
            r["orig_rate"] = round(r["orig_rate"] + 1.2 * 0.075 * r["pricing_score"] / 20, 3)
    c_flip = rate_con(flip_book, f"follow_flip_{flip_group}")
    read_flip = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c_flip), dict(c_flip.execute("SELECT id, short FROM entity_names").fetchall()))}
    assert read_flip[("fannie_purchase", flip_group_key)][flip_slope] > 0 > read_flip[("purchase", flip_group_key)][flip_slope] and " On purchases VS4 loans move about " in read_flip[("all", "vs4")]["sentence"] and "follow" not in read_flip[("all", "vs4")]["sentence"], read_flip[("all", "vs4")]["sentence"]
# One group holds and the other's slopes do not: the other is less clear, either way round, its bracket only on 300+ of its loans at Fannie. Here the rate stops moving with the score on the other group's purchases.
for flat_group, kept in (("V", "fico"), ("C", "vs4")):
    flat_book = follow_book()
    for r in flat_book:
        if r["purpose"] == "P" and r["score_model"] == flat_group:
            r["orig_rate"] = round(r["orig_rate"] + 0.075 * r["pricing_score"] / 20, 3)
    c_flat = rate_con(flat_book, f"follow_flat_{flat_group}")
    read_flat = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c_flat), dict(c_flat.execute("SELECT id, short FROM entity_names").fetchall()))}
    assert (f" On purchases FICO loans still follow FICO (about −7.5 and 0); VS4 loans are less clear (about " if kept == "fico" else f" On purchases VS4 loans still follow VS4 (about −7.5 and 0); FICO loans are less clear (about ") in read_flat[("all", "vs4")]["sentence"] and " at Fannie alone)." in read_flat[("all", "vs4")]["sentence"], (flat_group, kept, read_flat[("purchase", "vs4")], read_flat[("all", "vs4")]["sentence"])
    flat_out = set([r["loan_id"] for r in flat_book if r["agency"] == "FNMA" and r["score_model"] == flat_group and r["purpose"] == "P"][100:])
    flat_few = [r for r in flat_book if r["loan_id"] not in flat_out]
    c_flat_few = rate_con(flat_few, f"follow_flat_few_{flat_group}")
    read_flat_few = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c_flat_few), dict(c_flat_few.execute("SELECT id, short FROM entity_names").fetchall()))}
    assert 2 < read_flat_few[("fannie_purchase", "vs4" if flat_group == "V" else "fico")]["n"] < 300 and "are less clear (about " in read_flat_few[("all", "vs4")]["sentence"] and "at Fannie alone" not in read_flat_few[("all", "vs4")]["sentence"], read_flat_few[("all", "vs4")]["sentence"]
# Too few purchases: refinances alone.
few_purchases = [r for i, r in enumerate(follow_book()) if r["purpose"] != "P" or i % 40 == 0]
c_few_p = rate_con(few_purchases, "follow_few_p")
read_few_p = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c_few_p), dict(c_few_p.execute("SELECT id, short FROM entity_names").fetchall()))}
assert read_few_p[("purchase", "vs4")]["n"] < 1000 and read_few_p[("all", "vs4")]["sentence"] == f"{follow_head}{follow_held}", read_few_p[("all", "vs4")]
# Refinances must hold, and Fannie refinances lean the same way: the used slope 1.5 times the other's in both fits, a softer check, since Fannie alone has fewer loans.
assert follow_read("follow_refi", other_refi=-7.5)[("all", "vs4")]["sentence"] is None, "refinances do not hold"
read_freddie = follow_read("follow_freddie", other_freddie_refi=-16.0)
assert not read_freddie[("refi", "vs4")]["guard"] and read_freddie[("fannie_refi", "vs4")]["guard"] and read_freddie[("all", "vs4")]["sentence"] is None, "Fannie leaning is not enough"
read_near = follow_read("follow_near", other_fannie_refi=-4.5)
assert read_near[("all", "vs4")]["sentence"] and read_near[("refi", "vs4")]["guard"], read_near[("refi", "vs4")]
read_far = follow_read("follow_far", other_fannie_refi=-5.5)
assert read_far[("refi", "vs4")]["guard"] and read_far[("all", "vs4")]["sentence"] is None, read_far[("refi", "vs4")]
# A lender group that merely has too few loans holds nothing.
assert "other score" not in follow_read("follow_uwm", other_uwm=-9.0)[("all", "vs4")]["sentence"] and not follow_read("follow_uwm", other_uwm=-9.0)[("uwm", "vs4")]["guard"], "no sentence names a lender group"
assert not follow_read("follow_rocket", other_rocket_broker=-9.0)[("rocket_broker", "vs4")]["guard"], "by lender group, in the table"
few_uwm = [r for i, r in enumerate(follow_book()) if r["seller"] == "rocket-mortgage" or i < 1200]
for r in few_uwm:
    if r["seller"] != "rocket-mortgage":
        r["orig_rate"] = round(r["orig_rate"] + 0.035 * r["vs4"] / 20 * (1 if r["score_model"] == "C" else 0) + 0.035 * r["classic_fico"] / 20 * (1 if r["score_model"] == "V" else 0), 3)
c_few = rate_con(few_uwm, "follow_few")
read_few = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c_few), dict(c_few.execute("SELECT id, short FROM entity_names").fetchall()))}
assert read_few[("rocket_retail", "vs4")]["guard"] and not read_few[("uwm", "vs4")]["guard"] and read_few[("uwm", "vs4")]["n"] < 300, read_few[("uwm", "vs4")]
read_thin = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(rate_con(follow_book()[:900], "follow_thin")), {})}
assert not read_thin[("all", "vs4")]["guard"] and read_thin[("all", "vs4")]["sentence"] is None and read_thin[("all", "vs4")]["on_vs4_se"] is not None, read_thin
# The pooled scopes need 8 lender-weeks.
follow_short = [r for r in follow_book() if r["first_intraday_date"] in {w[0] for w in FOLLOW_WEEKS[:3]}]
c_short = rate_con(follow_short, "x_short")
read_short = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c_short), dict(c_short.execute("SELECT id, short FROM entity_names").fetchall()))}
assert read_short[("all", "vs4")]["n"] >= 1000 and read_short[("all", "vs4")]["lender_weeks"] < 8 and not read_short[("all", "vs4")]["guard"] and read_short[("rocket_retail", "vs4")]["guard"], read_short[("all", "vs4")]
follow_noisy, noisy_rng = follow_book(), random.Random(29)
for r in follow_noisy:
    if r["seller"] == "united-wholesale-mortgage":
        r["orig_rate"] = round(6.5 + noisy_rng.uniform(-0.2, 0.2), 3)
c_noisy = rate_con(follow_noisy, "x_noisy")
read_noisy = {(r["scope"], r["group"]): r for r in pricing._follows(pricing._sample(c_noisy), dict(c_noisy.execute("SELECT id, short FROM entity_names").fetchall()))}
assert read_noisy[("rocket_retail", "vs4")]["guard"] and not read_noisy[("uwm", "vs4")]["guard"] and read_noisy[("uwm", "vs4")]["n"] >= 300 and read_noisy[("all", "vs4")]["sentence"], (read_noisy[("uwm", "vs4")], read_noisy[("uwm", "fico")])
# The checks word themselves for the weekly report, and warn only.
said_checks = pricing.check_warnings([{"view": "check", "label": "A check", "value": 2.5, "limit": 1.5, "pass": False, "detail": "On these loans."}, {"view": "check", "label": "Thin", "value": None, "limit": 2, "pass": None, "detail": None}, {"view": "check", "label": "Fine", "value": 0.1, "limit": 1.5, "pass": True}, {"view": "check", "label": "Rates", "value": 3, "limit": 0, "unit": "loans", "pass": False, "detail": None}, {"view": "row"}])
assert len(said_checks) == 3 and said_checks[0] == "rate check: A check reads +2.50 bp, past its limit of 1.5. On these loans." and "could not be read" in said_checks[1] and said_checks[2] == "rate check: Rates counts 3, past its limit of 0.", said_checks
# A fourth check counts the note rates no loan should carry, and warns only.
wild_book = rate_book(gap=4)
wild_book[5]["orig_rate"], wild_book[7]["orig_rate"] = 15.25, 1.25
wild_check = next(r for r in rate_views(pricing.build_rates(rate_con(wild_book, "wild")))["check"] if r["key"] == "rate_range")
assert wild_check["value"] == 2 and wild_check["limit"] == 0 and wild_check["pass"] is False and wild_check["unit"] == "loans" and wild_check["detail"].startswith("2 loans of ") and wild_check["n"] == len(wild_book), wild_check
fine_check = next(r for r in views["check"] if r["key"] == "rate_range")
assert fine_check["pass"] is True and fine_check["value"] == 0 and "0 loans" not in fine_check["detail"] and next(r for r in views["check"] if r["key"] == "cells")["unit"] == "bp", fine_check
# The same-number chart's month rows: a dot from the two cell reads, a spread across all three, printed by the one rule. lo and hi stay the model's 95%. A month with no loans is blank, and nothing else carries these.
months_a = [r for r in views["same_number"] if r["scope"] == "month"]
month_stake = [r for r in months_a if r["group"] == "stake"]
assert len(month_stake) == 3 and all(r["n"] and abs(r["dot_raw"] - 4) < 1.5 for r in month_stake) and {(r["group"], r["label"]) for r in months_a} == {("stake", "Old rule would raise LLPA"), ("no_stake", "Old rule would not")}, month_stake
for r in month_stake:
    assert abs(r["dot_raw"] - (r["cell5"] + r["tier"]) / 2) <= 0.01 and r["lo_raw"] == min(r["cell5"], r["tier"], r["gap"]) and r["hi_raw"] == max(r["cell5"], r["tier"], r["gap"]), r
    assert (r["dot"], r["spread_lo"], r["spread_hi"]) == pricing.printed(r["dot_raw"], r["lo_raw"], r["hi_raw"]) and abs(r["lo"] - (r["gap"] - 1.96 * r["se"])) <= 0.02 and abs(r["hi"] - (r["gap"] + 1.96 * r["se"])) <= 0.02, r
assert all(r["n"] == 0 and r["dot_raw"] is None and r["lo_raw"] is None and r["hi_raw"] is None and r["dot"] is None and r["spread_lo"] is None and r["spread_hi"] is None for r in months_a if r["group"] == "no_stake"), months_a
assert all(r["dot_raw"] is None and r["dot"] is None and r["spread_lo"] is None for r in views["same_number"] if r["scope"] not in ("month", "gapband", "less20")) and all(r["spread_lo"] is None for v, rs in views.items() if v not in ("same_number", "cut", "fico_gap") for r in rs), views["same_number"]
# One cell read under its floor: only the counts stay. Moving the number 6 points takes each VS4 loan out of its comparators' 5-point band and leaves it in their LLPA tier. The rule that takes the dot from what remains stays for the lead rows.
parted_book = rate_book(gap=4)
for r in parted_book:
    if r["score_model"] == "V" and r["issue_month"] >= "2026-10-01" and r["pricing_score"] < 820:
        r["vs4"] = r["pricing_score"] = r["pricing_score"] + 6
parted = next(r for r in rate_views(pricing.build_rates(rate_con(parted_book, "parted")))["same_number"] if r["key"] == "stake|2026-09-01")
assert parted["n"] >= 100 and parted["read5"] == parted["read"] == 0 and parted["read_tier"] >= 100 and parted["thin"] and all(parted[k] is None for k in ("cell5", "tier", "gap", "se", "dot_raw", "lo_raw", "dot", "spread_lo")), parted
assert pricing._three(float("nan"), 4.5, 6.0)[:3] == (4.5, 4.5, 6.0) and pricing._three(float("nan"), float("nan"), 6.0)[0] is None
# Both cell reads missing: no FICO loans issued from October. The fit alone is no dot, and the sentences that need those loans go, while the rest of the file stands.
views_cold = rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=4) if not (r["score_model"] == "C" and r["issue_month"] >= "2026-10-01")], "cold")))
cold = next(r for r in views_cold["same_number"] if r["key"] == "stake|2026-09-01")
assert cold["n"] and cold["cell5"] is None and cold["tier"] is None and cold["gap"] is None and cold["dot_raw"] is None and cold["dot"] is None and cold["spread_lo"] is None and cold["lo_raw"] is None, cold
meta_cold = views_cold["meta"][0]
assert meta_cold["milliman_line"] is None and meta_cold["said_check"] is None and meta_cold["stamp_more"] is not None and meta_cold["answer"], meta_cold
# The stamp says what each loan is set against, with the GSEs in the sample; how the three methods work has its own field. Who is left out and which grid sorts the rows are limits: Rocket correspondent's clause goes with its reason, and the old rule's clause goes with where these rates closed.
stamp_said = "VS4 loans (those priced on VS4, Rocket correspondent left out) are compared with FICO loans of the same lender, channel, week first disclosed, closing month, GSE, purpose, LTV range and score (within 5 points or one LLPA tier), where a match exists, on 30-year fixed loans."
left_none = "Left out of same FICO: VS4 loans showing no FICO (unknown, not counted as having none)."
left_both = f"{left_none} Left out of every all-lender rate row: Rocket correspondent, not like for like."
grid_head = "Which grid: lower and same LLPA are sorted on the one grid in force since Oct 1"
grid_tail = "; most of these rates were likely set earlier, under the old rule that counted VS4 20 points lower."
limit_of = lambda vs, key: next(r["text"] for r in vs["limit"] if r["key"] == key)  # noqa: E731
assert meta_a["stamp"] == stamp_said and limit_of(views, "left_out") == left_both and limit_of(views, "grid") == grid_head + grid_tail, (meta_a["stamp"], views["limit"])  # no low-rate block here, and every loan here closed by September
assert meta_a["rc_reason"] is None and meta_a["sample"] == "The sample holds 1,280 VS4 and 1,850 FICO loans, Rocket correspondent left out.", (meta_a["rc_reason"], meta_a["sample"])
assert pricing._sample_line(pricing._sample(rate_con([r for r in rate_book(gap=4) if (r["seller"], r["channel"]) != ("rocket-mortgage", "C")], "sample_no_rc"))).endswith(" FICO loans."), "no Rocket correspondent, so none named"
assert meta_a["stamp_more"] == "Three methods: exact match with a 5-point score band; exact match with one LLPA tier as the band (20 points under 640); and a model fitted on FICO loans, by lender and channel where possible, that also controls for occupancy, units, property type, second liens, loan size, DTI, mortgage insurance, state, first-time buyers, number of borrowers and loan program. The dot is the midpoint of the first two and the bar the range across all three. Closing month is estimated from the first payment date. The grid matches Fannie Mae's matrix of Sep 30, 2026.", meta_a["stamp_more"]
rc_planted = rate_book(gap=4)
for i, r in enumerate(rc_planted):
    if (r["seller"], r["channel"]) == ("rocket-mortgage", "C"):
        if r["score_model"] == "V" and i % 2:
            r["purpose"] = "C"
        elif r["score_model"] == "C" and i % 4 == 0:
            r["orig_rate"] = 5.25
views_rc = rate_views(pricing.build_rates(rate_con(rc_planted, "rc")))
rc_said = views_rc["meta"][0]["rc_reason"]
assert re.fullmatch(r"\d+% of its FICO loans carry a rate of 5\.5% or lower, against 0% of its VS4 loans", rc_said), rc_said
assert limit_of(views_rc, "left_out") == left_both and views_rc["meta"][0]["stamp"] == stamp_said, views_rc["limit"]  # its reason prints on the lender card, from rc_reason
assert pricing._left_out() == left_both and pricing._left_out(False) == left_none, "its clause under its guard"
assert pricing._grid_line(0.5) == grid_head + "." and pricing._grid_line(0.51) == grid_head + grid_tail and pricing._grid_line(float("nan")) == grid_head + ".", "most of these rates only while most closed by then"
assert "on 30-year fixed Fannie loans." in pricing._stamp({"FNMA"}) and "on 30-year fixed Freddie loans." in pricing._stamp({"FHLMC"}) and pricing._stamp({"FNMA", "FHLMC"}, False).startswith("VS4 loans (those priced on VS4) are compared"), "what is named is in the sample"
fannie_only = rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=4) if r["agency"] == "FNMA" and (r["seller"], r["channel"]) != ("rocket-mortgage", "C")], "fannie_only")))
assert "on 30-year fixed Fannie loans." in fannie_only["meta"][0]["stamp"] and limit_of(fannie_only, "left_out") == left_none and [r["key"] for r in fannie_only["limit"]].index("left_out") < [r["key"] for r in fannie_only["limit"]].index("grid") < [r["key"] for r in fannie_only["limit"]].index("thin"), fannie_only["limit"]
oct_closed = rate_views(pricing.build_rates(rate_con([{**r, "first_pay_date": "2026-12-01"} for r in rate_book(gap=4)], "oct_closed")))
assert limit_of(oct_closed, "grid") == grid_head + ".", limit_of(oct_closed, "grid")
assert pricing._rc_shares(pricing._sample(rate_con(rate_book(gap=4), "rc_same"))) is None and pricing._rc_shares(pricing._sample(rate_con([r for r in rc_planted if r["seller"] != "rocket-mortgage" or r["channel"] != "C"], "rc_none"))) is None
rc_small = [r for i, r in enumerate(rc_planted) if (r["seller"], r["channel"]) != ("rocket-mortgage", "C") or r["score_model"] == "C" or i % 4 == 0]
assert pricing._rc_shares(pricing._sample(rate_con(rc_small, "x_rcsmall"))) is None, "under 100 of its VS4 loans, no reason"
assert pricing._pct(0.003) == "0.3%" and pricing._pct(0.0) == "0%" and pricing._pct(0.274) == "27%", (pricing._pct(0.003), pricing._pct(0.0))
# Beside Milliman: said_check is this line's first two sentences and its last two. Names only lenders present, and keeps Rocket correspondent only while such a loan is in the window.
milliman_two, milliman_rest = meta_a["milliman_line"].split(" Without channel, ")
assert milliman_two.startswith("Not the same comparison: Milliman takes 20 points off VS4 first and holds the LLPA. On that basis, with channel and finer score bands held, about ") and re.search(r" on loans closed and issued May to August, its window \(about [+−\d.]+ on those first disclosed from Jul 20, where the other figures here start\), and about ", milliman_two) and milliman_two.endswith(" on Rocket and UWM loans issued from Oct 1."), meta_a["milliman_line"]
assert re.fullmatch(r"with VS4 820\+ and Rocket correspondent kept, about [+−\d.]+ in its window; any gap left to its figure is not explained here\.", milliman_rest), milliman_rest
# The window has a date base of its own. The bracket reads it on loans first disclosed from Jul 20, both sides, under its pool floor; else it says the window reaches back, while a VS4 loan in it does; else nothing.
window_weeks = {w[0] for w in RATE_WEEKS if w[1] <= "2026-08-01"}
early_window = [{**r, "first_intraday_date": "2026-07-06"} if r["score_model"] == "V" and r["first_intraday_date"] in window_weeks else r for r in rate_book(gap=4, vs4_a_week=100)]
early_line = rate_views(pricing.build_rates(rate_con(early_window, "x_early_window")))["meta"][0]
assert " its window (which reaches back before Jul 20), and about " in early_line["milliman_line"] and early_line["said_check"].startswith(early_line["milliman_line"].split(" Without channel, ")[0]), early_line["milliman_line"]
early_some = rate_book(gap=4) + [rate_row(986000 + k, "rocket-mortgage", "R", ("2026-07-06", "2026-08-01", "2026-07-01"), 9.5, "V", 700, 721) for k in range(120)]
views_some = rate_views(pricing.build_rates(rate_con(early_some, "x_early_some")))
mil_some = {r["key"]: r for r in views_some["milliman"]}
assert mil_some["window"]["reaches_back"] is True and mil_some["window"]["pool"] == mil_some["window_late"]["pool"] + 120 and mil_some["window"]["cell5"] > mil_some["window_late"]["cell5"] + 5 and mil_some["window_late"]["reaches_back"] is None and f" its window (about {pricing._signed(pricing._near((mil_some['window_late']['cell5'] + mil_some['window_late']['tier']) / 2))} on those first disclosed from Jul 20, where the other figures here start), and about " in views_some["meta"][0]["milliman_line"], views_some["meta"][0]["milliman_line"]
late_few = [{**r, "first_intraday_date": "2026-07-06"} if r["score_model"] == "V" and r["first_intraday_date"] in window_weeks and int(r["loan_id"][1:]) % 40 else r for r in rate_book(gap=4)]
assert next(r for r in rate_views(pricing.build_rates(rate_con(late_few, "x_late_few")))["milliman"] if r["key"] == "window_late")["cell5"] is None and " its window (which reaches back before Jul 20), and about " in rate_views(pricing.build_rates(rate_con(late_few, "x_late_few2")))["meta"][0]["milliman_line"], "under its pool floor"
early_fico = [{**r, "first_intraday_date": "2026-07-06"} if r["score_model"] == "C" and r["first_intraday_date"] in window_weeks else r for r in rate_book(gap=4)]
assert " its window, and about " in rate_views(pricing.build_rates(rate_con(early_fico, "x_early_fico")))["meta"][0]["milliman_line"], "no comparable loan from Jul 20 and no VS4 loan reaching back: nothing"
assert next(r for r in views["milliman"] if r["key"] == "window")["reaches_back"] is False and next(r for r in views["milliman"] if r["key"] == "window_plain")["label"] == "May to August, no channel in the cell, VS4 820+ and Rocket correspondent kept" and next(r for r in views["milliman"] if r["key"] == "window_late")["label"] == "Rocket and UWM, closed and issued May to August, first disclosed from Jul 20", views["milliman"]
assert meta_a["said_check"] == milliman_two + " Same score number under 820 is about +4 bp, data through Oct 19. See Rates.", meta_a["said_check"]
no_rc_line = rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=4) if (r["seller"], r["channel"]) != ("rocket-mortgage", "C")], "no_rc_line")))["meta"][0]["milliman_line"]
assert "with VS4 820+ kept, about " in no_rc_line and "Rocket correspondent" not in no_rc_line, no_rc_line
uwm_only_views = rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=4) if r["seller"] != "rocket-mortgage"], "uwm_only")))
uwm_only_line = uwm_only_views["meta"][0]["milliman_line"]
assert " on UWM loans issued from Oct 1." in uwm_only_line and "Rocket" not in uwm_only_line and all(r["label"].startswith("UWM, ") for r in uwm_only_views["milliman"] if r["key"] != "window_plain"), uwm_only_line
small_line = [r for r in rate_views(pricing.build_rates(rate_con(rate_book(gap=4, vs4_a_week=3), "small_line")))["milliman"] if r["key"] != "window_plain"]
assert all(r["pool"] < 100 and r["cell5"] is None and r["tier"] is None and r["read"] for r in small_line), small_line
# The line stands on its own reads, and said_check also needs the same-number figure: here a VS4 number has no FICO loans at it, in band or tier, and VS4 less 20 sits right on them.
far_book, far_rng = [], random.Random(11)
for w, week in enumerate(RATE_WEEKS):
    for k in range(60):
        far_book.append(rate_row(1000 * w + 2 * k, "rocket-mortgage", "R", week, rate_rate(far_rng, "rocket-mortgage|R", w, 700), "C", 700, agency="FNMA"))
        far_book.append(rate_row(1000 * w + 2 * k + 1, "rocket-mortgage", "R", week, rate_rate(far_rng, "rocket-mortgage|R", w, 700) + 0.02, "V", None, 721, agency="FNMA"))
views_far = rate_views(pricing.build_rates(rate_con(far_book, "far")))
assert next(r for r in views_far["row"] if r["key"] == "same_number")["dot"] is None and views_far["meta"][0]["said_check"] is None and views_far["meta"][0]["milliman_line"].startswith("Not the same comparison"), views_far["meta"][0]
assert next(r for r in views["steps"] if r["key"] == "traits_under")["pool"] == next(r for r in views["steps"] if r["key"] == "number")["pool"] and next(r for r in views["steps"] if r["key"] == "traits_under")["pool"] < next(r for r in views["steps"] if r["key"] == "traits")["pool"], views["steps"]
# The test row in words: what it should show and why, and each lender outside the rule with enough loans, by channel where two have 50+; thin evidence for those at or below −3, as there while every lender printed is; a lender with too few such loans is named as untested; on a miss, a figure past the limit as printed; nothing when it could not be read. One lender's share stays on Method's check.
planted_test = {"pass": True, "value": 0.4, "limit": 2.0, "rocket": 2.2, "rocket_n": 400, "uwm": -4.3, "uwm_n": 1200, "uwm_correspondent": 0.1, "uwm_correspondent_n": 500, "uwm_broker": -6.2, "uwm_broker_n": 700, "top_share": 0.71, "without_top": -1.3, "without_top_n": 300}
first_clause = "A test: FICO loans with VS4 20+ above their FICO should show about 0 if a high VS4 lowers the rate only when it is the score picked."
at_rare, at_rocket = "about +0.5 at lenders that rarely use VS4", "about +2 at Rocket on 400 loans"
by_channel = "about −4.5 at UWM on 1,200 loans (about −6 on its 700 broker loans, about 0 on its 500 correspondent loans)"
evidence = lambda where: f": thin evidence that a high VS4 goes with a lower rate {where} even on FICO loans"  # noqa: E731
for changed, want in [({}, f"{first_clause} They show {at_rare}, {at_rocket} and {by_channel}{evidence('at UWM')}."),
                      ({"rocket": -4.2, "uwm": 2.2, "uwm_correspondent_n": 0}, f"{first_clause} They show {at_rare}, about −4 at Rocket on 400 loans and about +2 at UWM on 1,200 loans{evidence('at Rocket')}."),
                      ({"rocket": -4.2}, f"{first_clause} They show {at_rare}, about −4 at Rocket on 400 loans and {by_channel}{evidence('there')}."),
                      ({"top_share": 0.5}, f"{first_clause} They show {at_rare}, {at_rocket} and {by_channel}{evidence('at UWM')}."),
                      ({"top_share": 0.29, "rocket_n": 99}, f"{first_clause} They show {at_rare} and {by_channel}{evidence('there')}. Rocket has too few such loans to test (99)."),
                      ({"without_top_n": 99, "uwm_n": 99}, f"{first_clause} They show {at_rare} and {at_rocket}. UWM has too few such loans to test (99)."),
                      ({"uwm": -2.9, "rocket_n": 0, "rocket": None}, f"{first_clause} They show {at_rare} and about −3 at UWM on 1,200 loans (about −6 on its 700 broker loans, about 0 on its 500 correspondent loans)."),
                      ({"uwm": -3.0, "rocket_n": 0, "rocket": None}, f"{first_clause} They show {at_rare} and about −3 at UWM on 1,200 loans (about −6 on its 700 broker loans, about 0 on its 500 correspondent loans){evidence('there')}."),
                      ({"uwm_correspondent_n": 49, "rocket_n": 0, "rocket": None}, f"{first_clause} They show {at_rare} and about −4.5 at UWM on 1,200 loans{evidence('there')}."),
                      ({"uwm": 2.2, "rocket_n": 0, "rocket": None, "uwm_correspondent_n": 49}, f"{first_clause} They show {at_rare} and about +2 at UWM on 1,200 loans."),
                      ({"rocket_n": 0, "rocket": None, "uwm_n": 0, "uwm": None}, f"{first_clause} They show {at_rare}."),
                      ({"pass": False, "value": -3.3}, f"{first_clause} They show −3.5 at lenders that rarely use VS4, past the 2 bp limit, so treat these figures with care."),
                      ({"pass": False, "value": 2.1}, f"{first_clause} They show +2.5 at lenders that rarely use VS4, past the 2 bp limit, so treat these figures with care."),
                      ({"pass": None, "value": None}, None)]:
    assert pricing._test_line({**planted_test, **changed}) == want, (changed, pricing._test_line({**planted_test, **changed}))
assert "one lender" not in pricing._test_line(planted_test), "its share stays on Method's check"
assert meta_a["test_line"] is None, "no FICO loan here shows a VS4, so the test could not be read"
# How much to expect at the same LLPA: each ending goes with where the row's printed ends sit against the printed full credit and zero; none where they say none of the three, where full credit would not sit below zero as printed, or with no ends.
expect_head = "How much to expect: below FICO 780, full credit for the VS4 number (priced like the same FICO number) would be about −6.5, against "
for credit, lo, hi, want in [(-6.5, -8.5, 2.5, "−8.5 to +2.5 across the methods, so this row cannot tell full credit from none."), (-6.5, -9.5, -7.0, "−9.5 to −7 across the methods, so this row is at or past full credit."), (-6.5, -3.5, 0.5, "−3.5 to +0.5 across the methods, so this row falls short of full credit."),
                             (-6.5, -10.0, -6.5, "−10 to −6.5 across the methods, so this row is at or past full credit."),
                             (-6.5, 1.0, 3.5, None), (-6.5, -8.5, -1.5, None), (1.5, -8.5, 2.5, None), (-0.2, -8.5, 2.5, None), (float("nan"), -8.5, 2.5, None), (-6.5, None, None, None)]:
    assert pricing._expected_words(credit, lo, hi) == (expect_head + want if want else None), (credit, lo, hi, pricing._expected_words(credit, lo, hi))
# The ending goes on what prints: a low end and a full credit that print alike cannot be short of each other, nor a high end at the printed value short of being past it.
for credit, lo, hi in [(-3.6, -3.5, 2.0), (-3.26, -3.5, 2.0), (-3.74, -3.5, 2.0)]:
    assert pricing._expected_words(credit, lo, hi).endswith(", so this row cannot tell full credit from none."), (credit, lo, hi, pricing._expected_words(credit, lo, hi))
assert pricing._expected_words(-5.1, -7.5, -5.0).endswith(", so this row is at or past full credit.") and pricing._expected_words(-6.01, -5.5, 0.5).endswith(", so this row falls short of full credit."), "at or past while the high end prints at or below, short while the low end prints above"
assert meta_a["expected"] is None and views_b["meta"][0]["expected"] is None, "no FICO loan here at 780+, so nothing says how much to expect"


def split_book(low=-6.5, high=5.5, swing=0.0, top_slope=0.0, low_uwm=None):
    """Same-LLPA VS4 loans 15 points above FICO inside one LLPA tier: half at FICO 700, half at FICO 790, each at its planted gap. FICO loans' rates fall 7.5 bp per 20 points under 780 and move top_slope bp per 20 points past it. swing: bp on the low loans, one sign or the other by lender-week. low_uwm: the low loans' gap at UWM, if not the same. VS4 loans in a waived program have the same LLPA on any grid."""
    rng, out, i = random.Random(41), [], 0
    curve = lambda f: 0.075 * (780 - min(f, 780)) / 20 + top_slope / 100 * (max(f, 780) - 780) / 20  # noqa: E731
    for seller, channel in (("rocket-mortgage", "R"), ("united-wholesale-mortgage", "B")):
        for w, week in enumerate(RATE_WEEKS):
            agency = "FNMA" if w % 2 else "FHLMC"
            base = 6.5 + 0.02 * w
            sign = 1 if (w + len(seller)) % 2 else -1
            for k in range(60):
                for f in (700, 715, 790, 805):
                    out.append(rate_row(i, seller, channel, week, base + curve(f) + rng.uniform(-0.01, 0.01), "C", f, agency=agency, program="H"))
                    i += 1
                out.append(rate_row(i, seller, channel, week, base + curve(700) + ((low_uwm if low_uwm is not None and seller != "rocket-mortgage" else low) + sign * swing) / 100 + rng.uniform(-0.01, 0.01), "V", 700, 715, agency=agency, program="H"))
                out.append(rate_row(i + 1, seller, channel, week, base + curve(790) + high / 100 + rng.uniform(-0.01, 0.01), "V", 790, 805, agency=agency, program="H"))
                i += 2
    return out


s_split = pricing._sample(rate_con(split_book(), "split_book"))
s_split.fits = pricing._fit_all(s_split)
top_flat = pricing._top_slope(s_split)
assert abs(top_flat) < 0.5, top_flat
said_split = pricing._llpa_split(s_split, top_flat)
assert {k: said_split[k] for k in ("high", "low", "flat", "open", "share")} == {"high": 5.5, "low": -5.0, "flat": True, "open": False, "share": 0.5} and not {"middle", "spread"} & set(said_split) and said_split["reads"]["low"]["n"] == 1200 and said_split["reads"]["low"]["mid"] == round((said_split["reads"]["low"]["cell5"] + said_split["reads"]["low"]["tier"]) / 2, 2) and "under" not in said_split["reads"], said_split  # the tier read's comparators run 15 points up here, so the midpoint sits above the plant; both reads clear of zero below 780, so a discount there is read, not left open
assert pricing._split_words(said_split) == "about +5.5 bp at FICO 780+, where rates stop falling with the score, and about −5 bp below 780", pricing._split_words(said_split)
# The share is of the row's own loans: here half the 780+ loans leave the row.
s_share = copy.copy(s_split)
s_share.same = s_split.same.copy()
s_share.same[np.flatnonzero(s_split.tv & s_split.same & (s_split.fico >= 780))[::2]] = False
share_got, share_row, share_all = pricing._llpa_split(s_share, top_flat)["share"], float(np.mean(s_share.fico[s_share.tv & s_share.same] >= 780)), float(np.mean(s_share.fico[s_share.tv] >= 780))
assert share_got == share_row and abs(share_row - share_all) > 0.05, (share_got, share_row, share_all)
# The split's low half and the row under 780 read the same loans, on the same printed rule.
rows_split = pricing._read_rows(s_split)[0]
row_split_low = rows_split["same_llpa_low"]
assert (row_split_low["cell5"], row_split_low["tier"], row_split_low["model"], row_split_low["n"], row_split_low["read5"], row_split_low["read_tier"]) == tuple(said_split["reads"]["low"][k] for k in ("cell5", "tier", "model", "n", "read5", "read_tier")) and row_split_low["dot"] == said_split["low"] and row_split_low["title"] == "of those, FICO under 780" and row_split_low["sub"] == "about 1,200" and not row_split_low["strong"] and row_split_low["sentence"] != "Too few to compare yet." and row_split_low["tl"] is not None and (row_split_low["dot"], row_split_low["lo"], row_split_low["hi"]) == pricing.printed(row_split_low["dot_raw"], row_split_low["lo_raw"], row_split_low["hi_raw"]), row_split_low
assert [r["order"] for r in rows_split.values()] == [0, 1, 2, 3, 4], rows_split
# Part of a row, so its floor is 100 matched loans, not 1,000, as the split's on the same loans; and 8 lender-weeks as any row.
s_floor = pricing._sample(rate_con([r for r in split_book() if r["score_model"] == "C" or r["classic_fico"] != 700 or int(r["loan_id"][1:]) % 9 == 4], "split_floor"))
s_floor.fits = pricing._fit_all(s_floor)
floor_low = pricing._read_rows(s_floor)[0]["same_llpa_low"]
assert 100 <= min(floor_low["read5"], floor_low["read_tier"]) < pricing.ANSWER_N and floor_low["dot"] is not None and floor_low["sentence"] != "Too few to compare yet." and pricing._llpa_split(s_floor, 0.0)["low"] == floor_low["dot"], floor_low
assert pricing.answer_sentence(999, 40, -9.0, -7.0, -8.0, pricing.MIN_ROW) == "About 8 bp lower." and pricing.answer_sentence(99, 40, -9.0, -7.0, -8.0, pricing.MIN_ROW) == "Too few to compare yet." and pricing.answer_sentence(999, 7, -9.0, -7.0, -8.0, pricing.MIN_ROW) == "Too few to compare yet.", "the floor it is given, and the weeks all the same"
gap_kept, s_split.gap_fico = s_split.gap_fico, np.full(s_split.n, np.nan)
assert pricing._llpa_split(s_split, 0.0)["reads"]["low"]["mid"] == said_split["reads"]["low"]["mid"] and pricing._llpa_split(s_split, 0.0)["reads"]["low"]["model"] is None, "the midpoint stands without the model"
s_split.gap_fico = gap_kept
assert pricing._llpa_split(s_split, -1.0)["flat"] and not pricing._llpa_split(s_split, -1.01)["flat"] and not pricing._llpa_split(s_split, float("nan"))["flat"], "rates must have stopped falling"
under_book, under_rng = split_book(), random.Random(23)
for w, week in enumerate(RATE_WEEKS):
    for k in range(30):
        rate = 6.5 + 0.02 * w + 0.075 * 8.5 + under_rng.uniform(-0.01, 0.01)
        under_book.append(rate_row(1020000 + 100 * w + 2 * k, "rocket-mortgage", "R", week, rate, "C", 610, agency="FNMA" if w % 2 else "FHLMC", program="H"))
        under_book.append(rate_row(1020001 + 100 * w + 2 * k, "rocket-mortgage", "R", week, rate - 0.035, "V", 610, 615, agency="FNMA" if w % 2 else "FHLMC", program="H"))
s_under = pricing._sample(rate_con(under_book, "split_under"))
s_under.fits = pricing._fit_all(s_under)
under_reads = pricing._llpa_split(s_under, 0.0)["reads"]
assert under_reads["under"]["n"] == 300 and abs(under_reads["under"]["cell5"] + 3.5) < 0.5 and abs(under_reads["under"]["tier"] + 3.5) < 0.5 and "middle" not in under_reads and under_reads["low"]["n"] == 1500, under_reads["under"]
s_steep = pricing._sample(rate_con(split_book(top_slope=-3.5), "split_steep"))
assert pricing._top_slope(s_steep) < -3, pricing._top_slope(s_steep)
s_open = pricing._sample(rate_con(split_book(swing=20.0), "split_open"))
s_open.fits = pricing._fit_all(s_open)
assert pricing._llpa_split(s_open, 0.0)["open"] is True, pricing._llpa_split(s_open, 0.0)
s_apart = pricing._sample(rate_con(split_book(low=-6.0), "split_apart"))
s_apart.fits = pricing._fit_all(s_apart)
s_apart.gap_fico = np.where(s_apart.tv & s_apart.same & (s_apart.fico < 780), s_apart.gap_fico + 12.0, s_apart.gap_fico)
split_apart = pricing._llpa_split(s_apart, 0.0)
assert split_apart["low"] == pricing._read_rows(s_apart)[0]["same_llpa_low"]["dot"] == -5.0 and pricing._near(split_apart["reads"]["low"]["mid"]) == -4.5, split_apart  # the methods 4+ apart, so whole points, as the row prints it
s_model_open = pricing._sample(rate_con(split_book(), "split_model_open"))
s_model_open.fits = pricing._fit_all(s_model_open)
s_model_open.gap_fico = np.where(s_model_open.tv & s_model_open.same & (s_model_open.fico < 780), s_model_open.gap_fico + np.where(pricing._joint(s_model_open.c_seller, s_model_open.c_week) % 2 == 0, 40.0, -40.0), s_model_open.gap_fico)
assert pricing._llpa_split(s_model_open, 0.0)["open"] is True and said_split["open"] is False, "the tier read clear of zero and the model not: still open"
s_open_up = pricing._sample(rate_con(split_book(low=9.5, low_uwm=-6.0, swing=20.0), "split_open_up"))
s_open_up.fits = pricing._fit_all(s_open_up)
assert pricing._llpa_split(s_open_up, 0.0)["low"] > 0 and pricing._llpa_split(s_open_up, 0.0)["open"] is False, "a read above zero leaves no discount to rule out, though its thin line reaches below"
s_few = pricing._sample(rate_con([r for r in split_book() if r["score_model"] == "C" or r["classic_fico"] != 790 or int(r["loan_id"][1:]) % 40 == 1], "split_few"))
s_few.fits = pricing._fit_all(s_few)
few_split = pricing._llpa_split(s_few, 0.0)
assert few_split["high"] is None and few_split["low"] == -5.0 and pricing._split_words(few_split) is None and "high" not in few_split["reads"] and few_split["share"] < 0.1 and abs(few_split["share"] - (s_few.fico[s_few.tv & s_few.same] >= 780).mean()) < 1e-9, few_split
# The new row too few, through the rows: blank like any row, and the sentences on it go, while the row above it stands.
s_few_row = pricing._sample(rate_con([r for r in split_book() if r["score_model"] == "C" or r["classic_fico"] != 700 or int(r["loan_id"][1:]) % 40 == 0], "split_few_row"))
s_few_row.fits = pricing._fit_all(s_few_row)
few_rows = pricing._read_rows(s_few_row)[0]
few_low = few_rows["same_llpa_low"]
assert few_low["n"] > 0 and few_low["read5"] < 100 and few_low["sentence"] == "Too few to compare yet." and few_low["dot"] is None and few_low["lo"] is None and few_low["hi"] is None and few_low["cell5"] is not None and few_rows["same_llpa"]["dot"] is not None, few_low
few_said = pricing._same_llpa_line(few_rows, pricing._llpa_split(s_few_row, 0.0))
assert " overall" not in few_said and "of these loans are FICO" not in few_said, few_said
few_quote = pricing._split_words({"high": 5.5, "low": -5.0, "flat": True, "open": False}, few_low)
assert "across the methods" not in few_quote, few_quote
# Through the build, on the same loans: the row's own read under 780 and full credit on the loans' own curves.
for low, ending in ((-2.5, "falls short of full credit"), (-9.5, "is at or past full credit")):
    con_expect = rate_con(split_book(low=low), "split_curves")
    s_expect = pricing._sample(con_expect)
    s_expect.fits = pricing._fit_all(s_expect)
    row_expect = pricing._read_rows(s_expect)[0]["same_llpa_low"]
    said_expected = pricing._expected(s_expect, 0.0, row_expect)
    assert re.fullmatch(r"How much to expect: below FICO 780, full credit for the VS4 number \(priced like the same FICO number\) would be about −[\d.]+, against " + re.escape(pricing._range(row_expect["lo"], row_expect["hi"])) + r" across the methods, so this row " + ending + r"\.", said_expected), said_expected
    assert pricing._expected(s_expect, -1.01, row_expect) is None and pricing._expected(s_expect, float("nan"), row_expect) is None and pricing._expected(s_expect, 0.0, {**row_expect, "model": None}) is None and pricing._expected(s_expect, 0.0, {**row_expect, "lo": None, "hi": None}) is None, "rates must have stopped falling at the top, and the row must have its three methods and its ends"
assert rate_views(pricing.build_rates(rate_con(split_book(low=-9.5), "split_build")))["meta"][0]["expected"] == said_expected, "through the build"
assert pricing._expected(pricing._sample(rate_con(rate_book(gap=4), "expect_none")), 0.0, row_a["same_llpa_low"]) is None, "under a quarter of the row at the top"
s_few_low = pricing._sample(rate_con([r for r in split_book(low=-9.5) if r["score_model"] == "C" or r["classic_fico"] != 700 or int(r["loan_id"][1:]) % 40 == 0], "split_few_low"))
s_few_low.fits = pricing._fit_all(s_few_low)
assert pricing._expected(s_few_low, 0.0, pricing._read_rows(s_few_low)[0]["same_llpa_low"]) is None, "under 100 matched loans below the top"
# A same-FICO row with a model read but no comparable loans in its cells has no range to print: the method limit stays out and the build goes on. Its model read stays for the workbook, as it does on any row too few to read.
views_no_cell = rate_views(pricing.build_rates(rate_con([{**r, "ltv": 50} if r["score_model"] == "V" else r for r in rate_book(gap=4)], "no_cell")))
row_no_cell = next(r for r in views_no_cell["row"] if r["key"] == "same_fico")
assert row_no_cell["n"] >= 1000 and row_no_cell["read5"] == 0 and row_no_cell["sentence"] == "Too few to compare yet." and row_no_cell["lo"] is None and row_no_cell["lo_raw"] is not None and row_no_cell["model_n"] > 0, row_no_cell
assert not any(r["key"] == "method" for r in views_no_cell["limit"]), views_no_cell["limit"]
# The same-number chart's caption, from the month rows' two means, by loans, while the figure sits between them; the second line's share with a high VS4 or a low LTV says why the two are not comparable; what is left with 20 points off VS4; and what the FICO gap could be instead, while that is positive and at least half the figure.
caption_rows = [{"scope": "month", "key": "a", "group": "stake", "n": 300, "dot_raw": 8.0}, {"scope": "month", "key": "b", "group": "stake", "n": 100, "dot_raw": 12.0}, {"scope": "month", "key": "c", "group": "stake", "n": 50, "dot_raw": None}, {"scope": "month", "key": "d", "group": "no_stake", "n": 200, "dot_raw": 2.2}]
caption_first = "VS4 640-819 is about 88% of the +4's loans: about +9 where the old rule would raise the LLPA and about +2 on the rest"
caption_mostly = " (mostly VS4 780-819 or LTV 60 or under)."
caption_fell = " Is the old rule why? Take 20 points off VS4 and the +4 falls to about −0.5 to +1.5, which fits."
caption_said = lambda rows_in, dot, share, off20=None, curve=None, part=0.88: " ".join(t for t in pricing._number_lines(rows_in, dot, share, off20, curve, part) if t) or None  # noqa: E731
caption_gap = " But where a FICO shows (loans issued from Oct 1, about one of these in three), it averages about 25 below VS4, worth about 6 bp on FICO loans, and the data cannot separate the rule from the lower FICO."
caption_not_fell = "Where a FICO shows (loans issued from Oct 1, about 71% of these), it averages about 25 below VS4, worth about 6 bp on FICO loans."
for rows_in, dot, share, off20, curve, want in [(caption_rows, 4.0, 0.5, ("−0.5 to +1.5", True), (26.0, 6.2, 0.31, True), caption_first + caption_mostly + caption_fell + caption_gap), (caption_rows, 4.0, 0.49, ("−0.5 to +1.5", True), (26.0, 6.2, 0.31, True), caption_first + "." + caption_fell + caption_gap),
                                                (caption_rows, 4.0, 0.49, None, None, caption_first + "."), (caption_rows, 4.0, 0.49, ("+2 to +3.5", False), None, caption_first + ". Is the old rule why? Take 20 points off VS4 and it is about +2 to +3.5."),
                                                (caption_rows, 4.0, 0.49, ("+2 to +3.5", False), (26.0, 6.2, 0.71, True), caption_first + ". Is the old rule why? Take 20 points off VS4 and it is about +2 to +3.5. " + caption_not_fell),
                                                (caption_rows, 4.0, 0.49, ("−0.5 to +1.5", True), (26.0, 1.9, 0.31, True), caption_first + "." + caption_fell), (caption_rows, 4.0, 0.49, ("−0.5 to +1.5", True), (-3.0, 6.2, 0.31, True), caption_first + "." + caption_fell), (caption_rows, 4.0, 0.49, ("−0.5 to +1.5", True), (26.0, -6.2, 0.31, True), caption_first + "." + caption_fell),
                                                ([{**r, "dot_raw": 4.4} if r.get("group") == "stake" else r for r in caption_rows], 4.0, 0.49, None, None, "VS4 640-819 is about 88% of the +4's loans: about +4.5 where the old rule would raise the LLPA and about +2 on the rest."),
                                                (caption_rows, None, 0.5, None, None, None), (caption_rows, 4.0, float("nan"), None, None, None), (caption_rows[:3], 4.0, 0.5, None, None, None), (caption_rows, 1.6, 0.5, None, None, None), (caption_rows, 10.0, 0.5, None, None, None), (caption_rows, 1.75, 0.49, None, None, "VS4 640-819 is about 88% of the +1.75's loans: about +9 where the old rule would raise the LLPA and about +2 on the rest.")]:
    assert caption_said(rows_in, dot, share, off20, curve) == want, (dot, share, off20, curve, caption_said(rows_in, dot, share, off20, curve), want)
assert caption_said(caption_rows, 4.0, 0.49, None, None, None) == "On VS4 640-819, the +4 averages about +9 where the old rule would raise the LLPA and about +2 on the rest.", "no share to give"
# Loans issued from Oct 1, only while all of them are.
assert pricing._number_lines(caption_rows, 4.0, 0.49, ("−0.5 to +1.5", True), (26.0, 6.2, 0.31, False), 0.88)[1] == (caption_fell + caption_gap.replace("(loans issued from Oct 1, about", "(about")).strip(), pricing._number_lines(caption_rows, 4.0, 0.49, ("−0.5 to +1.5", True), (26.0, 6.2, 0.31, False), 0.88)
# The same lines apart: the blend, then the old rule's line with its head, which goes with what it has to say. The curve's sentences can stand with nothing off VS4.
assert caption_said([{**caption_rows[0], "dot_raw": 3.2}, {**caption_rows[3], "dot_raw": -2.6}], 0.0, 0.49, None, None) == "VS4 640-819 is about 88% of the same-number figure's loans: about +3 where the old rule would raise the LLPA and about −2.5 on the rest.", "a figure printing as zero is named in words"
assert pricing._number_lines(caption_rows, 4.0, 0.49, None, None, 0.88) == (caption_first + ".", None) and pricing._number_lines(caption_rows, None, 0.5, None, None) == (None, None), "no head with nothing after it"
assert pricing._number_lines(caption_rows, 4.0, 0.5, ("−0.5 to +1.5", True), (26.0, 6.2, 0.31, True), 0.88) == (caption_first + caption_mostly, (caption_fell + caption_gap).strip())
assert pricing._number_lines(caption_rows, 4.0, 0.49, None, (26.0, 6.2, 0.71, True))[1] == "Is the old rule why? " + caption_not_fell, pricing._number_lines(caption_rows, 4.0, 0.49, None, (26.0, 6.2, 0.71, True))
assert pricing._off20_words({"dot_raw": 0.4, "lo_raw": -0.3, "hi_raw": 1.2}, 4.0) == ("−0.5 to +1.5", True) and pricing._off20_words({"dot_raw": 2.0, "lo_raw": 2.0, "hi_raw": 3.2}, 4.0) == ("+2 to +3.5", False) and pricing._off20_words({"dot_raw": None}, 4.0) is None and pricing._off20_words({"dot_raw": 0.4, "lo_raw": -0.3, "hi_raw": 1.2}, None) is None, "a third of the figure"
caption_down = [{**r, "dot_raw": -r["dot_raw"]} if r["dot_raw"] is not None else r for r in caption_rows]
assert caption_said(caption_down, -4.0, 0.49, None, (26.0, 6.2, 0.31, True)) == "VS4 640-819 is about 88% of the −4's loans: about −9 where the old rule would raise the LLPA and about −2 on the rest.", "short of its number only above it"
share_week = RATE_WEEKS[0]
share_book = [rate_row(i, "other-bank", "R", share_week, 6.5, "V", 700, vs, ltv=ltv, program="H") for i, (vs, ltv) in enumerate([(701, 50)] * 3 + [(790, 80)] * 3 + [(701, 80)] * 4)]
share_book += [rate_row(100 + i, "other-bank", "R", share_week, 6.5, "V", 700, vs, ltv=50, program="H") for i, vs in enumerate((630, 830))]
share_book += [rate_row(200, "rocket-mortgage", "C", share_week, 6.5, "V", 700, 790, ltv=50, program="H"), rate_row(201, "other-bank", "R", ("2026-08-03", "2026-07-01", "2026-05-01"), 6.5, "V", 700, 790, ltv=50, program="H"), rate_row(202, "other-bank", "R", share_week, 6.5, "V", 700, 790, ltv=80)]
assert abs(pricing._no_stake_share(pricing._sample(rate_con(share_book, "share"))) - 0.6) < 1e-9
assert np.isnan(pricing._no_stake_share(pricing._sample(rate_con(share_book[10:], "share_none"))))
assert meta_a["number_caption"] is None and meta_a["number_blend"] is None and meta_a["number_why"] is None, "no loan here on the second line, so there is nothing to caption"
# And through the build: half the VS4 loans in a waived program, so with no LLPA to step; the first line carries more.
blended_book = rate_book(gap=4)
for i, r in enumerate(blended_book):
    if r["score_model"] == "V" and i % 2:
        r["special_program"] = "H"
    elif r["score_model"] == "V":
        r["orig_rate"] = round(r["orig_rate"] + 0.05, 3)
blended = rate_views(pricing.build_rates(rate_con(blended_book, "blended")))
assert blended["meta"][0]["number_caption"].startswith("VS4 640-819 is about 100% of the +") and " where the old rule would raise the LLPA and about +" in blended["meta"][0]["number_caption"] and "mostly" not in blended["meta"][0]["number_caption"], blended["meta"][0]["number_caption"]
assert blended["meta"][0]["number_caption"] == " ".join(t for t in (blended["meta"][0]["number_blend"], blended["meta"][0]["number_why"]) if t) and blended["meta"][0]["number_blend"].startswith("VS4 640-819 is about "), blended["meta"][0]
# With 20 points off VS4, on the same row: VS4 less 20 against FICO in cells, and the model's gap there. VS4 sits a tier above FICO here, so at the number it reads the gap and with 20 points off it reads about the plant.
less20_rows = rate_book(gap=0)
for r in less20_rows:
    if r["score_model"] == "V" and r["vs4"] and r["vs4"] < 820 and r["classic_fico"]:
        r["vs4"] = r["pricing_score"] = r["classic_fico"] + 20
        r["orig_rate"] = round(r["orig_rate"] + 0.015, 3)
views_less = rate_views(pricing.build_rates(rate_con(less20_rows, "less20")))
less20 = next(r for r in views_less["same_number"] if r["scope"] == "less20")
assert less20["key"] == "less20" and abs(less20["cell5"] - 1.5) < 0.5 and abs(less20["tier"] - 1.5) < 0.5 and less20["gap"] is not None and less20["n"] == next(r for r in views_less["row"] if r["key"] == "same_number")["n"] and less20["read"] >= 1000 and less20["read_tier"] >= 1000 and less20["dot_raw"] == round((less20["cell5"] + less20["tier"]) / 2, 2) and less20["lo_raw"] <= less20["hi_raw"], less20
less_thin = next(r for r in rate_views(pricing.build_rates(rate_con(rate_book(gap=4, vs4_a_week=1), "less_thin")))["same_number"] if r["scope"] == "less20")
assert less_thin["dot_raw"] is None and less_thin["cell5"] is None and less_thin["gap"] is None and less_thin["thin"], less_thin
# VS4 820+, while its row has loans and a flag, and the figure it is not in while there is one.
over_band = {"scope": "band", "key": "over820", "flag": "no_like_fico", "pool": 50}
share_said, like_said = "about one VS4 loan in nine", "has few FICO loans at its number"
for over, want in [({}, f"Left out: VS4 820+, {share_said}, {like_said}."), ({"flag": "few_like_fico"}, f"Left out: VS4 820+, {share_said}, {like_said}."), ({"flag": None}, None), ({"pool": 0}, None)]:
    assert pricing._number_bands([{"scope": "month", "key": "other"}, {**over_band, **over}], share_said, like_said) == want, (over, want)
assert meta_a["number_bands"] == "Left out: VS4 820+, about one VS4 loan in 64, has almost no FICO loans at its number.", meta_a["number_bands"]
over_a = next(r for r in views["same_number"] if r["key"] == "over820")
assert over_a["flag"] == "no_like_fico" and over_a["read_number"] == 0 and over_a["pool"] == 20, over_a
# Loans under 640 are in the same-number row, and the band's flag goes with the spread of its three methods: FICO loans further down the tier move its tier read and not its 5-point read.
low_book, low_rng = rate_book(gap=4), random.Random(9)
for w, week in enumerate(RATE_WEEKS):
    for k in range(15):
        low_book.append(rate_row(900000 + 30 * w + 2 * k, "rocket-mortgage", "R", week, rate_rate(low_rng, "rocket-mortgage|R", w, 630), "C", 630, agency="FNMA"))
        low_book.append(rate_row(900001 + 30 * w + 2 * k, "rocket-mortgage", "R", week, rate_rate(low_rng, "rocket-mortgage|R", w, 630) + 0.04, "V", 630, 631, agency="FNMA"))
views_low = rate_views(pricing.build_rates(rate_con(low_book, "low")))
band_low = next(r for r in views_low["same_number"] if r["key"] == "under640")
same_low = next(r for r in views_low["row"] if r["key"] == "same_number")
assert band_low["n"] == 150 and not band_low["thin"] and band_low["flag"] is None and same_low["n"] == row_a["same_number"]["n"] + 150, (band_low, same_low)
spread_book = low_book + [rate_row(950000 + 30 * w + k, "rocket-mortgage", "R", week, rate_rate(low_rng, "rocket-mortgage|R", w, 630) + 0.2, "C", 625, agency="FNMA") for w, week in enumerate(RATE_WEEKS) for k in range(15)]
band_spread = next(r for r in rate_views(pricing.build_rates(rate_con(spread_book, "spread")))["same_number"] if r["key"] == "under640")
assert band_spread["flag"] == "unsettled" and abs(band_spread["cell5"] - band_spread["tier"]) >= 3, band_spread
# Under 640 the tier method compares within 20 points, since the bottom LLPA tier spans everything: FICO loans 30 points down no longer move it.
far_down = low_book + [rate_row(950000 + 30 * w + k, "rocket-mortgage", "R", week, rate_rate(low_rng, "rocket-mortgage|R", w, 630) + 0.2, "C", 600, agency="FNMA") for w, week in enumerate(RATE_WEEKS) for k in range(15)]
band_far = next(r for r in rate_views(pricing.build_rates(rate_con(far_down, "far_down")))["same_number"] if r["key"] == "under640")
assert abs(band_far["tier"] - band_low["tier"]) < 0.5 and band_far["flag"] is None, band_far
s_far = pricing._sample(rate_con(far_down, "far_down_s"))
assert abs(pricing._gap(s_far.bp, s_far.tv & (s_far.fico == 630), s_far.fic & ~s_far.rc, s_far.cell_ft)["est"] - 4) < 1, "and at the same FICO"
# The equivalent's FICO at lenders that rarely use VS4: FICO loans showing both scores, issued from Oct 1, in the band. Before October, at Rocket correspondent and at the lender that uses VS4 the FICO shown is far lower, so a read that let them in would show it.


def rare_book(shown, a_week=50):
    out, rng, i = [], random.Random(7), 0
    for w, week in enumerate(RATE_WEEKS):
        for k in range(140):  # a band's VS4 loans issued from October clear the row floor
            f = 700 + 20 * (k % 4)
            out.append(rate_row(i, "united-wholesale-mortgage", "B", week, rate_rate(rng, "united-wholesale-mortgage|B", w, f), "C", f, agency="FNMA"))
            out.append(rate_row(i + 1, "united-wholesale-mortgage", "B", week, rate_rate(rng, "united-wholesale-mortgage|B", w, f), "V", f, f + 21, agency="FNMA"))
            i += 2
        for k in range(a_week):
            out.append(rate_row(i, "other-bank", "R", week, rate_rate(rng, "other-bank|R", w, 700), "C", shown if week[1] >= "2026-10-01" else 600, 725))
            out.append(rate_row(i + 1, "rocket-mortgage", "C", week, rate_rate(rng, "rocket-mortgage|C", w, 700), "C", 600, 725))
            out.append(rate_row(i + 2, "united-wholesale-mortgage", "B", week, rate_rate(rng, "united-wholesale-mortgage|B", w, 700), "C", 640, 725))
            i += 3
    return out


caption_end = "This is how these lenders have priced, not a conversion."
caption_high = "VS4 loans at these lenders sit well above FICO: a VS4 of 720-739 goes with a FICO near 700 there and near 715 at lenders that rarely use VS4. "
views_rare = rate_views(pricing.build_rates(rate_con(rare_book(715), "rare")))
band_rare = {r["band"]: r for r in views_rare["equivalent"]}
assert band_rare["720-739"]["fico_rare"] == 715 and band_rare["720-739"]["fico_rare_n"] == 150 and band_rare["720-739"]["fico_mean"] == 700, band_rare["720-739"]
assert all(r["fico_rare"] is None and r["fico_rare_n"] == 0 for band, r in band_rare.items() if band != "720-739"), band_rare
assert views_rare["meta"][0]["equivalent_caption"] == caption_high + caption_end, views_rare["meta"][0]["equivalent_caption"]  # one lender's VS4 loans, so no second name
# The test row reads here, Rocket's correspondent loans being out of it and UWM beside it.
assert re.fullmatch(fr"{re.escape(first_clause)} They show about [+−0-9.]+ at lenders that rarely use VS4 and (about 0|about [+−0-9.]+) at UWM on 500 loans\.", views_rare["meta"][0]["test_line"]), views_rare["meta"][0]["test_line"]
rare_check = next(r for r in views_rare["check"] if r["key"] == "rare_high_vs4")
assert rare_check["top_share"] == 1.0 and rare_check["without_top"] is None and rare_check["without_top_n"] == 0 and rare_check["without_top_se"] is None and rare_check["detail"] == "About 100% of these loans are one lender.", rare_check
# A further sentence goes with its guard: 5+ points above the band's own FICO, a read under 100 loans blank though its count stays.
assert rate_views(pricing.build_rates(rate_con(rare_book(705), "rare_at")))["meta"][0]["equivalent_caption"] == caption_high.replace("715", "705") + caption_end
assert rate_views(pricing.build_rates(rate_con(rare_book(704), "rare_near")))["meta"][0]["equivalent_caption"] == caption_end
few_rare = {r["band"]: r for r in rate_views(pricing.build_rates(rate_con(rare_book(715, a_week=33), "rare_few")))["equivalent"]}["720-739"]
assert few_rare["fico_rare"] is None and few_rare["fico_rare_n"] == 99, few_rare
late_book = rare_book(715)
for r in late_book:  # the last two of three weeks issued from October close in October
    if r["first_intraday_date"] in ("2026-10-12", "2026-10-19"):
        r["first_pay_date"] = "2026-12-01"
s_late = pricing._sample(rate_con(late_book, "rare_late"))
bands_late = pricing._equivalent(s_late, pricing._fit_all(s_late))
assert pricing._equivalent_caption(bands_late, [], float("nan")) == caption_high + caption_end, pricing._equivalent_caption(bands_late, [], float("nan"))  # the timing clause is the quote's now
assert pricing._equivalent_caption(bands_late, ["Lender A", "Lender B"], 0.9) == caption_high.replace("these lenders", "Lender A and Lender B") + caption_end and pricing._equivalent_caption(bands_late, ["Lender A", "Lender B"], 0.89) == caption_high + caption_end
assert pricing._equivalent_caption([{**r, "eq": None} for r in bands_late], [], float("nan")) is None, "no read, no caption"
# Near the old rule's 20 points, in words, within 5 points of them; a band pinned to the curve's end says nothing.
caption_rule = "Near the old rule's 20 points, which does not show the rule caused it."
assert pricing._rule_words(25.0) == caption_rule == pricing._rule_words(15.0) and pricing._rule_words(25.1) is None and pricing._rule_words(14.9) is None and pricing._rule_words(None) is None, pricing._rule_words(25.0)
assert pricing._rule_words(24.0, (17, 33)) == caption_rule == pricing._rule_words(24.0, (25, 36)) == pricing._rule_words(16.0, (8, 15)) and pricing._rule_words(24.0, (26, 36)) is None and pricing._rule_words(16.0, (8, 14)) is None and pricing._rule_words(26.0, (17, 33)) is None, "the range printed beside it reaches as near"
assert [(r["band"], r["use_bp"], r["points"]) for r in pricing._equivalent(s_late, pricing._fit_all(s_late)) if r["eq"] is not None and (r["use_bp"] or r["points"] is None)] == [(r["band"], True, None) for r in bands_late if r["use_bp"] and r["eq"] is not None], bands_late
assert all(r["points"] == pricing._points(r["vs_mean"], r["eq"]) for r in bands_late if r["points"] is not None) and pricing._points(650.2, 622.5) == 27, "points from the two whole numbers a reader sees"
few_fico_book = [r for r in rare_book(715) if r["score_model"] == "V" or r["loan_id"].endswith("0000")] + [rate_row(990000 + k, "other-bank", "R", RATE_WEEKS[0], 6.5, "C", 760) for k in range(30)]
bands_few = pricing._equivalent(s_few_eq := pricing._sample(rate_con(few_fico_book, "eq_pinned")), pricing._fit_all(s_few_eq))
assert all(r["eq"] is None and r["points"] is None for r in bands_few if r["n"] >= pricing.MIN_ROW and r["eq_lo"] is None), bands_few
# The sum in the LLPA fold: the grid is in percent of balance, so its difference is read in bp; each lower-LLPA loan here has VS4 a tier above FICO, at 80 LTV on a purchase.
grid_llpa, book_llpa = pricing._grid(), rate_book(gap=0, lower=-8)
fico_llpa = [r["classic_fico"] for r in book_llpa if r["score_model"] == "V" and r["vs4"] == (r["classic_fico"] or 0) + 20 and (r["seller"], r["channel"]) != ("rocket-mortgage", "C")]
less_llpa = sum(grid_llpa[0, pricing._tier(f), 4] - grid_llpa[0, pricing._tier(f + 20), 4] for f in fico_llpa) / len(fico_llpa) * 100
s_llpa = pricing._sample(rate_con(book_llpa, "llpa"))
assert abs(pricing._llpa_less(s_llpa) - less_llpa) < 1e-9 and 10 < less_llpa < 50, (less_llpa, len(fico_llpa))
assert abs(pricing._llpa_less(s_llpa, s_llpa.fee_20)) < 1e-9, "20 points off lands the very LLPA of FICO here"
lower_planted = {"lo": -3.5, "hi": -1.0}
sum_head = "Where VS4 lowers the LLPA, the LLPA is about 10 bp of balance lower on today's grid, about 2 bp of rate at the rule of thumb of 5 bp of LLPA to 1 bp of rate"
sum_tail = ". The rate itself differs by about −3.5 to −1 bp. The files cannot tell where any difference goes: points, lender credits or the lender's margin."
sum_old = "; on the old rule in force when most of these rates were likely set, about 7.5 bp, about 1.5 bp of rate"
by_lender_sum = [("Book A", -15.5, -13.0, 8.2), ("Book B", -4.0, -1.5, 4.9)]
assert pricing._llpa_sum(10.0, 7.5, 0.51, lower_planted) == sum_head + sum_old + sum_tail
assert pricing._llpa_sum(10.0, 7.5, 0.5, lower_planted) == sum_head + sum_tail and pricing._llpa_sum(10.0, float("nan"), 0.51, lower_planted) == sum_head + sum_tail
assert pricing._llpa_sum(10.0, 7.5, 0.51, lower_planted, by_lender_sum) == sum_head + sum_old + sum_tail + " By lender it is not even: Book A −15.5 to −13 against an old-rule LLPA gap worth about 8 bp of rate, Book B −4 to −1.5 against about 5." and pricing._llpa_sum(10.0, 7.5, 0.5, lower_planted, by_lender_sum) == sum_head + sum_tail, "on the old rule, so only while most of these rates were set under it"
assert all(pricing._llpa_sum(x, 7.5, 0.51, lower_planted) is None for x in (0.0, -2.0, float("nan"))) and pricing._llpa_sum(10.0, 7.5, 0.51, {"lo": None, "hi": None}) is None
assert views_b["meta"][0]["llpa_sum"].startswith(f"Where VS4 lowers the LLPA, the LLPA is about {pricing._near(less_llpa):g} bp of balance lower on today's grid, about {pricing._near(less_llpa / pricing.RATE_MULT):g} bp of rate"), views_b["meta"][0]["llpa_sum"]
s_by_lender = pricing._sample(rate_con(rate_book(gap=0, lower=-8), "by_lender"))
planted_llpa = [{"key": "rocket-mortgage|R|all", "label": "Book A", "lower_lo": -15.5, "lower_hi": -13.0}, {"key": "united-wholesale-mortgage|B|all", "label": "Book B", "lower_lo": -4.0, "lower_hi": -1.5}]
assert [(r[0], r[1], r[2]) for r in pricing._llpa_by_lender(s_by_lender, planted_llpa)] == [("Book A", -15.5, -13.0), ("Book B", -4.0, -1.5)] and abs(pricing._llpa_by_lender(s_by_lender, planted_llpa)[0][3] - pricing._llpa_less(s_by_lender, s_by_lender.fee_20, (s_by_lender.seller == "rocket-mortgage") & (s_by_lender.channel == "R")) / 5) < 1e-9, "both groups' ranges and their LLPA on the old rule"
assert pricing._llpa_by_lender(s_by_lender, planted_llpa[:1]) == [] and pricing._llpa_by_lender(s_by_lender, [planted_llpa[0], {**planted_llpa[1], "lower_lo": None}]) == [] and pricing._llpa_by_lender(s_by_lender, [planted_llpa[0], {**planted_llpa[1], "lower_lo": -14.0}]) == [], "both reading, and ranges apart, or it is not uneven"
assert f"The rate itself differs by about {pricing._range(row_b['lower_llpa']['lo'], row_b['lower_llpa']['hi'])} bp." in views_b["meta"][0]["llpa_sum"], views_b["meta"][0]["llpa_sum"]
assert meta_a["llpa_sum"] is None, "no lower-LLPA loan here, so the row is blank"
# The share where VS4's LLPA is lower, on loans issued from Oct 1 showing both, whichever priced them.
assert meta_a["llpa_share"] == "VS4's LLPA is lower on about 0% of all loans showing both scores, whichever score priced them." and views_b["meta"][0]["llpa_share"].startswith("VS4's LLPA is lower on about "), (meta_a["llpa_share"], views_b["meta"][0]["llpa_share"])
assert pricing._llpa_share(pricing._sample(rate_con(rate_book()[:40], "llpa_none"))) is None
# Same FICO by how far VS4 sits above FICO, in the fields of a same-number gap band: planted gaps read back, the answer says how it runs while the three bands fall at both GSE reads, and the line on both figures goes with the same-number bands rising.


def gap_book(gaps=(3.5, -2.5, -8.0), a_week=3, at_fannie=None):
    """VS4 loans 10, 30 and 50 points above their FICO at each planted gap, in two lenders and ten weeks. FICO loans' rates fall half a bp a point, so at its number a loan further above its FICO reads higher. at_fannie: the gaps at Fannie, if not the same."""
    rng, out, i = random.Random(43), [], 0
    for seller, channel, lift in (("rocket-mortgage", "R", 0.02), ("united-wholesale-mortgage", "B", -0.01)):
        for w, week in enumerate(RATE_WEEKS):
            agency = "FNMA" if w % 2 else "FHLMC"
            rate = lambda f: 6.5 + lift + 0.02 * w - 0.005 * (f - 700) + rng.uniform(-0.01, 0.01)  # noqa: E731, B023
            for f in range(700, 800, 10):
                for k in range(4):
                    out.append(rate_row(i, seller, channel, week, rate(f), "C", f, agency=agency, program="H"))
                    i += 1
            for points, gap, gap_fannie in zip((10, 30, 50), gaps, at_fannie or gaps):
                for f in (700, 720, 740):
                    for k in range(a_week):
                        out.append(rate_row(i, seller, channel, week, rate(f) + (gap_fannie if agency == "FNMA" else gap) / 100, "V", f, f + points, agency=agency, program="H"))
                        i += 1
    return out


views_gap = rate_views(pricing.build_rates(rate_con(gap_book(), "gap")))
assert [r["key"] for r in views_gap["fico_gap"]] == ["1-19", "20-39", "40+"] and [r["order"] for r in views_gap["fico_gap"]] == [0, 1, 2] and all(r["n"] == 180 and not r["thin"] for r in views_gap["fico_gap"]), views_gap["fico_gap"]
for r, planted_gap in zip(views_gap["fico_gap"], (3.5, -2.5, -8.0)):
    assert abs(r["cell5"] - planted_gap) < 0.5 and abs(r["tier"] - planted_gap - 2.5) < 0.5 and abs(r["dot"] - planted_gap - 1.25) <= 0.5 and r["model"] == r["gap"] and r["read5"] <= r["n"] and r["read5"] == r["read"] and r["pool"] == r["n"] and r["read_tier"] >= r["read5"] and abs(r["fannie"] - planted_gap - 1.25) < 1 and r["lo_raw"] <= r["dot_raw"] <= r["hi_raw"] and (r["dot"], r["spread_lo"], r["spread_hi"]) == pricing.printed(r["dot_raw"], r["lo_raw"], r["hi_raw"]) and r["tl"] is not None and r["tl"] <= r["th"], r  # the tier read's comparators run 10 points up, half a bp a point
answer_gap = next(r for r in views_gap["answer"] if r["key"] == "same_fico")["text"]
assert f"It runs from about {pricing._signed(views_gap['fico_gap'][0]['dot'])} at 1 to 19 above FICO to about {pricing._signed(views_gap['fico_gap'][2]['dot'])} at 40+ above." in answer_gap or not next(r for r in views_gap["row"] if r["key"] == "same_fico")["sentence"].startswith("About"), answer_gap
assert views_gap["meta"][0]["gap_line"] and views_gap["meta"][0]["gap_line"].startswith("The further VS4 sits above FICO, the lower the rate at the same FICO."), views_gap["meta"][0]["gap_line"]
gap_fannie_flat = rate_views(pricing.build_rates(rate_con(gap_book(at_fannie=(-6.0, -2.5, 1.5)), "gap_fannie")))
assert not (gap_fannie_flat["meta"][0]["gap_line"] or "").startswith("The further") and "It runs from" not in gap_fannie_flat["meta"][0]["answer"], "and at Fannie too"
few_gap = rate_views(pricing.build_rates(rate_con([r for r in gap_book() if r["score_model"] == "C" or r["vs4"] - r["classic_fico"] != 50 or int(r["loan_id"][1:]) % 9 == 0], "gap_few")))["fico_gap"][2]
assert few_gap["n"] > 0 and few_gap["read5"] < 100 and few_gap["thin"] and all(few_gap[k] is None for k in ("cell5", "tier", "model", "gap", "dot_raw", "dot", "spread_lo", "tl", "th", "fannie")), few_gap
gap_rows = [{"scope": "gapband", "order": 0, "dot": 6.5, "label": "VS4 1 to 19 above FICO"}, {"scope": "gapband", "order": 1, "dot": 7.0, "label": "VS4 20 to 39 above FICO"}, {"scope": "gapband", "order": 2, "dot": 7.5, "label": "VS4 61+ above FICO"}, {"scope": "month", "order": 0, "dot": 40.0, "label": "A month"}]
gap_at = lambda *dots: [{**r, "dot": dots[r["order"]]} if r["scope"] == "gapband" else r for r in gap_rows]  # noqa: E731
gap_pooled = "The further VS4 sits above FICO, the lower the rate at the same FICO."
gap_rises, gap_highest = "At the same score number it rises.", "At the same score number it is highest at 61+ above."
assert pricing._gap_line(answer_gaps, gap_rows) == f"{gap_pooled} {gap_rises}" and pricing._gap_line(answer_gaps, gap_at(6.5, 5.5, 8.5)) == f"{gap_pooled} {gap_highest}", pricing._gap_line(answer_gaps, gap_rows)
# The second part: rising at every step; else the last strictly highest and 1+ bp over the first; a band with no figure, or none of that: nothing. The first part stands alone then.
for dots in ((6.5, 7.0, 7.0), (6.5, 5.5, 7.0), (6.5, 9.5, 8.5), (6.5, 8.5, 8.5), (6.5, None, 8.5), (None, 7.0, 8.5), (8.5, 7.0, 6.5)):
    assert pricing._gap_line(answer_gaps, gap_at(*dots)) == gap_pooled, (dots, pricing._gap_line(answer_gaps, gap_at(*dots)))
assert pricing._gap_line(answer_gaps, gap_at(6.5, 5.5, 7.5)) == f"{gap_pooled} {gap_highest}" and pricing._gap_line(answer_gaps, gap_rows[:1]) == gap_pooled and pricing._gap_line(answer_gaps, gap_at(6.5, 7.0, 7.5)) == f"{gap_pooled} {gap_rises}", "1+ bp over the first only where it does not rise at every step"
# The first part: no fall at all, so only the same number, in words that stand alone; neither, so nothing.
gap_flat = [answer_gaps[0], {**answer_gaps[1], "dot": 2.5}, answer_gaps[2]]
assert pricing._gap_line(gap_flat, gap_rows) == "At the same score number the gap rises the further VS4 sits above FICO." and pricing._gap_line(gap_flat, gap_at(6.5, 5.5, 8.5)) == "At the same score number the gap is highest at 61+ above." and pricing._gap_line(gap_flat, gap_at(6.5, 7.0, 7.0)) is None and pricing._gap_line([answer_gaps[0], {**answer_gaps[1], "fannie": 3.0}, answer_gaps[2]], gap_at(8.5, 7.0, 6.5)) is None, "and falling at Fannie too"
assert pricing._gap_line(answer_gaps[:2], gap_at(8.5, 7.0, 6.5)) is None, "three bands"
# At the book: everything else on all three bands decides what follows it: printed midpoints falling, then model reads falling, then neither; and a band under its floor says nothing of elsewhere. The book's guard failing falls back to the pooled line.
gap_book_at = [band_mid, band_top]
rest_of = lambda dots, models, fannie=(None, None, None): [{"dot": d, "model": m, "fannie": f, "fannie_read5": 150 if f is not None else 0, "fannie_read_tier": 150} for d, m, f in zip(dots, models, fannie)]  # noqa: E731
gap_at_book = "the further VS4 sits above FICO, the lower the rate at the same FICO"
for rest_in, want in [(rest_of((3.5, -1.5, -3.5), (2.2, 0.1, -4.4)), f"The further VS4 sits above FICO, the lower the rate at the same FICO, at A book and elsewhere."),
                      (rest_of((3.5, -1.5, -3.5), (2.2, 0.1, -4.4), (3.0, -1.0, -2.0)), f"The further VS4 sits above FICO, the lower the rate at the same FICO, at A book and elsewhere."),
                      (rest_of((3.5, -1.5, -3.5), (2.2, 0.1, -4.4), (3.0, -2.0, -1.0)), f"At A book, {gap_at_book}."),
                      (rest_of((3.5, -1.5, -3.5), (2.2, 2.3, -4.4), (3.0, -2.0, -1.0)), f"At A book, {gap_at_book}."),
                      (rest_of((3.5, -1.5, -1.5), (2.2, 0.1, -4.4)), f"At A book, {gap_at_book}; elsewhere that shows only on the model."),
                      (rest_of((3.5, -1.5, 0.5), (2.2, 0.1, -4.4)), f"At A book, {gap_at_book}; elsewhere that shows only on the model."),
                      (rest_of((3.5, -1.5, 0.5), (2.2, 2.3, -4.4)), f"At A book, {gap_at_book}; not elsewhere."),
                      (rest_of((3.5, -1.5, 0.5), (2.2, 2.3, None)), f"At A book, {gap_at_book}; not elsewhere."),
                      (rest_of((3.5, -1.5, 0.5), (2.1, 2.0, -4.4)), f"At A book, {gap_at_book}; not elsewhere."),
                      (rest_of((3.5, None, 0.5), (2.2, 0.1, -4.4)), f"At A book, {gap_at_book}."),
                      (rest_of((3.5, -1.5), (2.2, 0.1)), f"At A book, {gap_at_book}."), ([], f"At A book, {gap_at_book}.")]:
    assert pricing._gap_line(gap_flat, gap_at(6.5, 5.5, 8.5), book_half, gap_book_at, rest_in) == f"{want} {gap_highest}", (rest_in, pricing._gap_line(gap_flat, gap_at(6.5, 5.5, 8.5), book_half, gap_book_at, rest_in))
assert pricing._gap_line(answer_gaps, gap_at(8.5, 7.0, 6.5), book_half, [{**band_mid, "read5": 99}, band_top], rest_of((3.5, -1.5, -3.5), (2.2, 0.1, -4.4))) == gap_pooled and pricing._gap_line(gap_flat, gap_at(8.5, 7.0, 6.5), book_half, [{**band_mid, "fannie": -9.0}, {**band_top, "fannie": -5.0}], rest_of((3.5, -1.5, -3.5), (2.2, 0.1, -4.4))) is None, "the book's guard first"
# Past Rocket's switch point, where the LLPA does not change on either grid: VS4 loans well above their FICO against FICO loans near theirs at the same lender, and FICO loans alone where nothing switches. A read on under 100 matched loans stays null.


def past_book(rocket=-6.5, uwm=1.5, rare=0.5, a_week=30):
    rng, out, i = random.Random(37), [], 0
    rate = lambda f, w: 6.5 + 0.02 * w - 0.001 * (f - 700) + rng.uniform(-0.01, 0.01)  # noqa: E731
    for w, week in enumerate(RATE_WEEKS):
        agency = "FNMA" if w % 2 else "FHLMC"
        for seller, channel, model, gap in (("rocket-mortgage", "R", "V", rocket), ("united-wholesale-mortgage", "B", "V", uwm), ("other-bank", "R", "C", rare)):
            for k in range(a_week):
                f = 700 + 20 * (k % 4)
                out.append(rate_row(i, seller, channel, week, rate(f, w), "C", f, f + 10, agency=agency, program="H"))
                out.append(rate_row(i + 1, seller, channel, week, rate(f, w) + gap / 100, model, f, f + 30, agency=agency, program="H"))
                i += 2
    return out


con_past = rate_con(past_book(), "past")
s_past = pricing._sample(con_past)
s_past.fits = pricing._fit_all(s_past)
past_names = {"rocket-mortgage": "Lender R", "united-wholesale-mortgage": "Lender U"}
past_rows = {r["key"]: r for r in pricing._past(s_past, past_names)}
assert list(past_rows) == ["rocket", "rocket_fannie", "uwm", "rare"] and past_rows["rocket"]["label"] == "Lender R" and past_rows["rocket_fannie"]["label"] == "Lender R, at Fannie alone" and past_rows["uwm"]["label"] == "Lender U", past_rows
for key, planted_gap, n in (("rocket", -6.5, 300), ("rocket_fannie", -6.5, 150), ("uwm", 1.5, 300), ("rare", 0.5, 300)):
    r = past_rows[key]
    assert abs(r["cell5"] - planted_gap) < 0.5 and abs(r["cell20"] - planted_gap) < 0.5 and abs(r["model"] - planted_gap) < 1 and r["n"] == n == r["comparators"] and r["read5"] <= r["n"] and r["read20"] <= r["n"] and r["lender_weeks"] == n // 30 and r["thin"] is (r["lender_weeks"] < 8), r
s_few_past = pricing._sample(rate_con(past_book(a_week=8), "past_few"))
pricing._fit_all(s_few_past)
few_past = {r["key"]: r for r in pricing._past(s_few_past, past_names)}
assert few_past["rocket"]["read5"] < 100 and few_past["rocket"]["cell5"] is None and few_past["rocket"]["cell20"] is None and few_past["rocket"]["model"] is None and few_past["rocket"]["n"] == 80, few_past["rocket"]
# Only where the LLPA does not change on either grid: loans in a program that pays one, where VS4 lands another tier or 20 points off would, stay out on both sides.
past_mixed = past_book() + [rate_row(996000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 9.0, "V", 700, 730, agency="FNMA" if k % 10 % 2 else "FHLMC") for k in range(200)] + [rate_row(997000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 9.0, "C", 700, 710, agency="FNMA" if k % 10 % 2 else "FHLMC") for k in range(200)]
s_mixed = pricing._sample(rate_con(past_mixed, "past_mixed"))
pricing._fit_all(s_mixed)
mixed_rocket = next(r for r in pricing._past(s_mixed, past_names) if r["key"] == "rocket")
assert mixed_rocket["n"] == 300 == mixed_rocket["comparators"] and abs(mixed_rocket["cell5"] + 6.5) < 0.5 and abs(mixed_rocket["cell20"] + 6.5) < 0.5, mixed_rocket
past_said = ("Past the switch point: at Lender R, VS4 25 to 49 points above FICO is about −9.5 to −3.5, on few weeks of loans, against FICO loans with the same FICO and VS4 0 to 19 points above it, where the LLPA is the same today and under the old rule. ", "At Lender U that comparison is about +1.5 to +8.5", "Lender R's choice of score and its higher VS4 come together, so this cannot say which.")
past_read = {"rocket": {"key": "rocket", "cell5": -9.3, "cell20": -4.2, "model": -3.6, "thin": True}, "rocket_fannie": {"key": "rocket_fannie", "cell5": -8.4, "cell20": -5.6, "model": -2.1, "thin": True}, "uwm": {"key": "uwm", "cell5": None, "cell20": 8.2, "model": 1.6, "thin": True}, "rare": {"key": "rare", "cell5": 3.5, "cell20": 4.1, "model": -1.4, "thin": False}}
past_with = lambda **change: list({**past_read, **{k: {**past_read[k], **v} for k, v in change.items()}}.values())  # noqa: E731
assert pricing._past_line(past_with(), past_names) == f"{past_said[0]}{past_said[1]} on two methods. {past_said[2]}", pricing._past_line(past_with(), past_names)
assert pricing._past_line(past_with(uwm={"cell5": 3.5}), past_names) == f"{past_said[0]}{past_said[1]}. {past_said[2]}", "two methods only while one read is under its floor"
assert pricing._past_line(past_with(uwm={"model": None}), past_names) == f"{past_said[0]}{past_said[2]}" and pricing._past_line(past_with(uwm={"cell20": None}), past_names) == f"{past_said[0]}{past_said[2]}" and pricing._past_line(past_with(uwm={"cell20": -8.2, "model": -1.6}), past_names) == f"{past_said[0]}{past_said[2]}", "UWM needs a cell read and a model read, and to reach zero"
assert "rarely" not in pricing._past_line(past_with(), past_names) and pricing._past_line(past_with(rare={"cell5": -3.5, "cell20": -4.1}), past_names) == pricing._past_line(past_with(), past_names), "those that rarely use VS4 stay in the workbook's table"
assert pricing._past_line(past_with(rocket={"thin": False}), past_names).startswith("Past the switch point: at Lender R, VS4 25 to 49 points above FICO is about −9.5 to −3.5, against FICO loans"), "few weeks, in words"
for change in ({"rocket": {"model": 0.2}}, {"rocket": {"cell5": None}}, {"rocket_fannie": {"cell20": None}}, {"rocket_fannie": {"cell5": 0.5}}):
    assert pricing._past_line(past_with(**change), past_names) is None, change
# Through the build, after the line it follows: a planted step past the switch point reads as the rate falling further up.
views_past = rate_views(pricing.build_rates(rate_con(line_book(step=-9.0), "past_build")))
past_limit = next(r for r in views_past["limit"] if r["key"] == "past")["text"]
assert past_limit.startswith("Past the switch point: at ") and past_limit.endswith("'s choice of score and its higher VS4 come together, so this cannot say which.") and [r["key"] for r in views_past["limit"]].index("past") == [r["key"] for r in views_past["limit"]].index("line") + 1 and {r["key"] for r in views_past["past"]} == {"rocket", "rocket_fannie", "uwm", "rare"}, past_limit
assert "past" not in {r["key"] for r in rate_views(pricing.build_rates(rate_con(past_book(), "past_no_line")))["limit"]}, "no switch point read, so nothing to be past"
# On the same-number row's loans that show a FICO, between the two scores: same FICO in all three methods with its 95% range. VS4 820+ stays out of the line and the file.
same_loans_at = next(r for r in views_between["limit"] if r["key"] == "same_loans")["text"]
assert re.fullmatch(r"VS4 loans under 820 that show a FICO, about 100%: about \+6 at the same number and about −[\d.]+ at the same FICO \(95% range about [+−0-9.]+ to [+−0-9.]+\)\.", same_loans_at), same_loans_at
assert "same_loans" not in {r["key"] for r in views["limit"]}, "not between the two scores, so no such line"
assert next(r for r in views_between["limit"] if r["key"] == "note_rate")["text"].endswith(" −6 bp is about 0.3 of a discount point."), "one conversion, the same-FICO figure's, though the same-number figure differs"
note_small = next(r["text"] for r in rate_views(pricing.build_rates(rate_con(rate_book(gap=6.5), "x_note_small")))["limit"] if r["key"] == "note_rate")
assert note_small.endswith(" +6.5 bp is about 0.3 of a discount point."), note_small  # one decimal place in every state
note_tiny = next(r["text"] for r in rate_views(pricing.build_rates(rate_con(rate_book(gap=0.5), "x_note_tiny")))["limit"] if r["key"] == "note_rate")
assert note_tiny.endswith("are not disclosed."), note_tiny  # 0.5 bp would print as 0.0
high_at = between_book(-6.0)
high_at += [rate_row(960000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 6.5 + 0.02 * (k % 10) - 0.003 * 100 + 0.03 + 0.025, "V", 800, 830, agency="FNMA" if k % 10 % 2 else "FHLMC") for k in range(240)] + [rate_row(961000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 6.5 + 0.02 * (k % 10) - 0.003 * 100 + 0.03, "C", 800, agency="FNMA" if k % 10 % 2 else "FHLMC") for k in range(240)]
said_high = next(r for r in rate_views(pricing.build_rates(rate_con(high_at, "x_high_at")))["limit"] if r["key"] == "same_loans")["text"]
assert "820+" not in said_high and said_high.startswith("VS4 loans under 820 that show a FICO"), said_high
few_at_number = [r for r in between_book(-6.0) if r["score_model"] == "V" or r["classic_fico"] < 700 or int(r["loan_id"][1:]) % 500 == 0]
s_few_number = pricing._sample(rate_con(few_at_number, "x_few_number"))
s_few_number.fits = pricing._fit_all(s_few_number)
s_loans_model = pricing._sample(rate_con(between_book(-6.0), "x_loans_model"))
s_loans_model.fits = pricing._fit_all(s_loans_model)
s_loans_model.gap_fico = s_loans_model.gap_fico - 6.0
assert pricing._same_loans(s_loans_model, {"same_number": {"dot": 6.0}})["dot"] == -6.0, "the model far off moves the range, not the figure"
said_few_number = pricing._same_loans(s_few_number, {"same_number": {"dot": 6.0}})
assert min(pricing._gap(s_few_number.bp, s_few_number.tv, s_few_number.fic, s_few_number.cell_n5)["n"], pricing._gap(s_few_number.bp, s_few_number.tv, s_few_number.fic, s_few_number.cell_nt)["n"]) < 100 and said_few_number["text"].startswith("VS4 loans under 820 that show a FICO, about 100%: about ") and "at the same number" not in said_few_number["text"] and said_few_number["at_number"] is None, said_few_number["text"]
# Beside chart 4: UWM's same-FICO read where it moves with the comparison: on VS4 under 820 while that sits 1.5+ bp off, and against FICO loans that also show a VS4 while that sits 2+ bp off, each read on 100+ matched loans. Without one of those two, nothing. The same-LLPA read stays in the workbook's table.
lender_planted = [{"scope": "group", "key": "rocket_retail", "label": "Book R", "same_fico_dot": -9.5, "same_number_dot": 3.5}, {"scope": "card", "key": "united-wholesale-mortgage", "label": "Book U", "same_fico_dot": -2.5, "same_fico_mid": -2.5, "same_number_dot": 6.5, "same_llpa_mid": 0.6, "same_fico_under820": -4.6, "same_fico_shown_cell5": 1.2, "same_fico_shown_tier": 1.6, "same_llpa_shown_cell5": 4.1, "same_llpa_shown_tier": 3.7, "same_number_mid": 6.5}]
lender_at = lambda **change: [lender_planted[0], {**lender_planted[1], **change}]  # noqa: E731
lender_head = "Book U: its same-FICO gap moves with the comparison: about −2.5 on its VS4 loans showing a FICO"
for rows_in, want in [(lender_at(), f"{lender_head}, about −4.5 on VS4 under 820, and about +1.5 against FICO loans that also show a VS4."),
                      (lender_planted[1:], f"{lender_head}, about −4.5 on VS4 under 820, and about +1.5 against FICO loans that also show a VS4."),
                      (lender_at(same_fico_under820=-4.0), f"{lender_head}, about −4 on VS4 under 820, and about +1.5 against FICO loans that also show a VS4."),
                      (lender_at(same_fico_under820=-3.75), f"{lender_head} and about +1.5 against FICO loans that also show a VS4."),
                      (lender_at(same_fico_under820=None), f"{lender_head} and about +1.5 against FICO loans that also show a VS4."),
                      (lender_at(same_fico_shown_tier=None), f"{lender_head} and about −4.5 on VS4 under 820."),
                      (lender_at(same_fico_shown_cell5=None), f"{lender_head} and about −4.5 on VS4 under 820."),
                      (lender_at(same_fico_shown_cell5=-0.75, same_fico_shown_tier=-0.25), f"{lender_head}, about −4.5 on VS4 under 820, and about −0.5 against FICO loans that also show a VS4."),
                      (lender_at(same_fico_shown_cell5=-0.75, same_fico_shown_tier=-0.5), f"{lender_head} and about −4.5 on VS4 under 820."),
                      (lender_at(same_fico_under820=None, same_fico_shown_tier=None), None), (lender_at(same_fico_under820=-3.75, same_fico_shown_cell5=-0.75, same_fico_shown_tier=-0.5), None),
                      (lender_at(same_fico_dot=None, same_fico_mid=None), None), (lender_planted[:1], None)]:
    assert pricing._lender_line(rows_in) == want, (rows_in, pricing._lender_line(rows_in))
assert "same LLPA" not in pricing._lender_line(lender_at()) and "Book R" not in pricing._lender_line(lender_at()), "UWM's same-FICO read alone"
assert lender_a["rocket_retail"]["same_fico_read5"] >= 100 and lender_a["rocket_retail"]["same_fico_read_tier"] >= 100 and lender_a["rocket_retail"]["same_fico_mid"] is not None and lender_a["rocket_broker"]["same_fico_read5"] == 0 and lender_a["rocket_retail"]["same_fico_shown_read5"] == 0 and lender_a["rocket_retail"]["same_fico_shown_cell5"] is None, lender_a["rocket_retail"]
assert views["meta"][0]["lender_line"] is None or "that also show a VS4" not in views["meta"][0]["lender_line"], "no FICO loan here shows a VS4"
shown_book = rate_book(gap=4)
for i, r in enumerate(shown_book):
    if r["score_model"] == "C" and i % 2:
        r["vs4"] = r["classic_fico"] + 5
        r["orig_rate"] = round(r["orig_rate"] - 0.09, 3)
shown_views = rate_views(pricing.build_rates(rate_con(shown_book, "shown")))
shown_uwm = next(r for r in shown_views["lender"] if r["scope"] == "card" and r["key"] == "united-wholesale-mortgage")
assert shown_uwm["same_fico_shown_read5"] >= 100 and abs(shown_uwm["same_fico_shown_cell5"] - 13) < 1.5 and abs(shown_uwm["same_fico_shown_tier"] - 13) < 1.5 and shown_uwm["same_fico_under820"] is not None and abs(shown_uwm["same_fico_mid"] - 8.5) < 1.5, shown_uwm
assert re.fullmatch(r"UWM: its same-FICO gap moves with the comparison: about \+[\d.]+ on its VS4 loans showing a FICO(, about [+−0-9.]+ on VS4 under 820,)? and about \+[\d.]+ against FICO loans that also show a VS4\.", shown_views["meta"][0]["lender_line"]), shown_views["meta"][0]["lender_line"]
shown_lenders = [r for r in shown_views["lender"]]
assert any(0 < r["same_fico_shown_read5"] < 100 for r in shown_lenders) and all((r["same_fico_shown_cell5"] is None) == (r["same_fico_shown_read5"] < 100) and (r["same_fico_shown_tier"] is None) == (r["same_fico_shown_read_tier"] < 100) for r in shown_lenders), "each read on 100+ matched loans"
# UWM's read on VS4 under 820 leaves its 820+ loans out.
uwm_high = rate_book(gap=4)
uwm_rng = random.Random(53)
for w, week in enumerate(RATE_WEEKS):
    agency = "FNMA" if w % 2 else "FHLMC"
    for k in range(20):
        uwm_high.append(rate_row(975000 + 100 * w + 2 * k, "united-wholesale-mortgage", "B", week, rate_rate(uwm_rng, "united-wholesale-mortgage|B", w, 790), "C", 790, agency=agency))
        uwm_high.append(rate_row(975001 + 100 * w + 2 * k, "united-wholesale-mortgage", "B", week, rate_rate(uwm_rng, "united-wholesale-mortgage|B", w, 790) + 0.3, "V", 790, 830, agency=agency))
uwm_high_card = next(r for r in rate_views(pricing.build_rates(rate_con(uwm_high, "x_uwm_high")))["lender"] if r["scope"] == "card" and r["key"] == "united-wholesale-mortgage")
assert abs(uwm_high_card["same_fico_under820"] - 4) < 1 and uwm_high_card["same_fico_mid"] > 8, uwm_high_card["same_fico_under820"]
# The floors read the loans the two exact matches reach, not the pool: under 100 on either, a lender row, a loan-type row and an LLPA-fold row keep only their counts.
few_lender = next(r for r in views_few["lender"] if r["scope"] == "group" and r["key"] == "rocket_retail")
assert few_lender["same_number_n"] >= 100 and few_lender["same_number_read5"] == 0 and few_lender["same_number_read_tier"] >= 100 and all(few_lender[f"same_number_{k}"] is None for k in ("dot", "lo", "hi", "se", "mid")) and few_lender["same_fico_dot"] is not None, few_lender
no_cell_cuts = [r for r in views_no_cell["cut"] if r["n"] >= 100]
assert no_cell_cuts and all(r["read5"] == 0 and all(r[k] is None for k in ("gap", "se", "dot", "spread_lo", "tl", "th", "model", "cell5", "tier", "dot_raw")) and r["thin"] for r in no_cell_cuts), no_cell_cuts[:1]
assert all(r["same_dot"] is None and r["same_gap"] is None and r["same_se"] is None for r in views_no_cell["llpa_rate"]) and any(r["same_n"] >= 100 for r in views_no_cell["llpa_rate"]), views_no_cell["llpa_rate"]
# More cuts: no comparable FICO loans, in the engine's own words, while its FICO band finds under a tenth; and the words stay where the figures go.
low_cut = rate_book(gap=4)
low_cut += [rate_row(960000 + 2 * w * 1000 + k, "rocket-mortgage", "R", week, 7.5, "V", 560, 561, agency="FNMA") for w, week in enumerate(RATE_WEEKS) for k in range(20)]
low_cut_rows = {r["key"]: r for r in rate_views(pricing.build_rates(rate_con(low_cut, "x_lowcut")))["cut"] if r["dim"] == "fico"}
assert low_cut_rows["under580"]["n"] >= 100 and low_cut_rows["under580"]["text"] == "No comparable FICO loans." and low_cut_rows["under580"]["dot"] is None and low_cut_rows["640-779"]["text"] is None, low_cut_rows["under580"]
# VS4 820+: few, not almost no, while a tenth or more find a FICO loan at their own number.
high_book = rate_book(gap=4)
high_book += [rate_row(970000 + 1000 * w + k, "rocket-mortgage", "R", week, 6.5, "C", 830) for w, week in enumerate(RATE_WEEKS) for k in range(40)] + [rate_row(980000 + 1000 * w + k, "rocket-mortgage", "R", week, 6.5, "V", 830, 832) for w, week in enumerate(RATE_WEEKS) for k in range(40)]
high_views = rate_views(pricing.build_rates(rate_con(high_book, "x_high")))
over_high = next(r for r in high_views["same_number"] if r["key"] == "over820")
assert over_high["read_number"] >= 0.1 * over_high["pool"] and over_high["flag"] == "few_like_fico" and "has few FICO loans at its number" in high_views["meta"][0]["number_bands"], (over_high, high_views["meta"][0]["number_bands"])
# The book: the one lender and channel on all three methods, each with the row's sign and a share of something; a month it prints needs 100+ loans and must hold or share the row's sign; the rest needs 100+.
from types import SimpleNamespace as _NS  # noqa: E402

# The figure with less held keeps the GSEs apart inside a lender and week: here FICO loans' rates differ by GSE in some weeks, and VS4 loans lean to one GSE in those weeks.
method_rows, method_rng = [], random.Random(9)
for i, r in enumerate(rate_book(gap=-6)):
    if (r["seller"], r["channel"]) != ("rocket-mortgage", "C"):
        method_week = [week[0] for week in RATE_WEEKS].index(r["first_intraday_date"])
        r = {**r, "loan_id": f"{r['loan_id']}x{i}", "agency": "FNMA" if method_rng.random() < (0.9 if r["score_model"] == "V" and method_week % 2 else 0.5) else "FHLMC"}
        if r["agency"] == "FNMA":
            r["orig_rate"] = round(r["orig_rate"] + (0.25 if method_week % 2 else -0.05), 3)
        if method_rng.random() < (0.4 if r["score_model"] == "V" else 0.2):
            r.update(purpose="C", orig_rate=round(r["orig_rate"] + 0.3, 3))
        method_rows.append(r)
method_plain, method_beta = pricing._method_reads(pricing._sample(rate_con(method_rows, "method_gse")))
assert abs(method_plain) < 1 and abs(method_beta + 6.0) < 0.5, (method_plain, method_beta)


def book_of(g5, gt, gm, dot_raw=-9.0, sentence="About 9 bp lower.", close=None, first=None, agency=None):
    n, first = len(g5), first if first is not None else len(g5) // 2
    stub = _NS(lc=np.array([0] * first + [1] * (n - first)), tv=np.ones(n, bool), gap_fico=np.array(gm, float), seller=np.array(["a"] * first + ["b"] * (n - first)), channel=np.array(["R"] * first + ["B"] * (n - first)), close=np.array(close or ["2026-09-01"] * n), week=np.array(["2026-09-07"] * n), agency=np.array(agency or ["FNMA"] * n))
    return pricing._book(stub, {}, {"same_fico": {"sentence": sentence, "dot_raw": dot_raw}}, {"same_fico": ({"g": np.array(g5, float)}, {"g": np.array(gt, float)})})


book_small = book_of([-8, -8, 0, 0], [-8, -8, 0, 0], [-8, -8, 0, 0])
assert book_small["label"] == "a retail" and book_small["share"] == 0.5 and book_small["lc"] == 0 and book_small["closed"] == [] and book_small["rest"] == [], "under 100 loans in a month or the rest, none printed"
assert book_of([-8, -8, -8, 0, 0, 0, 0, 0], [-8, -8, -8, 0, 0, 0, 0, 0], [-8, -8, -8, 0, 0, 0, 0, 0], first=3)["share"] == 0.375, "its share of the loans"
assert book_of([8, 8, 0, 0], [8, 8, 0, 0], [8, 8, 0, 0]) is None, "the other sign names no one"
assert book_of([-8, -8, 0, 0], [-8, -8, 0, 0], [-0.4, -0.4, 0, 0]) is None, "a share of next to nothing names no one"
assert book_of([-8, -8, 0, 0], [-8, -8, 0, 0], [-8, -8, 0, 0], sentence="Too few to compare yet.") is None, "no finding, no one named"
book_against = [12.0] * 150 + [-40.0] * 150 + [0.0] * 300
assert book_of(book_against, book_against, book_against, first=300, agency=["FNMA"] * 150 + ["FHLMC"] * 150 + ["FNMA"] * 150 + ["FHLMC"] * 150, dot_raw=-7.0) is None, "a gap of the other sign at Fannie names no one, however much of it one lender carries"
book_months = ["2026-09-01"] * 150 + ["2026-10-01"] * 150 + ["2026-09-01"] * 150 + ["2026-10-01"] * 150
book_big = book_of([-9] * 150 + [-3] * 150 + [-1] * 300, [-8] * 150 + [-2] * 150 + [-1] * 300, [-7] * 150 + [-1] * 150 + [-1] * 300, close=book_months)
assert [m for m, _, _ in book_big["closed"]] == ["2026-09-01", "2026-10-01"] and book_big["closed"][0][1] == [-9.0, -8.0, -7.0] and book_big["closed"][1][2] == -2.5 and book_big["rest"] == [-1.0, -1.0, -1.0], book_big
assert book_of([-9] * 150 + [3] * 150 + [-1] * 300, [-8] * 150 + [2] * 150 + [-1] * 300, [-7] * 150 + [1] * 150 + [-1] * 300, close=book_months) is None, "a month wholly against the row"
# Carrying it holds at Fannie alone too, where a method reads there on 100+ loans and 1+ bp: here one lender carries it at Freddie and the other at Fannie, so no one lender does on both.
book_gses = ["FNMA"] * 150 + ["FHLMC"] * 150 + ["FNMA"] * 150 + ["FHLMC"] * 150
book_split = [-1.0] * 150 + [-9.0] * 150 + [-9.0] * 150 + [0.0] * 150
assert book_of(book_split, book_split, book_split, agency=book_gses) is None, "carried at Fannie by the other lender"
assert book_of([-9.0] * 300 + [-1.0] * 300, [-9.0] * 300 + [-1.0] * 300, [-9.0] * 300 + [-1.0] * 300, agency=book_gses)["label"] == "a retail", "the same lender at both"
book_few = ["FHLMC"] * 300 + ["FNMA"] * 99 + ["FHLMC"] * 201
assert book_of([-9.0] * 300 + [-9.0] * 99 + [-1.0] * 201, [-9.0] * 300 + [-9.0] * 99 + [-1.0] * 201, [-9.0] * 300 + [-9.0] * 99 + [-1.0] * 201, agency=book_few)["label"] == "a retail", "under 100 loans at Fannie the test is not read"
assert book_of([-9.0] * 300 + [0.5] * 150 + [-1.0] * 150, [-9.0] * 300 + [0.5] * 150 + [-1.0] * 150, [-9.0] * 300 + [0.5] * 150 + [-1.0] * 150, agency=["FHLMC"] * 300 + ["FNMA"] * 300)["label"] == "a retail", "under 1 bp at Fannie the test is not read"
# The book's words: looks smaller only while the later month's midpoint is nearer zero; few weeks in words; the rest only while it has its reads.
line_of_book = {"label": "A book", "weeks": 6, "closed": [("2026-08-01", [-16.2, -13.6, -9.3], -14.9), ("2026-09-01", [-7.2, -5.6, -3.1], -6.4)], "rest": [-1.2, 1.3, -1.6]}
assert pricing._book_line(line_of_book) == "Over time: A book's gap looks smaller on later loans, on few weeks of loans: about −17 to −9 closed in August and −8 to −3 closed in September. All others: about −2 to +1.5.", pricing._book_line(line_of_book)
assert pricing._book_line({**line_of_book, "weeks": 9, "closed": line_of_book["closed"][::-1]}) == "Over time: A book's gap by closing month, on 9 weeks of loans: about −8 to −3 closed in September and −17 to −9 closed in August. All others: about −2 to +1.5.", "the later month further from zero"
assert pricing._book_line({**line_of_book, "rest": [], "closed": line_of_book["closed"][:1]}) == "Over time: A book's gap, on few weeks of loans: about −17 to −9 closed in August." and pricing._book_line({**line_of_book, "closed": []}) is None and pricing._book_line(None) is None
# The same-FICO figure by what is held equal, from the data; the row's own range under the printed rule.
said_method = next(r["text"] for r in views_b["limit"] if r["key"] == "method")
assert re.fullmatch(r"Controls, same FICO: about [+−0-9]+ with only lender, channel, week, GSE and FICO; about [+−0-9]+ in a simple regression; about [+−0-9.]+ on exact match within 5 points; about [+−0-9.]+ on exact match within one LLPA tier; about [+−0-9.]+ on the model, which also holds occupancy, units, property type, second liens, loan size, DTI, mortgage insurance, state, first-time buyers, number of borrowers and loan program\.", said_method) and f"about {pricing._signed(pricing._near(row_b['same_fico']['cell5']))} on exact match within 5 points; about {pricing._signed(pricing._near(row_b['same_fico']['tier']))} on exact match within one LLPA tier; about {pricing._signed(pricing._near(row_b['same_fico']['model']))} on the model" in said_method and pricing.MODEL_HOLDS in meta_a["stamp_more"], said_method
# Each figure in its own place: here the tier read's comparators run 10 points up, so the two exact matches differ.
views_controls = rate_views(pricing.build_rates(rate_con(gap_book(a_week=12), "x_controls")))
gap_row = next(r for r in views_controls["row"] if r["key"] == "same_fico")
assert abs(gap_row["cell5"] - gap_row["tier"]) >= 1 and f"about {pricing._signed(pricing._near(gap_row['cell5']))} on exact match within 5 points; about {pricing._signed(pricing._near(gap_row['tier']))} on exact match within one LLPA tier;" in next(r["text"] for r in views_controls["limit"] if r["key"] == "method"), gap_row
# With Rocket correspondent back in, the lower-LLPA range says where it reaches, its top end its own read.
rc_back = rate_book(gap=0, lower=-8)
for r in rc_back:
    if (r["seller"], r["channel"]) == ("rocket-mortgage", "C") and r["score_model"] == "V" and r["vs4"] == r["classic_fico"] + 20:
        r["orig_rate"] = round(r["orig_rate"] + 0.9, 3)
rc_back_views = rate_views(pricing.build_rates(rate_con(rc_back, "x_rc_back")))
rc_back_lower = next(r for r in rc_back_views["row"] if r["key"] == "lower_llpa")
assert rc_back_lower["th"] < 0 and re.search(r" With Rocket correspondent back, the lower-LLPA range reaches \+[\d.]+\.$", next(r["text"] for r in rc_back_views["limit"] if r["key"] == "thin")), (rc_back_lower["th"], next(r["text"] for r in rc_back_views["limit"] if r["key"] == "thin"))
assert not re.search(r"reaches \+", next(r["text"] for r in views_b["limit"] if r["key"] == "thin")), "not above zero here: its Rocket correspondent loans read about the same"
# Its words on planted ends: the top end rounds outward, and nothing unless it reads.
assert pricing._rc_back(2.59, -2.5) == " With Rocket correspondent back, the lower-LLPA range reaches +3.", pricing._rc_back(2.59, -2.5)
assert pricing._rc_back(-0.51, -2.5) == " With Rocket correspondent back, the lower-LLPA range reaches −0.5.", "still below zero, and it says so"
assert pricing._rc_back(float("nan"), -2.5) == "" and pricing._rc_back(2.59, None) == "", "nothing unless both read"
# The main rows converge: the passes reach the projections, so a few stop short and a thousand do not.
absorb_v, absorb_groups = np.array([3.0, 1.0, 0.0, 2.0, 7.0, 5.0]), [(np.array([0, 0, 1, 1, 2, 2]), np.array([2.0, 2.0, 2.0])), (np.array([0, 1, 1, 2, 2, 0]), np.array([2.0, 2.0, 2.0]))]
assert np.abs(pricing._absorb(absorb_v, absorb_groups, 1e-12, 1) - pricing._absorb(absorb_v, absorb_groups, 1e-12, 1000)).max() > 1e-6 and pricing.LINE_PASSES == 1000, "passes"
said_book = next(r["text"] for r in views_d["limit"] if r["key"] == "book")
assert ", on 10 weeks of loans:" in said_book and said_book.startswith("Over time: UWM broker's gap "), said_book
# The match line: which loans the two exact matches reach, by count. How far that moves the model's read stays in the workbook's table, on 100+ loans each side, 2+ bp apart.
match_stub = lambda far, a=150, b=150: _NS(tv=np.ones(a + b, bool), gap_fico=np.array([-8.0] * a + [-8.0 + far] * b))  # noqa: E731
match_cells = lambda a=150, b=150: {"same_fico": ({"g": np.array([1.0] * a + [np.nan] * b)},)}  # noqa: E731
match_rows = {"same_fico": {"read5": 3120, "read_tier": 4860, "n": 6240}, "lower_llpa": {"read5": 1240, "read_tier": 2360, "n": 3120}, "same_llpa": {"read5": 1910, "read_tier": 2610, "n": 3090}, "same_number": {"read5": 9150, "read_tier": 12260, "n": 15410}}
match_head = "Which loans match: by exact match, 3,100 to 4,900 of about 6,200 same-FICO loans and 9,200 to 12,300 of about 15,400 same-number loans find FICO loans to compare."
assert pricing._match_reads(match_stub(5.0), match_cells()) == (-8.0, 150, -3.0, 150) and pricing._match_reads(match_stub(1.5), match_cells()) is None and pricing._match_reads(match_stub(5.0, 99), match_cells(99)) is None and pricing._match_reads(match_stub(5.0, 150, 99), match_cells(150, 99)) is None, "two model reads on 100+ loans each"
assert pricing._match_line(match_rows) == match_head, pricing._match_line(match_rows)
match_none = {"read5": 0, "read_tier": 0, "n": 0}
assert pricing._match_line({**match_rows, "lower_llpa": match_none, "same_llpa": match_none}) == match_head and pricing._match_line({**match_rows, "same_number": match_none}) == "Which loans match: by exact match, 3,100 to 4,900 of about 6,200 same-FICO loans find FICO loans to compare." and pricing._match_line({"same_fico": match_none, "lower_llpa": match_none, "same_llpa": match_none, "same_number": match_rows["same_number"]}) == "Which loans match: by exact match, 9,200 to 12,300 of about 15,400 same-number loans find FICO loans to compare." and pricing._match_line({k: match_none for k in match_rows}) is None, "a row with no loans says nothing"
match_near = rate_book(gap=4)
match_near = [r for r in match_near if (r["seller"], r["channel"]) in (("rocket-mortgage", "R"), ("united-wholesale-mortgage", "B"), ("rocket-mortgage", "C")) and r["vs4"] != 830]
match_rng = random.Random(31)
match_near += [rate_row(991000 + 100 * w + k, "rocket-mortgage", "R", week, rate_rate(match_rng, "rocket-mortgage|R", w, 706) + 0.04, "V", 706, 707, agency="FNMA" if w % 2 else "FHLMC") for w, week in enumerate(RATE_WEEKS) for k in range(5)]
assert "match_with" not in {r["key"] for r in rate_views(pricing.build_rates(rate_con(match_near, "x_match")))["behind"]}, "Rocket correspondent stays out of it, and too few loans find no match"
# The lead line: the two rows must have findings, and all three methods must read.
s_lead = pricing._sample(rate_con(between_book(-6.0), "x_bt"))
s_lead.fits = pricing._fit_all(s_lead)
lead_about = {"same_fico": {"sentence": "About 6 bp lower."}, "same_number": {"sentence": "About 6 bp higher."}}
assert pricing._between(s_lead, lead_about) is True and pricing._between(s_lead, {**lead_about, "same_fico": {"sentence": "Too few to compare yet."}}) is False, "no lead on a blank row"
s_lead.gap_number = np.full(s_lead.n, np.nan)
assert pricing._between(s_lead, lead_about) is False, "all three methods"
s_lead_up = pricing._sample(rate_con(between_book(-6.0), "x_bt3"))
s_lead_up.fits = pricing._fit_all(s_lead_up)
assert pricing._between(s_lead_up, lead_about) is True, "the plant reads between"
s_lead_up.gap_fico = np.where(np.isnan(s_lead_up.gap_fico), s_lead_up.gap_fico, 1.5)
assert pricing._gap(s_lead_up.bp, s_lead_up.tv & (s_lead_up.vs < 820), s_lead_up.fic & ~s_lead_up.rc, s_lead_up.cell_f5)["est"] < 0 and pricing._between(s_lead_up, lead_about) is False, "the model above zero at its FICO, with both cell reads below"
# What the rows rest on: the share of VS4 loans issued since Oct 1, only while every VS4 loan showing a FICO is so issued and no earlier loan of any kind shows both scores.
rests_of = lambda vs: next(r["text"] for r in vs["limit"] if r["key"] == "rests_on")  # noqa: E731
oct_only = [r for r in rate_book(gap=4) if r["score_model"] == "C" or r["issue_month"] >= "2026-10-01"]
views_oct = rate_views(pricing.build_rates(rate_con(oct_only, "x_oct")))
assert rests_of(views_oct).endswith(" of these VS4 loans. Same-FICO loans are about 98% of VS4 loans issued since Oct 1, as no earlier loan shows both scores.") and rests_of(views_oct).startswith("Narrow base: Rocket and UWM are ") and rests_of(views).endswith(" of these VS4 loans.") and "issued since" not in rests_of(views), rests_of(views_oct)
# The share of VS4 loans issued since is on those issued from Oct 1, shown and not; the head goes with the top two's share.
oct_some = oct_only + [rate_row(987000 + k, "rocket-mortgage", "R", RATE_WEEKS[8], 6.5, "V", None, 720) for k in range(180)] + [rate_row(987500 + k, "rocket-mortgage", "R", RATE_WEEKS[0], 6.5, "V", None, 720) for k in range(400)]
assert " about 67% of VS4 loans issued since Oct 1," in rests_of(rate_views(pricing.build_rates(rate_con(oct_some, "x_oct_some")))), rests_of(rate_views(pricing.build_rates(rate_con(oct_some, "x_oct_some"))))
assert pricing._rests_on(["A", "B"], 0.75) == "Narrow base: A and B are 75% of these VS4 loans." and pricing._rests_on(["A", "B"], 0.74) == "Who is in these figures: A and B are 74% of these VS4 loans." and pricing._rests_on(["A"], 0.6) == "Who is in these figures: A is 60% of these VS4 loans." and pricing._rests_on(["A", "B"], 0.9, 0.61) == "Narrow base: A and B are 90% of these VS4 loans. Same-FICO loans are about 61% of VS4 loans issued since Oct 1, as no earlier loan shows both scores.", "the head is a claim, under its guard"
fico_early = oct_only + [rate_row(985000 + k, "other-bank", "R", RATE_WEEKS[0], 6.5, "C", 700, 720) for k in range(5)]
assert "issued since" not in rests_of(rate_views(pricing.build_rates(rate_con(fico_early, "x_early")))), "a FICO loan showing both scores before Oct 1"
one_lender_rests = rests_of(rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=4) if r["seller"] == "rocket-mortgage"], "x_one_lender"))))
assert one_lender_rests == "Narrow base: Rocket is 100% of these VS4 loans.", one_lender_rests
assert "Same-FICO loans are" not in rests_of(rate_views(pricing.build_rates(rate_con([{**r, "classic_fico": ""} if r["score_model"] == "V" else r for r in oct_only], "x_oct_none")))), "no loan showing a FICO, so nothing to say of them"
# The same-number line through the build: its range from the row's own thin line, and what it means only above zero.
firm_book = between_book(0.0)
for r in firm_book:
    if r["score_model"] == "V":
        r["orig_rate"] = round(r["orig_rate"] + (-0.08 if r["seller"] == "united-wholesale-mortgage" else 0.04), 3)
firm_views = rate_views(pricing.build_rates(rate_con(firm_book, "x_firm")))
firm_rows = {r["key"]: r for r in firm_views["row"]}
assert firm_rows["same_number"]["tl"] > 0 and firm_views["answer"][-1]["text"].endswith(f" 95% range about {pricing._range(*pricing._out95(firm_rows['same_number']['tl'], firm_rows['same_number']['th']))}. It says a VS4 number has got the rate of a lower FICO, not that VS4 costs more.") and "firmest" not in firm_views["meta"][0]["answer"], firm_views["answer"][-1]
assert "firmest" not in views["meta"][0]["answer"] and "firmest" not in json.dumps(firm_views["limit"]), "gone everywhere"
# Money only beside a finding: a row printing a figure but no finding has none, though its dot stays.
sentence_kept, pricing.answer_sentence = pricing.answer_sentence, lambda *a: "No visible difference."
rows_flat = pricing._read_rows(s_a)[0]
pricing.answer_sentence = sentence_kept
assert rows_flat["same_number"]["dot"] == 4 and rows_flat["same_number"]["sentence"] == "No visible difference." and rows_flat["same_number"]["money"] is None and row_a["same_number"]["money"] and row_a["same_fico"]["money"] is None, rows_flat["same_number"]
# The thin line's top end with Rocket correspondent in is its own read, well past the row's; and only while the row is drawn.
thin_b_said = next(r["text"] for r in rc_back_views["limit"] if r["key"] == "thin")
thin_first_top = float(re.search(r"reaches ([+−][\d.]+)\.$", thin_b_said).group(1).replace("−", "-"))
assert thin_first_top > rc_back_lower["th"] + 1, (thin_b_said, rc_back_lower["th"])
assert "With Rocket correspondent back" not in next(r["text"] for r in views["limit"] if r["key"] == "thin") and row_a["lower_llpa"]["dot"] is None, "no lower-LLPA row drawn"
thin_few = rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=0, lower=-8) if r["first_intraday_date"] <= RATE_WEEKS[2][0]], "x_thin_few")))
assert all(r["dot"] is None and r["th"] is not None for r in thin_few["row"]) and "With Rocket correspondent back" not in next(r["text"] for r in thin_few["limit"] if r["key"] == "thin"), "too few lender-weeks: the rows draw no line for it to speak of"
assert "With Rocket correspondent back" not in next(r["text"] for r in rate_views(pricing.build_rates(rate_con([r for r in rate_book(gap=0, lower=-8) if (r["seller"], r["channel"]) != ("rocket-mortgage", "C")], "x_no_rc")))["limit"] if r["key"] == "thin"), "none in the sample"
# How far below its number: the range from resampling weeks inside each lender and channel, its ends outward in whole points, the two lenders beside it, how many points 1 bp moves it; near the old rule only within 5 points of it. Here FICO loans fall 3 bp per 10 points through every band, so a VS4 loan 6 bp over at its number has priced 20 points below it.


def priced_book(at_number):
    rng, out, i = random.Random(47), [], 0
    rate = lambda lift, w, score: 6.5 + lift + 0.02 * w - 0.003 * (score - 700) + rng.uniform(-0.01, 0.01)  # noqa: E731
    for seller, channel, lift in (("rocket-mortgage", "R", 0.03), ("united-wholesale-mortgage", "B", -0.02)):
        for w, week in enumerate(RATE_WEEKS):
            agency = "FNMA" if w % 2 else "FHLMC"
            for k in range(240):
                f = 640 + 5 * (k % 40)
                out.append(rate_row(i, seller, channel, week, rate(lift, w, f), "C", f, agency=agency))
                i += 1
            for k in range(60):
                vs = 700 + 5 * (k % 12)
                out.append(rate_row(i, seller, channel, week, rate(lift, w, vs) + at_number / 100, "V", None, vs, agency=agency))
                i += 1
    return out


views_priced = rate_views(pricing.build_rates(rate_con(priced_book(6.0), "x_priced")))
priced_at = views_priced["meta"][0]["equivalent_stat"]
assert re.fullmatch(r"On average, a FICO about \d+( to \d+)? points below the VS4 number \(95% range\)\. Near the old rule's 20 points, which does not show the rule caused it\.", priced_at) and re.fullmatch(r"Which FICO pays the same \(95% ranges, which resample weeks, not lenders, so they run narrow\): about \d+( to \d+)? at Rocket retail, about \d+( to \d+)? at UWM\. A 1 bp change in the gap moves this about 3\.5 points\.", views_priced["meta"][0]["equivalent_more"]), (priced_at, views_priced["meta"][0]["equivalent_more"])
assert "ear the old rule" not in views_priced["meta"][0]["equivalent_caption"] and views_priced["meta"][0]["equivalent_caption"].endswith(caption_end) and "That is near those 20 points, which does not show the grid caused it." in next(r["text"] for r in views_priced["quote"] if r["text"].startswith("On average")), views_priced["meta"][0]["equivalent_caption"]
priced_others = [{**r, "seller": "other-bank", "channel": "R"} if r["seller"] == "rocket-mortgage" else {**r, "seller": "small-bank", "channel": "R"} for r in priced_book(6.0)]
assert rate_views(pricing.build_rates(rate_con(priced_others, "x_priced_others")))["meta"][0]["equivalent_more"] == "Which FICO pays the same: a 1 bp change in the gap moves this about 3.5 points.", "no bracket with no lender to name"
s_others = pricing._sample(rate_con(priced_others, "x_priced_others2"))
s_others.fits = pricing._fit_all(s_others)
curve_kept = pricing._priced_curve
pricing._priced_curve = lambda s_: (lambda at, c: (at, np.column_stack([c[:, :-1], c[:, 0] + 1.0])))(*curve_kept(s_))
priced_silent = pricing._priced_line(s_others, {})
pricing._priced_curve = curve_kept
assert priced_silent["more"] is None and priced_silent["per_bp"] is None and priced_silent["stat"].startswith("On average, a FICO about "), priced_silent["more"]
priced_far = rate_views(pricing.build_rates(rate_con(priced_book(12.5), "x_priced_far")))
priced_far_quote = next(r["text"] for r in priced_far["quote"] if r["text"].startswith("On average"))
assert priced_far["meta"][0]["equivalent_stat"].startswith("On average, a FICO about ") and "ear the old rule" not in priced_far["meta"][0]["equivalent_stat"] and "ear the old rule" not in priced_far["meta"][0]["equivalent_caption"] and "That is near" not in priced_far_quote and priced_far_quote.startswith("On average a VS4 number under 820 has got the rate of a FICO about "), (priced_far["meta"][0]["equivalent_stat"], priced_far_quote)
s_priced = pricing._sample(rate_con(priced_book(6.0), "x_priced_s"))
s_priced.fits = pricing._fit_all(s_priced)
at_priced, curve_priced = pricing._priced_curve(s_priced)
priced_ends = pricing._priced_range(s_priced, at_priced, curve_priced)
assert curve_priced.shape == (len(at_priced), len(pricing.PRICED_K)) and priced_ends == pricing._priced_range(s_priced, at_priced, curve_priced) and priced_ends[0] == np.floor(round(priced_ends[2], 2)) and priced_ends[1] == np.ceil(round(priced_ends[3], 2)) and isinstance(priced_ends[0], int) and isinstance(priced_ends[1], int), "seeded, its ends outward in whole points"
assert pricing._priced_range(s_priced, at_priced, curve_priced, s_priced.seller == "no-such-lender") is None, "under 100 loans"
s_never = pricing._sample(rate_con(priced_book(-5.0), "x_priced_never"))
s_never.fits = pricing._fit_all(s_never)
assert pricing._priced_line(s_never, {}) is None, "a gap below zero at its own number never crosses"
priced_shaky = priced_book(1.0)
for r in priced_shaky:
    if r["score_model"] == "V":
        r["orig_rate"] = round(r["orig_rate"] + (0.15 if RATE_WEEKS.index(next(w for w in RATE_WEEKS if w[0] == r["first_intraday_date"])) % 2 else -0.15), 3)
s_shaky = pricing._sample(rate_con(priced_shaky, "x_priced_shaky"))
s_shaky.fits = pricing._fit_all(s_shaky)
at_shaky, curve_shaky = pricing._priced_curve(s_shaky)
assert pricing._priced_range(s_shaky, at_shaky, curve_shaky) is None, "too many draws never cross zero to call it a range"
s_small = pricing._sample(rate_con(rate_book(gap=4, vs4_a_week=2), "x_small"))
s_small.fits = pricing._fit_all(s_small)
assert pricing._priced_below(s_small, s_small.fits) == [] and pricing._priced_line(s_small, {}) is None, "under 100 loans, no points below"
# The quote's lines, each standing alone when pasted, each clause under its row's guard.
quote_s = _NS(after=np.array([True, True, True]), tv=np.array([True, True, False]), is_v=np.array([True, True, True]), rc=np.array([False, False, True]), vs=np.array([700, 830, 700]), first_date=np.array(["2026-08-10", "2026-09-14", "2026-07-27"]))
quote_rows = {"same_fico": {"sentence": "About 9 bp lower.", "dot": -9.0, "tl": -14.2, "th": 1.1, "lo_raw": -11.3, "hi_raw": -7.1}, "same_llpa": {"sentence": "No visible difference.", "dot": 1.5, "tl": -2.2, "th": 3.3}, "same_llpa_low": {"sentence": "Not clearly different from zero.", "dot": -6.5, "lo": -9.0, "hi": 3.0}, "same_number": {"sentence": "About 7.5 bp higher.", "dot": 7.5, "tl": 5.2, "th": 9.1, "money": "About $17 a month on $350,000"}}
quote_priced = {"range": "about 35 to 45", "point": 24.5, "closed": 0.51, "top": ["Lender A", "Lender B"], "top_share": 0.91}
quote_lender = {"label": "A book", "dot": -9.5, "lo": -2.5, "hi": 0.5, "rough": True, "methods": (-12.0, -7.5, -3.5, 2.5)}
quote_want = ["At the same FICO, lender, channel, timing, purpose and LTV range, VS4 loans issued from Oct 1 and showing a FICO ran about 9 bp below FICO loans' note rates (95% range about −14.5 to +1.5; about +1 with few controls), before points and lender credits, which do not show. Most of it is A book, about −9.5 against about −2.5 to +0.5 at other lender groups (−12 to −7.5 and −3.5 to +2.5 across the methods), on few weeks of loans. Most of these rates were likely set before the Sep 29 announcement of one LLPA grid for both scores. Lenders can pick the score, so this shows where a gap sits, not what choosing VS4 is worth. Rocket correspondent is left out; with it the top of the range is +6.5.",
              "At the same FICO, where both scores carry the same LLPA on the Oct 1 grid, VS4 loans issued from Oct 1 ran about 1.5 bp above FICO loans' note rates (95% range about −2.5 to +3.5): about +3.5 bp at FICO 780+, where rates stop falling with the score, and about −6.5 bp below 780 (−9 to +3 across the methods), so this cannot tell a discount there from none. Most of these rates were likely set earlier, when the LLPA grid counted VS4 as 20 points lower. Rocket correspondent is left out; with it the top of the range is +9.5.",
              "At the same score number under 820 (VS4 720 against FICO 720), VS4 loans first disclosed from Aug 10 ran about 7.5 bp above FICO loans' note rates (95% range about +5 to +9.5), higher at every lender group large enough to read, with Rocket correspondent left out. That says a VS4 number has got the rate of a lower FICO, not that VS4 costs more: where a FICO shows (loans issued from Oct 1, about one of these in three), they are about 8.5 bp below the rate at their FICO. About one VS4 loan in two is 820+ and not in this figure. The 7.5 bp is about $17 a month on $350,000, before points and lender credits, which do not show.",
              "On average a VS4 number under 820 has got the rate of a FICO about 35 to 45 points lower (95% range, too narrow: it resamples weeks, not lenders), on loans issued from Oct 1, most with rates likely set while the LLPA grid still counted VS4 as 20 points lower. That is near those 20 points, which does not show the grid caused it. This is how Lender A and Lender B have priced, Rocket correspondent left out, not a conversion."]
quote_of = lambda rows=quote_rows, book={"label": "A book"}, priced=quote_priced, clause="at every lender group shown", split=answer_split, plain=(1.2, -1.4), s=quote_s, closed=0.51, closed_same=0.51, rc_tops={"same_fico": 6.11, "same_llpa": 9.11}, same_at=-8.5, curve=(26.0, 6.2, 0.31, True), lender=quote_lender, same_range=None, mix=None, lower_under_top=False: [r["text"] for r in pricing._quote(s, rows, book, priced, clause, split, plain, closed, closed_same, rc_tops, same_at, curve, lender, same_range, mix, lower_under_top)]  # noqa: E731
assert quote_of() == quote_want, quote_of()
# Line 0.
assert quote_of(lender=None)[0].count(" Most of it is A book. ") == 1 and "at other lender groups" not in quote_of(lender=None)[0] and "Most of it" not in quote_of(lender=None, book=None)[0], "the lender figures, else the book's name, else neither"
assert "(−12 to −7.5" not in quote_of(lender={**quote_lender, "methods": None})[0] and "about −2.5 to +0.5 at other lender groups, on few weeks of loans." in quote_of(lender={**quote_lender, "methods": None})[0] and "at other lender groups (−12 to −7.5 and −3.5 to +2.5 across the methods)." in quote_of(lender={**quote_lender, "rough": False})[0] and "about −2.5 at other lender groups" in quote_of(lender={**quote_lender, "hi": -2.5})[0], "each clause under its guard"
assert "few controls" not in quote_of(plain=(float("nan"), -1.4))[0] and "(95% range about −14.5 to +1.5)" in quote_of(plain=(float("nan"), -1.4))[0] and "few controls" not in quote_of(plain=(-12.0, -1.4))[0] and "few controls" not in quote_of(plain=(-9.0, -8.4))[0] and "depending on what is held equal" not in quote_of()[0], "the plain read only while it is the near end"
assert "Most of these rates" not in quote_of(closed=0.5)[0] and "Most of these rates" not in quote_of(closed=float("nan"))[0] and quote_of(closed=0.5)[0].count("on few weeks of loans. Lenders can pick the score,") == 1, quote_of(closed=0.5)[0]
assert "VS4 loans showing a FICO ran" in quote_of(s=_NS(**{**vars(quote_s), "after": np.array([True, False, True])}))[0] and "issued from Oct 1 and" not in quote_of(s=_NS(**{**vars(quote_s), "after": np.array([True, False, True])}))[0], "from Oct 1 only while all are"
assert "Rocket correspondent" not in quote_of(rc_tops=None)[0] and "Rocket correspondent" not in quote_of(rc_tops={"same_fico": float("nan"), "same_llpa": 9.11})[0] and "Rocket correspondent" not in quote_of(s=_NS(**{**vars(quote_s), "rc": np.array([False, False, False])}))[0] and "Rocket correspondent" not in quote_of(rows={**quote_rows, "same_fico": {**quote_rows["same_fico"], "tl": None}})[0], "its sentence while it exists, its top end reads and there is a range for it to speak of"
assert quote_of(rc_tops={"same_fico": 2.59})[0].count("with it the top of the range is +3.") == 1, "its end rounds outward"
assert quote_of(rows={**quote_rows, "same_fico": {**quote_rows["same_fico"], "sentence": "No visible difference.", "dot": 0.5}})[0].count("showing a FICO ran about level with FICO loans' note rates (95% range") == 1, "under 1 bp, level"
assert quote_of(rows={**quote_rows, "same_fico": {**quote_rows["same_fico"], "sentence": "About 3 bp higher.", "dot": 3.0}})[0].count("showing a FICO ran about 3 bp above FICO loans' note rates") == 1, "the other sign"
# Line 1.
assert "VS4 loans ran about 1.5 bp above" in quote_of(s=_NS(**{**vars(quote_s), "after": np.array([True, False, True])}))[1], "from Oct 1 only while all are"
assert quote_of(split=None)[1] == "At the same FICO, where both scores carry the same LLPA on the Oct 1 grid, VS4 loans issued from Oct 1 ran about 1.5 bp above FICO loans' note rates (95% range about −2.5 to +3.5). Most of these rates were likely set earlier, when the LLPA grid counted VS4 as 20 points lower. Rocket correspondent is left out; with it the top of the range is +9.5.", quote_of(split=None)[1]
assert quote_of(closed_same=0.5)[1].endswith("so this cannot tell a discount there from none. Rocket correspondent is left out; with it the top of the range is +9.5.") and "Most of these rates were likely set earlier" in quote_of(closed=0.1)[1], "most of its own loans, not the row above"
assert quote_of(rc_tops={"same_fico": 6.11})[1].endswith("when the LLPA grid counted VS4 as 20 points lower.") and "Rocket correspondent" not in quote_of(rows={**quote_rows, "same_llpa": {**quote_rows["same_llpa"], "tl": None}})[1], "its own top end, under its own guard"
assert "across the methods" not in quote_of(rows={k: v for k, v in quote_rows.items() if k != "same_llpa_low"})[1] and "across the methods" not in quote_of(rows={**quote_rows, "same_llpa_low": {"sentence": "Too few to compare yet.", "dot": None, "lo": None, "hi": None}})[1] and quote_of(split={**answer_split, "open": False})[1].count("below 780 (−9 to +3 across the methods). Most") == 1 and "FICO 640" not in quote_of()[1] and quote_of(rows={**quote_rows, "same_llpa": {**quote_rows["same_llpa"], "dot": 0.5}})[1].count("ran about level with FICO loans' note rates (95% range") == 1, "each clause under its guard"
# Line 2.
assert quote_of(clause=None)[2].startswith("At the same score number under 820 (VS4 720 against FICO 720), VS4 loans first disclosed from Aug 10 ran about 7.5 bp above FICO loans' note rates (95% range about +5 to +9.5), with Rocket correspondent left out."), quote_of(clause=None)[2]
assert quote_of(same_range=(-9.5, -3.0))[2].count("they are about 8.5 bp below the rate at their FICO (95% range about −9.5 to −3 under 820; with 820+ it reaches +1.5). About") == 1 and "95% range about −9.5" not in quote_of(same_range=(-9.5, -3.0), same_at=None)[2], "the range goes with its figure, and says so where it clears zero and the whole row does not"
assert quote_of(same_range=(-9.5, 1.0))[2].count("at their FICO (95% range about −9.5 to +1). About") == 1 and quote_of(same_range=(-9.5, -3.0), rows={**quote_rows, "same_fico": {**quote_rows["same_fico"], "th": -2.0}})[2].count("at their FICO (95% range about −9.5 to −3). About") == 1, "only where the two part at zero"
assert "where a FICO shows (about one of these in three), they" in quote_of(curve=(26.0, 6.2, 0.31, False))[2], "from Oct 1 only while all are"
quote_low = {**quote_rows, "lower_llpa": {"sentence": "About 12.5 bp lower.", "dot": -12.5}}
assert quote_of(rows=quote_low)[0].count("Across lenders the gap is about −12.5 where VS4 has the lower LLPA on the Oct 1 grid and about +1.5 where the LLPA is the same (about −6.5 below FICO 780; −9 to +3 across the methods), which does not show the LLPA caused it. Lenders can pick") == 1 and quote_of(rows=quote_low, lower_under_top=True)[0].count("(about −6.5 below FICO 780, where all the lower-LLPA loans sit; −9 to +3 across the methods), which") == 1 and quote_of(rows={**quote_low, "same_llpa": {**quote_rows["same_llpa"], "dot": 0.5}})[0].count("the Oct 1 grid and about level where the LLPA is the same (about") == 1, "where the gap sits, and that this does not show why"
assert quote_of(rows={k: v for k, v in quote_low.items() if k != "same_llpa_low"})[0].count("where the LLPA is the same, which does not show") == 1 and quote_of(rows={**quote_low, "same_llpa_low": {"sentence": "Too few to compare yet.", "dot": None, "lo": None, "hi": None}})[0].count("where the LLPA is the same, which does not show") == 1, "the row under 780 only while it reads"
assert quote_of(rows={**quote_low, "lower_llpa": {"sentence": "Not clearly different from zero.", "dot": -12.5}})[0].count("across the methods). Lenders can pick") == 1 and quote_of(rows={**quote_low, "lower_llpa": {"sentence": "About 0.5 bp lower.", "dot": -0.5}})[0].count("across the methods). Lenders can pick") == 1 and "the gap is about" not in quote_of(rows={**quote_low, "lower_llpa": {"sentence": "Too few to compare yet.", "dot": None}})[0] and "the gap is about" not in quote_of(rows={**quote_low, "same_llpa": {"sentence": "Too few to compare yet.", "dot": None, "tl": None, "th": None}})[0] and "the gap is about" not in quote_of()[0], "each clause under its guard"
assert "Take 20 points" not in quote_of()[2] and "not that VS4 costs more: where a FICO shows, they are about 8.5 bp below" in quote_of(curve=None)[2], "the share of these loans only while it reads"
assert "not that VS4 costs more. About" in quote_of(same_at=None)[2] and "not that VS4 costs more. About" in quote_of(same_at=0.5)[2] and "That says a VS4 number" not in quote_of(rows={**quote_rows, "same_number": {**quote_rows["same_number"], "sentence": "About 7.5 bp lower.", "dot": -7.5}})[2] and "That says a VS4 number" not in quote_of(rows={**quote_rows, "same_number": {**quote_rows["same_number"], "sentence": "Not clearly different from zero."}})[2] and "That says a VS4 number" not in quote_of(rows={**quote_rows, "same_fico": {**quote_rows["same_fico"], "sentence": "About 3 bp higher.", "dot": 3.0}})[2] and "That says a VS4 number" in quote_of(rows={**quote_rows, "same_fico": {**quote_rows["same_fico"], "sentence": "Not clearly different from zero.", "dot": 3.0}})[2], "what it means only on a finding above zero, and not with the same FICO clearly above zero too; the FICO clause only below"
assert ", lower at both A and B, " in quote_of(rows={**quote_rows, "same_number": {**quote_rows["same_number"], "sentence": "About 7.5 bp lower.", "dot": -7.5}}, clause="at both A and B")[2] and "every lender group" not in quote_of(rows={**quote_rows, "same_number": {**quote_rows["same_number"], "sentence": "No visible difference.", "dot": 1.5}})[2] and "every lender group" not in quote_of(rows={**quote_rows, "same_number": {**quote_rows["same_number"], "sentence": "About 0.5 bp higher.", "dot": 0.5}})[2], "the clause goes with a finding, and with the way the figure runs"
assert quote_of(s=_NS(**{**vars(quote_s), "vs": np.array([700, 800, 700])}))[2].count("820+") == 0, "820+ only while it has loans"
assert quote_of(rows={**quote_rows, "same_number": {**quote_rows["same_number"], "money": None}})[2].endswith("and not in this figure. Points and lender credits do not show.") and all("$" not in t for i, t in enumerate(quote_of()) if i != 2), "dollars only while the row prints them, and only on this line"
assert ", with Rocket correspondent left out" not in quote_of(s=_NS(**{**vars(quote_s), "rc": np.array([False, False, False])}))[2], "none to leave out"
# Line 3.
assert "That is near" not in quote_of(priced={**quote_priced, "point": 25.5})[3] and len(quote_of(priced=None)) == 3 , quote_of(priced=None)
assert quote_of(priced={**quote_priced, "whole": (30, 36)})[3].count("That is near") == 0 and quote_of(priced={**quote_priced, "whole": (17, 33)})[3].count("That is near") == 1, "the range printed beside it reaches as near"
assert quote_of(s=_NS(**{**vars(quote_s), "rc": np.array([False, False, False])}))[3].endswith("This is how Lender A and Lender B have priced, not a conversion."), "none to leave out"
assert quote_of(mix=(0.55, 0.15, None))[0].count("on few weeks of loans. Refinances are 55% of A book's loans here and 15% of the others'. Most of these rates") == 1 and quote_of(mix=(0.55, 0.15, "split"))[0].count("15% of the others', but the methods disagree on whether its gap is wider on refinances. Most") == 1 and "Refinances" not in quote_of(mix=(0.55, 0.15, None), lender=None)[0] and "Refinances" not in quote_of()[0], "the mix goes with the lender figures"
assert quote_of(priced={**quote_priced, "closed": 0.5})[3] == "On average a VS4 number under 820 has got the rate of a FICO about 35 to 45 points lower (95% range, too narrow: it resamples weeks, not lenders), on loans issued from Oct 1. That is near the 20 points the LLPA grid took off VS4 before Oct 1, which does not show the grid caused it. This is how Lender A and Lender B have priced, Rocket correspondent left out, not a conversion." and quote_of(priced={**quote_priced, "top_share": 0.89})[3].endswith("This is how these loans have priced, Rocket correspondent left out, not a conversion.") and quote_of(priced={**quote_priced, "top": ["Lender A"], "top_share": 0.95})[3].endswith("This is how Lender A has priced, Rocket correspondent left out, not a conversion.") and quote_of(priced={**quote_priced, "top": []})[3].endswith("This is how these loans have priced, Rocket correspondent left out, not a conversion."), "each under its guard"
# No fifth line: the lender figures sit in line 0.
assert len(quote_of()) == 4 and len(quote_of(lender=None)) == 4, "four lines"
# Each line under its row's guard.
quote_blank = {**quote_rows, "same_fico": {**quote_rows["same_fico"], "sentence": "Too few to compare yet.", "dot": None}, "same_llpa": {**quote_rows["same_llpa"], "sentence": "Too few to compare yet.", "dot": None}}
assert quote_of(rows=quote_blank) == quote_want[2:] and quote_of(rows={**quote_rows, "same_number": {**quote_rows["same_number"], "sentence": "Too few to compare yet.", "dot": None}}) == quote_want[:2], "each line under its row's guard"
# Through the build.
quote_between = views_between["quote"]
between_range = re.search(r"95% range about ([^)]+)\)", next(r["text"] for r in views_between["limit"] if r["key"] == "same_loans")).group(1)
assert any(f"at their FICO (95% range about {between_range}" in r["text"] for r in quote_between), (between_range, [r["text"] for r in quote_between])  # the quote's range is that line's
assert not any("$" in r["text"] for r in quote_between if not r["text"].startswith("At the same score number")), [r["text"] for r in quote_between]
assert re.fullmatch(r"At the same score number under 820 \(VS4 720 against FICO 720\), VS4 loans first disclosed from Aug 3 ran about 6 bp above FICO loans' note rates \(95% range about [+−0-9.]+ to [+−0-9.]+\), higher at both Rocket retail and UWM broker\. That says a VS4 number has got the rate of a lower FICO, not that VS4 costs more: where a FICO shows \(about \d+% of these\), they are about [\d.]+ bp below the rate at their FICO \(95% range about [+−0-9.]+ to [+−0-9.]+\)\. The 6 bp is about \$\d+ a month on \$350,000, before points and lender credits, which do not show\.", quote_between[1]["text"]), quote_between[1]["text"]
assert "Most of it is UWM broker." in next(r["text"] for r in views_split["quote"]), views_split["quote"]
assert views_priced["meta"][0]["stamp"].startswith("VS4 loans (those priced on VS4) are compared"), "no Rocket correspondent in this sample, so none named"
assert "This is how Rocket and UWM have priced, not a conversion." in next(r["text"] for r in views_priced["quote"] if r["text"].startswith("On average")), views_priced["quote"]
# Top two and timing on the line's own loans: VS4 loans issued before Oct 1 at another lender, and Rocket correspondent's, stay out of both; these loans closing in October take the timing clause.
priced_other = priced_book(6.0) + [rate_row(988000 + k, "other-bank", "R", RATE_WEEKS[k % 4], 6.5, "V", None, 720) for k in range(4000)] + [rate_row(992000 + k, "rocket-mortgage", "C", RATE_WEEKS[8], 6.5, "V", None, 720) for k in range(4000)]
views_other = rate_views(pricing.build_rates(rate_con(priced_other, "x_priced_other")))
assert next(r["text"] for r in views_other["quote"] if r["text"].startswith("On average")).endswith("This is how Rocket and UWM have priced, Rocket correspondent left out, not a conversion.") and ", most with rates likely set while the LLPA grid still counted VS4 as 20 points lower." in next(r["text"] for r in views_other["quote"] if r["text"].startswith("On average")), views_other["quote"]
priced_late = priced_book(6.0)
for r in priced_late:
    if r["issue_month"] >= "2026-10-01":
        r["first_pay_date"] = "2026-12-01"
    elif r["score_model"] == "V":
        r["orig_rate"] = round(r["orig_rate"] - 0.06, 3)
late_quote = next(r["text"] for r in rate_views(pricing.build_rates(rate_con(priced_late, "x_priced_late")))["quote"] if r["text"].startswith("On average"))
assert "likely set" not in late_quote and late_quote.startswith("On average a VS4 number under 820 has got the rate of a FICO about "), late_quote
# Chart 4's groups in words: the one lender and channel beside the others, figures only, Rocket correspondent out; at least two others with a figure, each 5+ bp off; few weeks while any of them is; each side's range across the methods while every group shown has its ends.
rates_rows = [{"scope": "group", "label": "A book", "same_fico_dot": -9.5, "same_fico_rough": False, "same_number_dot": 3.5}, {"scope": "group", "label": "B", "same_fico_dot": -2.5, "same_fico_rough": False, "same_number_dot": 8.5}, {"scope": "group", "label": "C", "same_fico_dot": 0.5, "same_fico_rough": False, "same_number_dot": 5.5}, {"scope": "group", "label": "D", "same_fico_dot": None, "same_fico_rough": True, "same_number_dot": 6.0}, {"scope": "group", "label": "Far", "same_fico_dot": 14.0, "same_fico_rough": True, "same_number_dot": 21.0, "not_like_for_like": True}, {"scope": "card", "label": "A book", "same_fico_dot": -1.0, "same_fico_rough": True, "same_number_dot": 40.0}]
rates_book = {"label": "A book"}
rates_said = pricing._lender_rates(rates_rows, rates_book)
assert rates_said == {"label": "A book", "dot": -9.5, "lo": -2.5, "hi": 0.5, "rough": False, "methods": None} and pricing._lender_rates_line(rates_said) == "On rate, at the same FICO: A book about −9.5 bp, other groups about −2.5 to +0.5.", rates_said
rates_with = lambda i, **change: [{**r, **change} if j == i else r for j, r in enumerate(rates_rows)]  # noqa: E731
assert pricing._lender_rates_line(pricing._lender_rates(rates_with(1, same_fico_rough=True), rates_book)).endswith(", on few weeks of loans.") and pricing._lender_rates_line(pricing._lender_rates(rates_with(0, same_fico_rough=True), rates_book)).endswith(", on few weeks of loans.") and pricing._lender_rates_line(None) is None, "few weeks while any of those is"
# Refinances' shares beside the lender comparison, then what the methods say of its gap by purpose: here its first 220 loans are refinances, the rest purchases, at Fannie alone unless planted.
def mix_stub(refi_gap=-12.0, buy_gap=-3.0, model=None, fannie=None, on=None, rest_refi=60):
    g = np.array([refi_gap] * 220 + [buy_gap] * 180 + [0.0] * 400)
    m = g.copy() if model is None else np.array([model[0]] * 220 + [model[1]] * 180 + [0.0] * 400)
    return _NS(tv=np.ones(800, bool) if on is None else on, lc=np.array([0] * 400 + [1] * 400), refi=np.array([True] * 220 + [False] * 180 + [True] * rest_refi + [False] * (400 - rest_refi)), gap_fico=m, agency=np.array(fannie or ["FNMA"] * 800)), {"same_fico": ({"g": g}, {"g": g.copy()})}


def mix_of(dot=-9.0, book={"lc": 0}, **change):
    stub, cells = mix_stub(**change)
    return pricing._refi_mix(stub, book, cells, dot)


assert mix_of() == (0.55, 0.15, "refi") and mix_of(refi_gap=-3.0, buy_gap=-12.0) == (0.55, 0.15, "purchase") and mix_of(model=(-3.0, -12.0)) == (0.55, 0.15, "split") and mix_of(book=None) is None, "all three methods, or they part"
assert mix_of(dot=6.0, refi_gap=12.0, buy_gap=3.0) == (0.55, 0.15, "refi") and mix_of(dot=6.0, refi_gap=3.0, buy_gap=12.0) == (0.55, 0.15, "purchase"), "wider is further from zero, whichever way the gap runs"
assert mix_of(rest_refi=140)[:2] == (0.55, 0.35) and mix_of(rest_refi=141) is None and mix_of(rest_refi=360)[:2] == (0.55, 0.9), "two shares REFI_APART apart, either way round"
mix_few, mix_cells = mix_stub()
assert pricing._refi_mix(_NS(**{**vars(mix_few), "lc": np.array([0] * 99 + [1] * 701)}), {"lc": 0}, mix_cells, -9.0) is None and pricing._refi_mix(_NS(**{**vars(mix_few), "tv": np.array([True] * 300 + [False] * 100 + [True] * 400)}), {"lc": 0}, mix_cells, -9.0)[0] == 220 / 300, "on 100+ loans each, VS4 loans showing a FICO only"
mix_gse = ["FNMA"] * 110 + ["FHLMC"] * 110 + ["FNMA"] * 90 + ["FHLMC"] * 90 + ["FNMA"] * 400
mix_read, mix_cells = mix_stub(fannie=mix_gse)
mix_read.gap_fico[:110], mix_cells["same_fico"][0]["g"][:110], mix_cells["same_fico"][1]["g"][:110] = -1.0, -1.0, -1.0
assert pricing._refi_mix(mix_read, {"lc": 0}, mix_cells, -9.0)[2] is None or sum(np.array(mix_gse[220:400]) == "FNMA") < 100, "Fannie differs"
mix_book = np.array([-1.0] * 110 + [-20.0] * 110 + [-3.0] * 110 + [-3.0] * 70 + [0.0] * 400)
mix_at = _NS(tv=np.ones(800, bool), lc=np.array([0] * 400 + [1] * 400), refi=np.array([True] * 220 + [False] * 180 + [True] * 60 + [False] * 340), gap_fico=mix_book.copy(), agency=np.array(["FNMA"] * 110 + ["FHLMC"] * 110 + ["FNMA"] * 110 + ["FHLMC"] * 70 + ["FNMA"] * 400))
assert pricing._refi_mix(mix_at, {"lc": 0}, {"same_fico": ({"g": mix_book}, {"g": mix_book.copy()})}, -9.0) == (0.55, 0.15, None), "agreeing whole and not at Fannie alone: no word on it"
mix_cell_few = mix_book.copy()
mix_cell_few[230:] = np.nan
assert pricing._refi_mix(mix_at, {"lc": 0}, {"same_fico": ({"g": mix_cell_few}, {"g": mix_book.copy()})}, -9.0)[2] is None, "a read on under 100 loans"
assert pricing._lender_rates_line(rates_said, (0.6, 0.3, "split")) == "On rate, at the same FICO: A book about −9.5 bp, other groups about −2.5 to +0.5. Refinances are 60% of A book's loans here and 30% of the others', but the methods disagree on whether its gap is wider on refinances." and pricing._lender_rates_line(None, (0.6, 0.3, None)) is None, "the shares and what the methods say"
assert pricing._mix_words("A book", (0.6, 0.3, "refi")).endswith("the others', and on all 3 methods its gap is wider on refinances.") and pricing._mix_words("A book", (0.6, 0.3, "purchase")).endswith("the others', and on all 3 methods its gap is wider on purchases.") and pricing._mix_words("A book", (0.6, 0.3, None)).endswith("the others'.")
assert pricing._lender_rates(rates_rows, None) is None and pricing._lender_rates(rates_rows, {"label": "No such book"}) is None and pricing._lender_rates(rates_with(0, same_fico_dot=None), rates_book) is None and pricing._lender_rates(rates_rows[:2], rates_book) is None and pricing._lender_rates(rates_with(2, same_fico_dot=None), rates_book) is None, "a book with a figure and two others with one"
assert pricing._lender_rates(rates_with(1, same_fico_dot=-4.5), rates_book)["lo"] == -4.5 and pricing._lender_rates(rates_with(1, same_fico_dot=-5.0), rates_book) is None and pricing._lender_rates(rates_with(2, same_fico_dot=-14.0), rates_book) is None and pricing._lender_rates(rates_with(2, same_fico_dot=-4.5), rates_book)["hi"] == -2.5, "5+ bp from every other, either way round"
rates_ends = {"A book": (-12.0, -7.5), "B": (-3.5, -1.0), "C": (-1.0, 2.5)}
rates_with_ends = [{**r, "same_fico_lo": rates_ends[r["label"]][0], "same_fico_hi": rates_ends[r["label"]][1]} if r["label"] in rates_ends else r for r in rates_rows]
assert pricing._lender_rates(rates_with_ends, rates_book)["methods"] == (-12.0, -7.5, -3.5, 2.5) and pricing._lender_rates([{**r, "same_fico_lo": None} if r["label"] == "C" else r for r in rates_with_ends], rates_book)["methods"] is None, "its ends, then the others' lowest and highest; none unless all read"
assert views_d["meta"][0]["lender_rates"] is None and "lender_rates" in meta_a and meta_a["lender_rates"] is None, "one other group with a figure here"
# The number's sentences through the build: between the two groups, 20 points off and what the FICO gap could be instead.
caption_book = between_book(-6.0)
for i, r in enumerate(caption_book):
    if r["score_model"] == "V" and i % 2:
        r["special_program"] = "H"
        r["orig_rate"] = round(r["orig_rate"] - 0.09, 3)
caption_views = rate_views(pricing.build_rates(rate_con(caption_book, "x_caption")))
caption_built = caption_views["meta"][0]["number_caption"]
caption_dot = next(r for r in caption_views["row"] if r["key"] == "same_number")["dot"]
caption_less = next(r for r in caption_views["same_number"] if r["scope"] == "less20")
assert caption_views["meta"][0]["number_blend"].startswith(f"VS4 640-819 is about 100% of the {pricing._signed(caption_dot)}'s loans: about +") and caption_views["meta"][0]["number_why"].startswith("Is the old rule why? Take 20 points off VS4 and ") and caption_built == f"{caption_views['meta'][0]['number_blend']} {caption_views['meta'][0]['number_why']}" and f"Take 20 points off VS4 and {'the ' + pricing._signed(caption_dot) + ' falls to' if abs(caption_less['dot_raw']) < abs(caption_dot) / 3 else 'it is'} about {pricing._span([caption_less['lo_raw'], caption_less['hi_raw']])}" in caption_built and re.search(r"[Ww]here a FICO shows \(about \d+% of these\), it averages about \d+ below VS4, worth about [\d.]+ bp on FICO loans", caption_built), caption_built
s_curve = pricing._sample(rate_con(between_book(-6.0), "x_curve"))
s_curve.fits = pricing._fit_all(s_curve)
assert pricing._curve_gap(s_curve)[0] == 40 and abs(pricing._curve_gap(s_curve)[1] - 12) < 1 and pricing._curve_gap(s_curve)[2] == 1 and pricing._curve_gap(s_curve)[3] is False, pricing._curve_gap(s_curve)
curve_some = between_book(-6.0) + [rate_row(989000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 6.5, "V", None, 720) for k in range(4800)] + [rate_row(994000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 6.5, "V", None, 830) for k in range(500)]
s_curve_some = pricing._sample(rate_con(curve_some, "x_curve_some"))
s_curve_some.fits = pricing._fit_all(s_curve_some)
s_share_high = pricing._sample(rate_con(curve_some + [rate_row(995000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 6.5, "V", None, 830) for k in range(6000)], "x_share_high"))
s_share_high.fits = pricing._fit_all(s_share_high)
assert pricing._same_loans(s_share_high, {"same_number": {"dot": 6.0}})["text"].startswith("VS4 loans under 820 that show a FICO, about one in three: "), pricing._same_loans(s_share_high, {"same_number": {"dot": 6.0}})["text"]
assert pricing._curve_gap(s_curve_some)[2] == 2400 / 7200 and pricing._one_of_these(0.5) == "about one of these loans in two" and pricing._one_of_these(0.71) == "about 71% of these loans" and pricing._one_of_these(0.5, "") == "about one of these in two" and pricing._one_of_these(0.71, "") == "about 71% of these" and pricing._one_bare(0.34) == "about one in three" and pricing._one_bare(0.41) == "about 41%", "the share is of the same-number row's loans, VS4 820+ out"
# Rows: thin under the loan floor though it has the weeks, and a lender cell rough.
one_lender = [r for r in rate_book(gap=4, vs4_a_week=5) if r["seller"] == "rocket-mortgage" and r["channel"] == "R"]
band_one = next(r for r in rate_views(pricing.build_rates(rate_con(one_lender, "x_one")))["same_number"] if r["key"] == "1-19")
assert band_one["n"] < 100 and band_one["lender_weeks"] >= 8 and band_one["thin"] is True, band_one
assert lender_a["rocket_broker"]["same_fico_rough"] is True, "no lender-weeks: rough"
# Beside Milliman: from_oct is Rocket and UWM only; window_plain keeps Rocket correspondent and has no channel in its cells.
mil_a = {r["key"]: r for r in views["milliman"]}
assert mil_a["from_oct"]["pool"] == sum(1 for r in rate_book(gap=4) if r["score_model"] == "V" and r["issue_month"] >= "2026-10-01" and r["seller"] in ("rocket-mortgage", "united-wholesale-mortgage") and (r["seller"], r["channel"]) != ("rocket-mortgage", "C") and r["vs4"] < 820) and mil_a["window_plain"]["pool"] > mil_a["window"]["pool"] and mil_a["window_plain"]["rc_kept"] is True and mil_a["window"]["rc_kept"] is None, mil_a
# llpa_share: issued from Oct 1, Rocket correspondent out: a lower LLPA only elsewhere leaves it at 0.
share_llpa = [r for r in rate_book(gap=0, lower=-8) if not (r["vs4"] and r["classic_fico"] and r["vs4"] == r["classic_fico"] + 20) or r["issue_month"] < "2026-10-01" or (r["seller"], r["channel"]) == ("rocket-mortgage", "C")]
assert pricing._llpa_share(pricing._sample(rate_con(share_llpa, "x_share"))) == "VS4's LLPA is lower on about 0% of all loans showing both scores, whichever score priced them.", pricing._llpa_share(pricing._sample(rate_con(share_llpa, "x_share")))
# Loans showing a FICO close mostly in October and the rest by September: "most of these rates" goes with the loans showing a FICO, not with every VS4 loan.
late_shown = rate_book(gap=0, lower=-8)
for r in late_shown:
    if r["classic_fico"]:
        r["first_pay_date"] = "2026-12-01"
late_shown += [rate_row(1000000 + k, "rocket-mortgage", "R", RATE_WEEKS[k % 10], 6.5, "V", None, 720) for k in range(4000)]
views_late = rate_views(pricing.build_rates(rate_con(late_shown, "x_late_shown")))
late_answer = next(r["text"] for r in views_late["answer"] if r["key"] == "same_llpa")
assert limit_of(views_late, "grid") == grid_head + "." and late_answer.endswith(", which does not show the LLPA caused the gap.") and "most of these rates" not in late_answer and "Most of these rates" not in " ".join(r["text"] for r in views_late["quote"]) and views_late["meta"][0]["rule_at_lock"] is None, (limit_of(views_late, "grid"), late_answer)
# Rocket correspondent's VS4 loans, however many, stay out of the top two's share.
rc_many = rate_book(gap=4) + [rate_row(1010000 + k, "rocket-mortgage", "C", RATE_WEEKS[k % 10], 6.5, "V", 700, 701) for k in range(2200)]
assert rests_of(rate_views(pricing.build_rates(rate_con(rc_many, "x_rc_many")))) == rests_of(views), rests_of(views)
# A book whose gap grows with how far VS4 sits above FICO, through the build: the sentence, the second line, and the figures behind them.
grow_rows = gap_book(gaps=(-2.0, -8.0, -18.0), a_week=12)
for r in grow_rows:
    if r["score_model"] == "V" and r["seller"] == "rocket-mortgage":
        r["orig_rate"] = round(r["orig_rate"] + {10: 0.02, 30: 0.08, 50: 0.18}[r["vs4"] - r["classic_fico"]], 3)
views_grow = rate_views(pricing.build_rates(rate_con(grow_rows, "x_grow")))
grow_answer = next(r["text"] for r in views_grow["answer"] if r["key"] == "same_fico")
assert re.search(r"UWM broker, about half these loans, carries most of it, and there it grows with how far VS4 sits above FICO: about −[\d.]+ at 20 to 39 above and about −[\d.]+ at 40\+\.", grow_answer) and "It runs from" not in grow_answer, grow_answer
assert re.fullmatch(r"(The further VS4 sits above FICO, the lower the rate at the same FICO, at UWM broker and elsewhere\.|At UWM broker, the further VS4 sits above FICO, the lower the rate at the same FICO; (elsewhere that shows only on the model|not elsewhere)\.)( At the same score number it (rises|is highest at 40\+ above)\.)?", views_grow["meta"][0]["gap_line"]), views_grow["meta"][0]["gap_line"]
# At Fannie the same two bands rising: the sentence goes back to the book alone.
grow_flat = gap_book(gaps=(-2.0, -6.0, -24.0), a_week=12, at_fannie=(-2.0, -16.0, -10.0))
for r in grow_flat:
    if r["score_model"] == "V" and r["seller"] == "rocket-mortgage":
        gap_other = dict(zip((10, 30, 50), (-2.0, -16.0, -10.0) if r["agency"] == "FNMA" else (-2.0, -6.0, -24.0)))[r["vs4"] - r["classic_fico"]]
        r["orig_rate"] = round(r["orig_rate"] - gap_other / 100, 3)
grow_flat_answer = rate_views(pricing.build_rates(rate_con(grow_flat, "x_grow_flat")))
assert "and there it grows" not in next(r["text"] for r in grow_flat_answer["answer"] if r["key"] == "same_fico") and "carries most of it." in next(r["text"] for r in grow_flat_answer["answer"] if r["key"] == "same_fico"), grow_flat_answer["answer"]
# By gap on the real function: the LLPA gap on the band's own loans, whole and at Fannie; a band with no Fannie loans says nothing against it; a band under its floor has no dot.
s_bands = pricing._sample(rate_con([r for r in gap_book(a_week=12) if r["agency"] != "FNMA" or r["score_model"] == "C"], "x_bands"))
s_bands.fits = pricing._fit_all(s_bands)
bands_real = pricing._by_gap(s_bands, np.ones(s_bands.n, bool), pricing.GAP_BANDS[1:])
assert all(r["fannie_read5"] == 0 and r["fannie_read_tier"] == 0 and r["fannie_n"] == 0 and r["fannie"] is None for r in bands_real) and pricing._falls_at_fannie(bands_real) and all(r["llpa_gap"] == 0 and r["llpa_gap_old"] == 0 for r in bands_real), bands_real[0]  # a waived program pays no LLPA
few_bands = pricing._by_gap(s_bands, s_bands.first_date == "2026-08-03", pricing.GAP_BANDS[1:])
assert all(r["dot"] is None and r["read5"] < pricing.MIN_ROW for r in few_bands), few_bands
s_paid = pricing._sample(rate_con(rate_book(gap=0, lower=-8), "x_paid"))
s_paid.fits = pricing._fit_all(s_paid)
paid = pricing._by_gap(s_paid, s_paid.seller == "rocket-mortgage", pricing.GAP_BANDS[1:])
paid_t = s_paid.tv & (s_paid.seller == "rocket-mortgage") & (s_paid.vs - s_paid.fico >= 20) & (s_paid.vs - s_paid.fico <= 39)
assert paid[0]["n"] > 0 and paid[0]["llpa_gap"] > 0 and abs(paid[0]["llpa_gap"] - (s_paid.fee_f[paid_t] - s_paid.fee_v[paid_t]).mean()) < 1e-9 and abs(paid[0]["llpa_gap_old"] - (s_paid.fee_f[paid_t] - s_paid.fee_20[paid_t]).mean()) < 1e-9 and paid[0]["fannie_n"] == int((paid_t & (s_paid.agency == "FNMA")).sum()) and abs(paid[0]["fannie_llpa_gap"] - (s_paid.fee_f[paid_t & (s_paid.agency == "FNMA")] - s_paid.fee_v[paid_t & (s_paid.agency == "FNMA")]).mean()) < 1e-9, paid[0]
s_paid.fee_v = np.where(s_paid.agency == "FNMA", s_paid.fee_v - 0.125, s_paid.fee_v)
paid_fannie = pricing._by_gap(s_paid, s_paid.seller == "rocket-mortgage", pricing.GAP_BANDS[1:])[0]
assert paid_fannie["fannie_llpa_gap"] > paid_fannie["llpa_gap"] and abs(paid_fannie["fannie_llpa_gap"] - (s_paid.fee_f[paid_t & (s_paid.agency == "FNMA")] - s_paid.fee_v[paid_t & (s_paid.agency == "FNMA")]).mean()) < 1e-9, paid_fannie
# View behind: every figure that exists only in words has a row with its reads, and where a line did not print its row stays out. The page reads none of them.
behind_at = lambda vs: {r["key"]: r for r in vs["behind"]}  # noqa: E731
grow_behind = behind_at(views_grow)
assert [r["order"] for r in views_grow["behind"]] == list(range(len(views_grow["behind"]))) and all(r["sentence"] and r["what"] for r in views_grow["behind"]), views_grow["behind"]
for key in ("book_20-39", "book_40+", "rest_1-19", "rest_20-39", "rest_40+", "book_closed_2026-07", "book_closed_2026-08", "method_plain", "method_regression"):
    assert key in grow_behind, (key, list(grow_behind))
for key in ("book_20-39", "book_40+", "rest_1-19", "rest_20-39", "rest_40+"):
    r = grow_behind[key]
    assert None not in (r["cell5"], r["tier"], r["model"], r["mid"], r["n"], r["read5"], r["read_tier"]) and abs(r["mid"] - (r["cell5"] + r["tier"]) / 2) <= 0.01 and r["read5"] <= r["n"] and r["value"] is None, r
assert grow_behind["book_40+"]["mid"] < grow_behind["book_20-39"]["mid"] < 0 and grow_behind["book_20-39"]["what"] == "UWM broker, VS4 20 to 39 above FICO" and grow_behind["rest_1-19"]["what"] == "All but UWM broker, VS4 1 to 19 above FICO" and grow_behind["rest_1-19"]["sentence"] == "The further VS4 sits above FICO" and f"about {pricing._signed(pricing.printed(grow_behind['book_40+']['mid'], min(grow_behind['book_40+'][k] for k in ('cell5', 'tier', 'model')), max(grow_behind['book_40+'][k] for k in ('cell5', 'tier', 'model')))[0])} at 40+" in grow_answer, (grow_behind["book_40+"], grow_answer)
assert grow_behind["method_plain"]["value"] is not None and grow_behind["method_regression"]["value"] is not None and grow_behind["method_plain"]["what"] == "Same FICO with only lender, channel, week, GSE and FICO held", grow_behind["method_plain"]
between_behind = behind_at(views_between)
assert {"same_loans_fico", "same_loans_number"} <= set(between_behind) and "same_loans_820" not in between_behind and "book_20-39" not in between_behind and "rest_1-19" not in between_behind, list(between_behind)
assert None not in tuple(between_behind["same_loans_fico"][k] for k in ("cell5", "tier", "model", "mid", "n", "read5", "read_tier", "lo", "hi")) and between_behind["same_loans_fico"]["lo"] <= between_behind["same_loans_fico"]["mid"] <= between_behind["same_loans_fico"]["hi"] and None not in tuple(between_behind["same_loans_number"][k] for k in ("cell5", "tier", "model", "mid", "n")), between_behind["same_loans_fico"]
assert "same_loans_820" not in behind_at(rate_views(pricing.build_rates(rate_con(high_at, "x_high_behind")))) and between_behind["same_loans_fico"]["sentence"] == "VS4 loans under 820 that show a FICO", "no line prints VS4 820+ at its FICO"
priced_behind = behind_at(views_priced)
assert priced_behind["crossing"]["sentence"] == "Points below the VS4 number" and priced_behind["crossing_uwm"]["sentence"] == "Which FICO pays the same" and priced_behind["crossing"]["value"] is not None and priced_behind["crossing"]["lo"] <= priced_behind["crossing"]["value"] <= priced_behind["crossing"]["hi"] and priced_behind["crossing_rocket_retail"]["lo"] is not None and priced_behind["crossing_rocket_retail"]["value"] is None and priced_behind["crossing_uwm"]["hi"] is not None and abs(priced_behind["crossing_per_bp"]["value"] - 3.5) < 0.5, priced_behind["crossing"]
split_views = rate_views(pricing.build_rates(rate_con(split_book(low=-9.5), "split_behind")))
split_behind = behind_at(split_views)
assert "same_llpa_from_780" in split_behind and not {"same_llpa_below_780", "same_llpa_from_640"} & set(split_behind) and split_behind["same_llpa_from_780"]["sentence"] == "What to quote, same LLPA" and split_behind["same_llpa_from_780"]["mid"] is not None and split_behind["expected_credit"]["value"] is not None and split_behind["expected_credit"]["n"] > 0 and next(r for r in split_views["row"] if r["key"] == "same_llpa")["sentence"] != "No visible difference.", list(split_behind)  # the row under 780 is in the lead table now, and FICO 640 to 779 in More cuts
assert behind_at(rate_views(pricing.build_rates(rate_con(split_book(low=-3.0, high=2.5), "split_behind2"))))["same_llpa_from_780"]["sentence"] == "What to quote, same LLPA", "the line that prints it"
assert not {"same_llpa_below_780", "same_llpa_from_780"} & set(behind_at(rate_views(pricing.build_rates(rate_con([r for r in split_book() if r["classic_fico"] != 790 or r["score_model"] == "C"], "split_behind3"))))), "no split printed, no row"
lock_views = rate_views(pricing.build_rates(rate_con(lock_rows, "x_lock_behind")))
lock_behind = behind_at(lock_views)
assert lock_views["meta"][0]["rule_at_lock"] and all(None not in tuple(lock_behind[key][k] for k in ("cell5", "tier", "model", "mid", "n", "read5", "read_tier")) for key in ("lock_lower", "lock_same")) and abs(lock_behind["lock_lower"]["mid"] + 12) < 2 and lock_behind["lock_lower"]["mid"] == round((lock_behind["lock_lower"]["cell5"] + lock_behind["lock_lower"]["tier"]) / 2, 2) and lock_behind["lock_same"]["what"] == "Old rule would have matched it" and lock_behind["lock_same"]["sentence"] == "On the old rule", lock_behind
assert "lock_lower" not in behind_at(views_late), "no old-rule line, no row"
assert "book_rest" in grow_behind and None not in tuple(grow_behind["book_rest"][k] for k in ("cell5", "tier", "model", "mid", "n", "read5", "read_tier")) and grow_behind["book_closed_2026-07"]["what"] == "UWM broker, closed in July", grow_behind["book_rest"]
behind_stub = lambda **change: pricing._behind(_NS(), {"same_llpa": {"sentence": "Too few to compare yet."}}, {}, None, None, [], [], None, None, change.get("match"), change.get("expected"), None, None, change.get("blend"), change.get("curve"))  # noqa: E731
assert behind_stub() == [] and behind_stub(match=(float("nan"), 150, float("nan"), 120)) == [], "no line, no row, and no row with no figure"
behind_book = {"label": "A book", "closed": [], "rest": []}
behind_bands = [{"key": "20-39", "label": "Band two", "dot": -6.5, "cell5": -7.1, "tier": -5.9, "model": -4.2, "mid": -6.5, "n": 300, "read5": 150, "read_tier": 180, "fannie": -5.0, "fannie_read5": 120, "fannie_read_tier": 130}, {"key": "40+", "label": "Band three", "dot": -13.5, "cell5": -14.1, "tier": -12.9, "model": -11.2, "mid": -13.5, "n": 300, "read5": 160, "read_tier": 190, "fannie": -9.0, "fannie_read5": 125, "fannie_read_tier": 135}]
behind_rest = [{**behind_bands[0], "key": "1-19", "label": "Band one", "dot": None, "read5": 20}, {**behind_bands[0], "dot": 2.0}, {**behind_bands[1], "dot": 1.5}]
behind_grown = lambda at_book, rest: [r["key"] for r in pricing._behind(_NS(), {"same_llpa": {"sentence": "Too few to compare yet."}}, {}, None, behind_book, at_book, rest, None, None, None, None, None, None, None, None)]  # noqa: E731
assert behind_grown(behind_bands, behind_rest) == ["book_20-39", "book_40+", "rest_20-39", "rest_40+"] and behind_grown([{**behind_bands[0], "dot": 2.0}, behind_bands[1]], behind_rest) == [], "the bands only under the sentence that prints them, and each at its floor"
split_reads = {**answer_split, "reads": {"high": {"cell5": 3.1, "tier": 3.9, "model": 1.2, "mid": 3.5, "n": 300, "read5": 150, "read_tier": 180}, "under": {"cell5": -7.1, "tier": -5.9, "model": -1.2, "mid": -6.5, "n": 200, "read5": 110, "read_tier": 130}, "low": {"cell5": -5.1, "tier": -3.9, "model": 0.2, "mid": -4.5, "n": 600, "read5": 250, "read_tier": 380}}}
behind_split = lambda row, split: [(r["key"], r["sentence"]) for r in pricing._behind(_NS(), {"same_llpa": row}, {}, split, None, [], [], None, None, None, None, None, None, None, None)]  # noqa: E731
assert behind_split({"sentence": "No visible difference."}, split_reads) == [("same_llpa_from_780", "What to quote, same LLPA"), ("same_llpa_under_640", "Workbook only")] and behind_split({"sentence": "About 8.5 bp lower."}, split_reads) == [("same_llpa_from_780", "What to quote, same LLPA"), ("same_llpa_under_640", "Workbook only")] and behind_split({"sentence": "Too few to compare yet."}, split_reads) == [] and behind_split({"sentence": "No visible difference."}, {**split_reads, "high": None}) == [], "each only where the split prints"
assert [(r["key"], r["value"], r["n"], r["sentence"]) for r in behind_stub(match=(-8.256, 150, -3.0, 120), expected=(-6.5, 90))] == [("match_with", -8.26, 150, "Workbook only"), ("match_without", -3.0, 120, "Workbook only"), ("expected_credit", -6.5, 90, "How much to expect")] and [(r["key"], r["value"], r["sentence"]) for r in behind_stub(blend=(7.5, 1.25), curve=(36.0, 8.5, 0.31, True))] == [("blend_stake", 7.5, "VS4 640-819"), ("blend_rest", 1.25, "VS4 640-819"), ("curve_points", 36.0, "Is the old rule why?"), ("curve_bp", 8.5, "Is the old rule why?")], "what the words print from"
# Rocket correspondent back: the 95% high only, one row a line that prints it; none on a row with no line, or a top end that does not read.
rc_back_rows = {"same_llpa": {"sentence": "Too few to compare yet.", "dot": 2.0, "th": 3.0}, "same_fico": {"dot": -4.5, "th": 1.5}, "lower_llpa": {"dot": None, "th": 1.0}}
rc_back_got = pricing._behind(_NS(), rc_back_rows, {}, None, None, [], [], None, None, None, None, None, None, None, None, {"same_fico": 3.25, "lower_llpa": 1.25, "same_llpa": float("nan")})
assert [(r["key"], r["sentence"], r["what"], r["hi"], r["lo"], r["value"]) for r in rc_back_got] == [("rc_back_same_fico", "What to quote, same FICO", "With Rocket correspondent back, 95% high, same FICO", 3.25, None, None)], rc_back_got
rc_back_real = behind_at(views_b)
assert {"rc_back_same_fico", "rc_back_lower_llpa", "rc_back_same_llpa"} <= set(rc_back_real) and rc_back_real["rc_back_lower_llpa"]["sentence"] == "The thin line" and rc_back_real["rc_back_same_llpa"]["what"] == "With Rocket correspondent back, 95% high, same LLPA", list(rc_back_real)
# The same loans' 95% ends, low then high, as the line printed from them.
behind_loans = pricing._behind(_NS(), {"same_llpa": {"sentence": "Too few to compare yet."}}, {}, None, None, [], [], {"t": np.array([True, True]), "at_fico": ({"est": -6.25, "n": 120}, {"est": -5.25, "n": 140}, -4.5, -8.25, -2.75), "at_number": None}, None, None, None, None, None, None, None)
assert [(r["key"], r["lo"], r["hi"], r["mid"]) for r in behind_loans] == [("same_loans_fico", -8.25, -2.75, -5.75)], behind_loans
# The crossing's value is the point itself, and its 95% ends the draws'.
priced_built = pricing._priced_line(s_priced, {"rocket-mortgage": "Rocket", "united-wholesale-mortgage": "UWM"})
assert priced_behind["crossing"]["value"] == round(priced_built["point"], 2) and priced_behind["crossing"]["lo"] == round(priced_built["whole"][2], 2) and priced_behind["crossing"]["hi"] == round(priced_built["whole"][3], 2) and priced_behind["crossing"]["lo"] < priced_behind["crossing"]["hi"], (priced_behind["crossing"], priced_built["point"])
assert all(set(r) == {"view", "order", "key", "sentence", "what", "cell5", "tier", "model", "mid", "n", "read5", "read_tier", "value", "lo", "hi"} for r in behind_stub(match=(-8.256, 150, -3.0, 120))), "its fields"
# Findings stay out of the source: sentences are templates. No signed figure or 'about' plus a number sits in a string in pricing.py, and no book is named. The rule of thumb's own '1 bp of rate' and what the test should show are rules, not findings.
import ast  # noqa: E402

source = Path(pricing.__file__).read_text()
said_in_source = [n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
for text in said_in_source:
    assert not re.search(r"[+−]\d", text) and not re.search(r"[Aa]bout [−+-]?\d", text.replace("should show about 0", "")) and not re.search(r"\d bp\b", text.replace("to 1 bp of rate", "").replace("A 1 bp change", "")), text
    assert not re.search(r"Rocket retail|Rocket broker|UWM broker|UWM correspondent|[Mm]ost of it (is )?[A-Z]", text), text
    assert not any(gone in text for gone in ("clear discount", "20-point line", "clear step", "closest test", "no sign of", "almost entirely", "through the LLPA", "offset then", "those 20 points", "reads about", "read as", "blending", "cells read", "over about", "By LLPA on today's grid", "track both", "Clearest at", "Which score the rate tracks: on")), text
assert "Lenders pick the score by rule" not in source and not re.search(r"[+−]\d", source), "the selected-group wording stays a possibility in public source, and no signed figure sits in it"
assert not any(word in source for word in ("like FICO loans", "like FICO", "not like loans", "three reads", "the old 20-point rule", "bp of fee", "clear discount", "20-point line", "closest test", "those 20 points", "weeks of files")), "the plain words hold in every template, docstring and comment"
assert not any(word in json.dumps(built) for built in (built_a, built_b) for word in ("over about", "weeks of files", "reads about", "read as", "blending", "cells read", "firmest", "barely", "redrawing", "disclosure week", "By LLPA on today's grid", "track both", "Clearest at")), "nor in what the engine prints"
assert all(any(start in text for text in said_in_source) for start in ("How much to expect", "A test: FICO loans with VS4", "mostly VS4 ", " is about ", "This is how these lenders have priced", "Where VS4 lowers the LLPA", "Three methods: exact match", "Controls, same FICO: ", "Past the switch point: at ", "'s switch point (", "VS4 loans (those priced on VS4", " of its FICO loans carry a rate", "On the old rule, in force", "Narrow base: ", "Who is in these figures: ", "Left out: ", "Which grid: ", "Is the old rule why? ", "Is the gap narrowing? ", "Which score the rate tracks", "Over time: ", "Which loans match: ", "The thin line: ", "Same LLPA: ", "Lenders can pick the score", "Note rate only: ", "These files cannot settle it", "On rate, at the same FICO: ", "Which FICO pays the same", "A range in bp with no label", "The newest file is provisional")), "the lint reads the new sentences"
# HMDA on planted files: a named model counts wherever the lender put it, each loan lands in one segment, a model's users are counted under it, and the raw files go only once the count ties to the lenders' filings.
from gsescore import hmda  # noqa: E402
from gsescore import paths as gse_paths  # noqa: E402

hmda.LENDER_MIN = 1
H_HEAD = ["activity_year", *hmda.KEEP_TEXT, *hmda.KEEP_INT, "income"]


def lar(lei, a=3, c=10, action=1, purchaser=0, loan_type=1, lien=1, open_end=2, reverse=2, biz=2, limit="C", dwelling="Single Family (1-4 Units):Site-Built"):
    v = {"activity_year": 2025, "lei": lei, "conforming_loan_limit": limit, "derived_dwelling_category": dwelling, "action_taken": action, "purchaser_type": purchaser, "loan_type": loan_type, "loan_purpose": 1, "lien_status": lien,
         "reverse_mortgage": reverse, "open_end_line_of_credit": open_end, "business_or_commercial_purpose": biz, "loan_amount": 300000, "occupancy_type": 1, "applicant_credit_score_type": a, "co_applicant_credit_score_type": c,
         "submission_of_application": 1, "initially_payable_to_institution": 1, "aus_1": 6, "income": "NA"}
    return lei, ",".join(str(v[h]) for h in H_HEAD)


planted = [lar("A", a=1, purchaser=1) for _ in range(10)] + [
    lar("C", biz=1, purchaser=3),  # sold to a GSE, whatever its purpose
    lar("A", a=9, c=2, loan_type=2), lar("A", a=9, c=9, loan_type=2),  # FHA: named in the co-applicant's field; nothing named
    lar("B", a=6, loan_type=3),  # VA, older VantageScore
    lar("B", a=15, c=9, lien=2), lar("B", a=9, c=15, lien=2), lar("B", a=1, c=15, lien=2), lar("B", a=11, open_end=1), lar("B", lien=2),  # home equity: VS4 in either field and over FICO; a first-lien line of credit
    lar("C", a=7, limit="NC"), lar("C", a=8, purchaser=5), lar("C", a=1111, c=1111, purchaser=71), lar("C", a=12), lar("C", biz=1),  # jumbo, private, another buyer, not sold, business
    lar("C", reverse=1), lar("C", dwelling="Multifamily:Site-Built"),  # left out
    lar("A", a=2, action=3, loan_type=2), lar("A", a=9, c=9, action=4, loan_type=2),  # FHA applications that never funded
    lar("A", a=9, c=9, action=6),  # bought, not made
]
h_raw = home / "data" / "hmda" / "raw" / "2025"
h_raw.mkdir(parents=True)


def write_h_zips(extra=0):
    with zipfile.ZipFile(h_raw / "2025_public_lar_csv.zip", "w") as z:
        z.writestr("2025_public_lar_csv.csv", "\n".join([",".join(H_HEAD)] + [r for _, r in planted]) + "\n")
        z.writestr("__MACOSX/._2025_public_lar_csv.csv", "not a table")
    counts = {k: sum(1 for lei, _ in planted if lei == k) for k in "ABC"}
    names = {"A": "BIG MORTGAGE, LLC", "B": "Second Bank", "C": "THIRD CREDIT UNION (68671)"}
    with zipfile.ZipFile(h_raw / "2025_public_ts_csv.zip", "w") as z:
        z.writestr("2025_public_ts_csv.csv", "lei,respondent_name,lar_count\n" + "".join(f'{k},"{names[k]}",{counts[k] + (extra if k == "C" else 0)}\n' for k in "ABC"))


write_h_zips(extra=1)
try:
    hmda.ingest(2025)
    raise AssertionError("a count that does not tie should stop the load")
except ValueError:
    assert (h_raw / "2025_public_lar_csv.zip").exists() and (h_raw / "2025_public_ts_csv.zip").exists()
assert hmda.build_datasets() == {"whole_market": []} and not (h_raw / "2025_public_lar.csv").exists()  # nothing loaded, and the unpacked file is gone
write_h_zips()
h_in = hmda.ingest(2025)
assert h_in["records"] == len(planted) and h_in["kept"] == len(planted) - 1 and not (home / "data" / "hmda" / "raw").exists(), h_in
# An earlier year, spelled the way those files spell their columns, adds to the year-by-year views and leaves the latest year's as they are.
h_raw_2024 = home / "data" / "hmda" / "raw" / "2024"
h_raw_2024.mkdir(parents=True)
hmda.LENDER_YEAR_MIN = 1
old_head = [{"co_applicant_credit_score_type": "co-applicant_credit_score_type", "open_end_line_of_credit": "open-end_line_of_credit", "aus_1": "aus-1"}.get(h, h) for h in H_HEAD]
with zipfile.ZipFile(h_raw_2024 / "2024_public_lar_csv.zip", "w") as z:
    z.writestr("2024_public_lar_csv.csv", "\n".join([",".join(old_head), lar("A", a=3)[1], lar("B", a=8, lien=2)[1]]) + "\n")
with zipfile.ZipFile(h_raw_2024 / "2024_public_ts_csv.zip", "w") as z:
    z.writestr("2024_public_ts_csv.csv", "lei,respondent_name,lar_count\nA,BIG MORTGAGE,1\nB,Second Bank,1\n")
assert hmda.ingest(2024)["kept"] == 2
wm = hmda.build_datasets()["whole_market"]
wm_trend = {(r["year"], r["key"]): r for r in wm if r["view"] == "trend"}
assert wm_trend[(2024, "all")]["n"] == 2 and wm_trend[(2024, "first")]["n"] == 1 and wm_trend[(2024, "first")]["classic"] == 1 and wm_trend[(2024, "equity")]["other"] == 1 and wm_trend[(2025, "all")]["n"] == 24, wm_trend[(2024, "all")]
assert wm_trend[(2025, "first")]["n"] == 19 and wm_trend[(2025, "equity")]["vs4"] == 0.6 and wm_trend[(2025, "all")]["order"] == 0 and wm_trend[(2024, "equity")]["fico"] == 0 and wm_trend[(2024, "equity")]["unnamed"] == 1
big_years = {r["year"]: r for r in wm if r["view"] == "lender_year" and r["scope"] == "all" and r["name"] == "Big Mortgage"}
assert big_years[2024]["n"] == 1 and big_years[2024]["classic"] == 1 and big_years[2025]["n"] == 12, big_years
assert {r["year"]: r["n"] for r in wm if r["view"] == "model_year" and r["code"] == 3} == {2024: 1, 2025: 3} and next(r for r in wm if r["view"] == "meta")["first_year"] == 2024
seg = {r["key"]: r for r in wm if r["view"] == "segment"}
assert seg["gse"]["n"] == 11 and seg["gse"]["classic"] == 1
assert seg["fha"]["n"] == 2 and seg["fha"]["classic"] == 0.5 and seg["fha"]["none"] == 0.5 and seg["fha"]["unknown"] == 0.5
assert seg["va"]["vs_old"] == 1 and seg["va"]["vs"] == 1
assert seg["equity"]["n"] == 5 and seg["equity"]["vs4"] == 0.6 and seg["equity"]["fico_new"] == 0.2 and seg["equity"]["classic"] == 0.2 and seg["equity"]["fico"] == 0.4 and seg["equity"]["vs"] == 0.6
assert seg["jumbo"]["multi"] == 1 and seg["jumbo"]["unnamed"] == 1 and seg["private"]["other"] == 1 and seg["other_buyer"]["none"] == 1 and seg["not_sold"]["fico_new"] == 1 and seg["business"]["classic"] == 1
assert seg["all"]["n"] == 24 and seg["first"]["n"] == 19, (seg["all"]["n"], seg["first"]["n"])
assert abs(sum(seg["all"][k] for k in hmda.SHARES) - 1) < 1e-5
assert seg["gse"]["first_lien"] and not seg["equity"]["first_lien"]
h_meta = next(r for r in wm if r["view"] == "meta")
assert h_meta["year"] == 2025 and h_meta["records"] == len(planted) and h_meta["n"] == 26 and h_meta["lenders"] == 3, h_meta
model = {r["code"]: r for r in wm if r["view"] == "model"}
assert model[15]["n"] == 3 and model[15]["equity_share"] == 1 and model[15]["users"] == "Second Bank (3)" and model[1]["n"] == 11 and model[14]["n"] == 0, model[15]
apps = {r["key"]: r for r in wm if r["view"] == "apps"}
assert apps["fha"]["n"] == 2 and apps["fha"]["apps"] == 4 and apps["fha"]["per_loan"] == 2, apps["fha"]
vs_first = [r for r in wm if r["view"] == "lender" and r["scope"] == "vs"][0]
assert vs_first["name"] == "Second Bank" and vs_first["n"] == 6 and vs_first["equity_share"] == round(5 / 6, 6), vs_first
biggest = [r for r in wm if r["view"] == "lender" and r["scope"] == "all"]
assert biggest[0]["name"] == "Big Mortgage" and biggest[0]["n"] == 12 and {r["name"] for r in biggest} == {"Big Mortgage", "Second Bank", "Third Credit Union"}, biggest[0]
assert hmda.short_name("CROSSCOUNTRY MORTGAGE, LLC") == "CrossCountry Mortgage" and hmda.short_name("US BANK, N.A.") == "US Bank" and hmda.short_name("DHI Mortgage Company, LTD.") == "DHI Mortgage" and hmda.short_name("loanDepot.com LLC") == "loanDepot.com"
(gse_paths.SITE_DATA / "whole_market.json").write_text(json.dumps({"rows": wm}))
with zipfile.ZipFile(build_workbook()) as z:
    book_xml = z.read("xl/workbook.xml").decode()
assert all(f'name="{n}"' in book_xml for n in ("Whole market", "Whole market by year", "Lenders by year", "Whole market lenders", "Score models")), book_xml[:400]

# Private-label reports on planted tables: a model counts wherever it sits, a spanning cell keeps columns in line, a table without a heading continues the last one, one loan in two reports counts once, and a label that only says FICO proves nothing.
from gsescore import edgar  # noqa: E402

assert edgar.model_family("VantageScore 4.0") == "vs4" and edgar.model_family("VantageScore 3.0") == "vs_old" and edgar.model_family("FICO Risk Score Classic 04") == "classic" and edgar.model_family("Beacon 5.0") == "classic"
assert edgar.model_family("FICO Classic (09)") == "fico_new" and edgar.model_family("Fair Issac 4") == "classic" and edgar.model_family("FICO v2") == "classic" and edgar.model_family("Next Generation") == "fico_new"
assert edgar.model_family("Classic 08") == "fico_new" and edgar.model_family("FICO Score 10T") == "fico_new" and edgar.model_family("3") == "code" and edgar.model_family("Other") == "other" and edgar.model_family("C3") == "junk" and edgar.model_family("75.000%") == "junk" and edgar.model_family("Classic") == "classic"
assert edgar.loan_family(["Beacon 5.0", "VantageScore 4.0"]) == "vs4" and edgar.loan_family(["3"]) == "unclear" and edgar.loan_family(["FICO 9", "Beacon 5.0"]) == "fico_new" and edgar.loan_family(["C3", "75.000%"]) == "blank" and edgar.loan_family([]) == "blank"
assert edgar.report_month("6/15/2026") == "2026-06" and edgar.report_month("20260615") == "2026-06" and edgar.report_month("XX/XX/2026") is None and edgar.report_month("[redacted]") is None
assert edgar.deal_name("CROSS 2026-NQM13 Mortgage Trust (Exact name of Issuer as specified)", "cross.htm") == "CROSS 2026-NQM13" and edgar.deal_name("nothing", "abs15g_semt2026cd7.htm") == "SEMT 2026-CD7" and edgar.deal_name("nothing", "abs15g.htm") is None
assert edgar.deal_kind("CROSS 2026-NQM13") == "nonqm" and edgar.deal_kind("TPMT 2026-CES4") == "second" and edgar.deal_kind("Sequoia Mortgage Trust 2026-CD8") == "prime" and edgar.deal_kind("GS Mortgage-Backed Securities Trust 2026-DSC1") == "investor" and edgar.deal_kind("EFMT 2026-RM3") == "other" and edgar.deal_kind(None) == "other"
assert [len(t) for t in edgar.read_tables("<table><tr><td>Title</td></tr><table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>")] == [2, 1]  # a table left open
assert edgar.parse_exhibit("<table><tr><th>EDGAR ID</th><th>FICO Model Used</th><th>Rate</th></tr><tr><td>PRET 2026-RPL3-100661</td><td>1</td><td>7.1</td></tr></table>")[0][0]["id"] == "PRET 2026-RPL3-100661"
assert edgar.mentions_vantage("<td>Most Recent Vantagescore Method</td><td>Vantagescore Primary Borrower</td><td>Vantage Score: Co-borrower</td><td>Vantage Score Date</td>") == 0 and edgar.mentions_vantage("<p>credit report data from Experian and/or Vantage used at origination</p>") == 1
assert edgar.mentions_vantage("<p>Vantage Data Centers leased the site</p>") == 0 and edgar.mentions_vantage("<p>the alternate VantageScore model</p>") == 1
report = """<table><tr><th>Customer Loan ID</th><th>Original Credit Report Date</th><th>Qualifying Credit Score</th><th>Borrower Experian FICO Model Used</th><th>Borrower Equifax FICO Model Used</th></tr>
<tr><td>1000001</td><td>6/15/2026</td><td>740</td><td>Fair Isaac (VER. 2)</td><td>Beacon 5.0</td></tr>
<tr><td>1000002</td><td>[redacted]</td><td>700</td><td colspan="2">VantageScore 4.0</td></tr>
<tr><td>1000003</td><td>7/2/2026</td><td>[redacted]</td><td>[redacted]</td><td></td></tr></table>
<p>page 2</p><table><tr><td>1000004</td><td>7/9/2026</td><td>680</td><td>FICO II</td><td>3</td></tr></table>
<table><tr><td>Not a loan table</td></tr></table>"""
rows, note = edgar.parse_exhibit(report)
assert note["model_tables"] == 2 and note["rows"] == 4, note
by_id = {r["id"]: r for r in rows}
assert by_id["1000001"]["models"] == ["Beacon 5.0", "Fair Isaac (VER. 2)"] and by_id["1000001"]["pull"] == "2026-06" and by_id["1000001"]["score"] == 740
assert by_id["1000002"]["models"] == ["VantageScore 4.0"] and by_id["1000002"]["pull"] is None
assert by_id["1000003"]["models"] == [] and by_id["1000003"]["score"] is None and by_id["1000004"]["models"] == ["3", "FICO II"]
no_model, note2 = edgar.parse_exhibit("<table><tr><th>Loan ID</th><th>Final Qualifying FICO</th><th>Rate</th></tr><tr><td>123456</td><td>753</td><td>9.1</td></tr></table>")
assert no_model == [] and note2["model_tables"] == 0  # a score called FICO, with no model: not a fact about the model
asf, _ = edgar.parse_exhibit("<table><tr><th>Loan Number</th><th>Vantage Score: Primary Borrower</th><th>Most Recent Vantage Score Method</th><th>Rate</th><th>Term</th></tr><tr><td>777777</td><td>712</td><td></td><td>7.1</td><td>360</td></tr><tr><td>888888</td><td></td><td></td><td>7.2</td><td>360</td></tr></table>")
assert asf[0]["vs_value"] and not asf[1]["vs_value"]
# The same report as a fixed-width text block, in two sections of the same loans, and with its headings broken across lines.
pre_report = """<html><body><table><tr><td>Supplemental Data</td></tr></table><font><pre>


SITUSAMC LOAN ID CUSTOMER LOAN ID SELLER LOAN ID ORIGINAL CREDIT REPORT DATE QUALIFYING CREDIT SCORE TILA STATUS
(redacted)                     13 (redacted)                       6/15/2026                     740 Safe Harbor QM
(redacted)                    684 (redacted)                      XX/XX/2026                     701 Non QM

SITUSAMC LOAN ID CUSTOMER LOAN ID SELLER LOAN ID DOCUMENT LEVEL BORROWER EXPERIAN FICO MODEL USED BORROWER EQUIFAX FICO MODEL USED BORROWER TRANSUNION FICO MODEL USED CHANNEL
(redacted)                     13 (redacted)     Full Doc       Fair Isaac (VER. 2)              Beacon 5.0                       FICO Risk Score Classic 04          Retail
(redacted)                    684 (redacted)     Full Doc       VantageScore 4.0                                                                                      Broker
</pre></font></body></html>"""
pre_rows, pre_note = edgar.parse_exhibit(pre_report)
assert pre_note.get("pre") and pre_note["rows"] == 2, pre_note
pre_by = {r["id"]: r for r in pre_rows}
assert pre_by["13"]["models"] == ["Beacon 5.0", "FICO Risk Score Classic 04", "Fair Isaac (VER. 2)"] and pre_by["13"]["pull"] == "2026-06" and pre_by["13"]["score"] == 740, pre_by
assert pre_by["684"]["models"] == ["VantageScore 4.0"] and pre_by["684"]["pull"] is None and pre_by["684"]["score"] == 701, pre_by
masked, _ = edgar.parse_exhibit("""<pre>
SITUSAMC LOAN ID CUSTOMER LOAN ID SELLER LOAN ID BORROWER EXPERIAN FICO MODEL USED NEXT
[Redacted]             [Redacted] (redacted)     FICO II                           X
[Redacted]             [Redacted] (redacted)     Beacon 5.0                        X
</pre>""")
assert [r["id"] for r in masked] == ["line1", "line2"] and masked[0]["models"] == ["FICO II"], masked  # masked numbers do not collapse loans into one
assert edgar.parse_exhibit("""<pre>
SITUSAMC LOAN ID CUSTOMER LOAN ID SELLER LOAN ID FICO MODEL USED NEXT
(redacted)                     13 (redacted)     1               X
</pre>""")[0] == []  # only codes: nothing to add
broken, broken_note = edgar.parse_exhibit("<TABLE><TR><TD>SitusAMC Loan ID</TD><TD>Borrower&nbsp;1<BR>TransUnion<BR>FICO<BR>Model Used</TD><TD>Rate</TD></TR><TR><TD>224733811</TD><TD>Beacon 5.0</TD><TD>7.1</TD></TR></TABLE>")
assert broken_note["model_tables"] == 1 and broken[0]["models"] == ["Beacon 5.0"], broken_note
os.environ.pop("EDGAR_CONTACT", None)
try:
    edgar.contact()
    raise AssertionError("no requests without a contact")
except SystemExit:
    pass
os.environ["EDGAR_CONTACT"] = "tester@example.com"
assert "tester@example.com" in edgar.Edgar().ua
del os.environ["EDGAR_CONTACT"]
assert [w for w in edgar.month_windows("2026-01-15", "2026-03-02")] == [("2026-01-15", "2026-01-31"), ("2026-02-01", "2026-02-28"), ("2026-03-01", "2026-03-02")]
assert edgar.build_datasets() == {"private_label": []}
assert edgar._loan_key("A", "6000080192") == edgar._loan_key("B", "6000080192") and edgar._loan_key("A", "358") != edgar._loan_key("B", "358")
e_home = home / "data" / "edgar"
e_home.mkdir(parents=True, exist_ok=True)


def e_hit(adsh, name, kind, day, filer="Deal Depositor LLC", typ="EX-99.1"):
    return {"adsh": adsh, "file": name, "cik": "0000123456", "date": day, "form": "ABS-15G", "type": typ, "desc": "", "filer": filer, "kind": kind}


edgar._append_jsonl(e_home / "hits.jsonl", [e_hit("A", "s5.htm", "model", "2026-09-10"), e_hit("A", "s6.htm", "model", "2026-09-10"), e_hit("B", "s5.htm", "model", "2026-09-20"), e_hit("C", "x.htm", "score", "2026-09-21", "Other Bank"),
                                            e_hit("D", "n.htm", "mention", "2026-07-01", "Home Equity Inc."), e_hit("E", "x.htm", "model", "2026-09-01", "Motor Auto Receivables LLC"), e_hit("F", "n.htm", "mention", "2026-07-01", "Deal Depositor LLC")])
edgar._append_jsonl(e_home / "filings.jsonl", [{"adsh": "A", "deal": "CROSS 2026-NQM1"}, {"adsh": "B", "deal": "CROSS 2026-NQM1"}, {"adsh": "D", "deal": "HOME 2026-HE1"}])
edgar._append_jsonl(e_home / "exhibits.jsonl", [{"adsh": "A", "file": "s5.htm"}, {"adsh": "A", "file": "s6.htm"}, {"adsh": "B", "file": "s5.htm"}])
edgar._append_jsonl(e_home / "mentions.jsonl", [{"adsh": "D", "file": "n.htm", "date": "2026-07-01", "count": 2}, {"adsh": "F", "file": "n.htm", "date": "2026-07-01", "count": 0}])
loan = lambda adsh, i, models, pull=None, name="s5.htm": {"adsh": adsh, "file": name, "id": i, "models": models, "vs_value": False, "pull": pull, "score": 700}  # noqa: E731
edgar._append_jsonl(e_home / "loans.jsonl", [loan("A", "1", ["Beacon 5.0"], "2026-05"), loan("A", "1", ["FICO II"], name="s6.htm"), loan("A", "2", ["VantageScore 4.0"], "2026-06"), loan("A", "3", []), loan("B", "2", ["Beacon 5.0"]), loan("B", "4", ["FICO 9"], "2026-06"), loan("B", "5", ["3"]),
                                             loan("E", "9", ["VantageScore 4.0"])])
pl = edgar.build_datasets()["private_label"]
p_meta = next(r for r in pl if r["view"] == "meta")
assert p_meta["n"] == 5 and p_meta["named"] == 4 and p_meta["classic_n"] == 1 and p_meta["vs4_n"] == 1 and p_meta["fico_new_n"] == 1 and p_meta["unclear_n"] == 1 and p_meta["blank_n"] == 1, p_meta  # the auto deal is out; loan 2's two reports count once, as VS4
assert p_meta["filings"] == 3 and p_meta["with_model"] == 2 and p_meta["dated"] == 0.6 and p_meta["deals"] == 1 and p_meta["lag_months"] == 3 and p_meta["vs_no_fico_n"] == 0, p_meta
q3 = next(r for r in pl if r["view"] == "period" and r["basis"] == "filed")
assert q3["period"] == "2026-Q3" and q3["label"] == "Q3 2026" and q3["filings"] == 3 and q3["with_model"] == 2 and q3["vs"] == 0.2 and q3["fico"] == 0.4 and q3["none"] == 0.2
assert not [r for r in pl if r["view"] == "period" and r["basis"] == "pulled"]  # too few loans in any month
assert [r["key"] for r in pl if r["view"] == "kind"] == ["nonqm"]
p_filers = {r["key"]: r for r in pl if r["view"] == "filer"}
assert p_filers["Deal Depositor LLC"]["filings"] == 2 and p_filers["Deal Depositor LLC"]["with_model"] == 2 and p_filers["Other Bank"]["filings"] == 1 and p_filers["Other Bank"]["with_model"] == 0 and p_filers["Other Bank"]["n"] == 0
p_deal = next(r for r in pl if r["view"] == "deal")
assert p_deal["key"] == "CROSS 2026-NQM1" and p_deal["vs4_n"] == 1 and p_deal["filed"] == "2026-09-10" and p_deal["url"].endswith("/123456/A/A-index.html"), p_deal
p_mention = [r for r in pl if r["view"] == "mention"]
assert len(p_mention) == 1 and p_mention[0]["key"] == "HOME 2026-HE1" and p_mention[0]["kind"] == "second" and p_mention[0]["count"] == 2, p_mention
(gse_paths.SITE_DATA / "private_label.json").write_text(json.dumps({"rows": pl}))
with zipfile.ZipFile(build_workbook()) as z:
    book_xml = z.read("xl/workbook.xml").decode()
assert 'name="Private-label deals"' in book_xml and 'name="Private-label VantageScore"' in book_xml

# Ginnie Mae's loan files: both layouts read alike, only new purchases and full refinances count, a lender's step shows by closing month, and FHA is the check
import duckdb  # noqa: E402

from gsescore import ginnie  # noqa: E402

ginnie.MONTH_MIN = ginnie.START_MIN = 1


def fixed_loan(issuer, agency, purpose, refi, score, channel, orig):
    ln = [" "] * 193
    for start, text in ((1, "L"), (18, issuer), (22, agency), (23, purpose), (24, refi), (109, score), (134, channel), (143, orig)):
        ln[start - 1:start - 1 + len(text)] = text
    return "".join(ln)


def pipe_loan(issuer, agency, purpose, refi, score, channel, orig):
    f = [""] * 55
    f[0], f[7], f[8], f[9], f[10], f[26], f[36], f[40] = "LL", issuer, agency, purpose, refi, score, channel, orig
    return "|".join(f)


g_in = home / "ginnie_in"
g_in.mkdir()
old_file = g_in / "dailyllmni_202605.zip"
with zipfile.ZipFile(old_file, "w") as z:
    z.writestr("dailyllmni.txt", "\n".join(["HGNMA_MBS_LL_MON_202605001N20260520260601", "P3617GU3X0BG9814CET202605014262202605",
                                            fixed_loan("4042", "V", "1", " ", "790", "3", "20260410"), fixed_loan("4042", "F", "1", " ", "690", "3", "20260410"),
                                            fixed_loan("3725", "V", "2", "2", "790", "1", "20260412"), fixed_loan("9001", "V", "1", " ", "832", "3", "20260415"),
                                            fixed_loan("9001", "V", "2", "3", "840", "3", "20260415"),  # a streamline
                                            fixed_loan("9001", "V", "4", " ", "840", "3", "20260415"),  # a modification
                                            fixed_loan("9001", "R", "1", " ", "840", "3", "20260415"),  # USDA
                                            fixed_loan("9001", "V", "1", " ", "840", "3", "20200415"),  # re-pooled
                                            fixed_loan("9001", "V", "1", " ", "   ", "3", "20260415")]))
new_file = g_in / "dailyllmnipd.zip"
with zipfile.ZipFile(new_file, "w") as z:
    z.writestr("dailyllmnipd_202607.txt", "\n".join(["HH|202607|NM|20260801", pipe_loan("4042", "V", "1", "", "835", "3", "20260610"), pipe_loan("4042", "V", "1", "", "848", "3", "20260610"),
                                                     pipe_loan("4042", "V", "2", "2", "790", "2", "20260610"), pipe_loan("4042", "F", "1", "", "700", "3", "20260610"),
                                                     pipe_loan("3725", "V", "1", "", "831", "1", "20260612"), pipe_loan("3725", "V", "1", "", "700", "1", "20260612"), pipe_loan("9001", "V", "1", "", "790", "3", "20260612"),
                                                     "TT|202607|7"]))
issuers = g_in / "issrinfo_202609.txt"
issuers.write_text("".join(f"{i}01{n:<100}{'x' * 60}\n" for i, n in (("4042", "ROCKET MORTGAGE, LLC"), ("3725", "UNITED WHOLESALE MORTGAGE, LLC"), ("9001", "OTHER BANK, N.A."))))
assert ginnie.read_loans(old_file)[0] == "2026-05" and ginnie.read_loans(new_file)[0] == "2026-07"
g_old = ginnie.read_loans(old_file)[1]
assert g_old.n.sum() == 5 and g_old.score5.isna().sum() == 1 and set(g_old.agency) == {"V", "F"}, g_old  # the streamline, modification, USDA and re-pooled loans are left out; a blank score stays, unscored
g_con = duckdb.connect()
g_con.execute("CREATE TABLE loans AS SELECT * FROM (VALUES ('FNMA', 790, 835), ('FNMA', 790, 800), ('FNMA', 700, 730), ('FHLMC', 790, 846)) t(agency, classic_fico, vs4)")
assert ginnie.build_datasets(g_con) == {"ginnie_va": []}  # nothing read yet
ginnie.ingest([issuers, old_file, new_file])
gv = ginnie.build_datasets(g_con)["ginnie_va"]
g_meta = next(r for r in gv if r["view"] == "meta")
assert g_meta["lead"] == "Rocket Mortgage" and g_meta["second"] == "United Wholesale Mortgage" and g_meta["since"] == "2026-06" and g_meta["first"] == "2026-04", g_meta
assert g_meta["ref_n"] == 4 and g_meta["ref_vs4"] == 0.5 and g_meta["ref_classic"] == 0 and g_meta["fha_k"] == 0 and g_meta["fha_n"] == 2 and g_meta["high_elsewhere"] == 0, g_meta
g_month = {(r["key"], r["month"]): r for r in gv if r["view"] == "month"}
assert g_month[("lead_own", "2026-04")]["k"] == 0 and g_month[("lead_retail", "2026-06")]["k"] == 2 and g_month[("lead_retail", "2026-06")]["n"] == 2 and g_month[("lead_own", "2026-06")]["n"] == 2, g_month
assert g_month[("second", "2026-06")]["share"] == 0.5 and g_month[("others", "2026-04")]["k"] == 1 and g_month[("fha", "2026-06")]["k"] == 0, g_month
g_lender = {r["name"]: r for r in gv if r["view"] == "lender"}
assert g_lender["Rocket Mortgage"]["k"] == 2 and g_lender["Rocket Mortgage"]["k_high"] == 1 and set(g_lender) == {"Rocket Mortgage", "United Wholesale Mortgage", "Other Bank"}, g_lender
assert g_lender["Other Bank"]["k"] == 0 and g_lender["Other Bank"]["too_few"], g_lender  # a full signal under SMALL_FULL can't be read
g_range = {r["key"]: r for r in gv if r["view"] == "range"}
assert {"lead_retail", "lead_own", "second", "all"} == set(g_range) and g_range["lead_own"]["low"] < g_range["lead_own"]["high"] == g_range["lead_own"]["signal"], g_range
(gse_paths.SITE_DATA / "ginnie_va.json").write_text(json.dumps({"rows": gv}))
with zipfile.ZipFile(build_workbook()) as z:
    assert 'name="VA loans at 830+"' in z.read("xl/workbook.xml").decode()


# The Rates sheet, on the engine's own rows from planted data, and the rate read on Lenders and Fees. Every value reads back with its decimals under its own heading, and a blank read stays blank.
def sheet_cells(book, name):
    """A sheet's cells by (row, column), strings read through, from the file's own XML."""
    with zipfile.ZipFile(book) as z:
        said = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        at = [e.get("name") for e in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", ns)].index(name)
        cells = {}
        for c in ET.fromstring(z.read(f"xl/worksheets/sheet{at + 1}.xml")).iter(f"{{{ns['m']}}}c"):
            v = c.find("m:v", ns)
            if v is not None:
                letters, row = re.fullmatch(r"([A-Z]+)(\d+)", c.get("r")).groups()
                col = sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(letters))) - 1
                cells[(int(row) - 1, col)] = said[int(v.text)] if c.get("t") == "s" else float(v.text)
    return cells


def table_under(cells, title):
    """The table under a heading, a dict a row: its header is the first row of two or more cells below, and it runs to the next row with fewer."""
    filled = lambda at: sum(1 for r, _ in cells if r == at)  # noqa: E731
    start = next(r for (r, c), v in cells.items() if c == 0 and v == title) + 1
    head = next(r for r in range(start, start + 3) if filled(r) >= 2)
    heads = {c: v for (r, c), v in cells.items() if r == head}
    out = []
    while filled(head + 1 + len(out)) >= 2:
        out.append({h: cells.get((head + 1 + len(out), c)) for c, h in heads.items()})
    return out


def cell_format(book, name, row, col):
    """A cell's number format, from the file's own XML."""
    with zipfile.ZipFile(book) as z:
        styles = ET.fromstring(z.read("xl/styles.xml"))
        at = [e.get("name") for e in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", ns)].index(name)
        ref = f"{chr(65 + col)}{row + 1}"
        cell = next(c for c in ET.fromstring(z.read(f"xl/worksheets/sheet{at + 1}.xml")).iter(f"{{{ns['m']}}}c") if c.get("r") == ref)
    format_id = styles.find("m:cellXfs", ns)[int(cell.get("s"))].get("numFmtId")
    return {"1": "0", "4": "#,##0.00"}.get(format_id) or next(f.get("formatCode") for f in styles.find("m:numFmts", ns) if f.get("numFmtId") == format_id)  # Excel's own formats have no entry


def reads_back(cells, title, want, fields):
    got = table_under(cells, title)
    assert len(got) == len(want) > 0, (title, len(got), len(want))
    for g, w in zip(got, want):
        for head, key in fields.items():
            assert g[head] == w[key], (title, head, g, w)
    return got


stage_kept, rates_kept, fees_kept = (gse_paths.SITE_DATA / "lender_stage.json").read_text(), (gse_paths.SITE_DATA / "rates.json").read_text(), (gse_paths.SITE_DATA / "fees.json").read_text()
stage_rows = json.loads(stage_kept)["rows"]
stage_one = next(r for r in stage_rows if r.get("view") == "lender")
(gse_paths.SITE_DATA / "lender_stage.json").write_text(json.dumps({"rows": [*stage_rows, {**stage_one, "id": "rocket-mortgage", "short": "Rocket", "rank": 90}, {**stage_one, "id": "no-read-bank", "short": "No Read Bank", "rank": 91}]}))
fee_lender = {"view": "lender", "month": "2026-10-01", "ticker": "PLAN", "loans": 900, "upb": 3.1e8, "saving_share": 0.62, "saved_bp": 21.5, "saving_avg_usd": 1400.0}
(gse_paths.SITE_DATA / "fees.json").write_text(json.dumps({"rows": [*json.loads(fees_kept)["rows"], {**fee_lender, "id": "planted-low", "short": "Planted Low", "rank": 81, "priced_loans": 40, "taken_usd": 2.5e5, "taken_all_usd": 3.5e5},
                                                                    {**fee_lender, "id": "planted-high", "short": "Planted High", "rank": 82, "priced_loans": 70, "taken_usd": 6.5e5, "taken_all_usd": 7.5e5}, {**fee_lender, "id": "planted-few", "short": "Planted Few", "rank": 83, "priced_loans": 19, "taken_usd": 9.5e5, "taken_all_usd": 9.5e5}, {"view": "lift", "key": "planted", "label": "Planted tier", "diff": 3.75, "loans": 310}, {**fee_lender, "view": "market", "key": "Planted GSE", "priced_loans": 50, "taken_usd": 4.5e5, "taken_all_usd": 5.5e5}]}))
PART_FIELDS = {"estimate": "dot", "low": "lo", "high": "hi", "VS4 loans": "n", "lender-weeks": "weeks"}
READ_LABELS = {"same_fico": "Same FICO", "same_llpa": "Same FICO, same LLPA", "same_number": "Same score number under 820"}
CUT_READS = {"Estimate": "dot", "Low": "spread_lo", "High": "spread_hi", "95% low": "tl", "95% high": "th", "Midpoint": "dot_raw", "5-point match": "cell5", "One-tier match": "tier", "Model": "gap", "Model error": "se", "Model 95% low": "lo", "Model 95% high": "hi"}
CUT_COUNTS = {"VS4 loans": "n", "VS4 loans the model covers": "model_n", "Matched, 5-point band": "read5", "Matched, one LLPA tier": "read_tier", "Lender-weeks": "lender_weeks"}


def planted_read(r):
    """The engine's rows, with what this book's planted loans do not reach: a seller's read gone blank, a sentence on the score used, a cut's words with figures beside them, the same-number rows' share and flags, reads past the switch point and against FICO loans showing a VS4, which FICO pays the same, a check on both sides of its lenders' floor, and lines from the meta row."""
    if r["view"] == "lender" and r["scope"] == "card":
        return {**r, "same_llpa_dot": None, "same_llpa_lo": None, "same_llpa_hi": None, "same_llpa_se": None, "same_llpa_rough": True} if r["key"] == "rocket-mortgage" else {**r, "key": stage_one["id"]}
    if r["view"] == "follows_score" and r["scope"] == "all":
        return {**r, "sentence": "A planted sentence on the score used."}
    if r["view"] == "cut" and r["key"] == "under580":
        return {**r, **dict(zip(CUT_READS.values(), (1.5, 1.0, 2.0, 0.5, 2.5, 1.445, 1.235, 1.655, 1.765, 0.705, 0.395, 3.135))), "text": "A planted cut's text."}
    if r["view"] == "same_number" and r["scope"] == "month":
        return {**r, "in_share": 0.25 if r["group"] == "stake" else 0.5, "thin": False}
    if r["view"] == "same_number" and r["key"] == "under640":
        return {**r, "flag": "unsettled"}
    if r["view"] == "same_number" and r["key"] == "over820":
        return {**r, "flag": "no_like_fico", "cell5": 3.25, "read": 87, "read_number": 6, "gap": -2.755, "se": 0.655, "lo": -4.035, "hi": -1.475}
    if r["view"] == "same_number" and r["scope"] == "fade":
        return {**r, "text": "Is the gap narrowing? The two lines still differ on closings from November on: no clear narrowing yet."}
    if r["view"] == "past":
        return {**r, **dict(zip(("cell5", "cell20", "model"), {"rocket": (-2.255, -1.745, -0.655), "rocket_fannie": (-2.355, -1.855, -0.765), "uwm": (None, 3.355, 0.555), "rare": (1.155, 1.365, -0.145)}[r["key"]])), "read5": 1110 + r["order"], "read20": 4440 + r["order"], "lender_weeks": 3 + r["order"], "comparators": 3330 + r["order"], "thin": r["key"] != "rare"}
    if r["view"] == "equivalent":
        return {**r, "eq": 673.25, "eq_lo": 665.75, "eq_hi": 681.25, "fico_rare": 687.25, "fico_rare_n": 148 + r["order"]}
    if r["view"] == "fico_gap":
        return {**r, "model_n": r["n"] - 1, "read5": 1120 + r["order"], "read_tier": 1130 + r["order"], "fannie": 1.135 + r["order"]}
    if r["view"] == "lender" and r["scope"] == "group" and r["key"] == "uwm_broker":
        return {**r, "same_fico_read5": 1116, "same_fico_read_tier": 1117, "same_fico_shown_cell5": 1.855, "same_fico_shown_tier": 2.145, "same_fico_shown_read5": 1110, "same_fico_shown_read_tier": 2220, "same_number_shown_tier": 3.655, "same_number_shown_read5": 88, "same_number_shown_read_tier": 1115}
    if r["view"] == "check" and r["key"] == "rare_high_vs4":
        return {**r, "rocket": -3.25, "rocket_n": 99, "uwm": -4.755, "uwm_n": 100, "uwm_correspondent": -5.255, "uwm_correspondent_n": pricing.RARE_CHANNEL, "uwm_broker": 2.755, "uwm_broker_n": pricing.RARE_CHANNEL - 1, "top_share": 0.355, "without_top": 1.255, "without_top_se": 0.455, "without_top_n": 123}
    if r["view"] == "check" and r["key"] == "rate_range":
        return {**r, "value": 23, "pass": False, "detail": "A planted line on the rates."}
    if r["view"] == "meta":
        return {**r, "expected": "A planted line on what to expect, so this row reads short of full credit.", "sample": "A planted line on the sample.", "gap_line": "A planted line on the gap.", "number_caption": "A planted caption.", "lender_line": "A planted line on one lender's reads.", "rule_at_lock": "A planted line on the rule at lock.", "test_line": "A planted line on the test.", "rc_reason": "a planted reason",
                "equivalent_stat": "A planted stat on what FICO a VS4 pays.", "equivalent_caption": "A planted caption on what FICO a VS4 pays.", "equivalent_more": "A planted line on which FICO pays the same.",
                "lender_rates": "A planted line on the lender groups.", "score_lead": "A planted reason. Each test below stops short."}
    return r


line_rows = [{**r, "use_below_late": 0.125, "use_below_late_n": 6615} if r["key"] == "main" else {**r, "lender_weeks": pricing.THIN_WEEKS - 1} if r["key"] == "fannie" else {**r, "lender_weeks": pricing.THIN_WEEKS} if r["key"] == "lower" else r for r in views_line["line"]]
said_by_line = {r["key"]: r["text"] for r in views_line["limit"] if r["key"] == "line"}
behind_b = [{**dict.fromkeys(("cell5", "tier", "model", "mid", "n", "read5", "read_tier", "value", "lo", "hi")), "view": "behind", "order": i, "sentence": "A planted head", **row} for i, row in enumerate((
    {"key": "same_llpa_from_780", "what": "A planted group", "cell5": -2.345, "tier": 1.255, "model": -0.645, "mid": -0.545, "n": 1237, "read5": 571, "read_tier": 893}, {"key": "method_plain", "what": "A planted value", "value": 1.875}, {"key": "same_loans_fico", "what": "A planted range", "cell5": -3.425, "tier": -2.305, "model": -1.115, "mid": -2.865, "n": 327, "read5": 216, "read_tier": 310, "lo": -5.555, "hi": -0.125},
    {"key": "crossing", "what": "A planted crossing", "value": 17.25, "lo": 12.75, "hi": 23.25}, {"key": "crossing_some_lender", "what": "The same at a planted lender", "lo": 11.25, "hi": 27.75}, {"key": "crossing_per_bp", "what": "A planted slope", "value": 3.25}, {"key": "curve_points", "what": "A planted gap in points", "value": 33.75}, {"key": "curve_bp", "what": "A planted gap in bp", "value": 6.25},
    {"key": "rc_back_lower_llpa", "sentence": "The thin line", "what": "A planted top", "hi": 6.125}))]
planted_b = [r for r in (planted_read(r) for r in built_b) if r["view"] not in ("line", "behind")] + line_rows + [{**views_b["limit"][0], "order": 90 + i, "key": k, "text": t} for i, (k, t) in enumerate((*said_by_line.items(), ("past", "A planted line past the switch point."), ("book", "A planted book: about the same in both months.")))] + behind_b[::-1]
(gse_paths.SITE_DATA / "rates.json").write_text(json.dumps({"rows": planted_b}))
book_b = build_workbook()
with zipfile.ZipFile(book_b) as z:
    names_b = [e.get("name") for e in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", ns)]
    strings_b = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    assert not any(b't="e"' in z.read(f"xl/worksheets/sheet{i + 1}.xml") for i in range(len(names_b))), "no error cells"
assert names_b.index("Fees") + 1 == names_b.index("Rates") == names_b.index("Rules") - 1, names_b
assert not workbook_says(strings_b), workbook_says(strings_b)
rates_sheet = sheet_cells(book_b, "Rates")
on_rates = {v for v in rates_sheet.values() if isinstance(v, str)}
# The answer leads, in its lines and not the one long sentence, with what the files cannot settle directly under it; then the date; then the lead table; then what is compared, who is left out and which grid sorts the rows, directly under the stamp and only there, the sentence on a VS4 loan showing no FICO and the methods, in sheet words.
meta_b = next(r for r in planted_b if r["view"] == "meta")
answers_b = sorted(views_b["answer"], key=lambda r: r["order"])
assert [rates_sheet.get((2 + i, 0)) for i in range(len(answers_b))] == [r["text"] for r in answers_b] and len(answers_b) > 1 and meta_b["answer"] not in on_rates, answers_b
selected_b = next(r["text"] for r in views_b["limit"] if r["key"] == "selected")
assert rates_sheet[(2 + len(answers_b), 0)] == selected_b and list(rates_sheet.values()).count(selected_b) == 1, "directly under the answer, and not again in the limits"
dated_at = 3 + len(answers_b)
assert rates_sheet[(dated_at, 0)] == "Data through" and rates_sheet[(dated_at, 1)] == (date.fromisoformat(meta_b["as_of"]) - date(1899, 12, 30)).days, rates_sheet.get((dated_at, 1))
assert rates_sheet[(dated_at + 2, 0)] == "The lead figures", "the lead table, directly under the date"
method_at = next(r for (r, c), v in rates_sheet.items() if c == 0 and v == meta_b["changed"])
assert rates_sheet[(method_at - 1, 0)] == "What is compared, and by which methods" and rates_sheet[(dated_at + 4, 0)] == "Comparison" and method_at == dated_at + 4 + len(views_b["row"]) + 3, method_at  # after the table's own rows
said_top = [rates_sheet.get((method_at + i, 0)) for i in range(10)]
limit_b = {r["key"]: r["text"] for r in planted_b if r["view"] == "limit"}
assert said_top[:6] == [meta_b["changed"], meta_b["stamp"], limit_b["left_out"], limit_b["grid"], limit_b["ranges"], "A planted line on the sample."] and "a VS4 loan showing no FICO is unknown and left out of the same-FICO rows" in said_top[6], said_top
assert all(list(rates_sheet.values()).count(limit_b[key]) == 1 for key in ("left_out", "grid", "ranges", "rebuilt")) and rates_sheet[(dated_at, 2)] == limit_b["rebuilt"], "printed once: under the stamp, and the newest file's beside the date"
assert said_top[7] == meta_b["stamp_more"].replace("The dot is the midpoint of the first two and the bar the range across all three.", "The estimate is the midpoint of the first two, and low and high the range across all three.") and "The dot" not in said_top[7], said_top[7]
assert "Error is one standard error" in said_top[8] and "Model 95% low and high are the model's figure less and plus about two errors." in said_top[8] and "A lender-week is one lender's loans first disclosed in one week, with at least 5 loans." in said_top[8], said_top[8]
assert said_top[9].startswith("A VS4 loan is one the Pricing Indicator says priced on VS4 or, on records before the indicator, one whose only score shown is VS4. VS4 loans means the loans in the row. VS4 loans the model covers: those of them inside its range of scores.") and "Rough: under 8 lender-weeks, or under 100 matched loans on either exact match." in said_top[9], said_top[9]
lead_fields = {"Comparison": "title", "Which loans": "sub", "What it says": "sentence", "Estimate": "dot", "Low": "lo", "High": "hi", "95% low": "tl", "95% high": "th", "5-point match": "cell5", "5-point match: error": "cell5_se", "One-tier match": "tier", "One-tier match: error": "tier_se", "Model": "model", "Model error": "model_se",
               "Midpoint": "dot_raw", "Lowest method": "lo_raw", "Highest method": "hi_raw", "VS4 loans": "n", "Matched, 5-point band": "read5", "Matched, one LLPA tier": "read_tier", "VS4 loans the model covers": "model_n", "Lender-weeks": "lender_weeks", "Fannie alone": "fannie", "Fannie alone: VS4 loans": "fannie_n"}
lead_got = reads_back(rates_sheet, "The lead figures", views_b["row"], lead_fields)
assert list(lead_got[0]) == list(lead_fields) and lead_got[0]["Comparison"] == "Same FICO" and len(lead_got) == 5 and lead_got[3]["Comparison"] == f"of those, FICO under {pricing.SCORE_CUTS[-1]}" and any(round(r["cell5"], 1) != r["cell5"] for r in views_b["row"]), lead_got[0]  # same FICO first, every column and all five rows, and these reads carry two decimals
assert any("Low and high are printed to the half point (whole point where the methods sit 4+ apart), low down and high up" in t and "95% low and 95% high: an approximate 95% range for the estimate, from resampling lender and channel groups; the sentences print" in t for t in on_rates), "the note on how low and high print, and on what the 95% range is of"
number_of = lambda scope: [r for r in planted_b if r["view"] == "same_number" and r["scope"] == scope]  # noqa: E731
number_fields = {"5-point match": "cell5", "One-tier match": "tier", "Model": "gap", "Model error": "se", "Model 95% low": "lo", "Model 95% high": "hi", "VS4 loans": "pool", "VS4 loans the model covers": "n", "Matched, 5-point band": "read", "Matched, one LLPA tier": "read_tier", "Lender-weeks": "lender_weeks"}
printed_fields = {"Estimate": "dot", "Low": "spread_lo", "High": "spread_hi", "Midpoint": "dot_raw", "Lowest method": "lo_raw", "Highest method": "hi_raw"}
by_month_b = sorted(number_of("month"), key=lambda r: (r["group"] != "stake", r["close"]))
assert {r["group"] for r in by_month_b} == {"stake", "no_stake"}, by_month_b
flag_of = lambda r: {"unsettled": "Unsettled: the 3 methods sit 3+ bp apart", "no_like_fico": "Almost no comparable FICO loans at its number", "few_like_fico": "Few comparable FICO loans at its number"}.get(r["flag"])  # noqa: E731
bands_b = [{**r, "shown_flag": flag_of(r), "shown_label": "VS4 820+", "plain": r["cell5"], "plain_n": r["read"], "cell5": None, "read": None, **dict.fromkeys(("gap", "se", "lo", "hi"))} if r["key"] == "over820" else {**r, "shown_flag": flag_of(r), "shown_label": r["label"], "plain": None, "plain_n": None} for r in number_of("band")]
beside_b = [{**r, "shown_rocket": r["rocket"] if (r["rocket_n"] or 0) >= 100 else None, "shown_uwm": r["uwm"] if (r["uwm_n"] or 0) >= 100 else None, "shown_uwm_c": r["uwm_correspondent"] if (r["uwm_correspondent_n"] or 0) >= 50 else None, "shown_uwm_b": r["uwm_broker"] if (r["uwm_broker_n"] or 0) >= 50 else None} for r in (planted_read(r) for r in views_b["check"])]
cuts_b = [planted_read(r) for r in views_b["cut"]]
lender_fields = {**PART_FIELDS, "matched, 5-point band": "read5", "matched, one LLPA tier": "read_tier"}
shown_fields = {"5-point match": "shown_cell5", "one-tier match": "shown_tier", "matched, 5-point band": "shown_read5", "matched, one LLPA tier": "shown_read_tier"}
lender_reads = {**{f"{label}: {head}": f"{read}_{part}" for read, label in READ_LABELS.items() for head, part in lender_fields.items()}, **{f"{label}, shown: {head}": f"{read}_{part}" for read, label in READ_LABELS.items() for head, part in shown_fields.items()}}
for title, want, fields in (("Rocket's switch point: the step in the rate", [r for r in line_rows if r["key"] != "scan"], {"Line": "label", "Step": "est", "Error": "se", "95% low": "lo", "95% high": "hi", "Loans": "n", "Loans above the line": "above", "Lender-weeks": "lender_weeks", "On VS4, 15 to 19 above FICO": "use_below", "On VS4, 20 to 24 above FICO": "use_above",
                                                                                                                       "15 to 19 above, closed by Sep: share on VS4": "use_below_early", "15 to 19 above, closed by Sep: loans": "use_below_early_n", "15 to 19 above, closed after Sep: share on VS4": "use_below_late", "15 to 19 above, closed after Sep: loans": "use_below_late_n"}),
                            ("The same test at every line where nothing switches", [r for r in line_rows if r["key"] == "scan"], {"Test": "label", "Lines": "lines", "2.5th percentile": "p2_5", "97.5th percentile": "p97_5", "Lowest": "min", "Highest": "max", "Size of a step, 90th percentile": "abs_p90", "Misses zero": "miss_share"}),
                            ("Past the switch point, where the LLPA does not change", [planted_read(r) for r in views_b["past"]], {"Loans": "label", "5-point match": "cell5", "20-point match": "cell20", "Model": "model", "Loans with VS4 25 to 49 above FICO": "n", "FICO loans with VS4 0 to 19 above FICO": "comparators", "Matched, 5-point band": "read5", "Matched, 20-point band": "read20", "Lender-weeks": "lender_weeks"}),
                            ("From raw to like for like", views_b["steps"], {"Step": "label", "Gap": "gap", "Error": "se", "VS4 loans matched": "read", "VS4 loans": "pool"}),
                            ("Same score number, by closing month", by_month_b, {"Group": "label", **printed_fields, **number_fields, "Share of the month in this table": "in_share"}),
                            ("Same score number, with 20 points off VS4", number_of("less20"), {"Loans": "label", **printed_fields, **{head: key for head, key in number_fields.items() if head != "VS4 loans the model covers"}}),
                            ("Same score number, by issue period", number_of("period"), {"Issued": "label", **number_fields, "VS4 less 20": "less20", "VS4 less 20: error": "less20_se"}),
                            ("Same FICO, by the gap between the scores", [planted_read(r) for r in views_b["fico_gap"]], {"VS4 above FICO": "label", **printed_fields, "95% low": "tl", "95% high": "th", "5-point match": "cell5", "One-tier match": "tier", "Model": "model", "VS4 loans": "n", "VS4 loans the model covers": "model_n", "Matched, 5-point band": "read5", "Matched, one LLPA tier": "read_tier", "Lender-weeks": "lender_weeks", "Fannie alone": "fannie"}),
                            ("Same score number: VS4 under 640 and VS4 820+", bands_b, {"VS4 band": "shown_label", "Flag": "shown_flag", **number_fields, "Matched at its own number, 5-point band": "read_number", "Against FICO 780+, no score band": "plain", "Against FICO 780+, no score band: VS4 loans matched": "plain_n"}),
                            ("Same score number, by the gap between the scores", number_of("gapband"), {"VS4 above FICO": "label", **printed_fields, "95% low": "tl", "95% high": "th", **number_fields}),
                            ("Same score number, by gap and closing month", sorted(number_of("gapband_month"), key=lambda r: (r["order"], r["close"])), {"VS4 above FICO": "label", **number_fields}),
                            ("Which FICO has paid the same rate as a VS4 score", [planted_read(r) for r in views_b["equivalent"]], {"VS4 band": "band", "VS4 loans the model covers": "n", "FICO they show": "fico_mean", "FICO that pays the same rate": "eq", "Its low": "eq_lo", "Its high": "eq_hi", "VS4 number": "vs_mean", "VS4 above that FICO": "points", "FICO at lenders that rarely use VS4": "fico_rare", "Loans behind that FICO": "fico_rare_n", "Rate falls, bp per 20 points": "slope"}),
                            ("By lender and channel", [planted_read(r) for r in views_b["lender"] if r["scope"] == "group"], {"Lender and channel": "label", **lender_reads}),
                            ("By lender, all its channels together", [planted_read(r) for r in views_b["lender"] if r["scope"] == "card"], {"Lender": "label", **lender_reads, "Same FICO, VS4 under 820 (UWM only)": "same_fico_under820"}),
                            ("Does the rate follow the score used?", views_b["follows_score"], {"Which loans": "label", "Per 20 points of VS4": "on_vs4", "VS4: error": "on_vs4_se", "Per 20 points of FICO": "on_fico", "FICO: error": "on_fico_se", "VS4 slope less FICO slope": "diff", "Slope gap: error": "diff_se", "Loans": "n", "Lender-weeks": "lender_weeks"}),
                            ("More cuts: description, not findings", [{**r, **dict.fromkeys(CUT_READS.values())} if r["text"] else r for r in cuts_b], {"Row": "label", **CUT_READS, **CUT_COUNTS}),
                            ("Milliman's basis: VS4 less 20", views_b["milliman"], {"Loans": "label", "5-point match": "cell5", "One-tier match": "tier", "Matched, 5-point band": "read", "Matched, one LLPA tier": "read_tier", "VS4 loans": "pool"}),
                            ("Build checks", beside_b, {"Check": "label", "Value": "value", "Limit": "limit", "Unit": "unit", "Loans": "n", "Rocket": "shown_rocket", "Rocket loans": "rocket_n", "UWM": "shown_uwm", "UWM loans": "uwm_n", "UWM, correspondent": "shown_uwm_c", "UWM, correspondent: loans": "uwm_correspondent_n", "UWM, broker": "shown_uwm_b", "UWM, broker: loans": "uwm_broker_n", "Largest lender's share": "top_share", "Without it": "without_top", "Without it: error": "without_top_se", "Without it: loans": "without_top_n"})):
    reads_back(rates_sheet, title, want, fields)
lender_got = table_under(rates_sheet, "By lender and channel")
assert [(r["Not like for like"], r["Same FICO: rough"]) for r in lender_got] == [("Yes" if r["not_like_for_like"] else None, "Yes" if r["same_fico_rough"] else None) for r in views_b["lender"] if r["scope"] == "group"]
assert not [head for head in lender_got[0] if "model error" in head] and next(r for r in lender_got if r["Lender and channel"] == "UWM broker")["Same FICO, shown: 5-point match"] == 1.855, "no model error beside the estimate, and the reads against FICO loans showing a VS4"
assert any("Gaps between lenders under about 3 bp on same number, or about 5 bp on the same-FICO and same-LLPA estimates, are too small to call." in t and "Shown: the two exact matches again" in t for t in on_rates), "how far to read gaps between lenders, and what shown means"
assert "UWM's midpoint on those of its loans that show a FICO." in " ".join(on_rates) and not [r for r in views_b["lender"] if r.get("same_fico_under820") is not None and r["key"] != "united-wholesale-mortgage"], "the column is one lender's, as its header says"
card_got = table_under(rates_sheet, "By lender, all its channels together")
assert [r["Rocket correspondent left out"] for r in card_got] == ["Yes" if r["correspondent_out"] else None for r in views_b["lender"] if r["scope"] == "card"] and "Yes" in [r["Rocket correspondent left out"] for r in card_got], card_got
assert "Blank under 100 VS4 loans" not in " ".join(on_rates) and sum("Blank under 100 matched loans on either exact match" in t for t in on_rates) >= 6, "the floor is on matched loans"
# Rocket's switch point: the note says what the first rows and the rows with no switch are, and what the use columns count; a line where nothing switches has its own table; the sentence sits under the first table.
assert line_rows[0]["key"] == "main" and line_rows[0]["use_below"] is not None and any(r["key"].startswith("false|") for r in line_rows), line_rows
assert any("Where the LLPA would not change: it is the same at FICO and at FICO plus 34" in t and "lines where nothing switches" in t and "The two On VS4 columns count all those loans, whatever the LLPA." in t and "The row where the LLPA would fall does not show what the LLPA does to the rate: the pick flips at the same line, so the two cannot be told apart." in t for t in on_rates) and all(t in on_rates for t in said_by_line.values()) and len(said_by_line) == 1 and list(rates_sheet.values()).count(said_by_line["line"]) == 1 and "On same FICO, a planted book: about the same in both months." in on_rates, said_by_line
line_got = table_under(rates_sheet, "Rocket's switch point: the step in the rate")
assert [r["Rough"] for r in line_got] == ["Yes" if r["lender_weeks"] < pricing.THIN_WEEKS else None for r in line_rows if r["key"] != "scan"] and {"Yes", None} == {r["Rough"] for r in line_got} and not [r for r in line_got if r["Line"] == "Every line where nothing switches"], line_got
said_at = lambda said: next(r for (r, c), v in rates_sheet.items() if c == 0 and v == said)  # noqa: E731
assert rates_sheet[(said_at(said_by_line["line"]) - 1, 0)] == line_rows[-2]["label"] and rates_sheet[(said_at("A planted line past the switch point.") - 1, 0)] == "FICO loans at lenders that rarely use VS4" and list(rates_sheet.values()).count("A planted line past the switch point.") == 1 and "A planted book: about the same in both months." not in on_rates, "each sentence under its table, and only there"
assert "VS4 loans the model covers" not in table_under(rates_sheet, "Same score number, with 20 points off VS4")[0], "that row's n counts every loan"
assert [r["Rough"] for r in table_under(rates_sheet, "Past the switch point, where the LLPA does not change")] == ["Yes", "Yes", "Yes", None], "past, rough by its own weeks"
# A row that says it has no comparable FICO loans keeps its counts and flags, and no figure beside the words.
cut_words = next(r for r in table_under(rates_sheet, "More cuts: description, not findings") if r["Row"] == "FICO under 580")
assert all(cut_words[head] is None for head in CUT_READS) and cut_words["Flag"] == "Description. A planted cut's text.", cut_words
assert {r["Cut"] for r in table_under(rates_sheet, "More cuts: description, not findings")} >= {"LTV", "On its own row"} and {r["Flag"] for r in table_under(rates_sheet, "More cuts: description, not findings")} >= {None, "Description. Not like for like."} and "Description." not in {r["Flag"] for r in table_under(rates_sheet, "More cuts: description, not findings")}, "the word only where the flag says more"
# Rough where the row says so, in every table that carries it; by closing month also on a month under half in, as the page draws it hollow, and exactly half is not under.
month_rough = [r["Rough"] for r in table_under(rates_sheet, "Same score number, by closing month")]
assert month_rough == ["Yes" if r["in_share"] < 0.5 else None for r in by_month_b] and {"Yes", None} == set(month_rough), month_rough
for title, want in (("Same score number, by issue period", number_of("period")), ("Same score number, by the gap between the scores", number_of("gapband")), ("Same score number, by gap and closing month", sorted(number_of("gapband_month"), key=lambda r: (r["order"], r["close"]))), ("More cuts: description, not findings", views_b["cut"])):
    assert [r["Rough"] for r in table_under(rates_sheet, title)] == ["Yes" if r["thin"] else None for r in want], title
# The 820+ row's own columns: its flag from the data, a count at its own number, its plain read away from the 5-point columns, and a line saying so.
over_b = next(r for r in table_under(rates_sheet, "Same score number: VS4 under 640 and VS4 820+") if r["VS4 band"].startswith("VS4 820+"))
over_row = next(r for r in number_of("band") if r["key"] == "over820")
assert over_b["VS4 band"] == "VS4 820+" and all(over_b[head] is None for head in ("Model", "Model error", "Model 95% low", "Model 95% high")) and over_b["VS4 loans"] == over_row["pool"] and over_b["5-point match"] is None and over_b["Matched, 5-point band"] is None and over_b["Against FICO 780+, no score band"] == over_row["cell5"] == 3.25 and over_b["Against FICO 780+, no score band: VS4 loans matched"] == over_row["read"] == 87 and over_b["Matched at its own number, 5-point band"] == 6, over_b
assert "On the VS4 820+ row the 5-point, one-tier and model columns stay blank while it has almost no comparable FICO loans at its own number: its exact match is against FICO 780+ with no score band, in the last two columns, and the column before them counts its loans that find a FICO loan at their own number." in on_rates and over_b["Flag"] == "Almost no comparable FICO loans at its number", over_b
assert [r["Result"] for r in table_under(rates_sheet, "Build checks")] == [{True: "Pass", False: "Warn"}.get(r["pass"], "Too few loans") for r in beside_b]
follows_got = table_under(rates_sheet, "Does the rate follow the score used?")
assert [r["Test held"] for r in follows_got] == [None if r["scope"] in ("refi_llpa", "purchase_llpa") else "Yes" if r["guard"] else "No" for r in views_b["follows_score"]] and {r["Which loans"] for r in follows_got} == {r["label"] for r in views_b["follows_score"]} and len(follows_got) == 22 and sum(r["Which loans"] == "Refinances, LLPA of the score used held" for r in follows_got) == 2 and sum(r["Which loans"] == "Purchases, LLPA of the score used held" for r in follows_got) == 2, "every scope, by name, and no test said of the four rows it is not run on"
assert any(t.endswith("Refinances and purchases, LLPA of the score used held: the same models with that LLPA held too. The test is not run on them, so Test held stays blank.") for t in on_rates), "what those four rows are"
assert [r["Rate barely moves"] for r in table_under(rates_sheet, "Which FICO has paid the same rate as a VS4 score")] == ["Yes" if r["use_bp"] else None for r in views_b["equivalent"]], "the flat bands"
assert any(t.startswith("VS4 under 820 showing a FICO. Blank under 100 matched loans on either exact match.") for t in on_rates), "the note on gap by closing month"
assert any(t.endswith("Its low and high: about two errors either way, on an error that does not resample lenders.") for t in on_rates), "what the equivalent's range counts"
check_cells = {(r, c): v for (r, c), v in rates_sheet.items() if r > said_at("Build checks")}
rate_range_at = next(r for (r, c), v in check_cells.items() if c == 0 and str(v).startswith("Loans with a note rate outside"))
assert cell_format(book_b, "Rates", rate_range_at, 2) == "0" and cell_format(book_b, "Rates", rate_range_at, 3) == "0" and cell_format(book_b, "Rates", rate_range_at - 2, 2) == "+0.00;-0.00;0.00" and cell_format(book_b, "Rates", rate_range_at - 2, 3) == "#,##0.00" and rates_sheet[(rate_range_at, 2)] == 23, "a count of loans prints as a count"
rare_b = next(r for r in views_b["check"] if r["key"] == "rare_high_vs4")
check_lines = [f"{r['label']}: {r['detail']}".replace("whose bar shows", "whose low and high show") for r in beside_b if r["key"] != rare_b["key"]]
for line in ("A planted caption. Is the gap narrowing? The two groups still differ on closings from November on: no clear narrowing yet.", meta_b["number_bands"], meta_b["equivalent_stat"], "A planted line on which FICO pays the same.", meta_b["equivalent_caption"], "A planted line on the lender groups.", "A planted reason. Each test on this sheet stops short.", meta_b["milliman_line"], meta_b["lender_line"], "A planted line on the gap.", "A planted sentence on the score used.", f"A planted line on what to expect, so the lead table's row for FICO under {pricing.SCORE_CUTS[-1]} reads short of full credit.", "A planted line on the rule at lock.", "A planted line on the test.",
             *(r["text"] for r in views_b["quote"]), *(r["text"] for r in views_b["limit"] if r["key"] not in ("thin", "method")), *check_lines):
    assert line in on_rates, line
assert f"{rare_b['label']}: {rare_b['detail']}" not in on_rates and "A planted line on the steps." not in on_rates, "the test's own line stands for its detail, and the steps table for its sentence"
# Each new line beside what it speaks of: which FICO under its table, between the stat and the caption; the lender groups under theirs; what the tests cannot settle under its own heading, directly above the follows table.
assert said_at("A planted line on which FICO pays the same.") == said_at(meta_b["equivalent_stat"]) + 1 == said_at(meta_b["equivalent_caption"]) - 1 and rates_sheet[(said_at(meta_b["equivalent_stat"]) - 1, 0)] == views_b["equivalent"][-1]["band"], "under the table of which FICO"
assert rates_sheet[(said_at("A planted line on the lender groups.") - 1, 0)] == [r for r in views_b["lender"] if r["scope"] == "group"][-1]["label"] and said_at("Rocket correspondent is left out of every all-lender rate row as not like for like: a planted reason.") == said_at("A planted line on the lender groups.") + 1, "under the lender groups, with what the column Not like for like marks"
assert said_at("A planted reason. Each test on this sheet stops short.") == said_at("Is the gap the score itself?") + 1 == said_at("Does the rate follow the score used?") - 2, "above the follows table"
# Words that only the page's layout gave a meaning now say what they stand for.
closing_note = rates_sheet[(said_at("Same score number, by closing month") + 1, 0)]
assert f"{pricing._day(pricing.ANNOUNCED, year=True)}: one LLPA grid for both scores announced (Statements sheet)." in closing_note and "Rough here also marks a month under half in." in closing_note, closing_note
assert any(r["date"] == pricing.ANNOUNCED and r["who"] == "FHFA" for r in json.loads((gse_paths.SITE_DATA / "statements.json").read_text())["rows"]), "the sheet the note points to says it"
raw_note = rates_sheet[(said_at("From raw to like for like") + 1, 0)]
assert "So it ends at the Issued from Oct 1 row below, not the lead table's figure, which goes back further." in raw_note and next(r for r in views_b["steps"] if r["key"] == "number")["gap"] == next(r for r in number_of("period") if r["key"] == "from_oct")["cell5"], raw_note
assert rates_sheet[(said_at("Milliman's basis: VS4 less 20") + 1, 0)].endswith("Milliman's own figure, on the Statements sheet, is not the same comparison as the lead table's same-number figure: the line under this table says how."), "what it is not the same as"
assert rates_sheet[(said_at("Build checks") - 2, 0)] == meta_b["milliman_line"], "the line under that table"
assert rates_sheet[(said_at("More cuts: description, not findings") + 1, 0)].endswith("On these small rows the 95% ends move with the random draw, so read them to the nearest few bp."), "how far to trust a small row's ends"
# Which FICO prints in whole points, so its points column ties by eye; the decimals stay in the cell.
which_head = said_at("Which FICO has paid the same rate as a VS4 score") + 2
which_cols = {v: c for (r, c), v in rates_sheet.items() if r == which_head}
which_got = table_under(rates_sheet, "Which FICO has paid the same rate as a VS4 score")
for head, want in (("FICO they show", "0"), ("FICO that pays the same rate", "0"), ("Its low", "0"), ("Its high", "0"), ("VS4 number", "0"), ("FICO at lenders that rarely use VS4", "0"), ("Rate falls, bp per 20 points", "#,##0.00")):
    assert cell_format(book_b, "Rates", which_head + 1 + next(i for i, r in enumerate(which_got) if r[head] is not None), which_cols[head]) == want, head
assert which_got[0]["FICO at lenders that rarely use VS4"] == 687.25, "whole points on the sheet, the decimals in the cell"
# The figures behind the sentences: every row in the engine's order at the end of the sheet, its decimals under plain headers, a blank where it has no such figure, and points never printed as a signed gap.
behind_got = reads_back(rates_sheet, "Figures behind the sentences", [{**r, "sentence": r["sentence"].replace("The thin line", "95% low and 95% high")} for r in behind_b], {"What it is": "what", "Sentence": "sentence", "5-point match": "cell5", "One-tier match": "tier", "Model": "model", "Midpoint": "mid", "Value": "value", "95% low": "lo", "95% high": "hi", "VS4 loans": "n", "Matched, 5-point band": "read5", "Matched, one LLPA tier": "read_tier"})
behind_head = said_at("Figures behind the sentences") + 2
behind_cols = {v: c for (r, c), v in rates_sheet.items() if r == behind_head}
assert behind_head + len(behind_b) == max(r for (r, c) in rates_sheet) and "print only in words" in rates_sheet[(behind_head - 1, 0)] and "Sentence: the line that prints or rests on the figure, or Workbook only where none does." in rates_sheet[(behind_head - 1, 0)] and rates_sheet[(behind_head - 1, 0)].endswith("95% low and 95% high: the line's range; on the points rows they move with the random draw, so read them to the nearest point or two."), "the end of the sheet, with what it is for and how far to read its ends"
assert [r["Unit"] for r in behind_got] == ["bp", "bp", "bp", "points", "points", "points per bp", "points", "bp", "bp"], behind_got
for i, r in enumerate(behind_got):
    in_bp = r["Unit"] == "bp"
    for head in ("Value", "95% low", "95% high"):
        if r[head] is not None:
            assert cell_format(book_b, "Rates", behind_head + 1 + i, behind_cols[head]) == ("+0.00;-0.00;0.00" if in_bp else "#,##0.00"), (head, r)
assert cell_format(book_b, "Rates", behind_head + 1, behind_cols["5-point match"]) == "+0.00;-0.00;0.00" and cell_format(book_b, "Rates", behind_head + 1, behind_cols["VS4 loans"]) == "#,##0;(#,##0);-", "a gap and a count"
thin_said = next(r["text"] for r in views_b["limit"] if r["key"] == "thin")
assert thin_said.startswith("The thin line: it resamples") and thin_said.replace("The thin line: it resamples", "95% low and 95% high: this range resamples") in on_rates, thin_said  # the words change, the numbers do not
method_said = next(r["text"] for r in views_b["limit"] if r["key"] == "method")
assert method_said in on_rates, method_said
said_on_sheets = [v for name in ("Rates", "Lenders", "Fees") for v in sheet_cells(book_b, name).values() if isinstance(v, str)]
for gone in ("the dot", "The dot", "the bar", "the second line", "the upper line", "Not on this chart", "thin line", "Thin line", "the whole list above", "Dot", "like FICO", "like loans", "three reads", "lead reads", "Central figure", "Fuller methods", "Spread across", "Rough 95%", "Guard held", "Use bp", "VS4 loans in all", "Read at", "Not read", "off the chart", "On its own line", "a fit", "the fit", "VS4 loans read", "this row", "The two lines", "the top ends", "each test below", "Each test below", "on that chart", "the two same-FICO columns", "every loan at Rocket", "where read", "not read as real", "can read about", "A read on", "redraw", "model read", "in the same cell", "Both, latest on the Lenders sheet", "same cut can come out", "Clearest at", "the same-LLPA row"):
    assert not [t for t in said_on_sheets if gone in t], (gone, [t[:80] for t in said_on_sheets if gone in t])
assert not [t for t in said_on_sheets if re.search(r"the [+\u2212]\d[\d.]* above", t)], "a figure above"
# The flag's other form, with no line on the test: the third check then prints its detail.
(gse_paths.SITE_DATA / "rates.json").write_text(json.dumps({"rows": [{**r, "flag": "few_like_fico"} if r.get("key") == "over820" else {**r, "test_line": None, "milliman_line": None, "rc_reason": None} if r["view"] == "meta" else r for r in (planted_read(r) for r in built_b)]}))
few_sheet = sheet_cells(build_workbook(), "Rates")
few_over = next(r for r in table_under(few_sheet, "Same score number: VS4 under 640 and VS4 820+") if r["VS4 band"] == "VS4 820+")
assert few_over["Flag"] == "Few comparable FICO loans at its number" and few_over["Model"] == -2.755 and few_over["5-point match"] is None and few_over["Against FICO 780+, no score band"] == 3.25, few_over  # the model's figure stays, and the note says what it is
assert "On the VS4 820+ row the 5-point and one-tier columns stay blank: its exact match is against FICO 780+ with no score band, in the last two columns, and the column before them counts its loans that find a FICO loan at their own number. Its Model figure is at its own number, on the few FICO loans the model has up there, not against FICO 780+." in few_sheet.values(), "the note in the other state"
assert f"{rare_b['label']}: {rare_b['detail']}" in few_sheet.values(), "its detail in place of the line"
assert not [v for v in few_sheet.values() if isinstance(v, str) and v.startswith("Rocket correspondent is left out of")], "no reason in the file, so no line on it"
assert few_sheet[(next(r for (r, c), v in few_sheet.items() if c == 0 and v == "Milliman's basis: VS4 less 20") + 1, 0)].endswith("is not the same comparison as the lead table's same-number figure."), "no line under the table, so no pointer to one"
# A month with no share is rough only by its lender-weeks.
(gse_paths.SITE_DATA / "rates.json").write_text(json.dumps({"rows": [{**r, "in_share": None, "thin": r["group"] == "stake"} if r["view"] == "same_number" and r["scope"] == "month" else r for r in planted_b]}))
assert [r["Rough"] for r in table_under(sheet_cells(build_workbook(), "Rates"), "Same score number, by closing month")] == ["Yes" if r["group"] == "stake" else None for r in by_month_b], "no share, so only its lender-weeks"
# Lenders: same FICO first; Rocket's read that is blank leaves all its columns blank; a seller with no row is blank all across; the note says what Rocket's row leaves out; the fee columns have gone to Fees.
lenders_sheet = sheet_cells(book_b, "Lenders")
lender_heads = {v: c for (r, c), v in lenders_sheet.items() if r == 3}
lender_at = {v: r for (r, c), v in lenders_sheet.items() if c == 0 and r > 3}
read_heads = [f"{label}: {part}" for label in READ_LABELS.values() for part in (*PART_FIELDS, "rough")]
assert sorted(lender_heads, key=lender_heads.get)[-18:] == read_heads, sorted(lender_heads, key=lender_heads.get)
assert not {"VS4-priced, both scores", "Of those, lower LLPA on VS4", "Saved per loan with a lower LLPA ($)", "Fees taken ($m)"} & set(lender_heads) and "Both, latest" in lender_heads, lender_heads
assert lenders_sheet[(2, 0)] == "Both, earlier and Both, latest are at Fannie Mae for a lender with 20+ Fannie loans in each period, else both GSEs.", "which GSE those two columns read"
assert "Rocket's row leaves Rocket correspondent out. Estimate: midpoint of the two exact-match methods. Rough: under 8 lender-weeks." in lenders_sheet[(2, lender_heads[read_heads[0]])] and lenders_sheet[(2, lender_heads[read_heads[0]])].endswith("Blank under 100 matched loans on either exact match."), lenders_sheet[(2, lender_heads[read_heads[0]])]
card_b = {r["key"]: r for r in views_b["lender"] if r["scope"] == "card"}
for short, row_b_card, blank_reads in (("Rocket", card_b["rocket-mortgage"], {"same_llpa"}), (stage_one["short"], card_b["united-wholesale-mortgage"], set()), ("No Read Bank", None, set(READ_LABELS))):
    for read, label in READ_LABELS.items():
        for part, field in {**PART_FIELDS, "rough": "rough"}.items():
            got_card = lenders_sheet.get((lender_at[short], lender_heads[f"{label}: {part}"]))
            want_card = None if read in blank_reads else row_b_card[f"{read}_{field}"]
            assert got_card == (want_card if part != "rough" else "Yes" if want_card else None), (short, read, part, got_card, want_card)
# Fees: the same columns by lender, 20 or more VS4-priced loans, most taken first; then the LLPA figures by lender and channel, in bp, the figures first and then the model's, marked where not like for like, with the sum and the share under them.
fees_sheet = sheet_cells(book_b, "Fees")
fee_lenders = table_under(fees_sheet, "By lender")
assert [r["Lender"] for r in fee_lenders if str(r["Lender"]).startswith("Planted")] == ["Planted High", "Planted Low"], fee_lenders
assert [fees_sheet.get((3, c)) for c in range(4, 8)] == ["VS4-priced, both scores", "Of those, lower LLPA on VS4", "Saved, net, on all of those (bp of balance)", "Saved per loan with a lower LLPA ($)"], "the market table's headers say what each counts"
market_at = next(r for (r, c), v in fees_sheet.items() if c == 0 and v == "Planted GSE")
assert fees_sheet[(3, 11)] == "Fees taken ($m)" and fees_sheet[(market_at, 11)] == 0.45 and fees_sheet[(market_at, 8)] == 0.55, "what the grossed-up figure starts from"
with zipfile.ZipFile(book_b) as z:
    assert '<mergeCell ref="A2:K2"/>' in z.read(f"xl/worksheets/sheet{names_b.index('Fees') + 1}.xml").decode(), "the note wraps inside the tables, so its last caveat stays on screen"
assert next(r for r in table_under(fees_sheet, "The GSEs' own scores, in points") if r["Fee bucket"] == "Planted tier")["Scope"] == "VS4 a tier better, same FICO tier", "the same FICO tier, not the same FICO"
assert next(r for r in fee_lenders if r["Lender"] == "Planted High") == {"Lender": "Planted High", "Month": (date(2026, 10, 1) - date(1899, 12, 30)).days, "Loans": 900, "Balance ($m)": 310, "VS4-priced, both scores": 70, "Of those, lower LLPA on VS4": 0.62, "Saved, net, on all of those (bp of balance)": 21.5, "Saved per loan with a lower LLPA ($)": 1400, "Taken, grossed up ($m)": 0.75, "Fees taken ($m)": 0.65, "Ticker": "PLAN"}, fee_lenders
llpa_fields = {"Lender and channel": "label", "Purpose": "purpose"}
for side, label in (("lower", "Lower LLPA on VS4"), ("same", "Same LLPA")):
    llpa_fields.update({f"{label}: gap": f"{side}_dot", f"{label}: low": f"{side}_lo", f"{label}: high": f"{side}_hi", f"{label}: model gap": f"{side}_gap", f"{label}: model error": f"{side}_se", f"{label}: VS4 loans": f"{side}_n"})
fees_got = reads_back(fees_sheet, "How the rate differs by LLPA, by lender and channel, in bp", views_b["llpa_rate"], llpa_fields)
assert list(fees_got[0])[:8] == list(llpa_fields)[:8] and not any(head.endswith(": rate") for head in fees_got[0]), fees_got[0]
assert [r["Lower LLPA on VS4: rough"] for r in fees_got] == ["Yes" if r["lower_rough"] else None for r in views_b["llpa_rate"]] and [r["Same LLPA: rough"] for r in fees_got] == ["Yes" if r["same_rough"] else None for r in views_b["llpa_rate"]], fees_got
assert [r["Not like for like"] for r in fees_got] == ["Yes" if r["not_like_for_like"] else None for r in views_b["llpa_rate"]] and "Yes" in [r["Not like for like"] for r in fees_got], fees_got
assert any(isinstance(v, str) and "Blank under 100 matched loans on either exact match. VS4 loans counts all of them, matched or not." in v for v in fees_sheet.values()), "the floor's note"
assert "Loans issued in the month shown, records with every score, terms over 15 years." in fees_sheet[(1, 0)] and any(isinstance(v, str) and v.endswith("The GSEs' own scores are not used for pricing. Neither figure measures how the loans will perform.") for v in fees_sheet.values()), "the base, and what these scores are not"
assert any(isinstance(v, str) and v.endswith("Rows do not add: each is a midpoint on the loans that find a match.") for v in fees_sheet.values()), "why the purpose rows do not add"
cost_heads = [v for v in sheet_cells(book_b, "Cost or rate").values() if isinstance(v, str)]
assert "Share of the saving taken" in cost_heads and "Taken" not in cost_heads, cost_heads
under_llpa = [fees_sheet.get((max(r for (r, c) in fees_sheet) - 1 + i, 0)) for i in range(2)]
assert meta_b["llpa_sum"] and under_llpa == [meta_b["llpa_sum"], meta_b["llpa_share"]] and meta_b["llpa_share"], under_llpa
# The Read me lists every sheet, in the sheets' own order, and says plainly which loans show only the score that priced them, as Carrying VS4 does.
read_me_b = sheet_cells(book_b, "Read me")
list_at = next(r for (r, c), v in read_me_b.items() if v == "Sheets, in order, after this one")
rates_said = next(v for v in read_me_b.values() if isinstance(v, str) and v.startswith("Rates: "))
in_order = [rates_said.index(t) for t in ("the lead figures", "what is compared", "Rocket's switch point", "from raw to like for like", "by closing month", "with 20 points off VS4", "by issue period", "VS4 under 640 and 820+", "by the gap between the scores", "which FICO has paid the same rate as a VS4 score", "by lender and channel", "follows the score used", "more cuts", "Milliman's basis", "the build's checks", "what to quote", "the limits", "the figures behind the sentences")]
assert in_order == sorted(in_order), rates_said
titles_at = [said_at(t) for t in ("The lead figures", "What is compared, and by which methods", "Rocket's switch point: the step in the rate", "Past the switch point, where the LLPA does not change", "From raw to like for like", "Same score number, by closing month", "Same score number, with 20 points off VS4", "Same score number, by issue period", "Same score number: VS4 under 640 and VS4 820+", "Same FICO, by the gap between the scores", "Same score number, by the gap between the scores", "Which FICO has paid the same rate as a VS4 score", "By lender and channel", "Is the gap the score itself?", "Does the rate follow the score used?", "More cuts: description, not findings", "Milliman's basis: VS4 less 20", "Build checks", "What to quote", "Limits", "Figures behind the sentences")]
assert titles_at == sorted(titles_at), titles_at  # the sheet's real order, as the Read me gives it
listed = []
for at in range(list_at + 1, list_at + 40):
    if at not in {r for (r, c) in read_me_b}:
        break
    listed += read_me_b[(at, 0)].split(":")[0].split(", ")
assert listed == names_b[1:], (listed, names_b)
for name in ("Read me", "Carrying VS4"):
    said_there = [v for v in sheet_cells(book_b, name).values() if isinstance(v, str)]
    assert any("oans first disclosed before late September show only the score that priced them" in t for t in said_there) and not any("Until late September" in t for t in said_there), name
# Rules, not findings, on the two sheets the calculator rests on.
assert "A lender priced on VS4 can still pull and pay for FICO, so the two are separate." in " ".join(v for v in sheet_cells(book_b, "Your scenario").values() if isinstance(v, str)) and "Read at Fannie Mae." in sheet_cells(book_b, "FICO exposure").values(), "the plain rule"
assert not [t for t in strings_b if "as nearly all do today" in t or "the cleaner read" in t], "no finding in these words"
# With no lower-LLPA loan the row stays blank and its sentence says so, and the sum is left out.
(gse_paths.SITE_DATA / "rates.json").write_text(json.dumps({"rows": built_a}))
book_a = build_workbook()
blank_lead = {r["Comparison"]: r for r in table_under(sheet_cells(book_a, "Rates"), "The lead figures")}["of which VS4 has a lower LLPA on today's grid"]
assert blank_lead["What it says"] == "Too few to compare yet." and blank_lead["Estimate"] is None and blank_lead["Model"] is None and blank_lead["VS4 loans"] == 0, blank_lead
assert meta_a["llpa_sum"] is None and not any(isinstance(v, str) and v.startswith("Where VS4 lowers the LLPA") for v in sheet_cells(book_a, "Fees").values())
assert not {"Rocket's switch point: the step in the rate", "The same test at every line where nothing switches", "Past the switch point, where the LLPA does not change"} & set(sheet_cells(book_a, "Rates").values()), "no loans around the line, so no table"
(gse_paths.SITE_DATA / "lender_stage.json").write_text(stage_kept)
(gse_paths.SITE_DATA / "rates.json").write_text(rates_kept)
(gse_paths.SITE_DATA / "fees.json").write_text(fees_kept)
# Nothing in the workbook's source holds a finding: labels, rules and policy dates only.
from gsescore.export import FIRM_IN, NUMBERS, SHEET_WORDS  # noqa: E402

assert not [chart for chart, _ in SHEET_WORDS if chart not in Path(pricing.__file__).read_text()], "each phrase still in the engine's sentences"

workbook_source = [n.value for n in ast.walk(ast.parse(Path(sys.modules[build_workbook.__module__].__file__).read_text())) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
for text in workbook_source:
    assert text in NUMBERS.values() or not re.search(r"[+\u2212]\d", text), text
    assert not re.search(r"\$\d", text), text
    said = text.replace("Gaps between lenders under about 3 bp on same number, or about 5 bp on the same-FICO and same-LLPA estimates, are too small to call.", "")  # how far to read a gap between lenders is a rule of the tab, the page's words too
    assert not re.search(r"[Aa]bout [\u2212+-]?\d", said) and not re.search(r"\d bp\b", said.replace("under 2 bp per 20 points", "")), text
    assert not re.search(r"Rocket retail|Rocket broker|UWM broker|UWM correspondent|[Mm]ost of it (is )?[A-Z]|Used VS4|one grid|one fee grid|single-grid|no sign of|clear discount|20-point line|closest test", text), text
assert any(text.startswith("Like-for-like rates") for text in workbook_source) and any("How the rate differs by LLPA" in text for text in workbook_source), "the lint reads the new sheet's text"

# A page must read only datasets its site carries, or its charts stay blank.
from gsescore import site  # noqa: E402
from gsescore.site import DASHBOARD_DATASETS, PUBLIC_DATASETS, PUBLIC_DROP, public_rows  # noqa: E402

public_page = gse_paths.REPO / "site" / "public"  # the repo's, not the planted home's
dashboard_page = gse_paths.REPO / "site" / "dashboard"
assert f"FIRM_IN = {FIRM_IN}" in (dashboard_page / "app.js").read_text(), "a month the page draws hollow is the month the workbook marks rough"


def page_reads(folder):
    reads = {d for attr in re.findall(r'data-source="([\w ]+)"', (folder / "index.html").read_text()) for d in attr.split()}
    for js in folder.glob("*.js"):
        text = js.read_text()
        reads |= set(re.findall(r"""(?:dash\.data|rowsOf)\(['"](\w+)['"]\)""", text))
        reads |= {d for args in re.findall(r"statusOf\(([^)]*)\)", text) for d in re.findall(r"""['"](\w+)['"]""", args)}
    return reads


public_reads, dashboard_reads = page_reads(public_page), page_reads(dashboard_page)
assert public_reads and public_reads <= set(PUBLIC_DATASETS), public_reads - set(PUBLIC_DATASETS)
assert dashboard_reads and dashboard_reads <= set(DASHBOARD_DATASETS), dashboard_reads - set(DASHBOARD_DATASETS)
assert "rate_readout" not in DASHBOARD_DATASETS and "rate_readout" not in PUBLIC_DATASETS and "pricing" not in PUBLIC_DATASETS and "pricing" not in DASHBOARD_DATASETS
assert "rates" in DASHBOARD_DATASETS and "rates" in PUBLIC_DATASETS and "rates" in public_reads, "the rate read went public on Nov 2, 2026"
assert "rates" in dashboard_reads and "rate_readout" not in dashboard_reads and "pricing" not in public_reads | dashboard_reads, (public_reads, dashboard_reads)

# The Rates tab reads only what the builder writes, on planted data: every meta field and limit key, every field of a row, and each lender read. A term on the page has its definition.
page_js = (dashboard_page / "app.js").read_text()
rates_js = page_js[page_js.index("// ---- Rates ----"):page_js.index("// Dollars at any size")]
meta_reads = set(re.findall(r"\bmeta\.(\w+)", rates_js)) | set(re.findall(r"rateLine\('[\w-]+', '(\w+)'", rates_js)) | set(re.findall(r"metaNote\('(\w+)'\)", rates_js)) | {"said_check"}
assert meta_reads == {"answer", "stamp", "dated", "changed", "expected", "rule_at_lock", "test_line", "rc_reason", "number_blend", "number_why", "number_bands", "milliman_line", "equivalent_stat", "equivalent_caption", "equivalent_more", "llpa_sum", "llpa_share", "said_check", "gap_line", "lender_rates", "score_lead", "sample", "offset_tail"}, meta_reads  # lender_line stays in the data, for the workbook
assert meta_reads <= set(meta_a) and all(meta_a["view"] == "meta" and k in views_d["meta"][0] for k in meta_reads), meta_reads - set(meta_a)
assert ".said_check" in page_js[page_js.index("function saidCheck"):page_js.index("function drawSaid")] and "rowsOf('rates')" in page_js[page_js.index("function saidCheck"):page_js.index("function drawSaid")]
limit_reads = set(re.findall(r"limitOf\('(\w+)'\)", rates_js))
assert limit_reads == {"note_rate", "selected", "rests_on", "same_loans", "line", "past", "ranges", "left_out", "method", "thin", "match", "book", "rebuilt"}, limit_reads  # grid stays in the data, for the workbook
assert limit_reads <= {r["key"] for r in views["limit"]} | {r["key"] for r in views_d["limit"]} | {r["key"] for r in views_d3["limit"]} | {r["key"] for r in views_line["limit"]} | {r["key"] for r in views_between["limit"]} | {r["key"] for r in views_past["limit"]}, limit_reads
assert "book" in {r["key"] for r in views_d["limit"]} and all(r["text"] for r in views_d["limit"]), views_d["limit"]
field_reads = set(re.findall(r"\b(?:r|lead|fade|follows)\.(\w+)", rates_js)) - {"who", "check", "date", "statement", "id"}  # how a statement and a lender are found in their own datasets
assert {"dot", "lo", "hi", "tl", "th", "read5", "read_tier", "dot_raw", "lo_raw", "hi_raw", "spread_lo", "spread_hi", "in_share", "thin", "close", "group", "label", "vs_mean", "eq", "eq_lo", "eq_hi", "fico_mean", "fico_rare", "fico_rare_n", "use_bp", "points", "n", "gap", "read", "pool", "text", "not_like_for_like", "lower_dot", "lower_n", "lower_rough", "same_dot", "same_n", "same_rough", "purpose", "pass", "value", "limit", "detail", "sentence", "lender_weeks"} <= field_reads, field_reads
assert field_reads <= set(built_a[0]), field_reads - set(built_a[0])
view_reads = set(re.findall(r"\.view === '(\w+)'", rates_js))
assert view_reads == {"meta", "limit", "answer", "steps", "row", "same_number", "fico_gap", "equivalent", "follows_score", "lender", "cut", "llpa_rate", "quote", "check"} and view_reads <= set(views), view_reads - set(views)
assert all(f"['{key}', '" in rates_js and key in {r["key"] for r in views["steps"]} for key in ("raw", "time", "lender", "traits", "traits_under", "number")), "the ladder's rungs"
assert {"month", "fade", "gapband"} == set(re.findall(r"r\.scope === '(\w+)'", rates_js)) - {"all", "group"} and {"month", "fade", "gapband"} <= {r["scope"] for r in views["same_number"]}, "chart 2 and More cuts"
assert all(f"{read}_{part}" in built_a[0] for read in ("same_fico", "same_llpa", "same_number") for part in ("dot", "lo", "hi", "n", "weeks", "rough")) and "correspondent_out" in built_a[0], "what a lender's cell and the company card read"
page_tools = (dashboard_page / "tools.js").read_text()
assert "rateText('rl-rates'" in rates_js and "hit.index + 1" in rates_js, "the lender line is drawn, and a sentence's stop stays with it"
assert "vx.inLabel = inLabel" in page_tools and "window.vx.inLabel" in rates_js and "d.scope === 'card'" in page_tools and "readText(r[`${k}_dot`]" in page_tools, "chart 2's month tags and the company card's block"
assert "rateList('ra-limits', st, [limitOf('note_rate'), limitOf('rests_on')], left, true)" in rates_js and "rateText('ra-selected', st === 'loading' ? 'ok' : st, limitOf('selected'), new Map(), runIn)" in rates_js and "el.replaceChildren(...parts(shown, left))" in rates_js, "the limits open on the page, in order, and the verdict under the lead with its head and no skeleton"
assert "rateList('ra-score-list', st, [meta.score_lead, meta.score_lead && limitOf('ranges'), meta.expected, meta.rule_at_lock, limitOf('past'), follows && follows.sentence, limitOf('same_loans'), meta.test_line, limitOf('line')], new Map(left), true)" in rates_js, "the first fold under them, in order, with its own term dots"
assert "rateList('ra-firm-list', st, [limitOf('ranges'), limitOf('left_out'), limitOf('method'), limitOf('thin'), limitOf('match'), limitOf('book'), meta.equivalent_more, limitOf('rebuilt')], new Map(left), true)" in rates_js and "meta.lender_line" not in rates_js, "the second fold, in order, with its own term dots"
assert "rateList('rn-notes', st, [...(rows.length ? [metaNote('number_blend'), metaNote('number_why'), { text: fade.text, field: 'text', where: 'view=same_number&scope=fade' }] : []), metaNote('number_bands')], left, true)" in rates_js, "the second card's list under its chart, each line naming its row"
# One helper heads the lists on the first two cards, and no other: the quotes and the checks print as they are.
assert "li.append(...(heads ? runIn : termParts)(rangeDash(textOf(line)), left))" in rates_js and "el.append(...runIn(rangeDash(row.text), left))" in rates_js and rates_js.count("runIn(") == 2 and "head.append(...termParts(" in rates_js, "the one run-in helper, with the term dots inside its head"
assert r"RUN_IN = /^((?:[^:.?(]|\.(?=\d)){2,85})(\s\([^)]*\))?([:?]) /" in rates_js and ".ra-head { color: var(--color-fg); font-weight: var(--cds-font-weight-medium); }" in (dashboard_page / "page.css").read_text(), "a short head, in the page's small bold"
# That pattern, compiled here from the page and run over every planted list sentence: each opens on a head of these shapes or has none, the head keeps its colon, and a bracket before the colon stays out of the bold.
run_in = re.compile(re.search(r"const RUN_IN = /(.+)/;", rates_js).group(1))
assert "head.append(...termParts(hit[2] ? hit[1] : `${hit[1]}${hit[3]}`, left));" in rates_js and "return [head, ...termParts(`${hit[2] ? `${hit[2]}${hit[3]}` : ''} ${text.slice(hit[0].length)}`, left)];" in rates_js, "the head's own line, in full"
LIST_HEADS = re.compile(r"(?:A test|At Rocket's switch point|Controls, same FICO|Fee or score|How much to expect|Is the gap narrowing|Is the old rule why|Left out of same FICO|Left out|Narrow base|On the old rule, in force when most of these rates were likely set|Which score the rate tracks, per 20 points, on loans with both scores 640 to 799|Who is in these figures|Note rate only|Over time|Past the switch point|Same FICO|Same LLPA|VS4 loans under 820 that show a FICO, about [^:]+|VS4 640-819 is about \d+% of the \S{1,6}'s loans|VS4 640-819 is about \d+% of the same-number figure's loans|The thin line|UWM|Which FICO pays the same|Which loans match)[:?]|At Rocket's switch point|Which FICO pays the same")
NO_HEAD = ("A range in bp with no label", "The newest file is provisional", "Each test below stops short", "On VS4 ")
# The old rule's line says when these rates were likely set while most closed by the announcement: the same guard as the grid's clause.
assert all((v["meta"][0]["offset_tail"] == ", though most of these rates were likely set before it") == (grid_tail in limit_of(v, "grid")) and (v["meta"][0]["offset_tail"] is None or grid_tail in limit_of(v, "grid")) for v in (views, views_b, views_late, views_oct, views_other)), [limit_of(v, "grid") for v in (views, views_b, views_late, views_oct, views_other)]
assert any(v["meta"][0]["offset_tail"] is None for v in (views, views_b, views_late, views_oct, views_other)) and views["meta"][0]["offset_tail"], "both ways"
assert next(r for r in views["check"] if r["key"] == "cells")["detail"].endswith(". Not tested: the lower-LLPA row and the row under FICO 780, whose bar shows how far its methods sit apart.") and "They show the methods agree within a few bp on the rows they test, not that the estimates are right." in rates_js, "what the check does not read"
list_heads_seen = set()
for planted_view in (views, views_b, views_c, views_d, views_d3, views_split, views_between, views_few, views_no_shown, views_line, views_e, views_cold, views_rc, views_far, views_no_cell, views_less, views_low, views_rare, views_gap, views_past, views_oct, views_priced, views_other, views_late, views_grow):
    planted_meta = planted_view["meta"][0] if planted_view["meta"] else {}
    for line in ([r["text"] for r in planted_view["limit"] if r["text"] and r["key"] != "grid"] + [r["text"] for r in planted_view["answer"] if r["text"] and r["key"] in ("same_fico", "same_llpa")]
                 + [planted_meta[k] for k in ("score_lead", "expected", "rule_at_lock", "test_line", "equivalent_more", "number_blend", "number_why", "number_bands") if planted_meta.get(k)]
                 + [r["text"] for r in planted_view["same_number"] if r["scope"] == "fade" and r["text"]] + [r["sentence"] for r in planted_view["follows_score"] if r["scope"] == "all" and r["sentence"]]):
        hit = run_in.match(line)
        if hit is None:
            assert line.startswith(NO_HEAD), line
            continue
        assert LIST_HEADS.fullmatch(hit.group(1) if hit.group(2) else hit.group(1) + hit.group(3)), line
        list_heads_seen.add(hit.group(3))
assert list_heads_seen == {":", "?"}, list_heads_seen
for line, want in (("The +14.5's loans that show a FICO, about 70%: about +14.5.", ("The +14.5's loans that show a FICO, about 70%", None, ":")), ("Same FICO (about 70% show one): about 6 bp lower.", ("Same FICO", " (about 70% show one)", ":")), ("Is it so? Yes.", ("Is it so", None, "?"))):
    assert run_in.match(line).groups() == want, line
assert not any(run_in.match(line) for line in ("About 6 bp higher. Then: more.", "A", f"{'long ' * 18}head: more.", "Starts at 5:30 sharp.")), "no head where none is meant"
# leadSplit, its patterns taken from the page: a sentence ends before a capital or a digit, and not at a name's own stop. No lookbehind, which older Safari cannot parse.
lead_end, lead_not = re.search(r"matchAll\(/(.+?)/g\)", rates_js).group(1), re.search(r"if \(!/(.+?)/\.test\(text\.slice", rates_js).group(1)
def lead_split(text):  # noqa: E302
    for hit in re.finditer(lead_end, text):
        if not re.search(lead_not, text[:hit.start()]):
            return text[:hit.start() + 1], text[hit.start() + 1:].strip()
    return text, None
assert lead_split("About 6 bp higher at both U.S. Bank retail and UWM broker. 95% range about +1 to +2. It says so.") == ("About 6 bp higher at both U.S. Bank retail and UWM broker.", "95% range about +1 to +2. It says so.")
assert lead_split("About 6 bp higher at Mr. Cooper retail. It says so.") == ("About 6 bp higher at Mr. Cooper retail.", "It says so.") and lead_split("One sentence at 0.5 bp.") == ("One sentence at 0.5 bp.", None)
for planted_view in (views, views_b, views_few):
    for r in planted_view["answer"]:
        if r["key"] == "same_number":
            assert lead_split(r["text"])[0].endswith(".") and (lead_split(r["text"])[1] or "")[:1] != ".", r["text"]
assert re.search(r"rateList\('rq-list', st, [^;]*\.map\(\(r\) => r\.text\)\)", rates_js) and not re.search(r"rateList\('(rq-list|ra-checks)'[^\n]*, left, true\)", rates_js), "the quotes and checks take no head"
# The answer: the lead above the chart, its caption and then the two lines under it, the same-number line on the second card, and each failure says so once.
assert "['same_fico', 'same_llpa'].includes(r.key)" in rates_js and "tracks" not in rates_js and "rateText('ra-stamp', st, meta.stamp, left);\n    points.replaceChildren(" in rates_js and "only.textContent = st === 'loading' ? '' : st !== 'ok' ? 'Failed to load' : meta.answer || (all.some((r) => r.view === 'row') ? '' : 'No rate figures in this build.')" in rates_js and "points.hidden = st !== 'loading' && !points.children.length" in rates_js, "the answer's lines and its empty and failed states: no line about no figures over a drawn chart, and no dash in a skeleton"
assert "r.view === 'answer' && r.key === 'same_number' && r.text" in rates_js and "answer ? { field: 'text', where: 'view=answer&key=same_number' } : { field: 'dot', where: 'view=row&key=same_number' }" in rates_js and "`${bpText(lead.dot)} bp on VS4 loans under 820`" in rates_js and "rateText('rn-rest', st === 'loading' ? 'ok' : st, statRest, left)" in rates_js and ".money" not in rates_js, "the second card's lead, its binding and its fallback, the rest under it, and no dollars on a card or a tip: What to quote prints them"
assert "Math.round(v / step) * step" in page_js and "step = v >= 1e8 ? 5e7 : 1e7" in page_js and "Math.floor(v / 1e7)" not in page_js, "the scaled-up figure rounds to its step, not down"
assert "Math.floor(r.tl * 2) / 2, Math.ceil(r.th * 2) / 2" in rates_js and "nearBp(r.tl)" not in rates_js, "a 95% range prints outward, as the sentences do"
assert "hollow(r) || hollow(a)" in rates_js and "'Old rule would raise LLPA'" in rates_js and "'Old rule would not'" in rates_js and "map(([g, color, label]) => ({ color, label, pts:" in rates_js and ".attr('fill-opacity', 0.55)" in rates_js, "chart 2 dashes any segment touching a hollow month, its end labels are the page's own, and a firm month's bar can be seen"
assert "if (!color) {  // words alone, with no swatch" in page_js and "...lines.map((l) => [l.color, l.label, 'line']), SAME_MARKS," in rates_js and "legend(key, [SAME_MARKS, ...(anyRough ? [roughKey] : [])])" in rates_js and "SAME_MARKS = [null, 'Dot and bar as above.']" in rates_js and "r.view === 'cut' && r.label && !r.not_like_for_like" in rates_js and "r.label} is left out as not like for like" in rates_js, "chart 4's legend, and what does not compare like for like stays out of the charts and gets its own line"
assert all(field in rates_js for field in ("isNum(r.lower_dot) || isNum(r.same_dot)", "keepsSwitch", "usesWhenever", "Math.abs(mixed) < raw / 2")), "the blank rows of the LLPA table drop, the lead on when lenders use VS4 and the ladder's title each follow from the rows"
assert "el.dataset.where = `view=answer&key=${row.key}`" in rates_js and "['llpa_rate', r.key]" in rates_js, "marks on the answer and the LLPA table name their rows"
assert "['rocket-mortgage', 'united-wholesale-mortgage']" in rates_js and "l.above >= 0.9 && l.below_late < 0.2" in rates_js and "l.above >= 0.75 && l.below_late >= 0.75" in rates_js and "isNum(l.both_late) && l.both_late < BOTH_FEW" in rates_js and "BOTH_FEW = 0.75" in rates_js, "the lender rule's shape"
assert "rungs.length < 3" in rates_js and "r === last ? C_DOT" in rates_js and "hi = Math.max(1, d3.max(rungs" in rates_js, "the ladder: enough rungs, a neutral last bar, a floor on its scale"
assert "like = rows.filter((r) => !r.not_like_for_like), apart = rows.filter((r) => r.not_like_for_like)" in rates_js, "chart 4's rule"
assert "bpLoans(r.lower_dot, r.lower_n)], [bpLoans(r.same_dot, r.same_n)]" in rates_js and '<th scope="col">Lower LLPA on VS4: bp (loans)</th>' in (dashboard_page / "index.html").read_text(), "the LLPA table's columns"
assert re.search(r"LENDER_READS = \[\['same_fico', .*\['same_llpa', .*\['same_number', ", rates_js), "the lender panel in chart 1's order"
assert "follows.clause" not in rates_js and "const hollow = (r) => !!r.thin || (isNum(r.in_share) && r.in_share < FIRM_IN);" in rates_js and "FIRM_IN = 0.5" in rates_js, "the follows sentence stands alone, and the hollow rule"
assert "4 of 4" not in page_js and "4 of 4" not in (dashboard_page / "index.html").read_text() and "checks passed" in rates_js and "rows.length" in rates_js[rates_js.index("function drawRateChecks"):rates_js.index("checks passed")], "how many checks passed follows from the rows"
assert all(word in rates_js for word in ("'Estimate'", "not a margin of error", "95% range, approximate", "Outlined bar: few weeks of loans.", "few lender-weeks", "Dot, bar and thin line as above.")) and "'rough'" not in rates_js.replace("termSpan('thin', 'rough')", "").replace("dotted ? 'rough'", ""), "the legends' plain words, and rough only in the LLPA table"
assert "still arriving" not in rates_js and "RULES" not in rates_js and all(f"l.{field}" in rates_js for field in ("above", "below_late", "both_late", "both_at")), "the lines above the lender panel come from a lender's own figures"
page_terms = set(re.findall(r"^    \['(\w+)', '", (dashboard_page / "visuals.js").read_text(), re.M))
page_index = (dashboard_page / "index.html").read_text()
term_uses = set(re.findall(r'data-term="(\w+)"', page_index)) | set(re.findall(r"termSpan\('(\w+)'", rates_js)) | set(re.findall(r"keyWords\((?:before|'(?:[^'\\]|\\.)*'), '(\w+)'", rates_js)) | set(re.findall(r"\['(\w+)', /", rates_js))
assert {"samefico", "samenumber", "thin", "methods", "llpa", "bp", "vs4loan", "ficoloan", "oldrule", "switchpoint", "dates", "range95"} <= term_uses <= page_terms, term_uses - page_terms
assert '<span data-term="oldrule">old rule</span>: for MBS issued' in page_index and "marked rough, outlined or hollow." in (dashboard_page / "visuals.js").read_text(), "the old rule's line opens on its dotted term, and the glossary names each mark of few lender-weeks"

# Every id a script reads exists, and every static mark on the tab names one row and a field it has.
all_page_js = "".join((dashboard_page / f).read_text() for f in ("app.js", "tools.js", "visuals.js", "market.js"))
assert not re.search(r"\(\?<[=!]", all_page_js), "no lookbehind: older Safari fails at parse and kills the whole script"
page_ids, page_made = set(re.findall(r'\bid="([\w-]+)"', page_index)), set(re.findall(r"\.id = '([\w-]+)'", all_page_js)) | set(re.findall(r'\bid="([\w-]+)"', all_page_js))
assert not set(re.findall(r"getElementById\('([\w-]+)'\)", all_page_js)) - page_ids - page_made, set(re.findall(r"getElementById\('([\w-]+)'\)", all_page_js)) - page_ids - page_made
for mark_field, mark_where in re.findall(r'data-source="rates" data-field="(\w+)" data-where="([^"]+)"', page_index):
    mark_hit = [r for r in built_a if all(str(r.get(k)) == v for k, v in (p.split("=", 1) for p in html.unescape(mark_where).split("&")))]
    assert len(mark_hit) == 1 and mark_field in mark_hit[0], (mark_field, mark_where, len(mark_hit))

# The Rates template's own words hold no finding: no signed number, and a digit only in a date, a rule's threshold or a question title (which carries only VS4's).
tpl_pricing = page_index[page_index.index('<template id="tpl-pricing">'):page_index.index('<template id="tpl-market">')]
assert 'both scores use one grid<span id="ra-offset-tail" data-source="rates" data-field="offset_tail" data-where="view=meta"></span>.</p>' in tpl_pricing and "document.getElementById('ra-offset-tail').textContent = st === 'ok' && meta.offset_tail ? meta.offset_tail : '';" in rates_js, "words only while the file says so"
tpl_words = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", tpl_pricing)))
assert not any(word in tpl_pricing + rates_js for word in ("clear discount", "20-point line", "clear step", "closest test", "no sign of", "almost entirely", "through the LLPA", "starting to loosen", "so these shares rest on", "these figures start", "however many loans", "the two same-FICO columns", "Which score the rate tracks")) and not any(word in tpl_pricing for word in ("fixed gap", "pay more", "These are charges", "Nothing in this fold feeds")), "words the tab has retired"
assert all(said in tpl_words for said in ("At the same score number, does a VS4 loan carry a higher rate?", "for MBS issued before Oct 1, 2026, the LLPA grid counted VS4 as 20 points lower. Since then both scores use one grid", "Does the gap fade or hold on loans locked after the announcement?", "Which FICO has paid the same rate as a VS4 score so far?", "Few weeks of loans.", "Lender gaps under about 3 bp (same number) or 5 bp (same FICO) are too small to call.", "Small groups, so treat these as a description.", "Only if the monthly file shows both scores on older loans.", "The first data are months off.", "at the same gap between VS4 and FICO.", "Can same FICO reach loans issued before Oct 1?", "The dollar figures in this section play no part in the rate figures above.", "which the yearly estimate above scales up for.", "LLPAs are charges the GSEs set, not what a borrower sees.")), "the tab's own lines"
assert not any(gone in tpl_words for gone in ("is the old rule why", "not read as real", "so read", "first read", "Early months are short", "still arriving", "Does the same-number gap fade", "Does same FICO hold", "What would the choice itself be worth", "An arrow marks", "in this fold", "the tile above")), "lines this tab has dropped"
tpl_order = lambda *ids: [tpl_pricing.index(f'id="{i}"') for i in ids]  # noqa: E731
assert tpl_order("ra-answer", "ra-selected", "ra-legend", "ra-chart", "ra-stamp", "ra-points", "ra-offset", "ra-limits", "ra-score", "ra-firm", "ra-steps-wrap", "ra-firm-list", "ra-dated-line") == sorted(tpl_order("ra-answer", "ra-selected", "ra-legend", "ra-chart", "ra-stamp", "ra-points", "ra-offset", "ra-limits", "ra-score", "ra-firm", "ra-steps-wrap", "ra-firm-list", "ra-dated-line")), "the first card's order"
assert '<p id="ra-selected"' in tpl_pricing and "#ra-selected { margin-top: var(--cds-gap-sm); max-width: 78ch; font-size: var(--cds-font-size-body); color: var(--color-fg); }" in (dashboard_page / "page.css").read_text() and tpl_order("rq-dated")[0] < tpl_order("rq-list")[0] and "Rebuilt each week, so date what you quote." in tpl_words and "document.getElementById('rq-dated-line').hidden = !read.meta.dated;" in rates_js, "the verdict is body text in full ink, and What to quote says to date what is quoted, from the file"
assert tpl_order("rn-stat", "rn-rest", "rn-sub", "rn-legend", "rn-chart", "rn-notes", "rn-more") == sorted(tpl_order("rn-stat", "rn-rest", "rn-sub", "rn-legend", "rn-chart", "rn-notes", "rn-more")), "the second card's order"
assert tpl_order("rl-rules", "rl-rates", "rl-legend", "rl-chart", "rl-apart", "rl-note") == sorted(tpl_order("rl-rules", "rl-rates", "rl-legend", "rl-chart", "rl-apart", "rl-note")) and not any(f'id="{gone}"' in tpl_pricing for gone in ("rl-line", "rn-offset", "rn-in", "rn-firm", "rn-money")), "the fourth card's order, and the blocks that left the cards"
assert 'id="rn-rest" data-source="rates" data-field="text" data-where="view=answer&amp;key=same_number" hidden' in tpl_pricing and 'id="ra-selected" data-source="rates" data-field="text" data-where="view=limit&amp;key=selected" hidden' in tpl_pricing and 'id="rl-rates" data-source="rates" data-field="lender_rates" data-where="view=meta" hidden' in tpl_pricing, "each block with no skeleton names its own row and starts hidden"
assert tpl_pricing.count('class="ra-lead') == 2 and rates_js.count("'ra-lead'") == 3 and tpl_pricing.index('id="rn-stat"') < tpl_pricing.index('id="rn-rest"') < tpl_pricing.index('id="rn-chart"') and tpl_pricing.index('id="re-stat"') < tpl_pricing.index('id="re-legend"'), "every card opens on its answer, in one style"
assert all(term in (dashboard_page / "visuals.js").read_text() for term in ("['vs4loan', 'VS4 loan'", "['ficoloan', 'FICO loan'", "['lenderweek', 'Lender-week'", "['range95', '95% range'", "['oldrule', 'The old rule'", "['switchpoint', 'Switch point'", "['dates', 'The dates'")), "the terms the tab dots"
assert all(said in page_index for said in ("Each weekly rebuild runs these checks. A failed check shows a warning here and does not stop the build.", "The range on the Which FICO chart does not resample lenders", "A lender can pick the score as late as delivery", "LTV range and score (within 5 points or one LLPA tier).", 'id="ra-sample"')) and "They show the methods agree within a few bp on the rows they test, not that the estimates are right." in rates_js and "r.unit === 'loans'" in rates_js, "Method says what the checks are and are not, and a count of loans carries no bp"
assert "RATE_READS" not in page_tools and "LENDER_READS" in page_tools and "a < 0.025 ? 'under 5%'" in page_tools, "one list of a lender's reads, and a month barely begun does not print as none in"
assert not re.search(r"(?<![\w.,])[+\u2212\u2013-]\s?\$?\d", tpl_words), re.search(r"(?<![\w.,])[+\u2212\u2013-]\s?\$?\d", tpl_words)
tpl_rest = re.sub(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?!\d)(?:, \d{4})?", "", tpl_words).replace("VS4", "")
for rule in ("under about 3 bp", "or 5 bp", "640\u2013819", "20 or more", "20 points lower", "over 15 years", "Exhibit 19", "2026 file", "June 2027"):
    assert rule in tpl_rest, rule
    tpl_rest = tpl_rest.replace(rule, "")
assert not re.search(r"\d", tpl_rest), re.findall(r".{30}\d.{10}", tpl_rest)

# A file of another shape fails on every tab that reads it, and the page's number moves with the engine's.
assert f"RATES_SHAPE = {pricing.RATES_SHAPE};" in rates_js and "rateRows = (rows) => (rows.length && (rows.find((r) => r.view === 'meta') || {}).shape !== RATES_SHAPE ? [] : rows);" in rates_js and "st: all === rows ? dash.data('rates').status : 'error'" in rates_js and "rateRows(rowsOf('rates'))" in page_js[page_js.index("function saidCheck"):page_js.index("function drawSaid")] and "vx.rateRows(rowsOf('rates'))" in page_tools, "the shape"
assert meta_a["shape"] == pricing.RATES_SHAPE, meta_a["shape"]
# The fixes the render lens asked for stay in.
page_visuals, page_css = (dashboard_page / "visuals.js").read_text(), (dashboard_page / "page.css").read_text()
assert "up = box.bottom + 6 + h > innerHeight && box.top - 6 - h >= 0" in page_visuals and "event.key === 'Escape' && popFor" in page_visuals and "root.addEventListener('pointerleave'" in page_visuals and "document.activeElement !== popFor" in page_visuals, "a definition stays in the viewport and closes by Escape or a pointer leaving"
assert "history.replaceState({ tab: root.querySelector('.vx-tabs [aria-selected=\"true\"]').dataset.tab }, '', location.href);\n        history.pushState({ tab: go.dataset.go }, '', location.href);\n      } catch {}" in page_visuals and "if (event.state && event.state.tab && event.state.tab !== current) show(event.state.tab);" in page_js and "wordsLink.dataset.go = 'method'" in rates_js and "key.append(wordsLink)" in rates_js and "goTab.focus({ preventScroll: true })" in page_visuals, "the words link sits in the first legend, one Back returns from it whether or not a host's setLink moves the frame's URL, and the keyboard goes on from the tab it landed on"
assert "const dragged = event.pointerType === 'mouse' && event.buttons;" in page_visuals and "if (el) { if (!dragged) showPop(el); }" in page_visuals and "else if (popFor && !(dragged ? pop.contains(getSelection().anchorNode) : event.target.closest('.vx-pop'))) hidePop();" in page_visuals and "if (event.target.closest('[data-term]') && !pop.matches(':hover')) hidePop();" in page_visuals and "if (popFor && !(event.target.closest('.vx-pop') && String(getSelection()))) hidePop();" in page_visuals and '.vx-pop::before { content: ""; position: absolute; inset: -7px 0; z-index: -1; }' in page_css and "#pricing .vx-legend [data-go] { padding: 4px 0; margin: -4px 0; }" in page_css and ".vx-tabs, .vx-controls, .vx-pop { display: none; }" in page_css and "#rn-sub { break-after: avoid; }" in page_css and ".vx-tablebox { overflow: visible !important; }" in page_css, "a pointer on a definition keeps it, the words link is a fair target that moves nothing, and a print drops an open definition, keeps a chart's line with it and cuts no table"
assert "`${b.head ? `${b.head}, ` : ''}${ariaOf(r)}`" in rates_js and ".text('VS4 minus FICO, by closing month')" in rates_js, "a screen reader hears each block's name, and chart 2's axis says what it measures"
# The first chart draws every row, a part of a part one step further in, and its axis says what it measures.
assert "(r.strong ? 0 : r.key === 'same_llpa_low' ? 24 : 12)" in rates_js and "const axisWords = 'VS4 minus FICO rate, bp (left of 0: VS4 lower)';" in rates_js and "textWidth(svg, [axisWords]) < W ? axisWords : axisWords.replace(' rate,', ',')" in rates_js and "items = all.filter((r) => r.view === 'row').sort((a, b) => a.order - b.order)" in rates_js and "of note rate (left of 0" not in rates_js, "chart 1's rows and axis"
# The second card's words: its lead without what its title says, and the hollow months in plain words, with few weeks only while a month is thin. More cuts points back to the first chart's marks and prints the first sentence of its line.
assert "statLead.replace(' at the same score number', '')" in rates_js and "`VS4 640-819: the ${bpText(lead.dot)} as two kinds of loan.`" in rates_js and "`Hollow, dashed: under half the month's loans are in this chart${rows.some((r) => r.thin) ? ', or few weeks of loans' : ''}. It starts with loans first disclosed Jul 20, and a recent month is not all in yet.`" in rates_js and "'% in: how much of the month\\'s loans are in this chart. It starts with loans first disclosed Jul 20, and a recent month is not all in yet.'" in rates_js and "keyWords('Hollow" not in rates_js, "card 2's lead and legend"
assert "[[null, 'Dot, bar and thin line as above.'], ...(firstRows.concat(gapRows)" in rates_js and "leadSplit(read.meta.gap_line)[0]" in rates_js and "gapBlocks.some((b) => b.rows === gaps) ? 'Same number: VS4 loans under 820 showing a FICO.' : null" in rates_js and "all issued from Oct 1" not in rates_js and "rc-past" not in rates_js + tpl_pricing, "More cuts' legend and notes"
assert pricing.MODEL_HOLDS in page_index, "Method lists what the model holds in the engine's own words"
assert "window.addEventListener('beforeprint'" in page_js and "window.addEventListener('afterprint'" in page_js and "@media print" in page_css and "print-color-adjust: exact" in page_css and ".vx-chart { min-height: 0 !important; }" in page_css, "print draws at a page's width, with its swatches"
assert "#pricing :is(p, li, .vx-sub, .vx-note) { text-wrap: pretty; }" in page_css and "#pricing :is(h2, .ra-lead, summary) { text-wrap: balance; }" in page_css and "#pricing .vx-card > .vx-more > summary { padding: 4px 0;" in page_css, "no lone last words, and a fold's summary is a fair target"
assert "bpTogether(line)" in rates_js and "bpTogether(rangeDash(text))" in rates_js and "(heads ? runIn : termParts)" in rates_js, "a number keeps its unit, but no such space reaches What to quote, which takes no head"
assert "MODELS" not in page_js and ".mx-grid" not in page_css and "vx-sw-bars" not in page_css, "nothing reads these"
assert "weeksWords = (weeks, rough) => (isNum(weeks) ? (weeks < 8 ? `few lender-weeks (${int(weeks)})` : `${int(weeks)} lender-weeks`) : rough ? 'few lender-weeks' : null);" in rates_js, "few lender-weeks only under the line the page states"
assert "['dates', /\\bweek first disclosed\\b/]" in rates_js and "new Map(TERM_WORDS))" in rates_js and "Too few loans" not in rates_js and "TOO_FEW = 'Too few to compare'" in rates_js, "the plain words, and each fold's own term dots"
assert "forestLoans = (r) => (isNum(r.pool) ? r.pool : r.n);" in rates_js and "of ${count(isNum(r.pool) ? r.pool : r.n)} loans" in rates_js and "saidBp && isNum(lead.dot) && bpText(lead.dot) !== '0' ?" in rates_js and "bpText(lead.dot) !== '0' && lines.length === 2 ?" in rates_js and rates_js.count("bpText(lead.dot) === '0'") == 1, "More cuts counts every loan in a row, and no line speaks of the 0"
assert "${keeper.short} at 20+ points above FICO${keeper.rule === 'moving' ? ', starting to dip below 20 on its newest loans' : ''}; ${user.short} almost whenever it is higher." in rates_js and "Share priced on VS4, on loans showing both scores:" in rates_js and "Share priced on VS4, on loans showing both scores, at 1 to 19 above FICO, in the latest weeks:" in rates_js and "'s rests on the ${pct0(l.both_late)} of its latest" in rates_js and "the rest's VS4 is unknown." in rates_js and "half" not in rates_js[rates_js.index("function lenderRules"):rates_js.index("function drawRateLender")], "the lender rule's words: the limit sits on the shares, and its bars are not said to cover half"
assert "${meta.rc_reason ? ` (${meta.rc_reason})` : ''}" in rates_js and "across the methods" not in rates_js[rates_js.index("function drawRateLender"):rates_js.index("function forestLabel")], "the line on what is left out gives its reason, from the file, and no spread"
assert "document.getElementById('rl-few').hidden = !anyRough || !!meta.lender_rates" in rates_js and 'id="rl-few"' in tpl_pricing and "`${title}: ${FOREST_HEAD}`" in rates_js and "`${bpText(c.dot)}${loans}`" in rates_js and "const start = onZero ? px(0) + 5 : right;" in rates_js and "withLoans" not in rates_js, "chart 4's counts sit on the first column's figures, clear of the zero line, under a head that says so, and its note's first words go when the rate line says them"
assert "mark('.fe-taken-m', 'taken_usd'" in page_js and "m.taken_annual_usd / m.taken_usd" in page_js and "aeiLine.append('Source: ', a, '.')" in page_js and 'class="fe-taken-m" data-source="fees" data-field="taken_usd"' in tpl_pricing and "VS4 loans showing both scores," in tpl_pricing and 'id="llpa-first"' in tpl_pricing, "the tile's figure and its whole factor share a base, and the fold's second sentence goes with its table"
# The page's scripts parse, where this machine can say so: a stray quote in a sentence stops the whole page.
if shutil.which("node"):
    for script_name in ("app.js", "market.js", "tools.js", "visuals.js"):
        script_check = subprocess.run(["node", "--check", str(dashboard_page / script_name)], capture_output=True, text=True, timeout=60)
        assert script_check.returncode == 0, (script_name, script_check.stderr[:300])
assert "A lender can change its pick at once, but rates on loans locked since then take weeks to reach the files." in page_index and "loans priced for it" not in page_index and "'An approximate range for the estimate, from resampling lender and channel groups, or weeks inside them on Which FICO. At the switch point it comes from that fit\\'s own error. Ends in the text are rounded outward. It does not cover points, credits or lock dates.'" in page_visuals, "the words on other tabs that spoke of the same things"
assert 'class="h-top2"' in page_index and "TOP_SHORT = { 'ROCKET MORTGAGE, LLC': 'Rocket', 'UNITED WHOLESALE MORTGAGE, LLC': 'UWM' }" in page_js and "'Two lenders'" in page_js and 'of <span class="mx-month" data-source="score_mix" data-field="start">—</span> loans have a Classic FICO.' in page_index, "the header names the two lenders where the file's two are the ones it knows, and gives the share its month"
assert "event.target.querySelector('.vx-chart, table, .vx-note, .vx-sec-h')) draw();" in page_js, "a fold of plain text keeps a selection and a focused term"

# What is withdrawn stays off the page sources, on both pages.
RATE_LABELS_GONE = ("net_bp", "premium_bp", "reaches_fee", "option_annual_usd", "Shows in the rate", "None visible", "against the FICO model", "Before that check", "VS4 loans compared", "typical miss", "Where does the fee saving go?", "About all",
                    "How spread out", "By type of loan", "A lower fee showing in the rate", "Same fee, rate against its own FICO loans", "of a lower fee shows in its note rate", "investors charging", "if every lender took the lower fee")
PUBLIC_GONE = RATE_LABELS_GONE + ("rate_readout", "m.option_bp")
DASHBOARD_GONE = RATE_LABELS_GONE + ("rowsOf('pricing')", 'rowsOf("pricing")', "Missed (est.)", "Missed, both scores", "All three", "Same fee tier", "Likely to finish", "f it moves as", "No FICO today", "Your no FICO", "if others keep starting", "Taken to match", "unchecked", "no worse",
                                     "saves a fee", "Credit score used for pricing", "±", "r.left_usd", "r.est_usd", "fee.option_bp", "r.on_better", "where the fee often does not change", "on the one fee grid",
                                     "rate_readout", "one-off", "One-off", "being rebuilt", "A version that rebuilds", "Used VS4", "no sign of", "discount beyond", "single-grid", "By LLPA on today's grid", "track both", "Clearest at",
                                     "lenders not redrawn", "redrawing", "Solid does not mean", "disclosure week", "Too few loans to read", "before points and credits", "first useful file is listed", "three reads", "Three reads", "like FICO", "not like loans", "Central figure", "Fuller methods", "Spread across", "Rough 95%", "Words:", "these reads", "use bp", "Thin (rough)", "squares with", "steps_line", "method_more", "old 20-point")
for folder, gone in ((public_page, PUBLIC_GONE), (dashboard_page, DASHBOARD_GONE)):
    sources = [f for f in folder.iterdir() if f.suffix in (".html", ".js", ".css")]
    assert len(sources) >= 5, sources
    for f in sources:
        text = f.read_text()
        for label in gone:
            assert label not in text, (str(f.relative_to(gse_paths.REPO)), label)

# The public contract: on the planted files, every public dataset keeps to the fields and views reference/public_contract.json lists, and a row of a listed view has that view's fields.
contract = json.loads(site.CONTRACT.read_text())
assert set(contract) == set(PUBLIC_DATASETS), set(contract) ^ set(PUBLIC_DATASETS)
assert all(re.fullmatch(r"\w+", k) for want in contract.values() for k in [*want["fields"], *want["views"], *(x for keys in want["views"].values() for x in keys)]), "names only, so no findings"
assert not {d for d in PUBLIC_DROP["fees"] if "." not in d} & set(contract["fees"]["fields"]) and not {"option_bp", "est_usd", "one_loans"} & set(contract["fees"]["views"]["market"]) and "option_bp" in contract["fees"]["views"]["lender"], contract["fees"]
planted_rows = {name: public_rows(name, json.loads((gse_paths.SITE_DATA / f"{name}.json").read_text())["rows"]) for name in PUBLIC_DATASETS}
reached = set()


def holds_contract(name, got):
    want = contract[name]
    outside = {k for r in got for k in r} - set(want["fields"])
    assert not outside, (name, "fields outside the contract", outside)
    for r in got:
        if want["views"]:
            assert "view" in r and r["view"] in want["views"], (name, "view outside the contract", r.get("view"))
            lacks = set(want["views"][r["view"]]) - set(r)
            assert not lacks, (name, r["view"], "lacks", lacks)
            reached.add((name, r["view"]))
        else:
            assert "view" not in r, (name, "a view field the contract does not list", r["view"])


for name, got in planted_rows.items():
    holds_contract(name, got)
assert [name for name, got in planted_rows.items() if not got] == ["seller_weekly", "rates"], [name for name, got in planted_rows.items() if not got]  # no lender here has enough VS4 loans for a row, nor these files FICO loans enough to fit a model
assert not any(r["kind"] == "rate" for r in planted_rows["week_note"] if r["view"] == "line"), planted_rows["week_note"]
for planted_view in (views, views_b, views_between, views_grow, views_line, views_past, views_rc):
    holds_contract("rates", [r for got in planted_view.values() for r in got])  # the rate read's own planted builds
for name, got in (("fees", fee), ("outlook", res), ("week_note", wn), ("closing", cl7), ("lender_stage", why.build_datasets(c4, "2026-12-01")["lender_stage"]), ("lender_mix", split4_rows),
                  ("ceiling", built2["ceiling"]), ("rules", built2["rules"]), ("score_mix", built2["score_mix"]), ("choice", built2["choice"])):
    holds_contract(name, public_rows(name, got))  # the views these builders reach only on the planted tables above
assert {(name, view) for name, want in contract.items() for view in want["views"]} - reached == {("score_mix", "vs_only")}, reached  # no VS4-only loans in records with the indicator here

# The public build: the fees file loses the withdrawn figure and what scales to it, a lender keeps option_bp, and a file the page no longer reads goes.
site.STANDALONE, site.PUBLIC_PAGE, site.DASHBOARD_PAGE = gse_paths.REPO / "site" / "standalone", public_page / "index.html", dashboard_page / "index.html"
assert site.DOCS == home / "docs" and site.PREVIEW == home / "build" / "preview"
(site.DOCS / "data").mkdir(parents=True)
(site.DOCS / "data" / "pricing.json").write_text('{"rows":[]}')
assert "data/fees.json" in site.build_site() and not (site.DOCS / "data" / "pricing.json").exists() and (site.DOCS / "data" / "rates.json").exists()
pub_fees = json.loads((site.DOCS / "data" / "fees.json").read_text())["rows"]
pub_market, pub_lender = [r for r in pub_fees if r["view"] == "market"], [r for r in pub_fees if r["view"] == "lender"]
assert pub_market and pub_lender and pub_market == public_rows("fees", [r for r in json.loads((gse_paths.SITE_DATA / "fees.json").read_text())["rows"] if r["view"] == "market"]), pub_market
assert not {"option_annual_usd", "option_usd", "annual_upb", "upb"} & {k for r in pub_fees for k in r}, pub_fees[0]
assert not {"option_bp", "est_usd"} & {k for r in pub_market for k in r} and all("option_bp" in r and "est_usd" in r for r in pub_lender), pub_market[0]
assert {"taken_annual_usd", "taken_all_usd", "left_usd", "left_loans"} <= set(pub_market[0]), pub_market[0]  # the fee tiles that stay
assert (site.DOCS / "data" / "fees.json").read_text().startswith('{"rows":[{') and set(PUBLIC_DROP) == {"fees"}
for name in PUBLIC_DATASETS:
    assert (site.DOCS / "data" / f"{name}.json").read_text() == (gse_paths.SITE_DATA / f"{name}.json").read_text() or name in PUBLIC_DROP, name
# The private preview keeps the whole fees file and carries the rate read.
preview = site.build_preview()
assert "data/rates.json" in preview and "data/rate_readout.json" not in preview and "data/pricing.json" not in preview and "option_annual_usd" in json.loads((site.PREVIEW / "data" / "fees.json").read_text())["rows"][0], preview

# The weekly report's warnings: a contract view or field missing from docs/data, or a file that cannot be read, is a warning and never a stop. Nothing here reads real data or today's date.
docs_data = site.DOCS / "data"
assert isinstance(site.contract_warnings(), list) and all(isinstance(w, str) for w in site.contract_warnings())
(docs_data / "monthly.json").unlink()
(docs_data / "weekly.json").write_text("{not json")
(docs_data / "summary.json").write_text('{"rows":[1,2]}')
(docs_data / "events.json").write_text('{"rows":[]}')
(docs_data / "choice.json").write_text('{"rows":[{"view":"rule","key":"1","loans":null}]}')
warned = site.contract_warnings()
for name, words in (("monthly", "could not read"), ("weekly", "could not read"), ("summary", "could not read"), ("events", "no rows"), ("choice", "view missing: pull"), ("choice", "fields missing:"), ("choice", "view rule has nothing in:")):
    assert any(w.startswith(f"{name}:") and words in w for w in warned), (name, words, warned)
(docs_data / "week_note.json").write_text('{"rows":[{"view":"not_listed","kind":"rate","not_a_field":1}]}')
warned = [w for w in site.contract_warnings() if w.startswith("week_note:")]
for words in ("fields outside the contract: not_a_field", "views outside the contract: not_listed", "has a rate line"):
    assert any(words in w for w in warned), (words, warned)
real_contract, site.CONTRACT = site.CONTRACT, home / "no_contract.json"
assert len(site.contract_warnings()) == 1 and "could not read" in site.contract_warnings()[0]
site.CONTRACT = real_contract
planted_rates = {"rows": [{"view": "meta", "as_of": "2026-10-27"}]}
(gse_paths.SITE_DATA / "rates.json").write_text(json.dumps(planted_rates))
assert site.rate_read_status(date(2026, 11, 10)) == ("2026-10-27", [])
as_of, old = site.rate_read_status(date(2026, 11, 11))
assert as_of == "2026-10-27" and len(old) == 1 and "15 days old" in old[0], old
missed = {"view": "check", "label": "A check", "value": 3.0, "limit": 1.5, "pass": False, "detail": None}
(gse_paths.SITE_DATA / "rates.json").write_text(json.dumps({"rows": [*planted_rates["rows"], missed]}))
as_of, old = site.rate_read_status(date(2026, 11, 11))
assert as_of == "2026-10-27" and len(old) == 2 and "15 days old" in old[0] and old[1].startswith("rate check: A check"), old  # the checks warn, and stop nothing
for planted_read in ('{"rows":[{"view":"meta","as_of":"not a date"}]}', '{"rows":[{"view":"row"}]}', '{"rows":[{"view":"meta"}]}', "{not json"):
    (gse_paths.SITE_DATA / "rates.json").write_text(planted_read)
    as_of, old = site.rate_read_status(date(2026, 11, 11))
    assert as_of is None and len(old) == 1 and old[0].startswith("rate read:"), (planted_read, old)
(gse_paths.SITE_DATA / "rates.json").unlink()
as_of, old = site.rate_read_status(date(2026, 11, 11))
assert as_of is None and len(old) == 1 and old[0].startswith("rate read:"), old
assert "rates" not in {c["id"] for c in site.dashboard_changes()}, "a dataset missing from site/data stops nothing: the warning above says so"

# And all of it on the weekly command itself: no new bundles, then ingest, build, the public site and the workbook on the planted files, with no rate read to find.
import contextlib  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from gsescore import cli  # noqa: E402

said_out = io.StringIO()
with contextlib.redirect_stdout(said_out):
    cli.cmd_refresh(SimpleNamespace(downloads=home / "no_downloads"))
weekly_report = json.loads(said_out.getvalue())
assert weekly_report["rate_read_as_of"] is None and isinstance(weekly_report["warnings"], list) and any(w.startswith("rate read:") for w in weekly_report["warnings"]), weekly_report
assert "rates" in {c["id"] for c in site.dashboard_changes()} and "rate_readout" not in {c["id"] for c in site.dashboard_changes()}, "every run writes rates.json, and the upload step reads it"
assert "option_annual_usd" not in (site.DOCS / "data" / "fees.json").read_text(), weekly_report
with zipfile.ZipFile(home / weekly_report["workbook"]) as z:
    last_strings = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
assert len(last_strings) > len(strings) and not workbook_says(last_strings), workbook_says(last_strings)  # every sheet this time, with the whole market's
# With a read in hand the report carries its date and any check that missed. Here the build makes that read itself, since these files are too few to fit.
import gsescore.aggregate  # noqa: E402

gsescore.aggregate.build_rates = lambda con, closing=None: [{"view": "meta", "as_of": "2026-10-27"}, {"view": "check", "label": "A check", "value": 3.0, "limit": 1.5, "pass": False, "detail": None}]
said_out = io.StringIO()
with contextlib.redirect_stdout(said_out):
    cli.cmd_refresh(SimpleNamespace(downloads=home / "no_downloads"))
weekly_report = json.loads(said_out.getvalue())
assert weekly_report["rate_read_as_of"] == "2026-10-27" and any(w.startswith("rate check: A check") for w in weekly_report["warnings"]), said_out.getvalue()

print("ok:", home)
