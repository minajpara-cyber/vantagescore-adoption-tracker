"""Loans sold to private securitizers, from the federal HMDA record, for the private-label view of the Rest of market tab, beside the SEC deal reports.

Private: on DASHBOARD_DATASETS only. Built from data/hmda/<year>.parquet for every year on disk, with hmda.py's definitions: loans made (action taken 1), multifamily and reverse
mortgages left out as SEGMENT_SQL leaves them, the score model by MODEL_SQL (tried in order, so a named VantageScore is never hidden), kinds by KIND_SQL, and lender names as
the Whole market view resolves them: the latest year's filed name, by legal entity, through short_name. A private securitizer is purchaser type 5. The buyers outside Fannie (1),
Ginnie (2), Freddie (3) and Farmer Mac (4) are types 5, 6, 71, 72, 8 and 9; type 0 is a loan not sold that year.

What HMDA can show: the buyer is whoever bought the loan in the calendar year it was made, so a loan sold the next year shows as not sold and one sold through an aggregator shows
the aggregator. Its form names VS4 only from VS4_ON_FORM, so in earlier years a loan on VS4 shows under another model. A named model is a fact; "more than one model", "other
model" and a score not reported are unknown, never FICO. A year's file comes out lender by lender (each lender's modified LAR) and as one combined file by March 31 the year
after, and carries the buyer and the score model on each loan; the national file follows about June. Lender names print as the Whole market view resolves them, with the
few that file oddly tidied here only (LABELS), as the public datasets keep short_name's.

  pl_hmda  view meta: the latest year and the one before, the first year on disk, file_date (the day the latest year's national data were frozen, hmda.YEAR_FILES) and
                      national_released (the day that file came out), the latest year's loans, $bn and shares, its VS4 loans, the loans sold outside the four that year
                      and their VS4 loans, lenders and VS4 loans sold to a private securitizer, the first year the form named VS4 (vs4_form_year), and when the next
                      year's files come out.
           view year: one row per year on disk, loans sold to private securitizers that year: n, usd_bn, the shares classic, fico_new, vs4, vs_old, multi, other, none and the sums
                      fico, vs, unnamed (multi + other) and unknown (unnamed + none), vs4_n, and vs4_on_form (whether the form named VS4 that year).
           view kind: the latest two years by kind of loan (KIND_SQL), the same fields and the kind's share of its year (share).
           view lender: the PL_TOP lenders selling the most to private securitizers in the latest year, by legal entity: the same fields and equity_share, with the year before
                        (prior_n, prior_usd_bn, prior_classic, prior_vs4_n; none where the entity sold none to them) and prior_unsold, the share of its loans made the
                        year before that it reported as not sold that year, and prior_mark, set past UNSOLD_MARK, when its count the year before is not comparable and
                        the page marks it.
           view vs4_lender: every lender that put VS4 on a loan sold to a buyer outside the four in the latest year: n (its loans sold to those buyers), vs4_n and vs4 (their share),
                            private_vs4_n (to private securitizers), and buyer, the kind of buyer that took most of its VS4 loans.
           view sentence: key, text, each under its guard here: form, kinds, dips (under the chart: VantageScore's share and where FICO's dips come from), vs4_tile,
                          route (the SEC reports' VS4 loans against HMDA's none: how many also name a FICO model, the deals of those naming VS4 alone, their credit
                          report years, and why HMDA's none can still hold; route_words, from private_label's counts), outside, unsold (the marked counts), next.
                          view warning: a build that stopped, for the weekly report.
"""
import json
from datetime import date
from pathlib import Path

import duckdb

from . import paths
from .edgar import deal_label
from .hmda import KIND_SQL, KINDS, MODEL_SQL, SEGMENT_SQL, SHARES, YEAR_FILES, short_name

