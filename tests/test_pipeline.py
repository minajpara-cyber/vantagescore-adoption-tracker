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
fee = fees.build_datasets(c3)["fees"]
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

# A lower fee's reach, on planted 30-year loans at one lender in one week, FICO 700 at 80 LTV: 2,000 show only a Classic FICO at 6.50%, 500 show both, priced on FICO, at 6.53%, and 500 are priced on
# VS4 745 at 6.43%. Against its own FICO loans with both scores the VS4 loans are 10 bp lower, whatever the model's level; a fifth of the FICO loans are held out.
from gsescore.fee_grid import load_grid as _grid  # noqa: E402
from gsescore.pricing import build_pricing  # noqa: E402

c5 = duckdb.connect()
c5.execute("CREATE MACRO seller_key(x) AS x")
c5.execute("CREATE TABLE seller_map AS SELECT 'R' AS key, 'r' AS id")
c5.execute("CREATE TABLE entity_names AS SELECT 'r' AS id, 'R' AS short, 'R' AS name, NULL::VARCHAR AS ticker")
c5.execute("""CREATE TABLE loans AS SELECT 'FNMA' AS agency, 'L' || i AS loan_id, DATE '2026-10-20' AS first_intraday_date, DATE '2026-11-01' AS first_pay_date, 'C' AS pricing_indicator, 'R' AS seller, 'R' AS channel, 'P' AS purpose, 'P' AS occupancy, 1 AS units, 'SF' AS property_type,
              300000 AS orig_loan_amt, 38 AS dti, 0.0 AS mi_pct, 'TX' AS state, 'N' AS fthb, 1 AS num_borrowers, 'C' AS score_model, 700 AS pricing_score, 700 AS classic_fico, CAST(NULL AS INT) AS vs4, DATE '2026-10-01' AS issue_month,
              '7' AS special_program, 80 AS ltv, 6.50 AS orig_rate, 360 AS loan_term, 'FRM' AS amort_type FROM range(2000) t(i)""")
c5.execute("INSERT INTO loans SELECT * REPLACE ('M' || loan_id AS loan_id, 705 AS vs4, 6.53 AS orig_rate) FROM loans WHERE regexp_extract(loan_id, '[0-9]+')::INT < 500")
c5.execute("INSERT INTO loans SELECT * REPLACE ('V' || loan_id AS loan_id, 'V' AS score_model, 'V' AS pricing_indicator, 745 AS vs4, 745 AS pricing_score, 6.43 AS orig_rate) FROM loans WHERE loan_id LIKE 'L%' AND regexp_extract(loan_id, '[0-9]+')::INT < 500")
reach = next(r for r in build_pricing(c5, "2026-07-20", "true") if r["view"] == "value" and r["scope"] == "All" and r["key"] == "better")
planted_fee = (_grid()[("purchase", 4, 4)] - _grid()[("purchase", 6, 4)]) * 100
assert reach["n"] == 500 and abs(reach["net_bp"] + 10) < 0.05 and abs(reach["fee_bp"] - planted_fee) < 0.01 and abs(reach["reaches_fee"] - 10 / (planted_fee / 5)) < 0.01, reach
assert any(r["view"] == "value" and r["scope"] == "r|R" and r["label"] == "R, retail" for r in build_pricing(c5, "2026-07-20", "true")), "the largest VS4 sellers by channel"

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
rate_rows = [{"view": "week", "cover": "all", "basis": "headline", "key": "2026-10-05", "n": 200, "net_bp": 1.0}, {"view": "week", "cover": "all", "basis": "headline", "key": "2026-10-12", "n": 300, "net_bp": -2.5}]
wn = notes.build_datasets(c4, said, rate_rows)["week_note"]
wk = {r["week"]: r for r in wn if r["view"] == "week"}
assert (wk["2026-10-05"]["partial"], wk["2026-10-05"]["latest"], wk["2026-10-12"]["partial"], wk["2026-10-12"]["latest"], wk["2026-10-12"]["label"]) == (False, True, True, False, "Oct 12 to Oct 14"), wk
lines = {r["kind"]: r for r in wn if r["view"] == "line" and r["week"] == "2026-10-12"}
mix_text = next(r["text"] for r in wn if r["view"] == "line" and r["week"] == "2026-10-12" and r["order"] == 0)
assert mix_text == "150 loans first disclosed Oct 12 to Oct 14, so far: priced on VS4 20.0% (6.7% the week before), both scores show on 100.0% (66.7% the week before), only VS4 shows on 0.0% (0.0% the week before).", mix_text
assert lines["movers"]["text"] == "VS4 share moved most at R 10.0% to 30.0%.", lines
assert lines["both"]["text"] == "Both scores at Fannie Mae moved most at N 0.0% to 100.0%.", lines
assert lines["rule"]["text"] == "Use of VS4 with its score 1 to 19 points above FICO moved at R 10.0% to 30.0%.", lines
assert lines["rate"]["text"] == "VS4 note rates against the FICO model: -2.5 bp on 300 loans (+1.0 bp the week before).", lines
assert (lines["said"]["text"], lines["said"]["url"]) == ("Z: Said something.", "https://example.com/z") and "start" not in lines, lines
assert any(r["kind"] == "start" and r["text"] == "First VS4 loan: R." for r in wn if r["view"] == "line" and r["week"] == "2026-10-05"), wn
assert not any("Too old" in (r["text"] or "") for r in wn if r["view"] == "line"), wn
# Each lender's split of its loans, overall and at each GSE.
from gsescore import why  # noqa: E402

ls4 = {r["id"]: r for r in why.build_datasets(c4)["lender_stage"] if r["view"] == "lender"}
assert (ls4["r"]["mix_fico_only"], ls4["r"]["mix_both_fico"], ls4["r"]["mix_both_vs"], ls4["r"]["mix_vs_only"], ls4["r"]["fnma_both_vs"], ls4["r"]["fhlmc_both_vs"]) == (0.0, 0.8, 0.2, 0.0, 0.2, None), ls4["r"]
assert (ls4["n"]["mix_fico_only"], ls4["n"]["mix_both_fico"], ls4["n"]["fnma_fico_only"], ls4["n"]["fhlmc_loans"]) == (0.5, 0.5, 0.5, 0), ls4["n"]
split4 = {(r["id"], r["agency"], r["start"]): r for r in why.build_datasets(c4)["lender_mix"] if r["view"] == "week"}
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
wm = hmda.build_datasets()["whole_market"]
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
assert all(f'name="{n}"' in book_xml for n in ("Whole market", "Whole market lenders", "Score models")), book_xml[:400]

print("ok:", home)
