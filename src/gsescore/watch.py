"""The VantageScore watch, for the private-label view of the Rest of market tab: SEC filings that name VantageScore and matter for mortgages, from edgar.py's weekly search
(collect_watch), and what no SEC search finds, kept by hand in data/private/vs_watch.csv: rating-agency reports, lender and loan-buyer guides, trade press.

Private: on DASHBOARD_DATASETS only. The hand-kept file has one row per item: date (YYYY-MM-DD), who, kind (KINDS), what (a plain sentence, in our words), source (the
link's words), url and standing (STANDINGS), which says where the item stands on its date and so names the date's basis: filed, published, closed, in force since,
comments closed or replaced; and, if it has the column, covers (OPTIONAL): the SEC filings the row stands for, by accession number, as when its link is the press. A
row that fails a guard stays off the list with a warning. A row stands for the SEC filing its link is, and for those in its covers, which the searches then do not list
again.

From the search, a filing counts once, however many of its files name VantageScore. It is kept when the company matters for mortgages (FICO, the bureaus, Fannie, Freddie,
the mortgage insurers, lenders, private-label sponsors and servicers), by name or industry code, else by mortgage words around the mention (edgar.watch_class). Filings on
auto, card or consumer loans, or on other business, are counted and left out, and so is a deal report that names VantageScore only as a column heading. A company filing
shows its own sentence naming VantageScore, in quotes (edgar.vantage_passage), or for a slide's words run together, the clause holding its share (edgar.share_clause, at
each build, so a line noted before that rule shows it too); a sentence a company repeats word for word shows once, in the row of its newest filing, which names the
others (also). A deal report whose loan file names VantageScore shows, of its loans whose score model the report names, how many name VantageScore, whether a FICO model
is named beside it and, where some have one and some not, which are which, counted at each build from the loan file (edgar.tape_counts): a loan with VantageScore for one
bureau beside Classic FICO is never a loan scored on VantageScore alone. A deal report the deal search found writing just "Vantage" (edgar's mentions.jsonl), filed from
WATCH_FROM on, is listed with its words.

New: an item first listed in the NEW_DAYS days to the build's day. The day an item was first listed comes forward from the last build's file (site/data/vs_watch.json);
with no items there, as on a first build, it is the item's own date.

  vs_watch  view meta: as_of (the build's day), searched (the last filing day the SEC search covered), search_from, new_from (the first day that counts as new), items_n,
                       new_n, sec_n (filings from the searches, mention_n of them deal reports writing just "Vantage"), hand_n (rows kept by hand), covered_n (filings
                       either search found that a hand-kept row stands for), repeat_n (filings that repeat a sentence another row shows), left_n and its parts left_auto,
                       left_card, left_consumer, left_other and left_heading, hand_out_n (rows a guard left off).
            view item: key, date, standing, basis (the words before the date), kind, kind_label, who, what, quote (what is the filing's own words), also (where else
                       a company's sentence appears), source (the link's words), url, form, count (a filing's mentions of VantageScore), first_seen, new, order
                       (newest first).
            view sentence: key, text: lead and search, each under its guard. view warning: text, for the weekly report.
"""
import csv
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import paths
from .edgar import DEAL_FORMS, TAPE_FIELDS, WATCH_FROM, _read_jsonl, deal_label, exhibit_url, share_clause, tape_counts, watch_class, watch_rows
from .hmda import short_name

INPUTS = paths.PRIVATE / "vs_watch.csv"
COLUMNS = ("date", "who", "kind", "what", "source", "url", "standing")
OPTIONAL = ("covers",)  # read where the file has them: the SEC filings a row stands for, beside the one its link may be
_ADSH = re.compile(r"\d{10}-?\d{2}-?\d{6}")  # an SEC accession number, as 0001214659-26-012431
KINDS = {"filing": "SEC filing", "deal": "Deal", "rating agency": "Rating agency", "lender guide": "Lender guide", "trade press": "Trade press"}
STANDINGS = {"filed": "Filed", "published": "Published", "closed": "Closed", "in force": "In force since", "comments closed": "Comments closed", "replaced": "Replaced"}
NEW_DAYS = 7  # an item is new for a week from the day a build first lists it
STALE_DAYS = 8  # past this, the weekly report says the SEC search is behind
WHAT_MAX = 600  # past this, a hand-kept sentence is a paragraph
FORM_WORDS = "10-K, 10-Q and 8-K reports, deal reports (ABS-15G) and free-writing prospectuses"
LEFT = ("auto", "card", "consumer", "other", "heading")
MENTION_BEFORE = 12  # the most words a deal report's mention of Vantage shows before it
# Names as the list prints them, by the number EDGAR files a company under; any other filer goes through short_name.
WHO = {"310522": "Fannie Mae", "1026214": "Freddie Mac", "814547": "FICO", "1552033": "TransUnion", "876437": "MGIC", "890926": "Radian", "1448893": "Essent", "1547903": "NMI Holdings",
       "1823529": "Enact", "1276520": "Genworth", "1805284": "Rocket", "1783398": "UWM", "1831631": "loanDepot", "1462418": "Altisource", "1599342": "PennyMac", "1176320": "Redwood Trust"}
