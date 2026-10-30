"""The analyst workbook: exports/vs4-tracker-<data through>.xlsx, from the datasets in site/data.

The tables a covering analyst would pull into a model, the weekly note, the statements with links, and the FICO exposure calculator with
your scenario as live formulas. Blue cells are inputs, black are formulas, green are links to another sheet, and yellow marks the judgment
calls. It holds findings, so exports/ is git-ignored and it goes no further than this computer unless the user sends it on.
"""
import json
from datetime import date
from pathlib import Path

import xlsxwriter

from . import paths

EXPORTS = paths.ROOT / "exports"
MONTHS_FROM = "2026-04-01"
TOP_SELLERS = 60
SCENARIO_NO_FICO = "'Your scenario'!K4"

FONT = {"font_name": "Arial", "font_size": 10}
NUMBERS = {"pct": "0.0%;(0.0%);-", "int": "#,##0;(#,##0);-", "usd": "$#,##0;($#,##0);-", "usd2": "$#,##0.00;($#,##0.00);-", "usdm": "$#,##0.0;($#,##0.0);-",
           "bp": "+0.0;-0.0;0.0", "num": "#,##0.00", "day": "mmm d, yyyy", "month": "mmm yyyy"}


def _rows(name: str) -> list[dict]:
    return json.loads((paths.SITE_DATA / f"{name}.json").read_text())["rows"]


def _day(s):
    return date.fromisoformat(s[:10]) if s else None


class _Book:
    def __init__(self, path: Path):
        self.book = xlsxwriter.Workbook(str(path))
        self.book.set_properties({"title": "VantageScore adoption tracker", "comments": "Aggregates from Fannie Mae and Freddie Mac loan-level disclosures."})
        self.book.formats[0].set_font_name("Arial")
        self.book.formats[0].set_font_size(10)
        self._fmt = {}

    def fmt(self, kind="text", **extra):
        key = (kind, tuple(sorted(extra.items())))
        if key not in self._fmt:
            spec = {**FONT, **extra}
            if kind == "wrap":
                spec.update(text_wrap=True, valign="top")
            elif kind in NUMBERS:
                spec["num_format"] = NUMBERS[kind]
                spec.setdefault("align", "right")
            self._fmt[key] = self.book.add_format(spec)
        return self._fmt[key]

    def head(self, **extra):
        return self.fmt("text", bold=True, bottom=1, text_wrap=True, valign="bottom", **extra)

    def sheet(self, name, title, note=None):
        ws = self.book.add_worksheet(name)
        ws.hide_gridlines(2)
        ws.write(0, 0, title, self.fmt("text", bold=True, font_size=13))
        if note:
            ws.write(1, 0, note, self.fmt("text", font_color="#555555"))
        return ws

    def table(self, ws, top, columns, rows):
        """columns: (header, key or function, kind, width). Writes a header at row top, then one row each; returns the next free row."""
        for c, (header, _, kind, width) in enumerate(columns):
            ws.write(top, c, header, self.head(align="right") if kind in NUMBERS else self.head())
            ws.set_column(c, c, width)
        for i, r in enumerate(rows):
            for c, (_, key, kind, _) in enumerate(columns):
                v = key(r) if callable(key) else r.get(key)
                if v is None:
                    continue
                if kind in ("day", "month"):
                    ws.write_datetime(top + 1 + i, c, _day(v), self.fmt(kind))
                elif kind == "link":
                    ws.write_url(top + 1 + i, c, v[1], self.fmt("text", font_color="#0563C1", underline=1), v[0])
                elif kind == "text" or kind == "wrap":
                    ws.write_string(top + 1 + i, c, str(v), self.fmt(kind))
                else:
                    ws.write_number(top + 1 + i, c, v, self.fmt(kind))
        return top + 1 + len(rows)


