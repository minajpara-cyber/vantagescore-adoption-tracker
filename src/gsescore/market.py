"""How big each piece of the mortgage market is, which score its loans use today, and what "FHA and VA follow" would mean for FICO's loans and dollars.

Private: on DASHBOARD_DATASETS only. Sizes are HMDA's rows for one year (whole_market view trend) with the GSEs' own counts for that same year from a git-ignored input file, so both sides of
every share and of the residual come from one year. A new HMDA file cannot leave an old residual behind: the pieces move to a new year only once that year's GSE counts are in the file, and a
warning says so until then. Figures are built here and never typed: outside numbers and analysis text sit in the input file, and every sentence that depends on data has a guard. The follow
table is arithmetic on stated assumptions, not a forecast. A score that does not show is unknown, so what shows VS4 only is "at most".

  data/private/market_inputs.csv  kind, key, year, value, unit, text, when, after, source, url, date, standing, order. A missing file stops nothing: the dataset then holds a meta row, the
                                  sentences that need no input, and a warning. kind: gse_count and gse_usd (fnma, fhlmc, by year); fhfa (by year: the tie-outs, and the yearly chart's
                                  Fannie and Freddie before the pieces' year); usd_share (published dollar shares); piece, part and break (text, with after replacing it once the data reaches
                                  the date in when). What FICO itself reports sits in reference/assumptions.csv.

  market_size  view meta: the year, the follow group's shares, the dollar range, the month and pulls behind the dollars, how the input file read.
               view piece: one row per piece: n, usd_bn, share_n, share_usd, share_all_n, first_lien, follow, label, note, uses (which score, in words), move (when it can move), fresh (how fresh our data is), its sources.
               view follow: today and FOLLOW_LEVELS: share of first-lien loans and FICO dollars a year, GSEs alone (gse_*) and with FHA and VA (both_*), at each of PULL_CASES, with share of FICO's revenue, as numbers and as text.
               view part: the three parts of "follow": permission, use, VS4 only. view break: what would break the assumption.
               view sentence: key, text, each under its guard here. view overview, overview_pic: the first screen's row and picture, so the two never disagree.
               view mix_year: one row per year and kind, every year built as the pieces are (by _pieces), all by the year the loan was made: HMDA's rows for that year, and for
                              Fannie and Freddie FHFA's count and dollars of the loans they bought, by the year each loan was made, in every year before the pieces' year, and their own
                              count and dollars in the pieces' year, so the latest year's rows equal the piece rows. n, usd_bn, share_n, share_usd, share_all_n, first_n and first_usd_bn
                              (that year's first-lien loans and $bn), first_lien; on the Fannie and Freddie row, basis (fhfa or own) and their own count and $bn for reference (own_n,
                              own_usd_bn). The sentences mix_caption (loans) and mix_caption_usd (dollars) say the basis and the figures behind it, each for its
                              own view.
               view mix_gap: a year on the chart's axis left out, for loans (measure n) or dollars (measure usd), with text saying why in plain words and short, a word or two for
                             its empty place. The report warns for each.
               view check: tie-outs. view warning: what the weekly report prints.
"""
import csv
import json
import re
from datetime import date
from math import ceil, isfinite
from pathlib import Path

from . import paths
from .exposure import PULL_CASES, assumption_slips, fico_dollars, fico_per_loan, usd_price
from .front import _one, shows_second, thin_gse, whose_words
from .hmda import SEGMENTS

INPUTS = paths.PRIVATE / "market_inputs.csv"
PIECES = [("gse", "Fannie and Freddie"), ("fha", "FHA"), ("va", "VA"), ("usda", "USDA"), ("other_conforming", "Other conforming size"), ("business", "Business purpose"), ("jumbo", "Jumbo")]
EQUITY_LABEL = "Home equity and second liens"
GSE_NAMES = (("fnma", "Fannie Mae"), ("fhlmc", "Freddie Mac"))
CONFORMING_ROWS = ("gse", "private", "other_buyer", "not_sold")  # HMDA's rows holding conforming-size loans sold to a GSE, another buyer or no one that year
OTHER_ROWS = ("private", "other_buyer", "not_sold")
REST_ROWS = ("usda", "jumbo", "private", "other_buyer", "not_sold", "business")  # HMDA's first-lien rows outside the GSE, FHA and VA rows
FOLLOW_LEVELS = (0.02, 0.10, 0.25, 0.50)
BOTH_SCORES_FROM = "2026-10"  # nothing issued before Oct 1, 2026 can show both scores
FHA_OPEN = "2027-01"  # FHA case numbers assigned from Jan 1, 2027
MOSTLY = 0.5
VS4_RARE = 0.01
NEAR_ZERO = 0.001
INPUT_KINDS = ("gse_count", "gse_usd", "fhfa", "usd_share", "piece", "part", "break")
VA_BEHIND = 2  # months the Ginnie Mae files can sit behind the GSE files before the weekly report says so
LEADER_MIN = 100  # GSE loans a lender needs in the two closing months for its comparison line
HMDA_URL = "https://ffiec.cfpb.gov/data-publication/snapshot-national-loan-level-dataset"
TIES = {"gse_n": 0.05, "gse_usd": 0.05, "gov_n": 0.05, "no_business_n": 0.05, "other_n": 0.15, "jumbo_n": 0.15}  # how far each piece may sit from FHFA's count before it warns
BASIS_NEAR = 0.001  # the yearly chart's captions say the GSEs' own count or dollars sit "within" this of FHFA's; from it on, by how much and which way


def pc0(v):
    return f"{v * 100:.0f}%"


def pc1(v):
    return f"{v * 100:.1f}%"


def pc2(v):
    return f"{v * 100:.2f}%"


def small(v):
    return "under 0.1%" if v < 0.001 else pc1(v)


def usd_m(v):
    return "under $1m" if v < 1e6 else f"${v / 1e6:,.0f}m"


def usd_bn(v):
    return f"${v / 1e9:,.2f}bn"


def avg_usd(v):
    return f"${v / 1e6:.2f}m" if v >= 1e6 else f"${v / 1e3:,.0f}k"


def rev_text(lo, hi):
    if lo is None or hi is None:
        return "not known"
    if hi < 0.001:
        return "under 0.1%"
    fmt = pc0 if lo >= 0.05 else pc1
    return fmt(lo) if fmt(lo) == fmt(hi) else f"{fmt(lo)} to {fmt(hi)}"


def _r(v, digits=6):
    return None if v is None else round(v, digits)


def _month(s):
    """'2026-10' or '2026-10-01' -> 'October 2026'."""
    return date(int(s[:4]), int(s[5:7]), 1).strftime("%B %Y")


def _two_months(a, b):
    if a == b:
        return _month(a)
    return f"{date(int(a[:4]), int(a[5:7]), 1).strftime('%B')} and {_month(b)}" if a[:4] == b[:4] else f"{_month(a)} and {_month(b)}"


