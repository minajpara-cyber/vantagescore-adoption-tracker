"""The first screen and the VS4-only card: who gets paid, in five rows. Both datasets are private: on DASHBOARD_DATASETS only.

  vs4_only  which loans show VS4 and no FICO, from the records that carry the Pricing Indicator (scw, scores.py), the base of score_mix and lender_mix, so every total ties to score_mix. A score not shown
            is unknown, so these counts are the most that can be VS4 only. Months go by issue month, in score_mix's headline month; weeks go by week first disclosed, in any issue month, which is a different set of loans.
            view meta      one row: month, final and final_fh (that GSE's month-end file for the month is in), through (the data's last day), week_from, lead_id and lead_label (the small lender set apart), name, fh_tag (the tag over Freddie's chart: its likely gap, and while its files stop short of the headline month, the gap in the latest month both GSEs reach).
            view gse       the headline month: key fnma, fnma_ex (Fannie without the small lender), fhlmc, all: label, number, what, n, vo, share, tag (Freddie's, under the guard of its sentence, or while its own month's files may not show second scores; Fannie's and both GSEs', while Fannie's month's files may not show them).
            view week      Fannie and Freddie by week first disclosed from WEEK_FROM: n, scored (every VS4 or FICO loan first disclosed that week), cover (n / scored), shows (shows VS4), priced (priced on VS4), vo (shows VS4 and no FICO),
                           vo_lead, n_lead, vo_without, share, share_without, vo_head (vo issued in the headline month), first (the week WEEK_FROM, the first week most loans could show both scores), partial, days, through, label, order.
            view before    the weeks before WEEK_FROM, one row per GSE, so the weeks tie to score_mix's view all.
            view lender    the headline month, one row per lender with VS4-only loans at either GSE (NAMED at most, most at Fannie first), and for Rocket and UWM whatever they show, then all other lenders (rest), then all lenders (total), so the rows tie to score_mix's month:
                           short, lenders, and for fn_ Fannie and fh_ Freddie: n, priced, priced_fico (priced on VS4 and shows a FICO), vo, fico_share (priced_fico / priced, from MIN_OWN priced loans), own_share (vo / n).
            view band      Fannie in the headline month by VS4 score band, counts: vo, vo_fthb (first-time buyers), vo_lead, vo_without, vo_without_fthb, shows_lead (the small lender's own loans showing VS4), and both, both_fthb (loans showing both scores, the comparison).
            view funnel    from pull to loan, each on its own base and date: key, label, share, text, what, kind (outside: the private input, with said, its words for the sentence; files), only, source, url, date.
            view sentence  key, order, text, each under its guard.
            view check     key, label, pass, detail: do the totals tie to score_mix; warn only (site.front_warnings).
  front     the first screen, in the order adoption, vs4_only, market, rate, price.
            view meta      one row: through, dated, line (the frame, from INPUTS, under its guard), lead, month, slice_note (the Overview chart's words on its VS4-only slice, under the card's guard).
            view said_check  one row, Step 1's: the tracker's quarter beside the GSEs' own figure, for the statements table.
            view row       key, order, label, number (as printed), number_value, unit, what (what the number is), line, go (the tab), cap (what the small picture draws), month.
            view pic       the row's small picture: key (the row's), order, x, label, v, text, what, and open and outside (adoption), n (market), dot, tl, th (rate), ref (price).
            view sentence  row, key, order, text: the words under a row, each under its guard. place = rate marks the one line of LLPA dollars, for its labelled place on the Rate tab.
Sentences are templates: every number and every name in them comes from the data, under a guard. Outside figures and words with no number behind them live in the git-ignored INPUTS file, by key, and print only where a guard here lets them.
"""
import csv
import re
from datetime import date, timedelta
from math import floor, isfinite

from . import paths
from .exposure import PULL_CASES, usd_price
from .pricing import GRID_CHANGE, LENDER_APART, NO_DIFF, PAYMENT_BALANCE, ROCKET, TOO_FEW, UWM, VS_OFFSET, _and, _day, _five, _holds_zero, _hundred, _month, _out95, _payment, _plural, _range, _signed, _word
from .scores import HEADLINE_MIN, MIX_GROUPS, WEEK_FROM
from .warehouse import WEEK_TO_FRIDAY

NAME = "Shows VS4 only, at most"
INPUTS = paths.PRIVATE / "front_inputs.csv"  # key,value,label,what,text,from_month,until_month,source,url,date
GO = {"adoption": "lenders", "vs4_only": "outlook", "market": "market", "rate": "pricing", "price": "outlook"}
BANDS = [("lt660", "Under 660", 659, "under 660"), ("660_699", "660-699", 699, "at 660-699"), ("700_739", "700-739", 739, "at 700-739"), ("740_779", "740-779", 779, "at 740-779"), ("780up", "780+", 850, "at 780+")]
UNDER = ("lt660", "660_699")  # the low bands, under 700
GSES = (("fn", "FNMA", "Fannie"), ("fh", "FHLMC", "Freddie"))
PIC_MONTHS = 4  # months on the adoption row's small picture
NAMED = 12  # lenders named on the card
MIN_OWN = 20  # VS4-priced loans a lender's share of them needs
MIN_PRICED = 100  # loans a sentence needs before it names a lender's share
SMALL_LENDER = 0.02  # under this share of Fannie's loans with the Pricing Indicator, a lender is a small lender
LEAD_MATTERS = 0.25  # the small lender is set apart while it holds this share of the month's VS4-only loans
ALMOST_NONE = 0.01  # the most of a month "almost none" can cover
BOTH_FLOOR = 0.02  # under this share of Fannie's month showing both scores, its files are not showing second scores, and "shows VS4 and no FICO" says more about the files than about lenders
ONE_SIDE = 0.10  # under this share of the month's VS4-priced loans showing a FICO, the files may have blanked that side alone
GSE_THIN = 0.10  # under this share of the month's loans, one GSE's files have stopped short and the month cannot speak for both
KEEPS = 0.90  # share of VS4-priced Fannie loans showing a FICO, at both of Rocket and UWM
GAP_TIMES, GAP_MIN = 5, 0.02  # how many times its Fannie share, and how high, a lender's Freddie share must sit before the card calls it a likely gap in the files
SAME_AT_BOTH = (0.75, 1.33)  # the ratio of a lender's two shares that reads as about the same at both
FEW = 4  # VS4 loans in a month at or under which a new lender "made few"
TWO_OF_IT = 0.5  # the two largest VS4 lenders' share of VS4 loans before the words name them
MIX_MOST, MIX_REVERSE, SINCE_MOST = 0.5, 0.5, 0.75  # the shift between lenders' share of the month's change; the earlier fall's size against it; the same lenders' share of the change since the first month
MIX_ZERO = 0.002  # 0.2 points: within this, and within a tenth of the change, the shift between lenders is about zero
FLAT_RECENT = 5  # the latest full weeks the flat test looks at, so one old week does not count for good
FLAT_MAX, FLAT_RISE, FLAT_WEEKS = 0.005, 1.5, 3  # the most a full week can show without the small lender; how far the latest full week may sit over the earlier ones' mean; how many full weeks it takes
BURST_TIMES, BURST_MIN = 3, 30  # a full week this many times the middle one of the weeks named, on at least this many loans, gets its own clause, so one week's burst does not colour the rest
BAND_MIN, BAND_APART, FTHB_APART = 50, 0.15, 0.10  # loans before the card says what the bands point to; how far a band's share must sit above loans showing both, and first-time buyers'
BARELY = 5.0  # bp: at or under this the rate gap is "barely"
SMALL_GAP = 2.0  # bp: at or under this a lender's note rate moves about this
SAVING = 0.9  # share of the LLPA saving collected
RARE_BELOW = 0.05  # share priced on VS4 with VS4 below FICO that counts as almost never
BOOK_SHARE = 0.5  # a lender group's share of the same-FICO gap before the words say mostly it
MIN_BOTH = 1000  # loans showing both scores the price row's break-even needs
ROUNDED = 0.005  # the GSEs print a whole percent
ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
FILLED = ("front_frame", "rate_fico")  # the lines _fill() puts a figure in
INPUT_SHARES = ("tu_pull_share", "du_app_share")  # outside figures the first screen prints, each a share
INPUT_WORDS = ("front_frame", "adoption_fico", "adoption_line_tail", "vs4_line_tail", "vs4_line_window", "vs4_tests_nothing", "vs4_tests_window", "vs4_allowed", "vs4_why_rare", "vs4_why_rare_fha_open", "rate_fico", "rate_cost_said")  # lines the first screen and the card print


def _r(v):
    return round(v, 6) if isinstance(v, float) else v


def _pad(rows):
    keys = sorted({k for r in rows for k in r})
    return [{k: _r(r.get(k)) for k in keys} for r in rows]


def _one(x):
    """A share: one decimal, two under 0.1%."""
    return f"{x:.2%}" if 0 < x < 0.001 else f"{x:.1%}"


def _whole(x):
    return f"{x:.0%}"


def _floor(x):
    """A floor as a whole percent, rounded down, so "at least" stays true."""
    return f"{floor(round(x * 100, 6))}%"


def _pts(x):
    """A change in share as points: 0.04, 0.6, 2.2."""
    v = abs(x) * 100
    return f"{v:.2f}" if v < 0.095 else f"{v:.1f}"


def _at_least(x):
    """A floor in words: 99% or more, or all."""
    return "all" if x >= 1 else f"{int(x * 100)}% or more"


def _versus(now, was, say=_whole):
    """up from, down from or level with, as the two print."""
    return "level with" if say(now) == say(was) else "up from" if now > was else "down from"


def load_inputs(path=None):
    """The private file by key: outside figures (value) and words (text), each with the issue months it holds for. A missing file leaves them out and a row too broken to trust drops out with it (a stray comma, a month not written 2026-11-01): the inputs check says which; it stops nothing."""
    def number(v):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return x if isfinite(x) else None

    def whole(r):
        return None not in r and all(not r.get(k) or ISO_DAY.fullmatch(r[k]) for k in ("from_month", "until_month"))

    try:
        with (path or INPUTS).open(newline="", encoding="utf-8-sig") as f:
            return {r["key"]: {**r, "value": number(r.get("value"))} for r in csv.DictReader(f) if r.get("key") and whole(r)}
    except (OSError, ValueError, csv.Error):
        return {}