def _read_me(b: _Book, through: str):
    ws = b.sheet("Read me", "VantageScore adoption tracker: analyst workbook")
    ws.set_column(0, 0, 118)
    lines = [
        (f"Data through {through}. Rebuilt with each refresh from Fannie Mae and Freddie Mac loan-level MBS issuance files. Research in progress, not for distribution.", None),
        ("", None),
        ("Colors", "bold"),
        ("Blue: inputs to change. Black: formulas. Green: links to another sheet. Yellow fill: judgment calls these files cannot test.", None),
        ("", None),
        ("Sheets", "bold"),
        ("FICO exposure: FICO's revenue on GSE loans under your inputs, as live formulas.", None),
        ("Your scenario: each lender's share priced on VS4 and share with no Classic FICO. Its totals feed FICO exposure.", None),
        ("Carrying VS4: the longest timeline. VS4-priced loans by issue month and week, split into both scores and VS4 only once the files show every score, with the same at a frozen lender mix.", None),
        ("By closing month: priced on VS4 and the scores that show, by estimated closing month, for the market at fixed lender weights and for each large lender, with how much of each month has arrived.", None),
        ("Score mix: shows FICO only, shows both (priced either way) and shows VS4 only, by issue month, week of first disclosure and quarter, by GSE.", None),
        ("Lenders: each large lender's stage, rule, score mix, fees and rates, with its ticker. Lender split by week: the same split over time, by GSE.", None),
        ("Cost or rate: what lenders pick when they hold both scores, by what VS4 would do to the fee, and what the pick is worth.", None),
        ("Fees: fee saved, taken, left and estimated from the GSEs' grid; the GSEs' own scores on these loans.", None),
        ("Rates: VS4 note rates against a model of FICO-priced loans, by week and lender, and how much of a lower fee reaches the rate, by lender and channel.", None),
        ("Rules: how often each lender prices on VS4 with its score under and over 20 points above FICO, by week.", None),
        ("VS4 share by month, Loans by month: the largest lenders and every lender with a ticker, both GSEs.", None),
        ("Weekly note, Statements: what changed each week; what companies and others have said, with links.", None),
        ("Whole market, Whole market lenders, Score models: which score lenders named on every kind of loan in the latest HMDA file, which lenders named what, and who uses each model.", None),
        ("", None),
        ("Read these with care", "bold"),
        ("Two things in these files are facts: a score that shows, and the Pricing Indicator saying which score priced the loan. A score that does not show is unknown, not absent. So priced on VS4 is exact, the share showing a score is a floor on loans that have it, and the share showing only one score is a ceiling on loans that have only that one.", None),
        ("Dates: issue month ties to GSE volume and sets the fee grid. Weeks are the earliest news and swing with which lenders delivered. Closing month, the first payment month less two, sits nearest the borrower's application and lock, and its recent months are still arriving. A rate is set at lock, while a lender can pick the score as late as delivery, so rates can lag picks.", None),
        ("Records show every score the GSE has on a loan only from Oct 19, 2026. Figures for loans disclosed with every score rest on those records. Earlier months show only the score that priced the loan.", None),
        ("Lenders deliver one score: the delivery file has a single credit score field. A second score most likely reaches the GSE through underwriting. Neither GSE says this decides which scores show, so it is our reading. VS4 only at Freddie Mac does not mean Classic FICO was not pulled.", None),
        ("A week's figures move with the mix of lenders delivering that week. The seller is not always the lender that made the loan.", None),
        ("The fee grid is Freddie Mac Guide Exhibit 19 (Bulletin 2026-K); Fannie Mae's matrix is taken to match it, unchecked. Fees are what the GSE charges, not what a borrower sees.", None),
        ("The rate model is a comparison of like loans, not a test of cause. Points and lender credits are not disclosed, so a saving can reach the borrower without showing in the note rate.", None),
        ("Until late September the files show only the score that priced a loan, so the earlier part of Carrying VS4 is a floor. Pulls on loans that never fund cannot be seen anywhere in these files.", None),
        ("The exposure calculator is arithmetic on your inputs, not a forecast. It covers loans sold to the GSEs only; FHA accepts VS4 from January 1, 2027.", None),
        ("HMDA is annual and names the model the lender relied on. A named model is a fact; more than one model, other model, not applicable and exempt are unknown, so the shares naming FICO and VantageScore are floors. The buyer is whoever bought the loan that calendar year.", None),
        ("Not affiliated with Fannie Mae, Freddie Mac, FICO or VantageScore Solutions.", None),
    ]
    for i, (text, style) in enumerate(lines):
        ws.write(2 + i, 0, text, b.fmt("text", bold=True) if style else b.fmt("wrap"))


def _scenario_rows() -> tuple[list[dict], float]:
    """As the page's scenario table: each lender with its share with no Classic FICO, read at Fannie Mae where it has enough loans."""
    nf_market = next((r["value"] for r in _rows("assumptions") if r["key"] == "no_fico_fnma"), 0)
    stage = {r["id"]: r for r in _rows("lender_stage") if r.get("view") == "lender"}
    lenders = [r for r in _rows("outlook") if r.get("view") == "lender"]
    lenders.sort(key=lambda r: (r.get("status") == "other", -r["share"]))
    out = []
    for r in lenders:
        s = stage.get(r["id"]) or {}
        nf = s.get("fnma_vs_only")
        out.append({**r, "nf0": (nf if nf is not None else s.get("mix_vs_only")) or 0})
    rest = next((r for r in out if r.get("status") == "other"), None)
    if rest and rest["share"] > 0:
        known = sum(r["share"] * r["nf0"] for r in out if r is not rest)
        rest["nf0"] = max(0, (nf_market - known) / rest["share"])
    return out, nf_market


def _scenario(b: _Book, rows: list[dict]):
    ws = b.sheet("Your scenario", "Your scenario", "Change the blue cells. A lender priced on VS4 can still pull and pay for FICO, as nearly all do today, so the two are separate.")
    top, first = 5, 6
    last = first + len(rows) - 1
    columns = [("Lender", lambda r: "Everyone else" if r.get("status") == "other" else r["short"], "text", 26), ("Ticker", "ticker", "text", 8), ("VS4 use", "status", "text", 10),
               ("Share of loans", "share", "pct", 10), ("VS4 today", "vs4_share", "pct", 10), ("Latest weeks", "recent_share", "pct", 10),
               ("On the rule: saves a fee", "on_better", "pct", 11), ("On the rule: score higher", "on_higher", "pct", 11)]
    b.table(ws, top, columns, rows)
    ws.write(top, 8, "Your VS4", b.head(align="right"))
    ws.write(top, 9, "No FICO today", b.head(align="right"))
    ws.write(top, 10, "Your no FICO", b.head(align="right"))
    ws.set_column(8, 10, 10)
    blue = b.fmt("pct", font_color="#0000FF")
    for i, r in enumerate(rows):
        ws.write_number(first + i, 8, r["vs4_share"], blue)
        ws.write_number(first + i, 9, r["nf0"], b.fmt("pct"))
        ws.write_number(first + i, 10, r["nf0"], blue)
    ws.freeze_panes(first, 1)
    v0 = sum(r["share"] * r["vs4_share"] for r in rows)
    nf0 = sum(r["share"] * r["nf0"] for r in rows)
    bold = b.fmt("pct", bold=True)
    ws.write(3, 0, "All lenders, weighted by share of loans", b.fmt("text", bold=True))
    for col, value in ((4, v0), (8, v0), (9, nf0), (10, nf0)):
        letter = "ABCDEFGHIJK"[col]
        ws.write_formula(3, col, f"=SUMPRODUCT($D${first + 1}:$D${last + 1},{letter}{first + 1}:{letter}{last + 1})", bold, value)
    ws.write_formula(3, 3, f"=SUM(D{first + 1}:D{last + 1})", bold, sum(r["share"] for r in rows))


