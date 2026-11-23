"""Private-label mortgage deals as they file, from SEC Form ABS-15G.

No residential deal files the SEC's asset-level form (ABS-EE), but any deal to be rated, registered or not, must furnish its third-party due diligence findings on Form ABS-15G at
least five business days before first sale. Many of those reports list each reviewed loan, and some name the score model per borrower and bureau (`Borrower Experian FICO Model Used`).

As elsewhere, a named model is a fact. A blank is unknown, and so is a score column with no model: a column called FICO can hold a VantageScore, so only a named model counts.

Requests carry a contact in the User-Agent, as the SEC's fair-access rules ask, at a few a second. The contact is read from the EDGAR_CONTACT setting or data/edgar/contact.txt and stays out of
the repo. What is kept, under data/edgar/ (git-ignored):
  hits.jsonl      every exhibit EDGAR's search returned for the phrases below
  exhibits.jsonl  each exhibit read: how many tables and rows, which columns, any value not recognized, how many loans it lists by number (listed) and how many
                  rows it left out as copies of loans its report lists already (copies)
  loans.jsonl     one line per loan row with a model column: filing, exhibit, loan id, the models named, the credit report month, the qualifying score, and the
                  loan's other numbers (alt). A loan carries one loan number in every table of its exhibit, the review firm's where its tables give it
                  (parse_exhibit), so a loan in several tables counts once; a table that only repeats loans its report lists already, with codes or blanks and no
                  loan numbers, is left out. A row with no number carries its place instead (row<table>-<row>, or line<n> in a fixed-width report)
  mentions.jsonl  exhibits that mention VantageScore other than as a template's column heading
  filings.jsonl   each filing read for its deal name
  watch.jsonl     the VantageScore watch (collect_watch): each file on WATCH_FORMS that EDGAR's search finds naming VantageScore, once per filing and file, with how often
                  it names VantageScore outside a template's column heading and the sentence to show (vantage_passage); a deal report the search above read keeps that
                  reading
  watch_runs.jsonl each watch search: the day it ran and the filing days it covered
The reports themselves are not kept.

  private_label  view meta: how far the search reached, filings, loans and how many name a model.
                 view period, basis filed: by quarter a deal first filed; basis pulled: by month of the loan's credit report (the one date these reports show, on some loans; application, lock and note dates are masked).
                 view kind: by kind of deal, going by its name. view filer: by depositor, with how many of its filings have a per-loan score column and a model column.
                 meta's recent_ fields cover loans with a credit report from AGENCY_OPEN on, lag_months is the median from credit report to filing, vs_no_fico_n counts loans naming VantageScore and no FICO model, and vs4_no_fico_n those naming VS4 and no FICO model. Each has n (loan rows), named (with a model the report names), classic, fico_new, vs4, vs_old and unclear (a code or a word this cannot read) and blank (none named), as counts (_n) and shares of n.
                 view deal: each deal with a loan naming VantageScore, with vs4_no_fico_n too. view mention: each deal whose report names VantageScore outside a model column, as in a narrative or a comment.
                 view vs4_year: the VS4 loans by year of credit report (key: the year, or undated), vs4_n, and vs4_no_fico_n of them, for the private-label view's sentence that sets them against HMDA (pl_hmda.py).
                 vs4_year and vs4_no_fico_n are private for now: the public build leaves them out (site.PUBLIC_DROP).
                 A loan in two reports, an amended filing or a later deal counts once, under the deal that first filed it: by its number, or by any other number of seven figures or more a report gives it (alt), so a loan one report numbers by the review firm and another by the seller is one loan. A numeric code in a model column counts as unclear: one report has VS4 loans coded the same as Classic FICO ones.
                 Two deals that give the same numbers to other loans (_reused: most of the numbers they share have a different score and month) keep them apart. A loan with no number counts once within its own file, and is the loan another schedule of its report lists where the order of their scores, or their shape, says so (_aligned): a Business Purpose schedule lists the Supplemental Data schedule's loans again with their numbers masked.
"""
import bisect
import gzip
import html
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

from . import paths
from .hmda import short_name

BACKFILL_FROM = "2025-01-01"
OVERLAP_DAYS = 21  # how far back a later run searches again, since EDGAR's search can take time to catch up
PAUSE = 0.3  # seconds between requests; the SEC's limit is 10 a second
SEARCH = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
# Phrases that find each kind of exhibit. MODEL: a per-loan model column. SCORE: a per-loan score column, for how many filings could show a model at all. MENTION: anything naming VantageScore.
MODEL_QUERIES = ['"FICO Model Used"', '"Credit Score Model Name"', '"Credit Score Model"']
SCORE_QUERIES = ['"Qualifying FICO"', '"Qualifying Credit Score"', '"Representative FICO"', '"Original FICO"', '"Borrower FICO"']
MENTION_QUERIES = ["VantageScore", "Vantage"]
# Filers that use the same words on other kinds of loans, or the GSEs' own deals.
NOT_PRIVATE_MORTGAGE = re.compile(r"\b(auto|automobile|receivables?|lease|leasing|card|student|equipment|marine|solar|timeshare|pagaya|consumer|personal|vehicle|motor|carvana|ally|drive|exeter|westlake|upstart|"
                                  r"affirm|cherry|jgw|reprise|marquis|rktl|occu|federal national mortgage|federal home loan mortgage|american credit acceptance|gls|santander drive|world omni|oportun|lendmark|vantage data|vantage valkyrie|"
                                  r"commercial mortgage|mortgage capital holdings|principal funding|mf1 reit|real estate income|benefit street|education|navient|aqua finance|sofi|cci gpcc|arra finance)\b", re.I)

_CACERTS = "/etc/ssl/cert.pem"
_ID_COL = re.compile(r"loan\s*(id|number|#|no\b)|deal\s*(id|number)|edgar id|\balt id\b|^unique id$", re.I)
_MODEL_COL = re.compile(r"fico model used|credit score model", re.I)
_VS_SCORE_COL = re.compile(r"vantage\s*score\s*:?\s*(primary|co)", re.I)
_BLANK = re.compile(r"^(|x+|\*+|\[?redact(ed)?\]?|n/?a|none|not applicable|not available|unavailable|unknown|-+|0+|9{2,}|null|yes|no)$", re.I)
_MASKED = re.compile(r"x{3,}|\*{2,}|redact", re.I)
_VS = re.compile(r"vantage", re.I)
_VS4 = re.compile(r"vantage\s*score\s*(ver\w*\.?\s*)?4|vantage\s*4", re.I)
_VS_OLD = re.compile(r"vantage\s*score\s*(ver\w*\.?\s*)?[123]|vantage\s*[123]", re.I)
_FICO_NEW = re.compile(r"classic\s*\(?0?[89]\)?|fico\s*(score\s*)?(8|9|10)|v8\b|v9\b|10t\b|next\s*gen", re.I)
_FICO_CLASSIC = re.compile(r"^classic$|beacon|v5\b|classic\s*\(?(0?4|98)\)?|fair\s*is+a+c|fico\s*ii\b|fico\s*v?(score\s*)?[245]\b|risk score", re.I)
_CODE = re.compile(r"^\d{1,2}$")
_VANTAGE_SCORE = re.compile(r"\bvantage\s*score|\bvantage\b(?=[^.]{0,80}\b(score|credit|fico|bureau)|\s+\d)|\b(score|credit|fico|experian|equifax|transunion|bureau)\b[^.]{0,80}\bvantage\b", re.I)
_TEMPLATE_WORDS = re.compile(r"(most recent )?vantage\s*score\s*:?\s*(primary borrower|co[- ]?borrower|method|date)", re.I)
_DEAL = re.compile(r"\b([A-Z][A-Za-z&.]*(?:[ -][A-Z][A-Za-z&.]*){0,7}?)[ -](20\d\d)[ -]([A-Z0-9]{1,8}(?:-[A-Z0-9]{1,6})?)\b")


def contact_file() -> Path:
    return paths.DATA / "edgar" / "contact.txt"


def contact() -> str:
    value = os.environ.get("EDGAR_CONTACT") or (contact_file().read_text().strip() if contact_file().exists() else "")
    if "@" not in value:
        raise SystemExit("EDGAR asks automated requests to declare a contact: put an email address in data/edgar/contact.txt or EDGAR_CONTACT.")
    return value


class Edgar:
    """One request at a time, paced, with retries that back off when the SEC pushes back."""

    def __init__(self, pause: float = PAUSE):
        self.ua = f"vantagescore-adoption-tracker {contact()}"
        self.pause = pause
        self.last = 0.0
        self.requests = 0
        self.context = ssl.create_default_context(cafile=_CACERTS if os.path.exists(_CACERTS) else None)

    def get(self, url: str) -> bytes | None:
        for attempt in range(6):
            wait = self.pause - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            self.requests += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Encoding": "gzip, deflate"})
                with urllib.request.urlopen(req, timeout=180, context=self.context) as r:
                    body = r.read()
                    coding = r.headers.get("Content-Encoding", "")
                return gzip.decompress(body) if coding == "gzip" else zlib.decompress(body) if coding == "deflate" else body
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code not in (403, 429, 500, 502, 503, 504):
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, EOFError, zlib.error):
                pass  # includes a response cut off part way, which is worth asking for again
            time.sleep(5 * 3 ** attempt)
        return None

    def search(self, q: str, start: str, end: str, frm: int = 0, forms: str = "ABS-15G") -> dict | None:
        args = {"q": q, "forms": forms, "dateRange": "custom", "startdt": start, "enddt": end}
        if frm:
            args["from"] = frm
        url = f"{SEARCH}?{urllib.parse.urlencode(args, quote_via=urllib.parse.quote)}"
        for attempt in range(6):
            body = self.get(url)
            if body:
                try:
                    out = json.loads(body)
                    if "hits" in out:
                        return out
                except ValueError:
                    pass
            time.sleep(4 + 4 * attempt)  # the search answers with an error body when it is busy
        return None


def exhibit_url(cik: str | int, adsh: str, name: str) -> str:
    return f"{ARCHIVES}/{int(cik)}/{adsh.replace('-', '')}/{name}"


def month_windows(start: str, end: str) -> list[tuple[str, str]]:
    out, day, last = [], date.fromisoformat(start), date.fromisoformat(end)
    while day <= last:
        nxt = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((day.isoformat(), min(nxt - timedelta(days=1), last).isoformat()))
        day = nxt
    return out


