"""Private-label mortgage deals as they file, from SEC Form ABS-15G.

No residential deal files the SEC's asset-level form (ABS-EE), but any deal to be rated, registered or not, must furnish its third-party due diligence findings on Form ABS-15G at
least five business days before first sale. Many of those reports list each reviewed loan, and some name the score model per borrower and bureau (`Borrower Experian FICO Model Used`).

As elsewhere, a named model is a fact. A blank is unknown, and so is a score column with no model: a column called FICO can hold a VantageScore, so only a named model counts.

Requests carry a contact in the User-Agent, as the SEC's fair-access rules ask, at a few a second. The contact is read from the EDGAR_CONTACT setting or data/edgar/contact.txt and stays out of
the repo. What is kept, under data/edgar/ (git-ignored):
  hits.jsonl      every exhibit EDGAR's search returned for the phrases below
  exhibits.jsonl  each exhibit read: how many tables and rows, which columns, any value not recognized
  loans.jsonl     one line per loan row with a model column: filing, exhibit, loan id, the models named, the credit report month, the qualifying score
  mentions.jsonl  exhibits that mention VantageScore other than as a template's column heading
  filings.jsonl   each filing read for its deal name
The reports themselves are not kept.

  private_label  view meta: how far the search reached, filings, loans and how many name a model.
                 view period, basis filed: by quarter a deal first filed; basis pulled: by month of the loan's credit report (the one date these reports show, on some loans; application, lock and note dates are masked).
                 view kind: by kind of deal, going by its name. view filer: by depositor, with how many of its filings have a per-loan score column and a model column.
                 meta's recent_ fields cover loans with a credit report from AGENCY_OPEN on, lag_months is the median from credit report to filing, and vs_no_fico_n counts loans naming VantageScore and no FICO model. Each has n (loan rows), named (with a model the report names), classic, fico_new, vs4, vs_old and unclear (a code or a word this cannot read) and blank (none named), as counts (_n) and shares of n.
                 view deal: each deal with a loan naming VantageScore. view mention: each deal whose report names VantageScore outside a model column, as in a narrative or a comment.
                 A loan in two reports, an amended filing or a later deal counts once, under the deal that first filed it. A numeric code in a model column counts as unclear: one report has VS4 loans coded the same as Classic FICO ones.
"""
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
_ID_COL = re.compile(r"loan\s*(id|number|#|no\b)|deal\s*(id|number)|edgar id", re.I)
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

    def search(self, q: str, start: str, end: str, frm: int = 0) -> dict | None:
        args = {"q": q, "forms": "ABS-15G", "dateRange": "custom", "startdt": start, "enddt": end}
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
                self.row = []
            elif tag in ("td", "th"):
                self._close_cell()
                self.cell = []
                try:
                    self.span = max(1, int(dict(attrs).get("colspan") or 1))
                except ValueError:
                    self.span = 1

    def _close_cell(self):
        if self.cell is not None and self.row is not None:
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
    """What one cell says: vs4, vs_old, vs_other, fico_new, classic, a code, the word other, or junk, which is what a report with its columns out of line puts here (C3, 75.000%)."""
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


def _loan_id(header: list[str], row: list[str], ids: list[int], fallback: str) -> str:
    for i in ids:
        v = row[i] if i < len(row) else ""
        if len(re.sub(r"\D", "", v)) >= 3 and not _MASKED.search(v):
            return v
    return fallback


def parse_exhibit(text: str) -> tuple[list[dict], dict]:
    """The loan rows of every table with a model column, and a note of what was read. A table with no heading row but the width of the last one continues it."""
    rows, note = [], {"tables": 0, "model_tables": 0, "rows": 0, "columns": [], "odd": {}}
    header = None
    tables = read_tables(text)
    note["tables"] = len(tables)
    for t_no, table in enumerate(tables):
        start = None
        for i, row in enumerate(table[:5]):
            if len(row) >= 3 and any(_ID_COL.search(c) or _MODEL_COL.search(c) for c in row):
                start = i
                break
        if start is not None:
            header = table[start]
            body = table[start + 1:]
        elif header is not None and table and len(table[0]) == len(header):
            body = table
        else:
            continue
        models = [i for i, h in enumerate(header) if _MODEL_COL.search(h) and "date" not in h.lower()]
        vs_scores = [i for i, h in enumerate(header) if _VS_SCORE_COL.search(h)]
        if not models and not vs_scores:
            continue
        note["model_tables"] += 1
        for i in models:
            if header[i] not in note["columns"] and len(note["columns"]) < 40:
                note["columns"].append(header[i])
        ids = sorted((i for i, h in enumerate(header) if _ID_COL.search(h)), key=lambda i: (0 if re.search(r"customer", header[i], re.I) else 1, i))
        pull = next((i for i, h in enumerate(header) if re.fullmatch(r"original credit report date", h, re.I)), None)
        score = next((i for i, h in enumerate(header) if re.fullmatch(r"qualifying (credit score|fico)", h, re.I)), None)
        for r_no, row in enumerate(body):
            if sum(1 for c in row if c) < 3:
                continue
            named = sorted({row[i] for i in models if i < len(row) and not _BLANK.match(row[i])})
            for v in named:
                if model_family(v) == "junk" and len(note["odd"]) < 25:
                    note["odd"][v[:40]] = note["odd"].get(v[:40], 0) + 1
            vs_value = any(i < len(row) and re.fullmatch(r"[3-8]\d\d", row[i] or "") for i in vs_scores)
            cell = lambda i: row[i] if i is not None and i < len(row) else ""  # noqa: E731
            digits = re.sub(r"\D", "", cell(score))
            rows.append({"id": _loan_id(header, row, ids, f"row{t_no}-{r_no}"), "models": named, "vs_value": vs_value, "pull": report_month(cell(pull)), "score": int(digits) if len(digits) == 3 else None})
            note["rows"] += 1
    return _parse_pre(text) if not note["model_tables"] else (rows, note)


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