def _day(s):
    d = date.fromisoformat(s[:10])
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _months_apart(a, b):
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def _pieces(seg: dict, gse_n: int, gse_usd: float | None) -> tuple[dict, int, float | None]:
    """One year's first-lien pieces as key -> (loans, $bn), from HMDA's rows for that year and a count and dollars of the loans Fannie and Freddie bought. Other conforming
    size is what is left of HMDA's conforming-size rows; its dollars are what is left of the year's first-lien dollars once the other six pieces are off, so the seven add to
    the year's total. The tab's pieces and the yearly chart both come from here. Also returns both remainders; a dollar remainder below zero gives that piece no dollars."""
    n_of = lambda k: (seg.get(k) or {}).get("n") or 0  # noqa: E731
    usd_of = lambda k: (seg.get(k) or {}).get("usd_bn") or 0.0  # noqa: E731
    residual = sum(n_of(k) for k in CONFORMING_ROWS) - gse_n
    residual_usd = round(usd_of("first") - gse_usd - sum(usd_of(k) for k in ("fha", "va", "usda", "business", "jumbo")), 1) if gse_usd is not None else None
    sizes = {"gse": (gse_n, gse_usd), "fha": (n_of("fha"), usd_of("fha")), "va": (n_of("va"), usd_of("va")), "usda": (n_of("usda"), usd_of("usda")),
             "other_conforming": (residual, residual_usd if residual_usd is None or residual_usd >= 0 else None), "business": (n_of("business"), usd_of("business")), "jumbo": (n_of("jumbo"), usd_of("jumbo"))}
    return sizes, residual, residual_usd


def _shares(n, usd, first_lien, first_n, first_usd, all_n) -> dict:
    """A piece's share of the year's first-lien loans and dollars, and of all home loans. One sum for the piece rows and the yearly rows."""
    return {"share_n": _r(n / first_n) if first_lien else None, "share_usd": _r(usd / first_usd) if first_lien and usd is not None and first_usd else None, "share_all_n": _r(n / all_n) if all_n else None}


def _count(n):
    """A count in millions to one place, or in full under a tenth of a million."""
    return f"{n / 1e6:.1f}m" if n >= 1e5 else f"{n:,}"


def _clause(text):
    """A sentence set after a colon: its first word in lower case, unless the sentence opens on a name."""
    return text[0].lower() + text[1:] if text.startswith("No ") else text


def _near(own, fhfa) -> str:
    """How near the GSEs' own figure for the pieces' year sits to FHFA's, the count and the dollars alike: the same; "within" BASIS_NEAR, rounded up so it holds; or from
    BASIS_NEAR on, by how much and which way. Nothing without both."""
    if not own or not fhfa:
        return ""
    off = own / fhfa - 1
    if not off:
        return ", the same as FHFA's"
    if abs(off) < BASIS_NEAR:
        return f", within {max(ceil(abs(off) * 1000 - 1e-9), 1) / 10:.1f}% of FHFA's"  # rounded up, so "within" holds
    return f", {pc1(abs(off))} {'above' if off > 0 else 'below'} FHFA's"


def _mix_caption(measure, basis, year, own, fhfa, mix_rows, gaps, hmda_latest, as_of) -> str:
    """The yearly chart's caption for one view, loans (measure n) or dollars (usd), every figure in it worked out here: whose count or dollars each year's Fannie and
    Freddie piece is, how near their own for the pieces' year sits to FHFA's (by _near), the newest year's home equity in the view's unit, each year the view leaves out
    and why, and when HMDA's next file comes out."""
    usd = measure == "usd"
    what = "dollars" if usd else "count"
    gone = {g["year"]: g["text"] for g in gaps if g["measure"] == measure}
    drawn = {y: b for y, b in basis.items() if y not in gone}  # the years this view draws, and whose figure each one is
    own_year = drawn.get(year) == "own"
    near = _near(own, fhfa) if own_year else ""
    said = []
    if "fhfa" in drawn.values():
        said.append(f"Fannie and Freddie: FHFA's {what} {'for' if usd else 'of'} the loans they bought, by the year each loan was made" + (f"; {year} is their own {what}{near}." if own_year else "."))
    elif own_year:
        said.append(f"Fannie and Freddie: their own {what} for {year}{near}.")
    if drawn:
        said.append("The rest from HMDA, by the year the loan was made.")
    size = (lambda r: f"${r['usd_bn']:,.1f}bn") if usd else (lambda r: f"{_count(r['n'])} loans")
    equity = max((r for r in mix_rows if r["key"] == "equity" and r["usd_bn" if usd else "n"]), key=lambda r: r["year"], default=None)
    said.append(f"{EQUITY_LABEL} ({size(equity)} in {equity['year']}) are not in the bars." if equity else f"{EQUITY_LABEL} are not in the bars.")
    said += [f"{y} is left out: {_clause(text)}" for y, text in sorted(gone.items())]
    nxt = hmda_latest + 1
    if nxt not in gone and (not as_of or as_of[:7] <= f"{nxt + 1}-06"):  # a next year already left out says when its file comes out
        said.append(f"HMDA's {nxt} file comes out about June {nxt + 1}.")
    return " ".join(said)


