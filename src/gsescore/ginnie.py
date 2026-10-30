"""Which lenders' VA loans show scores Classic FICO almost never reaches, from Ginnie Mae's monthly loan files.

Ginnie Mae's files carry one score on each FHA and VA loan and do not name its model. A model can still leave a mark. On loans showing both scores at Fannie and Freddie, a middle-of-three
Classic FICO almost never reaches TOP while VS4 often does, so VA loans at TOP or above mark a move off Classic FICO. FHA loans are the check: they cannot take VS4 until case numbers assigned
from Jan 1, 2027. This is inference. Another model reaching 850 could look the same, and a VS4 score sent to Ginnie Mae does not mean no FICO was bought.

Only high-scoring borrowers can show the mark. "Full signal" is how many of a group's loans would reach TOP if every loan showed VS4, from the odds of VS4 at TOP or above at each Classic score
on Fannie loans showing both (Fannie because a second score at Freddie often does not show). The test cannot tell VS4 on every loan from VS4 only when it is GAP or more above Classic: nearly
every loan at TOP is that far above. So the share of loans on VS4 is a range: high, the share of the signal showing; low, that share scaled to how few loans are GAP or more above.

Downloads need a Ginnie Mae sign-in. `ingest` reads the files wherever they are, keeps only counts (issuer, loan type, kind of loan, channel, closing month, score in 5-point steps)
in data/ginnie/{issue month}.parquet, and never deletes a file. A new file for an issue month replaces the old one, so a daily file gives way to that month's final file.

  ginnie_va  view meta: the files read, the months covered, the month the leading lender starts (since) and the checks from loans showing both scores.
             view month: for each closing month with at least MONTH_MIN VA loans, by series: lead_retail (the leading lender's retail purchases), lead_own (its retail and broker loans),
             second (the next lender, all its loans), others (every other lender), fha (all FHA loans). n, k (at TOP or above), share and signal (k over the full signal).
             view lender: since the start month, the LENDER_TOP biggest VA lenders and every other lender with at least 2 loans at TOP. n, k, k_high (at HIGH or above), full, signal, upper (a 95% upper limit on signal when k is small).
             view range: the last two months, the share of loans on VS4 from low to high, by series, plus all (every VA loan).
             view channel: since the start month, the two leading lenders' signal by kind of loan, channel and closing month.
"""
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

from . import paths
from .hmda import short_name

TOP = 830
HIGH = 845
GAP = 20
LAG_MAX = 4       # months from closing to the pool's issue month; older loans are re-pooled, not new
MONTH_MIN = 1000  # VA loans a closing month needs to be shown
START_MIN = 10    # loans at TOP in a month that mark the leading lender's start
LENDER_TOP = 25
SMALL_FULL = 20   # below this full signal a lender's share can't be read
UPPER = {0: 3.00, 1: 4.74, 2: 6.30, 3: 7.75, 4: 9.15, 5: 10.51, 6: 11.84, 7: 13.15, 8: 14.43, 9: 15.71, 10: 16.96}  # 95% upper limits on a count
CHANNELS = {"1": "broker", "2": "correspondent", "3": "retail"}
KINDS = {"1": "purchase", "2": "refinance"}
FULL_REFI = {"1", "2"}  # no cash-out and cash-out; streamlines need no new credit check
COLUMNS = ["issuer", "agency", "kind", "channel", "month", "score5", "n"]


def _records(lines):
    """(issuer, agency, purpose, refinance type, score, channel, closing date) per loan: the pipe layout from August 2026 (item LL-n is field n-1), the fixed layout before it."""
    for ln in lines:
        if ln.startswith("LL|"):
            p = ln.split("|")
            yield p[7], p[8], p[9], p[10], p[26], p[36], p[40]
        elif ln.startswith("L") and len(ln) >= 150:
            yield ln[17:21], ln[21], ln[22], ln[23], ln[108:111].strip(), ln[133], ln[142:150]


def _issue_month(path: Path, first_line: str) -> str:
    m = re.search(r"_(\d{4})(\d{2})\.zip$", path.name) or re.match(r"HH\|(\d{4})(\d{2})\|", first_line) or re.search(r"_(\d{4})(\d{2})\d{3}[A-Z]", first_line)
    if not m:
        raise ValueError(f"no issue month in {path.name}")
    return f"{m[1]}-{m[2]}"


def _lag(issue: str, month: str) -> int:
    return (int(issue[:4]) - int(month[:4])) * 12 + int(issue[5:]) - int(month[5:])


