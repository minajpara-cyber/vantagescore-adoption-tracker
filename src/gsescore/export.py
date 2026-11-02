"""The analyst workbook: exports/vs4-tracker-<data through>.xlsx, from the datasets in site/data.

The tables a covering analyst would pull into a model, the weekly note, the statements with links, and the FICO exposure calculator with
your scenario as live formulas. Blue cells are inputs, black are figures from the data and formulas, green are links to another sheet, and yellow
marks the judgment calls. It holds findings, so exports/ is git-ignored and it goes no further than this computer unless the user sends it on.
"""
import json
from datetime import date
from pathlib import Path

import xlsxwriter

from . import paths
from .pricing import ANNOUNCED, RARE_BESIDE, RARE_CHANNEL, SCORE_CUTS, THIN_WEEKS

EXPORTS = paths.ROOT / "exports"
MONTHS_FROM = "2026-04-01"
TOP_SELLERS = 60
FEE_LENDER_MIN = 20  # VS4-priced loans with both scores a lender needs for a row on Fees, as on the page's table
SCENARIO_NO_FICO = "'Your scenario'!J4"

FONT = {"font_name": "Arial", "font_size": 10}
NUMBERS = {"pct": "0.0%;(0.0%);-", "int": "#,##0;(#,##0);-", "usd": "$#,##0;($#,##0);-", "usd2": "$#,##0.00;($#,##0.00);-", "usdm": "$#,##0.0;($#,##0.0);-",
           "bp": "+0.0;-0.0;0.0", "bp2": "+0.00;-0.00;0.00", "num": "#,##0.00", "whole": "0", "day": "mmm d, yyyy", "month": "mmm yyyy"}
RATE_READS = (("same_fico", "Same FICO"), ("same_llpa", "Same FICO, same LLPA"), ("same_number", "Same score number under 820"))
# The engine's sentences are written beside the page's charts. On the Rates sheet the same figures sit in named columns, so these phrases change there; the numbers stay as the engine wrote them.
SHEET_WORDS = (("The dot is the midpoint of the first two and the bar the range across all three.", "The estimate is the midpoint of the first two, and low and high the range across all three."),
               ("The thin line: it resamples", "95% low and 95% high: this range resamples"),
               ("The thin line", "95% low and 95% high"),
               ("Each test below stops short", "Each test on this sheet stops short"),
               ("so this row", f"so the lead table's row for FICO under {SCORE_CUTS[-1]}"),
               ("The two lines", "The two groups"),
               ("whose bar shows", "whose low and high show"))
BAND_FLAGS = {"unsettled": "Unsettled: the 3 methods sit 3+ bp apart", "no_like_fico": "Almost no comparable FICO loans at its number", "few_like_fico": "Few comparable FICO loans at its number"}
UNDER_TABLES = ("selected", "rebuilt", "line", "past", "book", "left_out", "grid", "ranges")  # limits printed beside what they speak of, not in the list of limits: the first under the answer, the second beside the date, the next three under their tables, the rest under the stamp
FLOOR = "Blank under 100 matched loans on either exact match."  # the engine's floor on a figure; the row's counts stay
FIRM_IN = 0.5  # under this share of its closing month in so far, a month's row is rough, as the page draws it hollow


def _rows(name: str) -> list[dict]:
    return json.loads((paths.SITE_DATA / f"{name}.json").read_text())["rows"]


def _day(s):
    return date.fromisoformat(s[:10]) if s else None