_SEC_URL = re.compile(r"sec\.gov/Archives/edgar/data/\d+/(\d{18})/", re.I)


def _day(s) -> str:
    d = date.fromisoformat(str(s)[:10])
    return f"{d:%B} {d.day}, {d.year}"


def _short_day(s) -> str:
    d = date.fromisoformat(str(s)[:10])
    return f"{d:%b} {d.day}, {d.year}"


def _n(k: int, one: str, many: str) -> str:
    return f"{k:,} {one if k == 1 else many}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def _file_rows(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text())["rows"]
    except FileNotFoundError:
        return []


def _seen_before(out_dir: Path) -> dict | None:
    """Each item the last build's file lists, by key: its first day on the list, who and kind; None when it lists no items, as before a first build or after one that
    stopped."""
    try:
        rows = _file_rows(out_dir / "vs_watch.json")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    seen = {r["key"]: {"first_seen": r["first_seen"], "who": r.get("who"), "kind": r.get("kind"), "hand": not r.get("form")}
            for r in rows if isinstance(r, dict) and r.get("view") == "item" and r.get("key") and r.get("first_seen")}
    return seen or None


def _first_days(items: list[dict], seen: dict | None, as_of: date) -> dict:
    """Each item's first day on the list: from the last build's file by its key; a hand-kept row whose date or link was corrected, so its key changed, keeps the
    day of the one row it replaces, when it is the only row of its who and kind that the file lacks and the file's row of that who and kind is the only one gone.
    With no file, as on a first build, an item's own date; else the build's day."""
    if not seen:
        return {r["key"]: r["date"] for r in items}
    out = {r["key"]: seen[r["key"]]["first_seen"] for r in items if r["key"] in seen}
    keys = {r["key"] for r in items}
    gone = [k for k, v in seen.items() if k not in keys and v["hand"]]
    for r in items:
        if r["key"] in out or r.get("form"):
            continue
        pair = lambda w, k: w == r["who"] and k == r["kind"]  # noqa: E731
        was = [k for k in gone if pair(seen[k]["who"], seen[k]["kind"])]
        twins = [x for x in items if x["key"] not in out and not x.get("form") and pair(x["who"], x["kind"])]
        if len(was) == 1 and len(twins) == 1:
            out[r["key"]] = seen[was[0]]["first_seen"]
    return {r["key"]: out.get(r["key"], as_of.isoformat()) for r in items}


def _exhibit_order(typ) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(typ or ""))) or (0,)


def _form_words(form: str, typ) -> str:
    ex = re.fullmatch(r"EX-(\d+(?:\.\d+)*)\w*", str(typ or ""))
    return f"{form}, exhibit {ex.group(1)}" if ex else form


def _who(row: dict, deals: dict) -> str:
    if row.get("form") in DEAL_FORMS and deals.get(row["adsh"]):
        return deal_label(deals[row["adsh"]])
    cik = str(int(row.get("cik") or 0))
    return WHO.get(cik) or short_name(row.get("filer") or "") or "Filer"


def _which(vs: int, vs4: int, old: int) -> str:
    """Which VantageScore some loans name: VS4, one older than VS4, or a mix, with how many name VS4."""
    return "VS4" if vs4 == vs else "a VantageScore other than VS4" if old == vs else f"VantageScore ({vs4:,} VS4)" if vs4 else "VantageScore"


