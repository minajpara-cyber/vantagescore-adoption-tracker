"""The weekly note: what changed in a week of first disclosure, set against the week before.

From every record that carries the Pricing Indicator (scw, scores.py), by the week a loan first appeared in an intraday file, from
WEEK_FROM on. The lines are rebuilt from the loan files at each refresh, so corrections and later republished records can move an
old week's figures a little. Weeks move with the mix of lenders delivering in them, and a week is partial until the files reach its
Friday.

  week_note  view week: one row per week: its label, the last day seen, partial, latest (the note to open with: the last full week),
             loans and shares for both GSEs and Fannie Mae.
             view line: the week's sentences in order: kind (mix, movers, both, rule, rate, start, said), text, and for a statement
             its source and link.
"""
from datetime import date, timedelta

from .scores import WEEK_FROM

MIN_MOVER = 100  # loans in both weeks for a lender's VS4 share to count as moving
MOVE = 0.03
MIN_BOTH = 50  # Fannie Mae loans in both weeks
BOTH_MOVE = 0.10
MIN_RULE = 40  # loans with VS4 1-19 points above FICO in both weeks
RULE_MOVE = 0.05
TOP = 4
START_NAMES = 6


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def _signed(x: float) -> str:
    return f"{x:+.1f}"


def _r(v):
    return round(v, 6) if isinstance(v, float) else v