PRIVATE = 5  # HMDA's purchaser type for a private securitizer
OUTSIDE = (5, 6, 71, 72, 8, 9)  # every buyer but Fannie (1), Ginnie (2), Freddie (3) and Farmer Mac (4); 0 is not sold that year
BUYERS = {5: "Private securitizer", 6: "Bank or savings institution", 71: "Credit union, mortgage or finance company", 72: "Life insurer", 8: "Affiliate", 9: "Other buyer"}
PL_TOP = 15
VS4_ON_FORM = 2024  # HMDA's filing form names VantageScore 4.0 (code 15) from data collected in 2024: the 2024 Filing Instructions Guide added it with FICO 8, 10 and 10T
LENDER_FILE_DAY = "03-31"  # a year's file, lender by lender and as one combined file, by March 31 the year after: the CFPB says the statute requires it (2025's came Mar 31, 2026)
NATIONAL_MONTH = 6  # the national file about June the year after (2025's data froze Jun 2, 2026, and came out Jun 23, 2026)
NATIONAL_RELEASED = {2025: "2026-06-23"}  # the day each year's national file came out, from the FFIEC's news page; YEAR_FILES has the day its data froze
UNSOLD_MARK = 0.5  # a seller that reported more of the year before's loans than this as not sold that year has a count that year not comparable with the latest
VS_RARE = 0.01  # VantageScore under this share of the loans every year is said to stay under 1%
ALONE_DEALS = 4  # the most deals the sentence on the SEC reports names for their loans naming VS4 alone; past this, it counts them
# Filed names that print oddly through short_name, as this view shows them; the Whole market view and its public file keep short_name's.
LABELS = {"Spring Eq": "Spring EQ", "Lendage, Llc Dba Achieve Loans": "Achieve Loans (Lendage)", "Hopewell Federal Cu": "Hopewell Federal Credit Union",
          "Industrial Federal C. U": "Industrial Federal Credit Union"}
LENDER_FILE_URL = "https://ffiec.cfpb.gov/data-publication/modified-lar"
KIND_WORDS = {"conforming": "conforming size", "jumbo": "jumbo", "fha": "FHA", "va": "VA", "usda": "USDA", "business": "business purpose", "equity": "home equity and second liens"}
KIND_MIN = 0.1  # a kind named in the sentence on kinds; the three biggest at most
FAMILY_SUMS = {"fico": ("classic", "fico_new"), "vs": ("vs4", "vs_old"), "unnamed": ("multi", "other"), "unknown": ("multi", "other", "none")}


def _r(v, digits=6):
    return None if v is None else round(v, digits)


def pc1(v):
    return f"{v * 100:.1f}%"


def pc2(v):
    return f"{v * 100:.2f}%"


def _bn(v):
    return round((v or 0) / 1e9, 4)


def _mix(counts: dict, n: int) -> dict:
    """Each model family's share of n, and the four sums, from the counts (k_n); none of them without loans."""
    if not n:
        return dict.fromkeys([*SHARES, *FAMILY_SUMS])
    return {**{k: _r(counts[f"{k}_n"] / n) for k in SHARES}, **{k: _r(sum(counts[f"{p}_n"] for p in parts) / n) for k, parts in FAMILY_SUMS.items()}}


def _day(s):
    d = date.fromisoformat(s)
    return f"{d:%B} {d.day}, {d.year}"


def _join(words):
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _name(filed: str) -> str:
    name = short_name(filed)
    return LABELS.get(name, name)


def next_words(latest: int, as_of: str | None) -> str:
    """When the year after the latest comes out: its file lender by lender and as one combined file by LENDER_FILE_DAY the year after it, and the national file about
    NATIONAL_MONTH. Once the data's date passes either, it says so."""
    nxt, out = latest + 1, latest + 2
    by, month = f"{out}-{LENDER_FILE_DAY}", date(out, NATIONAL_MONTH, 1).strftime("%B")
    if as_of and as_of[:7] > f"{out}-{NATIONAL_MONTH:02d}":
        return f"HMDA's {nxt} national file was due about {month} {out} and is not loaded yet."
    if as_of and as_of[:10] >= by:
        return (f"The {nxt} HMDA file was due by {_day(by)}, lender by lender and as one combined file, naming the buyer and the score model on each loan; it is not loaded here. "
                f"The national file comes out about {month} {out}.")
    return (f"Next: the {nxt} HMDA file comes out by {_day(by)}, lender by lender and as one combined file, and names the buyer and the score model on each loan. "
            f"The national file follows about {month} {out}.")