def _fill(text, key, value):
    """A private line with its one figure in it, or None if a placeholder is left, so a mistyped one never prints."""
    out = (text or "").replace("{" + key + "}", value)
    return out if out and "{" not in out else None


def _say(inputs, key, month=None):
    """A row of words while its months hold: from_month <= month < until_month."""
    r = inputs.get(key)
    if not r or not r.get("text"):
        return None
    if month and ((r.get("from_month") and month < r["from_month"]) or (r.get("until_month") and month >= r["until_month"])):
        return None
    return r["text"] if "{" not in r["text"] or key in FILLED else None


# ---- the VS4-only card ----


def _small_lead(con):
    """The small lender with the most VS4-only loans at Fannie, over every record, so the weeks keep one lender whichever month heads the card: under SMALL_LENDER of those loans."""
    hit = con.execute(f"""
        WITH s AS (SELECT seller_id, count(*) AS n, count(*) FILTER (WHERE {MIX_GROUPS['vs_only']}) AS vo FROM scw WHERE agency = 'FNMA' GROUP BY 1)
        SELECT seller_id FROM s WHERE vo > 0 AND n < {SMALL_LENDER} * (SELECT sum(n) FROM s) AND vo >= {LEAD_MATTERS} * (SELECT sum(vo) FROM s) ORDER BY vo DESC, seller_id LIMIT 1""").fetchone()
    return hit[0] if hit else None


def _weeks(con, lead, month):
    """view week and view before, by GSE. A week is partial until that GSE's own files reach its Friday, the rule of the weekly files' complete flag."""
    vo = MIX_GROUPS["vs_only"]
    last_day = dict(con.execute("SELECT agency, max(first_intraday_date) FROM loans GROUP BY 1").fetchall())
    scored = {(a, w): n for a, w, n in con.execute(f"""
        SELECT agency, date_trunc('week', first_intraday_date)::DATE, count(*) FROM loans
        WHERE score_model IN ('V', 'C') AND first_intraday_date >= DATE '{WEEK_FROM}' GROUP BY 1, 2""").fetchall()}
    head = f"month = DATE '{month}'" if month else "false"
    start = date.fromisoformat(WEEK_FROM)
    weeks, before = [], {}
    fields = ("n", "shows", "priced", "vo", "vo_lead", "n_lead", "vo_head")
    for agency, week, *counts in con.execute(f"""
            SELECT agency, week, count(*), count(*) FILTER (WHERE has_vs4), count(*) FILTER (WHERE is_v), count(*) FILTER (WHERE {vo}),
                   count(*) FILTER (WHERE {vo} AND seller_id = ?), count(*) FILTER (WHERE seller_id = ?), count(*) FILTER (WHERE {vo} AND {head})
            FROM scw GROUP BY 1, 2 ORDER BY 1, 2""", [lead, lead]).fetchall():
        r = dict(zip(fields, counts))
        if week < start:
            b = before.setdefault(agency, {"view": "before", "agency": agency, "label": f"Before {_day(WEEK_FROM)}", **dict.fromkeys(fields, 0)})
            for k in fields:
                b[k] += r[k]
            continue
        rest_n, total = r["n"] - r["n_lead"], scored.get((agency, week))
        weeks.append({"view": "week", "agency": agency, "week": week.isoformat(), "order": (week - start).days // 7, "label": _day(week.isoformat()), "through": min(week + timedelta(days=6), last_day[agency]).isoformat(),
                      "partial": last_day[agency] < week + timedelta(days=WEEK_TO_FRIDAY), "days": min((last_day[agency] - week).days + 1, WEEK_TO_FRIDAY + 1), "first": week == start, "scored": total, "cover": r["n"] / total if total else None, **r,
                      "vo_without": r["vo"] - r["vo_lead"], "share": r["vo"] / r["n"], "share_without": (r["vo"] - r["vo_lead"]) / rest_n if rest_n else None})
    for b in before.values():
        b["vo_without"] = b["vo"] - b["vo_lead"]
    return weeks, list(before.values())


def _lender_rows(con, month, names):
    """view lender: one row per lender with VS4-only loans at either GSE, and for Rocket and UWM whatever they show, then all other lenders, then all lenders, tying to the month."""
    vo = MIX_GROUPS["vs_only"]
    cells = {}
    for agency, sid, n, priced, priced_fico, v in con.execute(f"""
            SELECT agency, seller_id, count(*), count(*) FILTER (WHERE is_v), count(*) FILTER (WHERE is_v AND has_fico), count(*) FILTER (WHERE {vo})
            FROM scw WHERE month = DATE '{month}' GROUP BY 1, 2""").fetchall():
        cells.setdefault(sid, {})[agency] = (n, priced, priced_fico, v)
    empty = (0, 0, 0, 0)
    vo_at = lambda sid, agency: cells[sid].get(agency, empty)[3]  # noqa: E731
    priced_of = lambda sid: sum(c[1] for c in cells[sid].values())  # noqa: E731
    named = sorted((s for s in cells if vo_at(s, "FNMA") or vo_at(s, "FHLMC")), key=lambda s: (-vo_at(s, "FNMA"), -vo_at(s, "FHLMC"), -priced_of(s), s))[:NAMED]
    named += [s for s in (ROCKET, UWM) if s in cells and s not in named]  # with no VS4-only loan or past the cap, the card's words still rest on these two

    def row(group, **extra):
        out = {"view": "lender", "month": month, **extra}
        for prefix, agency, _ in GSES:
            n, priced, priced_fico, v = (sum(cells[s].get(agency, empty)[i] for s in group) for i in range(4))
            out |= {f"{prefix}_n": n, f"{prefix}_priced": priced, f"{prefix}_priced_fico": priced_fico, f"{prefix}_vo": v, f"{prefix}_fico_share": priced_fico / priced if priced >= MIN_OWN else None, f"{prefix}_own_share": v / n if n else None}
        return out

    rows = [row([s], id=s, short=names.get(s, s), order=i, lenders=1) for i, s in enumerate(named)]
    rest = sorted(set(cells) - set(named))
    rows.append(row(rest, id=None, short="All other lenders", order=len(named), lenders=len(rest), rest=True))
    rows.append(row(sorted(cells), id=None, short="All lenders", order=len(named) + 1, lenders=len(cells), total=True))
    return rows


def _bands(con, month, lead):
    """view band: Fannie's VS4-only loans in the month by VS4 score band, as counts. vs: the VS4 score, on scw for this."""
    case = "CASE " + " ".join(f"WHEN vs <= {hi} THEN '{key}'" for key, _, hi, _ in BANDS) + " END"
    vo = MIX_GROUPS["vs_only"]
    got = {r[0]: r[1:] for r in con.execute(f"""
        SELECT {case} AS band, count(*) FILTER (WHERE {vo}), count(*) FILTER (WHERE {vo} AND fthb = 'Y'), count(*) FILTER (WHERE {vo} AND seller_id = ?), count(*) FILTER (WHERE {vo} AND fthb = 'Y' AND seller_id = ?),
               count(*) FILTER (WHERE seller_id = ?), count(*) FILTER (WHERE has_fico AND has_vs4), count(*) FILTER (WHERE has_fico AND has_vs4 AND fthb = 'Y')
        FROM scw WHERE agency = 'FNMA' AND month = DATE '{month}' AND has_vs4 GROUP BY 1""", [lead, lead, lead]).fetchall()}
    out = []
    for i, (key, label, _, words) in enumerate(BANDS):
        v, f, t, tf, tn, b, bf = got.get(key, (0, 0, 0, 0, 0, 0, 0))
        out.append({"view": "band", "agency": "FNMA", "month": month, "key": key, "label": label, "words": words, "order": i, "vo": v, "vo_fthb": f, "vo_lead": t, "vo_without": v - t, "vo_without_fthb": f - tf, "shows_lead": tn, "both": b, "both_fthb": bf})
    return out


def _funnel(inputs, fn, month):
    """From pull to loan, each on its own base and date. The outside figures come from the private input and drop out without it."""
    out = []
    for key in ("tu_pull_share", "du_app_share"):
        r = inputs.get(key)
        if r and r.get("value") is not None and 0 < r["value"] <= 1 and r.get("label"):
            out.append({"view": "funnel", "key": key, "label": r.get("label"), "share": r["value"], "text": f"about {_whole(r['value'])}", "what": r.get("what"), "kind": "outside", "said": _fill(r.get("text"), "share", _whole(r["value"])), "source": r.get("source"), "url": r.get("url"), "date": r.get("date")})
    if fn:
        at = f"Fannie's {_month(month)} loans"
        out += [{"view": "funnel", "key": "shows", "label": f"VS4 shows on {at}", "share": fn["vs_share"], "text": f"at least {_floor(fn['vs_share'])}", "what": "A floor: a score not shown is unknown.", "kind": "files"},
                {"view": "funnel", "key": "priced", "label": f"{at} priced on VS4", "share": fn["vs4_priced_share"], "text": _one(fn["vs4_priced_share"]), "what": "Exact: the Pricing Indicator names the score.", "kind": "files"},
                {"view": "funnel", "key": "vs_only", "label": f"{at}: {NAME[0].lower()}{NAME[1:]}", "share": fn["vs_only_share"], "text": f"at most {_one(fn['vs_only_share'])}", "what": "The most that can be VS4 only: a score not shown is unknown.", "kind": "files", "only": True}]
    return [{**r, "order": i} for i, r in enumerate(out)]


def counts(r):
    """A score_mix row in counts: its shares carry 6 places, enough under a million loans."""
    return {"n": r["loans"], "vo": round(r["vs_only_share"] * r["loans"]), "priced": round(r["vs4_priced_share"] * r["loans"]), "share": r["vs_only_share"]}


def both_share(r):
    """A score_mix row's share of loans showing both scores."""
    return (r.get("both_fico_share") or 0) + (r.get("both_vs_share") or 0)


def shows_second(r):
    """Whether a score_mix month's files show second scores: both scores on BOTH_FLOOR+ of its loans, and a FICO on ONE_SIDE+ of its VS4-priced loans, so a file that blanks only that side is caught too."""
    return both_share(r) >= BOTH_FLOOR and (r.get("both_vs_share") or 0) >= ONE_SIDE * (r.get("vs4_priced_share") or 0)


def blanked(score_mix, agency="FNMA"):
    """Months other than the headline whose files at this GSE do not show second scores. The weeks and the charts hold their loans whichever month heads the card."""
    return [r["start"] for r in score_mix if r["view"] == "month" and r["agency"] == agency and not r.get("headline") and r["loans"] >= HEADLINE_MIN and not shows_second(r)]