def read_loans(path: Path) -> tuple[str, pd.DataFrame]:
    """A monthly or daily new-issue zip -> its issue month and counts of FHA and VA purchases and full refinances, closed within LAG_MAX months of issue."""
    with zipfile.ZipFile(path) as z:
        member = next(i for i in z.infolist() if not i.is_dir())
        lines = z.read(member).decode("latin-1").splitlines()
    issue = _issue_month(path, lines[0])
    cells = Counter()
    for issuer, agency, purpose, refi, score, channel, orig in _records(lines):
        if agency not in ("F", "V") or purpose not in KINDS or (purpose == "2" and refi not in FULL_REFI) or not orig[:6].isdigit():
            continue
        month = f"{orig[:4]}-{orig[4:6]}"
        if not -1 <= _lag(issue, month) <= LAG_MAX:
            continue
        step = int(score) // 5 * 5 if len(score) == 3 and score.isdigit() else None
        cells[(issuer, agency, KINDS[purpose], CHANNELS.get(channel, "other"), month, step)] += 1
    return issue, pd.DataFrame([(*k, v) for k, v in cells.items()], columns=COLUMNS)


def _read_issuers(path: Path) -> dict[str, str]:
    names = {}
    for ln in path.read_text(encoding="latin-1").splitlines():  # issuer 1-4, program 5-6, name 7-106
        if len(ln) > 7 and ln[:4].isdigit():
            names.setdefault(ln[:4], " ".join(ln[6:106].split()))
    return names


def ingest(files: list[Path]) -> list[dict]:
    """Ginnie Mae loan zips and issuer files -> data/ginnie/."""
    paths.GINNIE.mkdir(parents=True, exist_ok=True)
    out = []
    for path in map(Path, files):
        if path.name.lower().startswith("issrinfo"):
            names = _read_issuers(path)
            (paths.GINNIE / "issuers.json").write_text(json.dumps(names, indent=0, sort_keys=True))
            out.append({"file": path.name, "issuers": len(names)})
            continue
        issue, cells = read_loans(path)
        cells.to_parquet(paths.GINNIE / f"{issue}.parquet", compression="zstd", index=False)
        out.append({"file": path.name, "issue": issue, "loans": int(cells.n.sum())})
    return out