def _tape_words(t: dict) -> str:
    """A deal report's loans naming VantageScore, in words: of the loans whose score model its report names (a line noted before that count: of all its loans),
    how many name VantageScore, which one, and whether a FICO model is named beside it; where some have a FICO model named and some not, which are which. Only a
    loan naming VantageScore and no FICO model is said to have it as the only score model."""
    get = lambda k: t.get(k) or 0  # noqa: E731
    n, named, vs, vs4, old, alone, classic = (get(k) for k in ("tape_n", "tape_named", "tape_vs", "tape_vs4", "tape_vs_old", "tape_vs_alone", "tape_vs_classic"))
    which, one = _which(vs, vs4, old), vs == 1
    base = (f"Of the {_n(n, 'loan', 'loans')} in its report, {vs:,}" if t.get("tape_named") is None
            else f"Of the {_n(named, 'loan', 'loans')} whose score model its report names, {vs:,}")
    if t.get("tape_vs_alone") is None:  # noted before the loan file said whether FICO is named beside it
        return f"{base} {'names' if one else 'name'} {which}."
    if alone == vs:
        return f"{base} {'names' if one else 'name'} {which} as the only score model."
    if not alone:
        fico = "Classic FICO" if classic == vs else "a FICO model"
        return f"{base} {'lists' if one else 'list'} {which} beside {fico}" + ("." if one else "; none names VantageScore alone.")
    if t.get("tape_vs4_alone") is None:  # noted before the loan file said which of them have no FICO named
        return f"{base} name {which}, {alone:,} of them with no FICO named."
    rest = vs - alone
    lone, beside = _which(alone, get("tape_vs4_alone"), get("tape_old_alone")), _which(rest, vs4 - get("tape_vs4_alone"), old - get("tape_old_alone"))
    fico = "Classic FICO" if classic == rest else "a FICO model"
    if lone == beside == which:
        return f"{base} name {which}: {alone:,} with no FICO named and {rest:,} beside {fico}."
    return f"{base} name {which}: {alone:,} {'names' if alone == 1 else 'name'} {lone} with no FICO named, and {rest:,} {'lists' if rest == 1 else 'list'} {beside} beside {fico}."


def sec_items(rows: dict, deals: dict, covered: set, tapes: dict | None = None) -> tuple[list[dict], dict, set]:
    """The search's filings as items, one per filing, with what was left out by class and the filings a hand-kept row stands for. tapes, when given, holds each
    deal report's loan counts as the loan file has them now (edgar.tape_counts), in place of those noted when the search found it."""
    by_filing = {}
    for r in rows.values():
        if tapes is not None and r.get("form") in DEAL_FORMS:
            r = {**r, **(tapes.get(r["adsh"]) or dict.fromkeys(TAPE_FIELDS))}
        by_filing.setdefault(r["adsh"], []).append(r)
    items, left, stood = [], dict.fromkeys(LEFT, 0), set()
    for adsh, files in sorted(by_filing.items()):
        files.sort(key=lambda r: (r.get("type") != r.get("form"), _exhibit_order(r.get("type")), r["file"]))
        opened = [f.get("near_mortgage") for f in files if f.get("near_mortgage") is not None]
        cls = watch_class(files[0], any(opened) if opened else None)
        if cls != "mortgage":
            left["other" if cls == "unknown" else cls] += 1  # unknown: a file that never opened, from a filer no name or code places
            continue
        named, failed = [f for f in files if f.get("count")], [f for f in files if f.get("error")]
        if not named and not failed:
            left["heading"] += 1
            continue
        if adsh.replace("-", "") in covered:
            stood.add(adsh)
            continue
        tape = max(files, key=lambda f: f.get("tape_vs") or 0)
        said = next((f for f in named if f.get("sentence")), None)
        show = tape if tape.get("tape_vs") else said or (named or failed)[0]
        count = sum(f.get("count") or 0 for f in files)
        if tape.get("tape_vs"):
            what, quote = _tape_words(tape), False
        elif said:
            what, quote = share_clause(said["sentence"]), True  # a slide's words noted before that rule show its clause too
        elif named:
            what, quote = f"Names VantageScore {_n(count, 'time', 'times')}, in tables or headings rather than a sentence.", False
        else:
            what, quote = "EDGAR's search finds VantageScore in this filing, but the document did not open, so its words are not shown yet.", False
        items.append({"key": adsh, "date": min(f["date"] for f in files), "standing": "filed", "kind": "deal" if files[0]["form"] in DEAL_FORMS else "filing", "who": _who(files[0], deals),
                      "what": what, "quote": quote, "source": _form_words(show["form"], show.get("type")), "url": exhibit_url(show["cik"], adsh, show["file"]), "form": files[0]["form"],
                      "count": count})
    return items, left, stood