def load_inputs(path: Path | None = None) -> dict:
    """The input file's rows. A missing or unreadable file reads as no rows and a bad row is skipped, so a refresh goes on and the weekly report warns."""
    path = path or INPUTS

    def clean(r):
        out = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in r.items()}
        if None in r or (out.get("when") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", out["when"])):  # a stray comma, or a date not written 2027-01-01, would get past a string comparison and print the wrong text
            raise ValueError(r.get("key"))
        out["value"] = float(out["value"]) if out.get("value") else None
        if out["value"] is not None and not isfinite(out["value"]):
            raise ValueError(r.get("key"))
        out["year"] = int(out["year"]) if out.get("year") else None
        out["order"] = int(out["order"]) if out.get("order") else 0
        return out

    rows, bad = [], 0
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                try:
                    rows.append(clean(r))
                except ValueError:
                    bad += 1
        return {"status": "ok", "rows": rows, "bad": bad}
    except FileNotFoundError:
        return {"status": "missing", "rows": []}
    except Exception as e:
        return {"status": f"unreadable: {e!r}", "rows": []}


def _va_words(ginnie_va, closing, say):
    """Use on VA and FHA, with its dates, from Ginnie Mae's files. Needs no input file."""
    meta = next((r for r in ginnie_va if r.get("view") == "meta"), None)
    out = {"meta": meta, "use_va": None, "use_fha": None, "leaders": None, "as_of": None, "span": None, "months": None}
    if not meta:
        return out
    ranges = {r["key"]: r for r in ginnie_va if r.get("view") == "range"}
    top = meta.get("top")

    def ends(key):
        r = ranges.get(key)
        return (r["low"], r["high"]) if r and r.get("low") is not None and r.get("high") is not None else None

    def span(key):
        low, high = ends(key)
        return f"{pc0(low)} to {pc0(high)}"

    if meta.get("last_issue"):
        out["as_of"] = f"Ginnie Mae's files through issue month {_month(meta['last_issue'])}"
    if ends("all") and meta.get("m1") and meta.get("m2"):
        months = _two_months(meta["m1"], meta["m2"])
        others = [r for r in ginnie_va if r.get("view") == "month" and r.get("key") == "others" and meta.get("since") and r["month"] >= meta["since"]]
        o_k, o_n = sum(r["k"] for r in others), sum(r["n"] for r in others)
        other_words = None
        if o_n:
            other_words = f"all other lenders near zero ({o_k:,} of {o_n:,} at {top} or above since {_month(meta['since'])})" if o_k / o_n < NEAR_ZERO else f"all other lenders {pc1(o_k / o_n)} at {top} or above since {_month(meta['since'])}"
        named = [f"{meta['lead']}, retail and broker loans, {span('lead_own')}" if ends("lead_own") else None, f"{meta['second']}, all its loans, {span('second')}" if ends("second") else None, other_words]
        named = [t for t in named if t]
        out["span"], out["months"] = span("all"), months
        out["use_va"] = f"About {span('all')} of VA loans closed {months} were likely on VS4, inferred from scores at {top} or above. No file names a model." + (f" {'; '.join(named)}." if named else "")
        say("va_use", out["use_va"])

        # The same closing months at the GSEs, lender by lender: the Pricing Indicator there is a fact, the VA range an inference.
        def gse_use(name):
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            got = [r for r in closing if r.get("view") == "lender" and r.get("agency") == "All" and r.get("id") == slug and r.get("start", "")[:7] in (meta["m1"], meta["m2"])]
            n, v = sum(r["n"] for r in got), sum(r["v"] for r in got)
            return v / n if n >= LEADER_MIN else None

        def compared(name, key):
            share, got = gse_use(name), ends(key)
            if share is None or not got:
                return None
            low, high = got
            return share, "about in line with" if low <= share <= high else "above" if low > share else "well below" if high < share * 0.5 else "below"

        lead_c, second_c = compared(meta["lead"], "lead_own"), compared(meta["second"], "second")
        if lead_c and second_c:
            out["leaders"] = (f"On those closing months, {meta['lead']} priced {pc0(lead_c[0])} of its GSE loans on VS4 and {meta['second']} {pc0(second_c[0])}. "
                              f"So on VA, {meta['lead']} is {lead_c[1]} that and {meta['second']} is {second_c[1]} it.")
            say("leaders", out["leaders"])
    if meta.get("fha_n"):
        k, n = meta.get("fha_k") or 0, meta["fha_n"]
        if (meta.get("last") or "") >= FHA_OPEN:
            out["use_fha"] = f"FHA can take VS4 since January 2027, so {top} or above is no longer a clean check. {k:,} of {n:,} FHA loans in Ginnie Mae's files sit there."
            say("fha_check", "No longer a clean check: FHA can take VS4 since January 2027")
            say("fha_note", "FHA can take VS4 since January 2027, so it is no longer a clean check.")
        else:
            out["use_fha"] = f"Not in Ginnie Mae's files yet: their FHA loans closed too soon to use VS4. {k:,} of {n:,} sit at {top} or above, the check on the VA figures."
            say("fha_check", "The check: these FHA loans closed too soon to use VS4")
            say("fha_note", "FHA takes VS4 only on case numbers assigned from Jan 1, 2027, so the FHA loans in these files closed too soon to use it, which makes them the check.")
        say("fha_use", out["use_fha"])
    return out


def build_rows(whole_market, assumptions, summary, score_mix, monthly, closing, ginnie_va, private_label, inputs) -> list[dict]:
    rows, warnings, checks, sentences = [], [], [], {}
    in_rows = inputs["rows"]
    if inputs["status"] != "ok":
        warnings.append(f"market size: the input file is {inputs['status']}, so the tab shows no sizes")
    if inputs.get("bad"):
        warnings.append(f"market size: skipped unreadable rows in the input file: {inputs['bad']}")
    if inputs["status"] == "ok":
        warnings += [f"market size: the input file has no {kind} rows, so what rests on them stays off" for kind in INPUT_KINDS if not any(r.get("kind") == kind for r in in_rows)]

    def inp(kind, key, year=None):
        return next((r for r in in_rows if r["kind"] == kind and r["key"] == key and (year is None or r["year"] == year)), None)

    def value(kind, key, year=None):
        r = inp(kind, key, year)
        return r["value"] if r else None

    def gse_of(y):
        """The GSEs' own count and $bn for a year: a count only with both GSEs' counts above zero, dollars only with both GSEs' dollars."""
        fn, fh = value("gse_count", "fnma", y), value("gse_count", "fhlmc", y)
        fn_usd, fh_usd = value("gse_usd", "fnma", y), value("gse_usd", "fhlmc", y)
        return (int(fn + fh) if fn and fh else None), (round(fn_usd + fh_usd, 1) if fn_usd is not None and fh_usd is not None else None)

    def say(key, text):
        sentences[key] = text

    as_of = next((r.get("data_through") for r in summary if r.get("agency") == "All"), None)

    def dated_text(r):
        """A row's text, or what replaces it once the data has reached its date."""
        if not r:
            return None
        return r["after"] if r.get("when") and r.get("after") and as_of and as_of >= r["when"] else r.get("text")

    va = _va_words(ginnie_va, closing, say)
    say("fha_when", "FHA can take VS4 since Jan 1, 2027." if as_of and as_of[:7] >= FHA_OPEN else "FHA can take VS4 from Jan 1, 2027.")

    # ---- The year, on both sides ----
    hmda = {}
    for r in whole_market:
        if r.get("view") == "trend":
            hmda.setdefault(r["year"], {})[r["key"]] = r
    hmda_latest = max(hmda) if hmda else None
    with_counts = [y for y in hmda if (hmda[y].get("first") or {}).get("n") and value("gse_count", "fnma", y) and value("gse_count", "fhlmc", y)]
    year = max(with_counts) if with_counts else None
    head = {r["agency"]: r for r in score_mix if r.get("view") == "month" and r.get("headline")}
    month = head["All"]["start"] if head.get("All") else None
    month_row = next((r for r in monthly if r.get("agency") == "All" and r.get("month") == month), {})
    so_far = "" if month_row.get("final") else " so far"
    fnma_month = head["FNMA"]["start"] if head.get("FNMA") else month
    fnma_row = next((r for r in monthly if r.get("agency") == "FNMA" and r.get("month") == fnma_month), month_row)
    fnma_so_far = "" if fnma_row.get("final") else " so far"
    # The card counts only loans with a daily record, so a month-end file can make the month final while its "at most" still holds part of it.
    vo_far = so_far or ("" if (head.get("All") or {}).get("loans", 0) >= 0.95 * (month_row.get("scored_loans") or 0) else " so far")
    fnma_vo_far = fnma_so_far or ("" if (head.get("FNMA") or {}).get("loans", 0) >= 0.95 * (fnma_row.get("scored_loans") or 0) else " so far")
    can_show = bool(month) and month[:7] >= BOTH_SCORES_FROM
    fn_ok = not head.get("FNMA") or shows_second(head["FNMA"])  # Fannie's month shows second scores, so its VS4-only count speaks of lenders and not of the files
    thin = thin_gse(head)  # one GSE's files stop short of the month, so nothing here speaks for both in it
    meta = {"view": "meta", "ok": False, "year": year, "hmda_latest": hmda_latest, "stale": bool(year and hmda_latest and year < hmda_latest), "inputs": inputs["status"], "as_of": as_of, "month": month, "month_final": month_row.get("final"),
            "pulls_low": PULL_CASES[0], "pulls_mid": PULL_CASES[1], "pulls_high": PULL_CASES[2]}
    if hmda_latest and inputs["status"] == "ok" and year is None:
        warnings.append(f"market size: no GSE counts in the input file for any HMDA year, latest {hmda_latest}")
    if meta["stale"]:
        warnings.append(f"market size: HMDA {hmda_latest} is loaded but the input file has the GSEs' counts only through {year}, so the pieces stay on {year}. Add the {hmda_latest} counts.")

    def check(key, label, ours, theirs, limit, detail):
        gap = ours / theirs - 1 if theirs else None
        passed = gap is not None and abs(gap) <= limit
        checks.append({"view": "check", "key": key, "label": label, "ours": _r(ours, 1), "theirs": _r(theirs, 1), "gap": _r(gap, 4), "limit": limit, "pass": passed, "detail": detail})
        if not passed:
            warnings.append(f"market size: {label}: ours {ours:,.0f} against {theirs:,.0f}, past the {limit:.0%} limit")

    seg = hmda.get(year) or {}
    n_of = lambda k: (seg.get(k) or {}).get("n") or 0  # noqa: E731
    usd_of = lambda k: (seg.get(k) or {}).get("usd_bn") or 0.0  # noqa: E731
    gse_n, gse_usd = gse_of(year) if year else (None, None)
    sizes, residual, residual_usd = _pieces(seg, gse_n, gse_usd) if year else ({}, None, None)
    if year and residual < 0:
        warnings.append(f"market size: the GSEs' {year} count tops HMDA's conforming-size rows by {-residual:,}, so the sizes are held back. Check the input file.")
        say("lead", f"The GSEs' own {year} count does not fit HMDA's conforming-size rows, so the sizes are held back until the input file is checked.")
    if year and residual >= 0:

        def mix(keys, field):
            total = sum(n_of(k) for k in keys)
            return sum(((seg.get(k) or {}).get(field) or 0) * n_of(k) for k in keys) / total if total else None

        first_n, first_usd, all_n, all_usd = n_of("first"), usd_of("first"), n_of("all"), usd_of("all")
        if residual_usd is not None and residual_usd < 0:  # _pieces gives other conforming size no dollars
            warnings.append(f"market size: the GSEs' {year} dollars top HMDA's conforming-size rows, so the dollar bar is held back. Check the input file.")
        fha_n, va_n, usda_n = n_of("fha"), n_of("va"), n_of("usda")
        three_n = gse_n + fha_n + va_n
        gse_share, three_share = gse_n / first_n, three_n / first_n
        reach = three_share / gse_share if gse_share else None
        row_n, gap = n_of("gse"), gse_n - n_of("gse")
        rest_n = sum(n_of(k) for k in REST_ROWS)
        rest_fico, rest_vs4, rest_unknown = mix(REST_ROWS, "fico"), mix(REST_ROWS, "vs4"), mix(REST_ROWS, "unknown")
        rest_pct = 100 - round(three_share * 100)
        own_usd = (gse_usd + usd_of("fha") + usd_of("va")) / first_usd if gse_usd is not None and first_usd else None
        urban_g, urban_f = inp("usd_share", "urban_gse"), inp("usd_share", "urban_fha_va")
        urban = urban_g["value"] + urban_f["value"] if urban_g and urban_f and None not in (urban_g["value"], urban_f["value"]) else None
        f_ent, f_gov, f_all = value("fhfa", "enterprise_usd", year), value("fhfa", "government_usd", year), value("fhfa", "all_usd", year)
        fhfa_usd = (f_ent + f_gov - usd_of("usda")) / f_all if f_all and None not in (f_ent, f_gov) else None  # FHFA's government row holds USDA, which HMDA can take off
        usd_ends = [v for v in (urban, own_usd, fhfa_usd) if v is not None]

        # ---- The lead, and each sentence's guard ----
        fico_words = "mostly names FICO" if rest_fico is not None and rest_fico > MOSTLY else f"names FICO on {pc1(rest_fico or 0)}"
        vs4_words = "VS4 under 1%" if rest_vs4 is not None and rest_vs4 < VS4_RARE else f"VS4 on {pc1(rest_vs4 or 0)}"
        lead_line = f"{pc0(three_share)} with FHA and VA, and the other {rest_pct}% {fico_words}, with {vs4_words} ({year})."
        say("lead", f"Fannie and Freddie are {pc1(gse_share)} of first-lien loans, {lead_line}")
        if len(usd_ends) > 1:
            said = [f"{pc0(urban)} on Urban's {urban_g.get('text') or 'latest'} split" if urban is not None else None, f"{pc1(own_usd)} from HMDA and the GSEs' own figures for {year}" if own_usd is not None else None, f"{pc0(fhfa_usd)} on FHFA's {year} database, less USDA" if fhfa_usd is not None else None]
            dollars = f"By dollars, Fannie, Freddie, FHA and VA are {pc0(min(usd_ends))} to {pc0(max(usd_ends))}: {'; '.join(t for t in said if t)}."
        else:
            dollars = f"By dollars, Fannie, Freddie, FHA and VA are {pc0(usd_ends[0])}." if usd_ends else None
        if dollars:
            jumbo_avg, gse_avg = usd_of("jumbo") * 1e9 / n_of("jumbo") if n_of("jumbo") else None, gse_usd * 1e9 / gse_n if gse_usd is not None and gse_n else None
            if jumbo_avg and gse_avg and jumbo_avg > gse_avg:
                dollars += f" Jumbo loans average {avg_usd(jumbo_avg)} against {avg_usd(gse_avg)} at the GSEs, and FICO is paid per score, not by loan size."
            say("dollars", dollars)
        if n_of("equity"):
            say("all_loans", f"Fannie, Freddie, FHA and VA are {pc0(three_n / all_n)} of all {all_n:,} home loans if you count home equity and second liens.")
        if all((value("fhfa", "all_n", year), value("fhfa", "enterprise_n", year), value("fhfa", "government_n", year))):
            say("fhfa_count", f"On FHFA's count, where it says investor loans are not as well represented, Fannie, Freddie, FHA and VA are {pc1((value('fhfa', 'enterprise_n', year) + value('fhfa', 'government_n', year) - usda_n) / value('fhfa', 'all_n', year))} of first-lien loans.")
        row_label = dict(SEGMENTS)["gse"]
        if gap > 0:
            say("hmda_gap", f"HMDA's row \"{row_label}\" holds {row_n:,} loans, {pc1(row_n / first_n)} of first-lien, because it counts only a sale straight to them in the same calendar year. The GSEs' own {year} count is {gse_n:,}, {pc1(gse_share)}. The other {gap:,} mostly sit in HMDA's rows for other buyers, private securitizers and loans not sold that year, which is why other conforming size here is what is left.")
        else:
            say("hmda_gap", f"HMDA's row \"{row_label}\" holds {row_n:,} loans, at or above the GSEs' own {year} count of {gse_n:,}. Check the input file.")
            warnings.append(f"market size: HMDA's GSE row ({row_n:,}) is at or above the GSEs' own {year} count ({gse_n:,})")
        if rest_fico is not None:
            say("rest_mix", f"On HMDA's first-lien rows outside Fannie, Freddie, FHA and VA, {rest_n:,} loans in {year}, {pc1(rest_fico)} name a FICO model and {pc2(rest_vs4)} name VS4. {pc1(rest_unknown)} name no model." + (f" About {round(gap, -3):,} of those loans reach the GSEs another way, which is why this row is bigger than the other {rest_pct}%." if gap > 0 else ""))
        if reach:
            say("reach", f"If FHA and VA follow, any level of VS4 only at the GSEs reaches {reach:.1f} times as much of the market's first-lien loans.")
        total = gse_n + fha_n + va_n + usda_n + residual + n_of("business") + n_of("jumbo")
        if total != first_n:
            warnings.append(f"market size: the pieces add to {total:,}, not HMDA's {first_n:,} first-lien loans")
        meta |= {"ok": True, "pieces_add": total == first_n, "first_n": first_n, "first_usd_bn": first_usd, "all_n": all_n, "all_usd_bn": all_usd, "gse_n": gse_n, "gse_usd_bn": gse_usd, "gse_share": _r(gse_share), "three_n": three_n, "three_share": _r(three_share), "three_all_share": _r(three_n / all_n),
                 "reach": _r(reach, 3), "rest_n": rest_n, "rest_fico": _r(rest_fico), "rest_vs4": _r(rest_vs4), "row_n": row_n, "row_share": _r(row_n / first_n), "gap_n": gap, "residual_n": residual, "usd_urban": _r(urban), "usd_own": _r(own_usd), "usd_fhfa": _r(fhfa_usd),
                 "usd_low": _r(min(usd_ends)) if usd_ends else None, "usd_high": _r(max(usd_ends)) if usd_ends else None, "next_file": hmda_latest + 2}

        # ---- One row per piece ----
        hmda_fresh = f"HMDA {year}. HMDA {hmda_latest} is loaded and waits on the GSEs' counts." if meta["stale"] else f"HMDA {year}." if as_of and as_of[:7] > f"{hmda_latest + 2}-06" else f"HMDA {year}, next file about June {hmda_latest + 2}."
        pl_meta = next((r for r in private_label if r.get("view") == "meta"), None)

        def hmda_words(keys, extra=""):
            fico, vs4 = mix(keys, "fico"), mix(keys, "vs4")
            return f"HMDA {year}: {pc1(fico)} name a FICO model, {small(vs4)} VS4.{extra}" if fico is not None else None

        gse_words = None
        if head.get("All"):
            priced = month_row.get("vs4_share") if month_row.get("vs4_share") is not None else head["All"].get("vs4_priced_share")
            only = head.get("FNMA", {}).get("vs_only_share") if fn_ok else None
            gse_words = f"Priced on VS4: {pc1(priced)} of loans issued {_month(month)}{so_far}{f', {whose_words(thin, head)}' if thin else ''}." + (f" Shows VS4 only: at most {_one(only)} at Fannie." if can_show and only is not None else "")
        va_extra = f" Since then: about {va['span']} of loans closed {va['months']} likely on VS4, inferred from scores." if va["use_va"] else ""
        none_share = mix(("business",), "none")
        uses = {"gse": gse_words, "fha": hmda_words(("fha",)), "va": hmda_words(("va",), va_extra), "usda": hmda_words(("usda",)), "other_conforming": hmda_words(OTHER_ROWS, " Measured on the HMDA rows that hold this piece, which also hold loans that reach the GSEs another way."),
                "business": hmda_words(("business",), f" No score reported on {pc1(none_share)}." if (none_share or 0) >= 0.2 else ""), "jumbo": hmda_words(("jumbo",))}
        notes = {"gse": "Their own count, not HMDA's row", "other_conforming": "What is left of HMDA's conforming-size rows after the GSEs' own count: bank and credit union portfolio, private label and others", "business": "HMDA's row, outside the GSE, FHA, VA and USDA rows"}
        fresh = {key: hmda_fresh for key, _ in PIECES}
        if as_of:
            lasts = {r.get("agency"): r.get("data_through") for r in summary}
            fn_last, fh_last = lasts.get("FNMA"), lasts.get("FHLMC")
            fresh["gse"] = f"Scores: daily files, through {f'{_day(fn_last)} at Fannie, {_day(fh_last)} at Freddie' if fn_last and fh_last and fn_last != fh_last else _day(as_of)}. Size: {year} counts."
        if va["as_of"]:
            fresh["fha"] = f"{hmda_fresh} {va['as_of']}, no model named."
            fresh["va"] = f"{hmda_fresh} {va['as_of']}, no model named."
        if pl_meta and pl_meta.get("through"):
            fresh["other_conforming"] = f"{hmda_fresh} Private-label deal reports weekly, filed through {_day(pl_meta['through'])}, on loans about {pl_meta['lag_months']} months older."

        def piece_row(key, order, label, n, usd, first_lien, words, fresh_words, note):
            text_row = inp("piece", key) or {}
            own = (inp("gse_count", "fnma", year), inp("gse_count", "fhlmc", year)) if key == "gse" else (None, None)
            return {"view": "piece", "key": key, "order": order, "label": label, "note": note, "first_lien": first_lien, "follow": key in ("gse", "fha", "va"), "n": n, "usd_bn": usd, **_shares(n, usd, first_lien, first_n, first_usd, all_n),
                    "uses": words, "move": dated_text(text_row), "fresh": fresh_words, "standing": text_row.get("standing"), "size_src_label": f"Size: {own[0]['source']}" if own[0] else ("HMDA" if key != "other_conforming" else "HMDA less the GSEs' counts"), "size_src_url": own[0]["url"] if own[0] else HMDA_URL,
                    "size2_src_label": own[1]["source"] if own[1] else None, "size2_src_url": own[1]["url"] if own[1] else None, "move_src_label": text_row.get("source"), "move_src_url": text_row.get("url")}

        for order, (key, label) in enumerate(PIECES):
            if sizes[key][0]:  # a piece with no loans that year gets no row
                rows.append(piece_row(key, order, label, sizes[key][0], sizes[key][1], True, uses[key], fresh[key], notes.get(key)))
        if n_of("equity"):
            eq = seg["equity"]
            rows.append(piece_row("equity", len(PIECES), EQUITY_LABEL, n_of("equity"), usd_of("equity"), False, f"HMDA {year}: {pc1(eq['fico'])} name a FICO model, {pc1(eq['vs4'])} VS4.", hmda_fresh, "Not first-lien. Dollars count a line at its limit"))
        if pl_meta and pl_meta.get("n"):
            say("private_label", f"Private-label deals cut across other conforming size, jumbo and business purpose. Of {pl_meta['n']:,} loans in deal reports filed {_day(pl_meta['from'])} to {_day(pl_meta['through'])}, {pc2(pl_meta['vs'])} name VantageScore, updated weekly.")

        # ---- If FHA and VA follow ----
        a = {r["key"]: r["value"] for r in assumptions}
        # With no month-end file yet, the data's own two inputs read zero: a thin input, so the table waits and says so.
        if all(a.get(k) is not None for k in ("bureaus", "borrowers_per_loan", "price_per_score", "closing_fee", "gse_loans_year")) and all(a[k] > 0 for k in ("bureaus", "borrowers_per_loan", "price_per_score", "gse_loans_year")):
            gse_year = a["gse_loans_year"]
            total_q = a.get("fico_total_q")
            rev_base = total_q * 4e6 if total_q else (a.get("fico_revenue_year") or 0) * 1e6
            rev_label = f"FICO's latest reported quarter times four, {usd_bn(rev_base)}" if total_q else f"FICO's fiscal guide, {usd_bn(rev_base)}"
            rev_share = lambda v: v / rev_base if rev_base else None  # noqa: E731
            low, high = PULL_CASES[0], PULL_CASES[-1]

            def follow_row(key, order, x, label, assumed):
                gse_at = {p: fico_dollars(gse_year, x, a, pulls=p) for p in PULL_CASES}
                both_at = {p: fico_dollars(gse_year + fha_n + va_n, x, a, pulls=p) for p in PULL_CASES} if assumed else None
                r = {"view": "follow", "key": key, "order": order, "label": label, "x": _r(x), "assumed": assumed, "gse_share": _r(x * gse_share), "both_share": _r(x * three_share) if assumed else None, "gse_share_text": pc1(x * gse_share), "both_share_text": pc1(x * three_share) if assumed else "cannot be seen", "pair_text": f"{pc1(x * gse_share)}, then {pc1(x * three_share)}" if assumed else f"{pc1(x * gse_share)}, GSEs alone",
                     "gse_rev_low": _r(rev_share(gse_at[low])), "gse_rev_high": _r(rev_share(gse_at[high])), "gse_rev_text": rev_text(rev_share(gse_at[low]), rev_share(gse_at[high])), "both_rev_low": _r(rev_share(both_at[low])) if assumed else None, "both_rev_high": _r(rev_share(both_at[high])) if assumed else None,
                     "both_rev_text": rev_text(rev_share(both_at[low]), rev_share(both_at[high])) if assumed else "cannot be seen"}
                for p in PULL_CASES:
                    r |= {f"gse_p{p}": round(gse_at[p]), f"gse_p{p}_text": usd_m(gse_at[p]), f"both_p{p}": round(both_at[p]) if assumed else None, f"both_p{p}_text": usd_m(both_at[p]) if assumed else "cannot be seen"}
                return r

            order = 0
            if can_show and not fn_ok:
                warnings.append(f"market size: Fannie's {_month(fnma_month)} files show too few second scores, so the \"Shows VS4 only, at most\" rows are held back")
            if can_show and fn_ok and head.get("FNMA", {}).get("vs_only_share") is not None:
                rows.append(follow_row("today_fnma", order, head["FNMA"]["vs_only_share"], f"Today: Fannie's at most {_one(head['FNMA']['vs_only_share'])}, if Freddie were the same, loans issued {_month(fnma_month)}{fnma_vo_far}", False))
                order += 1
            if can_show and fn_ok and not thin and head.get("All", {}).get("vs_only_share") is not None:
                same_loans = order and (fnma_month, fnma_vo_far) == (month, vo_far)
                rows.append(follow_row("today_both", order, head["All"]["vs_only_share"], f"Today: at most {_one(head['All']['vs_only_share'])} at both GSEs, the ceiling, " + ("same month" if same_loans else f"loans issued {_month(month)}{vo_far}"), False))
                order += 1
            for x in FOLLOW_LEVELS:
                rows.append(follow_row(f"x{round(x * 100):02d}", order, x, pc0(x), True))
                order += 1
            per = {p: fico_per_loan(a["bureaus"], a["borrowers_per_loan"], p, a["price_per_score"], a["closing_fee"]) for p in PULL_CASES}
            point = {p: fico_dollars(gse_year, 0.01, a, pulls=p) for p in PULL_CASES}
            both_point = {p: fico_dollars(gse_year + fha_n + va_n, 0.01, a, pulls=p) for p in PULL_CASES}
            tax, shares = a.get("fico_tax_rate"), a.get("fico_shares_q")
            eps = f", or ${point[low] * (1 - tax) / shares / 1e6:.2f} to ${point[high] * (1 - tax) / shares / 1e6:.2f} of EPS at full flow-through ({tax * 100:g}% tax, {shares:.2f}m shares)" if tax is not None and shares else ""
            fee_words = " and no fee on a funded loan" if not a["closing_fee"] else f" and {usd_price(a['closing_fee'])} on a funded loan"
            say("basis", f"Each point of VS4 only at the GSEs is about {round(gse_year * 0.01, -2):,.0f} loans a year times ${per[low]:,.0f} to ${per[high]:,.0f} ({low} to {high} credit pulls per funded loan, {a['bureaus']:.0f} bureaus, {a['borrowers_per_loan']:.2f} borrowers, {usd_price(a['price_per_score'])} a score{fee_words}). "
                         f"That is {usd_m(point[low])} to {usd_m(point[high])} a year{eps}. It assumes that price and that no pull behind a loan with VS4 only bought FICO. Dollars use the GSEs' pace of {gse_year / 1e6:.2f}m loans a year and FHA and VA's {year} counts. Shares use {year}'s {gse_n / 1e6:.2f}m GSE loans. Share of revenue is of {rev_label}. This is arithmetic, not a forecast.")
            mortgage_year = a["fico_mortgage_q"] * 4e6 if a.get("fico_mortgage_q") else None
            implied = (mortgage_year / ((gse_year + first_n - gse_n) * a["bureaus"] * a["borrowers_per_loan"]) - a["closing_fee"]) / a["price_per_score"] if mortgage_year else None
            if implied and implied > 0:
                fits = PULL_CASES[0] <= implied <= PULL_CASES[1] + 0.5
                say("pulls_check", f"FICO's mortgage origination revenue of {usd_bn(mortgage_year)} a year, its latest reported quarter times four, is about {implied:.1f} pulls on every first-lien loan at these counts, with nothing for home equity." + (f" So {PULL_CASES[0]} to {PULL_CASES[1]} pulls fits its revenue and {PULL_CASES[2]} is the outer case." if fits else f" That sits outside {PULL_CASES[0]} to {PULL_CASES[1]} pulls, so take the pull columns with care."))
                if not fits:
                    warnings.append(f"market size: FICO's revenue now points to about {implied:.1f} pulls per first-lien loan, outside {PULL_CASES[0]} to {PULL_CASES[1]}")
            meta |= {"gse_year": _r(gse_year, 1), "point_loans": round(gse_year * 0.01), "rev_base": round(rev_base), "implied_pulls": _r(implied, 2), **{f"per_p{p}": _r(per[p], 2) for p in PULL_CASES}, **{f"point_p{p}": round(point[p]) for p in PULL_CASES}, **{f"both_point_p{p}": round(both_point[p]) for p in PULL_CASES}}
        else:
            warnings.append("market size: an assumption the follow table needs is missing, so it has no rows")

        # ---- Tie-outs ----
        fhfa = lambda key: value("fhfa", key, year)  # noqa: E731
        if fhfa("enterprise_n"):
            check("gse_n", f"The GSEs' own {year} count against FHFA's Enterprise acquisitions", gse_n, fhfa("enterprise_n"), TIES["gse_n"], "FHFA's National Mortgage Database")
        if gse_usd is not None and fhfa("enterprise_usd"):
            check("gse_usd", f"The GSEs' own {year} dollars against FHFA's, $bn", gse_usd, fhfa("enterprise_usd"), TIES["gse_usd"], "FHFA's National Mortgage Database")
        if fhfa("government_n"):
            check("gov_n", f"HMDA's FHA, VA and USDA loans in {year} against FHFA's government count", fha_n + va_n + usda_n, fhfa("government_n"), TIES["gov_n"], "FHFA's National Mortgage Database")
        if fhfa("all_n"):
            check("no_business_n", f"HMDA's first-lien loans in {year} without business purpose against FHFA's count", first_n - n_of("business"), fhfa("all_n"), TIES["no_business_n"], "FHFA says investor loans are not as well represented in its credit-file sample, so business-purpose loans come off HMDA's side (an inference)")
        if fhfa("other_n"):
            check("other_n", f"Other conforming size, what is left, against FHFA's other conforming in {year}", residual, fhfa("other_n"), TIES["other_n"], "A wide limit: this piece is what is left")
        if fhfa("jumbo_n"):
            check("jumbo_n", f"HMDA's jumbo loans in {year} against FHFA's", n_of("jumbo"), fhfa("jumbo_n"), TIES["jumbo_n"], "HMDA's jumbo row leaves out jumbo loans it counts as FHA, VA or business purpose")

        # ---- The first screen reads these two views, so it and this tab never disagree ----
        over_line = f"The other {rest_pct}% {fico_words}, with {vs4_words} ({year})." + (f" If FHA and VA follow, any level of VS4 only at the GSEs reaches {reach:.1f} times as much." if reach else "")
        rows.append({"view": "overview", "key": "market", "label": "Rest of the market", "big": f"{pc1(gse_share)} → {pc0(three_share)}", "big_value": _r(gse_share), "big_unit": "share", "big_what": f"of {year} first-lien loans: Fannie and Freddie by their own count, then with FHA and VA if they follow", "line": over_line, "year": year})
        rows += [{"view": "overview_pic", "order": i, "key": k, "label": label, "value": _r(v / first_n), "n": v, "what": f"Share of {first_n:,} first-lien loans, {year}"} for i, (k, label, v) in enumerate((("gse", "Fannie and Freddie", gse_n), ("fha", "FHA", fha_n), ("va", "VA", va_n), ("rest", "Everything else", first_n - three_n)))]

    # ---- First-lien loans made each year, by kind, every piece on the year the loan was made. Before the pieces' year, Fannie and Freddie are FHFA's count of the loans
    # they bought, by the year each was made; the pieces' year keeps their own count, so its bar equals the size bar, and the caption says how near FHFA's that count sits.
    # Their own count rides on each year's row for reference only, so where it and FHFA's differ in a past year (the timing this basis fixes) nothing warns. Every year is
    # built by _pieces. The axis runs from the first year to the last with HMDA rows or a count of their own; a year that cannot be built keeps its place, says why in a
    # sentence and in a short word for its empty place, and the report warns. ----
    gse_years = {r["year"] for r in in_rows if r["kind"] == "gse_count" and r["year"]}
    if gse_years:  # no counts at all: the warning on the input file says so once
        span = sorted(set(hmda) | gse_years)
        mix_rows, gaps, basis = [], [], {}

        def mix_row(y, s, key, order, label, n, usd, first_lien, **more):
            first_y, first_usd_y, all_y = (s.get("first") or {}).get("n") or 0, (s.get("first") or {}).get("usd_bn") or 0.0, (s.get("all") or {}).get("n") or 0
            return {"view": "mix_year", "key": key, "year": y, "order": order, "label": label, "first_lien": first_lien, "n": n, "usd_bn": usd, **_shares(n, usd, first_lien, first_y, first_usd_y, all_y),
                    "first_n": first_y, "first_usd_bn": first_usd_y, **more}

        def names(kind, y, have):
            return " or ".join(name for key, name in GSE_NAMES if not have(value(kind, key, y)))

        for y in range(span[0], span[-1] + 1):
            s = hmda.get(y) or {}
            own_n, own_usd = gse_of(y)
            on_fhfa = year is not None and y < year  # the pieces' year, and any after it, stay on their own count
            if on_fhfa:
                f_n, f_usd = value("fhfa", "enterprise_n", y), value("fhfa", "enterprise_usd", y)
                g_n, g_usd = (int(f_n) if f_n else None), (f_usd or None)
                count_words, usd_words = f"FHFA's {y} count for Fannie and Freddie", f"FHFA's {y} dollars for Fannie and Freddie"
                whose_n, whose_usd = f"FHFA's {y} count for the GSEs", f"FHFA's {y} dollars for the GSEs"
            else:
                g_n, g_usd = own_n, own_usd
                count_words, usd_words = f"Fannie and Freddie's own {y} count", f"Fannie and Freddie's own {y} dollars"
                whose_n, whose_usd = f"the GSEs' {y} count", f"the GSEs' {y} dollars"
            whys, said, short = [], [], []  # the hover's and the caption's words, the report's, and a word for the empty place on the axis
            if not (s.get("first") or {}).get("n"):
                if s:
                    whys.append(f"HMDA's {y} rows hold no first-lien loans.")
                    short.append("file incomplete")
                elif hmda_latest is None or y > hmda_latest:
                    due_y = not as_of or as_of[:7] <= f"{y + 1}-06"
                    whys.append(f"HMDA's {y} file comes out about June {y + 1}." if due_y else f"HMDA's {y} file is not loaded yet.")
                    short.append("no file yet" if due_y else "not loaded")
                else:
                    whys.append(f"HMDA's {y} file is not loaded.")
                    short.append("not loaded")
                said.append("no HMDA first-lien rows for it")
            if not g_n:
                if on_fhfa:
                    whys.append(f"No {y} count from FHFA yet.")
                    said.append(f"the input file has no FHFA count for {y}")
                else:
                    missing = names("gse_count", y, bool)
                    whys.append(f"No {y} count from {missing} yet.")
                    said.append(f"the input file has no {y} count for {missing}")
                short.append("no count yet")
            if not whys:
                sizes_y, residual_y, residual_usd_y = _pieces(s, g_n, g_usd)
                if residual_y < 0:
                    whys.append(f"{count_words} is more than all of HMDA's conforming-size loans that year, so the year is held back.")
                    said.append(f"{whose_n} tops HMDA's conforming-size rows by {-residual_y:,}. Check the input file.")
                    short.append("held back")
            if whys:
                gaps += [{"view": "mix_gap", "year": y, "measure": m, "text": " ".join(whys), "short": short[0]} for m in ("n", "usd")]
                warnings.append(f"market size: the yearly chart leaves out {y}: {'; '.join(said)}")
                continue
            basis[y] = "fhfa" if on_fhfa else "own"
            for order, (key, label) in enumerate(PIECES):
                if sizes_y[key][0]:  # as on the pieces: a kind with no loans that year gets no row
                    more = {"basis": basis[y], "own_n": own_n, "own_usd_bn": own_usd} if key == "gse" else {}
                    mix_rows.append(mix_row(y, s, key, order, label, *sizes_y[key], True, **more))
            if (s.get("equity") or {}).get("n"):
                mix_rows.append(mix_row(y, s, "equity", len(PIECES), EQUITY_LABEL, s["equity"]["n"], s["equity"].get("usd_bn") or 0.0, False))
            if g_usd is None:
                missing = "FHFA" if on_fhfa else names("gse_usd", y, lambda v: v is not None)
                gaps.append({"view": "mix_gap", "year": y, "measure": "usd", "text": f"No {y} dollar figure from {missing} yet.", "short": "no dollars yet"})
                warnings.append(f"market size: the yearly chart leaves out {y}'s dollars: the input file has no {y} dollars {'from FHFA' if on_fhfa else f'for {missing}'}")
            elif residual_usd_y < 0:
                gaps.append({"view": "mix_gap", "year": y, "measure": "usd", "text": f"{usd_words} are more than all of HMDA's conforming-size dollars that year, so the year's dollars are held back.", "short": "held back"})
                warnings.append(f"market size: the yearly chart leaves out {y}'s dollars: {whose_usd} top HMDA's conforming-size rows. Check the input file.")
        if mix_rows:  # with no year to draw, the card stays off and the warnings above say why
            rows += mix_rows + gaps
            ours = dict(zip(("n", "usd"), gse_of(year) if year else (None, None)))
            for key, measure, fhfa_key in (("mix_caption", "n", "enterprise_n"), ("mix_caption_usd", "usd", "enterprise_usd")):  # one sentence for each view, worked out alike
                say(key, _mix_caption(measure, basis, year, ours[measure], value("fhfa", fhfa_key, year) if year else None, mix_rows, gaps, hmda_latest, as_of))

    g_meta = va["meta"]
    if g_meta and g_meta.get("last_issue") and as_of and _months_apart(g_meta["last_issue"], as_of) > VA_BEHIND:
        warnings.append(f"market size: Ginnie Mae's files stop at issue month {g_meta['last_issue']}, {_months_apart(g_meta['last_issue'], as_of)} months behind the GSE files. The VA figures need new files, through your sign-in.")

    # ---- The three parts of "follow" ----
    parts = [("permission_fha", "permission", "Permission", "FHA", dated_text(inp("part", "permission_fha")), False), ("permission_va", "permission", "Permission", "VA", dated_text(inp("part", "permission_va")), False),
             ("use_fha", "use", "Use", "FHA", va["use_fha"], True), ("use_va", "use", "Use", "VA", va["use_va"], True), ("use_leaders", "use", "Use", "VA", va["leaders"], True), ("use_why", "use", "Use", "Both", dated_text(inp("part", "use_why")), False), ("first_pull", "use", "Use", "GSEs too", dated_text(inp("part", "first_pull")), False),
             ("vs4_only", "vs4_only", "VS4 only", "FHA and VA", dated_text(inp("part", "vs4_only")), False)]
    for order, (key, part_key, part_label, program, text, computed) in enumerate(parts):
        if text:
            src = inp("part", key) or {}
            rows.append({"view": "part", "key": key, "order": order, "part": part_key, "part_label": part_label, "program": program, "text": text, "computed": computed, "as_of": va["as_of"] if computed else None, "src_label": src.get("source"), "src_url": src.get("url"), "date": src.get("date"), "standing": "inference" if computed else src.get("standing")})
    for r in sorted((r for r in in_rows if r["kind"] == "break"), key=lambda r: r["order"]):
        rows.append({"view": "break", "key": r["key"], "order": r["order"], "text": dated_text(r), "src_label": r.get("source"), "src_url": r.get("url"), "date": r.get("date"), "standing": r.get("standing")})
    rows += [{"view": "sentence", "key": k, "text": v} for k, v in sentences.items()]
    rows += checks
    rows += [{"view": "warning", "text": w} for w in warnings]
    rows.insert(0, meta)
    keys = sorted({k for r in rows for k in r})
    return [{k: r.get(k) for k in keys} for r in rows]


def _file_rows(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text())["rows"]
    except FileNotFoundError:
        return []


def build_datasets(more: dict | None = None, out_dir: Path = paths.SITE_DATA) -> dict[str, list[dict]]:
    """From the rows built so far in this run (more), else the files already in out_dir, so `gsescore ginnie` can rebuild this one alone."""
    more = more or {}
    read = lambda name: more[name] if name in more else _file_rows(out_dir / f"{name}.json")  # noqa: E731
    try:
        return {"market_size": build_rows(read("whole_market"), read("assumptions"), read("summary"), read("score_mix"), read("monthly"), read("closing"), read("ginnie_va"), read("private_label"), load_inputs())}
    except Exception as e:  # a shape this builder did not foresee stops nothing: the tab holds its sizes back and the weekly report says why
        return {"market_size": [{"view": "meta", "ok": False, "text": None}, {"view": "warning", "ok": None, "text": f"market size: could not build the dataset: {e!r}"}]}


def market_warnings(out_dir: Path = paths.SITE_DATA) -> list[str]:
    """What the weekly report prints from the dataset. Never raises."""
    try:
        return assumption_slips() + [r["text"] for r in _file_rows(out_dir / "market_size.json") if r.get("view") == "warning"]
    except Exception as e:
        return [f"market size: could not read market_size.json: {e!r}"]