def why_files(r, this="this"):
    """Why a month's count speaks of the files before it speaks of lenders. The second reason is only a may: a lender dropping FICO would look the same."""
    if both_share(r) < BOTH_FLOOR:
        return f"only {_one(both_share(r))} of the month's loans show both scores, so {this} says more about the files than about lenders dropping FICO"
    return f"only {_one((r.get('both_vs_share') or 0) / r['vs4_priced_share'])} of the month's VS4-priced loans show a FICO, so {this} may say more about the files than about lenders dropping FICO"


def thin_gse(rows, field="loans"):
    """The GSE holding under GSE_THIN of a month's loans, if one does. rows: the month's rows by agency, with All. None with no GSE's row to go by."""
    total = (rows.get("All") or {}).get(field)
    if not total or not (rows.get("FNMA") or rows.get("FHLMC")):
        return None
    return next((a for a in ("FHLMC", "FNMA") if (rows.get(a) or {}).get(field, 0) < GSE_THIN * total), None)


def whose_words(thin, rows, field="loans"):
    """What a month's both-GSE figure holds."""
    if not thin:
        return "both GSEs"
    name = "Fannie" if thin == "FHLMC" else "Freddie"
    return f"almost all {name}" if (rows.get(thin) or {}).get(field) else f"{name} only"


def thin_words(thin, months, lasts):
    """A month nearly all one GSE's: why the other is not set beside it."""
    name, other = ("Freddie", "Fannie") if thin == "FHLMC" else ("Fannie", "Freddie")
    n, stop, m = (months.get(thin) or {}).get("loans", 0), f" stop at {_day(lasts[thin])}, so they" if lasts.get(thin) else "", _month(months["All"]["start"])
    return f"{name}'s files{stop} hold only {n:,} of {m}'s loans, too few to set beside {other}." if n else f"{name}'s files{stop} hold none of {m}'s loans."