def fold_repeats(items: list[dict]) -> tuple[list[dict], int]:
    """A sentence a company repeats word for word, as a 10-Q does each quarter, shows once: in the row of its newest filing, which names the others (also). Returns
    the items left and how many filings were folded into another's row."""
    groups = {}
    for r in items:
        groups.setdefault((r["who"], re.sub(r"\s+", " ", r["what"]).strip()) if r["quote"] else (r["key"],), []).append(r)
    out, folded = [], 0
    for rows in groups.values():
        rows.sort(key=lambda r: (r["date"], r["key"]), reverse=True)
        top, rest = rows[0], rows[1:]
        if rest:
            folded += len(rest)
            top = {**top, "also": "Also in its " + _join([f"{r['form']} of {_short_day(r['date'])}" for r in rest]) + "."}
        out.append(top)
    return out, folded


def _mention_words(snippet: str) -> str | None:
    """The words the deal search saved around a report's mention of Vantage: the sentence holding it, without a numbered heading run into it (as "3.7 Credit
    History"), from at most MENTION_BEFORE words before the mention, with … where the saved words or this cut leave it."""
    s = re.sub(r"\s+", " ", snippet or "").strip()
    m = re.search(r"vantage", s, re.I)
    if not m:
        return None
    stops = [x.end() for x in re.finditer(r"[.?!](?=\s|$)", s[:m.start()])]
    after = re.search(r"[.?!](?=\s|$)", s[m.end():])
    lead = s[stops[-1] if stops else 0:m.start()]
    if stops:
        lead = re.sub(r"^\s*\d+(?:\.\d+)+\s+(?:[A-Z][a-z]+\s+){1,3}(?=[A-Z])", "", lead)
    before = lead.split()[0 if stops else 1:]  # with no stop before it, the saved words start part way through a word
    rest = s[m.start():m.end() + after.end() if after else len(s)].split()
    if not after and len(rest) > 1:
        rest = rest[:-1]  # and with none after it, they end part way through one
    whole = bool(stops) and len(before) <= MENTION_BEFORE
    return ("" if whole else "… ") + " ".join(before[-MENTION_BEFORE:] + rest) + ("" if after else " …")


def mention_items(edgar_home: Path, deals: dict, listed: set, covered: set) -> tuple[list[dict], set]:
    """Deal reports the deal search found naming Vantage outside a loan file, as "Vantage" alone, filed from WATCH_FROM on: one item per filing that is not listed
    already and that no hand-kept row stands for, with the words around its first mention; and the filings a hand-kept row stands for."""
    hits = {(h["adsh"], h["file"]): h for h in _read_jsonl(edgar_home / "hits.jsonl") if h.get("kind") == "mention"}
    found, stood = {}, set()
    for x in _read_jsonl(edgar_home / "mentions.jsonl"):
        h = hits.get((x.get("adsh"), x.get("file")))
        if not (h and x.get("count") and str(x.get("date") or "") >= WATCH_FROM and x["adsh"] not in listed):
            continue
        if x["adsh"].replace("-", "") in covered:
            stood.add(x["adsh"])
        else:
            found.setdefault(x["adsh"], []).append((x, h))
    items = []
    for adsh, pairs in sorted(found.items()):
        pairs.sort(key=lambda p: (_exhibit_order(p[1].get("type")), p[1]["file"]))
        x, h = pairs[0]
        words = _mention_words(x.get("snippet"))
        items.append({"key": adsh, "date": min(p[0]["date"] for p in pairs), "standing": "filed", "kind": "deal",
                      "who": deal_label(deals[adsh]) if deals.get(adsh) else short_name(h.get("filer") or "") or "Filer",
                      "what": f"Its report mentions Vantage: “{words}”" if words else "Its report mentions Vantage.", "quote": False, "source": _form_words(h.get("form") or "ABS-15G", h.get("type")),
                      "url": exhibit_url(h["cik"], adsh, h["file"]), "form": h.get("form") or "ABS-15G", "count": sum(p[0]["count"] for p in pairs)})
    return items, stood