def _exposure(b: _Book, assumptions: list[dict], nf_market: float, nf_cell: str, nf_scn: float):
    ws = b.sheet("FICO exposure", "FICO's exposure on GSE loans",
                 "FICO is paid for each score pulled, so it loses revenue when a lender stops pulling its score, not when a lender prices on VS4. Arithmetic on your inputs, not a forecast.")
    ws.set_column(0, 0, 58)
    ws.set_column(1, 1, 14)
    ws.set_column(2, 2, 88)
    ws.set_column(3, 3, 24)
    by = {r["key"]: r for r in assumptions}
    place = {}
    row = 3
    kinds = {"usd": "usd2", "usd_m": "usdm", "count": "num"}

    def header(text):
        nonlocal row
        ws.write(row, 0, text, b.fmt("text", bold=True, bottom=1))
        ws.write(row, 1, "", b.fmt("text", bottom=1))
        ws.write(row, 2, "", b.fmt("text", bottom=1))
        ws.write(row, 3, "", b.fmt("text", bottom=1))
        row += 1

    def put(key, label=None, value=None, note=None, kind=None, flag=False, url=None, source=None):
        nonlocal row
        r = by.get(key)
        label = label or r["label"]
        value = r["value"] if value is None else value
        note = note if note is not None else r["note"]
        extra = {"bg_color": "#FFFF00"} if flag or (r and r["kind"] == "judgment") else {}
        ws.write(row, 0, label, b.fmt("text"))
        ws.write_number(row, 1, value, b.fmt(kind or kinds.get(r["unit"], "num"), font_color="#0000FF", **extra))
        ws.write(row, 2, note or "", b.fmt("wrap"))
        src, link = source or (r and r["source"]), url or (r and r["url"])
        if link:
            ws.write_url(row, 3, link, b.fmt("text", font_color="#0563C1", underline=1), src or "Source")
        place[key] = f"$B${row + 1}"
        row += 1

    header("The market")
    put("gse_loans_year", kind="int")
    put("borrowers_per_loan")
    put("bureaus")
    put("pulls_per_loan")
    row += 1
    header("FICO's price")
    put("price_per_score")
    put("closing_fee")
    put("vs_price")
    row += 1
    header("FICO's reported revenue")
    put("fico_mortgage_q")
    put("fico_revenue_year")
    row += 1
    header("Loans with no Classic FICO")
    put("no_fico_today", "Today, at Fannie Mae", nf_market, "Some lenders show fewer of their scores at Freddie Mac, so Fannie Mae is the cleaner read.", "pct")
    ws.write(row, 0, "Your scenario", b.fmt("text"))
    ws.write_formula(row, 1, f"={nf_cell}", b.fmt("pct", font_color="#008000"), nf_scn)
    ws.write(row, 2, "From the Your scenario sheet.", b.fmt("wrap"))
    place["no_fico_scn"] = f"$B${row + 1}"
    row += 2
    header("Your scenario, beyond the lender table")
    put("scn_pulls", "FICO pulls per funded loan", by["pulls_per_loan"]["value"], "A lender can keep FICO for the loan it delivers and pull VantageScore earlier. These files cannot show that.", "num", True)
    put("scn_price", "FICO price per score", by["price_per_score"]["value"], "Price can outrun lost units, as FICO's latest quarter shows.", "usd2")
    row += 1
    header("Results")
    a = {k: by[k]["value"] for k in ("gse_loans_year", "borrowers_per_loan", "bureaus", "pulls_per_loan", "price_per_score", "closing_fee", "vs_price", "fico_mortgage_q", "fico_revenue_year")}
    scores = a["bureaus"] * a["borrowers_per_loan"]
    per_today = scores * (a["pulls_per_loan"] * a["price_per_score"] + a["closing_fee"])
    per_scn = per_today
    rev_today = a["gse_loans_year"] * (1 - nf_market) * per_today / 1e6
    rev_scn = a["gse_loans_year"] * (1 - nf_scn) * per_scn / 1e6
    p = place

    def result(key, label, formula, value, kind, note=""):
        nonlocal row
        ws.write(row, 0, label, b.fmt("text"))
        ws.write_formula(row, 1, "=" + formula, b.fmt(kind), value)
        ws.write(row, 2, note, b.fmt("wrap"))
        place[key] = f"$B${row + 1}"
        row += 1

    result("scores", "Scores per credit pull", f"{p['bureaus']}*{p['borrowers_per_loan']}", scores, "num", "Bureaus times borrowers.")
    result("per_today", "FICO's revenue per funded loan, today ($)", f"{p['scores']}*({p['pulls_per_loan']}*{p['price_per_score']}+{p['closing_fee']})", per_today, "usd2")
    result("rev_today", "FICO's revenue on GSE loans, today ($m)", f"{p['gse_loans_year']}*(1-{p['no_fico_today']})*{p['per_today']}/1000000", rev_today, "usdm")
    result("per_scn", "FICO's revenue per funded loan, your scenario ($)", f"{p['scores']}*({p['scn_pulls']}*{p['scn_price']}+{p['closing_fee']})", per_scn, "usd2")
    result("rev_scn", "FICO's revenue on GSE loans, your scenario ($m)", f"{p['gse_loans_year']}*(1-{p['no_fico_scn']})*{p['per_scn']}/1000000", rev_scn, "usdm")
    result("change", "The change ($m)", f"{p['rev_scn']}-{p['rev_today']}", rev_scn - rev_today, "usdm")
    result("of_company", "The change, as a share of FICO's revenue", f"{p['change']}/{p['fico_revenue_year']}", (rev_scn - rev_today) / a["fico_revenue_year"], "pct")
    yearly = a["fico_mortgage_q"] * 4
    result("of_mortgage", "The change, as a share of mortgage revenue at the latest quarter's pace", f"{p['change']}/({p['fico_mortgage_q']}*4)", (rev_scn - rev_today) / yearly, "pct")
    result("point", "Each point of GSE loans with no FICO ($m a year)", f"{p['gse_loans_year']}*0.01*{p['per_today']}/1000000", a["gse_loans_year"] * 0.01 * per_today / 1e6, "usdm")
    offset = max(rev_today / rev_scn - 1, 0) if rev_scn > 0 else "n/a"
    result("offset", "Price rise that would offset it", f'IF({p["rev_scn"]}>0,MAX({p["rev_today"]}/{p["rev_scn"]}-1,0),"n/a")', offset, "pct")
    saving = scores * (a["pulls_per_loan"] * (a["price_per_score"] - a["vs_price"]) + a["closing_fee"])
    result("saving", "A lender's saving per funded loan if it drops FICO ($)", f"{p['scores']}*({p['pulls_per_loan']}*({p['price_per_score']}-{p['vs_price']})+{p['closing_fee']})", saving, "usd2",
           "At these prices, before what the bureaus add. The upfront fee is on the Fees sheet.")
    result("check", "Check: GSE loans as a share of FICO's mortgage revenue at the latest quarter's pace", f"{p['rev_today']}/({p['fico_mortgage_q']}*4)", rev_today / yearly, "pct",
           "GSE loans are only part of mortgage lending, so this should sit well under 100%.")