def _bursts(shown):
    """The full weeks far above the others named beside them: BURST_TIMES the middle week, or the lower of the middle two, on BURST_MIN+ loans. None with one week: there is nothing to set it against."""
    counts = sorted(w["vo"] for w in shown)
    if len(counts) < 2:
        return []
    return [w for w in shown if w["vo"] >= max(BURST_TIMES * counts[(len(counts) - 1) // 2], BURST_MIN)]


def week_words(weeks, head_vo, name):
    """Fannie by week: the first week on the headline month's base where all of it is that month's, then the full weeks since and any partial week, in any issue month. A week that bursts past the rest gets its own count and the small lender's part of it, so it neither reads as a usual week nor colours "about half" for the others."""
    first = next((w for w in weeks if w["first"]), None)
    later = [w for w in weeks if not w["first"]]
    full, part = [w for w in later if not w["partial"]], [w for w in later if w["partial"]]
    out = []
    if first and first["vo"]:
        who = f", and {first['vo_lead']:,} of those are {name}" if name and first["vo_lead"] else ""
        if head_vo and first["vo_head"] == first["vo"] and first["vo"] * 2 >= head_vo:
            out.append(f"Of those {head_vo:,}, {first['vo']:,} came in the week of {first['label']}, the first week most loans could show both scores{who}.")
        else:
            out.append(f"The week of {first['label']}, the first week most loans could show both scores, shows {first['vo']:,}{who}.")
    bits = []
    shown = full[-4:]
    if shown:
        burst = _bursts(shown)
        usual = [w for w in shown if w not in burst]
        who = ""
        vo_all = sum(w["vo"] for w in usual)
        if name and vo_all:
            share = sum(w["vo_lead"] for w in usual) / vo_all
            who = f", about half {name}" if 0.4 <= share <= 0.6 else f", mostly {name}" if share > 0.6 else f", {_whole(share)} {name}" if share > 0 else ""
        when = "since then" if len(full) <= 4 else "in the latest four full weeks"
        each = ", ".join(f"{w['vo']:,}" for w in usual)
        apart = [f"{w['vo']:,} in the week of {w['label']}" + (f", {w['vo_lead']:,} of them {name}" if name and w["vo_lead"] else "") for w in burst]
        bits.append(f"By week first disclosed {when}, in any issue month: {each} a week{who}" + (f", with {_and(apart)}" if apart else ""))
    if part:
        w = part[-1]
        days = f"{_word(w['days'])}-day " if w["days"] < 5 else ""
        said = f"{w['vo']:,} in the {days}{w['label']} week"
        bits.append(said if bits else f"By week first disclosed, in any issue month: {said}")
    if bits:
        out.append(", and ".join(bits) + ".")
    return " ".join(out) or None


def _before(shares):
    """The mean of the latest full weeks before the latest one."""
    earlier = shares[-FLAT_RECENT:-1]
    return sum(earlier) / len(earlier)


def _flat(shares, latest_n=BURST_MIN):
    """Over the latest FLAT_RECENT full weeks: no week over FLAT_MAX, and the latest within FLAT_RISE of the mean of the weeks before it, unless it holds under BURST_MIN loans, too few to call a rise."""
    return max(shares[-FLAT_RECENT:]) <= FLAT_MAX and (latest_n < BURST_MIN or shares[-1] <= FLAT_RISE * _before(shares))


def trend(weeks):
    """Whether Fannie's latest full weeks look flat without the small lender, once FLAT_WEEKS of them exist. Past that, "rising" only while the latest week sits FLAT_RISE over the weeks before it, else "not flat"; None with too few."""
    full = [w for w in weeks if not w["first"] and not w["partial"]]
    if len(full) < FLAT_WEEKS or any(w["share_without"] is None for w in full[-FLAT_RECENT:]):
        return None
    shares = [w["share_without"] for w in full]
    if _flat(shares, full[-1].get("vo_without", BURST_MIN)):
        return "flat"
    return "rising" if shares[-1] > FLAT_RISE * _before(shares) else "not flat"


def trend_words(weeks, inputs, month, name):
    """Flat or rising, and whether a change at first pull could have reached the files yet (the private file's months). "That is flat" alone only while the weeks as printed are flat too: when the small lender bursts past them, the sentence says whose weeks are flat."""
    moving = trend(weeks)
    if moving == "flat":
        full = [w for w in weeks if not w["first"] and not w["partial"]]
        all_flat = not name or (_flat([w["share"] for w in full]) and not _bursts(full[-4:]))
        head = "That is flat" if all_flat else f"Without {name} that is flat"
        tail = _say(inputs, "vs4_tests_nothing", month) or _say(inputs, "vs4_tests_window", month)
        return f"{head}, but {tail}" if tail else f"{head}."
    if moving == "rising":
        last = [w for w in weeks if not w["first"] and not w["partial"]][-1]
        without = f" without {name}" if name else ""
        return f"That is rising: {_one(last['share_without'])} of the week of {last['label']}{without}."
    if moving == "not flat":
        full = [w for w in weeks if not w["first"] and not w["partial"]]
        without = f" without {name}" if name else ""
        return f"That has not stayed near zero: {_one(full[-1]['share_without'])} of the week of {full[-1]['label']}{without}, against {_one(_before([w['share_without'] for w in full]))} on average in the weeks just before it."
    return None


def band_words(bands, name):
    """What the bands point to, without the small lender while it matters (name), only where the counts allow and only against loans showing both scores. Then the small lender's own, as counts."""
    if not bands:
        return None
    vo, buyers = ("vo_without", "vo_without_fthb") if name else ("vo", "vo_fthb")
    n, both = sum(b[vo] for b in bands), sum(b["both"] for b in bands)
    top, low_bands = bands[-1], [b for b in bands if b["key"] in UNDER]
    low, fthb = sum(b[vo] for b in low_bands), sum(b[buyers] for b in bands)
    head = f"Without {name}, by" if name else "By"
    out = []
    if n:
        each = ", ".join(f"{b[vo]:,} {b['words']}" for b in bands)
        out.append(f"{head} VS4 score: {each}, and {fthb:,} of the {n:,} are first-time buyers.")
    if n and both:
        share_top, share_low, share_fthb = top[vo] / n, low / n, fthb / n
        both_top, both_low, both_fthb = top["both"] / both, sum(b["both"] for b in low_bands) / both, sum(b["both_fthb"] for b in bands) / both
        if n < BAND_MIN:
            out.append("Too few to tell whether FICO is not being bought or borrowers have thin credit files.")
        elif share_top >= both_top + BAND_APART:
            out.append(f"Clustered {top['words']} ({_whole(share_top)}, against {_whole(both_top)} of loans showing both scores), which points to FICO not being bought.")
        elif share_low >= both_low + BAND_APART and share_fthb >= both_fthb + FTHB_APART:
            out.append(f"Low scores and first-time buyers ({_whole(share_low)} under 700 and {_whole(share_fthb)} first-time buyers, against {_whole(both_low)} and {_whole(both_fthb)} of loans showing both scores) point to thin credit files more than to FICO not being bought.")
        else:
            out.append("Neither a cluster at the top nor low scores with first-time buyers stands out yet.")
    lead_n = sum(b["vo_lead"] for b in bands)
    if name and lead_n >= BAND_MIN:
        firsts = sum(b["vo_fthb"] - b["vo_without_fthb"] for b in bands)
        below, below_n = sum(b["vo_lead"] for b in bands[:-1]), sum(b.get("shows_lead", 0) for b in bands[:-1])
        own = f"; of its own loans showing VS4, {_whole(top['vo_lead'] / top['shows_lead'])} {top['words']} show no FICO, and {_whole(below / below_n)} of those below" if top.get("shows_lead", 0) >= MIN_OWN and below_n >= MIN_OWN else ""
        out.append(f"{name}'s {lead_n:,}: {bands[0]['vo_lead']:,} {bands[0]['words']}, {top['vo_lead']:,} {top['words']}, {firsts or 'no'} first-time buyers{own}.")
    return " ".join(out) or None


def freddie_gap(fh, fn, lenders, lead_id):
    """The large lender whose Freddie share sits far above its Fannie share, while Freddie as a whole sits far above Fannie: what the words "likely a gap in what its files show" rest on. None otherwise."""
    if not fh or not fn:
        return None
    named = sorted((r for r in lenders if r.get("id") and r["id"] != lead_id and r["fh_vo"]), key=lambda r: (-r["fh_vo"], r["id"]))
    big = named[0] if named else None
    if big and min(big["fh_n"], big["fn_n"]) >= MIN_PRICED and big["fh_own_share"] >= GAP_TIMES * big["fn_own_share"] and big["fh_own_share"] >= GAP_MIN and fh["vs_only_share"] >= 2 * fn["vs_only_share"]:
        return big
    return None


def freddie_words(fh, fn, al, lenders, lead_id, name, far_fh="", far_all=""):
    """Freddie beside Fannie, as a likely gap in what its files show while the lenders' own shares say so, never as confirmed. far_fh, far_all: " so far" while that month's month-end file is out, which at Freddie can differ from Fannie."""
    if not fh:
        return None
    head = f"Freddie shows {_one(fh['vs_only_share'])}{far_fh}"
    tail = f" Both GSEs together, at most {_one(al['vs_only_share'])}{far_all}." if al else ""
    big = freddie_gap(fh, fn, lenders, lead_id)
    if not big:
        beside = f", Fannie {_one(fn['vs_only_share'])}" if fn else ""
        return f"{head}{beside}.{tail}"
    t = next((r for r in lenders if lead_id and r.get("id") == lead_id), None)
    same = bool(t and t is not big and min(t["fh_n"], t["fn_n"]) >= MIN_PRICED and t["fn_own_share"] > 0 and SAME_AT_BOTH[0] <= t["fh_own_share"] / t["fn_own_share"] <= SAME_AT_BOTH[1])
    beside = f", while {name} shows about the same at both" if same else ""
    return f"{head}, most likely a gap in what its files show, not confirmed: {big['short']} shows {_one(big['fh_own_share'])} there and {_one(big['fn_own_share'])} at Fannie{beside}.{tail}"


def keeps(lenders):
    """Rocket's and UWM's lender rows, each only with MIN_PRICED+ VS4-priced Fannie loans in the headline month."""
    out = []
    for sid in (ROCKET, UWM):
        r = next((x for x in lenders if x.get("id") == sid), None)
        out.append(r if r and r["fn_priced"] >= MIN_PRICED else None)
    return out


def keep_fico(lenders):
    """Whether both show a FICO on KEEPS+ of their VS4-priced Fannie loans."""
    a, b = keeps(lenders)
    return bool(a and b and a["fn_priced_fico"] / a["fn_priced"] >= KEEPS and b["fn_priced_fico"] / b["fn_priced"] >= KEEPS)


def all_keep(lenders):
    """Whether Fannie's month as a whole shows a FICO on KEEPS+ of its VS4-priced loans."""
    total = next((r for r in lenders if r.get("total")), None)
    return bool(total and total["fn_priced"] and total["fn_priced_fico"] / total["fn_priced"] >= KEEPS)


def keeps_words(lenders):
    a, b = keeps(lenders)
    if not a or not b:
        return None
    still = "still " if keep_fico(lenders) else ""
    return f"{a['short']} and {b['short']} {still}show a FICO on {_one(a['fn_priced_fico'] / a['fn_priced'])} and {_one(b['fn_priced_fico'] / b['fn_priced'])} of the Fannie loans they price on VS4."


def funnel_words(funnel, month, readable=True):
    by = {r["key"]: r for r in funnel}
    out = []
    t, d = by.get("tu_pull_share"), by.get("du_app_share")
    if t and d and t.get("said") and d.get("said"):
        out.append(f"From pull to loan, on different bases: {t['said']}, and {d['said']}.")
    if {"shows", "priced", "vs_only"} <= set(by):
        out.append(f"VS4 shows on at least {_floor(by['shows']['share'])} of Fannie's {_month(month)} loans, prices {_one(by['priced']['share'])}, and at most {_one(by['vs_only']['share'])} are VS4 only." if readable else f"VS4 shows on at least {_floor(by['shows']['share'])} of Fannie's {_month(month)} loans and prices {_one(by['priced']['share'])}.")
    return " ".join(out) or None


def checks(score_mix, weeks, before, lenders, bands, inputs):
    """Do the totals tie to score_mix, and are the private files there? Warn only."""
    out = []

    def check(key, label, ok, detail):
        out.append({"view": "check", "key": key, "label": label, "pass": bool(ok), "detail": detail})

    lost = [k for k in INPUT_WORDS if "{" in ((inputs.get(k) or {}).get("text") or "{").replace("{share}", "").replace("{price}", "")] + [k for k in INPUT_SHARES if not 0 < ((inputs.get(k) or {}).get("value") or 0) <= 1 or not inputs[k].get("label") or not inputs[k].get("text")]
    check("inputs", "The first screen's private file is missing or thin" if lost else "The first screen's private file is there, with all its rows", not lost, f"{INPUTS.name}: these rows are gone or could not be read, so what rests on them stays off: {', '.join(lost)}." if lost else f"{INPUTS.name}: every row read.")
    head = {r["agency"]: r for r in score_mix if r["view"] == "month" and r.get("headline")}
    whole = {r["agency"]: r for r in score_mix if r["view"] == "all"}
    total = next((r for r in lenders if r.get("total")), None)
    for prefix, agency, gse in GSES:
        if agency in whole:
            c = counts(whole[agency])
            w = [x for x in [*weeks, *before] if x["agency"] == agency]
            got = (sum(x["n"] for x in w), sum(x["vo"] for x in w))
            check(f"week_{prefix}", f"{gse}: the weeks tie to score_mix", got == (c["n"], c["vo"]), f"{got} against {(c['n'], c['vo'])}")
        if agency in head and total:
            c = counts(head[agency])
            got = (total[f"{prefix}_n"], total[f"{prefix}_vo"], total[f"{prefix}_priced"])
            check(f"lender_{prefix}", f"{gse}: the lenders tie to score_mix", got == (c["n"], c["vo"], c["priced"]), f"{got} against {(c['n'], c['vo'], c['priced'])}")
    for prefix, agency, gse in GSES:
        if agency in head:
            r = head[agency]
            check("second_scores" if agency == "FNMA" else f"second_scores_{prefix}", f"{gse}'s month shows both scores on {BOTH_FLOOR:.0%} or more of its loans, and a FICO on {ONE_SIDE:.0%} or more of those it prices on VS4", shows_second(r), f"It shows both on {_one(both_share(r))}, and a FICO on {_one((r.get('both_vs_share') or 0) / r['vs4_priced_share']) if r.get('vs4_priced_share') else 'none'} of those it prices on VS4. If a month-end file dropped them, every share here that rests on a second score moves with it, not only this card's.")
    for prefix, agency, gse in GSES:
        gone = blanked(score_mix, agency)
        check(f"second_scores_past_{prefix}", f"{gse}'s months behind the headline show second scores", not gone, f"{_and([_month(m) for m in gone])} at {gse}: too few second scores, and the weeks and charts still hold those loans." if gone else "Each shows them.")
    thin = thin_gse(head)
    check("gse_thin", "Both GSEs' files reach the month", not thin, f"{'Freddie' if thin == 'FHLMC' else 'Fannie'} holds under {GSE_THIN:.0%} of the month's loans, so nothing here speaks for both GSEs in it until its files catch up." if thin else "Each holds enough of the month's loans.")
    if "FNMA" in head:
        c, r = counts(head["FNMA"]), head["FNMA"]
        check("band", "Fannie: the score bands tie to score_mix", sum(b["vo"] for b in bands) == c["vo"], f"{sum(b['vo'] for b in bands)} against {c['vo']}")
        check("level", f"Fannie shows under {ALMOST_NONE:.0%} VS4 only", r["vs_only_share"] < ALMOST_NONE, f"It shows {_one(r['vs_only_share'])}. Check that a month-end file has not dropped second scores before reading this as lenders dropping FICO.")
    return out


def ties_words(month, early, other, left):
    """Why the weeks and the month's count differ, and the month's loans that neither counts. None with nothing to say."""
    m = _month(month)
    said = ", and ".join(t for t in (f"{early:,} of {m}'s came before the week of {_day(WEEK_FROM)}" if early else None, f"{other:,} of the weeks' are in other issue months" if other else None) if t)
    parts = (f"At Fannie, the weeks and {m}'s count are not the same loans: {said}." if said else None, f"Another {left:,} of Fannie's {m} loans show VS4 and no FICO but carry no Pricing Indicator, so they are left out." if left else None)
    return " ".join(t for t in parts if t) or None


def card(con, score_mix, through, inputs, names, final=False, final_fh=False):
    """vs4_only's rows, and what the first screen needs of them. final, final_fh: Fannie's and Freddie's month-end files for the month are in."""
    months = {r["agency"]: r for r in score_mix if r["view"] == "month" and r.get("headline")}
    al, fn, fh = months.get("All"), months.get("FNMA"), months.get("FHLMC")
    month = al["start"] if al else None
    lead = _small_lead(con)
    name = names.get(lead, lead) if lead else None
    weeks, before = _weeks(con, lead, month)
    lasts = {a: d.isoformat() for a, d in con.execute("SELECT agency, max(first_intraday_date) FROM loans WHERE first_intraday_date IS NOT NULL GROUP BY 1").fetchall()}
    thin = thin_gse(months)
    lenders, bands = (_lender_rows(con, month, names), _bands(con, month, lead)) if month else ([], [])
    funnel = _funnel(inputs, fn, month)
    fweeks = [w for w in weeks if w["agency"] == "FNMA"]
    so_far, far_fh, far_all = "" if final else " so far", "" if final_fh else " so far", "" if final and final_fh else " so far"
    say, gse = [], []
    t = next((r for r in lenders if lead and r.get("id") == lead), None)
    matters = False
    readable = bool(fn and shows_second(fn))
    files_tag = None if readable or not fn else "May say more about the files than about lenders dropping FICO"
    big = None
    if fn:
        c = counts(fn)
        matters = bool(readable and t and c["vo"] and t["fn_vo"] / c["vo"] >= LEAD_MATTERS)
        big = next((r for r in lenders if r.get("id") and r["id"] != lead and readable and c["vo"] and r["fn_vo"] * 2 >= c["vo"]), None)  # the lender behind most of the count, when it is not the small one
        m = _month(month)
        gse.append({"view": "gse", "key": "fnma", "order": 0, "label": "Fannie", "number": _one(fn["vs_only_share"]), "what": f"{c['vo']:,} of {c['n']:,} {m}-issued loans{so_far}{', too few to set beside Freddie' if thin == 'FNMA' else ''}", "n": c["n"], "vo": c["vo"], "share": fn["vs_only_share"], "tag": files_tag})
        said = f"{NAME}: {_one(fn['vs_only_share'])} of Fannie's {m}-issued loans{so_far}, where {c['vo']:,} of {c['n']:,} show VS4 and no FICO."
        if not readable:
            why = why_files(fn, "this count")
            said = f"{said} {why[0].upper()}{why[1:]}."
        if big:
            said += f" {big['fn_vo']:,} of them are {big['short']}."
        if matters and c["n"] > t["fn_n"]:
            rest = (c["vo"] - t["fn_vo"]) / (c["n"] - t["fn_n"])
            said += f" {t['fn_vo']:,} of them are {name}{', a small lender' if t['fn_n'] < SMALL_LENDER * c['n'] else ''}. Without it, about {_one(rest)}."
            gse.append({"view": "gse", "key": "fnma_ex", "order": 1, "label": f"Fannie without {name}", "number": _one(rest), "what": f"{c['vo'] - t['fn_vo']:,} of {c['n'] - t['fn_n']:,} loans", "n": c["n"] - t["fn_n"], "vo": c["vo"] - t["fn_vo"], "share": rest})
        say.append(("lead", said))
        said = week_words(fweeks, c["vo"], name)
        past = blanked(score_mix)
        if said:
            say.append(("weeks", said if readable and not past else f"{said} These counts rest on the same files, so they may say more about the files than about lenders dropping FICO." if not readable else f"{said} {_and([_month(m) for m in past])}'s files at Fannie show too few second scores, so these counts may say more about the files than about lenders dropping FICO."))
        first = next((w for w in fweeks if w["first"]), None)
        if first:
            covers = [f"{_whole(w['cover'])} at {label}" for _, agency, label in GSES for w in weeks if w["agency"] == agency and w["first"] and w.get("cover") is not None and w["cover"] < 0.95]  # this sits over each GSE's chart, so each its own
            say.append(("first", f"{first['label']}: the first week most loans could show both scores{', ' + _and(covers) if covers else ''}."))
        said = trend_words(fweeks, inputs, month, name) if readable and not past else None
        if said:
            say.append(("trend", said))
    if fh:
        c = counts(fh)
        gse.append({"view": "gse", "key": "fhlmc", "order": 2, "label": "Freddie", "number": _one(fh["vs_only_share"]), "what": f"{c['vo']:,} of {c['n']:,} loans{far_fh}{', too few to set beside Fannie' if thin == 'FHLMC' else ''}", "n": c["n"], "vo": c["vo"], "share": fh["vs_only_share"],
                    "tag": "Likely a gap in what its files show, not confirmed" if freddie_gap(fh, fn, lenders, lead) else "May say more about the files than about lenders dropping FICO" if not shows_second(fh) else None})
    if al and not thin:
        c = counts(al)
        gse.append({"view": "gse", "key": "all", "order": 3, "label": "Both GSEs", "number": _one(al["vs_only_share"]), "what": f"{c['vo']:,} of {c['n']:,} loans{far_all}", "n": c["n"], "vo": c["vo"], "share": al["vs_only_share"], "tag": files_tag})
    fh_said = thin_words(thin, months, lasts) if thin == "FHLMC" else freddie_words(fh, fn, None if thin else al, lenders, lead, name, far_fh, far_all) if readable or not fn else None
    if thin == "FNMA":
        fh_said = f"{fh_said} {thin_words(thin, months, lasts)}" if fh_said else thin_words(thin, months, lasts)
    for key, said in (("lenders", keeps_words(lenders) if readable else None), ("pull", funnel_words(funnel, month, readable) if month else None), ("freddie", fh_said), ("bands", band_words(bands, name if matters else None) if readable else None),
                      ("allowed", _say(inputs, "vs4_allowed", month)), ("why_rare", (_say(inputs, "vs4_why_rare", month) or _say(inputs, "vs4_why_rare_fha_open", month)) if readable and fn["vs_only_share"] < ALMOST_NONE else None)):
        if said:
            say.append((key, said))
    early, other = sum(b["vo_head"] for b in before if b["agency"] == "FNMA"), sum(w["vo"] - w["vo_head"] for w in fweeks)
    if fn:
        left = con.execute(f"SELECT count(*) FROM loans WHERE agency = 'FNMA' AND issue_month = DATE '{month}' AND vs4 IS NOT NULL AND classic_fico IS NULL AND pricing_indicator IS NULL").fetchone()[0]
        said = ties_words(month, early, other, left)
        if said:
            say.append(("ties", said))
    gap = freddie_gap(fh, fn, lenders, lead)
    if thin == "FHLMC" and not gap:  # its files stopped short of this month, which says nothing of the weeks the charts still draw: go by the latest month both GSEs reach
        earlier = {}
        for r in score_mix:
            if r["view"] == "month" and r["start"] < month and r["agency"] != "All" and r["loans"] >= HEADLINE_MIN / 2:
                earlier.setdefault(r["start"], {})[r["agency"]] = r
        last = max((m for m, rs in earlier.items() if len(rs) == 2), default=None)
        if last:
            gap = freddie_gap(earlier[last]["FHLMC"], earlier[last]["FNMA"], _lender_rows(con, last, names), lead)
    rows = [{"view": "meta", "month": month, "final": final, "final_fh": final_fh, "through": through.isoformat(), "week_from": WEEK_FROM, "lead_id": lead, "lead_label": name, "name": NAME, "fh_tag": "Likely a gap in what its files show, not confirmed" if gap else None}, *gse, *weeks, *before, *lenders, *bands, *funnel]
    rows += [{"view": "sentence", "key": k, "order": i, "text": s} for i, (k, s) in enumerate(say)]
    rows += checks(score_mix, weeks, before, lenders, bands, inputs)
    return rows, {"month": month, "final": final, "fn": fn, "fh": fh, "al": al, "far_fh": far_fh, "far_all": far_all, "gap": freddie_gap(fh, fn, lenders, lead), "gap_chart": gap, "funnel": funnel, "lenders": lenders, "lead": t, "name": name, "matters": matters, "bands": bands, "readable": readable, "lasts": lasts, "big": big, "thin_said": thin_words(thin, months, lasts) if thin else None}


# ---- the first screen ----


def moved(rows, since):
    """What moved the latest month and the months since `since`. rows: adoption at agency All in month order. The month: a reversal is named only if the shift between lenders is most of the change and the months just before it fell by at least half as much. Since then: the same lenders are named only if they hold SINCE_MOST of the change, the shift about zero only within MIX_ZERO and a tenth of it, since the reader can add them up."""
    rows = [r for r in rows if r["month"] > since and r.get("d_total") is not None and r.get("d_mix") is not None]
    if not rows:
        return None, None
    last = rows[-1]
    total, new, within, mix = last["d_total"], last["d_new"], last["d_within"], last["d_mix"]
    run = []
    for r in reversed(rows[:-1]):
        if r["d_mix"] >= 0:
            break
        run.insert(0, r)
    fall = -sum(r["d_mix"] for r in run)
    back = mix > 0 and bool(run) and mix >= MIX_MOST * abs(total) and fall >= MIX_REVERSE * mix
    so_far = "" if last.get("final") else " so far"
    verb = lambda v, up, down: f"{up if v >= 0 else down} {_pts(v)}"  # noqa: E731
    if mix >= 0:
        shift = f"{_pts(mix)} was loans shifting {'back ' if back else ''}toward them"
    else:
        shift = f"{_pts(mix)} came off as loans shifted away from them"
    reverse = ""
    if back:
        how = "" if mix >= fall or _pts(mix) == _pts(fall) else "most of " if mix >= fall / 2 else "part of "
        reverse = f", reversing {how}a {_pts(fall)}-point fall in {_and([_month(r['month']) for r in run])}"
    using = "more" if within >= 0 else "less"
    month_line = (f"Of {_month(last['month'])}'s {_pts(total)}-point {'rise' if total >= 0 else 'fall'}{so_far}, new lenders {verb(new, 'added', 'took off')}, "
                  f"the same lenders using it {using} {verb(within, 'added', 'took off')}, and {shift}{reverse}.")
    if len(rows) < 2:
        return month_line, None
    st, sw, sm, sn = (sum(r[k] for r in rows) for k in ("d_total", "d_within", "d_mix", "d_new"))
    if st > 0 and sw >= SINCE_MOST * st:
        rest = "with the shift between lenders about zero" if abs(sm) <= min(MIX_ZERO, 0.1 * abs(st)) else f"with the shift between lenders {verb(sm, 'adding', 'taking off')}"
        return month_line, f"Since {_month(since)} it is the same lenders using it more: up {_pts(sw)} points, {rest}."
    parts = f"the same lenders {verb(sw, 'added', 'took off')}, the shift between lenders {verb(sm, 'added', 'took off')}, new lenders {verb(sn, 'added', 'took off')}"
    return month_line, f"Since {_month(since)}, {'up' if st >= 0 else 'down'} {_pts(st)} points: {parts}."


def adoption_row(adoption, series, sellers, monthly, adopters, since, keeps_it, closing_fee, inputs, whole_keeps=True):
    """The adoption row, its small picture and its words."""
    rows = sorted((r for r in adoption if r["agency"] == "All"), key=lambda r: r["month"])
    base = {"key": "adoption", "label": "Adoption at Fannie and Freddie", "cap": "Priced on VS4 by issue month, and outside the two largest"}
    if not rows:
        return {**base, "number": None, "line": TOO_FEW}, [], []
    last, prior = rows[-1], rows[-2] if len(rows) > 1 else None
    so_far = "" if last.get("final") else " so far"
    m = _month(last["month"])
    by_gse = {r["agency"]: r for r in adoption if r["month"] == last["month"]}
    thin = thin_gse(by_gse, "scored_loans")
    whose = whose_words(thin, by_gse, "scored_loans")
    top = sorted((r for r in sellers if r.get("level") == "seller" and r.get("vs4_loans")), key=lambda r: (-r["vs4_loans"], r["id"]))[:2]
    here = {r["id"]: r for r in monthly if r.get("level") == "seller" and r["agency"] == "All" and r["month"] == last["month"]}
    named = {r["id"]: r for r in sellers if r.get("level") == "seller"}
    v_all = sum(r["vs4"] for r in here.values())
    pair = [here[r["id"]] for r in top if r["id"] in here]
    names = _and([r["short"] for r in top]) if top else None
    share = sum(r["vs4"] for r in pair) / v_all if v_all and len(pair) == 2 else None
    say = []
    was = ""
    if prior:
        was = f", {_versus(last['vs4_share'], prior['vs4_share'], _one)} {_one(prior['vs4_share'])} in {_month(prior['month'])}"
    said = f"{_one(last['vs4_share'])} of {m}'s loans{so_far}{f', {whose},' if thin else ''} were priced on VS4{was}."
    if share is not None and share >= TWO_OF_IT:
        said += f" {names} are {_whole(share)} of those loans, and they use it on about {_whole(pair[0]['vs4_share'])} and {_whole(pair[1]['vs4_share'])} of their own."
    say.append(("level", said))
    if last.get("active_share"):
        n, s = last["active_sellers"], last["active_share"]
        was_n = was_s = ""
        if prior:
            was_n = f", {_versus(n, prior['active_sellers'], str)} {prior['active_sellers']}"
            was_s = f", {_versus(s, prior['active_share'])} {_whole(prior['active_share'])}"
        say.append(("inside", f"Inside adopting lenders: {n} {_plural(n, 'lender')} priced a loan on VS4 in {m}{was_n}. They hold {_whole(s)} of loans{was_s}, and use it on {_whole(last['vs4_share'] / s)} of those loans."))
    new_ids = [r["id"] for r in adopters if r["agency"] == "All" and r.get("first_any") == last["month"]]
    made = sorted(((here[i]["vs4"], named.get(i, {}).get("short", i)) for i in new_ids if i in here), key=lambda x: (-x[0], x[1]))
    said = None
    if len(made) == 1:
        said = f"New lenders: {made[0][1]} had a first VS4 loan in {m}, with {made[0][0]:,}, and holds {_one(last.get('new_share_any') or 0)} of loans."
    elif made:
        few = sum(1 for v, _ in made if v <= FEW)
        said = f"New lenders: {len(made)} had a first VS4 loan in {m} and {'holds' if len(made) == 1 else 'hold'} {_one(last.get('new_share_any') or 0)} of loans"
        if few == len(made) and len(made) > 1:
            said += f", and all made {FEW} or fewer."
        elif few and few == len(made) - 1:
            said += f", but {few} of them made {FEW} or fewer. {made[0][1]}, with {made[0][0]:,}, is the exception."
        elif few:
            said += f", {few} of them with {FEW} or fewer; {made[0][1]} made the most, {made[0][0]:,}."
        else:
            said += "."
    elif prior:
        said = f"New lenders: none had a first VS4 loan in {m}."
    outside = next((r for r in series if r["period"] == "month" and r["agency"] == "All" and r["start"] == last["month"]), None)
    if outside and outside.get("ex_top2") is not None:
        said = f"{said + ' ' if said else ''}Everyone outside {outside['excluded']} uses it on {_one(outside['ex_top2'])} of their loans."
    if said:
        say.append(("new", said))
    month_line, since_line = moved(rows, since)
    if month_line:
        say.append(("moved", f"{month_line} {since_line}" if since_line else month_line))
    if closing_fee == 0 and keeps_it and whole_keeps:
        said = _say(inputs, "adoption_fico", last["month"])
        if said:
            say.append(("fico", said))
    lead = f"{names} are {_whole(share)} of these loans" if share is not None and share >= TWO_OF_IT else None
    stay = f"since {_month(since)} the rise is the same lenders using VS4 more" if since_line and " it is the same lenders " in since_line else None
    if stay and (last.get("d_total") or 0) > 0 and " shifting back toward them" in month_line:
        stay += f", though most of {m}'s rise{so_far} is loans shifting back toward them"
    line = ", and ".join(t for t in (lead, stay) if t)
    line = f"{line[0].upper()}{line[1:]}." if line else month_line or TOO_FEW
    tail = _say(inputs, "adoption_line_tail", last["month"]) if closing_fee == 0 and keeps_it and whole_keeps and line != TOO_FEW else None
    if tail:
        line += f" {tail}"
    pics = []
    for i, r in enumerate(rows[-PIC_MONTHS:]):
        s = next((x for x in series if x["period"] == "month" and x["agency"] == "All" and x["start"] == r["month"]), {})
        pics.append({"key": "adoption", "order": i, "x": r["month"], "label": _month(r["month"])[:3], "v": r["vs4_share"], "text": _one(r["vs4_share"]), "outside": s.get("ex_top2"), "open": not r.get("final"), "what": f"Share of the month's loans priced on VS4; outside {s.get('excluded') or 'the two largest'}, the same among their loans"})
    return {**base, "number": _one(last["vs4_share"]), "number_value": last["vs4_share"], "unit": "share", "what": f"of {m}'s loans{so_far} priced on VS4, {whose}, by issue month", "line": line, "month": last["month"]}, pics, say


def pics_of(c):
    return [{"key": "vs4_only", "order": r["order"], "x": r["key"], "label": r["label"], "v": r["share"], "text": r["text"], "what": r["what"], "only": r.get("only")} for r in c["funnel"] if r["key"] != "tu_pull_share"]  # the pull figure stays in the card's sentence, off the picture


def funnel_cap(c):
    """What the small picture's bars are shares of, and the limit on "at most": it counts loans, not pulls."""
    du = next((r for r in c["funnel"] if r["key"] == "du_app_share"), None)
    du_words = du["label"].split("'s ", 1)[-1] if du else None  # the private label's words after the possessive
    at = f"Fannie's {_month(c['month'])} loans"
    said = f"VS4's share: {du_words}, then {at}" if du else f"VS4's share of {at}"
    return f'{said}. "At most" counts loans, not FICO pulls cut earlier on a loan that still shows a FICO'


def freddie_clause(c, market_size):
    """The row's one sentence on Freddie and both GSEs, so "at Fannie" does not stand for the whole. The likely gap only under the card's own guard, FICO's revenue only from the follow table's own row. With one GSE's files stopped short of the month, only that."""
    if c.get("thin_said"):
        return f" {c['thin_said']}"
    fh, al = c.get("fh"), c.get("al")
    if not fh or not al:
        return ""
    head = f"Freddie's {_one(fh['vs_only_share'])}{c['far_fh']} is most likely a gap in what its files show, not confirmed" if c.get("gap") else f"Freddie shows {_one(fh['vs_only_share'])}{c['far_fh']}"
    both = f"at both GSEs together the most is {_one(al['vs_only_share'])}{c['far_all']}"
    rev = next((r["gse_rev_text"] for r in market_size if r.get("view") == "follow" and r.get("key") == "today_both" and r.get("gse_rev_low") is not None), None)
    return f" {head}; {both}, which would be {rev} of FICO's revenue." if rev else f" {head}; {both}."


def vs4_row(c, inputs, market_size=()):
    """The VS4-only row and its small picture, which is the card's funnel."""
    base = {"key": "vs4_only", "label": NAME}
    fn = c["fn"]
    if not fn:
        return {**base, "number": None, "line": TOO_FEW}, []
    n = counts(fn)
    m = _month(c["month"])
    so_far = "" if c["final"] else " so far"
    base |= {"cap": funnel_cap(c), "number": _one(fn["vs_only_share"]), "number_value": fn["vs_only_share"], "unit": "share", "what": f"of Fannie's {m}-issued loans{so_far} show VS4 and no FICO, the most that can be VS4 only there", "month": c["month"]}
    if not c["readable"]:
        return {**base, "line": f"{n['vo']:,} of {n['n']:,} {m} loans{so_far} at Fannie show VS4 and no FICO, but {why_files(fn)}."}, pics_of(c)
    line = f"{n['vo']:,} of {n['n']:,}"
    if fn["vs_only_share"] < ALMOST_NONE:
        line = f"Almost none: {line}"
    if c.get("big"):
        line += f", {c['big']['fn_vo']:,} of them at {c['big']['short']}"
    if c["matters"]:
        line += f", {c['lead']['fn_vo']:,} of them at {c['name']}{', a small lender' if c['lead']['fn_n'] < SMALL_LENDER * n['n'] else ''}"
    line += "."
    line += freddie_clause(c, market_size)
    tail = (_say(inputs, "vs4_line_tail", c["month"]) or _say(inputs, "vs4_line_window", c["month"])) if keep_fico(c["lenders"]) else None
    if tail:
        line += f" {tail}"
    return {**base, "line": line}, pics_of(c)


def market_row(market_size):
    """Rest of the market, whole from market_size (market.py), so the first screen and its tab never disagree."""
    base = {"key": "market", "label": "Rest of the market", "cap": "Share of first-lien loans"}
    o = next((r for r in market_size if r.get("view") == "overview"), None)
    if not o:
        return {**base, "cap": None, "number": None, "line": next((r["text"] for r in market_size if r.get("view") == "sentence" and r.get("key") == "lead"), "Sizes are held back: the weekly report says why.")}, [], []
    pics = [{"key": "market", "order": r["order"], "x": r["key"], "label": r["label"], "v": r["value"], "n": r["n"], "text": _one(r["value"]), "what": r["what"]} for r in market_size if r.get("view") == "overview_pic"]
    said = {r["key"]: r["text"] for r in market_size if r.get("view") == "sentence"}
    say = [("fha_when", said["fha_when"])] if said.get("fha_when") else []  # the row's own line says the reach
    return {**base, "number": o["big"], "number_value": o["big_value"], "unit": o["big_unit"], "what": o["big_what"], "line": o["line"], "month": None}, pics, say


def book_of(rates, row, meta):
    """The lender group behind "mostly": its loans times its midpoint hold BOOK_SHARE of the row's, on the same side as the row with its methods' range clear of zero, and LENDER_APART from every other group, and the rate engine's own guard (meta.lender_rates) names it. None otherwise."""
    if not meta.get("lender_rates") or not row.get("dot_raw") or abs(row["dot_raw"]) < 1:
        return None
    groups = [g for g in rates if g.get("view") == "lender" and g.get("scope") == "group" and not g.get("not_like_for_like") and g.get("same_fico_dot") is not None]
    whole = row["dot_raw"] * row["n"]
    held = [(g["same_fico_mid"] * g["same_fico_n"] / whole, g) for g in groups if g.get("same_fico_mid") is not None]
    if not held:
        return None
    share, g = max(held, key=lambda x: x[0])
    lo, hi = g.get("same_fico_lo"), g.get("same_fico_hi")
    clear = lo is not None and hi is not None and (hi < 0 if row["dot_raw"] < 0 else lo > 0)
    apart = all(abs(g["same_fico_dot"] - o["same_fico_dot"]) >= LENDER_APART for o in groups if o is not g)
    return g if share >= BOOK_SHARE and clear and apart and g["label"] in meta["lender_rates"] else None


def _whose(lasts, since):
    """Whose files reach a window that opens on since: both GSEs', or one's alone."""
    fn, fh = (lasts or {}).get("FNMA"), (lasts or {}).get("FHLMC")
    return "Fannie only" if fh and fn and fh < since <= fn else "Freddie only" if fh and fn and fn < since <= fh else "both GSEs"


def rate_row(rates, rules, fees, lenders, keeps_it, note_rate, inputs, top_share=None, closing_fee=0, lasts=None):
    """The rate row: is there a rate difference, then dollars per score or executed rate, each clause under its guard."""
    base = {"key": "rate", "label": "Rate", "cap": "VS4 less FICO, with the 95% range"}
    row_of = lambda key: next((r for r in rates if r.get("view") == "row" and r.get("key") == key), None)  # noqa: E731
    f, c = row_of("same_fico"), row_of("same_number")
    meta = next((r for r in rates if r.get("view") == "meta"), {})
    if not f or f.get("sentence") in (None, TOO_FEW) or f.get("dot") is None:
        return {**base, "number": None, "line": TOO_FEW}, [], []
    read = f["sentence"].startswith("About")
    size, side = abs(f["dot"]), "lower" if f["dot"] < 0 else "higher"
    book = book_of(rates, f, meta) if read else None
    zero = read and _holds_zero(f)
    if read and size <= BARELY:
        line = f"Barely: about {size:g} bp {side} at the same FICO"
    elif read:
        line = f"About {size:g} bp {side} at the same FICO"
    elif f["sentence"] == NO_DIFF:
        line = "No visible difference at the same FICO"
    else:
        line = "Not clearly different from zero at the same FICO"
    if book:
        line += f", mostly {book['label']}"
    if zero:
        line += ", and zero is not ruled out"
    line += "."
    a, b = keeps(lenders)
    say = []
    ends = _out95(f["tl"], f["th"]) if f.get("tl") is not None and f.get("th") is not None else None
    money = ""
    if read and note_rate and size:
        money = f", about ${abs(_payment(note_rate + f['dot'] / 100) - _payment(note_rate)):,.0f} a month on ${PAYMENT_BALANCE:,}"
    since = f", {f['sub'].split(', ', 1)[1]}" if ", " in (f.get("sub") or "") else ""
    answer = "Barely, so far." if read and size <= BARELY else f"About {size:g} bp, so far." if read else "Not clearly, so far."
    said = f"Is there a rate difference? {answer}"
    if read:
        said += f" Same FICO: about {size:g} bp {side}{money}, on about {_hundred(f['n'])} VS4 loans showing a FICO{since}, against FICO loans of the same lender, channel, week first disclosed and score."
    else:
        said += f" Same FICO: {f['sentence'][0].lower()}{f['sentence'][1:-1]}, on about {_hundred(f['n'])} VS4 loans showing a FICO{since}."
    if ends:
        said += f" Zero is not ruled out (95% range {_range(*ends)})" if zero else f" 95% range {_range(*ends)}"
        said += f", and most of these rates were likely set before {_day(GRID_CHANGE)} ended the LLPA's {VS_OFFSET}-point markdown on VS4." if meta.get("offset_tail") else "."
    if book:
        others = sorted((g for g in rates if g.get("view") == "lender" and g.get("scope") == "group" and not g.get("not_like_for_like") and g.get("same_fico_dot") is not None and g is not book), key=lambda g: g["same_fico_dot"])
        each = ", ".join(f"{g['label']} {_signed(g['same_fico_dot'])}" for g in others)
        said += f" By lender: {book['label']} {_signed(book['same_fico_dot'])}, {each}."
    crossing = next((r for r in rates if r.get("view") == "behind" and r.get("key") == "crossing"), None)
    says_cost = read and f["dot"] > 0 and not zero  # the same-FICO gap itself says VS4 costs more, so nothing here may say it does not
    if c and (c.get("sentence") or "").startswith("About") and c.get("dot"):
        within = f" (95% range {_range(*_out95(c['tl'], c['th']))})" if c.get("tl") is not None and c.get("th") is not None else ""
        cross = f", so a VS4 720 gets about the rate of a FICO {720 - _five(crossing['value'])}" if crossing and crossing.get("value") and crossing["value"] > 0 and c["dot"] > 0 else ""
        means = " It does not say VS4 costs more." if c["dot"] > 0 and not says_cost else ""
        said += f" Same score number{', loans first disclosed ' + c['sub'].rsplit(', ', 1)[1] if ', from ' in (c.get('sub') or '') else ''}: about {abs(c['dot']):g} bp {'higher' if c['dot'] > 0 else 'lower'}{within}{cross}.{means}"
    say.append(("difference", said))
    said = None
    if a and b and keeps_it is not None:  # None: the month's files do not show second scores, so they say nothing either way
        sa, sb = a["fn_priced_fico"] / a["fn_priced"], b["fn_priced_fico"] / b["fn_priced"]
        if keeps_it:
            said = f"Dollars per score or executed rate? On funded loans it does not look like dollars per score at {a['short']} or {b['short']}: {_at_least(min(sa, sb))} of their VS4-priced Fannie loans show a FICO"
            below = {r["scope"]: r for r in rules if r.get("view") == "curve" and r.get("key") == "lt0" and r.get("cohort") == "latest"}
            ra, rb = below.get(ROCKET), below.get(UWM)
            if ra and rb and min(ra["loans"], rb["loans"]) >= MIN_PRICED and max(ra["vs4_share"], rb["vs4_share"]) <= RARE_BELOW:
                said += f", and they almost never use VS4 when it is below FICO ({_one(ra['vs4_share'])} and {_one(rb['vs4_share'])}, {_whose(lasts, ra['latest_from'])}, loans first disclosed from {_day(ra['latest_from'])})"
            cost = _say(inputs, "rate_cost_said")
            said += f". The limit on that: {cost}, and no file shows pulls before funding." if cost else ". No file shows pulls before funding."
        else:
            said = f"Dollars per score or executed rate? {a['short']} shows a FICO on {_one(sa)} of its VS4-priced Fannie loans and {b['short']} on {_one(sb)}, so funded loans no longer rule out dollars per score."
    follows = {r["key"]: r for r in rates if r.get("view") == "follows_score"}
    fits = lambda scope: bool(follows.get(f"{scope}|vs4", {}).get("guard") and follows.get(f"{scope}|fico", {}).get("guard"))  # noqa: E731
    option = {r["scope"]: r for r in fees if r.get("view") == "option"}
    cards = {r["key"]: r for r in rates if r.get("view") == "lender" and r.get("scope") == "card"}
    retail, other, got = follows.get("rocket_retail|vs4"), cards.get(UWM), None
    if UWM in option and option[UWM]["fee_fico_bp"] != option[UWM]["fee_best_bp"]:
        o = option[UWM]
        got = (o["fee_fico_bp"] - o["fee_actual_bp"]) / (o["fee_fico_bp"] - o["fee_best_bp"])
    bits = []
    fits_retail = bool(retail and fits("rocket_retail"))
    not_other = bool(other and other.get("same_fico_dot") is not None and got is not None and got >= SAVING and not fits("uwm") and abs(other["same_fico_dot"]) <= SMALL_GAP and other.get("same_fico_lo") is not None and other.get("same_fico_hi") is not None and other["same_fico_lo"] <= 0 <= other["same_fico_hi"])
    if fits_retail:
        bits.append(f"Executed rate fits {retail['label']}, where the rate follows whichever score priced the loan")
    if not_other:
        lead = "it does not yet fit" if bits else "Executed rate does not yet fit"
        moves = f"moves about {abs(other['same_fico_dot']):g} bp" if other["same_fico_dot"] else "barely moves"  # a gap that rounds to zero is not "about 0 bp"
        bits.append(f"{lead} {other['label']}, which collects {_whole(got)} of the LLPA saving while its note rate {moves}, so the saving goes to points, credits, insurance or margin, and these files cannot say which")
    if bits:
        joined = "; ".join(bits)
        said = f"{said} {joined}." if said else f"Dollars per score or executed rate? {joined}."
    if keeps_it:  # the row and the sentence above share these guards
        line += f" On funded loans, {a['short']} and {b['short']} do not look to be choosing on dollars per score: {_at_least(min(a['fn_priced_fico'] / a['fn_priced'], b['fn_priced_fico'] / b['fn_priced']))} of their VS4-priced Fannie loans show a FICO{', so FICO still gets paid' if closing_fee == 0 else ''}."
        line += f" Executed rate fits {retail['label']}, not yet {other['label']}." if fits_retail and not_other else f" Executed rate fits {retail['label']}." if fits_retail else f" Executed rate does not yet fit {other['label']}." if not_other else ""
    if said:
        say.append(("dollars_or_rate", said))
    fico = _say(inputs, "rate_fico") if keeps_it and top_share is not None else None
    if fico:
        said = _fill(fico, "share", _whole(top_share))
        if said:
            say.append(("fico", said))
    pics = []
    for i, (r, label) in enumerate(((f, "Same FICO"), (c, "Same score number"))):
        if r and r.get("dot") is not None:
            lo, hi = _out95(r["tl"], r["th"]) if r.get("tl") is not None and r.get("th") is not None else (None, None)
            pics.append({"key": "rate", "order": i, "x": r["key"], "label": label, "dot": r["dot"], "tl": lo, "th": hi, "n": r["n"], "text": f"{_signed(r['dot'])} bp", "what": f"VS4 less FICO, bp of note rate, with its 95% range, on about {_hundred(r['n'])} VS4 loans"})
    old_rule = " (most rates likely set before that day's LLPA change)" if since and meta.get("offset_tail") else ""
    window = f", on loans first disclosed {c['sub'].rsplit(', ', 1)[1]}," if c and ", from " in (c.get("sub") or "") else ""
    gloss = f". {_signed(c['dot'])} bp{window} means a VS4 720 gets about the rate of a FICO {720 - _five(crossing['value'])}, not that VS4 costs more" if c and (c.get("sentence") or "").startswith("About") and c.get("dot") and c["dot"] > 0 and not says_cost and crossing and crossing.get("value") and crossing["value"] > 0 else ""
    return {**base, "cap": f"{base['cap']}{gloss}", "number": f"{_signed(f['dot'])} bp", "number_value": f["dot"], "unit": "bp", "what": f"VS4-priced against FICO-priced loans, same FICO score, lender, channel and week first disclosed{since}{old_rule}, note rate only", "line": line, "month": None}, pics, say


def price_row(assumptions, fees):
    """FICO's price against what keeping FICO is worth: the LLPA saved by holding both scores, over the scores a funded loan takes at each number of credit pulls, plus VS4's own price. The LLPA dollars go in one sentence, marked for their labelled place on the Rate tab."""
    a = {r["key"]: r["value"] for r in assumptions if r.get("value") is not None}
    base = {"key": "price", "label": "Price", "cap": "The most a FICO score can cost before keeping it stops paying"}
    price = a.get("price_per_score")
    if price is None:
        return {**base, "number": None, "line": TOO_FEW}, [], []
    vs_price, fee = a.get("vs_price", 0), a.get("closing_fee", 0)
    base |= {"number": usd_price(price), "number_value": price, "unit": "usd", "what": f"a FICO score today{f', plus {usd_price(fee)} per borrower per score on a funded loan' if fee else ''}; a VS4 score is about {usd_price(vs_price)}", "line": TOO_FEW, "month": None}
    opt = next((r for r in fees if r.get("view") == "option" and r.get("key") == "All"), None)
    if not opt or opt["loans"] < MIN_BOTH or opt["fee_vs_bp"] <= opt["fee_best_bp"] or not a.get("bureaus") or not a.get("borrowers_per_loan"):
        return base, [{"key": "price", "order": 0, "x": "today", "label": "Today", "v": price, "ref": True, "text": f"{usd_price(price)} today", "what": "Dollars a FICO score"}], []
    keep = (opt["fee_vs_bp"] - opt["fee_best_bp"]) / 1e4 * opt["avg_upb"]
    per_pull = a["bureaus"] * a["borrowers_per_loan"]
    be = {p: max((keep - per_pull * fee) / (per_pull * p) + vs_price, 0) for p in PULL_CASES}  # the fee is due once on the funded loan, whatever the pulls
    most = ", ".join(f"${be[p]:.2f} at {p}" for p in PULL_CASES[1:])
    pays = f"keeping FICO pays up to about ${be[PULL_CASES[0]]:.2f} a score at {PULL_CASES[0]} credit pulls per funded loan, {most}, if the lower LLPA from holding both scores is worth its full value to the lender{f' and the {usd_price(fee)} fee is due on a loan that keeps FICO' if fee else ''}"
    if min(be.values()) <= price <= max(be.values()):
        line = f"Close to the point where dropping FICO starts to pay: {pays}."
    elif price < min(be.values()):
        line = f"Below the point where dropping FICO starts to pay: {pays}."
    else:
        line = f"Past the point where keeping FICO pays: {pays}."
    pics = [{"key": "price", "order": i, "x": str(p), "label": f"{p} pulls", "v": round(be[p], 2), "ref": False, "text": f"${be[p]:.2f}", "what": "Dollars a FICO score at which keeping FICO stops paying, at this many credit pulls per funded loan"} for i, p in enumerate(PULL_CASES)]
    pics.append({"key": "price", "order": len(PULL_CASES), "x": "today", "label": "Today", "v": price, "ref": True, "text": f"{usd_price(price)} today", "what": "Dollars a FICO score"})
    say = [("working", f"Having FICO as well as VS4 is worth about ${keep:,.0f} a loan in LLPA on average, on {opt['loans']:,} loans showing both scores.", "rate")]
    return {**base, "line": line}, pics, say


def said_gse_q3(score_mix: list[dict], own: dict | None) -> dict | None:
    """The tracker's quarter by issue month beside the GSEs' own figure, for the statements table (Step 1). It speaks of a difference only when both GSEs sit outside that figure's rounding, by loans and by balance."""
    if not own or own.get("value") is None or not own.get("from_month"):
        return None
    quarter = {r["agency"]: r for r in score_mix if r.get("view") == "quarter" and r.get("start") == own["from_month"]}
    al, fn, fh = quarter.get("All"), quarter.get("FNMA"), quarter.get("FHLMC")
    if not (al and fn and fh) or any(r.get("months") != 3 or not r.get("complete") for r in (al, fn, fh)):
        return None
    v = own["value"]
    shares = [r[k] for r in (fn, fh) for k in ("vs4_priced_share", "vs4_priced_upb_share")]
    one = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    head = (f"By issue month here, VS4 priced {one(al['vs4_priced_share'])} of Q{(int(own['from_month'][5:7]) - 1) // 3 + 1} loans "
            f"(Fannie Mae {one(fn['vs4_priced_share'])}, Freddie Mac {one(fh['vs4_priced_share'])}), {one(al['vs4_priced_upb_share'])} by balance")
    if all(v - ROUNDED <= s < v + ROUNDED for s in shares):
        tail = f", which rounds to the GSEs' own about {v * 100:.0f}%."
    elif all(s < v - ROUNDED for s in shares) or all(s >= v + ROUNDED for s in shares):
        tail = f", against the GSEs' own about {v * 100:.0f}%. They round to a whole percent and count on their own basis; the cause of the difference is not established."
    else:
        tail = f". The GSEs report about {v * 100:.0f}% on their own basis."
    return {"view": "said_check", "key": "gse_q3", "text": head + tail}


def dated_words(through, lasts):
    """The data's last day, and each GSE's when they differ, so a GSE whose files stop earlier does not read as covered to the later day."""
    fn, fh = lasts.get("FNMA"), lasts.get("FHLMC")
    if fn and fh and fn != fh:
        return f"Data through {_day(fn, True)} at Fannie, {_day(fh)} at Freddie."
    return f"Data through {_day(through.isoformat(), True)}."


def slice_note(score_mix, gap):
    """The Overview chart's words on its VS4-only slice at both GSEs, while Freddie holds most of it and the card calls Freddie's share a likely gap in its files, or while a month behind the headline at Fannie does not show second scores."""
    past = [r["start"] for r in score_mix if r["view"] == "month" and r["agency"] == "FNMA" and r["loans"] >= HEADLINE_MIN and not shows_second(r)]
    if past:
        return f'{_and([_month(m) for m in past])} at Fannie shows too few second scores, so "{NAME}" there may say more about the files than about lenders dropping FICO.'
    if not gap:
        return None
    count = lambda agency: sum((r.get("vs_only_share") or 0) * r["loans"] for r in score_mix if r["view"] == "week" and r["agency"] == agency)  # noqa: E731
    return f'Most of "{NAME}" here is Freddie\'s, most likely a gap in what its files show, not confirmed.' if count("FHLMC") > 0.5 * count("All") else None


def screen(more, c, through, inputs, since, note_rate=None):
    """front's rows."""
    assumptions = more.get("assumptions", [])
    closing_fee = next((r["value"] for r in assumptions if r.get("key") == "closing_fee"), None)
    price = next((r["value"] for r in assumptions if r.get("key") == "price_per_score"), None)
    keeps_it = keep_fico(c["lenders"]) if c["readable"] else None
    both = sum(b["both"] for b in c["bands"])
    top_share = c["bands"][-1]["both"] / both if both >= MIN_BOTH else None
    built = [adoption_row(more.get("adoption", []), more.get("series", []), more.get("sellers", []), more.get("seller_monthly", []), more.get("adopters", []), since, keeps_it, closing_fee, inputs, all_keep(c["lenders"])),
             (*vs4_row(c, inputs, more.get("market_size", [])), []),
             market_row(more.get("market_size", [])),
             rate_row(more.get("rates", []), more.get("rules", []), more.get("fees", []), c["lenders"], keeps_it, note_rate, inputs, top_share, closing_fee, c["lasts"]),
             price_row(assumptions, more.get("fees", []))]
    if (built[4][0].get("line") or "").startswith("Past the point"):  # the price row says keeping FICO no longer pays, so "the rate story protects FICO's units" stays off
        built[3] = (built[3][0], built[3][1], [s for s in built[3][2] if s[0] != "fico"])
    frame = _say(inputs, "front_frame") if closing_fee == 0 and price is not None else None
    out = [{"view": "meta", "through": through.isoformat(), "dated": dated_words(through, c["lasts"]), "line": _fill(frame, "price", usd_price(price)) if frame else None, "lead": c["name"], "month": c["month"], "slice_note": slice_note(more.get("score_mix", []), c.get("gap_chart"))}]
    for order, (row, pics, say) in enumerate(built):
        key = row["key"]
        out.append({"view": "row", "order": order, "go": GO[key], **row})
        out += [{"view": "pic", **x} for x in pics]
        for i, line in enumerate(say):
            out.append({"view": "sentence", "row": key, "order": i, "key": line[0], "text": line[1], "place": line[2] if len(line) > 2 else None})
    said = said_gse_q3(more.get("score_mix", []), inputs.get("gse_own_q3_share"))
    if said:
        out.append(said)
    return out


def build_datasets(con, more: dict, since: str) -> dict[str, list[dict]]:
    """Runs last in aggregate.build: reads the rows built before it, and scw (scores.py) and entity_names (lenders.py). since: MIX_START, the month "since" counts from."""
    through = con.execute("SELECT max(first_intraday_date) FROM loans").fetchone()[0]
    if through is None:
        return {"vs4_only": [], "front": []}
    names = dict(con.execute("SELECT id, short FROM entity_names").fetchall())
    inputs = load_inputs()
    head = next((r["start"] for r in more.get("score_mix", []) if r["view"] == "month" and r.get("headline") and r["agency"] == "All"), None)
    mix = {r["agency"]: r for r in more.get("score_mix", []) if r["view"] == "month" and r.get("headline")}
    finals = {r["agency"] for r in more.get("adoption", []) if r["month"] == head and r.get("final") and (mix.get(r["agency"]) or {}).get("loans", 0) >= 0.95 * (r.get("scored_loans") or 0)}  # a month-end file whose loans have no intraday record stay out of the card's count, so that count is still "so far"
    rows, c = card(con, more.get("score_mix", []), through, inputs, names, "FNMA" in finals, "FHLMC" in finals)
    note_rate = con.execute("SELECT avg(orig_rate) FROM loans WHERE score_model = 'V' AND pricing_indicator IS NOT NULL AND classic_fico IS NOT NULL AND coalesce(loan_term, 360) = 360").fetchone()[0]
    return {"vs4_only": _pad(rows), "front": _pad(screen(more, c, through, inputs, since, note_rate))}