def collect(since: str | None = None, until: str | None = None, limit: int | None = None, log=print) -> dict:
    """Searches, then reads each exhibit and filing not read yet. Safe to stop and run again: what is done is on disk, one line at a time."""
    home = paths.DATA / "edgar"
    home.mkdir(parents=True, exist_ok=True)
    hits_path, exhibits_path, loans_path, mentions_path, filings_path = (home / f"{n}.jsonl" for n in ("hits", "exhibits", "loans", "mentions", "filings"))
    known = {(h["adsh"], h["file"], h["kind"]): h for h in _read_jsonl(hits_path)}
    until = until or date.today().isoformat()
    if since is None:
        last = max((h["date"] for h in known.values() if h.get("date")), default=None)
        since = (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)).isoformat() if last else BACKFILL_FROM
    client = Edgar()
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
    done = {(e["adsh"], e["file"]) for e in _read_jsonl(exhibits_path)}
    queue = sorted({(h["date"], h["adsh"], h["file"], h["cik"]) for h in hits if h["kind"] == "model" and is_mortgage(h) and (h["adsh"], h["file"]) not in done}, reverse=True)
    if limit:
        queue = queue[:limit]
    log(f"{len(queue)} exhibits to read")
    loans_added = 0
    for n, (day, adsh, name, cik) in enumerate(queue, 1):
        body = client.get(exhibit_url(cik, adsh, name))
        if body is None:
            _append_jsonl(exhibits_path, [{"adsh": adsh, "file": name, "date": day, "error": True}])
            continue
        text = body.decode("utf-8", errors="replace")
        rows, note = parse_exhibit(text)
        _append_jsonl(loans_path, [{"adsh": adsh, "file": name, **r} for r in rows])
        _append_jsonl(exhibits_path, [{"adsh": adsh, "file": name, "date": day, "kb": len(body) // 1024, "vantage": mentions_vantage(text), **note}])
        loans_added += len(rows)
        if n % 25 == 0:
            log(f"  {n}/{len(queue)} exhibits, {loans_added:,} loan rows, {client.requests} requests")
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


def _loan_key(deal: str, loan_id: str) -> tuple:
    """A long loan number is the same loan wherever it appears, as when a loan moves to a later deal; a short one is only sure within its deal."""
    return (None, loan_id) if len(re.sub(r"\D", "", loan_id)) >= 7 else (deal, loan_id)


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
    merged = {}
    with_model = set()
    for r in _read_jsonl(home / "loans.jsonl"):
        h = info.get(r["adsh"])
        if not h:
            continue
        if r.get("vs_value") or any(model_family(v) != "junk" for v in r["models"]):
            with_model.add(r["adsh"])
        deal = deals.get(r["adsh"]) or r["adsh"]
        m = merged.setdefault(_loan_key(deal, r["id"]), {"deal": deal, "adsh": r["adsh"], "date": h["date"], "filer": h["filer"], "models": set(), "vs_value": False, "pull": None})
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
    loans = list(merged.values())
    filings_any = {h["adsh"] for h in mortgage if h["kind"] in ("model", "score")}
    lags = sorted((int(m["date"][:4]) - int(m["pull"][:4])) * 12 + int(m["date"][5:7]) - int(m["pull"][5:7]) for m in loans if m["pull"])
    recent = [m for m in loans if m["pull"] and m["pull"] >= AGENCY_OPEN]
    out = [{"view": "meta", "from": BACKFILL_FROM, "through": max(h["date"] for h in hits), "filings": len(filings_any | with_model), "with_model": len(with_model), "exhibits": len(_read_jsonl(home / "exhibits.jsonl")), "deals": len({m["deal"] for m in loans}),
            "dated": round(sum(1 for m in loans if m["pull"]) / len(loans), 6) if loans else None, "recent_from": AGENCY_OPEN, "recent_n": len(recent), "recent_vs_n": sum(1 for m in recent if m["family"] in ("vs4", "vs_old")),
            "recent_vs": round(sum(1 for m in recent if m["family"] in ("vs4", "vs_old")) / len(recent), 6) if recent else None, "lag_months": lags[len(lags) // 2] if lags else None,
            "vs_no_fico_n": sum(1 for m in loans if m["family"] in ("vs4", "vs_old") and not any(model_family(v) in ("classic", "fico_new") for v in m["models"])), **_tally(loans)}]
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
                        "url": f"{ARCHIVES}/{int(h['cik'])}/{rows[0]['adsh'].replace('-', '')}/{rows[0]['adsh']}-index.html", **t})
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