def _reference(con) -> dict:
    """What the two scores do on Fannie and Freddie loans showing both."""
    both = con.execute("SELECT agency, classic_fico AS c, vs4 AS v FROM loans WHERE classic_fico BETWEEN 300 AND 850 AND vs4 BETWEEN 300 AND 850").df()
    if both.empty:
        return {"odds": pd.Series(dtype=float), "factor": None, "n": 0}
    top = both[both.v >= TOP]
    gap = both.v - both.c
    fannie = both[both.agency == "FNMA"]
    use = fannie if len(fannie) else both
    far_at_top = float((top.v - top.c >= GAP).mean()) if len(top) else None
    return {"odds": use.assign(step=use.c // 5 * 5).groupby("step").v.agg(lambda s: float((s >= TOP).mean())), "n": len(both), "vs4": float((both.v >= TOP).mean()), "classic": float((both.c >= TOP).mean()),
            "high_of_top": float((top.v >= HIGH).mean()) if len(top) else None, "far_at_top": far_at_top, "far_all": float((gap >= GAP).mean()),
            "factor": float((gap >= GAP).mean()) / far_at_top if far_at_top else None}


def _r(v, digits=6):
    return None if v is None or v != v else round(float(v), digits)


def build_datasets(con) -> dict[str, list[dict]]:
    files = sorted(str(p) for p in paths.GINNIE.glob("*.parquet")) if paths.GINNIE.exists() else []
    if not files:
        return {"ginnie_va": []}
    cells = pd.concat([pd.read_parquet(f).assign(issue=Path(f).stem) for f in files], ignore_index=True)
    first_issue = min(cells.issue)
    floor = f"{int(first_issue[:4]) - 1}-12" if first_issue.endswith("-01") else f"{first_issue[:5]}{int(first_issue[5:]) - 1:02d}"  # earlier closings are only part-covered by the first file
    scored = cells[cells.score5.notna() & (cells.month >= floor)]
    names_file = paths.GINNIE / "issuers.json"
    names = json.loads(names_file.read_text()) if names_file.exists() else {}
    name = lambda i: short_name(names[i]) if i in names else f"Issuer {i}"  # noqa: E731
    ref = _reference(con)

    def stats(q) -> dict:
        n, k = int(q.n.sum()), int(q.n[q.score5 >= TOP].sum())
        full = float((q.score5.map(ref["odds"]).fillna(0) * q.n).sum())
        return {"n": n, "k": k, "share": _r(k / n) if n else None, "full": _r(full, 1), "signal": _r(k / full) if full else None}

    va, fha = scored[scored.agency == "V"], scored[scored.agency == "F"]
    at_top = va[va.score5 >= TOP].groupby("issuer").n.sum().sort_values(ascending=False)
    leaders = list(at_top.index[:2])
    lead = leaders[0] if leaders else None
    second = leaders[1] if len(leaders) > 1 else None
    by_month = va.groupby("month").n.sum()
    months = sorted(by_month[by_month >= MONTH_MIN].index)
    lead_va = va[va.issuer == lead]
    lead_own = lead_va[lead_va.channel.isin(["retail", "broker"])]
    lead_retail = lead_va[(lead_va.channel == "retail") & (lead_va.kind == "purchase")]
    second_va = va[va.issuer == second]
    series = [("lead_retail", f"{name(lead)}, retail purchase", lead_retail), ("lead_own", f"{name(lead)}, retail and broker", lead_own), ("second", f"{name(second)}, all loans", second_va),
              ("others", "All other lenders", va[~va.issuer.isin(leaders)]), ("fha", "FHA, all lenders", fha)]
    rows = [{"view": "month", "month": m, "key": key, "label": label, **stats(q[q.month == m])} for key, label, q in series for m in months]
    since = next((m for m in months if int(lead_own[(lead_own.month == m) & (lead_own.score5 >= TOP)].n.sum()) >= START_MIN), None)

    window = va[va.month >= since] if since else va.iloc[0:0]
    tally = window.groupby("issuer").n.sum().sort_values(ascending=False)
    k_by = window[window.score5 >= TOP].groupby("issuer").n.sum()
    shown = list(tally.index[:LENDER_TOP]) + [i for i in tally.index[LENDER_TOP:] if k_by.get(i, 0) >= 2]
    for rank, issuer in enumerate(shown, 1):
        q = window[window.issuer == issuer]
        s = stats(q)
        small = s["full"] < SMALL_FULL
        rows.append({"view": "lender", "rank": rank, "issuer": issuer, "name": name(issuer), **s, "k_high": int(q.n[q.score5 >= HIGH].sum()),
                     "signal": None if small else s["signal"], "upper": None if small or s["k"] > max(UPPER) else _r(UPPER[s["k"]] / s["full"]), "too_few": small})

    recent = months[-2:]
    for key, label, q in [*series[:3], ("all", "All VA loans", va)]:
        s = stats(q[q.month.isin(recent)])
        rows.append({"view": "range", "key": key, "label": label, **s, "high": s["signal"], "low": _r(s["signal"] * ref["factor"]) if s["signal"] is not None and ref["factor"] else None})
    for issuer in leaders:
        q = window[window.issuer == issuer]
        for (kind, channel, month), part in q.groupby(["kind", "channel", "month"]):
            if month in months:
                rows.append({"view": "channel", "issuer": issuer, "name": name(issuer), "kind": kind, "channel": channel, "month": month, **stats(part)})

    before = va[va.month < since] if since else va
    win_k = int(window.n[window.score5 >= TOP].sum())
    rows.append({"view": "meta", "files": len(files), "first_issue": min(cells.issue), "last_issue": max(cells.issue), "first": months[0] if months else None, "last": months[-1] if months else None, "since": since, "m1": recent[0] if recent else None, "m2": recent[-1] if recent else None,
                 "lead": name(lead), "second": name(second), "va_n": int(va.n.sum()), "fha_n": int(fha.n.sum()), "fha_k": int(fha.n[fha.score5 >= TOP].sum()), "window_k": win_k,
                 "leaders_share": _r(int(window.n[(window.score5 >= TOP) & window.issuer.isin(leaders)].sum()) / win_k) if win_k else None,
                 "before_lead_k": int(before.n[(before.issuer == lead) & before.channel.isin(["retail", "broker"]) & (before.score5 >= TOP)].sum()), "before_lead_n": int(before.n[(before.issuer == lead) & before.channel.isin(["retail", "broker"])].sum()),
                 "before_second_k": int(before.n[(before.issuer == second) & (before.score5 >= TOP)].sum()), "before_second_n": int(before.n[before.issuer == second].sum()),
                 "high_elsewhere": int(va.n[(va.score5 >= HIGH) & ~va.issuer.isin(leaders)].sum()), "lead_high_of_top": _r(int(va.n[(va.issuer == lead) & (va.score5 >= HIGH)].sum()) / max(int(at_top.get(lead, 0)), 1)),
                 "second_high_of_top": _r(int(va.n[(va.issuer == second) & (va.score5 >= HIGH)].sum()) / max(int(at_top.get(second, 0)), 1)), "top": TOP, "high": HIGH, "gap": GAP,
                 "ref_n": ref["n"], "ref_vs4": _r(ref.get("vs4")), "ref_classic": _r(ref.get("classic")), "ref_high_of_top": _r(ref.get("high_of_top")), "ref_far_at_top": _r(ref.get("far_at_top")), "ref_far_all": _r(ref.get("far_all")), "factor": _r(ref.get("factor"))})
    keys = sorted({k for r in rows for k in r})
    return {"ginnie_va": [{k: r.get(k) for k in keys} for r in rows]}