def _score_mix(b: _Book):
    ws = b.sheet("Score mix", "Which scores the loans carry", "Records that carry the Pricing Indicator. Weeks by first disclosure. Quarters without every score show only the score that priced the loan.")
    label = {"month": "Issue month", "week": "Week", "quarter": "Quarter"}
    gse = {"All": "Both GSEs", "FNMA": "Fannie Mae", "FHLMC": "Freddie Mac"}
    rows = [r for r in _rows("score_mix") if r["view"] in label]
    rows.sort(key=lambda r: (list(label).index(r["view"]), r["start"], list(gse).index(r["agency"])))
    columns = [("Period", lambda r: label[r["view"]], "text", 11), ("From", "start", "day", 12), ("GSE", lambda r: gse[r["agency"]], "text", 12), ("Loans", "loans", "int", 10),
               ("Shows FICO only", "fico_only_share", "pct", 9), ("Both, priced on FICO", "both_fico_share", "pct", 10), ("Both, priced on VS4", "both_vs_share", "pct", 10), ("Shows VS4 only", "vs_only_share", "pct", 9),
               ("Shows Classic FICO (floor)", "fico_share", "pct", 10), ("Shows VS4 (floor)", "vs_share", "pct", 10), ("Priced on VS4", "vs4_priced_share", "pct", 10),
               ("Priced on VS4, by balance", "vs4_priced_upb_share", "pct", 10), ("Complete", lambda r: "Yes" if r.get("complete") else "So far" if r["view"] == "quarter" else None, "text", 9)]
    b.table(ws, 3, columns, rows)
    ws.freeze_panes(4, 0)
    ws.autofilter(3, 0, 3 + len(rows), len(columns) - 1)


def _lenders(b: _Book):
    ws = b.sheet("Lenders", "Lender by lender", "The 60 largest and every other lender past the first stages. Loans disclosed with every score, both GSEs unless named. Fees from the latest full-enough month.")
    fees = {r["id"]: r for r in _rows("fees") if r.get("view") == "lender"}
    pricing = _rows("pricing")
    rate = {r["key"]: r for r in pricing if r.get("view") == "seller" and r.get("cover") == "all" and r.get("basis") == "headline"}
    value = {(r["scope"], r["key"]): r for r in pricing if r.get("view") == "value"}
    outlook = {r["id"]: r for r in _rows("outlook") if r.get("view") == "lender"}
    rows = sorted((r for r in _rows("lender_stage") if r.get("view") == "lender"), key=lambda r: r["rank"])
    fee = lambda f: (lambda r: (fees.get(r["id"]) or {}).get(f))  # noqa: E731
    out = lambda f: (lambda r: (outlook.get(r["id"]) or {}).get(f))  # noqa: E731
    enough = lambda d, f: d[f] if d and d.get("n", 0) >= 100 else None  # noqa: E731
    columns = [("Lender", "short", "text", 24), ("Ticker", "ticker", "text", 7), ("Type", "kind", "text", 10), ("Main channel", "lead", "text", 12), ("Rank", "rank", "int", 6), ("Loans", "loans", "int", 8),
               ("Share of loans", "share", "pct", 8), ("Stage", "stage", "text", 8), ("Rule", "rule", "text", 9),
               ("Shows FICO only", "mix_fico_only", "pct", 8), ("Both, on FICO", "mix_both_fico", "pct", 8), ("Both, on VS4", "mix_both_vs", "pct", 8), ("Shows VS4 only", "mix_vs_only", "pct", 8),
               ("Fannie: shows FICO only", "fnma_fico_only", "pct", 8), ("Fannie: both, on FICO", "fnma_both_fico", "pct", 8), ("Fannie: both, on VS4", "fnma_both_vs", "pct", 8), ("Fannie: shows VS4 only", "fnma_vs_only", "pct", 8),
               ("Freddie: shows FICO only", "fhlmc_fico_only", "pct", 8), ("Freddie: both, on FICO", "fhlmc_both_fico", "pct", 8), ("Freddie: both, on VS4", "fhlmc_both_vs", "pct", 8), ("Freddie: shows VS4 only", "fhlmc_vs_only", "pct", 8),
               ("Priced on VS4", "vs4_share", "pct", 8), ("Latest weeks", "recent_share", "pct", 8), ("Uses VS4 when higher", "uses_higher", "pct", 8),
               ("Under 20 pts, earlier", "below_early", "pct", 8), ("Under 20 pts, latest", "below_late", "pct", 8), ("20+ pts", "above", "pct", 8), ("Both, earlier", "both_early", "pct", 8), ("Both, latest", "both_late", "pct", 8),
               ("On the rule: saves a fee", out("on_better"), "pct", 8), ("On the rule: score higher", out("on_higher"), "pct", 8),
               ("VS4-priced, both scores", fee("priced_loans"), "int", 8), ("Saves a fee", fee("saving_share"), "pct", 8), ("Saved per loan ($)", fee("saving_avg_usd"), "usd", 8),
               ("Fees taken ($m)", lambda r: _m(fee("taken_usd")(r)), "usdm", 8), ("Fees left ($m)", lambda r: _m(fee("left_usd")(r)), "usdm", 8), ("Fees estimated ($m)", lambda r: _m(fee("est_usd")(r)), "usdm", 8), ("Potential (bp)", fee("option_bp"), "num", 8),
               ("Rate vs model (bp)", lambda r: (rate.get(r["id"]) or {}).get("net_bp"), "bp", 8), ("Rate: VS4 loans", lambda r: (rate.get(r["id"]) or {}).get("n"), "int", 8),
               ("Lower fee reaches the rate", lambda r: enough(value.get((r["id"], "better")), "reaches_fee"), "pct", 8), ("Same fee, vs own FICO loans (bp)", lambda r: enough(value.get((r["id"], "same")), "net_bp"), "bp", 8)]
    b.table(ws, 3, columns, rows)
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 3 + len(rows), len(columns) - 1)