def sec_counts(rows: list[dict]) -> dict | None:
    """What the sentence setting the SEC deal reports against HMDA takes from private_label's rows: their VS4 loans (meta vs4_n), how many name no FICO model
    (meta vs4_no_fico_n; None from a build before that count), the deals holding those, oldest filed first, with how many each (deal rows), and the VS4 loans by
    year of credit report (view vs4_year; undated left out). None without a meta row."""
    meta = next((r for r in rows if r.get("view") == "meta"), None)
    if not meta or meta.get("vs4_n") is None:
        return None
    alone = sorted((r["filed"], deal_label(r["label"]), r["vs4_no_fico_n"]) for r in rows if r.get("view") == "deal" and r.get("vs4_no_fico_n"))
    years = [r for r in rows if r.get("view") == "vs4_year" and str(r.get("key")).isdigit()]
    return {"vs4_n": meta["vs4_n"], "alone_n": meta.get("vs4_no_fico_n"), "alone": [(label, k) for _, label, k in alone], "pulled": {int(r["key"]): r["vs4_n"] for r in years},
            "pulled_alone": {int(r["key"]): r.get("vs4_no_fico_n") for r in years}}


def route_words(sec: dict | None, latest: int) -> str | None:
    """The SEC deal reports' VS4 loans set against HMDA naming none sold to a private securitizer in the latest year: how many also name a FICO model, which deals
    hold those naming VS4 alone, how many had credit pulled in each year (and how many of that year's name VS4 alone), and why HMDA's none can still
    hold: it counts a sale to a private securitizer only within the year the loan was made, and names the one score the lender relied on for each borrower. None
    without SEC VS4 loans. Every count is one the reports show; the last words say what HMDA's rules allow, not what happened to any loan."""
    n = (sec or {}).get("vs4_n")
    if not n:
        return None
    alone = sec.get("alone_n")
    said = [f"The SEC deal reports above find {n:,} VS4 loan{'' if n == 1 else 's'} in private-label deals; HMDA names none sold to a private securitizer in {latest}."]
    if alone is not None:
        deals = [f"{label} ({k:,} loans)" if k > 1 else label for label, k in sec.get("alone") or []]
        where = f", in {_join(deals)}" if 0 < len(deals) <= ALONE_DEALS else f", in {len(deals):,} deals" if deals else ""
        fico, every = n - alone, "It" if n == 1 else "Both" if n == 2 else f"All {n:,}"
        if not alone:
            said.append(f"{every} also {'names' if n == 1 else 'name'} a FICO model.")
        elif not fico:
            said.append(f"{every} {'names' if n == 1 else 'name'} VS4 alone{where}.")
        else:
            said.append(f"{fico:,} of the {n:,} also {'names' if fico == 1 else 'name'} a FICO model; {alone:,} {'names' if alone == 1 else 'name'} VS4 alone{where}.")
    pulled = sec.get("pulled") or {}
    dated = sum(pulled.values())
    if dated and n > 1:  # every year, the HMDA year always among them; no word on FICO by year, since some reports name it only in a summary cell
        k_alone = (sec.get("pulled_alone") or {}).get(latest)
        parts = []
        for i, y in enumerate(sorted(set(pulled) | {latest})):
            k = pulled.get(y, 0)
            parts.append(f"{f'{k:,}' if k else 'none'}{' had credit pulled' if not i else ''} in {y}" + (f", {k_alone:,} of them with VS4 alone" if y == latest and k and k_alone else ""))
        said.append(f"Of the {f'{dated:,} with a credit report date' if dated < n else f'{n:,}'}, {_join(parts)}.")
    elif dated:
        said.append(f"Its credit was pulled in {next(iter(pulled))}.")
    said.append("HMDA counts a sale to a private securitizer only within the year the loan was made"
                + (", and names the one score the lender relied on for each borrower, so a loan with a FICO model beside VS4 can show there under FICO."
                   if alone is None or alone < n else "."))
    return " ".join(said)