def _hit(h: dict, kind: str) -> dict:
    s = h["_source"]
    adsh, name = h["_id"].split(":", 1)
    return {"adsh": adsh, "file": name, "cik": (s.get("ciks") or ["0"])[0], "date": s.get("file_date"), "form": s.get("form"), "type": s.get("file_type"), "desc": (s.get("file_description") or "")[:80],
            "filer": (s.get("display_names") or [""])[0].split("  (")[0].strip(), "kind": kind}


def discover(client: Edgar, start: str, end: str, log=print) -> list[dict]:
    """Every exhibit the search returns for the phrases, month by month."""
    out = []
    for q_kind, queries in (("model", MODEL_QUERIES), ("score", SCORE_QUERIES), ("mention", MENTION_QUERIES)):
        for q in queries:
            found = 0
            for a, b in month_windows(start, end):
                frm = 0
                while True:
                    res = client.search(q, a, b, frm)
                    if res is None:
                        raise RuntimeError(f"EDGAR's search did not answer for {q} {a}..{b}")
                    hits = res["hits"]["hits"]
                    out.extend(_hit(h, q_kind) for h in hits)
                    found += len(hits)
                    frm += len(hits)
                    if not hits or frm >= res["hits"]["total"]["value"] or frm >= 9900:
                        break
            log(f"  {q}: {found} exhibits")
    return out


class _Row(list):
    """A table row's cells, a cell that spans columns padded so later cells stay under their headings, and where each of its own cells starts and how many columns it
    spans (spans), so a value set off inside its heading's span can be found (_gather)."""
    __slots__ = ("spans",)

    def __init__(self):
        super().__init__()
        self.spans = []


class _Tables(HTMLParser):
    """Each table's rows, as lists of cell text, with a cell that spans columns padded so later cells stay under their headings. A table inside another, or one left open, is still its own table."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.row, self.cell, self.span = [], [], None, None, 1

    def handle_starttag(self, tag, attrs):
        if tag == "br" and self.cell is not None:
            self.cell.append(" ")
        elif tag == "table":
            self._close_row()
            self.stack.append([])
        elif self.stack:
            if tag == "tr":
                self._close_row()
                self.row = _Row()
            elif tag in ("td", "th"):
                self._close_cell()
                self.cell = []
                try:
                    self.span = max(1, int(dict(attrs).get("colspan") or 1))
                except ValueError:
                    self.span = 1

    def _close_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.spans.append((len(self.row), self.span))
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.row.extend([""] * (self.span - 1))
        self.cell = None

    def _close_row(self):
        self._close_cell()
        if self.row is not None and self.stack and any(self.row):
            self.stack[-1].append(self.row)
        self.row = None

    def _close_table(self):
        self._close_row()
        table = self.stack.pop()
        if table:
            self.tables.append(table)

    def handle_endtag(self, tag):
        if tag == "table":
            if self.stack:
                self._close_table()
        elif self.stack:
            if tag in ("td", "th"):
                self._close_cell()
            elif tag == "tr":
                self._close_row()

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def finish(self):
        self.close()
        while self.stack:
            self._close_table()


def read_tables(text: str) -> list[list[list[str]]]:
    p = _Tables()
    p.feed(text)
    p.finish()
    return p.tables


def report_month(value: str) -> str | None:
    """A date as YYYY-MM, or None when it is blank or masked."""
    v = (value or "").strip()
    m = re.fullmatch(r"(\d{1,2})/\d{1,2}/(\d{2}|\d{4})", v)
    if m:
        year = m.group(2) if len(m.group(2)) == 4 else f"20{m.group(2)}"
        month = int(m.group(1))
    else:
        m = re.fullmatch(r"(\d{4})-?(\d{2})-?\d{2}", v)
        if not m:
            return None
        year, month = m.group(1), int(m.group(2))
    return f"{year}-{month:02d}" if 1 <= month <= 12 and 1990 <= int(year) <= 2100 else None


def model_family(value: str) -> str:
    """What one cell says: vs4, vs_old, vs_other, fico_new, classic, a code, the word other, or junk, which is what a report with its columns out of line puts here (C3, 75.000%),
    as it is a template's column heading read as a cell ("Vantagescore Date"), which names no model."""
    if _TEMPLATE_WORDS.fullmatch(value.strip()):
        return "junk"
    if _VS.search(value):
        return "vs4" if _VS4.search(value) else "vs_old" if _VS_OLD.search(value) else "vs_other"
    if _FICO_NEW.search(value):
        return "fico_new"
    if _FICO_CLASSIC.search(value):
        return "classic"
    return "code" if _CODE.match(value) else "other" if value.strip().lower() == "other" else "junk"


def loan_family(values: list[str]) -> str:
    """One loan's models count once, under the first that applies, so a named VantageScore is never hidden. A code or the word other stays unclear, and nothing but junk is blank."""
    fams = {model_family(v) for v in values}
    for f in ("vs4", "vs_old", "vs_other", "fico_new", "classic"):
        if f in fams:
            return f
    return "unclear" if fams & {"code", "other"} else "blank"


_REVIEW_ID = re.compile(r"\b((situs)?amc loan id|alt id)\b|^unique id$", re.I)  # the review firm's own loan number, which every table of its report carries (AMC's, ALT's, and Unique ID in GS's)
_PLACE = re.compile(r"row(\d+)-\d+")  # a loan row with no number: its table's place and its own (parse_exhibit)
_UNNUMBERED = re.compile(r"row\d+-\d+|line\d+")  # the same, or a fixed-width report's line (_parse_pre)


def _id_kind(heading: str) -> str:
    """Which loan number a column holds: the review firm's, the customer's, or another, by its heading."""
    return "review" if _REVIEW_ID.search(heading) else "customer" if re.search(r"customer", heading, re.I) else re.sub(r"\W+", " ", heading.lower()).strip()


def _id_rank(kind: str) -> int:
    """The review firm's number first, then the customer's, then any other; a deal's number last, as it can name every loan alike."""
    return 0 if kind == "review" else 1 if kind == "customer" else 3 if kind.startswith("deal") else 2


def _number(value: str) -> str | None:
    """A cell as a loan number: a figure in it, and not masked."""
    v = (value or "").strip()
    return v if re.search(r"\d", v) and not _MASKED.search(v) else None


def _full(row: list[str]) -> bool:
    """A loan's row: three cells or more filled."""
    return sum(1 for c in row if c) >= 3


def _gather(row: list[str], wide: list[tuple[int, int]]) -> list[str]:
    """A row with each value set off inside its heading's span moved under the heading: some filing agents give each heading four columns and put its value in the
    second, a mark such as $ or % or a split name's second half beside it (CROSS 2026-NQM1 and NQM2: 'Fair Isaac' and '(VER. 2)'). wide: each heading that spans
    columns, where it starts and how many it spans."""
    out = list(row)
    for at, span in wide:
        if at < len(row):
            end = min(len(row), at + span)
            out[at:end] = [" ".join(c for c in row[at:end] if c)] + [""] * (end - at - 1)
    return out


def _runs(tables: list) -> list[dict]:
    """Each table with a heading row as one run, with any table after it that has no heading row but its width, which continues it: its heading, where it starts and
    how many tables it spans, and its rows, a sparse one too, so each keeps its place. A table whose first row repeats the heading's first cell has a heading of its own,
    even one that names no loan number or model, so its heading is never read as a loan's row. Where a heading spans several columns, its rows' cells under it read as
    one value (_gather)."""
    runs, header = [], None
    for t_no, table in enumerate(tables):
        start = next((i for i, row in enumerate(table[:5]) if len(row) >= 3 and any(_ID_COL.search(c) or _MODEL_COL.search(c) for c in row)), None)
        if start is None and header is not None and table and table[0] and table[0][0] == header[0] and header[0] and not re.search(r"\d", header[0]):
            start = 0  # its first row repeats the last heading's first cell, as each slice of a loan tape split by columns does: a table of its own, headed by that row
        if start is not None:
            header = table[start]
            runs.append({"t": t_no, "header": header, "tables": 1, "rows": []})
            body = table[start + 1:]
        elif header is not None and table and len(table[0]) == len(header):
            runs[-1]["tables"] += 1
            body = table
        else:
            continue
        runs[-1]["rows"].extend(body)
    for run in runs:
        h = run["header"]
        wide = [(at, span) for at, span in getattr(h, "spans", ()) if span > 1 and h[at]]
        if wide:
            run["rows"] = [_gather(row, wide) for row in run["rows"]]
        run["ids"] = {i: _id_kind(c) for i, c in enumerate(h) if _ID_COL.search(c)}
        run["models"] = [i for i, c in enumerate(h) if _MODEL_COL.search(c) and "date" not in c.lower()]
        run["vs_scores"] = [i for i, c in enumerate(h) if _VS_SCORE_COL.search(c)]
    return runs


def _figures(run: dict, i: int) -> list[str]:
    """The loan numbers one column of a run gives, on its loans' rows."""
    return [v for v in (_number(row[i]) for row in run["rows"] if _full(row) and i < len(row)) if v]