def _m(v):
    return None if v is None else v / 1e6


def _fees(b: _Book):
    ws = b.sheet("Fees", "What the fee grid is worth", "Freddie Mac Guide Exhibit 19, taken to match Fannie Mae's matrix. Fees the GSE charges, not what a borrower sees. A year's figures scale the month's to the GSE's balance.")
    rows = _rows("fees")
    gse = {"All": "Both GSEs", "FNMA": "Fannie Mae", "FHLMC": "Freddie Mac"}
    market = [r for r in rows if r["view"] == "market"]
    columns = [("GSE", lambda r: gse.get(r["key"], r["key"]), "text", 26), ("Month", "month", "month", 10), ("Loans", "loans", "int", 9), ("Balance ($m)", lambda r: _m(r["upb"]), "usdm", 11),
               ("VS4-priced, both scores", "priced_loans", "int", 9), ("Saves a fee", "saving_share", "pct", 8), ("Saved (bp of balance)", "saved_bp", "num", 9), ("Saved per loan ($)", "saving_avg_usd", "usd", 9),
               ("Taken, grossed up ($m)", lambda r: _m(r["taken_all_usd"]), "usdm", 9), ("Left ($m)", lambda r: _m(r["left_usd"]), "usdm", 9), ("Estimated ($m)", lambda r: _m(r["est_usd"]), "usdm", 9),
               ("Potential ($m)", lambda r: _m(r["option_usd"]), "usdm", 9), ("Potential (bp)", "option_bp", "num", 9), ("Balance a year ($m)", lambda r: _m(r.get("annual_upb")), "usdm", 11),
               ("Taken, a year ($m)", lambda r: _m(r.get("taken_annual_usd")), "usdm", 9), ("Potential, a year ($m)", lambda r: _m(r.get("option_annual_usd")), "usdm", 9)]
    next_row = b.table(ws, 3, columns, market)
    ws.write(next_row + 1, 0, "The GSEs' own scores, in points", b.fmt("text", bold=True))
    ws.write(next_row + 2, 0, "VS4-priced minus FICO-priced in the same fee bucket, same lender and GSE. Last rows: better VS4 bucket minus same bucket, at the same Classic FICO.", b.fmt("text", font_color="#555555"))
    scores = [r for r in rows if r["view"] in ("gse", "lift")]
    scores.sort(key=lambda r: (r["view"], r.get("scope") or "", r["key"]))
    b.table(ws, next_row + 3, [("Fee bucket", lambda r: r["label"], "text", 26), ("Scope", lambda r: "Better VS4, same FICO" if r["view"] == "lift" else r.get("scope_label"), "text", 10), ("Points", "diff", "bp", 9), ("Loans", "loans", "int", 9)], scores)


def _carrying(b: _Book):
    ws = b.sheet("Carrying VS4", "Loans carrying VS4, the longest timeline", "Until late September the files show only the score that priced a loan: those rows are a floor, with the split blank. Weeks by first disclosure, and they swing with which lenders delivered.")
    gse = {"All": "Both GSEs", "FNMA": "Fannie Mae", "FHLMC": "Freddie Mac"}
    mix = _rows("score_mix")
    head = next((r["start"] for r in mix if r["view"] == "month" and r["agency"] == "All" and r.get("headline")), None)
    rows = []
    for agency in gse:
        months = [r for r in mix if r["view"] == "month" and r["agency"] == agency and head and r["start"] <= head]
        first = min((r["start"] for r in months), default=None)
        rows += [{"period": "Issue month", "start": r["month"], "agency": agency, "loans": r["scored_loans"], "priced": r["vs4_share"]} for r in _rows("monthly")
                 if r["agency"] == agency and r["month"] >= MONTHS_FROM and (not first or r["month"] < first)]
        weeks = [r for r in mix if r["view"] == "week" and r["agency"] == agency]
        first_w = min((r["start"] for r in weeks), default=None)
        split = lambda r, period: {"period": period, "start": r["start"], "agency": r["agency"], "loans": r["loans"], "priced": r["vs4_priced_share"], "both_vs": r["both_vs_share"], "vs_only": r["vs_only_share"],  # noqa: E731
                                   "both_fico": r["both_fico_share"], "carrying": r["vs_share"], "steady_carrying": r.get("steady_carrying"), "steady_priced": r.get("steady_priced")}
        rows += [split(r, "Issue month") for r in months]
        rows += [{"period": "Week", "start": r["week"], "agency": agency, "loans": r["scored_loans"], "priced": r["vs4_share"]} for r in _rows("weekly") if r["agency"] == agency and (not first_w or r["week"] < first_w)]
        rows += [split(r, "Week") for r in weeks]
    rows.sort(key=lambda r: (r["period"] != "Issue month", list(gse).index(r["agency"]), r["start"]))
    columns = [("Period", "period", "text", 12), ("From", "start", "day", 12), ("GSE", lambda r: gse[r["agency"]], "text", 12), ("Loans", "loans", "int", 10), ("Priced on VS4", "priced", "pct", 9), ("Both, on VS4", "both_vs", "pct", 9), ("Shows VS4 only", "vs_only", "pct", 9),
               ("Both, on FICO", "both_fico", "pct", 9), ("Carrying VS4", "carrying", "pct", 9), ("Carrying, lender mix frozen", "steady_carrying", "pct", 10), ("Priced on VS4, lender mix frozen", "steady_priced", "pct", 10)]
    b.table(ws, 3, columns, rows)
    ws.freeze_panes(4, 0)
    ws.autofilter(3, 0, 3 + len(rows), len(columns) - 1)