def build_rows(folder: Path, as_of: str | None = None, sec: dict | None = None) -> list[dict]:
    """sec: what the SEC deal reports find on VS4 (sec_counts, from private_label), for the sentence that sets them against HMDA's count."""
    years = sorted(int(p.stem) for p in folder.glob("*.parquet") if p.stem.isdigit()) if folder.exists() else []
    if not years:
        return []
    latest, first = years[-1], years[0]
    prior = latest - 1 if latest - 1 in years else None
    con = duckdb.connect()
    files = [str(folder / f"{y}.parquet") for y in years]
    con.execute(f"""CREATE VIEW every_year AS SELECT regexp_extract(filename, '(\\d{{4}})\\.parquet$', 1)::INTEGER AS year, * EXCLUDE (filename) FROM read_parquet({files}, filename=true)""")
    con.execute(f"CREATE VIEW n AS SELECT * FROM '{folder / f'lenders_{latest}.parquet'}'")
    con.execute(f"""CREATE TEMP TABLE y AS SELECT year, lei, purchaser_type AS p, coalesce(loan_amount, 0) AS amt, {MODEL_SQL} AS m, {KIND_SQL} AS kind
                    FROM every_year WHERE action_taken = 1 AND ({SEGMENT_SQL}) IS NOT NULL AND purchaser_type IN {OUTSIDE}""")
    count = ", ".join(f"count(*) FILTER (WHERE m = '{k}') AS {k}_n" for k in SHARES)
    names = [f"{k}_n" for k in SHARES]

    def fields(r, at=0) -> dict:
        """A query row as n, usd_bn, vs4_n and the shares; at is where its count sits, with its dollars and then the SHARES counts after it."""
        n, counts = r[at], dict(zip(names, r[at + 2:at + 2 + len(SHARES)]))
        return {"n": n, "usd_bn": _bn(r[at + 1]), **_mix(counts, n), "vs4_n": counts["vs4_n"]}

    out, said = [], {}
    by_year = {r[0]: fields(r, 1) for r in con.execute(f"SELECT year, count(*), sum(amt), {count} FROM y WHERE p = {PRIVATE} GROUP BY 1").fetchall()}
    none = {"n": 0, "usd_bn": 0.0, **_mix({}, 0), "vs4_n": 0}
    for y in years:
        out.append({"view": "year", "year": y, **by_year.get(y, none), "vs4_on_form": y >= VS4_ON_FORM})
    head = by_year.get(latest, none)

    # ---- By kind, the latest two years ----
    kinds = {(r[0], r[1]): fields(r, 2) for r in con.execute(f"SELECT year, kind, count(*), sum(amt), {count} FROM y WHERE p = {PRIVATE} AND year IN ({latest}, {prior or latest}) GROUP BY 1, 2").fetchall()}
    for y in [latest] + ([prior] if prior else []):
        total = by_year.get(y, none)["n"]
        for order, (key, label) in enumerate(KINDS):
            if (y, key) in kinds:
                out.append({"view": "kind", "year": y, "key": key, "label": label, "order": order, **kinds[(y, key)], "share": _r(kinds[(y, key)]["n"] / total) if total else None})

    # ---- The biggest sellers to private securitizers in the latest year, with the year before, by legal entity ----
    top = con.execute(f"""SELECT t.lei, coalesce(l.name, t.lei), t.n, t.amt, {", ".join(f"t.{k}" for k in names)}, t.equity_n FROM (
                              SELECT lei, count(*) AS n, sum(amt) AS amt, {count}, count(*) FILTER (WHERE kind = 'equity') AS equity_n FROM y WHERE year = {latest} AND p = {PRIVATE} GROUP BY 1) t
                          LEFT JOIN n l USING (lei) ORDER BY t.n DESC, t.lei LIMIT {PL_TOP}""").fetchall()
    before, unsold = {}, {}
    if prior and top:
        leis = ", ".join(f"'{r[0]}'" for r in top)
        before = {r[0]: fields(r, 1) for r in con.execute(f"SELECT lei, count(*), sum(amt), {count} FROM y WHERE year = {prior} AND p = {PRIVATE} AND lei IN ({leis}) GROUP BY 1").fetchall()}
        unsold = dict(con.execute(f"""SELECT lei, avg(CASE WHEN purchaser_type = 0 THEN 1.0 ELSE 0 END) FROM every_year
                                      WHERE year = {prior} AND action_taken = 1 AND ({SEGMENT_SQL}) IS NOT NULL AND lei IN ({leis}) GROUP BY 1""").fetchall())
    for rank, r in enumerate(top, 1):
        was = before.get(r[0])
        out.append({"view": "lender", "rank": rank, "name": _name(r[1]), **fields(r, 2), "equity_share": _r(r[-1] / r[2]), "prior_year": prior,
                    "prior_n": was["n"] if was else None, "prior_usd_bn": was["usd_bn"] if was else None, "prior_classic": was["classic"] if was else None, "prior_vs4_n": was["vs4_n"] if was else None,
                    "prior_unsold": _r(unsold.get(r[0])), "prior_mark": bool(was) and (unsold.get(r[0]) or 0) > UNSOLD_MARK})

    # ---- Every lender putting VS4 on a loan sold outside the four in the latest year ----
    outside_n, outside_vs4, private_vs4 = con.execute(f"SELECT count(*), count(*) FILTER (WHERE m = 'vs4'), count(*) FILTER (WHERE m = 'vs4' AND p = {PRIVATE}) FROM y WHERE year = {latest}").fetchone()
    users = con.execute(f"""WITH t AS (SELECT lei, count(*) AS n, count(*) FILTER (WHERE m = 'vs4') AS v, count(*) FILTER (WHERE m = 'vs4' AND p = {PRIVATE}) AS v5 FROM y WHERE year = {latest} GROUP BY 1),
                                 b AS (SELECT lei, p, count(*) AS k FROM y WHERE year = {latest} AND m = 'vs4' GROUP BY 1, 2)
                            SELECT coalesce(l.name, t.lei), t.n, t.v, t.v5, (SELECT p FROM b WHERE b.lei = t.lei ORDER BY k DESC, p LIMIT 1) FROM t LEFT JOIN n l USING (lei)
                            WHERE t.v > 0 ORDER BY t.v DESC, t.n DESC, t.lei""").fetchall()
    for rank, (name, n, v, v5, buyer) in enumerate(users, 1):
        out.append({"view": "vs4_lender", "rank": rank, "name": _name(name), "n": n, "vs4_n": v, "vs4": _r(v / n), "private_vs4_n": v5, "buyer": BUYERS.get(buyer)})
    con.close()

    # ---- The sentences, each under its guard ----
    if first < VS4_ON_FORM:
        said["form"] = f"HMDA's form names VS4 only from {VS4_ON_FORM}, so in {'earlier' if latest >= VS4_ON_FORM else 'these'} years a loan on VS4 shows under another model."
    if head["n"]:
        big = sorted(((r["share"], r["key"]) for r in out if r["view"] == "kind" and r["year"] == latest), reverse=True)
        named = [(s, k) for s, k in big if s >= KIND_MIN][:3] or big[:1]
        parts = [pc1(s) + (" are " if i == 0 else " ") + KIND_WORDS[k] for i, (s, k) in enumerate(named)]
        said["kinds"] = f"Of these {latest} loans, {_join(parts)}."
    sold = [r for r in out if r["view"] == "year" and r["n"]]
    if sold:
        top_vs = max(sold, key=lambda r: (r["vs"], r["year"]))
        low = min(sold, key=lambda r: (r["fico"], r["year"]))
        scored = [r["fico"] / (1 - r["none"]) for r in sold if r["none"] < 1]
        dips = ["VantageScore stays under 1% of these loans in every year." if top_vs["vs"] < VS_RARE else f"VantageScore's share reaches {pc1(top_vs['vs'])} in {top_vs['year']}."]
        if len(sold) > 1 and low["none"] * 2 > 1 - low["fico"]:
            dips.append(f"The dips in FICO's share are loans with no score reported, {pc1(low['none'])} in {low['year']}"
                        + (f"; of the loans that report a score, FICO's share never falls below {pc1(min(scored))}." if scored else "."))
        said["dips"] = " ".join(dips)
    if prior and prior >= VS4_ON_FORM:
        k = by_year.get(prior, none)["vs4_n"]
        said["vs4_tile"] = f"{f'{k:,}' if k else 'Also none' if not head['vs4_n'] else 'None'} in {prior}" + (", the first year HMDA's form names VS4" if prior == VS4_ON_FORM else "")
    elif latest == VS4_ON_FORM:
        said["vs4_tile"] = "The first year HMDA's form names VS4"
    elif latest < VS4_ON_FORM:
        said["vs4_tile"] = f"HMDA's form names VS4 only from {VS4_ON_FORM}"
    if outside_n:
        who = "a buyer other than Fannie, Freddie, Ginnie or Farmer Mac"
        if outside_vs4:
            to_private = "None was sold to a private securitizer." if not private_vs4 else f"{private_vs4:,} {'was' if private_vs4 == 1 else 'were'} sold to a private securitizer."
            said["outside"] = f"In {latest}, {outside_vs4:,} of the {outside_n:,} loans sold to {who} name VS4 ({pc2(outside_vs4 / outside_n)}), at {len(users):,} lender{'' if len(users) == 1 else 's'}. {to_private}"
        else:
            said["outside"] = f"In {latest}, none of the {outside_n:,} loans sold to {who} names VS4."
    route = route_words(sec, latest) if latest >= VS4_ON_FORM and not private_vs4 else None
    if route:
        said["route"] = route
    marked = [r for r in out if r["view"] == "lender" and r["prior_mark"]]
    if marked:
        one = len(marked) == 1
        said["unsold"] = ("* " + "; ".join(f"{r['name']} reported {pc1(r['prior_unsold'])} of its {prior} loans as not sold that year" for r in marked)
                          + f", so {'its' if one else 'their'} {prior} {'count' if one else 'counts'} of loans sold to private securitizers {'is' if one else 'are'} not comparable.")
    said["next"] = next_words(latest, as_of)

    meta = {"view": "meta", "year": latest, "prior": prior, "first_year": first, "file_date": YEAR_FILES.get(latest), "national_released": NATIONAL_RELEASED.get(latest), **head, "prior_n": by_year.get(prior, none)["n"] if prior else None,
            "prior_vs4_n": by_year.get(prior, none)["vs4_n"] if prior else None, "outside_n": outside_n, "outside_vs4_n": outside_vs4, "outside_lenders": len(users), "private_vs4_n": private_vs4,
            "vs4_form_year": VS4_ON_FORM, "next_year": latest + 1, "lender_file_by": f"{latest + 2}-{LENDER_FILE_DAY}", "national_about": f"{latest + 2}-{NATIONAL_MONTH:02d}", "lender_file_url": LENDER_FILE_URL, "as_of": as_of}
    rows = [meta, *out, *({"view": "sentence", "key": k, "text": v} for k, v in said.items())]
    keys = sorted({k for r in rows for k in r})
    return [{k: r.get(k) for k in keys} for r in rows]