def _loan_numbers(runs: list[dict]) -> None:
    """One loan number for the whole exhibit, so a loan in several tables counts once, and each loan's other numbers. A number column with no figure in a run, all
    masked or blank, is not there. Of the kinds its model tables carry, the review firm's number, else the customer's, else another, that gives a figure on at least
    half its cells and is not one figure for every loan, is the exhibit's own. A row without it takes, in turn: the figure of a column that repeats the own numbers
    under another heading, however short (an ASF tape's Loan Number that is the customer's, 1 to 59); the own number a table with both gives beside another of its
    numbers, where that leads to one loan only; its first number with three figures or more. A model table with no number at all takes the numbers of the last table
    before it that has them, one loan to a row and as many rows, its sparse ones counted. Each run gets numbers, one per row or None, and alts: the other numbers of
    each row's loan, those that lead to that loan only and are no other loan's number, a deal's number aside."""
    for r in runs:
        r["ids"] = {i: k for i, k in r["ids"].items() if _figures(r, i)}
    with_loans = [r for r in runs if r["models"] or r["vs_scores"]]
    kinds = list(dict.fromkeys(k for r in with_loans for k in r["ids"].values()))

    def usable(kind):
        cells = [row[i] if i < len(row) else "" for r in with_loans for row in r["rows"] if _full(row) for i, k in r["ids"].items() if k == kind]
        figures = [v for v in map(_number, cells) if v]
        return bool(cells) and len(figures) * 2 >= len(cells) and len(set(figures)) * 4 >= len(figures)

    own = next((k for k in sorted(kinds, key=lambda k: (_id_rank(k), kinds.index(k))) if usable(k)), None)
    own_numbers = {v for r in runs for i, k in r["ids"].items() if k == own for v in _figures(r, i)}
    beside = {}
    for r in runs:
        at = [i for i, k in r["ids"].items() if k == own]
        for row in r["rows"] if at else []:
            mine = next((v for v in (_number(row[i]) for i in at if i < len(row)) if v), None)
            for i, k in r["ids"].items() if mine else ():
                v = _number(row[i]) if k != own and i < len(row) else None
                if v and v != mine and v not in own_numbers:
                    beside.setdefault(v, set()).add(mine)
    beside = {v: next(iter(s)) for v, s in beside.items() if len(s) == 1}
    for r in runs:  # a column that repeats the own numbers under another heading: nine in ten of its figures are own numbers
        r["same"] = {i for i, k in r["ids"].items() if k != own and sum(v in own_numbers for v in _figures(r, i)) * 10 >= len(_figures(r, i)) * 9}

    def number(r, row):
        order = sorted(r["ids"], key=lambda i: (r["ids"][i] != own, _id_rank(r["ids"][i]), i))
        cells = [(i, _number(row[i]) if i < len(row) else None) for i in order]
        mine = next((v for i, v in cells if v and r["ids"][i] == own), None)
        same = next((v for i, v in cells if i in r["same"] and v in own_numbers), None)
        led = next((beside[v] for _, v in cells if v in beside), None)
        return mine or same or led or next((v for _, v in cells if v and len(re.sub(r"\D", "", v)) >= 3), None)

    lists = []  # the runs so far that number their rows one loan to a row
    for r in runs:
        r["numbers"] = [number(r, row) if r["ids"] else None for row in r["rows"]]
        if (r["models"] or r["vs_scores"]) and not any(r["numbers"]):
            r["numbers"] = list(next((n for n in reversed(lists) if len(n) == len(r["rows"])), r["numbers"]))
        found = [n for n in r["numbers"] if n]
        if found and len(set(found)) * 10 >= len(found) * 9:  # not an exceptions table, which lists a loan on several rows
            lists.append(r["numbers"])
    loans, others = {n for r in runs for n in r["numbers"] if n}, {}
    for r in runs:
        for row, n in zip(r["rows"], r["numbers"]):
            for i, k in r["ids"].items() if n else ():
                v = _number(row[i]) if i < len(row) and _id_rank(k) < 3 else None
                if v and v not in loans:
                    others.setdefault(v, set()).add(n)
    alts = {}
    for v, s in others.items():
        if len(s) == 1:
            alts.setdefault(next(iter(s)), []).append(v)
    for r in runs:
        r["alts"] = [sorted(alts.get(n, ())) for n in r["numbers"]]


def _listed(runs: list[dict]) -> int:
    """How many loans an exhibit's model tables list by number: their distinct numbers, or the most rows with a number in one of them, where a loan shows twice."""
    numbered = [[n for row, n in zip(r["rows"], r["numbers"]) if n and _full(row)] for r in runs if r["models"] or r["vs_scores"]]
    return max([len({n for ns in numbered for n in ns})] + [len(ns) for ns in numbered])


def _copy_tables(rows: list[dict]) -> dict[str, int]:
    """The tables whose loan rows all carry no number (row places) and name only codes or nothing, no model and no VantageScore: each table's place and its rows."""
    tables = {}
    for r in rows:
        m = _PLACE.fullmatch(r["id"])
        if m:
            tables.setdefault(m.group(1), []).append(r)
    return {t: len(g) for t, g in tables.items() if not any(r.get("vs_value") or any(model_family(v) not in ("code", "other", "junk") for v in r["models"]) for r in g)}


def _copies(rows: list[dict], listed: int) -> tuple[list[dict], int]:
    """Leaves out each of those tables (_copy_tables) where the report it sits in lists by number at least as many loans: a copy of loans counted already, as an ASF
    tape whose loan numbers are masked. A table that names a model or gives a VantageScore stays. Gives the rows kept and how many were left out."""
    copies = {t for t, n in _copy_tables(rows).items() if n <= listed}
    kept = [r for r in rows if not ((m := _PLACE.fullmatch(r["id"])) and m.group(1) in copies)]
    return kept, len(rows) - len(kept)


_BUREAU = re.compile(r"\b(experian|equifax|trans\s*union)\b", re.I)
_VS_FAMILIES = ("vs4", "vs_old", "vs_other")
_FICO_FAMILIES = ("classic", "fico_new")


def _summaries(header: list[str], models: list[int]) -> dict[int, list[int]]:
    """A borrower's summary model column (Guarantor 1 FICO Model Used) beside the same borrower's columns for each bureau (Guarantor 1 Experian FICO Model Used): the
    summary column and its bureau columns."""
    whose = {}
    for i in models:
        h = re.sub(r"\s+", " ", header[i].lower())
        who = re.split(r"\b(?:experian|equifax|trans\s*union)\b|fico model used|credit score model", h)[0].strip()
        whose.setdefault(who, ([], []))[bool(_BUREAU.search(h))].append(i)
    return {i: bureaus for summary, bureaus in whose.values() if bureaus for i in summary}


def _named(row: list[str], models: list[int], summaries: dict[int, list[int]]) -> list[str]:
    """The models one row names. A borrower's summary cell counts as a FICO model only when that borrower's bureau columns name no VantageScore: NYMT's reports put
    Classic in Guarantor 1 FICO Model Used on loans whose every bureau column, the guarantor's too, says VantageScore 4.0."""
    cell = lambda i: row[i] if i < len(row) else ""  # noqa: E731
    out = set()
    for i in models:
        v = cell(i)
        if _BLANK.match(v):
            continue
        if model_family(v) in _FICO_FAMILIES and any(model_family(cell(j)) in _VS_FAMILIES for j in summaries.get(i, ())):
            continue
        out.add(v)
    return sorted(out)


def parse_exhibit(text: str) -> tuple[list[dict], dict]:
    """The loan rows of every table with a model column, and a note of what was read. A table with no heading row but the width of the last one continues it. Every
    row carries the exhibit's one loan number (_loan_numbers) and, as alt, the loan's other numbers, or its table's place and its own when there is none. A table that
    only repeats loans the exhibit lists by number, with codes or blanks, is left out (_copies). The note says how many loans the exhibit lists by number (listed), for
    the same check across the files of one report (collect), and how many rows it left out (copies). A borrower's summary model cell naming FICO beside bureau columns
    naming a VantageScore is not counted (_named)."""
    rows, note = [], {"tables": 0, "model_tables": 0, "rows": 0, "columns": [], "odd": {}}
    tables = read_tables(text)
    note["tables"] = len(tables)
    runs = _runs(tables)
    _loan_numbers(runs)
    for run in runs:
        header, models, vs_scores = run["header"], run["models"], run["vs_scores"]
        if not models and not vs_scores:
            continue
        note["model_tables"] += run["tables"]
        for i in models:
            if header[i] not in note["columns"] and len(note["columns"]) < 40:
                note["columns"].append(header[i])
        pull = next((i for i, h in enumerate(header) if re.fullmatch(r"original credit report date", h, re.I)), None)
        score = next((i for i, h in enumerate(header) if re.fullmatch(r"qualifying (credit score|fico)", h, re.I)), None)
        summaries = _summaries(header, models)
        for r_no, (row, number, alt) in enumerate(zip(run["rows"], run["numbers"], run["alts"])):
            if not _full(row):
                continue
            named = _named(row, models, summaries)
            for v in named:
                if model_family(v) == "junk" and len(note["odd"]) < 25:
                    note["odd"][v[:40]] = note["odd"].get(v[:40], 0) + 1
            vs_value = any(i < len(row) and re.fullmatch(r"[3-8]\d\d", row[i] or "") for i in vs_scores)
            cell = lambda i: row[i] if i is not None and i < len(row) else ""  # noqa: E731
            digits = re.sub(r"\D", "", cell(score))
            rows.append({"id": number or f"row{run['t']}-{r_no}", "models": named, "vs_value": vs_value, "pull": report_month(cell(pull)), "score": int(digits) if len(digits) == 3 else None,
                         **({"alt": alt} if alt else {})})
    if not note["model_tables"]:
        return _parse_pre(text)
    note["listed"] = _listed(runs)
    rows, note["copies"] = _copies(rows, note["listed"])
    note["rows"] = len(rows)
    return rows, note


_PRE_MODEL = re.compile(r"Equifax Beacon 5\.0|Enhanced Beacon|Beacon 5\.0|FICO Risk Score Classic \d+|FICO Classic V\d+ Facta|FICO Classic \(?\d+\)?|Experian Fair Isaac Model \d|Fair Isaac \(VER\. ?\d\)|Fair Isaac Advanced|Fair Isaac|FICO II|"
                        r"FICO Score \d+T?|FICO \d+T?|Classic \d+|Vantage\s*Score\s*\d(?:\.\d)?|Vantage\s*Score", re.I)


def _parse_pre(text: str) -> tuple[list[dict], dict]:
    """A report filed as a fixed-width text block: sections of the same loans, each with a heading line and its columns at fixed places. The model columns have no separators, so known model names are read from where those columns sit."""
    rows, note = [], {"tables": 0, "model_tables": 0, "rows": 0, "columns": [], "odd": {}, "pre": True}
    lower = text.lower()
    start = lower.find("<pre")
    if start < 0:
        return rows, note
    lines = html.unescape(text[lower.find(">", start) + 1:lower.find("</pre", start)]).split("\n")
    heads = [i for i, line in enumerate(lines) if re.search(r"LOAN (ID|NUMBER)", line) and not re.search(r"[a-z]{3}", line)]
    pulls, scores = {}, {}
    for pos, h in enumerate(heads):
        head, end = lines[h], heads[pos + 1] if pos + 1 < len(heads) else len(lines)
        used = [m.end() for m in re.finditer(r"FICO MODEL USED", head)]
        cust = re.search(r"CUSTOMER LOAN ID", head)
        seller = re.search(r"SELLER LOAN ID", head)
        report = re.search(r"ORIGINAL CREDIT REPORT DATE", head)
        score = re.search(r"QUALIFYING CREDIT SCORE", head)
        first = re.search(r"((CO )?BORROWER\s?\d? |GUARANTOR \d )?(EXPERIAN |EQUIFAX |TRANSUNION )?FICO MODEL USED", head)
        if used:
            note["model_tables"] += 1
            note["columns"] = ["FICO MODEL USED"]
        for n in range(h + 1, end):
            line = lines[n]
            if len(line.strip()) < 20:
                continue
            raw = line[0:seller.start() if seller else 40] if cust else ""
            found = [t for t in re.findall(r"[^\s()\[\]]+", raw) if not _MASKED.search(t)]  # the customer's number if it shows, else the review firm's, else its place in the section
            loan = found[-1] if found else f"line{n - h}"
            if report:
                pulls[loan] = report_month(next(iter(re.findall(r"\d{1,2}/\d{1,2}/\d{2,4}", line[report.start():report.end() + 1])), ""))
            if score:
                digits = re.findall(r"\b\d{3}\b", line[score.start():score.end() + 1])
                scores[loan] = int(digits[0]) if digits else None
            if used:
                names = sorted({re.sub(r"\s+", " ", m.group(0)) for m in _PRE_MODEL.finditer(line[max(0, first.start() - 12):used[-1] + 12])})
                rows.append({"id": loan, "models": names, "vs_value": False, "pull": None, "score": None})
                note["rows"] += 1
    for r in rows:
        r["pull"], r["score"] = pulls.get(r["id"]), scores.get(r["id"])
    if not any(r["models"] for r in rows):  # codes in columns this cannot place: the rows would only repeat loans under other numbers
        note["rows"] = 0
        return [], note
    note["listed"] = len({r["id"] for r in rows if not _UNNUMBERED.fullmatch(r["id"])})
    return rows, note