def _closing(b: _Book):
    ws = b.sheet("By closing month", "Priced on VS4 and the scores that show, by estimated closing month", "Closing month: the first payment month less two. The market rows keep each lender at a fixed weight, since recent months otherwise hold mostly the fastest deliverers. Arrived estimates how much of the month's loans are in so far. Shows VS4 is a floor on loans that have it, from records that show every score, and is blank unless those hold 20 or more loans and at least half the month's.")
    gse = {"All": "Both GSEs", "FNMA": "Fannie Mae", "FHLMC": "Freddie Mac"}
    names = {r["id"]: r for r in _rows("lender_stage") if r.get("view") == "lender"}
    rows = []
    for r in _rows("closing"):
        if r["start"] < MONTHS_FROM:
            continue
        if r["view"] == "market":
            rows.append({"rank": 0, "lender": "All lenders, fixed weights", "ticker": None, "agency": r["agency"], "start": r["start"], "n": r["n"], "priced": r["priced"], "every": r["every_share"], "shows": r["both_fico"] + r["both_vs"] + r["vs_only"] if r["every_share"] >= 0.5 else None,
                         "only": r["vs_only"] if r["every_share"] >= 0.5 else None, "arrived": r["arrived"]})
        elif r["id"] in names and r["n"] >= 20:
            enough = r["every"] >= 20 and r["every"] / r["n"] >= 0.5
            rows.append({"rank": names[r["id"]]["rank"], "lender": names[r["id"]]["short"], "ticker": names[r["id"]]["ticker"], "agency": r["agency"], "start": r["start"], "n": r["n"], "priced": r["v"] / r["n"], "every": r["every"] / r["n"],
                         "shows": (r["bf"] + r["bv"] + r["vo"]) / r["every"] if enough else None, "only": r["vo"] / r["every"] if enough else None, "arrived": r["arrived"]})
    rows.sort(key=lambda r: (r["rank"], list(gse).index(r["agency"]), r["start"]))
    columns = [("Lender", "lender", "text", 26), ("Ticker", "ticker", "text", 7), ("GSE", lambda r: gse[r["agency"]], "text", 12), ("Closing month", "start", "day", 12), ("Loans so far", "n", "int", 9), ("Priced on VS4 (exact)", "priced", "pct", 10),
               ("Shows VS4 (floor)", "shows", "pct", 9), ("Shows VS4 only (ceiling)", "only", "pct", 9), ("In records with every score", "every", "pct", 10), ("Arrived, estimated", "arrived", "pct", 9)]
    b.table(ws, 3, columns, rows)
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 3 + len(rows), len(columns) - 1)


def _lender_split(b: _Book):
    ws = b.sheet("Lender split by week", "Each lender's split, by week first disclosed and issue month", "Share of its loans, for the 60 largest lenders and every other lender past the first stages, with 20 or more loans in the period.")
    gse = {"All": "Both GSEs", "FNMA": "Fannie Mae", "FHLMC": "Freddie Mac"}
    names = {r["id"]: r for r in _rows("lender_stage") if r.get("view") == "lender"}
    rows = [r for r in _rows("lender_mix") if r["n"] >= 20 and r["id"] in names]
    rows.sort(key=lambda r: (names[r["id"]]["rank"], r["view"] != "week", list(gse).index(r["agency"]), r["start"]))
    columns = [("Lender", lambda r: names[r["id"]]["short"], "text", 24), ("Ticker", lambda r: names[r["id"]]["ticker"], "text", 7), ("GSE", lambda r: gse[r["agency"]], "text", 12), ("Period", lambda r: "Week" if r["view"] == "week" else "Issue month", "text", 11), ("From", "start", "day", 12),
               ("Loans", "n", "int", 8), ("Shows FICO only", lambda r: r["fo"] / r["n"], "pct", 8), ("Both, on FICO", lambda r: r["bf"] / r["n"], "pct", 8), ("Both, on VS4", lambda r: r["bv"] / r["n"], "pct", 8), ("Shows VS4 only", lambda r: r["vo"] / r["n"], "pct", 8),
               ("Carrying VS4", lambda r: (r["bf"] + r["bv"] + r["vo"]) / r["n"], "pct", 8)]
    b.table(ws, 3, columns, rows)
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 3 + len(rows), len(columns) - 1)


COST_ROWS = [("lower|up20", "VS4's fee lower, its score 20+ points higher"), ("lower|up1", "VS4's fee lower, its score 1-19 points higher"), ("same|up20", "Same fee, VS4 20+ points higher"), ("same|up1", "Same fee, VS4 1-19 points higher"),
             ("same|equal", "Same fee, same score"), ("same|down1", "Same fee, VS4 1-19 points lower"), ("same|down20", "Same fee, VS4 20+ points lower"), ("higher|all", "VS4's fee higher")]