def _sheet_words(text):
    for chart, sheet in SHEET_WORDS:
        text = text.replace(chart, sheet)
    return text


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
            elif kind == "flag":
                spec["align"] = "center"
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
        """columns: (header, key or function, kind, width); a kind that is a function picks a number's format row by row. Writes a header at row top, then one row each; returns the next free row."""
        for c, (header, _, kind, width) in enumerate(columns):
            ws.write(top, c, header, self.head(align="right") if callable(kind) or kind in NUMBERS else self.head(align="center") if kind == "flag" else self.head())
            ws.set_column(c, c, width)
        for i, r in enumerate(rows):
            for c, (_, key, kind, _) in enumerate(columns):
                v = key(r) if callable(key) else r.get(key)
                if v is None:
                    continue
                kind = kind(r) if callable(kind) else kind
                if kind in ("day", "month"):
                    ws.write_datetime(top + 1 + i, c, _day(v), self.fmt(kind))
                elif kind == "link":
                    ws.write_url(top + 1 + i, c, v[1], self.fmt("text", font_color="#0563C1", underline=1), v[0])
                elif kind in ("text", "wrap", "flag"):
                    ws.write_string(top + 1 + i, c, str(v), self.fmt(kind))
                else:
                    ws.write_number(top + 1 + i, c, v, self.fmt(kind))
        return top + 1 + len(rows)

    def para(self, ws, row, text, last_col, chars, **extra):
        """Long text across columns 0 to last_col, about chars wide. A merged cell's row does not fit itself, so its height is set here."""
        ws.merge_range(row, 0, row, last_col, text, self.fmt("wrap", **extra))
        ws.set_row(row, 13.5 * (len(text) // chars + 1))


def _read_me(b: _Book, through: str):
    ws = b.sheet("Read me", "VantageScore adoption tracker: analyst workbook")
    ws.set_column(0, 0, 118)
    lines = [
        (f"Data through {through}. Rebuilt with each refresh from Fannie Mae and Freddie Mac loan-level MBS issuance files. Research in progress, not for distribution.", None),
        ("", None),
        ("Colors", "bold"),
        ("Blue: inputs to change. Black: figures from the data, and formulas. Green: links to another sheet. Yellow fill: judgment calls these files cannot test.", None),
        ("", None),
        ("Sheets, in order, after this one", "bold"),
        ("FICO exposure: FICO's revenue on GSE loans under your inputs, as live formulas.", None),
        ("Your scenario: each lender's share priced on VS4, the share showing no FICO at most, and the share you assume drops FICO. Its totals feed FICO exposure.", None),
        ("Carrying VS4: the longest timeline. VS4-priced loans by issue month and week, split into both scores and VS4 only once the files show every score, with the same at a frozen lender mix.", None),
        ("By closing month: priced on VS4 and the scores that show, by estimated closing month, for the market at fixed lender weights and for each large lender, with how much of each month has arrived.", None),
        ("Score mix: shows FICO only, shows both (priced either way) and shows VS4 only, by issue month, week of first disclosure and quarter, by GSE.", None),
        ("Lenders: each large lender's stage, rule, score mix and rate figures, with its ticker.", None),
        ("Lender split by week: the same split over time, by GSE.", None),
        ("Cost or rate: what lenders pick when they hold both scores, by what VS4 would do to the fee, and what the pick saves in LLPAs.", None),
        ("Fees: fee saved and taken on the GSEs' grid, in all and by lender; the GSEs' own scores on these loans; how the rate gap differs by LLPA, by lender and channel.", None),
        ("Rates: how a VS4 loan's note rate compares with comparable FICO loans, at the same FICO and at the same score number: the lead figures, what is compared, Rocket's switch point and the rate past it, from raw to like for like, the same score number by closing month, with 20 points off VS4, by issue period and for VS4 under 640 and 820+, both comparisons by the gap between the scores, which FICO has paid the same rate as a VS4 score, by lender and channel, whether the rate follows the score used, more cuts, Milliman's basis, the build's checks, what to quote, the limits and the figures behind the sentences.", None),
        ("Rules: how often each lender prices on VS4 with its score under and over 20 points above FICO, by week.", None),
        ("VS4 share by month, Loans by month: the largest lenders and every lender with a ticker, both GSEs.", None),
        ("Whole market, Whole market by year, Lenders by year, Whole market lenders, Score models: which score lenders named on every kind of loan in the latest HMDA file and in each year, which lenders named what, and who uses each model.", None),
        ("Private-label deals, Private-label VantageScore: which model SEC due diligence reports name, by credit report month, quarter filed and kind of deal, with the deals and filers behind them, and the deals and reports that name VantageScore.", None),
        ("VA loans at 830+: whose VA loans show scores Classic FICO almost never reaches, by closing month and by lender, from Ginnie Mae's monthly loan files, with FHA as the check.", None),
        ("Weekly note, Statements: what changed each week; what companies and others have said, with links.", None),
        ("", None),
        ("Read these with care", "bold"),
        ("Two things in these files are facts: a score that shows, and the Pricing Indicator saying which score priced the loan. A score that does not show is unknown, not absent. So priced on VS4 is exact, the share showing a score is a floor on loans that have it, and the share showing only one score is a ceiling on loans that have only that one.", None),
        ("Dates: issue month ties to GSE volume and sets the fee grid. Weeks are the earliest news and swing with which lenders delivered. Closing month, the first payment month less two, sits nearest the borrower's application and lock, and its recent months are still arriving. A rate is set at lock, while a lender can pick the score as late as delivery, so rates can lag picks.", None),
        ("Records show every score the GSE has on a loan only from Oct 19, 2026. Figures for loans disclosed with every score rest on those records. Earlier months show only the score that priced the loan.", None),
        ("Lenders deliver one score: the delivery file has a single credit score field. A second score most likely reaches the GSE through underwriting. Neither GSE says this decides which scores show, so it is our reading. VS4 only at Freddie Mac does not mean Classic FICO was not pulled.", None),
        ("A week's figures move with the mix of lenders delivering that week. The seller is not always the lender that made the loan.", None),
        ("The fee grid is Freddie Mac Guide Exhibit 19 (Bulletin 2026-K). It matches Fannie Mae's LLPA matrix of Sep 30, 2026, cell by cell (https://singlefamily.fanniemae.com/media/9391/display). Fees are what the GSE charges, not what a borrower sees.", None),
        ("The Rates sheet is a like-for-like comparison, not a test of cause. Points, lender credits and lock dates are not disclosed, so the note rate is not all a borrower pays, and closing month and week first disclosed stand in for the day a rate was set.", None),
        ("Loans first disclosed before late September show only the score that priced them, so the earlier part of Carrying VS4 is a floor. Pulls on loans that never fund cannot be seen anywhere in these files.", None),
        ("The exposure calculator is arithmetic on your inputs, not a forecast. It covers loans sold to the GSEs only; FHA accepts VS4 from January 1, 2027.", None),
        ("Private-label reports cover only rated deals and reports with a model column; a score column headed FICO can hold a VantageScore, so a blank or a label is not a fact. The loans are months old when a deal files.", None),
        ("HMDA is annual and names the model the lender relied on. A named model is a fact; more than one model, other model, not applicable and exempt are unknown, so the shares naming FICO and VantageScore are floors. The buyer is whoever bought the loan that calendar year.", None),
        ("VA loans at 830 or above are inference: no Ginnie Mae file names a score model, and another model reaching 850 could look the same. A VS4 score sent to Ginnie Mae does not mean no FICO was bought. The share on VS4 is a range, because the files can't tell VS4 on every loan from VS4 only when it is 20 or more points higher.", None),
        ("Not affiliated with Fannie Mae, Freddie Mac, Ginnie Mae, the VA, FICO or VantageScore Solutions.", None),
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
    ws = b.sheet("Your scenario", "Your scenario", "Change the blue cells. A lender priced on VS4 can still pull and pay for FICO, so the two are separate.")
    top, first = 5, 6
    last = first + len(rows) - 1
    columns = [("Lender", lambda r: "Everyone else" if r.get("status") == "other" else r["short"], "text", 26), ("Ticker", "ticker", "text", 8), ("VS4 use", "status", "text", 10),
               ("Share of loans", "share", "pct", 10), ("VS4 today", "vs4_share", "pct", 10), ("Latest weeks", "recent_share", "pct", 10),
               ("On the rule: score higher", "on_higher", "pct", 11)]
    b.table(ws, top, columns, rows)
    ws.write(top, 7, "Your VS4", b.head(align="right"))
    ws.write(top, 8, "Shows no FICO, at most", b.head(align="right"))
    ws.write(top, 9, "Lender drops FICO (your assumption)", b.head(align="right"))
    ws.set_column(7, 9, 12)
    blue = b.fmt("pct", font_color="#0000FF")
    for i, r in enumerate(rows):
        ws.write_number(first + i, 7, r["vs4_share"], blue)
        ws.write_number(first + i, 8, r["nf0"], b.fmt("pct"))
        ws.write_number(first + i, 9, r["nf0"], blue)
    ws.freeze_panes(first, 1)
    v0 = sum(r["share"] * r["vs4_share"] for r in rows)
    nf0 = sum(r["share"] * r["nf0"] for r in rows)
    bold = b.fmt("pct", bold=True)
    ws.write(3, 0, "All lenders, weighted by share of loans", b.fmt("text", bold=True))
    for col, value in ((4, v0), (7, v0), (8, nf0), (9, nf0)):
        letter = "ABCDEFGHIJ"[col]
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
    put("no_fico_today", "Today, at Fannie Mae", nf_market, "Read at Fannie Mae.", "pct")
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
    ws = b.sheet("Lenders", "Lender by lender", "The 60 largest and every other lender past the first stages. Loans disclosed with every score, both GSEs unless named. Rate figures are at the far right; fees by lender are on the Fees sheet.")
    ws.write(2, 0, "Both, earlier and Both, latest are at Fannie Mae for a lender with 20+ Fannie loans in each period, else both GSEs.", b.fmt("text", font_color="#555555"))
    outlook = {r["id"]: r for r in _rows("outlook") if r.get("view") == "lender"}
    rows = sorted((r for r in _rows("lender_stage") if r.get("view") == "lender"), key=lambda r: r["rank"])
    out = lambda f: (lambda r: (outlook.get(r["id"]) or {}).get(f))  # noqa: E731
    card = {r["key"]: r for r in _rows("rates") if r["view"] == "lender" and r.get("scope") == "card"}
    rate = lambda read, part: (lambda r: (card.get(r["id"]) or {}).get(f"{read}_{part}") if (card.get(r["id"]) or {}).get(f"{read}_dot") is not None else None)  # noqa: E731
    rough = lambda read: (lambda r: "Yes" if rate(read, "rough")(r) else None)  # noqa: E731
    columns = [("Lender", "short", "text", 27), ("Ticker", "ticker", "text", 7), ("Type", "kind", "text", 14), ("Main channel", "lead", "text", 13), ("Rank", "rank", "int", 6), ("Loans", "loans", "int", 8),
               ("Share of loans", "share", "pct", 8), ("Stage", "stage", "text", 8), ("Rule", "rule", "text", 9),
               ("Shows FICO only", "mix_fico_only", "pct", 8), ("Both, on FICO", "mix_both_fico", "pct", 8), ("Both, on VS4", "mix_both_vs", "pct", 8), ("Shows VS4 only", "mix_vs_only", "pct", 8),
               ("Fannie: shows FICO only", "fnma_fico_only", "pct", 8), ("Fannie: both, on FICO", "fnma_both_fico", "pct", 8), ("Fannie: both, on VS4", "fnma_both_vs", "pct", 8), ("Fannie: shows VS4 only", "fnma_vs_only", "pct", 8),
               ("Freddie: shows FICO only", "fhlmc_fico_only", "pct", 8), ("Freddie: both, on FICO", "fhlmc_both_fico", "pct", 8), ("Freddie: both, on VS4", "fhlmc_both_vs", "pct", 8), ("Freddie: shows VS4 only", "fhlmc_vs_only", "pct", 8),
               ("Priced on VS4", "vs4_share", "pct", 8), ("Latest weeks", "recent_share", "pct", 8), ("Uses VS4 when higher", "uses_higher", "pct", 8),
               ("Under 20 pts, earlier", "below_early", "pct", 8), ("Under 20 pts, latest", "below_late", "pct", 8), ("20+ pts", "above", "pct", 8), ("Both, earlier", "both_early", "pct", 8), ("Both, latest", "both_late", "pct", 8),
               ("On the rule: score higher", out("on_higher"), "pct", 8)]
    ws.write(2, len(columns), "Rate against comparable FICO loans, bp. Rocket's row leaves Rocket correspondent out. Estimate: midpoint of the two exact-match methods. Rough: under 8 lender-weeks. Low and high: the range across the 3 methods. " + FLOOR, b.fmt("text", font_color="#555555"))
    for read, label in RATE_READS:
        columns += [(f"{label}: estimate", rate(read, "dot"), "bp", 8), (f"{label}: low", rate(read, "lo"), "bp", 8), (f"{label}: high", rate(read, "hi"), "bp", 8), (f"{label}: VS4 loans", rate(read, "n"), "int", 8), (f"{label}: lender-weeks", rate(read, "weeks"), "int", 8), (f"{label}: rough", rough(read), "flag", 8)]
    b.table(ws, 3, columns, rows)
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 3 + len(rows), len(columns) - 1)


def _m(v):
    return None if v is None else v / 1e6


def _fees(b: _Book):
    ws = b.sheet("Fees", "What the fee grid is worth")
    b.para(ws, 1, "Freddie Mac Guide Exhibit 19, which matches Fannie Mae's LLPA matrix of Sep 30, 2026. Fees the GSE charges, not what a borrower sees. Loans issued in the month shown, records with every score, terms over 15 years. A year's figures scale the month's to the GSE's balance, an estimate from one part month.", 10, 130, font_color="#555555")
    rows = _rows("fees")
    gse = {"All": "Both GSEs", "FNMA": "Fannie Mae", "FHLMC": "Freddie Mac"}
    market = [r for r in rows if r["view"] == "market"]
    columns = [("GSE", lambda r: gse.get(r["key"], r["key"]), "text", 26), ("Month", "month", "month", 10), ("Loans", "loans", "int", 9), ("Balance ($m)", lambda r: _m(r["upb"]), "usdm", 11),
               ("VS4-priced, both scores", "priced_loans", "int", 9), ("Of those, lower LLPA on VS4", "saving_share", "pct", 8), ("Saved, net, on all of those (bp of balance)", "saved_bp", "num", 9), ("Saved per loan with a lower LLPA ($)", "saving_avg_usd", "usd", 9),
               ("Taken, grossed up ($m)", lambda r: _m(r["taken_all_usd"]), "usdm", 9), ("Balance a year ($m)", lambda r: _m(r.get("annual_upb")), "usdm", 11),
               ("Taken, a year ($m)", lambda r: _m(r.get("taken_annual_usd")), "usdm", 9), ("Fees taken ($m)", lambda r: _m(r["taken_usd"]), "usdm", 9)]
    next_row = b.table(ws, 3, columns, market)
    lenders = sorted((r for r in rows if r["view"] == "lender" and r["priced_loans"] >= FEE_LENDER_MIN), key=lambda r: -r["taken_usd"])
    if lenders:
        ws.write(next_row + 1, 0, "By lender", b.fmt("text", bold=True))
        b.para(ws, next_row + 2, "Lenders with 20 or more VS4-priced loans showing both scores, the same month as above. Fees taken counts those loans; grossed up scales that up for VS4-priced loans that show one score.", 10, 130, font_color="#555555")
        next_row = b.table(ws, next_row + 3, [("Lender", "short", "text", 26), ("Month", "month", "month", 10), ("Loans", "loans", "int", 9), ("Balance ($m)", lambda r: _m(r["upb"]), "usdm", 11), ("VS4-priced, both scores", "priced_loans", "int", 9), ("Of those, lower LLPA on VS4", "saving_share", "pct", 8),
                                               ("Saved, net, on all of those (bp of balance)", "saved_bp", "num", 9), ("Saved per loan with a lower LLPA ($)", "saving_avg_usd", "usd", 9), ("Taken, grossed up ($m)", lambda r: _m(r["taken_all_usd"]), "usd2", 9), ("Fees taken ($m)", lambda r: _m(r["taken_usd"]), "usd2", 11), ("Ticker", "ticker", "text", 9)], lenders)
    ws.write(next_row + 1, 0, "The GSEs' own scores, in points", b.fmt("text", bold=True))
    b.para(ws, next_row + 2, "VS4-priced minus FICO-priced in the same fee bucket, same lender and GSE. Last rows: VS4 a tier better minus the same tier, in the same Classic FICO tier. The GSEs' own scores are not used for pricing. Neither figure measures how the loans will perform.", 10, 130, font_color="#555555")
    scores = [r for r in rows if r["view"] in ("gse", "lift")]
    scores.sort(key=lambda r: (r["view"], r.get("scope") or "", r["key"]))
    top = b.table(ws, next_row + 3, [("Fee bucket", lambda r: r["label"], "text", 26), ("Scope", lambda r: "VS4 a tier better, same FICO tier" if r["view"] == "lift" else r.get("scope_label"), "text", 29), ("Points", "diff", "bp", 9), ("Loans", "loans", "int", 9)], scores) + 1
    rates = _rows("rates")
    llpa = sorted((r for r in rates if r["view"] == "llpa_rate"), key=lambda r: r.get("order") or 0)
    if llpa:
        ws.write(top, 0, "How the rate differs by LLPA, by lender and channel, in bp", b.fmt("text", bold=True))
        b.para(ws, top + 1, "VS4 minus FICO at the same FICO, in bp of note rate, by whether VS4 lowers the LLPA. The gap is the midpoint of the two exact-match methods and low and high the range across the 3 methods, as on the Rates sheet; then the model's gap and its one standard error. " + FLOOR + " VS4 loans counts all of them, matched or not. Rough: under 8 lender-weeks. Rows do not add: each is a midpoint on the loans that find a match.", 10, 130, font_color="#555555")
        columns = [("Lender and channel", "label", "text", 26), ("Purpose", "purpose", "text", 29)]
        for side, label in (("lower", "Lower LLPA on VS4"), ("same", "Same LLPA")):
            columns += [(f"{label}: gap", f"{side}_dot", "bp", 9), (f"{label}: low", f"{side}_lo", "bp", 9), (f"{label}: high", f"{side}_hi", "bp", 9), (f"{label}: model gap", f"{side}_gap", "bp2", 9), (f"{label}: model error", f"{side}_se", "num", 9),
                        (f"{label}: VS4 loans", f"{side}_n", "int", 9), (f"{label}: rough", lambda r, side=side: "Yes" if r.get(f"{side}_rough") else None, "flag", 9)]
        top = b.table(ws, top + 2, [*columns, ("Not like for like", lambda r: "Yes" if r.get("not_like_for_like") else None, "flag", 9)], llpa)
        ws.set_column(3, 3, 11)  # the balance columns of the tables above
        ws.set_column(9, 9, 11)
        meta = next((r for r in rates if r["view"] == "meta"), {})
        for said in (meta.get("llpa_sum"), meta.get("llpa_share")):
            if said:
                b.para(ws, top, said, 10, 130)
                top += 1


def _carrying(b: _Book):
    ws = b.sheet("Carrying VS4", "Loans carrying VS4, the longest timeline", "Loans first disclosed before late September show only the score that priced them: those rows are a floor, with the split blank. Weeks by first disclosure, and they swing with which lenders delivered.")
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
    ws = b.sheet("Cost or rate", "What lenders pick when they hold both scores", "Share priced on VS4, loans with both scores issued from Oct 1. Blank under 20 loans. Pulls on loans that never fund cannot be seen.")
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
            columns.append((labels[s], (lambda k, s=s: (cells[(cohort, s, k[0])]["vs4_share"] if (cohort, s, k[0]) in cells and cells[(cohort, s, k[0])]["loans"] >= 20 else None)), "pct", 13))
        row = b.table(ws, row, columns, COST_ROWS) + 1
    options = sorted((r for r in _rows("fees") if r.get("view") == "option"), key=lambda r: r["scope_rank"])
    ws.write(row, 0, "What the pick saves in LLPAs: the upfront fee as bp of balance", b.fmt("text", bold=True))
    row += 1
    heads = ["Lender", "Loans", "All on FICO", "All on VS4", "Lower of the two", "As priced", "Average loan ($)", "Share of the saving taken", "Picking saves, per loan ($)", "Dropping FICO gives up, per loan ($)"]
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
    rows = _rows("rates")
    meta = next((r for r in rows if r["view"] == "meta"), None)
    if not meta:
        return
    ws = b.sheet("Rates", "Like-for-like rates: a VS4 loan against comparable FICO loans", "VS4 minus FICO, in bp of note rate. A like-for-like comparison, not a test of cause. Points, lender credits and lock dates are not disclosed.")
    grey = {"font_color": "#555555"}
    top = 2

    def para(text, **extra):
        nonlocal top
        if text:
            b.para(ws, top, _sheet_words(text), 7, 125, **extra)  # columns A to H
            top += 1

    def heading(title):
        nonlocal top
        ws.write(top + 1, 0, title, b.fmt("text", bold=True))
        top += 2

    def table(title, note, columns, picked, *under):
        nonlocal top
        if picked:
            heading(title)
            para(note, **grey)
            top = b.table(ws, top, columns, picked)
            for said in under:
                para(said)

    def lines(title, said):
        said = [t for t in said if t]
        if said:
            heading(title)
            for t in said:
                para(t)

    view = lambda name, scope=None: [r for r in rows if r["view"] == name and (scope is None or r.get("scope") == scope)]  # noqa: E731
    ordered = lambda name, scope=None: sorted(view(name, scope), key=lambda r: r.get("order") or 0)  # noqa: E731
    yes = lambda key: (lambda r: "Yes" if r.get(key) else None)  # noqa: E731
    num = lambda head, key, kind="bp2": (head, key, kind, 9)  # noqa: E731
    blank = ("", lambda r: None, "text", 24)
    limit = {r["key"]: r["text"] for r in view("limit")}

    for r in ordered("answer"):
        para(r["text"], **({"bold": True} if r["key"] == "lead" else {}))
    para(limit.get("selected"))
    if meta.get("as_of"):
        ws.write(top, 0, "Data through", b.fmt("text", bold=True))
        ws.write_datetime(top, 1, _day(meta["as_of"]), b.fmt("day", align="left"))
        ws.write(top, 2, "The newest file is provisional.", b.fmt("text", **grey))
        top += 1
    table("The lead figures", "Estimate: midpoint of the two exact-match methods. Low and high: the range across the 3 methods, not a margin of error. Low and high are printed to the half point (whole point where the methods sit 4+ apart), low down and high up. The estimate is printed on the same points, to the nearest. Midpoint, lowest method and highest method are the same figures unrounded. 95% low and 95% high: an approximate 95% range for the estimate, from resampling lender and channel groups; the sentences print its ends to the half point, low down and high up. Fannie alone: the midpoint at Fannie Mae only.",
          [("Comparison", "title", "text", 46), ("Which loans", "sub", "wrap", 24), ("What it says", "sentence", "wrap", 12), num("Estimate", "dot", "bp"), num("Low", "lo", "bp"), num("High", "hi", "bp"), num("95% low", "tl"), num("95% high", "th"),
           num("5-point match", "cell5"), num("5-point match: error", "cell5_se", "num"), num("One-tier match", "tier"), num("One-tier match: error", "tier_se", "num"), num("Model", "model"), num("Model error", "model_se", "num"),
           num("Midpoint", "dot_raw"), num("Lowest method", "lo_raw"), num("Highest method", "hi_raw"), num("VS4 loans", "n", "int"), num("Matched, 5-point band", "read5", "int"), num("Matched, one LLPA tier", "read_tier", "int"), num("VS4 loans the model covers", "model_n", "int"),
           num("Lender-weeks", "lender_weeks", "int"), num("Fannie alone", "fannie"), num("Fannie alone: VS4 loans", "fannie_n", "int")], ordered("row"))
    heading("What is compared, and by which methods")
    para(meta.get("changed"))
    para(meta.get("stamp"))
    para(limit.get("left_out"))
    para(limit.get("grid"))
    para(limit.get("ranges"))
    para(meta.get("sample"))
    para("Same FICO sets a VS4 loan showing a FICO against FICO loans at that FICO; a VS4 loan showing no FICO is unknown and left out of the same-FICO rows. Same score number sets its VS4 number against FICO loans at that number.")
    para(meta.get("stamp_more"))
    para("In the tables. 5-point match and one-tier match are the first two of those methods, and Model is the third, trained only on FICO loans. Error is one standard error. Model 95% low and high are the model's figure less and plus about two errors. A lender-week is one lender's loans first disclosed in one week, with at least 5 loans. Errors allow for loans of one lender and week moving together; a model error outside the lead table is the widest of three such groupings.", **grey)
    para("A VS4 loan is one the Pricing Indicator says priced on VS4 or, on records before the indicator, one whose only score shown is VS4. VS4 loans means the loans in the row. VS4 loans the model covers: those of them inside its range of scores. Matched: those of them that find a comparable FICO loan. Rough: under 8 lender-weeks, or under 100 matched loans on either exact match. A blank number means too few loans, or no such figure on that row.", **grey)

    stepped = any(r.get("est") is not None for r in view("line"))
    table("Rocket's switch point: the step in the rate", "Loans at Rocket showing both scores, Rocket correspondent left out, within 15 points either side of a line in VS4 less FICO. Step: how far the note rate moves at the line, with each side free to slope and the loan's traits held. Where the LLPA would not change: it is the same at FICO and at FICO plus 34, the whole window at this line. The rows marked no switch take those loans too, in the same test at lines where nothing switches, so a step there is not the pick. 95% low and high: the step less and plus the error times Student's t on the row's lender-weeks less one, which widens the range when they are few. Rough: under 8 lender-weeks. The two On VS4 columns count all those loans, whatever the LLPA. So do the columns by closing month, on those 15 to 19 above FICO. The row where the LLPA would fall does not show what the LLPA does to the rate: the pick flips at the same line, so the two cannot be told apart.",
          [("Line", "label", "text", 46), blank, num("Step", "est"), num("Error", "se", "num"), num("95% low", "lo"), num("95% high", "hi"), num("Loans", "n", "int"), num("Loans above the line", "above", "int"), num("Lender-weeks", "lender_weeks", "int"), ("Rough", lambda r: "Yes" if (r.get("lender_weeks") or 0) < THIN_WEEKS else None, "flag", 9),
           num("On VS4, 15 to 19 above FICO", "use_below", "pct"), num("On VS4, 20 to 24 above FICO", "use_above", "pct"), num("15 to 19 above, closed by Sep: share on VS4", "use_below_early", "pct"), num("15 to 19 above, closed by Sep: loans", "use_below_early_n", "int"), num("15 to 19 above, closed after Sep: share on VS4", "use_below_late", "pct"), num("15 to 19 above, closed after Sep: loans", "use_below_late_n", "int")],
          [r for r in ordered("line") if r["key"] != "scan"] if stepped else [], limit.get("line"))
    table("The same test at every line where nothing switches", "The regression above at every line from 40 below FICO to 5 above on FICO loans, and from 35 to 75 above on VS4 loans. Percentiles, lowest and highest: the step across those lines. Size of a step: how large it runs with nothing there, ignoring its sign. Misses zero: the share of lines whose 95% range leaves out zero.",
          [("Test", "label", "text", 46), blank, num("Lines", "lines", "int"), num("2.5th percentile", "p2_5"), num("97.5th percentile", "p97_5"), num("Lowest", "min"), num("Highest", "max"), num("Size of a step, 90th percentile", "abs_p90", "num"), num("Misses zero", "miss_share", "pct")], [r for r in view("line") if r["key"] == "scan" and r.get("lines")] if stepped else [])
    table("Past the switch point, where the LLPA does not change", "Loans showing both scores whose LLPA is the same at VS4, at FICO and at VS4 less 20, so the same on today's grid and the old rule. Each row but the last sets VS4 loans 25 to 49 points above their FICO against FICO loans of the same lender with VS4 0 to 19 above theirs, matched as in the lead table and at the same FICO, in a 5-point or a 20-point band. Model: the mean gap to the FICO model, the first group less the second. The last row sets FICO loans 25 to 49 above against the same second group, at lenders that rarely use VS4, where nothing switches. Rocket's rows leave Rocket correspondent out. A figure on under 100 matched loans stays blank. Rough: under 8 lender-weeks.",
          [("Loans", "label", "text", 46), blank, num("5-point match", "cell5"), num("20-point match", "cell20"), num("Model", "model"), num("Loans with VS4 25 to 49 above FICO", "n", "int"), num("FICO loans with VS4 0 to 19 above FICO", "comparators", "int"), num("Matched, 5-point band", "read5", "int"), num("Matched, 20-point band", "read20", "int"), num("Lender-weeks", "lender_weeks", "int"), ("Rough", yes("thin"), "flag", 9)],
          ordered("past") if any(r.get(k) is not None for r in view("past") for k in ("cell5", "cell20", "model")) else [], limit.get("past"))
    table("From raw to like for like", "Both sides issued from Oct 1, Rocket correspondent left out. So it ends at the Issued from Oct 1 row below, not the lead table's figure, which goes back further. Each row holds more equal than the one above it. The last two are the raw gap at one GSE.",
          [("Step", "label", "wrap", 46), blank, num("Gap", "gap"), num("Error", "se", "num"), num("VS4 loans matched", "read", "int"), num("VS4 loans", "pool", "int")], ordered("steps"))
    printed = [num("Estimate", "dot", "bp"), num("Low", "spread_lo", "bp"), num("High", "spread_hi", "bp")]
    thin = [num("95% low", "tl"), num("95% high", "th")]
    exact = [num("Midpoint", "dot_raw"), num("Lowest method", "lo_raw"), num("Highest method", "hi_raw")]
    same_number = [num("5-point match", "cell5"), num("One-tier match", "tier"), num("Model", "gap"), num("Model error", "se", "num"), num("Model 95% low", "lo"), num("Model 95% high", "hi"), num("VS4 loans", "pool", "int"), num("VS4 loans the model covers", "n", "int"), num("Matched, 5-point band", "read", "int"), num("Matched, one LLPA tier", "read_tier", "int"), num("Lender-weeks", "lender_weeks", "int"), ("Rough", yes("thin"), "flag", 9)]
    announced = _day(ANNOUNCED)
    under_half = lambda r: "Yes" if r.get("thin") or (r.get("in_share") is not None and r["in_share"] < FIRM_IN) else None  # noqa: E731
    table("Same score number, by closing month", f"VS4 640 to 819, in two groups: where 20 points less would raise the LLPA and where it would not. For MBS issued before Oct 1, 2026, the LLPA grid counted a VS4 score as 20 points lower (the old rule). {announced:%b} {announced.day}, {announced.year}: one LLPA grid for both scores announced (Statements sheet). Share of the month in this table: how much of the closing month has arrived, times how much of it this sample keeps. Rough here also marks a month under half in. Estimate, low and high as in the lead table. {FLOOR}",
          [("Group", "label", "text", 46), ("Closing month", "close", "month", 24), *printed, *exact, *(("Rough", under_half, "flag", 9) if c[0] == "Rough" else c for c in same_number), num("Share of the month in this table", "in_share", "pct")], sorted(view("same_number", "month"), key=lambda r: (r.get("group") != "stake", r["close"])),
          " ".join(t for t in (meta.get("number_caption"), *(r.get("text") for r in view("same_number", "fade"))) if t))
    table("Same score number, with 20 points off VS4", f"The lead table's same-number loans, VS4 under 820, with VS4 less 20 set against FICO loans at that number. Model: the model at VS4 less 20. Estimate, low and high as in the lead table. {FLOOR}", [("Loans", "label", "text", 46), blank, *printed, *exact, *(c for c in same_number if c[1] != "n")], view("same_number", "less20"))  # its n counts every loan, not those with a model read
    table("Same score number, by issue period", "VS4 under 820. VS4 less 20: the model with 20 points taken off VS4 first.", [("Issued", "label", "text", 46), blank, *same_number, num("VS4 less 20", "less20"), num("VS4 less 20: error", "less20_se", "num")], ordered("same_number", "period"))
    almost_none = lambda r: r.get("flag") == "no_like_fico"  # noqa: E731
    over = lambda r: {**r, "label": "VS4 820+", "plain": r.get("cell5"), "plain_n": r.get("read"), "cell5": None, "read": None, **(dict.fromkeys(("gap", "se", "lo", "hi")) if almost_none(r) else {})}  # noqa: E731
    bands = [over(r) if r["key"] == "over820" else r for r in ordered("same_number", "band")]
    none_like = any(almost_none(r) for r in bands if r["key"] == "over820")
    table("Same score number: VS4 under 640 and VS4 820+", f"On the VS4 820+ row the {'5-point, one-tier and model columns stay blank while it has almost no comparable FICO loans at its own number' if none_like else '5-point and one-tier columns stay blank'}: its exact match is against FICO 780+ with no score band, in the last two columns, and the column before them counts its loans that find a FICO loan at their own number.{'' if none_like else ' Its Model figure is at its own number, on the few FICO loans the model has up there, not against FICO 780+.'}",
          [("VS4 band", "label", "text", 46), ("Flag", lambda r: BAND_FLAGS.get(r.get("flag"), r.get("flag")), "wrap", 24), *same_number, num("Matched at its own number, 5-point band", "read_number", "int"), num("Against FICO 780+, no score band", "plain"), num("Against FICO 780+, no score band: VS4 loans matched", "plain_n", "int")], bands, meta.get("number_bands"))
    table("Same FICO, by the gap between the scores", f"VS4 loans showing a FICO, by how far VS4 sits above it, against FICO loans at that FICO. Estimate, low, high and 95% low and high as in the lead table. Fannie alone: the midpoint at Fannie Mae only. {FLOOR}",
          [("VS4 above FICO", "label", "text", 46), blank, *printed, *thin, *exact, num("5-point match", "cell5"), num("One-tier match", "tier"), num("Model", "model"), num("VS4 loans", "n", "int"), num("VS4 loans the model covers", "model_n", "int"), num("Matched, 5-point band", "read5", "int"), num("Matched, one LLPA tier", "read_tier", "int"), num("Lender-weeks", "lender_weeks", "int"), ("Rough", yes("thin"), "flag", 9), num("Fannie alone", "fannie")], ordered("fico_gap"))
    table("Same score number, by the gap between the scores", f"VS4 loans under 820 showing a FICO, by how far VS4 sits above it. Estimate, low, high and 95% low and high as in the lead table. {FLOOR}", [("VS4 above FICO", "label", "text", 46), blank, *printed, *thin, *exact, *same_number], ordered("same_number", "gapband"), meta.get("gap_line"))
    table("Same score number, by gap and closing month", f"VS4 under 820 showing a FICO. {FLOOR}", [("VS4 above FICO", "label", "text", 46), ("Closing month", "close", "month", 24), *same_number], sorted(view("same_number", "gapband_month"), key=lambda r: (r.get("order") or 0, r["close"])))
    table("Which FICO has paid the same rate as a VS4 score", "Loans issued from Oct 1. FICO that pays the same rate: where the band's mean rate falls on a model of FICO loans, with its range. VS4 above that FICO: the VS4 number less that FICO, in whole points. Rate barely moves: the rate falls under 2 bp per 20 points around the band, so the FICO that pays the same rate means little there. Its low and high: about two errors either way, on an error that does not resample lenders.",
          [("VS4 band", "band", "text", 46), blank, num("VS4 loans the model covers", "n", "int"), num("FICO they show", "fico_mean", "whole"), num("FICO that pays the same rate", "eq", "whole"), num("Its low", "eq_lo", "whole"), num("Its high", "eq_hi", "whole"), num("VS4 number", "vs_mean", "whole"), num("VS4 above that FICO", "points", "whole"),
           num("FICO at lenders that rarely use VS4", "fico_rare", "whole"), num("Loans behind that FICO", "fico_rare_n", "int"), num("Rate falls, bp per 20 points", "slope", "num"), ("Rate barely moves", yes("use_bp"), "flag", 9)], ordered("equivalent"), meta.get("equivalent_stat"), meta.get("equivalent_more"), meta.get("equivalent_caption"))
    reads = []
    for read, label in RATE_READS:
        reads += [num(f"{label}: estimate", f"{read}_dot", "bp"), num(f"{label}: low", f"{read}_lo", "bp"), num(f"{label}: high", f"{read}_hi", "bp"), num(f"{label}: VS4 loans", f"{read}_n", "int"), num(f"{label}: matched, 5-point band", f"{read}_read5", "int"), num(f"{label}: matched, one LLPA tier", f"{read}_read_tier", "int"), num(f"{label}: lender-weeks", f"{read}_weeks", "int"), (f"{label}: rough", yes(f"{read}_rough"), "flag", 9),
                  num(f"{label}, shown: 5-point match", f"{read}_shown_cell5"), num(f"{label}, shown: one-tier match", f"{read}_shown_tier"), num(f"{label}, shown: matched, 5-point band", f"{read}_shown_read5", "int"), num(f"{label}, shown: matched, one LLPA tier", f"{read}_shown_read_tier", "int")]
    table("By lender and channel", f"Estimate, low and high as in the lead table, against the lender's own FICO loans. {FLOOR} Rough: under 8 lender-weeks. Shown: the two exact matches again, against only those of its FICO loans that also show a VS4, each blank under 100 matched loans. How the rate differs by LLPA is on the Fees sheet. Gaps between lenders under about 3 bp on same number, or about 5 bp on the same-FICO and same-LLPA estimates, are too small to call.",
          [("Lender and channel", "label", "text", 46), ("Not like for like", yes("not_like_for_like"), "text", 24), *reads], ordered("lender", "group"), meta.get("lender_rates"), f"Rocket correspondent is left out of every all-lender rate row as not like for like: {meta['rc_reason']}." if meta.get("rc_reason") else None)
    table("By lender, all its channels together", "The columns above, for each lender with 100 or more VS4 loans. Same FICO, VS4 under 820: UWM's midpoint on those of its loans that show a FICO.",
          [("Lender", "label", "text", 46), ("Rocket correspondent left out", yes("correspondent_out"), "text", 24), *reads, num("Same FICO, VS4 under 820 (UWM only)", "same_fico_under820")], ordered("lender", "card"))
    para(meta.get("lender_line"))
    para(f"On same FICO, {limit['book'][0].lower()}{limit['book'][1:]}" if limit.get("book") else None)
    lines("Is the gap the score itself?", [meta.get("score_lead")])
    fit = {"vs4": "VS4 loans", "fico": "FICO loans"}
    table("Does the rate follow the score used?", "bp per 20 points of each score, both in one model. Loans issued from Oct 1 showing both scores, both 640 to 799. VS4 slope less FICO slope: the first less the second, from the same model turned around, with its error. Test held: in both models the slope on the score used and VS4 slope less FICO slope sit clear of zero by about two errors, and the used slope is the larger. All lenders, refinances and purchases need 1,000+ loans in each model and 8+ lender-weeks; the rest 300+ loans. The sentence under the table also needs Fannie refinances to lean the same way: their used slopes of one sign, each at least 1.5 times the other's. Refinances and purchases, LLPA of the score used held: the same models with that LLPA held too. The test is not run on them, so Test held stays blank.",
          [("Which loans", "label", "text", 46), ("Loans in the model", lambda r: fit.get(r.get("group"), r.get("group")), "text", 24), num("Per 20 points of VS4", "on_vs4"), num("VS4: error", "on_vs4_se", "num"), num("Per 20 points of FICO", "on_fico"), num("FICO: error", "on_fico_se", "num"), num("VS4 slope less FICO slope", "diff"), num("Slope gap: error", "diff_se", "num"),
           num("Loans", "n", "int"), num("Lender-weeks", "lender_weeks", "int"), ("Test held", lambda r: None if r.get("scope") in ("refi_llpa", "purchase_llpa") else "Yes" if r.get("guard") else "No", "flag", 9)], view("follows_score"),
          *dict.fromkeys(r["sentence"] for r in view("follows_score") if r.get("sentence")))
    dims = {"ltv": "LTV", "size": "Loan size", "fico": "FICO band", "purpose": "Purpose", "rocket_correspondent": "On its own row"}
    shown = lambda key: (lambda r: None if r.get("text") else r.get(key))  # noqa: E731
    more = lambda r: [t for t in ("Not like for like." if r.get("not_like_for_like") else None, r.get("text")) if t]  # noqa: E731
    table("More cuts: description, not findings", "Same FICO, same LLPA, by loan type. Estimate, low, high and 95% low and high as in the lead table. Blank under 100 matched loans on either exact match, and on a row that says it has no comparable FICO loans, where only the counts and flags stay. On these small rows the 95% ends move with the random draw, so read them to the nearest few bp.",
          [("Cut", lambda r: dims.get(r.get("dim"), r.get("dim")), "text", 46), ("Row", "label", "text", 24), num("Estimate", shown("dot"), "bp"), num("Low", shown("spread_lo"), "bp"), num("High", shown("spread_hi"), "bp"), num("95% low", shown("tl")), num("95% high", shown("th")), num("Midpoint", shown("dot_raw")),
           num("5-point match", shown("cell5")), num("One-tier match", shown("tier")), num("Model", shown("gap")), num("Model error", shown("se"), "num"), num("Model 95% low", shown("lo")), num("Model 95% high", shown("hi")),
           num("VS4 loans", "n", "int"), num("VS4 loans the model covers", "model_n", "int"), num("Matched, 5-point band", "read5", "int"), num("Matched, one LLPA tier", "read_tier", "int"), num("Lender-weeks", "lender_weeks", "int"), ("Rough", yes("thin"), "flag", 9),
           ("Flag", lambda r: " ".join((["Description."] if r.get("description") else []) + more(r)) if more(r) else None, "text", 9)], view("cut"))
    table("Milliman's basis: VS4 less 20", f"VS4 less 20 against FICO, exact match only, on VS4 under 820 unless the row says otherwise. Milliman's own figure, on the Statements sheet, is not the same comparison as the lead table's same-number figure{': the line under this table says how' if meta.get('milliman_line') else ''}.", [("Loans", "label", "text", 46), blank, num("5-point match", "cell5"), num("One-tier match", "tier"), num("Matched, 5-point band", "read", "int"), num("Matched, one LLPA tier", "read_tier", "int"), num("VS4 loans", "pool", "int")], ordered("milliman"), meta.get("milliman_line"))
    results = {True: "Pass", False: "Warn"}
    beside = lambda key, floor=RARE_BESIDE: (lambda r: r.get(key) if (r.get(f"{key}_n") or 0) >= floor else None)  # noqa: E731
    table("Build checks", "They warn and stop nothing. Value and limit are in the unit beside them; Rocket, UWM and without it are in bp. Loans: the count behind the value. Held-out FICO loans: one FICO loan in five is held out of the model to test it. Rocket and UWM stay blank under 100 loans, and UWM's channels under 50; their counts stay.",
          [("Check", "label", "wrap", 46), ("Result", lambda r: results.get(r.get("pass"), "Too few loans"), "text", 24), num("Value", "value", lambda r: "whole" if r.get("unit") == "loans" else "bp2"), num("Limit", "limit", lambda r: "whole" if r.get("unit") == "loans" else "num"), ("Unit", "unit", "text", 9), num("Loans", "n", "int"), num("Rocket", beside("rocket")), num("Rocket loans", "rocket_n", "int"), num("UWM", beside("uwm")), num("UWM loans", "uwm_n", "int"),
           ("UWM, correspondent", beside("uwm_correspondent", RARE_CHANNEL), "bp2", 14), ("UWM, correspondent: loans", "uwm_correspondent_n", "int", 14), num("UWM, broker", beside("uwm_broker", RARE_CHANNEL)), num("UWM, broker: loans", "uwm_broker_n", "int"),
           num("Largest lender's share", "top_share", "pct"), num("Without it", "without_top"), num("Without it: error", "without_top_se", "num"), num("Without it: loans", "without_top_n", "int")], ordered("check"),
          *((meta.get("test_line") if r.get("key") == "rare_high_vs4" and meta.get("test_line") else f"{r.get('label')}: {r['detail']}") for r in ordered("check") if r.get("detail")))
    lines("What to quote", (r.get("text") for r in ordered("quote")))
    lines("Limits", [*(r["text"] for r in ordered("limit") if r["key"] not in UNDER_TABLES), meta.get("expected"), meta.get("rule_at_lock")])
    unit = lambda r: "points per bp" if r["key"] == "crossing_per_bp" else "points" if r["key"] == "curve_points" or r["key"].startswith("crossing") else "bp"  # noqa: E731
    in_unit = lambda r: "bp2" if unit(r) == "bp" else "num"  # noqa: E731
    table("Figures behind the sentences", "The decimals for figures that the sentences on this sheet print only in words, so they can be tied or pulled into a model. Sentence: the line that prints or rests on the figure, or Workbook only where none does. 5-point match, one-tier match and Model as in the lead table; Midpoint: the midpoint of the first two. Value: the figure, where it is one number and not split by method. 95% low and 95% high: the line's range; on the points rows they move with the random draw, so read them to the nearest point or two.",
          [("What it is", "what", "wrap", 46), ("Sentence", lambda r: _sheet_words(r["sentence"]), "wrap", 24), ("Unit", unit, "text", 12), num("5-point match", "cell5"), num("One-tier match", "tier"), num("Model", "model"), num("Midpoint", "mid"), num("Value", "value", in_unit), num("95% low", "lo", in_unit), num("95% high", "hi", in_unit), ("VS4 loans", "n", "int", 14), ("Matched, 5-point band", "read5", "int", 14), num("Matched, one LLPA tier", "read_tier", "int")], ordered("behind"))
    ws.set_column(2, 2, 12)  # the lead table's words


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
    shares = [("Classic FICO", "classic", "pct", 9), ("Newer FICO", "fico_new", "pct", 9), ("VS4", "vs4", "pct", 9), ("VantageScore 2.0, 3.0", "vs_old", "pct", 13), ("More than one model", "multi", "pct", 10), ("Other model", "other", "pct", 9), ("No score reported", "none", "pct", 9)]
    ws = b.sheet("Whole market", f"Which score lenders named on loans made in {meta['year']}, from HMDA", "A named model is a fact and the rest is unknown, so what is named is a floor. Each loan counts once; multifamily and reverse mortgages are left out.")
    next_row = b.table(ws, 3, [("Kind of loan", "label", "text", 44), ("Loans", "n", "int", 11), ("$bn", "usd_bn", "usdm", 10), *shares], sorted((r for r in rows if r["view"] == "segment"), key=lambda r: r["order"]))
    ws.write(next_row + 1, 0, "Applications taken for each loan made, funded or not", b.fmt("text", bold=True))
    b.table(ws, next_row + 2, [("Kind of loan", "label", "text", 44), ("Loans", "n", "int", 11), ("Applications", "apps", "int", 12), ("Per loan", "per_loan", "num", 9)], [r for r in rows if r["view"] == "apps"])
    trend = sorted((r for r in rows if r["view"] == "trend"), key=lambda r: (r["order"], r["year"]))
    if trend:
        ws = b.sheet("Whole market by year", f"Which score lenders named each year, {meta['first_year']} to {meta['year']}, from HMDA", "The form's list of models grew over time: a lender using a model not yet listed had to mark another model, so a model's first year is partly the form changing.")
        top = b.table(ws, 3, [("Kind of loan", "label", "text", 44), ("Year", lambda r: str(r["year"]), "text", 7), ("Loans", "n", "int", 11), ("$bn", "usd_bn", "usdm", 10), *shares], trend) + 1
        ws.write(top, 0, "Each model's loans by year (a loan counts under each model it names)", b.fmt("text", bold=True))
        b.table(ws, top + 1, [("Model named", "name", "text", 44), ("Year", lambda r: str(r["year"]), "text", 7), ("Loans", "n", "int", 11), ("Share of the year's loans", "share", "pct", 10)], [r for r in rows if r["view"] == "model_year"])
        ws = b.sheet("Lenders by year", "Which score each big lender named each year, going by legal entity", "The same lender groups as Whole market lenders. A merger or a new entity breaks a row.")
        groups_y = {"all": "Biggest", "first": "Biggest in first-lien", "equity": "Biggest in home equity", "vs": "Most VantageScore", "fico_new": "Most newer FICO"}
        b.table(ws, 3, [("Group", lambda r: groups_y[r["scope"]], "text", 22), ("Rank", "rank", "int", 6), ("Lender", "name", "text", 34), ("Year", lambda r: str(r["year"]), "text", 7), ("Loans", "n", "int", 10), *shares],
                sorted((r for r in rows if r["view"] == "lender_year"), key=lambda r: (list(groups_y).index(r["scope"]), r["rank"], r["year"])))
    ws = b.sheet("Whole market lenders", f"Which score each lender named on loans made in {meta['year']}, from HMDA", "The biggest lenders in each group. Names as filed; a lender's record covers the loans it made.")
    groups = {"all": "Biggest", "first": "Biggest in first-lien", "equity": "Biggest in home equity", "vs": "Most VantageScore", "fico_new": "Most newer FICO"}
    lenders = sorted((r for r in rows if r["view"] == "lender"), key=lambda r: (list(groups).index(r["scope"]), r["rank"]))
    b.table(ws, 3, [("Group", lambda r: groups[r["scope"]], "text", 22), ("Rank", "rank", "int", 6), ("Lender", "name", "text", 34), ("Loans", "n", "int", 10), ("In home equity", "equity_share", "pct", 9), *shares], lenders)
    ws = b.sheet("Score models", f"Who used each score model on loans made in {meta['year']}, from HMDA", "A loan counts under each model it names.")
    b.table(ws, 3, [("Model named", "name", "text", 28), ("Loans", "n", "int", 11), ("In home equity", "equity_share", "pct", 9), ("Biggest users", "users", "text", 90)], [r for r in rows if r["view"] == "model"])


def _private_label(b: _Book):
    rows = _rows("private_label")
    meta = next((r for r in rows if r["view"] == "meta"), None)
    if not meta:
        return
    counts = [("Loans", "n", "int", 10), ("Classic FICO", "classic_n", "int", 10), ("Newer FICO", "fico_new_n", "int", 10), ("VS4", "vs4_n", "int", 8), ("Other VantageScore", "vs_old_n", "int", 13), ("A code or word not read", "unclear_n", "int", 11), ("None named", "blank_n", "int", 9), ("Names FICO", "fico", "pct", 9)]
    ws = b.sheet("Private-label deals", "Which model private-label deal reports name, from SEC Form ABS-15G", f"Reports filed {meta['from']} to {meta['through']}. A named model is a fact; a blank or a score column headed FICO is not. Share naming VantageScore is at the right of each row.")
    vs = ("Names VantageScore", lambda r: r["vs"], "pct", 13)
    groups = [("By month of credit report", [r for r in rows if r["view"] == "period" and r["basis"] == "pulled"]), ("By quarter filed", [r for r in rows if r["view"] == "period" and r["basis"] == "filed"]), ("By kind of deal", [r for r in rows if r["view"] == "kind"])]
    top = 3
    for title, picked in groups:
        ws.write(top, 0, title, b.fmt("text", bold=True))
        top = b.table(ws, top + 1, [("", "label", "text", 34), *counts, vs], sorted(picked, key=lambda r: r["order"])) + 1
    ws.write(top, 0, "By filer", b.fmt("text", bold=True))
    top = b.table(ws, top + 1, [("", "label", "text", 34), *counts, vs, ("Filings with a score column", "filings", "int", 11), ("With a model column", "with_model", "int", 10)], sorted((r for r in rows if r["view"] == "filer"), key=lambda r: r["rank"])) + 1
    ws = b.sheet("Private-label VantageScore", "Deals with a loan naming VantageScore, and reports naming it elsewhere", "Mentions are in a report's text or notes; each needs a read.")
    deal_rows = [r for r in rows if r["view"] == "deal"]
    top = b.table(ws, 3, [("Filed", "filed", "day", 12), ("Deal", "label", "text", 44), ("Filer", "filer", "text", 34), ("Loans", "n", "int", 9), ("VS4", "vs4_n", "int", 7), ("Other VantageScore", "vs_old_n", "int", 13), ("Filing", lambda r: ("Open", r["url"]), "link", 8)], deal_rows) + 1
    ws.write(top, 0, "Reports that name VantageScore outside a model column", b.fmt("text", bold=True))
    b.table(ws, top + 1, [("Filed", "filed", "day", 12), ("Deal", "label", "text", 44), ("Filer", "filer", "text", 34), ("Mentions", "count", "int", 9), ("", lambda r: None, "text", 7), ("", lambda r: None, "text", 13), ("Filing", lambda r: ("Open", r["url"]), "link", 8)], [r for r in rows if r["view"] == "mention"])


def _ginnie(b: _Book):
    rows = _rows("ginnie_va")
    meta = next((r for r in rows if r["view"] == "meta"), None)
    if not meta:
        return
    ws = b.sheet("VA loans at 830+", "Whose VA loans show scores Classic FICO almost never reaches, from Ginnie Mae's loan files", "Inference: no file names a model, and a VS4 score does not mean no FICO was bought. Would reach 830 if all on VS4 uses the odds at each Classic score on Fannie loans showing both scores. By closing date.")
    top = b.table(ws, 3, [("Closing month", "month", "text", 34), ("Loans", "label", "text", 34), ("VA or FHA loans", "n", "int", 10), ("At 830 or above", "k", "int", 10), ("Share", "share", "pct", 9), ("Would reach 830 if all on VS4", "full", "int", 10), ("Share of that showing", "signal", "pct", 10)], [r for r in rows if r["view"] == "month"]) + 1
    ws.write(top, 0, f"Loans closed since {meta['since']}, by lender", b.fmt("text", bold=True))
    top = b.table(ws, top + 1, [("Lender", "name", "text", 34), ("Issuer", "issuer", "text", 34), ("VA loans", "n", "int", 10), ("At 830 or above", "k", "int", 10), ("At 845 or above", "k_high", "int", 9), ("Would reach 830 if all on VS4", "full", "int", 10), ("Share of that showing", "signal", "pct", 10), ("95% upper limit", "upper", "pct", 9)], [r for r in rows if r["view"] == "lender"]) + 1
    ws.write(top, 0, f"Rough estimate of VA loans on VS4, closed {meta['m1']} and {meta['m2']}", b.fmt("text", bold=True))
    b.table(ws, top + 1, [("Loans", "label", "text", 34), ("", lambda r: None, "text", 34), ("VA loans", "n", "int", 10), ("At 830 or above", "k", "int", 10), ("Low: VS4 only when 20+ points higher", "low", "pct", 9), ("High: VS4 on every loan", "high", "pct", 10)], [r for r in rows if r["view"] == "range"])


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
    _private_label(b)
    _ginnie(b)
    _notes(b)
    _statements(b)
    b.book.close()
    return path