def _fault(v: dict, as_of: date) -> str | None:
    """Why a hand-kept row cannot be listed, or None."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v["date"]):
        return f"its date {v['date']!r} is not YYYY-MM-DD"
    try:
        if date.fromisoformat(v["date"]) > as_of:
            return f"its date {v['date']} comes after the build's day, {as_of.isoformat()}"
    except ValueError:
        return f"its date {v['date']!r} is not a day"
    if not v["who"]:
        return "it names no one"
    if v["kind"] not in KINDS:
        return f"its kind {v['kind']!r} is not one of {', '.join(KINDS)}"
    if not v["what"]:
        return "it says nothing"
    if len(v["what"]) > WHAT_MAX:
        return f"its sentence runs past {WHAT_MAX} characters"
    if "{" in v["what"] or "}" in v["what"]:
        return "its sentence holds a placeholder"
    if not v["source"]:
        return "its link has no words"
    if not re.fullmatch(r"https://[^\s]+\.[^\s]+", v["url"]):
        return "its link is not a web address starting https://"
    if v["standing"] not in STANDINGS:
        return f"its standing {v['standing']!r} is not one of {', '.join(STANDINGS)}"
    bad = [a for a in _covers(v.get("covers") or "") if not _ADSH.fullmatch(a)]
    if bad:
        return f"its covers {bad[0]!r} is not an SEC accession number, as 0001234567-26-012345"
    return None


def _covers(value: str) -> list[str]:
    return [a for a in re.split(r"[\s;,]+", value) if a]


def hand_items(path: Path, as_of: date) -> tuple[list[dict], list[str], int]:
    """The hand-kept rows that pass their guards, a warning for each that does not, and how many did not. A missing or unreadable file is a warning too."""
    if not path.exists():
        return [], [f"VantageScore watch: {path.name} is missing, so only SEC filings show."], 0
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                return [], [f"VantageScore watch: {path.name} lacks the column{'s' if len(missing) > 1 else ''} {', '.join(missing)}, so only SEC filings show."], 0
            raw = [(reader.line_num, r) for r in reader]  # the file's own line, past blank lines and sentences that run over two
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        return [], [f"VantageScore watch: could not read {path.name}, so only SEC filings show: {e!r}"], 0
    items, warnings, keys = [], [], set()
    for line, r in raw:
        v = {c: (r.get(c) or "").strip() for c in COLUMNS + OPTIONAL}
        if not any(v.values()):
            continue
        key = f"{v['date']} {v['who']} {hashlib.sha1('|'.join((v['date'], v['who'], v['url'])).encode()).hexdigest()[:6]}"
        why = _fault(v, as_of) or ("it repeats the date, who and link of an earlier row" if key in keys else None)
        if why:
            warnings.append(f"VantageScore watch: line {line} of {path.name} is left off the list: {why}.")
            continue
        keys.add(key)
        sec = _SEC_URL.search(v["url"])
        covers = {a.replace("-", "") for a in _covers(v["covers"])} | ({sec.group(1)} if sec else set())
        items.append({"key": key, "date": v["date"], "standing": v["standing"], "kind": v["kind"], "who": v["who"], "what": v["what"], "quote": False, "source": v["source"],
                      "url": v["url"], "form": None, "count": None, "covers": sorted(covers)})
    return items, warnings, len(warnings)


def build_rows(edgar_home: Path, inputs: Path, as_of: date, seen: dict | None) -> list[dict]:
    hand, warnings, hand_out = hand_items(inputs, as_of)
    covered = {a for r in hand for a in r["covers"]}
    deals = {f["adsh"]: f.get("deal") for f in _read_jsonl(edgar_home / "filings.jsonl") if f.get("deal")}
    noted = watch_rows(edgar_home)
    tapes = tape_counts({r["adsh"] for r in noted.values() if r.get("form") in DEAL_FORMS}, edgar_home / "loans.jsonl")
    sec, left, stood = sec_items(noted, deals, covered, tapes)
    sec, repeat_n = fold_repeats(sec)
    mentions, mentions_stood = mention_items(edgar_home, deals, {r["key"] for r in sec}, covered)
    sec += mentions
    stood |= mentions_stood
    runs = _read_jsonl(edgar_home / "watch_runs.jsonl")
    searched = max((r["until"] for r in runs if r.get("until")), default=None)
    if searched is None:
        warnings.append("VantageScore watch: the SEC search has not run yet; `edgar` runs it.")
    elif (as_of - date.fromisoformat(searched)).days > STALE_DAYS:
        warnings.append(f"VantageScore watch: the SEC search last covered filings to {searched}, {(as_of - date.fromisoformat(searched)).days} days before {as_of.isoformat()}.")

    # ---- Each item's first day on the list, and the mark on what is new ----
    items = sorted(sec + hand, key=lambda r: (-date.fromisoformat(r["date"]).toordinal(), list(KINDS).index(r["kind"]), r["who"].lower(), r["key"]))
    new_from = as_of - timedelta(days=NEW_DAYS - 1)
    firsts = _first_days(items, seen, as_of)
    for order, r in enumerate(items):
        r.pop("covers", None)
        r.setdefault("also", None)
        r.update(view="item", order=order, kind_label=KINDS[r["kind"]], basis=STANDINGS[r["standing"]], first_seen=firsts[r["key"]], new=firsts[r["key"]] >= new_from.isoformat())
    new_n, sec_n, hand_n, mention_n = sum(r["new"] for r in items), len(sec), len(hand), len(mentions)

    # ---- The sentences, each under its guard ----
    said = {}
    if items:
        every = "" if len(items) == 1 else "all "
        whose = (f": {_n(sec_n, 'SEC filing', 'SEC filings')} from the weekly search and {hand_n:,} kept by hand" if sec_n and hand_n
                 else f", {every}SEC {'filing' if sec_n == 1 else 'filings'} from the weekly search" if sec_n else f", {every}kept by hand")
        said["lead"] = (f"{_n(len(items), 'item', 'items')}{whose}. "
                        + (f"{new_n:,} {'is' if new_n == 1 else 'are'} new, first listed in the week to {_day(as_of)}." if new_n else f"None was first listed in the week to {_day(as_of)}."))
    if searched:
        gone = [f"{_n(left['auto'] + left['card'] + left['consumer'], 'filing', 'filings')} on auto, card or consumer loans"] if left["auto"] + left["card"] + left["consumer"] else []
        gone += [f"{_n(left['heading'], 'deal report', 'deal reports')} naming VantageScore only as a column heading"] if left["heading"] else []
        gone += [f"{_n(left['other'], 'filing', 'filings')} on other business"] if left["other"] else []
        late = (as_of - date.fromisoformat(searched)).days
        said["search"] = (f"The SEC search covers {FORM_WORDS} filed from {_day(WATCH_FROM)} to {_day(searched)}." + (f" That is {late} days before this list was built." if late > STALE_DAYS else "")
                          + (f" It left out {_join(gone)}." if gone else "")
                          + (f" It also lists {_n(mention_n, 'deal report', 'deal reports')} that {'writes' if mention_n == 1 else 'write'} just “Vantage”, from the weekly search of deal reports."
                             if mention_n else "")
                          + (f" {_n(repeat_n, 'filing', 'filings')} that {'repeats' if repeat_n == 1 else 'repeat'} a company's sentence word for word {'is' if repeat_n == 1 else 'are'} named"
                             " in the row of its newest filing." if repeat_n else ""))
    meta = {"view": "meta", "as_of": as_of.isoformat(), "searched": searched, "search_from": WATCH_FROM, "new_from": new_from.isoformat(), "items_n": len(items), "new_n": new_n, "sec_n": sec_n,
            "mention_n": mention_n, "hand_n": hand_n, "covered_n": len(stood), "repeat_n": repeat_n, "left_n": sum(left.values()), **{f"left_{k}": v for k, v in left.items()}, "hand_out_n": hand_out}
    rows = [meta, *items, *({"view": "sentence", "key": k, "text": v} for k, v in said.items()), *({"view": "warning", "text": w} for w in warnings)]
    keys = sorted({k for r in rows for k in r})
    return [{k: r.get(k) for k in keys} for r in rows]


def build_datasets(out_dir: Path = paths.SITE_DATA, edgar_home: Path | None = None, inputs: Path | None = None, today: date | None = None) -> dict[str, list[dict]]:
    """From the watch's files under data/edgar, the hand-kept file and the last build's file in out_dir. A shape this builder did not foresee stops nothing: the card stays
    off and the weekly report says why."""
    try:
        return {"vs_watch": build_rows(edgar_home or paths.DATA / "edgar", inputs or INPUTS, today or date.today(), _seen_before(out_dir))}
    except Exception as e:
        return {"vs_watch": [{"view": "meta", "items_n": None, "text": None}, {"view": "warning", "items_n": None, "text": f"VantageScore watch: could not build the dataset: {e!r}"}]}


def watch_warnings(out_dir: Path = paths.SITE_DATA) -> list[str]:
    """What the weekly report prints from the dataset. Never raises."""
    try:
        return [r["text"] for r in _file_rows(out_dir / "vs_watch.json") if r.get("view") == "warning"]
    except Exception as e:
        return [f"VantageScore watch: could not read vs_watch.json: {e!r}"]