def _cost(b: _Book):
    ws = b.sheet("Cost or rate", "What lenders pick when they hold both scores", "Share priced on VS4, loans with both scores issued on the one fee grid. Blank under 20 loans. Pulls on loans that never fund cannot be seen.")
    rows = [r for r in _rows("fees") if r.get("view") == "choice"]
    scopes = list(dict.fromkeys(r["scope"] for r in sorted(rows, key=lambda r: r["scope_rank"])))
    labels = {r["scope"]: r["scope_label"] for r in rows}
    cells = {(r["cohort"], r["scope"], r["key"]): r for r in rows}
    row = 3
    for cohort, title in (("all", "All weeks"), ("latest", "Latest two weeks")):
        ws.write(row, 0, title, b.fmt("text", bold=True))
        row += 1
        columns = [("What VS4 would do", lambda k: k[1], "text", 44), ("Loans", lambda k: (cells.get((cohort, "All", k[0])) or {}).get("loans"), "int", 9)]
        for s in scopes:
            columns.append((labels[s], (lambda k, s=s: (cells[(cohort, s, k[0])]["vs4_share"] if (cohort, s, k[0]) in cells and cells[(cohort, s, k[0])]["loans"] >= 20 else None)), "pct", 11))
        row = b.table(ws, row, columns, COST_ROWS) + 1
    options = sorted((r for r in _rows("fees") if r.get("view") == "option"), key=lambda r: r["scope_rank"])
    ws.write(row, 0, "What the pick is worth: the upfront fee as bp of balance", b.fmt("text", bold=True))
    row += 1
    heads = ["Lender", "Loans", "All on FICO", "All on VS4", "Lower of the two", "As priced", "Average loan ($)", "Taken", "Picking saves, per loan ($)", "Dropping FICO gives up, per loan ($)"]
    for c, h in enumerate(heads):
        ws.write(row, c, h, b.head() if c == 0 else b.head(align="right"))
    for i, r in enumerate(options):
        at = row + 1 + i
        n = at + 1
        ws.write_string(at, 0, r["scope_label"], b.fmt("text"))
        ws.write_number(at, 1, r["loans"], b.fmt("int"))
        for c, f in ((2, "fee_fico_bp"), (3, "fee_vs_bp"), (4, "fee_best_bp"), (5, "fee_actual_bp")):
            ws.write_number(at, c, r[f], b.fmt("num"))
        ws.write_number(at, 6, r["avg_upb"], b.fmt("usd"))
        room = r["fee_fico_bp"] - r["fee_best_bp"]
        ws.write_formula(at, 7, f'=IF((C{n}-E{n})>0,(C{n}-F{n})/(C{n}-E{n}),"n/a")', b.fmt("pct"), (r["fee_fico_bp"] - r["fee_actual_bp"]) / room if room > 0 else "n/a")
        ws.write_formula(at, 8, f"=(C{n}-E{n})*G{n}/10000", b.fmt("usd"), room * r["avg_upb"] / 1e4)
        ws.write_formula(at, 9, f"=(D{n}-E{n})*G{n}/10000", b.fmt("usd"), (r["fee_vs_bp"] - r["fee_best_bp"]) * r["avg_upb"] / 1e4)


def _rates(b: _Book):
    ws = b.sheet("Rates", "VS4 note rates against the FICO model", "30-year fixed. Positive means VS4 borrowers pay more than the model gives like FICO loans, net of the model's miss on held-out FICO loans. Points and lender credits are not disclosed.")
    rows = _rows("pricing")
    week = sorted((r for r in rows if r["view"] == "week" and r["cover"] == "all" and r["basis"] == "headline"), key=lambda r: r["key"])
    columns = [("Week of first disclosure", "key", "day", 26), ("VS4 loans", "n", "int", 10), ("Rate vs model (bp)", "net_bp", "bp", 10), ("Before netting (bp)", "premium_bp", "bp", 10), ("Standard error (bp)", "se_bp", "num", 10), ("Held-out FICO loans (bp)", "check_bp", "bp", 10)]
    n = b.table(ws, 3, columns, week)
    ws.write(n + 1, 0, "By lender", b.fmt("text", bold=True))
    seller = sorted((r for r in rows if r["view"] == "seller" and r["cover"] == "all" and r["basis"] == "headline"), key=lambda r: -r["n"])
    n = b.table(ws, n + 2, [("Lender", "label", "text", 26), ("VS4 loans", "n", "int", 10), ("Rate vs model (bp)", "net_bp", "bp", 10), ("Before netting (bp)", "premium_bp", "bp", 10), ("Standard error (bp)", "se_bp", "num", 10), ("Held-out FICO loans (bp)", "check_bp", "bp", 10)], seller)
    ws.write(n + 1, 0, "How much of a lower fee reaches the rate", b.fmt("text", bold=True))
    ws.write(n + 2, 0, "Against the lender and channel's own FICO-priced loans with both scores, loans on the one grid. better: VS4's fee lower. to25 to over100: by fee saved. same: same fee. fico_better: priced on FICO though VS4's fee was lower.", b.fmt("text", font_color="#555555"))
    value = sorted((r for r in rows if r["view"] == "value"), key=lambda r: (r.get("scope_rank") or 0, r.get("order") or 0))
    b.table(ws, n + 3, [("Lender", "label", "text", 26), ("Loans", "n", "int", 10), ("Group", "key", "text", 10), ("Fee saved (bp)", "fee_bp", "num", 10), ("At 5 to 1 (bp)", "fee_rate_bp", "num", 10),
                        ("Rate vs own FICO loans (bp)", "net_bp", "bp", 10), ("Standard error (bp)", "se_bp", "num", 10), ("Reaches the rate", "reaches_fee", "pct", 10)], value)


def _rules(b: _Book):
    ws = b.sheet("Rules", "How often each lender prices on VS4, by week", "Loans with both scores unless noted. Under 20: VS4 1 to 19 points above FICO. Over 20: 20 or more. Both GSEs.")
    rows = sorted((r for r in _rows("rules") if r["view"] == "week" and r["agency"] == "All"), key=lambda r: (r["scope"] != "All", r["scope_label"], r["week"]))
    columns = [("Lender", "scope_label", "text", 26), ("Week", "week", "day", 12), ("Loans", "loans", "int", 9), ("Both scores", "both_share", "pct", 9), ("Priced on VS4", "vs4_share", "pct", 9),
               ("Under 20: loans", "under20_loans", "int", 9), ("Under 20: on VS4", "under20_share", "pct", 9), ("Over 20: loans", "over20_loans", "int", 9), ("Over 20: on VS4", "over20_share", "pct", 9)]
    b.table(ws, 3, columns, rows)
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 3 + len(rows), len(columns) - 1)