def _file_rows(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text())["rows"]
    except FileNotFoundError:
        return []


def build_datasets(more: dict | None = None, out_dir: Path = paths.SITE_DATA, folder: Path | None = None) -> dict[str, list[dict]]:
    """From the HMDA files on disk, with the data's date from summary and the SEC reports' VS4 counts from private_label (sec_counts; the rows built so far in this
    run, else the files in out_dir). A shape this builder did not foresee stops nothing: the card stays off and the weekly report says why."""
    more = more or {}
    try:
        summary = more["summary"] if "summary" in more else _file_rows(out_dir / "summary.json")
        deals = more["private_label"] if "private_label" in more else _file_rows(out_dir / "private_label.json")
        as_of = next((r.get("data_through") for r in summary if r.get("agency") == "All"), None)
        return {"pl_hmda": build_rows(folder or paths.HMDA, as_of, sec_counts(deals))}
    except Exception as e:
        return {"pl_hmda": [{"view": "meta", "text": None}, {"view": "warning", "text": f"private securitizers: could not build the dataset: {e!r}"}]}


def pl_hmda_warnings(out_dir: Path = paths.SITE_DATA) -> list[str]:
    """What the weekly report prints from the dataset. Never raises."""
    try:
        return [r["text"] for r in _file_rows(out_dir / "pl_hmda.json") if r.get("view") == "warning"]
    except Exception as e:
        return [f"private securitizers: could not read pl_hmda.json: {e!r}"]