def mentions_vantage(text: str) -> int:
    """How many times an exhibit names VantageScore, leaving out template column headings."""
    plain = _TEMPLATE_WORDS.sub(" ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
    return len(_VANTAGE_SCORE.findall(plain))


def deal_name(text: str, file_name: str) -> str | None:
    """The deal, from the filing's cover page or, failing that, its file name."""
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
    m = re.search(r"([^.;:()]{3,90}?)\s*\(?\s*Exact name of (?:the )?issu", plain, re.I)
    for chunk in ([m.group(1)] if m else []) + [plain]:
        d = _DEAL.search(chunk)
        if d and not re.match(r"(OMB|Form|Rule|Section|Date|December|January|October|September|November|August|July|June|May|April|March|February)\b", d.group(1)):
            return f"{re.sub(r'^(A|An|The) ', '', d.group(1))} {d.group(2)}-{d.group(3)}"
    m = re.search(r"([a-z]{2,8})[-_]?(20\d\d)[-_]?([a-z]{1,5}\d{0,3})", file_name, re.I)
    return f"{m.group(1).upper()} {m.group(2)}-{m.group(3).upper()}" if m else None


def _read_jsonl(path: Path) -> list[dict]:
    """Every whole line; a run that was stopped can leave a part line at the end, and its exhibit gets read again."""
    out = []
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _append_jsonl(path: Path, rows: list[dict]):
    if rows:
        with open(path, "a") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")


def _report(h: dict) -> tuple[str, str]:
    """The report a file is part of: its filing and exhibit number, EX-99.1 whether it comes as one file or as schedules 5A to 5D (EX-99.1(SC5A))."""
    return h["adsh"], re.sub(r"\(.*", "", str(h.get("type") or "")).strip().upper()


def _numbers_on_disk(loans: Path, files: set) -> set:
    """The loan numbers the loan file holds for these files, row places aside."""
    found = set()
    if not files or not loans.exists():
        return found
    adshs = {a for a, _ in files}
    with open(loans) as f:
        for line in f:
            if any(a in line for a in adshs):
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if (r.get("adsh"), r.get("file")) in files and not _UNNUMBERED.fullmatch(r.get("id") or ""):
                    found.add(r["id"])
    return found


def _report_copies(read: list[tuple], others: dict, loans: Path) -> None:
    """The files of one report read together, each (rows, note): a table in one of them that only repeats, with codes or blanks and no loan numbers, loans the report
    lists by number in its other files is left out (_copies), as the ASF schedules 5C and 5D of a report whose schedules 5A and 5B list the same loans. The report lists
    the distinct numbers of all its files, or more where one file says so (its note's listed); others gives the notes of its files read before, by filing and file."""
    if not any(_copy_tables(rows) for rows, _ in read):
        return
    numbers = {r["id"] for rows, _ in read for r in rows if not _UNNUMBERED.fullmatch(r["id"])} | _numbers_on_disk(loans, set(others))
    listed = max([len(numbers)] + [note.get("listed") or 0 for _, note in read] + [n.get("listed") or 0 for n in others.values()])
    for rows, note in read:
        kept, gone = _copies(rows, listed)
        if gone:
            rows[:] = kept
            note.update(rows=len(kept), copies=(note.get("copies") or 0) + gone)


def collect(since: str | None = None, until: str | None = None, limit: int | None = None, log=print, client: Edgar | None = None, home: Path | None = None) -> dict:
    """Searches, then reads each exhibit and filing not read yet, the files of one report (_report) together, so a table that repeats loans another file lists counts
    them once (_report_copies). Safe to stop and run again: what is done is on disk, one line at a time, each report's files once all are read."""
    home = home or paths.DATA / "edgar"
    home.mkdir(parents=True, exist_ok=True)
    hits_path, exhibits_path, loans_path, mentions_path, filings_path = (home / f"{n}.jsonl" for n in ("hits", "exhibits", "loans", "mentions", "filings"))
    known = {(h["adsh"], h["file"], h["kind"]): h for h in _read_jsonl(hits_path)}
    until = until or date.today().isoformat()
    if since is None:
        last = max((h["date"] for h in known.values() if h.get("date")), default=None)
        since = (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)).isoformat() if last else BACKFILL_FROM
    client = client or Edgar()
    log(f"searching {since} to {until}")
    fresh = {}
    for h in discover(client, since, until, log):
        key = (h["adsh"], h["file"], h["kind"])
        if key not in known:
            fresh[key] = h
    known.update(fresh)
    _append_jsonl(hits_path, list(fresh.values()))
    hits = list(known.values())
    is_mortgage = lambda h: not NOT_PRIVATE_MORTGAGE.search(h["filer"]) and str(h.get("type") or "").startswith("EX")  # noqa: E731
    notes = {(e["adsh"], e["file"]): e for e in _read_jsonl(exhibits_path)}
    queue = sorted({(h["date"], h["adsh"], h["file"], h["cik"]) for h in hits if h["kind"] == "model" and is_mortgage(h) and (h["adsh"], h["file"]) not in notes}, reverse=True)
    if limit:
        queue = queue[:limit]
    log(f"{len(queue)} exhibits to read")
    report = {(h["adsh"], h["file"]): _report(h) for h in hits}
    reports = {}
    for item in queue:
        reports.setdefault(report.get((item[1], item[2])), []).append(item)
    loans_added = n = 0
    for key, items in reports.items():
        files = []
        for day, adsh, name, cik in items:
            n += 1
            body = client.get(exhibit_url(cik, adsh, name))
            if body is None:
                _append_jsonl(exhibits_path, [{"adsh": adsh, "file": name, "date": day, "error": True}])
                continue
            text = body.decode("utf-8", errors="replace")
            rows, note = parse_exhibit(text)
            files.append((rows, {"adsh": adsh, "file": name, "date": day, "kb": len(body) // 1024, "vantage": mentions_vantage(text), **note}))
            if n % 25 == 0:
                log(f"  {n}/{len(queue)} exhibits, {loans_added:,} loan rows, {client.requests} requests")
        _report_copies(files, {k: e for k, e in notes.items() if report.get(k) == key and not e.get("error")}, loans_path)
        for rows, note in files:
            _append_jsonl(loans_path, [{"adsh": note["adsh"], "file": note["file"], **r} for r in rows])
            _append_jsonl(exhibits_path, [note])
            loans_added += len(rows)
    done = {(e["adsh"], e["file"]) for e in _read_jsonl(exhibits_path)}
    seen = {(m["adsh"], m["file"]) for m in _read_jsonl(mentions_path)}
    queue = sorted({(h["date"], h["adsh"], h["file"], h["cik"]) for h in hits if h["kind"] == "mention" and is_mortgage(h) and (h["adsh"], h["file"]) not in done and (h["adsh"], h["file"]) not in seen}, reverse=True)
    if limit:
        queue = queue[:limit]
    log(f"{len(queue)} other exhibits that name VantageScore to read")
    for day, adsh, name, cik in queue:
        body = client.get(exhibit_url(cik, adsh, name))
        text = (body or b"").decode("utf-8", errors="replace")
        count = mentions_vantage(text)
        plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
        at = _VANTAGE_SCORE.search(_TEMPLATE_WORDS.sub(" ", plain))
        _append_jsonl(mentions_path, [{"adsh": adsh, "file": name, "date": day, "count": count, "snippet": _TEMPLATE_WORDS.sub(" ", plain)[max(0, at.start() - 90):at.start() + 90] if at else None}])
    read = {f["adsh"] for f in _read_jsonl(filings_path)}
    wanted = sorted({(h["adsh"], h["cik"]) for h in hits if h["kind"] in ("model", "mention") and is_mortgage(h) and h["adsh"] not in read})
    if limit:
        wanted = wanted[:limit]
    log(f"{len(wanted)} filings to read for their deal names")
    for adsh, cik in wanted:
        base = f"{ARCHIVES}/{int(cik)}/{adsh.replace('-', '')}"
        page = (client.get(f"{base}/{adsh}-index.html") or b"").decode("utf-8", errors="replace")
        m = re.search(r'<a href="([^"]+)"[^>]*>([^<]+)</a></td>\s*<td[^>]*>\s*ABS-15G', page)
        main = (client.get("https://www.sec.gov" + m.group(1)) or b"").decode("utf-8", errors="replace") if m else ""
        _append_jsonl(filings_path, [{"adsh": adsh, "cik": cik, "main": m.group(2) if m else None, "deal": deal_name(main, m.group(2) if m else ""), "cover": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", main)))[:2500]}])
    return {"since": since, "until": until, "new_hits": len(fresh), "loan_rows_added": loans_added, "requests": client.requests}


# Kinds of deal, going by the deal's name; the first that matches applies.
DEAL_KINDS = [("second", "Second liens and home equity", re.compile(r"-(CES|HE|HELOC|SL|LOC|HLTV)\d*$", re.I)), ("nonqm", "Non-QM", re.compile(r"NQM|^Verus |^Cross 20\d\d-H\d", re.I)),
              ("investor", "Investor", re.compile(r"-(INV|DSC|DSCR)\d*$", re.I)), ("prime", "Prime and jumbo", re.compile(r"-(PJ|J|S)\d*$|^Sequoia ", re.I)), ("seasoned", "Re-performing", re.compile(r"-(RPL|NPL|RCF|R)\d*$", re.I)), ("other", "Other", re.compile(r""))]
FAMILY_COUNTS = ("classic", "fico_new", "vs4", "vs_old", "unclear", "blank")
PERIOD_MIN = 100
AGENCY_OPEN = "2026-05"  # the month Fannie and Freddie began taking VS4 from their first lenders
FILER_TOP = 25
_FILER_WORDS = {"GS": "GS", "EFMT": "EFMT", "CCC": "CCC", "CRM": "CRM", "MFRA": "MFRA", "NQM": "NQM", "VMC": "VMC", "RCF": "RCF", "PRP": "PRP", "TVC": "TVC", "GCAT": "GCAT", "OVLAC": "OVLAC", "BFA": "BFA", "VCC": "VCC", "III": "III", "II": "II", "IV": "IV", "VI": "VI", "VII": "VII", "SG": "SG", "J.P.": "J.P.", "SLC": "SLC", "APF": "APF", "APCA": "APCA", "KH": "KH", "WCM1": "WCM1", "BINOM": "Binom"}


def _filer_name(name: str) -> str:
    out = short_name(re.sub(r"\s+Depositor\s+(?=[IVX]+\b)", " Depositor ", name))
    out = " ".join(_FILER_WORDS.get(w.upper(), w) for w in out.split())
    return out


def deal_kind(deal: str | None) -> str:
    return next(k for k, _, rule in DEAL_KINDS if rule.search(deal or ""))


def deal_label(name: str) -> str:
    """A deal's name as the page prints it (market.js dealName): as filed, with an all-capital name of two or more words in title case and the shelf filed both ways
    in one spelling."""
    name = re.sub(r"^[A-Z][A-Z ]+(?= 20\d\d-)", lambda m: m.group(0).title() if " " in m.group(0) else m.group(0), name)
    return re.sub(r"^Cross (?=20\d\d-)", "CROSS ", name)


def _quarter(day: str) -> str:
    return f"{day[:4]}-Q{(int(day[5:7]) + 2) // 3}"


def _quarter_label(q: str) -> str:
    return f"Q{q[-1]} {q[:4]}"


def _month_label(m: str) -> str:
    return date(int(m[:4]), int(m[5:7]), 1).strftime("%b %Y")


def _tally(rows: list[dict]) -> dict:
    n = len(rows)
    counts = {f"{k}_n": sum(1 for r in rows if r["family"] == k) for k in FAMILY_COUNTS}
    named = n - counts["blank_n"]
    round6 = lambda v: round(v, 6) if n else None  # noqa: E731
    out = {"n": n, "named": named, **counts}
    for k in FAMILY_COUNTS:
        out[k] = round6(counts[f"{k}_n"] / n if n else 0)
    out["none"] = out["blank"]
    out["unnamed"] = out["unclear"]
    out["fico"] = round6((counts["classic_n"] + counts["fico_new_n"]) / n if n else 0)
    out["vs"] = round6((counts["vs4_n"] + counts["vs_old_n"]) / n if n else 0)
    return out


def _loan_key(deal: str, loan_id: str, file: tuple = ()) -> tuple:
    """A long loan number is the same loan wherever it appears, as when a loan moves to a later deal; a short one is only sure within its deal. A loan with no number,
    its row's place in a table or its line in a fixed-width report (_UNNUMBERED), is only sure within its own file (file: its filing and file name), so two files'
    places never join by place alone: rows 0 to 37 of a Business Purpose schedule are not rows 0 to 37 of the Supplemental Data schedule (_aligned joins them)."""
    if _UNNUMBERED.fullmatch(loan_id):
        return (deal, *file, loan_id)
    return (None, loan_id) if len(re.sub(r"\D", "", loan_id)) >= 7 else (deal, loan_id)


def _loan_keys(where: str, r: dict) -> list[tuple]:
    """A loan row's keys: its number (_loan_key, where: its deal, and the row's file for a place) and each other number it carries with seven figures or more (alt),
    any of which names the loan."""
    return [_loan_key(where, r["id"], (r.get("adsh"), r.get("file")))] + [(None, a) for a in r.get("alt") or () if len(re.sub(r"\D", "", a)) >= 7]


def _one_loan(keys: list[list[tuple]]) -> list[tuple]:
    """For each loan row's keys, the key of the loan it is: rows that share any key, directly or through other rows, are one loan."""
    parent = {}

    def root(k):
        while parent.get(k, k) != k:
            parent[k] = parent.get(parent[k], parent[k])
            k = parent[k]
        return k

    for ks in keys:
        top = root(ks[0])
        for k in ks[1:]:
            other = root(k)
            if other != top:
                parent[other] = top
    return [root(ks[0]) for ks in keys]


ALIGN_MIN = 10  # scored loans a schedule needs before the order of its scores can say which loans of another schedule it lists
ALIGN_SHARE = 0.95  # the share of them that must line up, in order, with the other schedule's loans
ALIGN_OVER = 0.25  # and by how much that must beat the same schedule read backwards, which lines up by chance about as well as another pool's loans would


def _units(rows: list[dict]) -> dict[str, list[dict]]:
    """One file's loans, each once and in its order, by unit: its numbered loans, and each table of row places or its fixed-width lines (_UNNUMBERED), a schedule
    whose loan numbers are masked. Each loan's id, score, credit report month, models and whether it names a VantageScore, its lines in the file together."""
    out = {}
    for r in rows:
        m = _PLACE.fullmatch(r["id"])
        unit = f"table {m.group(1)}" if m else "lines" if _UNNUMBERED.fullmatch(r["id"]) else "numbered"
        x = out.setdefault(unit, {}).setdefault(r["id"], {"id": r["id"], "score": None, "pull": None, "models": set(), "vs": False})
        x["score"] = x["score"] or r.get("score")
        x["pull"] = x["pull"] or r.get("pull")
        x["models"].update(r.get("models") or ())
        x["vs"] = x["vs"] or bool(r.get("vs_value")) or any(model_family(v) in _VS_FAMILIES for v in r.get("models") or ())
    return {u: list(v.values()) for u, v in out.items()}


def _in_order(small: list[dict], big: list[dict], among: tuple, key) -> list[tuple[int, int]]:
    """Pairs (i, j) in order: each of small's loans (indexes among[0], in order) with the first of big's (indexes among[1]) after the last pair that has the same key.
    A loan whose key is None pairs with none."""
    where = {}
    for j in among[1]:
        k = key(big[j])
        if k is not None:
            where.setdefault(k, []).append(j)
    pairs, at = [], -1
    for i in among[0]:
        k = key(small[i])
        js = where.get(k, ()) if k is not None else ()
        n = bisect.bisect_right(js, at)
        if n < len(js):
            at = js[n]
            pairs.append((i, at))
    return pairs


def _between(pairs: list[tuple[int, int]], n_small: int, n_big: int) -> list[tuple[range, range]]:
    """The stretches of two schedules between consecutive pairs, as index ranges."""
    edges = [(-1, -1)] + sorted(pairs) + [(n_small, n_big)]
    return [(range(i0 + 1, i1), range(j0 + 1, j1)) for (i0, j0), (i1, j1) in zip(edges, edges[1:])]


def _line_up(small: list[dict], big: list[dict]) -> tuple[list[tuple[int, int]], float, int]:
    """How the loans of one schedule line up, in order, with another's that lists them too, as a Business Purpose schedule's within the Supplemental Data schedule's:
    pairs by score and models first, then by score alone between those, then the loans with no score between those, one for one in order. Gives the pairs, the share
    of small's scored loans paired and how many it has."""
    pairs = _in_order(small, big, (range(len(small)), range(len(big))), lambda x: (x["score"], frozenset(x["models"])) if x["score"] else None)
    for among in _between(pairs, len(small), len(big)):
        pairs += _in_order(small, big, among, lambda x: x["score"])
    for a, b in _between(pairs, len(small), len(big)):
        pairs += zip([i for i in a if not small[i]["score"]], [j for j in b if not big[j]["score"]])
    scored = sum(1 for x in small if x["score"])
    return sorted(pairs), sum(1 for i, _ in pairs if small[i]["score"]) / scored if scored else 0.0, scored


def _same_shape(a: list[dict], b: list[dict]) -> int | None:
    """Two schedules of as many loans whose scores and credit report months, where both give one, agree place by place (ALIGN_SHARE of them): how many places they
    compare, or None."""
    if len(a) != len(b):
        return None
    seen = 0
    for f in ("score", "pull"):
        both = [(x[f], y[f]) for x, y in zip(a, b) if x[f] and y[f]]
        if both and sum(p == q for p, q in both) < ALIGN_SHARE * len(both):
            return None
        seen += len(both)
    return seen


def _aligned(rows: list[dict], report: dict, deal: dict) -> list[tuple[tuple, tuple]]:
    """Loans with no number, in a schedule whose numbers are masked (a file's fixed-width lines or a table of row places, _units), joined to the loans they are in
    another schedule, as pairs of (filing, file, id). For each such schedule, in turn:
    - in order: within its report (filing and exhibit number, _report), a schedule whose scored loans line up in order with another's, ALIGN_MIN of them or more,
      ALIGN_SHARE of them lined up and ALIGN_OVER more than read backwards (_line_up): a Business Purpose schedule's loans within the Supplemental Data schedule's;
    - same shape: else the closest schedule of its deal with as many loans whose scores and credit report months agree place by place (_same_shape), closest being
      of the same report, then the same filing, then the most places compared and the longest common file name: one schedule split over two files (CIM 2025-I1's 9
      and 9b), an ASF tape filed as an exhibit of its own, a report filed again;
    - by count: else a table of two rows or more with no score takes, in order, as many loans its report lists by number that no schedule has joined yet and that
      name no VantageScore, where there are as many: a model table whose every number is masked (Sequoia 2025-9's), of loans its report lists.
    rows: loan lines with their filing and file; report: (filing, file) to its report; deal: filing to its deal."""
    files = {}
    for r in rows:
        files.setdefault((r["adsh"], r["file"]), []).append(r)
    units = {(f, u): loans for f, rs in files.items() for u, loans in _units(rs).items()}
    by_report, by_deal = {}, {}
    for f, u in units:
        by_report.setdefault(report.get(f, (f[0], "")), []).append((f, u))
        by_deal.setdefault(deal.get(f[0], f[0]), []).append((f, u))
    joins, done, used = [], set(), set()

    def join(a, i, b, j):
        x, y = (*a[0], units[a][i]["id"]), (*b[0], units[b][j]["id"])
        joins.append((x, y))
        used.update(z for z, u in ((x, a), (y, b)) if u[1] == "numbered")

    for group in by_report.values():
        for n, a in enumerate(group):
            for b in group[n + 1:]:
                if a[1] == b[1] == "numbered":
                    continue
                small, big = (a, b) if len(units[a]) <= len(units[b]) else (b, a)
                pairs, share, scored = _line_up(units[small], units[big])
                if scored < ALIGN_MIN or share < ALIGN_SHARE or share - _line_up(units[small][::-1], units[big])[1] < ALIGN_OVER:
                    continue
                for i, j in pairs:
                    join(small, i, big, j)
                done.update(u for u in (a, b) if u[1] != "numbered")
    for group in by_deal.values():
        for a in group:
            if a[1] == "numbered" or a in done:
                continue
            best = None
            for b in group:
                seen = None if b == a else _same_shape(units[a], units[b])
                if seen is not None:
                    rank = (report.get(a[0]) == report.get(b[0]), a[0][0] == b[0][0], seen, len(os.path.commonprefix([a[0][1], b[0][1]])))
                    best = best if best and best[0] >= rank else (rank, b)
            if best:
                for i in range(len(units[a])):
                    join(a, i, best[1], i)
                done.update(u for u in (a, best[1]) if u[1] != "numbered")
    for group in by_report.values():
        for a in group:
            loans = units[a]
            places = [int(x["id"].rsplit("-", 1)[1]) for x in loans] if a[1].startswith("table") else []
            if a in done or len(loans) < 2 or any(x["score"] for x in loans) or not places or max(places) - min(places) + 1 != len(places):
                continue
            listed, ids = [], set()
            for b in sorted((b for b in group if b[1] == "numbered"), key=lambda b: (b[0] != a[0], b[0])):
                for k, x in enumerate(units[b]):
                    if not x["vs"] and x["id"] not in ids and (*b[0], x["id"]) not in used:
                        ids.add(x["id"])
                        listed.append((b, k))
            if len(listed) >= len(loans):
                for i, (b, k) in enumerate(listed[:len(loans)]):
                    join(a, i, b, k)
                done.add(a)
    return joins


REUSE_MIN = 10  # numbers two deals must share, with a score or a month on both sides, before their disagreeing can say the deals reuse numbers


def _reused(lines: list[tuple]) -> set[tuple[str, str]]:
    """Pairs of deals that give the same long numbers to other loans (GCAT 2025-NQM3 and NQM5 both number theirs 2025xxxx): of the numbers two deals share whose
    lines both give a score or both a credit report month, REUSE_MIN or more, over half name lines that disagree, a different score and not the same month, or a
    different month and not the same score. A loan moved to a later deal keeps its score or its month (OBX 2025-NQM19 and NQM22 share 150 loans: three changed
    score, none month), and one loan reviewed again for a later deal may change both, so a few shared numbers say nothing. lines: (deal, keys, score, month), one
    per loan line."""
    seen = {}
    for deal, keys, score, month in lines:
        for k in keys:
            if k[0] is None:
                g = seen.setdefault(k, {}).setdefault(deal, (set(), set()))
                if score:
                    g[0].add(score)
                if month:
                    g[1].add(month)
    tally = {}
    for by_deal in seen.values():
        names = sorted(by_deal)
        for n, a in enumerate(names):
            for b in names[n + 1:]:
                (sa, ma), (sb, mb) = by_deal[a], by_deal[b]
                if (sa and sb) or (ma and mb):
                    t = tally.setdefault((a, b), [0, 0])
                    t[0] += 1
                    t[1] += bool(((sa and sb and not sa & sb) or (ma and mb and not ma & mb)) and not (sa & sb or ma & mb))
    return {pair for pair, (compared, differ) in tally.items() if compared >= REUSE_MIN and differ * 2 > compared}


def _apart(lines: list[tuple], reused: set[tuple[str, str]]) -> dict[tuple, tuple]:
    """For a long number two deals reuse (_reused), each deal's key for it, so their loans stay apart; deals that share it and do not reuse numbers keep one key.
    lines: (deal, keys) for each loan line."""
    carriers = {}
    for deal, keys in lines:
        for k in keys:
            if k[0] is None:
                carriers.setdefault(k, set()).add(deal)
    out = {}
    for k, ds in carriers.items():
        names = sorted(ds)
        if not any((a, b) in reused for n, a in enumerate(names) for b in names[n + 1:]):
            continue
        groups = []  # each deal joins the first group with no deal it reuses numbers with
        for d in names:
            g = next((g for g in groups if not any(tuple(sorted((d, e))) in reused for e in g)), None)
            groups.append([d]) if g is None else g.append(d)
        for g in groups:
            for d in g:
                out[(k, d)] = (None, k[1], g[0])
    return out


def build_datasets() -> dict[str, list[dict]]:
    home = paths.DATA / "edgar"
    hits = _read_jsonl(home / "hits.jsonl")
    if not hits:
        return {"private_label": []}
    mortgage = [h for h in hits if not NOT_PRIVATE_MORTGAGE.search(h["filer"]) and str(h.get("type") or "").startswith("EX")]
    info = {}
    for h in sorted(mortgage, key=lambda h: h["date"]):
        info.setdefault(h["adsh"], h)
    deals = {f["adsh"]: f["deal"] for f in _read_jsonl(home / "filings.jsonl")}
    deal_of = {a: deals.get(a) or a for a in info}
    rows = [r for r in _read_jsonl(home / "loans.jsonl") if r["adsh"] in info]
    extra = {}  # a loan with no number: the key of the loan it is in another schedule (_aligned)
    for a, b in _aligned(rows, {(h["adsh"], h["file"]): _report(h) for h in hits}, deal_of):
        extra.setdefault(a, []).append(_loan_key(deal_of[b[0]], b[2], b[:2]))
    merged, lines = {}, []
    with_model = set()
    for r in rows:
        h = info[r["adsh"]]
        if r.get("vs_value") or any(model_family(v) != "junk" for v in r["models"]):
            with_model.add(r["adsh"])
        deal = deal_of[r["adsh"]]
        lines.append((r, h, deal, _loan_keys(deal, r) + extra.get((r["adsh"], r["file"], r["id"]), [])))
    apart = _apart([(deal, keys) for _, _, deal, keys in lines], _reused([(deal, keys, r.get("score"), r.get("pull")) for r, _, deal, keys in lines]))
    if apart:
        lines = [(r, h, deal, [apart.get((k, deal), k) for k in keys]) for r, h, deal, keys in lines]
    for (r, h, deal, _), loan in zip(lines, _one_loan([keys for *_, keys in lines])):
        m = merged.setdefault(loan, {"deal": deal, "adsh": r["adsh"], "date": h["date"], "filer": h["filer"], "models": set(), "vs_value": False, "pull": None})
        m["models"].update(r["models"])
        m["vs_value"] = m["vs_value"] or r.get("vs_value", False)
        m["pull"] = m["pull"] or r.get("pull")
        if h["date"] < m["date"]:  # the deal that first filed it
            m.update(date=h["date"], deal=deal, adsh=r["adsh"], filer=h["filer"])
    first_filed = {}
    for m in merged.values():
        first_filed[m["deal"]] = min(first_filed.get(m["deal"], m["date"]), m["date"])
    for m in merged.values():
        m["date"] = first_filed[m["deal"]]
        fam = loan_family(sorted(m["models"]))
        if m["vs_value"] and not fam.startswith("vs"):
            fam = "vs_other"
        m["family"] = "vs_old" if fam == "vs_other" else fam
        m["kind"] = deal_kind(m["deal"])
        m["fico_named"] = any(model_family(v) in ("classic", "fico_new") for v in m["models"])
    loans = list(merged.values())
    vs4_alone = lambda rows: sum(1 for m in rows if m["family"] == "vs4" and not m["fico_named"])  # noqa: E731
    filings_any = {h["adsh"] for h in mortgage if h["kind"] in ("model", "score")}
    lags = sorted((int(m["date"][:4]) - int(m["pull"][:4])) * 12 + int(m["date"][5:7]) - int(m["pull"][5:7]) for m in loans if m["pull"])
    recent = [m for m in loans if m["pull"] and m["pull"] >= AGENCY_OPEN]
    out = [{"view": "meta", "from": BACKFILL_FROM, "through": max(h["date"] for h in hits), "filings": len(filings_any | with_model), "with_model": len(with_model), "exhibits": len(_read_jsonl(home / "exhibits.jsonl")), "deals": len({m["deal"] for m in loans}),
            "dated": round(sum(1 for m in loans if m["pull"]) / len(loans), 6) if loans else None, "recent_from": AGENCY_OPEN, "recent_n": len(recent), "recent_vs_n": sum(1 for m in recent if m["family"] in ("vs4", "vs_old")),
            "recent_vs": round(sum(1 for m in recent if m["family"] in ("vs4", "vs_old")) / len(recent), 6) if recent else None, "lag_months": lags[len(lags) // 2] if lags else None,
            "vs_no_fico_n": sum(1 for m in loans if m["family"] in ("vs4", "vs_old") and not m["fico_named"]), "vs4_no_fico_n": vs4_alone(loans), **_tally(loans)}]
    quarters = {}
    for m in loans:
        quarters.setdefault(_quarter(m["date"]), []).append(m)
    filed_by_q, model_by_q = {}, {}
    for adsh in filings_any | with_model:
        h = info.get(adsh)
        if h:
            filed_by_q.setdefault(_quarter(h["date"]), set()).add(adsh)
            if adsh in with_model:
                model_by_q.setdefault(_quarter(h["date"]), set()).add(adsh)
    for i, q in enumerate(sorted(quarters)):
        out.append({"view": "period", "basis": "filed", "period": q, "label": _quarter_label(q), "order": i, "filings": len(filed_by_q.get(q, ())), "with_model": len(model_by_q.get(q, ())), **_tally(quarters[q])})
    months = {}
    for m in loans:
        if m["pull"]:
            months.setdefault(m["pull"], []).append(m)
    for i, k in enumerate(sorted(k for k, v in months.items() if len(v) >= PERIOD_MIN)):
        out.append({"view": "period", "basis": "pulled", "period": k, "label": _month_label(k), "order": i, **_tally(months[k])})
    for i, (key, label, _) in enumerate(DEAL_KINDS):
        rows = [m for m in loans if m["kind"] == key]
        if rows:
            out.append({"view": "kind", "key": key, "label": label, "order": i, "deals": len({m["deal"] for m in rows}), **_tally(rows)})
    pulled = {}
    for m in loans:
        if m["family"] == "vs4":
            pulled.setdefault(m["pull"][:4] if m["pull"] else None, []).append(m)
    for i, year in enumerate(sorted(pulled, key=lambda y: (y is None, y or ""))):
        out.append({"view": "vs4_year", "key": year or "undated", "label": year or "No credit report date", "order": i, "vs4_n": len(pulled[year]), "vs4_no_fico_n": vs4_alone(pulled[year])})
    filers = {}
    for h in mortgage:
        if h["kind"] in ("model", "score"):
            filers.setdefault(h["filer"], set()).add(h["adsh"])
    by_filer = {}
    for m in loans:
        by_filer.setdefault(m["filer"], []).append(m)
    ranked = sorted(filers, key=lambda f: (-len(filers[f]), f))[:FILER_TOP]
    for i, f in enumerate(ranked):
        out.append({"view": "filer", "key": f, "label": _filer_name(f), "rank": i + 1, "filings": len(filers[f]), "with_model": len(filers[f] & with_model), **_tally(by_filer.get(f, []))})
    by_deal = {}
    for m in loans:
        by_deal.setdefault(m["deal"], []).append(m)
    for deal, rows in sorted(by_deal.items(), key=lambda kv: (kv[1][0]["date"], kv[0]), reverse=True):
        t = _tally(rows)
        if t["vs4_n"] + t["vs_old_n"]:
            h = info[rows[0]["adsh"]]
            out.append({"view": "deal", "key": deal, "label": deal if deal != rows[0]["adsh"] else _filer_name(h["filer"]), "filed": rows[0]["date"], "filer": _filer_name(h["filer"]), "kind": deal_kind(deal),
                        "url": f"{ARCHIVES}/{int(h['cik'])}/{rows[0]['adsh'].replace('-', '')}/{rows[0]['adsh']}-index.html", "vs4_no_fico_n": vs4_alone(rows), **t})
    seen = {}
    for x in _read_jsonl(home / "mentions.jsonl"):
        h = info.get(x["adsh"])
        if not h or not x.get("count"):
            continue
        deal = deals.get(x["adsh"]) or x["adsh"]
        cur = seen.setdefault(deal, {"view": "mention", "key": deal, "label": deal if deal != x["adsh"] else _filer_name(h["filer"]), "filed": x["date"], "filer": _filer_name(h["filer"]), "kind": deal_kind(deal), "count": 0,
                                     "url": f"{ARCHIVES}/{int(h['cik'])}/{x['adsh'].replace('-', '')}/{x['adsh']}-index.html"})
        cur["count"] += x["count"]
        cur["filed"] = min(cur["filed"], x["date"])
    out.extend(sorted(seen.values(), key=lambda r: (r["filed"], r["key"]), reverse=True))
    keys = sorted({k for r in out for k in r})
    return {"private_label": [{k: r.get(k) for k in keys} for r in out]}


# ---- The VantageScore watch: every filing on these forms that names VantageScore at all, for the weekly list in the private-label section (watch.py builds it) ----
WATCH_FROM = "2026-07-01"
WATCH_FORMS = ("10-K", "10-Q", "8-K", "ABS-15G", "FWP")  # annual, quarterly and current reports, deal reports and free-writing prospectuses
DEAL_FORMS = ("ABS-15G", "FWP")
WATCH_QUERY = '"VantageScore"'
WATCH_WORDS = 45  # the words of a filing's sentence the list prints, around its mention
WATCH_TAIL = 15  # and up to this many more, when that reaches the sentence's end
WATCH_KEYS = ("adsh", "file", "cik", "date", "form", "type", "desc", "filer", "sics")
TAPE_FIELDS = ("tape_n", "tape_named", "tape_vs", "tape_vs4", "tape_vs_old", "tape_vs_alone", "tape_vs_classic", "tape_vs4_alone", "tape_old_alone")  # what tape_counts gives each filing
# Who matters for mortgages, by industry code: the GSEs (6111), mortgage bankers and brokers (6162, 6163), mortgage insurers (6351) and the credit bureaus (7320).
MORTGAGE_SICS = {"6111", "6162", "6163", "6351", "7320"}
_MORTGAGE_NAME = re.compile(r"\b(mortgages?|home loans?|homes|residential|housing|fannie mae|freddie mac|fair isaac|fico|transunion|equifax|experian|mgic|radian|essent|nmi holdings|enact|"
                            r"genworth|rocket companies|rocket mortgage|uwm|united wholesale|loandepot|pennymac|guild holdings|mr\.? cooper|rithm|redwood trust|annaly|chimera|mfa financial|"
                            r"ellington|angel oak|two harbors|sequoia|onslow|altisource|newrez|onity|ocwen|finance of america|arch capital)\b", re.I)
_AUTO = re.compile(r"\b(auto|autos|automobile|motor|vehicles?|cars?|carmax|carvana|exeter|westlake|credit acceptance|consumer portfolio services|world omni|americredit|flagship credit|veros)\b", re.I)
_CARD = re.compile(r"\b(cards?|synchrony|bread financial|capital one|discover financial|american express|mission lane|continental finance)\b", re.I)
_CONSUMER = re.compile(r"\b(consumer|personal|installment|regional management|onemain|oportun|upstart|affirm|lendingclub|pagaya|signet|jewel\w*|student|navient|sofi|enova|world acceptance|"
                       r"mariner|lendmark|rktl|rocket loans|best egg|marlette|prosper|cherry|timeshare|solar|marine|equipment)\b", re.I)
_MORTGAGE_TEXT = re.compile(r"\b(mortgages?|GSEs?|Fannie|Freddie|FHFA|home equity|HELOCs?|MBS|loan-level price|LLPAs?|housing|homebuyers?|homeowners?)\b", re.I)
_ABBR = re.compile(r"(?:\b(?:U\.S|Inc|Corp|Co|Ltd|No|Nos|vs|e\.g|i\.e|etc|approx|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Mr|Ms|Dr|St|L\.P|N\.A)|(?<![\w-])[A-Z])$")  # an initial, not 10-K.
# Where a sentence stops: a stop and any closing quote before a space, a slide's bullet, or a footnote's number before its first word, as in "(2)Credit scores".
_STOP = re.compile(r"[.?!][\"”’)\]]*(?=\s|$)|\s[•✓▪●■◦](?=\s)|\(\d{1,2}\)\s?(?=[A-Z])")
_OPENERS = r"(?:In|On|As|At|The|We|Our|During|Effective|Beginning|Since|For|With|After|Under|Following|Recently)\b"
# A heading run into the sentence, its words led by a capital or a figure, as in "Market Developments On April 22, ..." or "VantageScore 4.0 Expansion Effective ...".
_HEADING = re.compile(rf"^(?:[A-Z0-9][\w.’'&-]*\s+){{2,6}}(?={_OPENERS})")
# A page's footer run into its words: a slide's copyright line, and a page number with its "Confidential" mark or "Table of Contents" link, as in "22Confidential".
_FOOTER = re.compile(r"\s*©\s*\d{4}\b[^.]*\.(\s*All Rights Reserved\.)?|^\d{1,3}\s?(?:Confidential|Table of Contents)\b\s*", re.I)
WATCH_NEAR = 12  # words either side of a mention within which a share and mortgage words make its passage the one shown
_FIGURE = re.compile(r"\d%")


def watch_class(row: dict, near_mortgage: bool | None = None) -> str:
    """Whether a filing matters for mortgages: mortgage, else the class it is left out under: auto, card, consumer or other, or unknown until its document is open. A
    filer on auto, card or consumer loans goes by that name; a deal report (DEAL_FORMS) is a private-label sponsor's unless its filer is one the deal search leaves out;
    a company counts by its name or industry code, else by mortgage words around its mention of VantageScore."""
    filer = row.get("filer") or ""
    for cls, rule in (("auto", _AUTO), ("card", _CARD), ("consumer", _CONSUMER)):
        if rule.search(filer):
            return cls
    if row.get("form") in DEAL_FORMS:
        return "other" if NOT_PRIVATE_MORTGAGE.search(filer) else "mortgage"
    if _MORTGAGE_NAME.search(filer) or MORTGAGE_SICS & set(row.get("sics") or []):
        return "mortgage"
    return "unknown" if near_mortgage is None else "mortgage" if near_mortgage else "other"


def _plain(text: str) -> str:
    """A document's words: no scripts, styles or tags, one space between words, and none left before a mark or a stop that a tag split off."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", text))))
    return re.sub(r"\s+([.,;:!?])(?=\s|$)", r"\1", re.sub(r"\s+([®™])", r"\1", text)).strip()


def _sentence_at(plain: str, at: int, end: int) -> str:
    """The sentence around plain[at:end]: from the stop before it (_STOP) to the stop after, passing over the stop of an abbreviation (U.S., Inc., Oct.) or an initial,
    at most 1,500 characters either way, without its quote marks or a heading run into it."""
    def real(m):
        return not (m.group(0)[0] == "." and _ABBR.search(plain[max(0, m.start() - 6):m.start()]))
    start = max([m.end() for m in _STOP.finditer(plain, max(0, at - 1500), at) if real(m)], default=max(0, at - 1500))
    after = next((m for m in _STOP.finditer(plain, end, min(len(plain), end + 1500)) if real(m)), None)
    stop = min(len(plain), end + 1500) if after is None else after.end() if after.group(0)[0] in ".?!" else after.start()
    sentence = _FOOTER.sub(" ", plain[start:stop].strip()).strip().strip("\"“”‘’'").strip()
    return _HEADING.sub("", re.sub(r"\s{2,}", " ", sentence))


def _cut(words: list[str], at: int) -> str:
    """A sentence's words cut to WATCH_WORDS around the word at, from 15 before it; a sentence that ends within WATCH_TAIL words past the cut runs to its end, where
    its point tends to be, as in FICO's 10-K: "... which has experienced increased regulatory acceptance in the U.S. mortgage market." """
    if len(words) <= WATCH_WORDS:
        return " ".join(words)
    lo = max(0, min(at - 15, len(words) - WATCH_WORDS))
    hi = len(words) if len(words) - (lo + WATCH_WORDS) <= WATCH_TAIL else lo + WATCH_WORDS
    return ("… " if lo else "") + " ".join(words[lo:hi]) + (" …" if hi < len(words) else "")


_SHARE = re.compile(r"[~<>≈]?\d[\d.,]*%")  # a share as a slide prints it: 35%, ~35%, <5%
_VERSION = re.compile(r"\d+(?:\.\d+)?")


def share_clause(passage: str) -> str:
    """A slide's words, run together with no stop between its title, labels and bullets, cut to the clause from a share to the VantageScore it counts, with its
    version, where mortgage words sit between them: "~35% of mortgage credit pulls in Q3 used VantageScore 4.0". A passage with a stop, one already cut (…), or
    one with no share before a mention within WATCH_NEAR words, stays as it is."""
    if "…" in passage or re.search(r"[.?!](?=\s|$)", passage):
        return passage
    words = passage.split()
    for i, w in enumerate(words):
        if not _VS.search(w):
            continue
        j = next((k for k in range(i - 1, max(-1, i - WATCH_NEAR - 1), -1) if _SHARE.fullmatch(words[k]) or _VS.search(words[k])), None)
        if j is None or _VS.search(words[j]):
            continue  # no share before it, or another mention nearer
        end = i + 1
        if end < len(words) and re.fullmatch(r"score\W?", words[end], re.I):
            end += 1  # "Vantage Score 4.0"
        if end < len(words) and _VERSION.fullmatch(words[end]):
            end += 1
        if _MORTGAGE_TEXT.search(" ".join(words[j:end])):
            return " ".join(words[j:end])
    return passage


def _shown(words: list[str], at: int) -> str:
    """What a passage shows: a slide's clause holding its share (share_clause) where it has one, else the passage cut around the word at (_cut)."""
    whole = " ".join(words)
    clause = share_clause(whole)
    return clause if clause != whole else _cut(words, at)


def vantage_passage(text: str) -> tuple[int, str | None, bool]:
    """How many times a document names VantageScore outside a template's column heading; the sentence to show, as prose, passing over a heading, a table cell or a
    run of figures: the first with a share (as 35%) and mortgage words within WATCH_NEAR words of its mention where there is one, else the first; cut to WATCH_WORDS
    words around that mention (_cut), or, for a slide's words with no stop, to the clause holding its share (share_clause); and whether mortgage words sit near
    any of its mentions."""
    plain = _TEMPLATE_WORDS.sub(" ", _plain(text))
    marks = list(_VANTAGE_SCORE.finditer(plain))
    near = any(_MORTGAGE_TEXT.search(plain[max(0, m.start() - 600):m.end() + 600]) for m in marks)
    first, seen = None, set()
    for m in marks:
        sentence = _sentence_at(plain, m.start(), m.end())
        if sentence in seen or len(re.findall(r"\b[a-z]{3,}\b", sentence)) < 6 or sum(c.isdigit() for c in sentence) * 6 > len(sentence):
            continue
        seen.add(sentence)
        words = sentence.split()
        names = [i for i, w in enumerate(words) if _VS.search(w)] or [0]
        first = first or (words, names[0])
        for i in names:
            around = " ".join(words[max(0, i - WATCH_NEAR):i + WATCH_NEAR + 1])
            if _FIGURE.search(around) and _MORTGAGE_TEXT.search(around):
                return len(marks), _shown(words, i), near
    return len(marks), _shown(*first) if first else None, near


def tape_counts(adshs: set, loans: Path) -> dict[str, dict]:
    """For each filing, from the loan rows the deal search read, each loan once: its loans (tape_n), those its report names a score model for (tape_named: not a
    code, a word this cannot read or a blank alone), those naming VantageScore in a model column or giving a VantageScore (tape_vs), of them VS4 (tape_vs4) and an
    older VantageScore (tape_vs_old), those with no FICO model named beside it (tape_vs_alone; tape_vs4_alone and tape_old_alone of them VS4 and older) and those
    with Classic FICO named beside it (tape_vs_classic). A loan whose report names VantageScore for one bureau and Classic FICO for the others had FICO pulled: it
    is not a loan scored on VantageScore alone. A loan two files of the filing give under two numbers is one loan where they share a number (_loan_keys), and a loan
    with no number is the loan of another schedule of the filing that _aligned finds."""
    if not adshs or not loans.exists():
        return {}
    lines = []
    with open(loans) as f:
        for line in f:
            if not any(a in line for a in adshs):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("adsh") in adshs:
                lines.append(r)
    report = {(h["adsh"], h["file"]): _report(h) for h in _read_jsonl(loans.parent / "hits.jsonl") if h.get("adsh") in adshs}
    extra = {}
    for a, b in _aligned(lines, report, {}):
        extra.setdefault(a, []).append((b[0], *_loan_key(b[0], b[2], b[:2])))
    merged = {}
    for r, loan in zip(lines, _one_loan([[(r["adsh"], *k) for k in _loan_keys(r["adsh"], r)] + extra.get((r["adsh"], r["file"], r["id"]), []) for r in lines])):
        m = merged.setdefault(loan, {"adsh": r["adsh"], "models": set(), "vs_value": False})
        m["models"].update(r.get("models") or [])
        m["vs_value"] = m["vs_value"] or bool(r.get("vs_value"))
    out = {}
    for m in merged.values():
        adsh = m["adsh"]
        fam, fams = loan_family(sorted(m["models"])), {model_family(v) for v in m["models"]}
        vs = fam.startswith("vs") or m["vs_value"]
        alone = vs and not fams & {"classic", "fico_new"}
        t = out.setdefault(adsh, dict.fromkeys(TAPE_FIELDS, 0))
        t["tape_n"] += 1
        t["tape_named"] += int(vs or fam not in ("unclear", "blank"))
        t["tape_vs"] += int(vs)
        t["tape_vs4"] += int(fam == "vs4")
        t["tape_vs_old"] += int(fam == "vs_old")
        t["tape_vs_alone"] += int(alone)
        t["tape_vs_classic"] += int(vs and "classic" in fams)
        t["tape_vs4_alone"] += int(alone and fam == "vs4")
        t["tape_old_alone"] += int(alone and fam == "vs_old")
    return out


def _watch_hit(h: dict) -> dict:
    s = h["_source"]
    adsh, name = h["_id"].split(":", 1)
    return {"adsh": adsh, "file": name, "cik": (s.get("ciks") or ["0"])[0], "date": s.get("file_date"), "form": s.get("form"), "type": s.get("file_type"),
            "desc": (s.get("file_description") or "")[:80], "filer": (s.get("display_names") or [""])[0].split("  (")[0].strip(), "sics": list(s.get("sics") or [])}


def discover_watch(client: Edgar, start: str, end: str) -> list[dict]:
    """Every file on WATCH_FORMS that EDGAR's search returns for VantageScore, month by month."""
    out = []
    for a, b in month_windows(start, end):
        frm = 0
        while True:
            res = client.search(WATCH_QUERY, a, b, frm, forms=",".join(WATCH_FORMS))
            if res is None:
                raise RuntimeError(f"EDGAR's search did not answer for {WATCH_QUERY} {a}..{b}")
            hits = res["hits"]["hits"]
            out.extend(_watch_hit(h) for h in hits)
            frm += len(hits)
            if not hits or frm >= res["hits"]["total"]["value"] or frm >= 9900:
                break
    return out


def watch_rows(home: Path | None = None) -> dict[tuple, dict]:
    """The watch's files, by filing and file: the last line for each."""
    return {(r["adsh"], r["file"]): r for r in _read_jsonl((home or paths.DATA / "edgar") / "watch.jsonl")}


def collect_watch(since: str | None = None, until: str | None = None, limit: int | None = None, log=print, client: Edgar | None = None, home: Path | None = None) -> dict:
    """Searches EDGAR for VantageScore on WATCH_FORMS, from WATCH_FROM on a first run and OVERLAP_DAYS before the last filing found on a later one, then notes each new
    file once. A file a mortgage company filed is opened: how often it names VantageScore and the first sentence that does. One on auto, card or consumer loans is noted
    and not opened. A deal report the deal search read keeps that reading, with its loan file's counts, unless only its text names VantageScore. A file that would not
    open is tried again next run. Safe to stop and run again: what is done is on disk, one line at a time."""
    home = home or paths.DATA / "edgar"
    home.mkdir(parents=True, exist_ok=True)
    known = watch_rows(home)
    until = until or date.today().isoformat()
    if since is None:
        last = max((r["date"] for r in known.values() if r.get("date")), default=None)
        since = (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)).isoformat() if last else WATCH_FROM
    since = max(since, WATCH_FROM)
    client = client or Edgar()
    log(f"watch: searching {since} to {until}")
    fresh = {}
    for h in discover_watch(client, since, until):
        fresh.setdefault((h["adsh"], h["file"]), h)
    todo = [h for k, h in fresh.items() if k not in known] + [r for r in known.values() if r.get("error")]
    if limit:
        todo = todo[:limit]
    read = {(e["adsh"], e["file"]): e for e in _read_jsonl(home / "exhibits.jsonl")}
    tapes = tape_counts({h["adsh"] for h in todo if h.get("form") in DEAL_FORMS and (h["adsh"], h["file"]) in read}, home / "loans.jsonl")
    log(f"watch: {len(fresh)} files found, {len(todo)} to note")
    opened = 0
    for h in todo:
        row = {k: h.get(k) for k in WATCH_KEYS}
        was, tape = read.get((row["adsh"], row["file"])) or {}, tapes.get(row["adsh"]) or {}
        if watch_class(row) not in ("mortgage", "unknown"):
            pass  # another kind of loan: noted, not opened
        elif row["form"] in DEAL_FORMS and was.get("vantage") is not None and (not was["vantage"] or tape.get("tape_vs")):
            row.update(count=was["vantage"], **tape)  # the deal search's reading: a column heading only, or loans naming it
        else:
            body = client.get(exhibit_url(row["cik"], row["adsh"], row["file"]))
            opened += 1
            if body is None:
                row["error"] = True
            else:
                row["count"], row["sentence"], row["near_mortgage"] = vantage_passage(body.decode("utf-8", errors="replace"))
                row.update(kb=len(body) // 1024, **tape)
        _append_jsonl(home / "watch.jsonl", [row])
    new = sum(1 for k in fresh if k not in known)
    _append_jsonl(home / "watch_runs.jsonl", [{"at": date.today().isoformat(), "since": since, "until": until, "found": len(fresh), "new": new, "opened": opened, "requests": client.requests}])
    return {"since": since, "until": until, "found": len(fresh), "new": new, "noted": len(todo), "opened": opened, "requests": client.requests}