def _by_month(b: _Book):
    sellers = [r for r in _rows("sellers") if r["level"] == "seller"]
    keep = sorted((r for r in sellers if r["rank"] <= TOP_SELLERS or r["ticker"]), key=lambda r: r["rank"])
    monthly = {}
    months = set()
    for r in _rows("seller_monthly"):
        if r["level"] == "seller" and r["agency"] == "All" and r["month"] >= MONTHS_FROM:
            monthly[(r["id"], r["month"])] = r
            months.add(r["month"])
    months = sorted(months)
    for name, title, field, kind in (("VS4 share by month", "VS4's share of each lender's loans, by issue month", "vs4_share", "pct"), ("Loans by month", "Loans with a credit score, by issue month", "scored", "int")):
        ws = b.sheet(name, title, "Both GSEs. The latest month is partial until its month-end file arrives.")
        columns = [("Lender", "short", "text", 26), ("Ticker", "ticker", "text", 8)]
        columns += [(_day(m).strftime("%b %Y"), (lambda r, m=m: (monthly.get((r["id"], m)) or {}).get(field)), kind, 9) for m in months]
        b.table(ws, 3, columns, keep)
        ws.freeze_panes(4, 1)


def _notes(b: _Book):
    ws = b.sheet("Weekly note", "What changed each week", "Loans by the week they first appeared in an intraday file, each week against the one before it.")
    rows = _rows("week_note")
    labels = {r["week"]: f"{r['label']}{', so far' if r['partial'] else ''}" for r in rows if r["view"] == "week"}
    lines = sorted((r for r in rows if r["view"] == "line"), key=lambda r: (-int(r["week"].replace("-", "")), r["order"]))
    n = b.table(ws, 3, [("Week", lambda r: labels[r["week"]], "text", 22), ("What", "kind", "text", 8), ("Line", "text", "wrap", 110), ("Source", lambda r: (r["source"] or "Source", r["url"]) if r["url"] else None, "link", 26)], lines)
    return n


def _statements(b: _Book):
    ws = b.sheet("Statements", "What companies and others have said", "Paraphrased from the linked sources.")
    rows = sorted(_rows("statements"), key=lambda r: r["date"], reverse=True)
    b.table(ws, 3, [("Date", "date", "day", 12), ("Who", "who", "text", 22), ("Statement", "statement", "wrap", 110), ("Source", lambda r: (r["source"] or "Source", r["url"]) if r["url"] else None, "link", 28)], rows)


def _whole_market(b: _Book):
    rows = _rows("whole_market")
    meta = next((r for r in rows if r["view"] == "meta"), None)
    if not meta:
        return
    shares = [("Classic FICO", "classic", "pct", 9), ("Newer FICO", "fico_new", "pct", 9), ("VS4", "vs4", "pct", 9), ("VantageScore 2.0, 3.0", "vs_old", "pct", 11), ("More than one model", "multi", "pct", 10), ("Other model", "other", "pct", 9), ("No score reported", "none", "pct", 9)]
    ws = b.sheet("Whole market", f"Which score lenders named on loans made in {meta['year']}, from HMDA", "A named model is a fact and the rest is unknown, so what is named is a floor. Each loan counts once; multifamily and reverse mortgages are left out.")
    next_row = b.table(ws, 3, [("Kind of loan", "label", "text", 44), ("Loans", "n", "int", 11), ("$bn", "usd_bn", "usdm", 10), *shares], sorted((r for r in rows if r["view"] == "segment"), key=lambda r: r["order"]))
    ws.write(next_row + 1, 0, "Applications taken for each loan made, funded or not", b.fmt("text", bold=True))
    b.table(ws, next_row + 2, [("Kind of loan", "label", "text", 44), ("Loans", "n", "int", 11), ("Applications", "apps", "int", 10), ("Per loan", "per_loan", "num", 9)], [r for r in rows if r["view"] == "apps"])
    ws = b.sheet("Whole market lenders", f"Which score each lender named on loans made in {meta['year']}, from HMDA", "The biggest lenders in each group. Names as filed; a lender's record covers the loans it made.")
    groups = {"all": "Biggest", "first": "Biggest in first-lien", "equity": "Biggest in home equity", "vs": "Most VantageScore", "fico_new": "Most newer FICO"}
    lenders = sorted((r for r in rows if r["view"] == "lender"), key=lambda r: (list(groups).index(r["scope"]), r["rank"]))
    b.table(ws, 3, [("Group", lambda r: groups[r["scope"]], "text", 22), ("Rank", "rank", "int", 6), ("Lender", "name", "text", 34), ("Loans", "n", "int", 10), ("In home equity", "equity_share", "pct", 9), *shares], lenders)
    ws = b.sheet("Score models", f"Who used each score model on loans made in {meta['year']}, from HMDA", "A loan counts under each model it names.")
    b.table(ws, 3, [("Model named", "name", "text", 28), ("Loans", "n", "int", 11), ("In home equity", "equity_share", "pct", 9), ("Biggest users", "users", "text", 90)], [r for r in rows if r["view"] == "model"])


def build_workbook() -> Path:
    summary = next((r for r in _rows("summary") if r["agency"] == "All"), {})
    through = str(summary.get("data_through") or date.today().isoformat())[:10]
    EXPORTS.mkdir(parents=True, exist_ok=True)
    path = EXPORTS / f"vs4-tracker-{through}.xlsx"
    b = _Book(path)
    _read_me(b, through)
    rows, nf_market = _scenario_rows()
    nf0 = sum(r["share"] * r["nf0"] for r in rows)
    _exposure(b, _rows("assumptions"), nf_market, SCENARIO_NO_FICO, nf0)  # first in the book; reads the scenario's totals, whose place is fixed
    _scenario(b, rows)
    _carrying(b)
    _closing(b)
    _score_mix(b)
    _lenders(b)
    _lender_split(b)
    _cost(b)
    _fees(b)
    _rates(b)
    _rules(b)
    _by_month(b)
    _whole_market(b)
    _notes(b)
    _statements(b)
    b.book.close()
    return path