def build_datasets(con, statements: list[dict], pricing: list[dict]) -> dict[str, list[dict]]:
    """Needs scw (scores.py) and seller_map and entity_names (lenders.py)."""
    through = con.execute("SELECT max(first_intraday_date) FROM loans").fetchone()[0]
    weeks: dict[date, dict] = {}
    for week, agency, n, v, b, vo, fo in con.execute(f"""
            SELECT week, coalesce(agency, 'All'), count(*), count(*) FILTER (WHERE is_v), count(*) FILTER (WHERE has_fico AND has_vs4),
                   count(*) FILTER (WHERE has_vs4 AND NOT has_fico), count(*) FILTER (WHERE has_fico AND NOT has_vs4)
            FROM scw WHERE week >= DATE '{WEEK_FROM}' GROUP BY week, ROLLUP(agency)""").fetchall():
        weeks.setdefault(week, {})[agency] = {"n": n, "v": v / n, "b": b / n, "vo": vo / n, "fo": fo / n}
    if not weeks:
        return {"week_note": []}
    by_seller: dict[date, dict] = {}
    for week, sid, n, v, fn, fb, rn, rv in con.execute(f"""
            SELECT week, seller_id, count(*), count(*) FILTER (WHERE is_v), count(*) FILTER (WHERE agency = 'FNMA'),
                   count(*) FILTER (WHERE agency = 'FNMA' AND has_fico AND has_vs4), count(*) FILTER (WHERE gap BETWEEN 1 AND 19),
                   count(*) FILTER (WHERE gap BETWEEN 1 AND 19 AND is_v)
            FROM scw WHERE week >= DATE '{WEEK_FROM}' GROUP BY 1, 2""").fetchall():
        by_seller.setdefault(week, {})[sid] = {"n": n, "v": v, "fn": fn, "fb": fb, "rn": rn, "rv": rv}
    names = {i: s for i, s in con.execute("SELECT id, short FROM entity_names").fetchall()}
    firsts = con.execute("""
        SELECT m.id, min(coalesce(l.first_intraday_date, l.issue_month)) FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.score_model = 'V' GROUP BY 1""").fetchall()
    rates = {r["key"]: r for r in pricing if r.get("view") == "week" and r.get("cover") == "all" and r.get("basis") == "headline"}

    def moved(cur, prev, top, bottom, least, far):
        """Lenders whose share top / bottom moved at least far, largest contribution first."""
        out = []
        for sid, c in cur.items():
            p = prev.get(sid)
            if p and c[bottom] >= least and p[bottom] >= least:
                was, now = p[top] / p[bottom], c[top] / c[bottom]
                if abs(now - was) >= far:
                    out.append((abs(now - was) * c[bottom], names.get(sid, sid), was, now))
        return [f"{name} {_pct(was)} to {_pct(now)}" for _, name, was, now in sorted(out, key=lambda x: (-x[0], x[1]))[:TOP]]

    ordered = sorted(weeks)
    full = [w for w in ordered if through >= w + timedelta(days=4)]
    opening = full[-1] if full else ordered[-1]
    out = []
    for i, week in enumerate(ordered):
        end = week + timedelta(days=6)
        last = min(end, through)
        partial = through < week + timedelta(days=4)
        label = f"{_day(week)} to {_day(last)}" if last != week else _day(week)
        cur, prev = weeks[week], weeks[ordered[i - 1]] if i else {}
        a, f = cur["All"], cur.get("FNMA")
        out.append({"view": "week", "week": week.isoformat(), "label": label, "through": last.isoformat(), "partial": partial, "latest": week == opening,
                    "loans": a["n"], "vs4_share": a["v"], "both_share": a["b"], "no_fico_share": a["vo"], "fico_only_share": a["fo"],
                    "fnma_loans": f["n"] if f else None, "fnma_vs4_share": f["v"] if f else None, "fnma_both_share": f["b"] if f else None})
        lines = []
        pa, pf = prev.get("All"), prev.get("FNMA")
        ago = lambda now, was: f"{_pct(now)} ({_pct(was)} the week before)" if was is not None else _pct(now)  # noqa: E731
        lines.append(("mix", f"{a['n']:,} loans first disclosed {label}{', so far' if partial else ''}: priced on VS4 {ago(a['v'], pa and pa['v'])}, both scores on "
                             f"{ago(a['b'], pa and pa['b'])}, no Classic FICO on {ago(a['vo'], pa and pa['vo'])}."))
        if f:
            lines.append(("mix", f"At Fannie Mae, whose files show both scores more fully: priced on VS4 {ago(f['v'], pf and pf['v'])}, both scores on {ago(f['b'], pf and pf['b'])}."))
        if i:
            sc, sp = by_seller.get(week, {}), by_seller.get(ordered[i - 1], {})
            if m := moved(sc, sp, "v", "n", MIN_MOVER, MOVE):
                lines.append(("movers", f"VS4 share moved most at {', '.join(m)}."))
            if m := moved(sc, sp, "fb", "fn", MIN_BOTH, BOTH_MOVE):
                lines.append(("both", f"Both scores at Fannie Mae moved most at {', '.join(m)}."))
            if m := moved(sc, sp, "rv", "rn", MIN_RULE, RULE_MOVE):
                lines.append(("rule", f"Use of VS4 with its score 1 to 19 points above FICO moved at {', '.join(m)}."))
        rate, was = rates.get(week.isoformat()), rates.get(ordered[i - 1].isoformat()) if i else None
        if rate and rate.get("net_bp") is not None:
            lines.append(("rate", f"VS4 note rates against the FICO model: {_signed(rate['net_bp'])} bp on {rate['n']:,} loans"
                                  + (f" ({_signed(was['net_bp'])} bp the week before)." if was and was.get("net_bp") is not None else ".")))
        started = sorted(names.get(sid, sid) for sid, first in firsts if week <= first <= end)
        if started:
            shown = ", ".join(started[:START_NAMES]) + (f" and {len(started) - START_NAMES} more" if len(started) > START_NAMES else "")
            lines.append(("start", f"First VS4 loan: {shown}."))
        rows = [("said", f"{s['who']}: {s['statement']}", s["source"], s["url"]) for s in statements if s["date"] and week.isoformat() <= s["date"] <= end.isoformat()]
        for order, line in enumerate(lines + rows):
            kind, text, *link = line
            out.append({"view": "line", "week": week.isoformat(), "order": order, "kind": kind, "text": text,
                        "source": link[0] if link else None, "url": link[1] if link else None})
    keys = sorted({k for r in out for k in r})
    return {"week_note": [{k: _r(r.get(k)) for k in keys} for r in out]}
