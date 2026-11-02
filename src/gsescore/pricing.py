"""Rate engine: how a VS4 loan's note rate compares with comparable FICO loans, by three methods, for site/data/rates.json (dashboard only).

Sample: 30-year fixed loans priced on Classic FICO or VS4 with a score and an LTV, first disclosed from WEEKLY_START and closed from CLOSE_FROM (closing.py), in every
issue month, since the reads go by week first disclosed and closing month. A rate is set at lock; those two dates stand in for it. A score that shows is a fact and one
that does not is unknown, so a VS4 loan showing no FICO has no read at its FICO. Rocket's correspondent channel is out of every all-lender row, both sides, and has its own row.
The not_like_for_like flag on it is a rule of the tab, with its reason computed in meta.rc_reason.

LLPA flags: reference/llpa.csv at the loan's own LTV and purpose, on the grid in force since GRID_CHANGE, wherever it was issued (0 in FEE_WAIVED programs). They say which loans
are compared, not what caused a gap: same LLPA and lower LLPA need both scores to show; step at stake is VS4 640 to 819 where VS4 less 20 lands a higher LLPA.

Reads, each covering the row's VS4 loans that method can reach:
  cell5   plain same-cell mean, weighted by VS4 loans. Cell: lender, channel, closing month, week first disclosed, GSE, purpose, LTV band, 5-point score band (at same FICO each
          side's FICO; at same number the VS4 number against the FICO). Errors by influence function.
  tier    the same with one LLPA tier in place of the 5-point band, the bottom tier in 20-point bands since it spans everything under 640.
  model   mean of per-loan gaps, on loans with one: the loan's rate less what a fit of FICO loans gives it at a score. One fit per lender and channel with MIN_OWN+ FICO training
          loans and a VS4 loan, the pooled fit for the rest, trained outside a one-in-five hold-out. Below an own fit's lowest FICO band with MIN_BAND+ loans there is no
          comparison; above its highest, that band stands in. gap_fico at the FICO shown, gap_number at the VS4 number, gap_less20 at VS4 less 20.
Errors are clustered: lender x week on all-lender rows; on cut and lender rows the widest of lender x week, lender x channel x week and lender x closing month.

  rates  view meta      one row: shape (RATES_SHAPE, which the page checks), dates, loan counts, answer, stamp and stamp_more, rc_reason, sample, the lines beside Milliman's statement, and the guarded sentences printed around the charts and in the folds; number_caption is number_blend and number_why joined.
         view row       same_fico, lower_llpa, same_llpa, same_llpa_low, same_number: printed dot and range (printed()), thin line (tl, th: the estimate's 95% range from _thin_mid(), resampling lender-channel groups with their loan weights), every read behind them, and the sentence (answer_sentence()). Under its floors a row keeps its reads and prints no dot, range or money. money prints only in the quote.
         view answer    the answer in lines (order, key, text): lead, same_fico, same_llpa, same_number; meta.answer is the same lines joined. The page prints same_number on the second card.
         view limit     the limits, each computed: selected under the lead; note_rate, rests_on under the chart; same_loans, line, past in the first fold; ranges, left_out, method, thin, match, book, rebuilt in the second; grid for the workbook.
         view line      Rocket's switch point: the step in the rate where the pick flips, the same test at lines where nothing switches, and a scan of every such line.
         view past      the rate past Rocket's switch point where the LLPA does not change on either grid, beside UWM and FICO loans at lenders that rarely use VS4.
         view steps     from the raw gap to the same number, both sides issued from GRID_CHANGE, plain cells.
         view same_number  by closing month and whether the old rule would raise the LLPA, with the three methods' dot and range and the share of the month in the chart; by issue period, by score band, by VS4 minus FICO, with 20 points off VS4, and the fade line. Under MIN_ROW matched loans a row keeps only its counts.
         view fico_gap  same FICO by VS4 minus FICO, in the fields of a same-number gap band.
         view equivalent  the FICO that pays the same rate, by 20-point VS4 band, loans issued from GRID_CHANGE, beside the FICO shown at lenders that rarely use VS4.
         view lender    by lender and channel (scope group) and by seller with MIN_ROW+ VS4 loans (scope card), and against FICO loans showing a VS4. Figures print only on MIN_ROW+ matched loans.
         view cut       same-LLPA gap by LTV, size, FICO band and purpose, in the same grammar as view row; description, not findings.
         view check     four build checks, warn only; check_warnings() words them for the weekly report.
         view milliman  VS4 less 20 against FICO on Milliman's window, on its loans first disclosed from WEEKLY_START, on Rocket and UWM loans issued from GRID_CHANGE, and on Milliman's window with its plainer cells.
         view follows_score  whether the rate moves with the score used, on loans showing both, in all and by purpose, at Fannie and by lender, and with the LLPA of the score used held (scopes refi_llpa, purchase_llpa): the regressions printed as a sentence.
         view llpa_rate bp by lender and channel where the LLPA is lower and where it is the same, the reads of view lender, for the LLPA fold and the workbook's Fees sheet; no rate figure above the fold reads it.
         view quote     lines to quote, each standing alone when pasted.
         view behind    one row per figure that exists only in words, with the reads behind it, for the workbook; the page reads none of them.
Sentences here are templates: every number and every named book in them comes from the data, under a guard. Findings live only in the git-ignored JSON.
A sentence that sits in a list may open with a short head ending in a colon or a question mark: the page bolds it and the workbook prints it as plain words.
"""
from calendar import month_name
from datetime import date
from types import SimpleNamespace

import numpy as np

from .closing import closing_month
from .fee_grid import FEE_WAIVED, load_grid

# The portal's intraday history starts Jul 1, 2026, and a loan is republished for up to ~3 weeks (90th percentile 20 days), so weeks before this would count June disclosures as new.
WEEKLY_START = "2026-07-20"
BOTH_START = "2026-10-19"  # the Pricing Indicator, and both scores, are disclosed from here
GRID_CHANGE = "2026-10-01"  # MBS issued from here pay one fee grid whichever score priced the loan
VS_OFFSET = 20  # before that, FICO's fee tiers applied to VS4 at this many points higher
GRID_MATRIX = "2026-09-30"  # the date of Fannie Mae's matrix that reference/llpa.csv was checked against
CLOSE_FROM = "2026-04-01"  # seasoned loans closed earlier carry rates from other years
MONTHS_FROM = "2026-06-01"  # closing months read by month
FADE_CLOSE = "2026-11-01"  # closing dates are monthly, so closings from Oct 15 on are read from the first month wholly past it
ANNOUNCED = "2026-09-29"  # FHFA announces the move to one pricing grid (reference/statements.csv)
RATES_CHANGED = "2026-10-31"  # the day these reads replaced the earlier rate figures
RATES_SHAPE = 2  # the rows' shape: the page refuses any other, so a page and a file that do not fit say so and print nothing
MILLIMAN = ("2026-05-01", "2026-08-01")  # closed and issued, the window of its published read
ROCKET, UWM = "rocket-mortgage", "united-wholesale-mortgage"
CHANNEL_LABELS = {"R": "Retail", "B": "Broker", "C": "Correspondent"}
PURPOSE_LABELS = {"P": "Purchase", "C": "Cash-out refinance", "R": "No cash-out refinance"}
RATE_MULT = 5  # a common rule of thumb: 5 bp of upfront price is about 1 bp of note rate
LAMBDA = 10.0
PASSES = 300  # a cap, and in practice what stops the fits, so results repeat
TOL = 2e-6
MIN_N = 20  # too few FICO loans to fit below this
MIN_OWN = 300  # FICO loans a lender and channel needs to be fitted on its own
MIN_BAND = 5  # FICO loans a 5-point band needs to count as inside a fit's support
MIN_ROW = 100  # a row under this many VS4 loans, or this many matched on a cell read, stays blank
THIN_WEEKS = 8  # lender-weeks: fewer reads as rough, or thin
WEEK_MIN = 5  # loans a lender-week needs to count: a lender-week with one stray loan is not a week of data
ANSWER_N, ANSWER_WEEKS = 1000, THIN_WEEKS  # below either, the answer function says too few
NO_VISIBLE = 3  # bp: a range holding zero and within this of it reads as no visible difference
RANGE_HALF = 4  # bp: the printed rule uses half points while the methods sit within this, whole points past it
NO_LIKE = 0.1  # under this share of a row's VS4 loans in cells with a comparable FICO loan, it has almost none
SEED, DRAWS = 20261031, 200_000  # the thin line's resampling
PRICED_K, PRICED_DRAWS = tuple(range(0, 65, 5)), 2000  # points off VS4 the crossing reads; its resampling
PAYMENT_BALANCE, PAYMENT_MONTHS = 350_000, 360
CHECK_LOOKALIKE, CHECK_CELLS, CHECK_RARE = 1.5, 3.0, 2.0  # bp
CHECK_RATE = (2.0, 12.0)  # a note rate outside this, in percent, is counted by the fourth check
RARE_SHARE, RARE_N, RARE_ABOVE = 0.05, 100, 20  # at most this share of loans on VS4; this many loans in all; VS4 this far above FICO
RARE_BESIDE = MIN_ROW  # under this many loans, a lender outside the test's rule is not named beside it
RARE_BORROWERS = -3.0  # bp: at or below this, the test says a high VS4 goes with a lower rate at such a lender even on FICO loans
RARE_CHANNEL = 50  # under this many loans, a lender's channel is not printed beside its read in the test
TOP_SHARE = 0.3  # from this share of a test's loans, one lender is named in words
NARROW_BASE = 0.75  # from this share of VS4 loans, the top two lenders are a narrow base
LENDER_APART = 5.0  # bp: a same-FICO gap between lender groups under this is too small to call, the page's own rule on chart 4
REFI_APART = 0.2  # how far apart refinances' shares must sit for the lender comparison to name them
FOLLOWS_N, FOLLOWS_GROUP_N = 1000, 300  # loans a fit needs: pooled scopes, then Fannie and lender groups
FOLLOWS_RATIO_FANNIE = 1.5  # how many times the other score's slope the used score's must be on Fannie refinances, which have too few loans for the full test
FOLLOWS_LEAN = 1.0  # bp per 20 points: with the LLPA held, a used slope this far above the other's has not lost its lean, however wide its error
TOP_FLAT, EXPECT_SHARE = -1.0, 0.25  # bp per 20 points of FICO in the top LLPA tier: at or above this, rates have stopped falling with the score; the share of the same-LLPA row that must sit there before the page says how much to expect
NO_STAKE_VS, NO_STAKE_LTV = 780, 60  # the test of the same-number chart's second line: VS4 from here to 819, or LTV this or under
EQ_BAND, EQ_RUNS_HIGH = "720-739", 5  # the band the equivalent's caption names; how many points above that band's FICO it must read at lenders that rarely use VS4
EQ_FLAT = 2.0  # bp per 20 points: under this the rate barely moves with the score, so read bp and not the FICO
UNSETTLED = 3.0  # bp: a band whose three methods spread this far is unsettled
LOW_RATE, RC_APART = 5.5, 0.1  # the low rate rc_reason counts loans at, in percent; how far apart Rocket correspondent's two shares at it must sit for it to say they differ
LINE_CUT, LINE_H, LINE_N, LINE_PASSES = 20, 15, 500, 1000  # Rocket's switch point; the points read each side of it; loans the sentence needs; the passes that let the main rows converge
LINE_CLEAR = LINE_CUT + LINE_H - 1  # how far up FICO the LLPA must hold for none to be at stake anywhere in the window
LINE_FICO, LINE_VS4 = (-20, -10, 0, 5), (35, 45, 55)  # lines where nothing switches, in VS4 minus FICO, read on FICO loans and on VS4 loans, printed row by row
SCAN_FICO, SCAN_VS4, SCAN_MIN = (-40, 5), (35, 75), 20  # the same, every line from low to high, on FICO loans and on VS4 loans; lines the sentence needs
PAST_LO, PAST_HI, PAST_NEAR = 25, 49, 19  # past the switch point, VS4 this far above FICO, against FICO loans with VS4 0 to this far above
T975 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.16, 2.145, 2.131, 2.12, 2.11, 2.101, 2.093, 2.086, 2.08, 2.074, 2.069, 2.064, 2.06, 2.056, 2.052, 2.048, 2.045, 2.042)  # Student's t at 97.5%, from 1 degree of freedom
SCORE_CUTS = [640, 660, 680, 700, 720, 740, 760, 780]  # LLPA credit score buckets
SCORE_LABELS = ["639 or less", "640-659", "660-679", "680-699", "700-719", "720-739", "740-759", "760-779", "780+"]
LTV_CUTS = [30, 60, 70, 75, 80, 85, 90, 95]  # LLPA LTV buckets; each cut is the top of its bucket
LTV_LABELS = ["30 or less", "30.01-60", "60.01-70", "70.01-75", "75.01-80", "80.01-85", "85.01-90", "90.01-95", "Over 95"]
SIZE_CUTS = [100e3, 150e3, 200e3, 250e3, 300e3, 350e3, 400e3, 450e3, 500e3, 600e3, 700e3, 806.5e3]
DTI_CUTS = [20, 30, 36, 40, 45, 50]
SEGMENT_SIZE = ([150e3, 250e3, 400e3, 600e3], ["Under $150k", "$150k-250k", "$250k-400k", "$400k-600k", "$600k+"])
FICO_CUT = [("under580", "FICO under 580", 0, 579), ("580-639", "FICO 580-639", 580, 639), ("640-779", "FICO 640-779", 640, 779), ("780+", "FICO 780+", 780, 850)]
GAP_BANDS = [("1-19", "VS4 1 to 19 above FICO", 1, 19), ("20-39", "VS4 20 to 39 above FICO", 20, 39), ("40+", "VS4 40+ above FICO", 40, 1000)]
VS_BANDS = [(lo, lo + 19) for lo in range(640, 800, 20)]  # the equivalent's 20-point VS4 bands
EX_LOW = 540  # lowest FICO band the equivalent's curve reads
# Score bands in the fits: anything under 505 or at 825 and up shares an end band.
S_LO, S_HI = 500, 825
N5 = (S_HI - S_LO) // 5 + 1
N20 = len(SCORE_CUTS) + 1
BAND_TIER = np.searchsorted(SCORE_CUTS, S_LO + 5 * np.arange(N5) + 2, side="right")
CENTERS = S_LO + 5 * np.arange(N5) + 2.0
CELL_K = 1000  # room for a score band beside a cell code
MINUS = "−"
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
TOO_FEW = "Too few to compare yet."
NO_DIFF = "No visible difference."
NOT_CLEAR = "Not clearly different from zero."
ANSWER_WORDS = 195
MODEL_HOLDS = "occupancy, units, property type, second liens, loan size, DTI, mortgage insurance, state, first-time buyers, number of borrowers and loan program"


def _band5(score):
    return np.clip((np.asarray(score) - S_LO) // 5, 0, N5 - 1)


def _tier(score):
    return np.searchsorted(SCORE_CUTS, score, side="right")


def _tier_band(score):
    """One LLPA tier as a score band, the bottom tier, which spans everything under the first cut, in 20-point bands."""
    return np.where(score < SCORE_CUTS[0], 100 + score // 20, _tier(score))


def _num(v, places=2):
    """A number for the JSON: rounded, so parallel float noise cannot reach the file, and null where it is not a number."""
    return None if v is None or not np.isfinite(v) else round(float(v), places) + 0.0


def _mean(v):
    return float(v.mean()) if len(v) else float("nan")


def _finite(*values):
    return [float(v) for v in values if v is not None and np.isfinite(v)]


def printed(dot_raw, lo_raw, hi_raw):
    """One rule for every range across the methods: half points while the reads sit within RANGE_HALF bp of each other, whole points past that; the dot to the nearest, lo down and hi up. 95% ends have their own (_out95), and so do side reads a sentence quotes off the rows (_half_span)."""
    dot_raw, lo_raw, hi_raw = round(dot_raw, 2), round(lo_raw, 2), round(hi_raw, 2)
    step = 0.5 if hi_raw - lo_raw < RANGE_HALF else 1.0
    return (float(np.sign(dot_raw) * np.floor(abs(dot_raw) / step + 0.5) * step) + 0.0, float(np.floor(lo_raw / step) * step) + 0.0, float(np.ceil(hi_raw / step) * step) + 0.0)


def _out95(lo, hi):
    """A 95% range's ends: half points, each rounded outward."""
    return float(np.floor(round(lo, 2) * 2) / 2) + 0.0, float(np.ceil(round(hi, 2) * 2) / 2) + 0.0


def answer_sentence(n, lender_weeks, lo, hi, dot, floor=ANSWER_N):
    """One function turns a row into its sentence. floor: the matched loans it needs, if not ANSWER_N."""
    if n < floor or lender_weeks < ANSWER_WEEKS or lo is None or hi is None or dot is None:
        return TOO_FEW
    if lo <= 0 <= hi and max(-lo, hi) <= NO_VISIBLE:
        return NO_DIFF
    if hi < 0 or lo > 0:
        return f"About {abs(dot):g} bp {'lower' if hi < 0 else 'higher'}."
    return NOT_CLEAR


def _signed(x):
    """A figure in text with its sign, as a reader sees it on the chart."""
    return "0" if x == 0 else f"{'+' if x > 0 else MINUS}{abs(x):g}"


def _whole(x):
    return float(np.sign(x) * np.floor(abs(x) + 0.5)) + 0.0


def _near(x):
    """A single read in text terms, on the printed rule's half points."""
    return printed(x, x, x)[0]


def _range(lo, hi):
    return f"{_signed(lo)} to {_signed(hi)}"


def _span(values):
    """The reads' range in text under the printed rule, low to high."""
    lo, hi = min(values), max(values)
    return _range(*printed((lo + hi) / 2, lo, hi)[1:])


def _half_span(values):
    """Side reads in a sentence, off the rows: half points, low down and high up."""
    return _range(*_out95(min(values), max(values)))


def _day(iso, year=False):
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}, {d.year}" if year else f"{d:%b} {d.day}"


def _month(iso):
    return month_name[int(iso[5:7])]


def _word(n):
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)


def _plural(n, noun):
    return noun if n == 1 else f"{noun}s"


def _count(n, noun):
    return f"{n:,} {_plural(n, noun)}"


def _hundred(n):
    return f"{round(n, -2):,}" if n >= 100 else f"{n:,}"


def _five(x):
    """To the nearest 5."""
    return int(5 * np.floor(x / 5 + 0.5))


def _pct(x):
    return f"{x:.1%}" if 0 < x < 0.01 else f"{x:.0%}"


def _one_k(share):
    """The k of one in k, while that is close to the share and it is half or less; else None."""
    k = int(round(1 / share)) if share > 0 else 0
    return k if k >= 2 and share <= 0.5 and abs(1 / k - share) <= 0.05 else None


def _one_in(share, noun):
    """A share in words: one in so many while that is close and it is half or less, else the percent."""
    k = _one_k(share)
    return f"about one {noun} in {_word(k)}" if k else f"about {share:.0%} of {noun}s"


def _one_bare(share):
    """The same with no noun."""
    k = _one_k(share)
    return f"about one in {_word(k)}" if k else f"about {share:.0%}"


def _one_of_these(share, noun=" loans"):
    """The same, of the loans just named."""
    k = _one_k(share)
    return f"about one of these{noun} in {_word(k)}" if k else f"about {share:.0%} of these{noun}"


def _half_of(share):
    return "about half" if 0.45 <= share <= 0.55 else f"about {share:.0%}"


def _about(n):
    return f"About {round(n, -2):,}" if n >= 100 else f"{n:,}"


def _and(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _payment(rate):
    r = rate / 1200
    return PAYMENT_BALANCE * r / (1 - (1 + r) ** -PAYMENT_MONTHS)


def _grid():
    grid = load_grid()
    out = np.zeros((3, N20, len(LTV_CUTS) + 1))
    for p, name in enumerate(("purchase", "rate_term", "cash_out")):
        for b in range(N20):
            for lb in range(len(LTV_CUTS) + 1):
                out[p, b, lb] = grid[(name, b, min(lb, 4) if name == "cash_out" else lb)]  # the cash-out grid stops at its fifth LTV bucket
    return out


def _code(values):
    return np.unique(np.asarray(values).astype(str), return_inverse=True)[1]


def _joint(*cols):
    """One compact code per distinct combination of integer columns."""
    out = np.zeros(len(cols[0]), dtype=np.int64)
    for c in cols:
        out = np.unique(out * (int(c.max(initial=0)) + 1) + c, return_inverse=True)[1]
    return out


def _load(con):
    # Needs seller_map and seller_key from lenders.py on this connection. Ordered so the fit is repeatable.
    d = con.execute(f"""
        SELECT l.agency, l.first_intraday_date::VARCHAR AS first_date, date_trunc('week', l.first_intraday_date)::DATE::VARCHAR AS week, {closing_month('l.first_pay_date')}::VARCHAR AS close,
               l.issue_month::VARCHAR AS issue, m.id AS seller, coalesce(l.channel, '?') AS channel,
               CASE WHEN l.purpose = 'P' THEN 'P' WHEN l.purpose = 'C' THEN 'C' ELSE 'R' END AS purpose,
               coalesce(l.occupancy, '?') AS occupancy, least(coalesce(l.units, 1), 2) AS units, coalesce(l.property_type, '?') AS ptype, coalesce(l.orig_loan_amt, 0) AS amount,
               coalesce(l.dti, -1) AS dti, coalesce(l.mi_pct, 0) > 0 AS mi, coalesce(l.state, '?') AS state, coalesce(l.fthb, '?') AS fthb,
               least(coalesce(l.num_borrowers, 1), 2) AS borrowers, coalesce(l.special_program, '7') AS program, l.score_model = 'V' AS is_v, l.pricing_score AS score,
               CASE WHEN l.classic_fico BETWEEN 300 AND 850 THEN l.classic_fico ELSE -1 END AS fico,
               CASE WHEN l.vs4 BETWEEN 300 AND 850 THEN l.vs4 ELSE -1 END AS vs,
               l.ltv, coalesce(l.cltv, 0) AS cltv, l.orig_rate, hash(l.agency || l.loan_id) % 5 = 0 AS holdout
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.loan_term = 360 AND l.amort_type = 'FRM' AND l.score_model IN ('C', 'V') AND l.orig_rate > 0 AND l.pricing_score IS NOT NULL AND l.ltv IS NOT NULL
          AND l.first_intraday_date >= DATE '{WEEKLY_START}' AND {closing_month('l.first_pay_date')} >= DATE '{CLOSE_FROM}'
        ORDER BY l.agency, l.loan_id""").fetchnumpy()
    return {k: np.asarray(v) for k, v in d.items()}


def _sample(con):
    d = _load(con)
    s = SimpleNamespace(n=len(d["orig_rate"]))
    for k in ("agency", "first_date", "week", "close", "issue", "seller", "channel", "purpose"):
        setattr(s, k, d[k].astype(str))
    s.y = d["orig_rate"].astype(float)
    s.bp = s.y * 100
    s.is_v, s.holdout, s.mi = d["is_v"].astype(bool), d["holdout"].astype(bool), d["mi"].astype(bool)
    s.score, s.fico, s.vs = d["score"].astype(np.int64), d["fico"].astype(np.int64), d["vs"].astype(np.int64)
    s.amount = d["amount"].astype(float)
    s.has_f, s.has_v = s.fico > 0, s.vs > 0
    s.fic = ~s.is_v & s.has_f  # a comparator must show a FICO
    s.train = ~s.is_v & ~s.holdout
    s.rc = (s.seller == ROCKET) & (s.channel == "C")
    s.after = s.issue >= GRID_CHANGE
    s.refi = s.purpose != "P"
    s.ltvb = np.searchsorted(LTV_CUTS, d["ltv"].astype(float), side="left")
    s.pidx = np.where(s.purpose == "P", 0, np.where(s.purpose == "C", 2, 1))
    s.lp = s.ltvb + (len(LTV_CUTS) + 1) * s.pidx
    s.waived = np.isin(d["program"].astype(str), FEE_WAIVED)
    s.subfin = d["cltv"].astype(float) > d["ltv"].astype(float)
    s.sizeb = np.searchsorted(SIZE_CUTS, s.amount, side="right")
    dti = d["dti"].astype(float)
    s.dtib = np.where(dti < 0, -1, np.searchsorted(DTI_CUTS, dti, side="left")) + 1
    # Codes, so cells and fits never compare strings.
    s.c_agency, s.c_week, s.c_close = _code(s.agency), _code(s.week), _code(s.close)
    s.c_seller, s.c_channel, s.c_purpose = _code(s.seller), _code(s.channel), _code(s.purpose)
    s.c_occupancy, s.c_ptype, s.c_state, s.c_fthb, s.c_program = (_code(d[k]) for k in ("occupancy", "ptype", "state", "fthb", "program"))
    s.c_units, s.c_borrowers = d["units"].astype(np.int64), d["borrowers"].astype(np.int64)
    s.lc = _joint(s.c_seller, s.c_channel)
    s.lw = _joint(s.c_seller, s.c_week)
    s.lcw = _joint(s.c_seller, s.c_channel, s.c_week)
    s.lm = _joint(s.c_seller, s.c_close)
    s.widest = (s.lw, s.lcw, s.lm)
    s.cell = _joint(s.c_seller, s.c_channel, s.c_close, s.c_week, s.c_agency, s.c_purpose, s.ltvb)
    s.cell_f5 = s.cell * CELL_K + s.fico // 5
    s.cell_ft = s.cell * CELL_K + _tier_band(s.fico)
    s.cell_n5 = s.cell * CELL_K + s.score // 5
    s.cell_nt = s.cell * CELL_K + _tier_band(s.score)
    # The LLPA flags, on the grid in force since GRID_CHANGE.
    grid = _grid()
    fee = lambda score: np.where(s.waived, 0.0, grid[s.pidx, _tier(score), s.ltvb])  # noqa: E731
    s.fee_v, s.fee_f, s.fee_20, s.fee_near = fee(s.vs), fee(s.fico), fee(s.vs - VS_OFFSET), fee(s.fico + LINE_CLEAR)
    both = s.has_f & s.has_v
    s.tv = s.is_v & s.has_f & ~s.rc
    s.same = both & (s.fee_v == s.fee_f)
    s.lower = both & (s.fee_v < s.fee_f)
    s.stake = (s.vs >= 640) & (s.vs < 820) & (s.fee_20 > s.fee_v)
    return s


class _Fit:
    """An additive fit of FICO loans' rates on the loans at ix: each level's effect is the shrunk mean of what the others leave, as if it had LAMBDA more loans at zero."""

    def __init__(self, s, ix, factors, support):
        self.ix = ix
        self.pidx, self.lp, self.prog = s.pidx[ix], s.lp[ix], s.waived[ix].astype(np.int64)
        b5, b20 = _band5(s.score[ix]), _tier(s.score[ix])
        codes = {**factors, "s5": b5, "s5_p": b5 + N5 * self.pidx, "s20_lp": b20 + N20 * self.lp, "s5_lp": b5 + N5 * self.lp, "s20_prog": b20 + N20 * self.prog}
        sizes = {f: int(c.max()) + 1 for f, c in factors.items()} | {"s5": N5, "s5_p": N5 * 3, "s20_lp": N20 * 27, "s5_lp": N5 * 27, "s20_prog": N20 * 2}
        train = s.train[ix]
        mu, self.eff = self._backfit(s.y[ix][train], {f: c[train] for f, c in codes.items()}, sizes)
        self.base = np.full(len(ix), mu)
        for f, c in factors.items():
            self.base += self.eff[f][c]
        have = np.flatnonzero(np.bincount(b5[train], minlength=N5) >= MIN_BAND) if support else np.arange(N5)
        self.lo, self.hi = int(have.min()), int(have.max())

    @staticmethod
    def _backfit(y, codes, sizes):
        mu = float(y.mean())
        eff = {f: np.zeros(sizes[f]) for f in codes}
        den = {f: np.bincount(c, minlength=sizes[f]) + LAMBDA for f, c in codes.items()}
        r = y - mu
        for _ in range(PASSES):
            moved = 0.0
            for f, c in codes.items():
                partial = r + eff[f][c]
                new = np.bincount(c, weights=partial, minlength=sizes[f]) / den[f]
                moved = max(moved, float(np.abs(new - eff[f]).max()))
                r = partial - new[c]
                eff[f] = new
            if moved < TOL:
                break
        return mu, eff

    def at(self, rows, b5):
        """The rate this fit gives its loans at the rows at 5-point bands: none below its support, its top band above it."""
        low = b5 < self.lo
        b5 = np.clip(b5, self.lo, self.hi)
        b20, e = BAND_TIER[b5], self.eff
        lp, p, prog = self.lp[rows], self.pidx[rows], self.prog[rows]
        out = self.base[rows] + e["s5"][b5] + e["s5_p"][b5 + N5 * p] + e["s20_lp"][b20 + N20 * lp] + e["s5_lp"][b5 + N5 * lp] + e["s20_prog"][b20 + N20 * prog]
        out[low] = np.nan
        return out

    def curve(self, rows):
        return np.column_stack([self.at(rows, np.full(len(rows), k)) for k in range(N5)])


def _traits(s, ix):
    b = s.ltvb[ix]
    return {"occ_ltv": _joint(s.c_occupancy[ix], b), "units_ltv": _joint(s.c_units[ix], b), "ptype_ltv": _joint(s.c_ptype[ix], b), "subfin_ltv": _joint(s.subfin[ix].astype(np.int64), b),
            "size": _joint(s.sizeb[ix]), "dti": _joint(s.dtib[ix]), "mi": _joint(s.mi[ix].astype(np.int64)), "state": _joint(s.c_state[ix]), "fthb": _joint(s.c_fthb[ix]),
            "borrowers": _joint(s.c_borrowers[ix]), "program": _joint(s.c_program[ix]), "lp": _joint(s.lp[ix])}


def _own_factors(s, ix):
    wk, cl, ag = _joint(s.c_week[ix]), _joint(s.c_close[ix]), _joint(s.c_agency[ix])
    return {"week": wk, "close": cl, "agency": ag, "week_close": _joint(wk, cl), "purpose": _joint(s.c_purpose[ix]), "agency_week": _joint(ag, wk), **_traits(s, ix)}


def _pooled_factors(s):
    ix = np.arange(s.n)
    counts = np.bincount(s.c_seller[s.train], minlength=int(s.c_seller.max()) + 1)
    g = _joint(np.where(counts[s.c_seller] >= MIN_OWN, s.c_seller + 1, 0), s.c_channel)
    wk, cl, ag, pu = _joint(s.c_week), _joint(s.c_close), _joint(s.c_agency), _joint(s.c_purpose)
    return {"week": wk, "close": cl, "agency": ag, "sc": g, "sc_week": _joint(g, wk), "sc_close": _joint(g, cl), "sc_purpose": _joint(g, pu), "sc_agency": _joint(g, ag), **_traits(s, ix)}


def _fit_all(s):
    """Fits every loan and sets the per-loan gaps, in bp, on s."""
    counts = np.bincount(s.lc[s.train], minlength=int(s.lc.max()) + 1)
    wanted = np.flatnonzero((counts >= MIN_OWN) & (np.bincount(s.lc[s.is_v], minlength=len(counts)) > 0))
    fits = []
    for k in wanted:
        ix = np.flatnonzero(s.lc == k)
        fits.append(_Fit(s, ix, _own_factors(s, ix), True))
    s.n_own = len(fits)
    rest = ~np.isin(s.lc, wanted)
    if rest.any():  # the pooled fit is trained on every FICO loan and speaks only for loans without their own fit
        pooled = _Fit(s, np.arange(s.n), _pooled_factors(s), False)
        keep = np.flatnonzero(rest)
        pooled.ix, pooled.base, pooled.lp, pooled.pidx, pooled.prog = keep, pooled.base[keep], pooled.lp[keep], pooled.pidx[keep], pooled.prog[keep]
        fits.append(pooled)
    s.gap_fico, s.gap_number, s.gap_less20, s.gap_own = (np.full(s.n, np.nan) for _ in range(4))
    for f in fits:
        rows = np.flatnonzero(s.is_v[f.ix])
        at = f.ix[rows]
        s.gap_number[at] = s.bp[at] - f.at(rows, _band5(s.vs[at])) * 100
        s.gap_less20[at] = s.bp[at] - f.at(rows, _band5(s.vs[at] - 20)) * 100
        show = s.has_f[at]
        s.gap_fico[at[show]] = s.bp[at[show]] - f.at(rows[show], _band5(s.fico[at[show]])) * 100
        rows = np.flatnonzero(s.fic[f.ix])
        at = f.ix[rows]
        s.gap_own[at] = s.bp[at] - f.at(rows, _band5(s.fico[at])) * 100
    return fits


def _cluster_se(gap, cluster):
    """Standard error of a mean with errors clustered."""
    if len(gap) < 2:
        return float("nan")
    inv = np.unique(cluster, return_inverse=True)[1]
    g = int(inv.max()) + 1
    if g < 2:
        return float("nan")
    return float(np.sqrt((np.bincount(inv, weights=gap - gap.mean()) ** 2).sum() * g / (g - 1)) / len(gap))


def _gap(y, t, c, cell, clusters=(), cell_c=None):
    """Mean of t's loans less c's inside cells, weighted by t's loans, with errors by influence function clustered on each of clusters. cell_c: the comparators' cells, where they differ.
    g: each loan read, less its cell's comparators; a mean over any set of whole cells is that set's read."""
    c = c & ~t
    yt, yc = y[t], y[c]
    out = {"est": float("nan"), "n": 0, "pool": len(yt), "fic": 0, "cells": 0, "se": [float("nan")] * len(clusters), "g": np.full(len(y), np.nan)}
    if not len(yt) or not len(yc):
        return out
    ct, cc = cell[t], (cell if cell_c is None else cell_c)[c]
    inv = np.unique(np.concatenate((ct, cc)), return_inverse=True)[1]
    it, ic = inv[:len(ct)], inv[len(ct):]
    m = int(inv.max()) + 1
    nt, nc = np.bincount(it, minlength=m), np.bincount(ic, minlength=m)
    mc = np.bincount(ic, weights=yc, minlength=m) / np.maximum(nc, 1)
    ok = (nt > 0) & (nc > 0)
    w = int(nt[ok].sum())
    if not w:
        return out
    rt, rc = ok[it], ok[ic]
    gt = yt[rt] - mc[it[rt]]
    est = float(gt.mean())
    out["g"][np.flatnonzero(t)[rt]] = gt
    psi_t = (gt - est) / w
    psi_c = -(nt[ic[rc]] / nc[ic[rc]]) * (yc[rc] - mc[ic[rc]]) / w
    for i, k in enumerate(clusters):
        kt, kc = k[t][rt], k[c][rc]
        inv = np.unique(np.concatenate((kt, kc)), return_inverse=True)[1]
        groups = int(inv.max()) + 1
        if groups > 1:
            total = np.bincount(inv, weights=np.concatenate((psi_t, psi_c)), minlength=groups)
            out["se"][i] = float(np.sqrt((total ** 2).sum() * groups / (groups - 1)))
    out.update(est=est, n=w, fic=int(nc[ok].sum()), cells=int(ok.sum()))
    return out


def _thin_mid(r5, rt, lc):
    """95% for the estimate, from resampling lender-channel groups with their loan weights: which groups are in the read, not how many loans each has, is the error it speaks to. Each draw is the midpoint of the two cell reads, each on its own weights; a draw with no loans on one read uses the other, and a group in only one read still counts. None to redraw under two groups."""
    a, b = r5["g"], rt["g"]
    oka, okb = ~np.isnan(a), ~np.isnan(b)
    groups = np.unique(lc[oka | okb])
    size = len(groups)
    if size < 2:
        return float("nan"), float("nan")
    ia, ib = np.searchsorted(groups, lc[oka]), np.searchsorted(groups, lc[okb])
    idx = np.random.default_rng(SEED).integers(0, size, size=(DRAWS, size))
    sa, na = np.bincount(ia, weights=a[oka], minlength=size)[idx].sum(axis=1), np.bincount(ia, minlength=size)[idx].sum(axis=1)
    sb, nb = np.bincount(ib, weights=b[okb], minlength=size)[idx].sum(axis=1), np.bincount(ib, minlength=size)[idx].sum(axis=1)
    ma, mb = sa / np.maximum(na, 1), sb / np.maximum(nb, 1)
    lo, hi = np.percentile(np.where(na == 0, mb, np.where(nb == 0, ma, (ma + mb) / 2)), [2.5, 97.5])
    return float(lo), float(hi)


def _thin_groups(r5, rt, lc):
    """How many lender-channel groups a row's estimate rests on, and how many that is by weight."""
    n = np.unique(lc[~np.isnan(r5["g"]) | ~np.isnan(rt["g"])], return_counts=True)[1].astype(float)
    return len(n), float(n.sum() ** 2 / (n ** 2).sum()) if len(n) else 0.0


def _absorb(v, groups, tol, passes=PASSES):
    """Takes out several sets of fixed effects by alternating projections."""
    v = v.astype(float).copy()
    for _ in range(passes):
        moved = 0.0
        for c, den in groups:
            m = np.bincount(c, weights=v) / den
            v -= m[c]
            moved = max(moved, float(np.abs(m).max()))
        if moved < tol:
            break
    return v


def _regress(y, xs, fes, cluster, tol=1e-6, passes=PASSES):
    """Least squares of y on xs with the fixed effects fes absorbed. Coefficients and errors clustered on cluster; none where the fit cannot be read."""
    empty = [float("nan")] * len(xs)
    if len(y) <= len(xs):
        return empty, empty
    groups = [(c, np.bincount(c).astype(float)) for c in (np.unique(f, return_inverse=True)[1] for f in fes)]
    yr = _absorb(y, groups, tol, passes)
    xr = np.column_stack([_absorb(x, groups, tol, passes) for x in xs])
    if np.linalg.matrix_rank(xr) < len(xs):
        return empty, empty
    beta = np.linalg.lstsq(xr, yr, rcond=None)[0]
    inv = np.unique(cluster, return_inverse=True)[1]
    g = int(inv.max()) + 1
    if g < 2:
        return list(beta), empty
    e = yr - xr @ beta
    meat = np.column_stack([np.bincount(inv, weights=xr[:, j] * e, minlength=g) for j in range(xr.shape[1])])
    bread = np.linalg.pinv(xr.T @ xr)
    return list(beta), list(np.sqrt(np.diag(bread @ (meat.T @ meat) @ bread) * g / (g - 1)))


def _t975(df):
    """Student's t at 97.5%: a table to 30 degrees of freedom, a close formula past it. None under one."""
    if df < 1:
        return float("nan")
    return T975[df - 1] if df <= len(T975) else 1.96 + 2.4 / df


def _widest(s, gap, m):
    """The widest clustered error of the mean of gap on m."""
    ok = m & ~np.isnan(gap)
    return max(_finite(*(_cluster_se(gap[ok], k[ok]) for k in s.widest)), default=float("nan"))


def _weeks(s, m):
    return int((np.unique(s.lw[m], return_counts=True)[1] >= WEEK_MIN).sum())


def _three(cell5, tier, model):
    """A row's figures from its three methods: the midpoint of the two cell reads and the range across all three, exact and printed. Without a cell read there is no dot."""
    mid, spread = _finite(cell5, tier), _finite(cell5, tier, model)
    dot_raw = sum(mid) / len(mid) if mid else None
    lo_raw, hi_raw = (min(spread), max(spread)) if spread else (None, None)
    dot, lo, hi = printed(dot_raw, lo_raw, hi_raw) if mid else (None, None, None)
    return dot_raw, lo_raw, hi_raw, dot, lo, hi


def _matched(read5, read_tier, n):
    """A row's counts in words: how many its two exact matches reach, of how many. None with no loans."""
    if not n:
        return None
    lo, hi = sorted((read5, read_tier))
    reach = "none" if not hi else f"up to {_hundred(hi)}" if not lo else _hundred(hi) if _hundred(lo) == _hundred(hi) else f"{_hundred(lo)} to {_hundred(hi)}"
    return f"{reach} of about {_hundred(n)}"


def _fannie_mid(s, t, r5, rt):
    """The midpoint of the two cell reads on t's loans at Fannie."""
    fannie = t & (s.agency == "FNMA")
    mid = _finite(_mean(r5["g"][fannie & ~np.isnan(r5["g"])]), _mean(rt["g"][fannie & ~np.isnan(rt["g"])]))
    return sum(mid) / len(mid) if mid else None


def _label(s, names, seller, channel=None):
    """A lender's plain label, with its channel."""
    short = names.get(seller, seller)
    return f"{short} {CHANNEL_LABELS.get(channel, channel).lower()}" if channel else short


def _pools(s):
    """The reads, Rocket correspondent still in but for same_llpa_low: VS4 loans, their cells at 5 points and at one LLPA tier, and their per-loan gaps."""
    v = s.is_v & s.has_f
    return {"same_fico": (v, s.cell_f5, s.cell_ft, s.gap_fico), "lower_llpa": (v & s.lower, s.cell_f5, s.cell_ft, s.gap_fico), "same_llpa": (v & s.same, s.cell_f5, s.cell_ft, s.gap_fico), "same_llpa_low": (s.tv & s.same & (s.fico < SCORE_CUTS[-1]), s.cell_f5, s.cell_ft, s.gap_fico),
            "same_number": (s.is_v & (s.vs < 820), s.cell_n5, s.cell_nt, s.gap_number)}


def _row(s, key, order, title, sub, strong, reads, floor=ANSWER_N):
    t, c5, ct, gap = reads
    t, c = t & ~s.rc, s.fic & ~s.rc
    r5, rt = _gap(s.bp, t, c, c5, (s.lw,)), _gap(s.bp, t, c, ct, (s.lw,))
    ok = t & ~np.isnan(gap)
    model = _mean(gap[ok])
    n, weeks = int(t.sum()), _weeks(s, t)
    dot_raw, lo_raw, hi_raw, dot, lo, hi = _three(r5["est"], rt["est"], model)
    sentence = answer_sentence(min(r5["n"], rt["n"]), weeks, lo, hi, dot, floor)
    if sentence == TOO_FEW:
        dot = lo = hi = None
    tl, th = _thin_mid(r5, rt, s.lc)
    money = None
    if key == "same_number" and dot and sentence.startswith("About"):
        rate = float(s.y[t].mean())
        money = f"About ${abs(_payment(rate + dot / 100) - _payment(rate)):,.0f} a month on ${PAYMENT_BALANCE:,}"
    row = {"view": "row", "order": order, "key": key, "title": title, "sub": f"about {_hundred(n)}{sub}" if n else None, "strong": strong, "dot": dot, "lo": lo, "hi": hi, "tl": _num(tl), "th": _num(th),
           "loans": f"{_about(n)} {_plural(n, 'loan')}" if n else None, "money": money, "n": n, "read5": r5["n"], "read_tier": rt["n"], "cell5": _num(r5["est"]), "cell5_se": _num(r5["se"][0]), "tier": _num(rt["est"]), "tier_se": _num(rt["se"][0]),
           "model": _num(model), "model_se": _num(_cluster_se(gap[ok], s.lw[ok])), "model_n": int(ok.sum()), "lender_weeks": weeks, "dot_raw": _num(dot_raw), "lo_raw": _num(lo_raw), "hi_raw": _num(hi_raw),
           "fannie": _num(_fannie_mid(s, t, r5, rt)), "fannie_n": int((t & (s.agency == "FNMA")).sum()), "sentence": sentence}
    return row, r5, rt


def _read_rows(s):
    """The lead rows, in the chart's order. The row under FICO 780 is part of a row, so it takes MIN_ROW's floor, as _llpa_split()'s figure on the same loans does."""
    pools = _pools(s)
    since = f", issued from {_day(GRID_CHANGE)}" if s.after[s.tv].all() else ""
    first = np.unique(s.first_date[pools["same_number"][0] & ~s.rc])
    start = f", from {_day(str(first[0]))}" if len(first) else ""
    spec = [("same_fico", "Same FICO", f" showing a FICO{since}", True, ANSWER_N), ("lower_llpa", "of which VS4 has a lower LLPA on today's grid", "", False, ANSWER_N),
            ("same_llpa", "of which same LLPA on today's grid", "", False, ANSWER_N), ("same_llpa_low", f"of those, FICO under {SCORE_CUTS[-1]}", "", False, MIN_ROW), ("same_number", "Same score number", f" VS4 loans under 820{start}", True, ANSWER_N)]
    rows, cells = {}, {}
    for order, (key, title, sub, strong, floor) in enumerate(spec):
        rows[key], r5, rt = _row(s, key, order, title, sub, strong, pools[key], floor)
        cells[key] = (r5, rt)
    return rows, cells


def _book(s, names, rows, cells):
    """The one lender and channel carrying half or more of the same-FICO gap on all three methods, whole and at Fannie alone wherever a method reads there (MIN_ROW+ loans, 1+ bp), with its share of the loans and its reads: a closing month only with MIN_ROW+ loans, the rest only with MIN_ROW+. None if none does, or if a month it prints reads wholly against the row."""
    r5, rt = cells["same_fico"]
    f = rows["same_fico"]
    if not f["sentence"].startswith("About"):
        return None
    size = int(s.lc.max()) + 1
    shares = []
    for g in (r5["g"], rt["g"], np.where(s.tv, s.gap_fico, np.nan)):
        ok = ~np.isnan(g)
        est = _mean(g[ok])
        if not abs(est) >= 1 or est * f["dot_raw"] < 0:  # a share of next to nothing, or of the other sign, says nothing
            return None
        shares.append(np.bincount(s.lc[ok], weights=g[ok], minlength=size) / g[ok].sum())
        at = ok & (s.agency == "FNMA")
        if at.sum() >= MIN_ROW and abs(_mean(g[at])) >= 1:
            if _mean(g[at]) * f["dot_raw"] < 0:  # a share of the other sign, at Fannie as above
                return None
            shares.append(np.bincount(s.lc[at], weights=g[at], minlength=size) / g[at].sum())
    held = np.min(shares, axis=0)
    k = int(np.argmax(held))
    if held[k] < 0.5:
        return None
    t = s.tv & (s.lc == k)
    i = np.flatnonzero(t)[0]
    cell_reads = lambda m: _finite(_mean(r5["g"][m & ~np.isnan(r5["g"])]), _mean(rt["g"][m & ~np.isnan(rt["g"])]))  # noqa: E731
    reads = lambda m: cell_reads(m) + _finite(_mean(s.gap_fico[m & ~np.isnan(s.gap_fico)]))  # noqa: E731
    months, counts = np.unique(s.close[t], return_counts=True)
    closed = []
    for m in sorted(str(x) for x in months[np.argsort(-counts, kind="stable")[:2]]):
        at = t & (s.close == m)
        if at.sum() >= MIN_ROW and reads(at):
            closed.append((m, reads(at), sum(cell_reads(at)) / max(len(cell_reads(at)), 1)))
    if any((max(v) < 0 if f["dot_raw"] > 0 else min(v) > 0) for _, v, _ in closed):
        return None
    rest = s.tv & ~t
    return {"label": _label(s, names, s.seller[i], s.channel[i]), "lc": k, "share": float(t.sum() / s.tv.sum()), "closed": closed, "rest": reads(rest) if rest.sum() >= MIN_ROW else [], "weeks": _weeks_holding(s.week[t])}


def _weeks_holding(week, share=0.95):
    """The fewest latest weeks of first disclosure holding this share of the loans."""
    if not len(week):
        return 0
    weeks, counts = np.unique(week, return_counts=True)
    held = np.cumsum(counts[::-1]) / counts.sum()
    return int(np.searchsorted(held, share) + 1)


def _lender_clause(s, names, dot, shown=()):
    """The same-number read by lender and channel: at every group if 3+ sellers have MIN_ROW+ compared loans, each group's read nearest zero keeps the row's sign and half its size, and every figure on chart 4 keeps its sign; at both if the two largest keep its sign; else nothing. shown: chart 4's rows."""
    if not dot:
        return None
    t, c5, ct, _ = _pools(s)["same_number"]
    t, c = t & ~s.rc, s.fic & ~s.rc
    r5, rt = _gap(s.bp, t, c, c5), _gap(s.bp, t, c, ct)
    groups = []
    for k in np.unique(s.lc[t]):
        m = s.lc == k
        read = []
        for r in (r5, rt):
            g = r["g"][m & ~np.isnan(r["g"])]
            if len(g) >= MIN_ROW:
                read.append(float(g.mean()))
        i = np.flatnonzero(t & m)[0]
        groups.append((int((t & m).sum()), s.seller[i], s.channel[i], read))
    nearest = lambda read: min(read) if dot > 0 else -max(read)  # noqa: E731
    read = [g for g in groups if g[3]]
    if len({g[1] for g in read}) >= 3 and all(nearest(g[3]) >= abs(dot) / 2 for g in read) and all(r["same_number_dot"] is None or r["same_number_dot"] * dot > 0 for r in shown):
        return "at every lender group shown"
    two = sorted(groups, key=lambda g: (-g[0], g[1], g[2]))[:2]
    if len(two) == 2 and all(g[3] and nearest(g[3]) > 0 for g in two):
        return f"at both {_label(s, names, two[0][1], two[0][2])} and {_label(s, names, two[1][1], two[1][2])}"
    return None


def _falls(gaps):
    """Whether the same-FICO gap falls as VS4 sits further above FICO: the three bands' dots strictly, and at Fannie alone too."""
    dots, fannie = [r["dot"] for r in gaps], [r["fannie"] for r in gaps]
    if len(gaps) != len(GAP_BANDS) or None in dots or None in fannie:
        return False
    return all(a > b for a, b in zip(dots, dots[1:])) and all(a > b for a, b in zip(fannie, fannie[1:]))


def _by_gap(s, m, bands):
    """Same FICO on the VS4 loans at m, by how far VS4 sits above FICO: each band's three methods, its matched loans, its midpoint and its printed dot, none under MIN_ROW matched loans; its midpoint and matched loans at Fannie alone; and its mean LLPA gap in percent of balance, FICO's less VS4's on today's grid and on the old rule, whole and at Fannie alone."""
    c, diff, fannie = s.fic & ~s.rc, s.vs - s.fico, s.agency == "FNMA"
    out = []
    for key, label, lo, hi in bands:
        t = s.tv & m & (diff >= lo) & (diff <= hi)
        r5, rt = _gap(s.bp, t, c, s.cell_f5), _gap(s.bp, t, c, s.cell_ft)
        model = _mean(s.gap_fico[t & ~np.isnan(s.gap_fico)])
        raw, _, _, dot, _, _ = _three(r5["est"], rt["est"], model)
        out.append({"key": key, "label": label, "n": int(t.sum()), "read5": r5["n"], "read_tier": rt["n"], "cell5": _num(r5["est"]), "tier": _num(rt["est"]), "model": _num(model), "mid": _num(raw), "dot": dot if min(r5["n"], rt["n"]) >= MIN_ROW else None,
                    "fannie": _num(_fannie_mid(s, t, r5, rt)), "fannie_read5": int((fannie & ~np.isnan(r5["g"])).sum()), "fannie_read_tier": int((fannie & ~np.isnan(rt["g"])).sum()),
                    "llpa_gap": _mean(s.fee_f[t] - s.fee_v[t]), "llpa_gap_old": _mean(s.fee_f[t] - s.fee_20[t]), "fannie_n": int((t & fannie).sum()), "fannie_llpa_gap": _mean(s.fee_f[t & fannie] - s.fee_v[t & fannie]), "fannie_llpa_gap_old": _mean(s.fee_f[t & fannie] - s.fee_20[t & fannie])})
    return out


def _falls_at_fannie(bands):
    """Anything resting on the second score must hold at Fannie alone: the midpoints there fall from band to band, wherever every band can be compared there. bands: _by_gap()."""
    if any(min(r["fannie_read5"], r["fannie_read_tier"]) < MIN_ROW for r in bands):
        return True
    return all(a["fannie"] > b["fannie"] for a, b in zip(bands, bands[1:]))


def _book_grows(book, bands):
    """Whether the one lender and channel's gap grows with how far VS4 sits above FICO. bands: _by_gap() on it at GAP_BANDS[1:]. Both on MIN_ROW+ matched loans on each cell read, both dots below zero and the further one lower, each method that reads lower too, and the same at Fannie alone."""
    if not book or len(bands) != 2 or any(r["dot"] is None or min(r["read5"], r["read_tier"]) < MIN_ROW for r in bands):
        return False
    near, far = bands
    return near["dot"] < 0 and far["dot"] < 0 and far["dot"] < near["dot"] and all(near.get(m) is None or far.get(m) is None or far[m] < near[m] for m in ("cell5", "tier", "model")) and _falls_at_fannie(bands)


def _llpa_gap_rises(bands):
    """Whether the mean LLPA gap rises from band to band on today's grid and on the old rule, and at Fannie alone too wherever every band has MIN_ROW+ loans there. bands: _by_gap()."""
    rises = lambda key: all(a.get(key) is not None and b.get(key) is not None and b[key] > a[key] for a, b in zip(bands, bands[1:]))  # noqa: E731
    return rises("llpa_gap") and rises("llpa_gap_old") and (any(r.get("fannie_n", 0) < MIN_ROW for r in bands) or (rises("fannie_llpa_gap") and rises("fannie_llpa_gap_old")))


def _book_words(book, bands):
    """The one lender and channel in the answer, with its gap by band while _book_grows(), and the LLPA gap beside it while _llpa_gap_rises(). None without one."""
    if not book:
        return None
    share = _half_of(book["share"])
    grows = ""
    if _book_grows(book, bands):
        (_, _, lo, hi), (_, _, top, _) = GAP_BANDS[1:]
        grows = f", and there it grows{', as the LLPA gap does,' if _llpa_gap_rises(bands) else ''} with how far VS4 sits above FICO: about {_signed(bands[0]['dot'])} at {lo} to {hi} above and about {_signed(bands[1]['dot'])} at {top}+"
    return f"{book['label']}, {share}{'' if share == 'about half' else ' of'} these loans, carries most of it{grows}."


def _gap_line(gaps, number, book=None, at_book=(), rest=()):
    """The two figures against the gap between the scores. at_book: _by_gap() on the book at GAP_BANDS[1:]. rest: _by_gap() on everything but it at every band. First the same FICO, at the book while _book_grows() and elsewhere as the rest's printed midpoints, at Fannie too, or model reads fall, or pooled while _falls(). Then the same number: the bands rise at every step, or only the last is the highest, 1+ bp over the first. None with neither."""
    falling = lambda values: None not in values and all(a > b for a, b in zip(values, values[1:]))  # noqa: E731
    first = None
    if _book_grows(book, at_book):
        name = book["label"]
        shown = len(rest) == len(GAP_BANDS) and all(r["dot"] is not None for r in rest)
        if not shown:
            first = f"At {name}, the further VS4 sits above FICO, the lower the rate at the same FICO."
        elif falling([r["dot"] for r in rest]) and _falls_at_fannie(rest):
            first = f"The further VS4 sits above FICO, the lower the rate at the same FICO, at {name} and elsewhere."
        elif falling([r["dot"] for r in rest]):
            first = f"At {name}, the further VS4 sits above FICO, the lower the rate at the same FICO."
        elif falling([None if r["model"] is None else _near(r["model"]) for r in rest]):
            first = f"At {name}, the further VS4 sits above FICO, the lower the rate at the same FICO; elsewhere that shows only on the model."
        else:
            first = f"At {name}, the further VS4 sits above FICO, the lower the rate at the same FICO; not elsewhere."
    elif _falls(gaps):
        first = "The further VS4 sits above FICO, the lower the rate at the same FICO."
    bands = sorted((r for r in number if r["scope"] == "gapband"), key=lambda r: r["order"])
    dots = [r["dot"] for r in bands]
    second = None
    if len(bands) >= 2 and None not in dots:
        top = bands[-1]["label"].removeprefix("VS4 ").removesuffix(" FICO")
        if all(a < b for a, b in zip(dots, dots[1:])):
            second = "At the same score number it rises." if first else "At the same score number the gap rises the further VS4 sits above FICO."
        elif dots[-1] > max(dots[:-1]) and dots[-1] >= dots[0] + 1:
            second = f"At the same score number {'it' if first else 'the gap'} is highest at {top}."
    return " ".join(t for t in (first, second) if t) or None


def _split_words(split, row=None):
    """The same-LLPA row's two halves for the quote, in bp, each clause under its guard. None without both. row: the row under FICO 780, whose printed ends it quotes while it has them."""
    if not split or split["high"] is None or split["low"] is None:
        return None
    stop = ", where rates stop falling with the score," if split["flat"] else ""
    methods = f" ({_range(row['lo'], row['hi'])} across the methods)" if row and row.get("lo") is not None and row.get("hi") is not None else ""
    discount = ", so this cannot tell a discount there from none" if split["open"] else ""
    return f"about {_signed(split['high'])} bp at FICO {SCORE_CUTS[-1]}+{stop} and about {_signed(split['low'])} bp below {SCORE_CUTS[-1]}{methods}{discount}"


def _holds_zero(row):
    """Whether a row's 95% range holds zero, as it prints."""
    if row.get("tl") is None or row.get("th") is None:
        return False
    lo, hi = _out95(row["tl"], row["th"])
    return lo <= 0 <= hi


def _fannie_note(row):
    """A same-FICO finding must hold at Fannie alone, or the answer says it differs."""
    whole, fannie = row["dot_raw"], row["fannie"]
    if whole is None or fannie is None or row["sentence"] in (TOO_FEW, NO_DIFF):
        return None
    if fannie * whole < 0 or (abs(fannie) <= 1 and abs(whole) > 2):
        return f"At Fannie alone it reads {_signed(_whole(fannie))}."
    return None


def _clause(sentence, dot):
    """A row's sentence as a clause."""
    if sentence == NO_DIFF:
        return f"about {'0' if abs(dot) < 1 else _signed(dot)}"
    return sentence[0].lower() + sentence[1:-1]


def _between(s, rows):
    """Whether a VS4 loan has priced between its two scores: on one set of loans, VS4 under 820 showing a FICO, all three methods below zero at its FICO and above zero at its number."""
    if not (rows["same_fico"]["sentence"].startswith("About") and rows["same_number"]["sentence"].startswith("About")):
        return False
    t, c = s.tv & (s.vs < 820), s.fic & ~s.rc
    at_fico = _finite(_gap(s.bp, t, c, s.cell_f5)["est"], _gap(s.bp, t, c, s.cell_ft)["est"], _mean(s.gap_fico[t & ~np.isnan(s.gap_fico)]))
    at_number = _finite(_gap(s.bp, t, c, s.cell_n5)["est"], _gap(s.bp, t, c, s.cell_nt)["est"], _mean(s.gap_number[t & ~np.isnan(s.gap_number)]))
    return len(at_fico) == 3 and len(at_number) == 3 and max(at_fico) < 0 and min(at_number) > 0


def _held_ends(row, plain):
    """How far a row's figure moves with what is held equal: the lowest and the highest of its two ends and plain's two reads, the one nearer zero first. None on a row too few to compare, without all four, or where they print as one figure. plain: _method_reads()."""
    reads = _finite(*plain, row.get("lo_raw"), row.get("hi_raw"))
    if row["sentence"] == TOO_FEW or len(reads) != 4:
        return None
    near, far = sorted((min(reads), max(reads)), key=abs)
    return None if _whole(near) == _whole(far) else (near, far)


def _held(row, plain):
    """_held_ends() in words, in whole points: from few controls to the tightest match while those ends are plain's first read and the row's 5-point read, each with its own label."""
    ends = _held_ends(row, plain)
    if not ends:
        return None
    if set(ends) == {float(plain[0]), row.get("cell5")}:
        return f"from about {_signed(_whole(plain[0]))} with few controls to about {_signed(_whole(row['cell5']))} on the tightest match"
    return f"about {_signed(_whole(ends[0]))} to {_signed(_whole(ends[1]))} depending on what is held equal"


def _same_llpa_line(rows, split):
    """The same-LLPA line: the row overall, then its two halves while the split and the row under FICO 780 both read, each clause under its guard. Whether a discount below 780 is ruled out stays in the quote. split: _llpa_split()."""
    low, ll, under = rows["lower_llpa"], rows["same_llpa"], rows.get("same_llpa_low")
    if ll["sentence"] == TOO_FEW:
        return "Same LLPA: too few to compare yet."
    read = lambda r: r["sentence"].startswith("About")  # noqa: E731
    top = SCORE_CUTS[-1]
    halves = None
    if split and split["high"] is not None and split["low"] is not None and split.get("share") is not None and under and under["sentence"] != TOO_FEW:
        stop = ", where rates stop falling with the score" if split["flat"] else ""
        methods = f", with the methods running {_range(under['lo'], under['hi'])}" if under.get("lo") is not None and under.get("hi") is not None else ""
        halves = f"About {_five(split['share'] * 100)}% of these loans are FICO {top}+{stop}; below {top} it is about {_signed(split['low'])}{methods}."
    at_same = f"about {_signed(ll['dot'])}" if read(ll) else _clause(ll["sentence"], ll["dot"])
    zero = ", though zero is not ruled out" if read(ll) and _holds_zero(ll) else ""
    cause = ", which does not show the LLPA caused the gap" if read(low) and low["dot"] < 0 and ll["dot"] - low["dot"] >= 3 else ""
    return " ".join(t for t in (f"Same LLPA: {at_same}{' overall' if halves else ''}{zero}{cause}.", halves) if t)


def _answer(rows, book, clause, between, gaps=(), split=None, plain=(), at_book=()):
    """The answer as lines of (key, text), each clause under its guard. gaps: the fico_gap rows. split: _llpa_split(). plain: _method_reads(). at_book: _by_gap() on the book at GAP_BANDS[1:]. The lender clause goes only if the whole passes ANSWER_WORDS."""
    f, c = rows["same_fico"], rows["same_number"]
    read = lambda r: r["sentence"].startswith("About")  # noqa: E731
    plain_words = lambda r: "no visible difference" if r["sentence"] == NO_DIFF else _clause(r["sentence"], r["dot"])  # noqa: E731
    example = " (VS4 720 against FICO 720)"
    lead = between and read(f) and read(c) and f["dot"] < 0 < c["dot"]
    lines = []
    if lead:
        lines.append(("lead", f"About {abs(f['dot']):g} bp lower at the same FICO and about {abs(c['dot']):g} bp higher at the same score number{example}, so where both scores show, its rate has averaged between the rates of FICO loans at those two scores."))
    zero = read(f) and _holds_zero(f)
    held = _held(f, plain)
    if lead:
        first = f"zero is not ruled out, and the figure runs {held}" if zero and held else f"the figure runs {held}" if held else "zero is not ruled out" if zero else ""
    else:
        first = f"{plain_words(f)}{', though zero is not ruled out' if zero else ''}{f', and it runs {held}' if held else ''}"
    runs = f"It runs from about {_signed(gaps[0]['dot'])} at {GAP_BANDS[0][2]} to {GAP_BANDS[0][3]} above FICO to about {_signed(gaps[-1]['dot'])} at {GAP_BANDS[2][2]}+ above." if read(f) and not _book_grows(book, at_book) and _falls(gaps) else None
    most = _book_words(book, at_book)
    rest = [t for t in (runs, most, _fannie_note(f)) if t]
    if not first and rest and rest[0] != most:
        rest[0] = f"{rest[0][0].lower()}{rest[0][1:]}"
    if first or rest:
        lines.append(("same_fico", " ".join(["Same FICO:", *([f"{first}."] if first else []), *rest])))
    lines.append(("same_llpa", _same_llpa_line(rows, split)))
    number = f"{c['sentence'][:-1]} at the same score number under 820{'' if lead else example}"
    across = f", {clause}" if clause and read(c) else ""
    range_ = f" 95% range about {_range(*_out95(c['tl'], c['th']))}." if c["sentence"] != TOO_FEW and None not in (c["tl"], c["th"]) and (read(c) or c["tl"] <= 0 <= c["th"]) else ""  # beside no finding, only a range that holds zero: the methods can part while the range on the two exact matches clears it
    means = " It says a VS4 number has got the rate of a lower FICO, not that VS4 costs more." if read(c) and c["dot"] > 0 and not (read(f) and f["dot"] > 0) else ""
    if sum(len(t.split()) for _, t in lines) + len(f"{number}{across}.{range_}{means}".split()) > ANSWER_WORDS:
        across = ""
    lines.append(("same_number", f"{number}{across}.{range_}{means}"))
    return lines


def _top_two(s, names, m=None):
    """The two largest sellers of VS4 loans, by name, and their share of those loans. m: which VS4 loans, if not all, Rocket correspondent out."""
    sellers, counts = np.unique(s.seller[s.is_v & ~s.rc if m is None else m], return_counts=True)
    if not len(sellers):
        return [], float("nan")
    top = np.argsort(-counts, kind="stable")[:2]
    return [names.get(sellers[i], sellers[i]) for i in top], float(counts[top].sum() / counts.sum())


def _rocket_line(s, names):
    """Rocket's switch point: the step in the rate where the pick flips, each side free to slope, with lender, channel, week, GSE, closing month, purpose, score, LTV and traits held. VS4 less 20 equals FICO there, so the old rule predicts no step whichever score sets the rate; the same test at lines where nothing switches says how much it can see.
    Returns the rows and the sentence, None where its guards fail. Each range rests on few lender-weeks, so it uses t(G - 1) on the clustered error."""
    both = s.has_f & s.has_v & (s.seller == ROCKET) & ~s.rc
    lift = s.vs - s.fico
    clear = s.fee_f == s.fee_near
    wide = [_joint(s.c_seller, s.c_channel, s.c_week, s.c_agency), _joint(s.c_seller, s.c_channel, s.c_close), _joint(s.c_seller, s.c_channel, s.c_purpose), _joint(s.fico // 20, s.ltvb, s.c_purpose), _joint(s.fico // 5, s.c_purpose),
            s.sizeb, s.dtib, s.c_occupancy, s.c_units, s.c_ptype, s.mi.astype(np.int64), s.c_fthb, s.c_borrowers, s.c_program]

    def step(key, label, m, cut=LINE_CUT, passes=PASSES):
        at = np.flatnonzero(m & (lift >= cut - LINE_H) & (lift < cut + LINE_H))
        above = lift[at] >= cut
        est, se = float("nan"), float("nan")
        if len(at) >= MIN_ROW and min(above.sum(), (~above).sum()) >= MIN_N:  # a step needs loans on both sides of its line
            z = (lift[at] - cut).astype(float)
            beta, errors = _regress(s.bp[at], [above.astype(float), z, z * above], [f[at] for f in wide], s.lw[at], tol=1e-8, passes=passes)
            est, se = beta[0], errors[0]
        weeks = _weeks(s, at)
        t = _t975(weeks - 1)
        return {"view": "line", "key": key, "label": label, "est": _num(est), "se": _num(se), "lo": _num(est - t * se), "hi": _num(est + t * se), "n": len(at), "above": int(above.sum()), "lender_weeks": weeks}

    below = both & (lift >= LINE_CUT - 5) & (lift <= LINE_CUT - 1)
    early, late = below & (s.close <= ANNOUNCED), below & (s.close > ANNOUNCED)
    use_below, use_above = _mean(s.is_v[below]), _mean(s.is_v[both & (lift >= LINE_CUT) & (lift <= LINE_CUT + 4)])
    main = {**step("main", "At the switch point, where the LLPA would not change", both & clear, passes=LINE_PASSES), "use_below": _num(use_below, 3), "use_above": _num(use_above, 3),
            "use_below_early": _num(_mean(s.is_v[early]), 3), "use_below_early_n": int(early.sum()), "use_below_late": _num(_mean(s.is_v[late]), 3), "use_below_late_n": int(late.sum())}
    fannie = step("fannie", "The same, at Fannie alone", both & clear & (s.agency == "FNMA"), passes=LINE_PASSES)
    rows = [main, fannie, step("lower", "At the switch point, where the LLPA would fall", both & ~clear, passes=LINE_PASSES), step("all", "At the switch point, every loan", both, passes=LINE_PASSES)]

    def no_switch(cut, side, m):
        where = f"{abs(cut)} below" if cut < 0 else f"{cut} above" if cut else "level with"
        return step(f"false|{cut}", f"No switch here, {side} loans: VS4 {where} FICO", m, cut)

    rows += [no_switch(cut, "FICO", both & clear & ~s.is_v) for cut in LINE_FICO] + [no_switch(cut, "VS4", both & clear & s.is_v) for cut in LINE_VS4]
    lines = [step("", "", m, cut) for m, lo, hi in ((both & clear & ~s.is_v, *SCAN_FICO), (both & clear & s.is_v, *SCAN_VS4)) for cut in range(lo, hi + 1)]
    lines = [r for r in lines if r["est"] is not None and r["se"] is not None]
    swing = np.array([r["est"] for r in lines])
    scan = {"view": "line", "key": "scan", "label": "Every line where nothing switches", "lines": len(lines), **dict.fromkeys(("p2_5", "p97_5", "min", "max", "abs_p90", "miss_share"))}
    if lines:
        low, high = np.percentile(swing, [2.5, 97.5])
        misses = sum(r["lo"] is not None and (r["lo"] > 0 or r["hi"] < 0) for r in lines) / len(lines)
        scan.update(p2_5=_num(low), p97_5=_num(high), min=_num(swing.min()), max=_num(swing.max()), abs_p90=_num(np.percentile(np.abs(swing), 90)), miss_share=_num(misses, 3))
    rows = [{**r, "order": i} for i, r in enumerate([*rows, scan])]
    if not (np.isfinite(use_below) and np.isfinite(use_above) and use_below <= 0.2 and use_above >= 0.8 and main["n"] >= LINE_N and main["lo"] is not None):
        return rows, None
    verb = "steps" if main["lo"] > 0 or main["hi"] < 0 else "moves"
    few = ", on few weeks of loans" if main["lender_weeks"] < THIN_WEEKS else ""
    said = f"At {names.get(ROCKET, ROCKET)}'s switch point ({LINE_CUT} points above FICO): where the LLPA would not change, the rate {verb} about {_signed(_near(main['est']))} (95% range about {_range(*_out95(main['lo'], main['hi']))}{few})."
    if len(lines) >= SCAN_MIN:
        said += f" The same test at about {int(round(len(lines), -1))} other cut-offs where nothing switches swings about {_range(float(np.floor(scan['p2_5'])), float(np.ceil(scan['p97_5'])))}, so it cannot see a step under about {int(np.ceil(scan['abs_p90'] / 5) * 5)} bp."
    return rows, said


def _past(s, names):
    """The rate past Rocket's switch point where the LLPA does not change on either grid: VS4 loans well above their FICO against FICO loans near theirs, same lender, in the same cell with the same FICO band, on 5- and 20-point bands and on the model. Beside them UWM, and FICO loans at lenders that rarely use VS4, where nothing switches. A read on under MIN_ROW matched loans stays null."""
    flat = s.has_f & s.has_v & (s.fee_v == s.fee_f) & (s.fee_20 == s.fee_f)
    lift = s.vs - s.fico
    far, near = (lift >= PAST_LO) & (lift <= PAST_HI), (lift >= 0) & (lift <= PAST_NEAR)
    rocket = (s.seller == ROCKET) & ~s.rc
    who = names.get(ROCKET, ROCKET)
    rows = []
    for order, (key, label, m, side, gap) in enumerate((("rocket", who, rocket, s.is_v, s.gap_fico), ("rocket_fannie", f"{who}, at Fannie alone", rocket & (s.agency == "FNMA"), s.is_v, s.gap_fico),
                                                        ("uwm", names.get(UWM, UWM), s.seller == UWM, s.is_v, s.gap_fico), ("rare", "FICO loans at lenders that rarely use VS4", _rare(s) & ~s.rc, s.fic, s.gap_own))):
        t, c = m & flat & far & side, m & flat & near & s.fic
        r5, r20 = _gap(s.bp, t, c, s.cell * CELL_K + s.fico // 5), _gap(s.bp, t, c, s.cell * CELL_K + s.fico // 20)
        at, against = t & ~np.isnan(gap), c & ~np.isnan(s.gap_own)
        model = _mean(gap[at]) - _mean(s.gap_own[against]) if min(at.sum(), against.sum()) >= MIN_ROW else None
        rows.append({"view": "past", "key": key, "label": label, "order": order, "n": int(t.sum()), "comparators": int(c.sum()), "read5": r5["n"], "read20": r20["n"], "lender_weeks": _weeks(s, t), "thin": _weeks(s, t) < THIN_WEEKS,
                     "cell5": _num(r5["est"]) if r5["n"] >= MIN_ROW else None, "cell20": _num(r20["est"]) if r20["n"] >= MIN_ROW else None, "model": _num(model)})
    return rows


def _past_line(rows, names):
    """The rate past the switch point in words, only while it reads below zero at Rocket on 2+ cell reads, whole and at Fannie alone. UWM goes beside it while it has a cell read and a model read and reaches zero, saying so where one read is under its floor. The lenders that rarely use VS4 stay in the workbook's table."""
    by = {r["key"]: r for r in rows}
    reads = lambda r: _finite(r["cell5"], r["cell20"], r["model"])  # noqa: E731
    falls = lambda r: len(_finite(r["cell5"], r["cell20"])) == 2 and max(reads(r)) < 0  # noqa: E731
    beside = lambda r: bool(_finite(r["cell5"], r["cell20"])) and r["model"] is not None and max(reads(r)) >= 0  # noqa: E731
    rocket, uwm = by["rocket"], by["uwm"]
    if not (falls(rocket) and falls(by["rocket_fannie"])):
        return None
    who = names.get(ROCKET, ROCKET)
    out = [f"Past the switch point: at {who}, VS4 {PAST_LO} to {PAST_HI} points above FICO is about {_half_span(reads(rocket))}{', on few weeks of loans' if rocket['thin'] else ''}, against FICO loans with the same FICO and VS4 0 to {PAST_NEAR} points above it, where the LLPA is the same today and under the old rule."]
    if beside(uwm):
        out.append(f"At {names.get(UWM, UWM)} that comparison is about {_half_span(reads(uwm))}{' on two methods' if len(reads(uwm)) == 2 else ''}.")
    out.append(f"{who}'s choice of score and its higher VS4 come together, so this cannot say which.")
    return " ".join(out)


def _match_reads(s, cells):
    """Whether which loans a method reaches moves the model's read: the model's read on the loans a 5-point match finds and on the rest, with their counts, on MIN_ROW+ loans each side, 2+ bp apart. None otherwise."""
    found = ~np.isnan(cells["same_fico"][0]["g"])
    known = s.tv & ~np.isnan(s.gap_fico)
    if min((known & found).sum(), (known & ~found).sum()) < MIN_ROW:
        return None
    with_match, without = _mean(s.gap_fico[known & found]), _mean(s.gap_fico[known & ~found])
    if abs(with_match - without) < 2:
        return None
    return with_match, int((known & found).sum()), without, int((known & ~found).sum())


def _match_line(rows):
    """Which loans the two exact matches reach, in words, while a main row has loans."""
    of, number = _matched(rows["same_fico"]["read5"], rows["same_fico"]["read_tier"], rows["same_fico"]["n"]), _matched(rows["same_number"]["read5"], rows["same_number"]["read_tier"], rows["same_number"]["n"])
    if of:
        said = f"{of} same-FICO loans{f' and {number} same-number loans' if number else ''} find FICO loans to compare."
    elif number:
        said = f"{number} same-number loans find FICO loans to compare."
    else:
        return None
    return f"Which loans match: by exact match, {said}"


def _sample_line(s):
    v, f = int((s.is_v & ~s.rc).sum()), int((s.fic & ~s.rc).sum())
    return f"The sample holds {v:,} VS4 and {f:,} FICO loans{', Rocket correspondent left out' if s.rc.any() else ''}." if v and f else None


def _method_reads(s):
    """The same-FICO figure with less held: lender, channel, week, GSE and FICO only, and a simple regression. Each keeps the GSEs apart inside a lender and week, as a read across them also carries how VS4 loans split between them."""
    c = s.fic & ~s.rc
    plain = _gap(s.bp, s.tv, c, _joint(s.c_seller, s.c_channel, s.c_week, s.c_agency) * CELL_K + s.fico // 5)["est"]
    m = c | s.tv
    lc = s.lc[m]
    beta, _ = _regress(s.bp[m], [s.tv[m].astype(float)], [_joint(lc, s.c_week[m], s.c_agency[m]), _joint(lc, s.c_close[m]), _joint(lc, s.c_purpose[m]), _joint(s.lp[m], s.fico[m] // 5)], s.lw[m], tol=1e-4)
    return plain, beta[0]


def _same_loans(s, rows):
    """The same-number row's loans that show a FICO: same FICO on all three methods with its 95% range, and the same loans at the same number on their own guard. The reads and the sentence, or None."""
    t, c = s.tv & (s.vs < 820), s.fic & ~s.rc
    r5, rt = _gap(s.bp, t, c, s.cell_f5), _gap(s.bp, t, c, s.cell_ft)
    gap = _mean(s.gap_fico[t & ~np.isnan(s.gap_fico)])
    tl, th = _thin_mid(r5, rt, s.lc)
    if rows["same_number"]["dot"] is None or len(_finite(r5["est"], rt["est"], gap)) < 3 or len(_finite(tl, th)) < 2:
        return None
    dot = printed((r5["est"] + rt["est"]) / 2, min(r5["est"], rt["est"], gap), max(r5["est"], rt["est"], gap))[0]
    n5, nt = _gap(s.bp, t, c, s.cell_n5), _gap(s.bp, t, c, s.cell_nt)
    at_number = _near((n5["est"] + nt["est"]) / 2) if min(n5["n"], nt["n"]) >= MIN_ROW else None
    share = t.sum() / max((s.is_v & ~s.rc & (s.vs < 820)).sum(), 1)
    out = {"dot": dot, "t": t, "at_fico": (r5, rt, gap, tl, th), "at_number": (n5, nt, _mean(s.gap_number[t & ~np.isnan(s.gap_number)])) if at_number is not None else None}
    said = f"VS4 loans under 820 that show a FICO, {_one_bare(share)}: {f'about {_signed(at_number)} at the same number and ' if at_number is not None else ''}about {_signed(dot)} at the same FICO (95% range about {_range(*_out95(tl, th))})."
    return {**out, "text": said}


def _book_line(book):
    """The one lender and channel by closing month, and the rest. It looks smaller on later loans only while the later month's midpoint is nearer zero. None without a month to print."""
    if not book or not book["closed"]:
        return None
    few = "few weeks of loans" if book["weeks"] <= THIN_WEEKS else f"{book['weeks']} weeks of loans"
    months = book["closed"]
    how = "'s gap looks smaller on later loans" if len(months) == 2 and abs(months[1][2]) < abs(months[0][2]) else "'s gap by closing month" if len(months) == 2 else "'s gap"
    closed = " and ".join(f"{_span(v)} closed in {_month(m)}" for m, v, _ in months)
    rest = f" All others: about {_span(book['rest'])}." if book["rest"] else ""
    return f"Over time: {book['label']}{how}, on {few}: about {closed}.{rest}"


def _left_out(has_rc=True):
    """Who is out of which rows. has_rc: whether the sample holds any Rocket correspondent loan. Its reason prints on the lender card, from meta.rc_reason."""
    return f"Left out of same FICO: VS4 loans showing no FICO (unknown, not counted as having none).{' Left out of every all-lender rate row: Rocket correspondent, not like for like.' if has_rc else ''}"


def _grid_line(closed):
    """Which grid sorts the rows. closed: the share of the same-FICO loans closed by ANNOUNCED's month."""
    return f"Which grid: lower and same LLPA are sorted on the one grid in force since {_day(GRID_CHANGE)}{f'; most of these rates were likely set earlier, under the old rule that counted VS4 {VS_OFFSET} points lower' if closed > 0.5 else ''}."


def _rc_tops(s):
    """The thin line's top ends with Rocket correspondent in, same FICO, lower LLPA and same LLPA. None with none in the sample."""
    if not s.rc.any():
        return None
    pools = _pools(s)
    return {key: _thin_mid(_gap(s.bp, pools[key][0], s.fic, pools[key][1]), _gap(s.bp, pools[key][0], s.fic, pools[key][2]), s.lc)[1] for key in ("same_fico", "lower_llpa", "same_llpa")}


def _rc_back(hi, th):
    """The lower-LLPA row's thin line with Rocket correspondent back in. hi: its top end with it. th: the row's own. Nothing unless both read. Its end rounds outward."""
    if not np.isfinite(hi) or th is None:
        return ""
    return f" With Rocket correspondent back, the lower-LLPA range reaches {_signed(_out95(hi, hi)[1])}."


def _rests_on(top, share, since=None):
    """What the rows rest on: the top two lenders, a narrow base only while they hold NARROW_BASE of the loans. since: the share of VS4 loans issued from GRID_CHANGE that show a FICO, while every same-FICO loan is so issued and no earlier loan shows both scores."""
    issued = f" Same-FICO loans are about {since:.0%} of VS4 loans issued since {_day(GRID_CHANGE)}, as no earlier loan shows both scores." if since is not None else ""
    return f"{'Narrow base: ' if share >= NARROW_BASE else 'Who is in these figures: '}{_and(top)} {'are' if len(top) > 1 else 'is'} {share:.0%} of these VS4 loans.{issued}"


def _limits(s, rows, cells, book, names, line, past, loans, plain, closed, rc_tops):
    """The limits in the page's order. loans: _same_loans(), while a VS4 loan has priced between its two scores. plain: _method_reads(). closed: the share of the same-FICO loans closed by ANNOUNCED's month. rc_tops: _rc_tops()."""
    f, n = rows["same_fico"], rows["same_number"]
    point = 0.1 * 100 / RATE_MULT  # bp of rate in 0.1 of a discount point
    worth = next((r["dot"] for r in (f, n) if r["dot"]), None)
    points = float(np.floor(abs(worth) * 0.1 / point * 10 + 0.5) / 10) if worth else 0.0  # one decimal place in every state
    so = f" {_signed(worth)} bp is about {points:.1f} of a discount point." if points else ""
    out = [("selected", "Fee or score? These files cannot settle it: lenders can pick the score, sometimes after the rate is set, and lock dates do not show. So this shows where a gap sits, not what choosing VS4 is worth."),
           ("note_rate", f"Note rate only: discount points, lender credits and lock dates are not disclosed.{so}")]
    # What the rows rest on.
    top, share = _top_two(s, names)
    if top:
        since = (s.tv & s.after).sum() / (s.is_v & ~s.rc & s.after).sum() if s.tv.any() and s.after[s.tv].all() and not (s.has_f & s.has_v & ~s.after).any() else None
        out.append(("rests_on", _rests_on(top, share, since)))
    if loans:
        out.append(("same_loans", loans["text"]))
    if line:
        out.append(("line", line))
    if line and past:
        out.append(("past", past))
    out += [("ranges", "A range in bp with no label is the spread across the 3 methods, not a margin of error."), ("left_out", _left_out(bool(s.rc.any()))), ("grid", _grid_line(closed))]
    # The same-FICO figure by what is held equal.
    plain, beta = plain
    if f["lo"] is not None and np.isfinite(plain) and np.isfinite(beta):
        held = [f"about {_signed(_whole(plain))} with only lender, channel, week, GSE and FICO", f"about {_signed(_whole(beta))} in a simple regression", f"about {_signed(_near(f['cell5']))} on exact match within 5 points", f"about {_signed(_near(f['tier']))} on exact match within one LLPA tier"]
        if f["model"] is not None:
            held.append(f"about {_signed(_near(f['model']))} on the model, which also holds {MODEL_HOLDS}")
        out.append(("method", f"Controls, same FICO: {'; '.join(held)}."))
    # The thin line: how many groups it resamples, and the lower-LLPA row's top end with Rocket correspondent in.
    groups, weight = _thin_groups(*cells["same_fico"], s.lc)
    thin = f"The thin line: it resamples about {groups} lender and channel groups, about {_whole(weight):.0f} carrying most of the weight, so treat it as the minimum uncertainty." if groups >= 2 else "The thin line: it resamples lender and channel groups."
    if rc_tops and rows["lower_llpa"]["dot"] is not None:
        thin += _rc_back(rc_tops["lower_llpa"], rows["lower_llpa"]["th"])
    out.append(("thin", thin))
    match = _match_line(rows)
    if match:
        out.append(("match", match))
    said = _book_line(book)
    if said:
        out.append(("book", said))
    out.append(("rebuilt", "The newest file is provisional."))
    return [{"view": "limit", "order": i, "key": k, "text": t_} for i, (k, t_) in enumerate(out)]


def _high_share(s):
    """VS4 820+ as a share of VS4 loans, in words."""
    v = s.is_v & ~s.rc
    return _one_in((v & (s.vs >= 820)).sum() / max(v.sum(), 1), "VS4 loan")


def _high_read(s):
    """How many VS4 820+ loans find FICO loans at their own number, of how many; and whether that is almost none."""
    read = _gap(s.bp, s.is_v & ~s.rc & (s.vs >= 820), s.fic & ~s.rc, s.cell_n5)
    return read["n"], read["pool"], read["n"] < NO_LIKE * max(read["pool"], 1)


def _high_like(s):
    return "has almost no FICO loans at its number" if _high_read(s)[2] else "has few FICO loans at its number"


def _steps(s):
    t, c = s.is_v & ~s.rc & s.after, s.fic & ~s.rc & s.after
    time_ = _joint(s.c_week, s.c_close)
    rungs = [("raw", "Raw, by loan", np.zeros(s.n, dtype=np.int64), t, c), ("time", "Same week and closing month", time_, t, c),
             ("lender", "Plus lender, channel and purpose", _joint(time_, s.c_seller, s.c_channel, s.c_purpose), t, c), ("traits", "Plus GSE and LTV band, no score held", s.cell, t, c),
             ("traits_under", "The same, VS4 under 820", s.cell, t & (s.vs < 820), c), ("number", "Plus the score number in 5-point bands, VS4 under 820", s.cell_n5, t & (s.vs < 820), c),
             ("raw_fannie", "Raw at Fannie alone", np.zeros(s.n, dtype=np.int64), t & (s.agency == "FNMA"), c & (s.agency == "FNMA")),
             ("raw_freddie", "Raw at Freddie alone", np.zeros(s.n, dtype=np.int64), t & (s.agency == "FHLMC"), c & (s.agency == "FHLMC"))]
    rows = []
    for order, (key, label, cell, tt, cc) in enumerate(rungs):
        r = _gap(s.bp, tt, cc, cell, (s.lw,))
        rows.append({"view": "steps", "order": order, "key": key, "label": label, "gap": _num(r["est"]), "se": _num(r["se"][0]), "read": r["n"], "pool": r["pool"]})
    return rows


def _number_row(s, scope, key, label, order, m, c, cell, tier_cell=None, **extra):
    """One same_number row: mean gap_number with the widest error, its plain cells beside it. A month's and a gap band's rows also have what the charts draw: the midpoint of the two cell reads, the range across all three, and those printed; a gap band's its thin line. Figures print only on MIN_ROW+ matched loans on each cell read (the one read where a row has no tier cell); under that only the counts stay."""
    ok = m & ~np.isnan(s.gap_number)
    n, weeks = int(ok.sum()), _weeks(s, ok)
    r = _gap(s.bp, m, c, cell)
    rt = _gap(s.bp, m, c, tier_cell) if tier_cell is not None else None
    reached = min(n, r["n"], rt["n"] if rt else r["n"])
    row = {"view": "same_number", "scope": scope, "key": key, "label": label, "order": order, "n": n, "lender_weeks": weeks, "read": r["n"], "read5": r["n"], "read_tier": rt["n"] if rt else None, "pool": r["pool"], "thin": reached < MIN_ROW or weeks < THIN_WEEKS, **extra,
           **dict.fromkeys(("gap", "se", "lo", "hi", "cell5", "tier", "dot_raw", "lo_raw", "hi_raw", "dot", "spread_lo", "spread_hi", "tl", "th"))}
    if reached < MIN_ROW:
        return row
    gap = _mean(s.gap_number[ok])
    se = _widest(s, s.gap_number, m)
    tier = rt["est"] if rt else float("nan")
    row.update(gap=_num(gap), se=_num(se), lo=_num(gap - 1.96 * se), hi=_num(gap + 1.96 * se), cell5=_num(r["est"]), tier=_num(tier))
    if scope in ("month", "gapband"):
        dot_raw, lo_raw, hi_raw, dot, spread_lo, spread_hi = _three(r["est"], tier, gap)
        row.update(dot_raw=_num(dot_raw), lo_raw=_num(lo_raw), hi_raw=_num(hi_raw), dot=dot, spread_lo=spread_lo, spread_hi=spread_hi)
    if scope == "gapband":
        tl, th = _thin_mid(r, rt, s.lc)
        row.update(tl=_num(tl), th=_num(th))
    return row


def _less20_row(s, t, c):
    """The same-number row's loans with 20 points off VS4: VS4 less 20 against FICO in plain cells, and the model's gap there. Figures print only on MIN_ROW+ matched loans on each cell read."""
    less = s.vs - VS_OFFSET
    r5, rt = _gap(s.bp, t, c, s.cell * CELL_K + less // 5, cell_c=s.cell_n5), _gap(s.bp, t, c, s.cell * CELL_K + _tier_band(less), cell_c=s.cell_nt)
    ok = t & ~np.isnan(s.gap_less20)
    weeks = _weeks(s, t)
    row = {"view": "same_number", "scope": "less20", "key": "less20", "label": f"VS4 less {VS_OFFSET} against FICO, VS4 under 820", "order": 0, "n": int(t.sum()), "lender_weeks": weeks, "read": r5["n"], "read5": r5["n"], "read_tier": rt["n"], "pool": r5["pool"], "thin": min(r5["n"], rt["n"]) < MIN_ROW or weeks < THIN_WEEKS,
           **dict.fromkeys(("gap", "se", "lo", "hi", "cell5", "tier", "dot_raw", "lo_raw", "hi_raw", "dot", "spread_lo", "spread_hi", "tl", "th"))}
    if min(r5["n"], rt["n"]) < MIN_ROW:
        return row
    gap, se = _mean(s.gap_less20[ok]), _widest(s, s.gap_less20, t)
    dot_raw, lo_raw, hi_raw, dot, spread_lo, spread_hi = _three(r5["est"], rt["est"], gap)
    row.update(gap=_num(gap), se=_num(se), lo=_num(gap - 1.96 * se), hi=_num(gap + 1.96 * se), cell5=_num(r5["est"]), tier=_num(rt["est"]), dot_raw=_num(dot_raw), lo_raw=_num(lo_raw), hi_raw=_num(hi_raw), dot=dot, spread_lo=spread_lo, spread_hi=spread_hi)
    return row


def _moved_at_gap(s, shown, c):
    """Whether the same-number read moved past FADE_CLOSE at a fixed gap between the two scores, in at least one band from the old rule's points up: a change of mix alone is not the two lines closing."""
    diff = s.vs - s.fico
    for _, _, lo, hi in GAP_BANDS[1:]:
        band = shown & (diff >= lo) & (diff <= hi)
        after, before = _gap(s.bp, band & (s.close >= FADE_CLOSE), c, s.cell_n5, s.widest), _gap(s.bp, band & (s.close < FADE_CLOSE), c, s.cell_n5, s.widest)
        se = float(np.hypot(max(_finite(*after["se"]), default=float("nan")), max(_finite(*before["se"]), default=float("nan"))))
        if len(_finite(after["est"], before["est"], se)) == 3 and abs(after["est"] - before["est"]) > 1.96 * se:
            return True
    return False


def _fade(s, mid, c, shown):
    """Whether the line where LLPA is at stake is falling, on closings past the mark. Closing dates are monthly, so the test waits for the first month wholly past it. The fit holds a score's effect fixed across months, so its lines alone do not decide: both reads must agree, and a read that the lines closed needs a move at a fixed gap too. With no read the early text stands."""
    late = mid & (s.close >= FADE_CLOSE)
    weeks = _weeks(s, late)
    a, b = late & s.stake, late & ~s.stake
    text, state, diff, se = f"Is the gap narrowing? Too early to say: rates on closings just after the {_day(ANNOUNCED)} announcement were mostly set before it.", "early", float("nan"), float("nan")
    if weeks >= THIN_WEEKS and a.any() and b.any():
        diff = _mean(s.gap_number[a & ~np.isnan(s.gap_number)]) - _mean(s.gap_number[b & ~np.isnan(s.gap_number)])
        se = float(np.hypot(_widest(s, s.gap_number, a), _widest(s, s.gap_number, b)))
        ra, rb = _gap(s.bp, a, c, s.cell_n5, s.widest), _gap(s.bp, b, c, s.cell_n5, s.widest)
        plain = ra["est"] - rb["est"]
        plain_se = float(np.hypot(max(_finite(*ra["se"]), default=float("nan")), max(_finite(*rb["se"]), default=float("nan"))))
        apart = [abs(d) > 1.96 * e for d, e in ((diff, se), (plain, plain_se)) if np.isfinite(d) and np.isfinite(e)]
        when = f"on closings from {_month(FADE_CLOSE)} on"
        if apart and all(apart):
            text, state = f"Is the gap narrowing? The two lines still differ {when}: no clear narrowing yet.", "holds"
        elif any(apart):
            text, state = f"Is the gap narrowing? The methods disagree {when}: no clear narrowing yet.", "unsettled"
        elif apart and _moved_at_gap(s, shown, c):
            text, state = f"Is the gap narrowing? The two lines no longer clearly differ {when}.", "fades"
        elif apart:
            text, state = f"Is the gap narrowing? The two lines no longer clearly differ {when}, but nothing has moved among loans with the same gap between VS4 and FICO: no clear narrowing yet.", "no_move"
    return {"view": "same_number", "scope": "fade", "key": "fade", "label": "Where the old rule would raise the LLPA", "order": 0, "text": text, "state": state, "gap": _num(diff), "se": _num(se), "lo": _num(diff - 1.96 * se), "hi": _num(diff + 1.96 * se),
            "n": int(late.sum()), "lender_weeks": weeks, "thin": weeks < THIN_WEEKS}


def _kept(con):
    """Of each closing month's VS4 loans under the sample's other limits, Rocket correspondent out, the share first disclosed from WEEKLY_START: the rest are not in any read."""
    return dict(con.execute(f"""
        SELECT {closing_month('l.first_pay_date')}::VARCHAR, avg(CASE WHEN l.first_intraday_date >= DATE '{WEEKLY_START}' THEN 1.0 ELSE 0.0 END)
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.loan_term = 360 AND l.amort_type = 'FRM' AND l.score_model = 'V' AND l.orig_rate > 0 AND l.pricing_score IS NOT NULL AND l.ltv IS NOT NULL
          AND NOT (m.id = '{ROCKET}' AND coalesce(l.channel, '?') = 'C')
        GROUP BY 1""").fetchall())


def _in_share(con, s, closing):
    """A closing month's share of its loans in the same-number chart: how much of the month has arrived, from the closing dataset's lender rows weighted by each seller's share of the month's chart loans (the market row for a seller with no row), times how much of it the sample keeps. Without an arrival figure for every seller, none."""
    rows = [r for r in closing or [] if r.get("agency") == "All" and r.get("arrived") is not None]
    market = {r["start"]: r["arrived"] for r in rows if r.get("view") == "market"}
    lender = {(r["start"], r.get("id")): r["arrived"] for r in rows if r.get("view") == "lender"}
    if not market and not lender:
        return {}
    kept = _kept(con)
    chart = s.is_v & ~s.rc & (s.vs >= 640) & (s.vs < 820)
    out = {}
    for month in (str(m) for m in np.unique(s.close[chart]) if m >= MONTHS_FROM):
        sellers, counts = np.unique(s.seller[chart & (s.close == month)], return_counts=True)
        arrived = [lender.get((month, str(x)), market.get(month)) for x in sellers]
        if month in kept and None not in arrived:
            out[month] = _num(float(np.average(arrived, weights=counts)) * kept[month], 3)
    return out


def _same_number(s, in_share):
    v, c = s.is_v & ~s.rc, s.fic & ~s.rc
    under = v & (s.vs < 820)
    mid = v & (s.vs >= 640) & (s.vs < 820)
    rows = []
    for order, close in enumerate(str(m) for m in np.unique(s.close[mid]) if m >= MONTHS_FROM):
        for group, m, label in (("stake", mid & s.stake, "Old rule would raise LLPA"), ("no_stake", mid & ~s.stake, "Old rule would not")):
            rows.append(_number_row(s, "month", f"{group}|{close}", label, order, m & (s.close == close), c, s.cell_n5, s.cell_nt, group=group, close=close, in_share=in_share.get(close)))
    # Both sides of an issue-period read come from that period, so from_oct ties to the last rung of the steps.
    for order, (key, label, side) in enumerate((("before", f"Issued before {_day(GRID_CHANGE)}", ~s.after), ("from_oct", f"Issued from {_day(GRID_CHANGE)}", s.after))):
        row = _number_row(s, "period", key, label, order, under & side, c & side, s.cell_n5, s.cell_nt, less20=None, less20_se=None)
        if row["gap"] is not None:
            row.update(less20=_num(_mean(s.gap_less20[under & side & ~np.isnan(s.gap_less20)])), less20_se=_num(_widest(s, s.gap_less20, under & side)))
        rows.append(row)
    low = _number_row(s, "band", "under640", "VS4 under 640", 0, v & (s.vs < 640), c, s.cell_n5, s.cell_nt)
    reads = _finite(low.get("cell5"), low.get("tier"), low.get("gap"))
    low["flag"] = "unsettled" if len(reads) == 3 and max(reads) - min(reads) >= UNSETTLED else None
    at_number, _, almost_none = _high_read(s)
    rows += [low, _number_row(s, "band", "over820", "VS4 820+, against FICO 780+", 1, v & (s.vs >= 820), c & (s.fico >= 780), s.cell, flag="no_like_fico" if almost_none else "few_like_fico", read_number=at_number)]
    shown = under & s.has_f
    diff = s.vs - s.fico
    for order, (key, label, lo, hi) in enumerate(GAP_BANDS):
        in_band = shown & (diff >= lo) & (diff <= hi)
        rows.append(_number_row(s, "gapband", key, label, order, in_band, c, s.cell_n5, s.cell_nt))
        for close in (str(m) for m in np.unique(s.close[in_band])):
            if close >= MONTHS_FROM:
                rows.append(_number_row(s, "gapband_month", f"{key}|{close}", label, order, in_band & (s.close == close), c, s.cell_n5, s.cell_nt, group=key, close=close))
    rows.append(_less20_row(s, under, c))
    rows.append(_fade(s, mid, c, shown))
    return rows


def _invert(a, centers, p):
    """The score at which the falling curve p, on centers, pays a; the ends of the curve when a is off it."""
    vals, lens = [], []
    for v in p:  # pool adjacent violators: the closest falling curve
        vals.append(float(v))
        lens.append(1)
        while len(vals) > 1 and vals[-2] < vals[-1]:
            top, width = vals.pop(), lens.pop()
            vals[-1] = (vals[-1] * lens[-1] + top * width) / (lens[-1] + width)
            lens[-1] += width
    q = np.repeat(vals, lens)
    if a >= q[0]:
        return float(centers[0])
    if a <= q[-1]:
        return float(centers[-1])
    i = int(np.flatnonzero(q >= a)[-1])
    if q[i] == q[i + 1]:
        return float(centers[i + 1])
    return float(centers[i] + (centers[i + 1] - centers[i]) * (q[i] - a) / (q[i] - q[i + 1]))


def _equivalent(s, fits):
    """By 20-point VS4 band, loans issued from GRID_CHANGE: the FICO that pays the band's mean rate on the loans' own curves. The error is on the loans against those curves, since a week's or a trait's rate moves both sides.
    Beside it, the FICO shown on FICO loans with that VS4 at lenders that rarely use VS4. Under MIN_ROW VS4 loans a band keeps only its counts."""
    t = s.is_v & ~s.rc & s.after & (s.vs >= VS_BANDS[0][0]) & (s.vs <= VS_BANDS[-1][1])
    both_rare = s.fic & s.has_v & s.after & ~s.rc & _rare(s)
    p = np.flatnonzero(t)
    pos = np.full(s.n, -1)
    pos[p] = np.arange(len(p))
    curve = np.full((len(p), N5), np.nan)
    for f in fits:
        rows = np.flatnonzero(t[f.ix])
        if len(rows):
            curve[pos[f.ix[rows]]] = f.curve(rows)
    start = (EX_LOW - S_LO) // 5
    grid = np.arange(start, N5)
    out = []
    for order, (lo, hi) in enumerate(VS_BANDS):
        sel = (s.vs[p] >= lo) & (s.vs[p] <= hi)
        rare = s.fico[both_rare & (s.vs >= lo) & (s.vs <= hi)]
        row = {"view": "equivalent", "order": order, "key": f"{lo}-{hi}", "band": f"{lo}-{hi}", "n": int(sel.sum()), "eq": None, "eq_lo": None, "eq_hi": None, "fico_mean": None, "slope": None, "use_bp": None, "vs_mean": None, "points": None,
               "fico_rare": _num(_mean(rare), 1) if len(rare) >= MIN_ROW else None, "fico_rare_n": len(rare)}
        if not sel.any():
            out.append(row)
            continue
        cc = curve[sel][:, grid]
        ok_b = (~np.isnan(cc)).mean(axis=0) >= 0.95
        if ok_b.sum() >= 3:
            first = int(np.flatnonzero(ok_b)[0])
            good = ~np.isnan(cc[:, first:]).any(axis=1)
            if good.sum() < MIN_ROW:
                row["n"] = int(good.sum())
                out.append(row)
                continue
            at = p[sel][good]
            q = cc[good, first:].mean(axis=0)
            cen = CENTERS[grid][first:]
            a = float(s.y[at].mean())
            eq = _invert(a, cen, q)
            near = int(np.argmin(np.abs(cen - eq)))
            se = _cluster_se((s.y[at] - cc[good, first:][:, near]) * 100, s.lw[at]) / 100
            i_lo = max((lo - 10 - S_LO) // 5 - start - first, 0)
            i_hi = min((hi + 10 - S_LO) // 5 - start - first, len(q) - 1)
            slope = (q[i_lo] - q[i_hi]) * 100 / (i_hi - i_lo) * 4 if i_hi > i_lo else float("nan")
            shown = s.fico[at][s.has_f[at]]
            use_bp = bool(slope < EQ_FLAT) if np.isfinite(slope) else None
            vs_mean = _num(_mean(s.vs[at]), 1)
            row.update(n=int(good.sum()), eq=_num(eq, 1), eq_lo=_num(_invert(a + 1.96 * se, cen, q), 1) if np.isfinite(se) else None, eq_hi=_num(_invert(a - 1.96 * se, cen, q), 1) if np.isfinite(se) else None,
                       fico_mean=_num(_mean(shown), 1), slope=_num(slope), use_bp=use_bp, vs_mean=vs_mean, points=None if use_bp else _points(vs_mean, _num(eq, 1)))
            if row["eq_lo"] == row["eq"] == row["eq_hi"]:  # pinned to the end of the curve, so it says nothing
                row.update(eq=None, eq_lo=None, eq_hi=None, points=None)
        out.append(row)
    return out


def _points(vs_mean, eq):
    """VS4 above the FICO that pays the same rate, from the two whole numbers a reader sees."""
    return int(_whole(vs_mean) - _whole(eq))


def _crossing(gaps):
    """Where a gap falling with the points taken off VS4 crosses zero."""
    for (k0, g0), (k1, g1) in zip(gaps, gaps[1:]):
        if np.isfinite(g0) and np.isfinite(g1) and g0 >= 0 > g1:
            return k0 + (k1 - k0) * g0 / (g0 - g1)
    return None


def _priced_below(s, fits, group=None):
    """How many points below its own number a VS4 loan under 820 has priced, both sides issued from GRID_CHANGE: the points that take the mean gap to zero, on the loans' own curves and in plain cells."""
    t = s.is_v & ~s.rc & s.after & (s.vs < 820)
    c = s.fic & ~s.rc & s.after
    if group is not None:
        t, c = t & group, c & group
    if t.sum() < MIN_ROW:
        return []
    model, plain = [], []
    for k in PRICED_K:
        g = np.full(s.n, np.nan)
        for f in fits:
            rows = np.flatnonzero(t[f.ix])
            if len(rows):
                at = f.ix[rows]
                g[at] = s.bp[at] - f.at(rows, _band5(s.vs[at] - k)) * 100
        model.append((k, _mean(g[t & ~np.isnan(g)])))
        plain.append((k, _gap(s.bp, t, c, s.cell * CELL_K + (s.vs - k) // 5, cell_c=s.cell * CELL_K + s.fico // 5)["est"]))
    return _finite(_crossing(model), _crossing(plain))


def _priced_curve(s):
    """The loans _priced_below reads, and each one's gap on the model at each k points off VS4."""
    t = s.is_v & ~s.rc & s.after & (s.vs < 820)
    at = np.flatnonzero(t)
    pos = np.full(s.n, -1)
    pos[at] = np.arange(len(at))
    curve = np.full((len(at), len(PRICED_K)), np.nan)
    for f in s.fits:
        rows = np.flatnonzero(t[f.ix])
        if len(rows):
            here = f.ix[rows]
            for j, k in enumerate(PRICED_K):
                curve[pos[here], j] = s.bp[here] - f.at(rows, _band5(s.vs[here] - k)) * 100
    return at, curve


def _priced_range(s, at, curve, group=None):
    """95% for how far below its number a VS4 loan has priced, on the model, from resampling weeks inside each lender and channel: the ends outward in whole points, then as they came. None on under MIN_ROW loans, or where over 2.5% of the draws never cross zero."""
    sel = np.ones(len(at), bool) if group is None else group[at]
    if sel.sum() < MIN_ROW:
        return None
    ix, gaps = at[sel], curve[sel]
    inv = np.unique(_joint(s.lc[ix], s.c_week[ix]), return_inverse=True)[1]
    size = int(inv.max()) + 1
    known = ~np.isnan(gaps)
    total = np.column_stack([np.bincount(inv[known[:, j]], weights=gaps[known[:, j], j], minlength=size) for j in range(len(PRICED_K))])
    count = np.column_stack([np.bincount(inv[known[:, j]], minlength=size) for j in range(len(PRICED_K))])
    first = np.zeros(size, dtype=np.int64)
    first[inv] = s.lc[ix]
    groups = [np.flatnonzero(first == g) for g in np.unique(first)]
    rng = np.random.default_rng(SEED)
    cross = np.full(PRICED_DRAWS, np.nan)
    for d in range(PRICED_DRAWS):
        pick = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groups])
        n = count[pick].sum(axis=0)
        mean = total[pick].sum(axis=0) / np.where(n > 0, n, np.nan)
        found = _crossing(list(zip(PRICED_K, mean)))
        if found is not None:
            cross[d] = found
    if np.isnan(cross).mean() > 0.025:
        return None
    lo, hi = np.percentile(cross[~np.isnan(cross)], [2.5, 97.5])
    return int(np.floor(round(lo, 2))), int(np.ceil(round(hi, 2))), float(lo), float(hi)


def _lender_row(s, scope, key, label, order, m, **extra):
    """A lender row's reads: its own loans against its own FICO loans, and the two cell reads against those of them showing a VS4. Figures print only on MIN_ROW+ matched loans on each cell read; n stays the pool."""
    row = {"view": "lender", "scope": scope, "key": key, "label": label, "order": order, **extra}
    c = s.fic & m
    pools = _pools(s)
    for r in ("same_fico", "same_llpa", "same_number"):
        t, c5, ct, gap = pools[r]
        t = t & m
        n = int(t.sum())
        weeks = _weeks(s, t)
        r5, rt = _gap(s.bp, t, c, c5), _gap(s.bp, t, c, ct)
        v5, vt = _gap(s.bp, t, c & s.has_v, c5), _gap(s.bp, t, c & s.has_v, ct)
        row.update({f"{r}_n": n, f"{r}_weeks": weeks, f"{r}_rough": weeks < THIN_WEEKS, f"{r}_read5": r5["n"], f"{r}_read_tier": rt["n"], f"{r}_shown_read5": v5["n"], f"{r}_shown_read_tier": vt["n"],
                    f"{r}_shown_cell5": _num(v5["est"]) if v5["n"] >= MIN_ROW else None, f"{r}_shown_tier": _num(vt["est"]) if vt["n"] >= MIN_ROW else None})
        raw = dot = lo = hi = se = None
        if min(r5["n"], rt["n"]) >= MIN_ROW:
            raw, _, _, dot, lo, hi = _three(r5["est"], rt["est"], _mean(gap[t & ~np.isnan(gap)]))
            se = _num(_widest(s, gap, t))
        row.update({f"{r}_dot": dot, f"{r}_lo": lo, f"{r}_hi": hi, f"{r}_se": se, f"{r}_mid": _num(raw)})
    return row


def _lender(s, names):
    rkt, uwm = s.seller == ROCKET, s.seller == UWM
    groups = [("rocket_retail", ROCKET, "R"), ("rocket_broker", ROCKET, "B"), ("uwm_broker", UWM, "B"), ("uwm_correspondent", UWM, "C")]
    rows, named = [], s.rc.copy()
    for order, (key, seller, channel) in enumerate(groups):
        m = (rkt if seller == ROCKET else uwm) & (s.channel == channel)
        named |= m
        rows.append(_lender_row(s, "group", key, _label(s, names, seller, channel), order, m))
    rows.append(_lender_row(s, "group", "other", "Other lenders", len(groups), ~named))
    rows.append(_lender_row(s, "group", "rocket_correspondent", _label(s, names, ROCKET, "C"), len(groups) + 1, s.rc, not_like_for_like=True))
    sellers, counts = np.unique(s.seller[s.is_v], return_counts=True)
    order = np.argsort(-counts, kind="stable")
    for rank, i in enumerate(order):
        if counts[i] >= MIN_ROW:
            m = s.seller == sellers[i]
            extra = {"correspondent_out": True} if sellers[i] == ROCKET else {}
            if sellers[i] == UWM:
                t, c = s.tv & uwm & (s.vs < 820), s.fic & uwm
                r5, rt = _gap(s.bp, t, c, s.cell_f5), _gap(s.bp, t, c, s.cell_ft)
                extra["same_fico_under820"] = _num((r5["est"] + rt["est"]) / 2) if min(r5["n"], rt["n"]) >= MIN_ROW else None
            rows.append(_lender_row(s, "card", str(sellers[i]), names.get(sellers[i], sellers[i]), rank, m & ~s.rc, **extra))
    return rows


def _lender_line(rows):
    """UWM's same-FICO read against what it is compared with: its read on VS4 under 820 while that sits 1.5+ bp off, and against FICO loans showing a VS4 while that sits 2+ bp off and each cell read has MIN_ROW+ matched loans. None unless one of those two prints."""
    uwm = next((r for r in rows if r["scope"] == "card" and r["key"] == UWM), None)
    if not uwm or uwm["same_fico_dot"] is None:
        return None
    under, cell5, tier, mid = uwm.get("same_fico_under820"), uwm["same_fico_shown_cell5"], uwm["same_fico_shown_tier"], uwm["same_fico_mid"]
    more = [*([f"about {_signed(_near(under))} on VS4 under 820"] if under is not None and abs(under - mid) >= 1.5 else []),
            *([f"about {_signed(_near((cell5 + tier) / 2))} against FICO loans that also show a VS4"] if None not in (cell5, tier) and abs((cell5 + tier) / 2 - mid) >= 2 else [])]
    if not more:
        return None
    reads = [f"about {_signed(uwm['same_fico_dot'])} on its VS4 loans showing a FICO", *more]
    return f"{uwm['label']}: its same-FICO gap moves with the comparison: {' and '.join(reads) if len(reads) == 2 else f'{reads[0]}, {reads[1]}, and {reads[2]}'}."


def _cut(s, names):
    """Same FICO, same LLPA, by loan type, in the same grammar as chart 4, so the same label prints the same number. The model read and its error stay for the workbook. n is the pool, model_n the loans with a model read. Figures print only on MIN_ROW+ matched loans on each cell read; under that only the counts and any words stay."""
    t = s.tv & s.same
    size_b = np.searchsorted(SEGMENT_SIZE[0], s.amount, side="right")
    dims = [("ltv", [(str(i), lab, s.ltvb == i) for i, lab in enumerate(LTV_LABELS)]),
            ("size", [(str(i), lab, size_b == i) for i, lab in enumerate(SEGMENT_SIZE[1])]),
            ("fico", [(key, lab, (s.fico >= lo) & (s.fico <= hi)) for key, lab, lo, hi in FICO_CUT]),
            ("purpose", [("P", PURPOSE_LABELS["P"], ~s.refi), ("refi", "Refinance", s.refi), *((k, PURPOSE_LABELS[k], s.purpose == k) for k in ("C", "R"))])]
    rows = []

    def add(dim, key, label, order, m, **extra):
        c = s.fic & (s.rc if dim == "rocket_correspondent" else ~s.rc)
        ok = m & ~np.isnan(s.gap_fico)
        n, weeks = int(m.sum()), _weeks(s, m)
        r5, rt = _gap(s.bp, m, c, s.cell_f5), _gap(s.bp, m, c, s.cell_ft)
        reached = min(r5["n"], rt["n"])
        row = {"view": "cut", "dim": dim, "key": key, "label": label, "order": order, "n": n, "model_n": int(ok.sum()), "read5": r5["n"], "read_tier": rt["n"], "lender_weeks": weeks, "thin": reached < MIN_ROW or weeks < THIN_WEEKS, "description": True, "text": None, **extra,
               **dict.fromkeys(("gap", "se", "lo", "hi", "model", "cell5", "tier", "dot_raw", "lo_raw", "hi_raw", "dot", "spread_lo", "spread_hi", "tl", "th"))}
        if reached >= MIN_ROW:
            gap, se = _mean(s.gap_fico[ok]), _widest(s, s.gap_fico, m)
            dot_raw, lo_raw, hi_raw, dot, spread_lo, spread_hi = _three(r5["est"], rt["est"], gap)
            tl, th = _thin_mid(r5, rt, s.lc)
            row.update(gap=_num(gap), se=_num(se), lo=_num(gap - 1.96 * se), hi=_num(gap + 1.96 * se), model=_num(gap), cell5=_num(r5["est"]), tier=_num(rt["est"]), dot_raw=_num(dot_raw), lo_raw=_num(lo_raw), hi_raw=_num(hi_raw), dot=dot, spread_lo=spread_lo, spread_hi=spread_hi, tl=_num(tl), th=_num(th))
        if dim == "fico" and n >= MIN_ROW and r5["n"] < NO_LIKE * n:  # the fit may still give a number here; the cells say there is nothing comparable
            row["text"] = "No comparable FICO loans."
        rows.append(row)

    for dim, parts in dims:
        for order, (key, label, m) in enumerate(parts):
            add(dim, key, label, order, t & m)
    # Rocket correspondent's own row, the same read on its own loans, not like for like.
    add("rocket_correspondent", "rocket_correspondent", _label(s, names, ROCKET, "C"), 0, s.is_v & s.has_f & s.same & s.rc, not_like_for_like=True)
    return rows


def _fico_gap(s):
    """Same FICO by how far VS4 sits above FICO, on the same-FICO row's loans, in the fields of a same-number gap band so a chart can draw both. Figures print only on MIN_ROW+ matched loans on each cell read."""
    c = s.fic & ~s.rc
    diff = s.vs - s.fico
    rows = []
    for order, (key, label, lo, hi) in enumerate(GAP_BANDS):
        t = s.tv & (diff >= lo) & (diff <= hi)
        r5, rt = _gap(s.bp, t, c, s.cell_f5), _gap(s.bp, t, c, s.cell_ft)
        ok = t & ~np.isnan(s.gap_fico)
        weeks = _weeks(s, t)
        reached = min(r5["n"], rt["n"])
        row = {"view": "fico_gap", "key": key, "label": label, "order": order, "n": int(t.sum()), "model_n": int(ok.sum()), "read5": r5["n"], "read": r5["n"], "read_tier": rt["n"], "pool": int(t.sum()), "lender_weeks": weeks, "thin": reached < MIN_ROW or weeks < THIN_WEEKS,
               **dict.fromkeys(("cell5", "tier", "model", "gap", "dot_raw", "lo_raw", "hi_raw", "dot", "spread_lo", "spread_hi", "tl", "th", "fannie"))}
        if reached >= MIN_ROW:
            model = _mean(s.gap_fico[ok])
            dot_raw, lo_raw, hi_raw, dot, spread_lo, spread_hi = _three(r5["est"], rt["est"], model)
            tl, th = _thin_mid(r5, rt, s.lc)
            row.update(cell5=_num(r5["est"]), tier=_num(rt["est"]), model=_num(model), gap=_num(model), dot_raw=_num(dot_raw), lo_raw=_num(lo_raw), hi_raw=_num(hi_raw), dot=dot, spread_lo=spread_lo, spread_hi=spread_hi, tl=_num(tl), th=_num(th), fannie=_num(_fannie_mid(s, t, r5, rt)))
        rows.append(row)
    return rows


def _checks(s, rows):
    out = []
    said = lambda x: _signed(_near(x)) if np.isfinite(x) else "no figure"  # noqa: E731
    about = lambda x: f"about {said(x)}" if np.isfinite(x) else "no figure"  # noqa: E731
    reach = lambda v, words=" matched": f" ({v[1]:,} of {v[2]:,}{words})" if v[1] else f" (none of {v[2]:,}{words})" if v[2] else ""  # noqa: E731
    # Look-alikes: held-out FICO loans, at their own FICO through the fit that covers them, weighted to the VS4 loans' cells. It should read about zero.
    base = _joint(s.c_seller, s.c_channel, s.c_week, s.c_purpose, s.ltvb) * 10
    h = s.fic & s.holdout & ~s.rc & ~np.isnan(s.gap_own)
    number = _lookalike_value(s, s.is_v & ~s.rc, h, base + _tier(s.score))
    fico = _lookalike_value(s, s.tv, h, base + _tier(s.fico))
    worst = number if not np.isfinite(fico[0]) or abs(number[0]) >= abs(fico[0]) else fico
    held = f"; {_count(int(h.sum()), 'held-out FICO loan')}" if h.any() else ""
    out.append({"key": "lookalike", "label": "Held-out FICO loans weighted to the VS4 loans' cells, against the model", "value": _num(worst[0]), "limit": CHECK_LOOKALIKE, "pass": bool(abs(worst[0]) <= CHECK_LOOKALIKE) if np.isfinite(worst[0]) else None, "n": int(worst[1]),
                "detail": f"{about(number[0]).capitalize()} weighted to all VS4 loans at their VS4 number{reach(number)}; {about(fico[0])} weighted to VS4 loans showing a FICO at that FICO{reach(fico, '')}{held}."})
    # Each read's model against its plain cells.
    diffs = {k: (rows[k]["model"] - rows[k]["cell5"]) if rows[k]["model"] is not None and rows[k]["cell5"] is not None else None for k in ("same_fico", "same_llpa", "same_number")}
    known = [k for k, v in diffs.items() if v is not None]
    far = max(known, key=lambda k: abs(diffs[k])) if known else None
    out.append({"key": "cells", "label": "Model minus the plain same-cell figure", "value": _num(diffs[far]) if far else None, "limit": CHECK_CELLS, "pass": bool(abs(diffs[far]) <= CHECK_CELLS) if far else None, "n": rows[far]["n"] if far else 0,
                "detail": "; ".join(f"{name} {said(diffs[k]) if diffs[k] is not None else 'no figure'}" for k, name in (("same_fico", "Same FICO"), ("same_llpa", "same FICO and LLPA"), ("same_number", "same score number"))) + f". Not tested: the lower-LLPA row and the row under FICO {SCORE_CUTS[-1]}, whose bar shows how far its methods sit apart."})
    # FICO loans with VS4 well above their FICO, at lenders that rarely use VS4: they have what a VS4 loan has but the pick, so they should read about zero.
    high = s.fic & s.has_v & (s.vs - s.fico >= RARE_ABOVE) & ~np.isnan(s.gap_own)
    m = high & _rare(s) & ~s.rc
    value = _mean(s.gap_own[m]) if m.sum() >= RARE_N else float("nan")
    rkt, uwm = high & (s.seller == ROCKET) & ~s.rc, high & (s.seller == UWM)
    uwm_c, uwm_b = uwm & (s.channel == "C"), uwm & (s.channel == "B")
    top_share, without, without_n, without_se = None, float("nan"), 0, float("nan")
    if m.any():
        sellers, counts = np.unique(s.seller[m], return_counts=True)
        rest = m & (s.seller != sellers[np.argmax(counts)])
        top_share, without_n = float(counts.max() / counts.sum()), int(rest.sum())
        without, without_se = _mean(s.gap_own[rest]), _cluster_se(s.gap_own[rest], s.lw[rest])
    detail = "Too few of these loans to test."
    if np.isfinite(value):
        beyond = f"; without it, about {said(without)}" if without_n >= RARE_N else ""
        detail = f"{_half_of(top_share).capitalize()} of these loans are one lender{beyond}." if top_share >= TOP_SHARE else f"No one lender is {TOP_SHARE:.0%} of these loans."
    out.append({"key": "rare_high_vs4", "label": f"FICO loans with VS4 {RARE_ABOVE}+ above FICO, at lenders that rarely use VS4", "value": _num(value), "limit": CHECK_RARE, "pass": bool(abs(value) <= CHECK_RARE) if np.isfinite(value) else None, "n": int(m.sum()),
                "rocket": _num(_mean(s.gap_own[rkt])), "rocket_n": int(rkt.sum()), "uwm": _num(_mean(s.gap_own[uwm])), "uwm_n": int(uwm.sum()), "uwm_correspondent": _num(_mean(s.gap_own[uwm_c])), "uwm_correspondent_n": int(uwm_c.sum()), "uwm_broker": _num(_mean(s.gap_own[uwm_b])), "uwm_broker_n": int(uwm_b.sum()),
                "top_share": _num(top_share, 3), "without_top": _num(without), "without_top_n": without_n, "without_top_se": _num(without_se), "detail": detail})
    # One bad file would reach the answer, so count the rates no loan should carry. Nothing is filtered on it.
    outside = int(((s.y < CHECK_RATE[0]) | (s.y > CHECK_RATE[1])).sum())
    out.append({"key": "rate_range", "label": f"Loans with a note rate outside {CHECK_RATE[0]:g}% to {CHECK_RATE[1]:g}%", "value": outside, "limit": 0, "unit": "loans", "pass": outside == 0, "n": s.n,
                "detail": f"{_count(outside, 'loan')} of {s.n:,}. They stay in the figures." if outside else "Every note rate in the sample is inside that range."})
    return [{"view": "check", "order": i, "unit": "bp", **r} for i, r in enumerate(out)]


def _rare(s):
    """Loans at lenders that rarely use VS4."""
    sellers = int(s.c_seller.max()) + 1
    used, loans = np.bincount(s.c_seller[s.is_v], minlength=sellers), np.bincount(s.c_seller, minlength=sellers)
    return (used / np.maximum(loans, 1))[s.c_seller] <= RARE_SHARE


def _lookalike_value(s, t, h, cell):
    """The mean held-out FICO loans' miss, cell by cell, weighted by t's loans; with the VS4 loans matched and in all."""
    if not t.any() or not h.any():
        return float("nan"), 0, int(t.sum())
    inv = np.unique(np.concatenate((cell[t], cell[h])), return_inverse=True)[1]
    it, ih = inv[:int(t.sum())], inv[int(t.sum()):]
    m = int(inv.max()) + 1
    nt, nh = np.bincount(it, minlength=m), np.bincount(ih, minlength=m)
    miss = np.bincount(ih, weights=s.gap_own[h], minlength=m) / np.maximum(nh, 1)
    ok = (nt > 0) & (nh > 0)
    if not ok.any():
        return float("nan"), 0, int(t.sum())
    return float((nt[ok] * miss[ok]).sum() / nt[ok].sum()), int(nt[ok].sum()), int(t.sum())


def check_warnings(rows) -> list[str]:
    """The build checks that missed, as plain text for the weekly report. They warn and stop nothing."""
    out = []
    for r in rows:
        if r.get("view") == "check" and not r.get("pass"):
            if r.get("value") is None:
                what = "could not be read"
            elif r.get("unit") == "loans":
                what = f"counts {r['value']:,}, past its limit of {r['limit']:g}"
            else:
                what = f"reads {r['value']:+.2f} bp, past its limit of {r['limit']:g}"
            out.append(f"rate check: {r['label']} {what}. {r.get('detail') or ''}".strip())
    return out


def _milliman(con, s, names):
    """VS4 less 20 against FICO on plain cells, VS4 under 820. Milliman's own loans predate the first-disclosure limit, so its window is a query of its own, and read again with both sides first disclosed from WEEKLY_START. Figures print only on a pool of MIN_ROW+ VS4 loans."""
    d = con.execute(f"""
        SELECT l.agency, {closing_month('l.first_pay_date')}::VARCHAR AS close, m.id AS seller, coalesce(l.channel, '?') AS channel,
               CASE WHEN l.purpose = 'P' THEN 'P' WHEN l.purpose = 'C' THEN 'C' ELSE 'R' END AS purpose, l.score_model = 'V' AS is_v, l.pricing_score AS score, l.ltv, l.orig_rate,
               coalesce(l.first_intraday_date < DATE '{WEEKLY_START}', true) AS before_start
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.loan_term = 360 AND l.amort_type = 'FRM' AND l.score_model IN ('C', 'V') AND l.orig_rate > 0 AND l.pricing_score IS NOT NULL AND l.ltv IS NOT NULL
          AND m.id IN ('{ROCKET}', '{UWM}') AND {closing_month('l.first_pay_date')} BETWEEN DATE '{MILLIMAN[0]}' AND DATE '{MILLIMAN[1]}'
          AND l.issue_month BETWEEN DATE '{MILLIMAN[0]}' AND DATE '{MILLIMAN[1]}'
        ORDER BY l.agency, l.loan_id""").fetchnumpy()
    d = {k: np.asarray(v) for k, v in d.items()}
    seller, channel = d["seller"].astype(str), d["channel"].astype(str)
    is_v = d["is_v"].astype(bool)
    rc_kept = bool((is_v & (seller == ROCKET) & (channel == "C")).any())
    who = _and([names.get(x, x) for x in (ROCKET, UWM) if (is_v & (seller == x)).any()] or [names.get(ROCKET, ROCKET), names.get(UWM, UWM)])
    window, late, plain = f"{who}, closed and issued May to August", f"{who}, closed and issued May to August, first disclosed from {_day(WEEKLY_START)}", f"May to August, no channel in the cell, VS4 820+{' and Rocket correspondent' if rc_kept else ''} kept"
    rows = []
    if len(d["orig_rate"]):
        keep = ~((seller == ROCKET) & (channel == "C"))
        held = (_code(seller), _code(d["close"]), _code(d["agency"]), _code(d["purpose"]), np.searchsorted(LTV_CUTS, d["ltv"].astype(float), side="left"))
        score = d["score"].astype(np.int64)
        y = d["orig_rate"].astype(float) * 100
        less20 = np.where(is_v, score - 20, score)
        recent = ~d["before_start"].astype(bool)
        rows += [("window", window, y, is_v & keep & (score < 820), ~is_v & keep, _joint(*held, _code(channel)), less20), ("window_late", late, y, is_v & keep & (score < 820) & recent, ~is_v & keep & recent, _joint(*held, _code(channel)), less20), ("window_plain", plain, y, is_v, ~is_v, _joint(*held), less20)]
    else:
        rows += [(key, label, np.zeros(0), np.zeros(0, bool), np.zeros(0, bool), np.zeros(0, np.int64), np.zeros(0, np.int64)) for key, label in (("window", window), ("window_late", late), ("window_plain", plain))]
    cell = _joint(s.c_seller, s.c_channel, s.c_close, s.c_agency, s.c_purpose, s.ltvb)
    theirs = np.isin(s.seller, (ROCKET, UWM))
    now = _and([names.get(x, x) for x in (ROCKET, UWM) if (s.is_v & (s.seller == x)).any()] or [names.get(ROCKET, ROCKET), names.get(UWM, UWM)])
    rows.insert(2, ("from_oct", f"{now}, issued from {_day(GRID_CHANGE)}", s.bp, theirs & s.is_v & ~s.rc & s.after & (s.vs < 820), theirs & s.fic & ~s.rc & s.after, cell, np.where(s.is_v, s.vs - 20, s.fico)))
    out = []
    for order, (key, label, y, t, c, cell, score) in enumerate(rows):
        r5, rt = _gap(y, t, c, cell * CELL_K + score // 5), _gap(y, t, c, cell * CELL_K + _tier_band(score))
        enough = r5["pool"] >= MIN_ROW
        out.append({"view": "milliman", "order": order, "key": key, "label": label, "cell5": _num(r5["est"]) if enough else None, "tier": _num(rt["est"]) if enough else None, "read": r5["n"], "read_tier": rt["n"], "pool": r5["pool"], "rc_kept": rc_kept if key == "window_plain" else None, "reaches_back": bool((is_v & d["before_start"].astype(bool)).any()) if key == "window" and len(d["orig_rate"]) else None})
    return out


def _follows(s, names):
    """Whether the rate moves mainly with the score used: the slope on each score, per 20 points, on VS4 loans and on FICO loans showing both, and VS4's slope less FICO's from one more regression. A fit holds where the used slope and used less other both clear zero at 1.96, on enough loans; a scope where both its fits do, and the pooled scopes also need THIN_WEEKS+ lender-weeks, which one lender can't reach in a few weeks.
    The sentence needs refinances to hold and Fannie refinances to lean the same way. It says what purchases do, with what holds on purchases checked at Fannie alone, then what the refinance slopes and those of any group the purchases line says follows its score come to with the LLPA of the score used held (scopes refi_llpa and purchase_llpa, guard False: the score used also sets the LLPA). The lean goes only where no fit's slopes still differ clearly by FOLLOWS_LEAN or more and no used slope still tops the other by that; on purchases, a fit whose used slope is not the larger has lost it too."""
    m = s.after & s.has_f & s.has_v & ~s.rc & (s.fico >= 640) & (s.fico <= 799) & (s.vs >= 640) & (s.vs <= 799)
    wide = (_joint(s.c_seller, s.c_channel, s.c_week, s.c_agency), _joint(s.c_seller, s.c_channel, s.c_close), _joint(s.c_seller, s.c_purpose), _joint(s.ltvb, s.c_purpose), s.sizeb, s.dtib, s.c_occupancy, s.c_units, s.c_ptype, s.c_state, s.mi.astype(np.int64), s.c_fthb, s.c_borrowers, s.c_program)
    clear = lambda slope, se: np.isfinite(slope) and np.isfinite(se) and abs(slope) > 1.96 * se  # noqa: E731
    fannie, rocket = s.agency == "FNMA", s.seller == ROCKET
    labels = {"rocket_retail": _label(s, names, ROCKET, "R"), "rocket_broker": _label(s, names, ROCKET, "B"), "uwm": names.get(UWM, UWM)}
    scopes = (("all", "All lenders", np.ones(s.n, bool), FOLLOWS_N), ("refi", "Refinances", s.refi, FOLLOWS_N), ("purchase", "Purchases", ~s.refi, FOLLOWS_N), ("fannie", "Fannie alone", fannie, FOLLOWS_GROUP_N), ("fannie_refi", "Fannie refinances", fannie & s.refi, FOLLOWS_GROUP_N), ("fannie_purchase", "Fannie purchases", fannie & ~s.refi, FOLLOWS_GROUP_N),
              ("rocket_retail", labels["rocket_retail"], rocket & (s.channel == "R"), FOLLOWS_GROUP_N), ("rocket_broker", labels["rocket_broker"], rocket & (s.channel == "B"), FOLLOWS_GROUP_N), ("uwm", labels["uwm"], s.seller == UWM, FOLLOWS_GROUP_N))
    rows, held, read, hold = [], {}, {}, {}

    def fit(at, effects):
        fes = [f[at] for f in effects]
        beta, se = _regress(s.bp[at], [s.vs[at] / 20.0, s.fico[at] / 20.0], fes, s.lw[at], tol=1e-8)
        apart, apart_se = _regress(s.bp[at], [(s.vs[at] + s.fico[at]) / 40.0, (s.vs[at] - s.fico[at]) / 40.0], fes, s.lw[at], tol=1e-8)
        return {"n": len(at), "lender_weeks": _weeks(s, at), "on_vs4": beta[0], "on_vs4_se": se[0], "on_fico": beta[1], "on_fico_se": se[1], "diff": apart[1], "diff_se": apart_se[1]}

    def fit_row(scope, label, group, order, x, guard):
        return {"view": "follows_score", "scope": scope, "group": group, "key": f"{scope}|{group}", "label": label, "order": order, "n": x["n"], "lender_weeks": x["lender_weeks"], "on_vs4": _num(x["on_vs4"]), "on_vs4_se": _num(x["on_vs4_se"]),
                "on_fico": _num(x["on_fico"]), "on_fico_se": _num(x["on_fico_se"]), "diff": _num(x["diff"]), "diff_se": _num(x["diff_se"]), "guard": guard, "sentence": None}

    for scope, label, sm, floor in scopes:
        fits = {}
        for group, gm in (("vs4", s.is_v), ("fico", ~s.is_v)):
            x = fit(np.flatnonzero(m & sm & gm), wide)
            used, used_se, other = (x["on_vs4"], x["on_vs4_se"], x["on_fico"]) if group == "vs4" else (x["on_fico"], x["on_fico_se"], x["on_vs4"])
            x["holds"] = bool(x["n"] >= floor and clear(used, used_se) and clear(x["diff"], x["diff_se"]) and abs(used) > abs(other))
            fits[group] = x
        held[scope], read[scope] = all(x["holds"] for x in fits.values()) and (floor == FOLLOWS_GROUP_N or all(x["lender_weeks"] >= THIN_WEEKS for x in fits.values())), fits
        rows += [fit_row(scope, label, group, order, x, held[scope]) for order, (group, x) in enumerate(fits.items())]
        if scope in ("refi", "purchase"):
            llpa = _code(np.round(np.where(s.is_v, s.fee_v, s.fee_f), 4))
            hold[scope] = {group: fit(np.flatnonzero(m & sm & gm), (*wide, llpa)) for group, gm in (("vs4", s.is_v), ("fico", ~s.is_v))}
            rows += [fit_row(f"{scope}_llpa", f"{label}, LLPA of the score used held", group, order, x, False) for order, (group, x) in enumerate(hold[scope].items())]
    near = lambda v: _signed(_near(v))  # noqa: E731
    lean = lambda x, used, other: x["n"] >= FOLLOWS_GROUP_N and len(_finite(x[used], x[other])) == 2 and abs(x[used]) >= FOLLOWS_RATIO_FANNIE * abs(x[other])  # noqa: E731
    leans = lambda fv, ff: lean(fv, "on_vs4", "on_fico") and lean(ff, "on_fico", "on_vs4") and fv["on_vs4"] * ff["on_fico"] > 0  # noqa: E731
    slopes = {"vs4": ("on_vs4", "on_fico"), "fico": ("on_fico", "on_vs4")}
    names_of = {"vs4": "VS4", "fico": "FICO"}
    both = lambda x, group: f"{near(x[slopes[group][0]])} and {near(x[slopes[group][1]])}"  # noqa: E731
    known = lambda fits: len(_finite(*(x[k] for x in fits for k in ("on_vs4", "on_fico", "diff", "diff_se")))) == 4 * len(fits)  # noqa: E731
    gone = lambda x, group: not (clear(x["diff"], x["diff_se"]) and abs(x["diff"]) >= FOLLOWS_LEAN) and abs(x[slopes[group][0]]) - abs(x[slopes[group][1]]) < FOLLOWS_LEAN  # noqa: E731

    def held_words(claimed):
        """What holding the LLPA of the score used does to refinances' slopes and to the groups the purchases line says follow their score. None without the refinance fits."""
        hv, hf = hold["refi"]["vs4"], hold["refi"]["fico"]
        if not known((hv, hf)):
            return None
        on_purchases = {group: hold["purchase"][group] for group in claimed}
        if not known(tuple(on_purchases.values())):
            on_purchases = {}
        refi_gone = gone(hv, "vs4") and gone(hf, "fico")
        one = next(iter(on_purchases)) if len(on_purchases) == 1 else None
        whose = f"{names_of[one]} loans' purchases" if one else "purchases"
        if refi_gone:
            refi = f"on refinances (VS4 loans about {both(hv, 'vs4')}; FICO loans about {both(hf, 'fico')})"
            if not on_purchases:
                return f"hold that LLPA and the lean goes {refi}"
            figures = f"about {both(on_purchases[one], one)}" if one else f"VS4 loans about {both(on_purchases['vs4'], 'vs4')}; FICO loans about {both(on_purchases['fico'], 'fico')}"
            if all(gone(x, group) or abs(x[slopes[group][0]]) <= abs(x[slopes[group][1]]) for group, x in on_purchases.items()):  # slopes that part the other way: its lean has gone, not stayed
                return f"hold that LLPA and the lean goes, {refi} and on {whose} ({figures})"
            return f"hold that LLPA and the lean goes {refi} but not on {whose} ({figures})"
        refi = f"hold that LLPA on refinances and they come to about {both(hv, 'vs4')} on VS4 loans and about {both(hf, 'fico')} on FICO loans"
        if not on_purchases:
            return refi
        figures = f"about {both(on_purchases[one], one)}" if one else f"about {both(on_purchases['vs4'], 'vs4')} on VS4 loans and about {both(on_purchases['fico'], 'fico')} on FICO loans"
        return f"{refi}, and on {whose} to {figures}"

    sentence = None
    if held["refi"] and leans(read["fannie_refi"]["vs4"], read["fannie_refi"]["fico"]):
        v, f = read["refi"]["vs4"], read["refi"]["fico"]
        sentence = f"Which score the rate tracks, per 20 points, on loans with both scores 640 to 799: on refinances, VS4 loans move about {near(v['on_vs4'])} bp on VS4 and {near(v['on_fico'])} on FICO; FICO loans about {near(f['on_fico'])} on FICO and {near(f['on_vs4'])} on VS4."
        v, f = read["purchase"]["vs4"], read["purchase"]["fico"]
        claimed = ()
        if min(v["n"], f["n"]) >= FOLLOWS_N and len(_finite(v["on_vs4"], v["on_fico"], f["on_fico"], f["on_vs4"])) == 4:
            gv, gf = read["fannie_purchase"]["vs4"], read["fannie_purchase"]["fico"]
            at_fannie = lambda x, a, b: f", and about {near(x[a])} and {near(x[b])} at Fannie alone" if x["n"] >= FOLLOWS_GROUP_N and len(_finite(x[a], x[b])) == 2 else ""  # noqa: E731
            if v["holds"] and f["holds"] and leans(gv, gf):
                sentence += " Purchases go the same way."
                claimed = ("vs4", "fico")
            elif f["holds"] and not v["holds"] and lean(gf, "on_fico", "on_vs4") and gf["on_fico"] * f["on_fico"] > 0:
                sentence += f" On purchases FICO loans still follow FICO (about {near(f['on_fico'])} and {near(f['on_vs4'])}); VS4 loans are less clear (about {near(v['on_vs4'])} and {near(v['on_fico'])}{at_fannie(gv, 'on_vs4', 'on_fico')})."
                claimed = ("fico",)
            elif v["holds"] and not f["holds"] and lean(gv, "on_vs4", "on_fico") and gv["on_vs4"] * v["on_vs4"] > 0:
                sentence += f" On purchases VS4 loans still follow VS4 (about {near(v['on_vs4'])} and {near(v['on_fico'])}); FICO loans are less clear (about {near(f['on_fico'])} and {near(f['on_vs4'])}{at_fannie(gf, 'on_fico', 'on_vs4')})."
                claimed = ("vs4",)
            else:
                sentence += f" On purchases VS4 loans move about {near(v['on_vs4'])} on VS4 and {near(v['on_fico'])} on FICO; FICO loans about {near(f['on_fico'])} on FICO and {near(f['on_vs4'])} on VS4."
        at_held = held_words(claimed)
        sentence += f" But the score used also sets the LLPA{f': {at_held}' if at_held else ''}, so this cannot tell a view on credit from the LLPA."
    for r in rows:
        if r["scope"] == "all":
            r["sentence"] = sentence
    return rows


def _llpa_rate(s, names):
    """For the LLPA fold and the workbook's Fees sheet; no rate figure above the fold reads it: bp at the same FICO where the LLPA is lower and where it is the same, by lender and channel, with purpose beside it. Chart 4's reads on chart 4's masks, so a row of all purposes prints what chart 4 prints; the model read and its error stay for the workbook. Figures print only on MIN_ROW+ matched loans on each cell read."""
    v = s.is_v & s.has_f
    rows = []
    groups, counts = np.unique(s.lc[v], return_counts=True)
    order = 0
    for g, n in sorted(zip(groups, counts), key=lambda x: -x[1]):
        if n < MIN_ROW:
            continue
        lc = s.lc == g
        c = s.fic & lc
        i = np.flatnonzero(v & lc)[0]
        label = _label(s, names, s.seller[i], s.channel[i])
        for purpose, label_p, pm in (("all", "All", np.ones(s.n, bool)), ("P", "Purchase", ~s.refi), ("refi", "Refinance", s.refi)):
            row = {"view": "llpa_rate", "key": f"{s.seller[i]}|{s.channel[i]}|{purpose}", "label": label, "purpose": label_p, "order": order, "not_like_for_like": True if s.rc[i] else None}
            for r, flag in (("lower", s.lower), ("same", s.same)):
                t = v & lc & pm & flag
                k = int(t.sum())
                r5, rt = _gap(s.bp, t, c, s.cell_f5), _gap(s.bp, t, c, s.cell_ft)
                row.update({f"{r}_n": k, f"{r}_rough": _weeks(s, t) < THIN_WEEKS, **dict.fromkeys(f"{r}_{field}" for field in ("dot", "lo", "hi", "gap", "se"))})
                if min(r5["n"], rt["n"]) >= MIN_ROW:
                    gap = _mean(s.gap_fico[t & ~np.isnan(s.gap_fico)])
                    _, _, _, dot, lo, hi = _three(r5["est"], rt["est"], gap)
                    row.update({f"{r}_dot": dot, f"{r}_lo": lo, f"{r}_hi": hi, f"{r}_gap": _num(gap), f"{r}_se": _num(_widest(s, s.gap_fico, t))})
            rows.append(row)
            order += 1
    return rows


def _priced_line(s, names):
    """How far below its own number a VS4 loan has priced: the 95% range in words with the rule clause under its guard on the point estimate; then, for the second fold, Rocket's retail channel and UWM, and how many points a bp of gap moves it. For the quote and the workbook, these loans' top two lenders and how many closed by ANNOUNCED's month, and the reads as they came. None on too few loans."""
    below = _priced_below(s, s.fits)
    at, curve = _priced_curve(s)
    whole = _priced_range(s, at, curve) if below else None
    if whole is None:
        return None
    words = lambda r: f"about {r[0]}" if r[0] == r[1] else f"about {r[0]} to {r[1]}"  # noqa: E731
    by_lender = []
    for label, m in ((_label(s, names, ROCKET, "R"), (s.seller == ROCKET) & (s.channel == "R")), (names.get(UWM, UWM), s.seller == UWM)):
        r = _priced_range(s, at, curve, m)
        if r:
            by_lender.append((label, r))
    mean = np.nanmean(curve, axis=0)
    per_bp = (PRICED_K[-1] - PRICED_K[0]) / (mean[0] - mean[-1]) if mean[0] > mean[-1] else None
    shift = f"A 1 bp change in the gap moves this about {_near(per_bp):g} points." if per_bp else None
    if by_lender:
        more = f"Which FICO pays the same (95% ranges, which resample weeks, not lenders, so they run narrow): {', '.join(f'{words(r)} at {label}' for label, r in by_lender)}.{f' {shift}' if shift else ''}"
    else:
        more = f"Which FICO pays the same: {shift[0].lower()}{shift[1:]}" if shift else None
    point = sum(below) / len(below)
    rule = _rule_words(point, whole)
    t = s.is_v & ~s.rc & s.after & (s.vs < 820)
    top, top_share = _top_two(s, names, t)
    return {"stat": f"On average, a FICO {words(whole)} points below the VS4 number (95% range).{f' {rule}' if rule else ''}", "more": more, "range": words(whole), "point": point,
            "whole": whole, "by_lender": by_lender, "per_bp": per_bp, "top": top, "top_share": top_share, "closed": _mean(s.close[t] <= ANNOUNCED)}


def _rule_words(point, ends=None):
    """The rule clause, while how far a VS4 number has priced below itself sits near the old rule. ends: the range printed beside it, which must reach as near."""
    near = VS_OFFSET / 4
    return f"Near the old rule's {VS_OFFSET} points, which does not show the rule caused it." if point is not None and abs(point - VS_OFFSET) <= near and (ends is None or (ends[0] <= VS_OFFSET + near and ends[1] >= VS_OFFSET - near)) else None


def _off20_words(row, dot):
    """The same-number row with 20 points off VS4: the range in text, and whether it fell away: its midpoint under a third of the dot. None without the row."""
    if not row or row["dot_raw"] is None or not dot:
        return None
    return _span(_finite(row["lo_raw"], row["hi_raw"])), abs(row["dot_raw"]) < abs(dot) / 3


def _lender_rates(rows, book):
    """Chart 4's lender groups at the same FICO, Rocket correspondent out: the one lender and channel beside the others' figures, with no word on what that means, while there are 2+ others and it sits LENDER_APART or more from each. Beside them each side's range across the methods: its printed ends, then the others' lowest and highest. None otherwise."""
    groups = [r for r in rows if r["scope"] == "group" and not r.get("not_like_for_like")]
    shown = [r for r in groups if r["same_fico_dot"] is not None]
    top = next((r for r in shown if book and r["label"] == book["label"]), None)
    others = [r for r in shown if r is not top]
    if top is None or len(others) < 2 or any(abs(top["same_fico_dot"] - r["same_fico_dot"]) < LENDER_APART for r in others):
        return None
    ends = [r.get(k) for r in (top, *others) for k in ("same_fico_lo", "same_fico_hi")]
    return {"label": top["label"], "dot": top["same_fico_dot"], "lo": min(r["same_fico_dot"] for r in others), "hi": max(r["same_fico_dot"] for r in others), "rough": any(r["same_fico_rough"] for r in (top, *others)),
            "methods": None if None in ends else (top["same_fico_lo"], top["same_fico_hi"], min(r["same_fico_lo"] for r in others), max(r["same_fico_hi"] for r in others))}


def _about_range(lo, hi):
    return f"about {_signed(lo)}" if lo == hi else f"about {_range(lo, hi)}"


def _refi_mix(s, book, cells, dot):
    """Refinances' share of the same-FICO loans at the one lender and channel and at everyone else, while the two sit REFI_APART or more apart on MIN_ROW+ loans each. Every row holds purpose in its cells, so the groups' purposes differ only in how the row averages them. Then whether its gap, which reads dot, is wider on refinances: "refi" or "purchase" where all three methods agree, whole and at Fannie alone wherever both purposes read there on MIN_ROW+ loans; "split" where the methods part; None where a read is missing or Fannie differs. None otherwise."""
    if not book:
        return None
    t, rest = s.tv & (s.lc == book["lc"]), s.tv & (s.lc != book["lc"])
    if min(t.sum(), rest.sum()) < MIN_ROW or abs(_mean(s.refi[t]) - _mean(s.refi[rest])) < REFI_APART:
        return None
    r5, rt = cells["same_fico"]

    def wider(m):
        out = []
        for g in (r5["g"], rt["g"], s.gap_fico):
            on_refi, on_purchase = g[m & s.refi & ~np.isnan(g)], g[m & ~s.refi & ~np.isnan(g)]
            if min(len(on_refi), len(on_purchase)) < MIN_ROW:
                return None
            out.append(bool((on_refi.mean() < on_purchase.mean()) == (dot < 0)))
        return out

    whole, fannie = wider(t), wider(t & (s.agency == "FNMA"))
    form = None
    if whole:
        form = "split" if len(set(whole)) > 1 else ("refi" if whole[0] else "purchase") if not fannie or set(fannie) == set(whole) else None
    return _mean(s.refi[t]), _mean(s.refi[rest]), form


def _mix_words(label, mix):
    """_refi_mix() in words: the shares, then what the methods say of its gap by purpose."""
    tail = {"split": ", but the methods disagree on whether its gap is wider on refinances", "refi": ", and on all 3 methods its gap is wider on refinances", "purchase": ", and on all 3 methods its gap is wider on purchases"}.get(mix[2], "")
    return f"Refinances are {mix[0]:.0%} of {label}'s loans here and {mix[1]:.0%} of the others'{tail}."


def _lender_rates_line(said, mix=None):
    """_lender_rates() in words: figures only. mix: _refi_mix()."""
    if not said:
        return None
    return f"On rate, at the same FICO: {said['label']} about {_signed(said['dot'])} bp, other groups {_about_range(said['lo'], said['hi'])}{', on few weeks of loans' if said['rough'] else ''}.{' ' + _mix_words(said['label'], mix) if mix else ''}"


def _curve_holds(curve, dot):
    """Whether the FICO gap could explain the same-number figure instead: positive and at least half the figure. curve: _curve_gap()."""
    return bool(curve and dot and dot > 0 and curve[0] > 0 and curve[1] > 0 and curve[1] >= dot / 2)


def _quote(s, rows, book, priced, clause, split, plain, closed=0.0, closed_same=0.0, rc_tops=None, same_at=None, curve=None, lender=None, same_range=None, mix=None, lower_under_top=False):
    """Lines to quote, each standing alone when pasted, each clause under its row's guard. plain: _method_reads(). closed, closed_same: the shares of the same-FICO and same-LLPA loans closed by ANNOUNCED's month. rc_tops: _rc_tops(). same_at, same_range: _same_loans()' figure at the same FICO and its 95% range's printed ends. curve: _curve_gap(). lender: _lender_rates(). mix: _refi_mix(). lower_under_top: whether every lower-LLPA loan sits under the top score cut."""
    f, ll, c = rows["same_fico"], rows["same_llpa"], rows["same_number"]
    out = []
    read = lambda r: r["sentence"].startswith("About")  # noqa: E731
    ran = lambda r: f"about {abs(r['dot']):g} bp {'below' if r['dot'] < 0 else 'above'} FICO loans'" if abs(r["dot"]) >= 1 else "about level with FICO loans'"  # noqa: E731
    thin = lambda r: f"95% range about {_range(*_out95(r['tl'], r['th']))}" if r["tl"] is not None and r["th"] is not None else None  # noqa: E731
    rc_out = bool(s.rc.any())
    tops = rc_tops or {}
    back = lambda r, key: f" Rocket correspondent is left out; with it the top of the range is {_signed(_out95(tops[key], tops[key])[1])}." if rc_out and thin(r) and tops.get(key) is not None and np.isfinite(tops[key]) else ""  # noqa: E731
    grid = _day(GRID_CHANGE)
    if f["sentence"] != TOO_FEW:
        ends = _held_ends(f, plain)
        side = "; ".join(t for t in (thin(f), f"about {_signed(_whole(plain[0]))} with few controls" if ends and ends[0] == plain[0] else None) if t)
        said = f"At the same FICO, lender, channel, timing, purpose and LTV range, VS4 loans {f'issued from {grid} and ' if s.after[s.tv].all() else ''}showing a FICO ran {ran(f)} note rates{f' ({side})' if side else ''}, before points and lender credits, which do not show."
        if lender:
            methods = f" ({_range(*lender['methods'][:2])} and {_range(*lender['methods'][2:])} across the methods)" if lender.get("methods") else ""
            said += f" Most of it is {lender['label']}, about {_signed(lender['dot'])} against {_about_range(lender['lo'], lender['hi'])} at other lender groups{methods}{', on few weeks of loans' if lender['rough'] else ''}.{' ' + _mix_words(lender['label'], mix) if mix else ''}"
        elif book:
            said += f" Most of it is {book['label']}."
        if closed > 0.5:
            said += f" Most of these rates were likely set before the {_day(ANNOUNCED)} announcement of one LLPA grid for both scores."
        low = rows.get("lower_llpa")
        if low and low.get("dot") is not None and ll.get("dot") is not None:
            level = "about level" if abs(ll["dot"]) < 1 else f"about {_signed(ll['dot'])}"
            cause = ", which does not show the LLPA caused it" if read(low) and low["dot"] < 0 and ll["dot"] - low["dot"] >= 3 else ""
            under = rows.get("same_llpa_low")
            part = f" (about {_signed(under['dot'])} below FICO {SCORE_CUTS[-1]}{', where all the lower-LLPA loans sit' if lower_under_top else ''}; {_range(under['lo'], under['hi'])} across the methods)" if under and None not in (under.get("dot"), under.get("lo"), under.get("hi")) else ""
            said += f" Across lenders the gap is about {_signed(low['dot'])} where VS4 has the lower LLPA on the {grid} grid and {level} where the LLPA is the same{part}{cause}."
        out.append(f"{said} Lenders can pick the score, so this shows where a gap sits, not what choosing VS4 is worth.{back(f, 'same_fico')}")
    if ll["sentence"] != TOO_FEW:
        blend = _split_words(split, rows.get("same_llpa_low"))
        range_ = f" ({thin(ll)})" if thin(ll) else ""
        earlier = f" Most of these rates were likely set earlier, when the LLPA grid counted VS4 as {VS_OFFSET} points lower." if closed_same > 0.5 else ""
        out.append(f"At the same FICO, where both scores carry the same LLPA on the {grid} grid, VS4 loans {f'issued from {grid} ' if s.after[s.tv].all() else ''}ran {ran(ll)} note rates{range_}{f': {blend}' if blend else ''}.{earlier}{back(ll, 'same_llpa')}")
    if c["sentence"] != TOO_FEW:
        t = s.is_v & ~s.rc & (s.vs < 820)
        range_ = f" ({thin(c)})" if thin(c) else ""
        first = f" first disclosed from {_day(str(np.unique(s.first_date[t])[0]))}" if t.any() else ""
        across = f", {'higher' if c['dot'] > 0 else 'lower'} {clause.replace(' shown', ' large enough to read')}" if clause and read(c) and abs(c["dot"]) >= 1 else ""
        said = f"At the same score number under 820 (VS4 720 against FICO 720), VS4 loans{first} ran {ran(c)} note rates{range_}{across}{', with Rocket correspondent left out' if rc_out else ''}."
        if read(c) and c["dot"] > 0 and not (read(f) and f["dot"] > 0):
            shows = f" ({f'loans issued from {grid}, ' if curve[3] else ''}{_one_of_these(curve[2], '')})" if curve else ""
            top = _out95(f["tl"], f["th"])[1] if same_range and f.get("tl") is not None and f.get("th") is not None else None
            reach = f" under 820; with 820+ it reaches {_signed(top)}" if top is not None and same_range[1] < 0 <= top else ""
            ends = f" (95% range about {_range(*same_range)}{reach})" if same_range else ""
            where = f": where a FICO shows{shows}, they are about {abs(same_at):g} bp below the rate at their FICO{ends}" if same_at is not None and same_at < 0 else ""
            said += f" That says a VS4 number has got the rate of a lower FICO, not that VS4 costs more{where}."
        high = (s.is_v & ~s.rc & (s.vs >= 820))
        if high.any():
            words = _high_share(s)
            said += f" {words[0].upper()}{words[1:]} {'are' if '%' in words else 'is'} 820+ and not in this figure."
        money = c.get("money")
        out.append(f"{said} The {abs(c['dot']):g} bp is {money[0].lower()}{money[1:]}, before points and lender credits, which do not show." if money else f"{said} Points and lender credits do not show.")
        if priced:
            who, share = priced["top"], priced["top_share"]
            left = " Rocket correspondent left out," if rc_out else ""
            how = f"This is how {_and(who)} {'have' if len(who) > 1 else 'has'} priced,{left} not a conversion." if who and share >= 0.9 else f"This is how these loans have priced,{left} not a conversion."
            timing = f", most with rates likely set while the LLPA grid still counted VS4 as {VS_OFFSET} points lower" if priced["closed"] > 0.5 else ""
            near = f" That is near {f'those {VS_OFFSET} points' if timing else f'the {VS_OFFSET} points the LLPA grid took off VS4 before {grid}'}, which does not show the grid caused it." if _rule_words(priced["point"], priced.get("whole")) else ""
            out.append(f"On average a VS4 number under 820 has got the rate of a FICO {priced['range']} points lower (95% range, too narrow: it resamples weeks, not lenders), on loans issued from {grid}{timing}.{near} {how}")
    return [{"view": "quote", "order": i, "text": t} for i, t in enumerate(out)]


def _top_slope(s):
    """What 20 points of FICO move the rate on FICO loans in the top LLPA tier, every cell control held, in bp."""
    m = s.fic & ~s.rc & (s.fico >= SCORE_CUTS[-1])
    return _regress(s.bp[m], [s.fico[m] / 20.0], [s.cell[m]], s.lw[m])[0][0]


def _llpa_split(s, top_slope):
    """The same-LLPA row at FICO 780+ and under it, the second on the same loans as its own row: the figure as a row prints it, on MIN_ROW+ matched loans on each cell read; the share of the row at FICO 780+; whether rates have stopped falling with the score up there; whether a discount below it is not ruled out: the midpoint and its thin line's low end below zero, and its model or tier read not clear of zero. reads: every part's reads, for the workbook."""
    t, c = s.tv & s.same, s.fic & ~s.rc
    out = {"high": None, "low": None, "flat": bool(np.isfinite(top_slope) and top_slope >= TOP_FLAT), "open": False, "share": _mean(s.fico[t] >= SCORE_CUTS[-1]), "reads": {}}
    clear = lambda v, se: np.isfinite(v) and np.isfinite(se) and abs(v) > 1.96 * se  # noqa: E731
    top = SCORE_CUTS[-1]
    for key, m in (("high", t & (s.fico >= top)), ("low", t & (s.fico < top)), ("under", t & (s.fico < SCORE_CUTS[0]))):
        r5, rt = _gap(s.bp, m, c, s.cell_f5, (s.lw,)), _gap(s.bp, m, c, s.cell_ft, (s.lw,))
        ok = m & ~np.isnan(s.gap_fico)
        model = _mean(s.gap_fico[ok])
        if min(r5["n"], rt["n"]) < MIN_ROW:
            continue
        mid = (r5["est"] + rt["est"]) / 2
        out["reads"][key] = {"cell5": _num(r5["est"]), "tier": _num(rt["est"]), "model": _num(model), "mid": _num(mid), "n": int(m.sum()), "read5": r5["n"], "read_tier": rt["n"]}
        if key in ("high", "low"):
            out[key] = _three(r5["est"], rt["est"], model)[3]
        if key == "low":
            tl = _thin_mid(r5, rt, s.lc)[0]
            out["open"] = bool(mid < 0 and np.isfinite(tl) and tl < 0 and not (clear(rt["est"], rt["se"][0]) and clear(model, _cluster_se(s.gap_fico[ok], s.lw[ok]))))
    return out


def _full_value(s):
    """Below FICO 780 on the same-LLPA row, on loans with both model reads: what the gap would be at full credit for the VS4 number, and on how many loans."""
    known = s.tv & s.same & (s.fico < SCORE_CUTS[-1]) & ~np.isnan(s.gap_fico) & ~np.isnan(s.gap_number)
    return _mean(s.gap_fico[known] - s.gap_number[known]), int(known.sum())


def _expected(s, top_slope, row):
    """How much to expect at the same LLPA, from the loans' own curves, while enough of the row sits where rates have stopped falling with the score and full credit below that would sit below zero. row: the row under FICO 780, which needs all three methods. None where the figures say none of the three things."""
    share = _mean(s.fico[s.tv & s.same] >= SCORE_CUTS[-1])
    if not (np.isfinite(top_slope) and top_slope >= TOP_FLAT and share >= EXPECT_SHARE) or None in (row["cell5"], row["tier"], row["model"]):
        return None
    return _expected_words(_full_value(s)[0], row["lo"], row["hi"])


def _expected_words(credit, lo, hi):
    """credit: what the gap would be below FICO 780 at full credit for the VS4 number. lo, hi: the row there, as it prints. Each ending goes with where those ends sit against the printed credit and zero."""
    if lo is None or hi is None or not np.isfinite(credit) or not _near(credit) < 0:
        return None
    credit = _near(credit)
    if lo <= credit <= hi and lo <= 0 <= hi:
        end = "so this row cannot tell full credit from none"
    elif hi <= credit:
        end = "so this row is at or past full credit"
    elif lo > credit and lo <= 0 <= hi:
        end = "so this row falls short of full credit"
    else:
        return None
    return f"How much to expect: below FICO {SCORE_CUTS[-1]}, full credit for the VS4 number (priced like the same FICO number) would be about {_signed(credit)}, against {_range(lo, hi)} across the methods, {end}."


def _test_line(check):
    """The rare_high_vs4 check in words: on a miss the figure is past the limit as printed, so the sentence cannot contradict itself. A lender at or below RARE_BORROWERS is named as thin evidence, as 'there' while every lender printed is."""
    v = check["value"]
    if v is None or check["pass"] is None:
        return None
    head = f"A test: FICO loans with VS4 {RARE_ABOVE}+ above their FICO should show about 0 if a high VS4 lowers the rate only when it is the score picked."
    if not check["pass"]:
        past = _near(v) if abs(_near(v)) > check["limit"] else float(np.sign(v) * np.ceil(abs(v) * 2) / 2)
        return f"{head} They show {_signed(past)} at lenders that rarely use VS4, past the {check['limit']:g} bp limit, so treat these figures with care."
    shown, named, low, few = [f"about {_signed(_near(v))} at lenders that rarely use VS4"], [], [], []
    for name, k in (("Rocket", "rocket"), ("UWM", "uwm")):
        n = check[f"{k}_n"]
        if n >= RARE_BESIDE and check[k] is not None:
            by = sorted(((check[f"{k}_{ch}_n"], check[f"{k}_{ch}"], ch) for ch in ("correspondent", "broker") if (check.get(f"{k}_{ch}_n") or 0) >= RARE_CHANNEL and check.get(f"{k}_{ch}") is not None), key=lambda x: -x[0])
            split = f" ({', '.join(f'about {_signed(_near(x))} on its {count:,} {ch} loans' for count, x, ch in by)})" if len(by) > 1 else ""
            shown.append(f"about {_signed(_near(check[k]))} at {name} on {_count(n, 'loan')}{split}")
            named.append(name)
            if check[k] <= RARE_BORROWERS:
                low.append(name)
        elif n:
            few.append(f"{name} has too few such loans to test ({n:,}).")
    evidence = f": thin evidence that a high VS4 goes with a lower rate {'there' if low == named else f'at {_and(low)}'} even on FICO loans" if low else ""
    return " ".join([f"{head} They show {_and(shown)}{evidence}.", *few])


def _no_stake_share(s):
    """On the loans the same-number chart draws, the share of the line where VS4 less 20 lands the same LLPA that has a high VS4 or a low LTV."""
    m = s.is_v & ~s.rc & (s.vs >= 640) & (s.vs < 820) & ~s.stake & (s.close >= MONTHS_FROM)
    return _mean((s.vs[m] >= NO_STAKE_VS) | (s.ltvb[m] <= LTV_CUTS.index(NO_STAKE_LTV)))


def _curve_gap(s):
    """On VS4 loans under 820 showing a FICO with both reads: how far VS4 sits above FICO, and what that distance is worth on FICO loans' curve; the share of the same-number row's loans that show a FICO; and whether all of those are issued from GRID_CHANGE."""
    shown = s.tv & (s.vs < 820)
    m = shown & ~np.isnan(s.gap_number) & ~np.isnan(s.gap_fico)
    return _mean(s.vs[m] - s.fico[m]), _mean(s.gap_number[m] - s.gap_fico[m]), shown.sum() / max((s.is_v & ~s.rc & (s.vs < 820)).sum(), 1), bool(s.after[shown].all())


def _the_number(dot):
    """The same-number figure in a sentence: by its value, or in words where it prints as zero."""
    return f"the {_signed(dot)}" if dot else "the same-number figure"


def _blend(number):
    """The chart's two groups' loan-weighted means, from the month rows: where the old rule would raise the LLPA, and the rest. None for a group with no figure."""
    means = {}
    for group in ("stake", "no_stake"):
        months = [r for r in number if r["scope"] == "month" and r["group"] == group and r.get("dot_raw") is not None]
        weight = sum(r["n"] for r in months)
        means[group] = sum(r["dot_raw"] * r["n"] for r in months) / weight if weight else None
    return means["stake"], means["no_stake"]


def _number_lines(number, dot, share, off20=None, curve=None, part=None):
    """Where the same-number figure sits, from the month rows, as two lines. First the two groups' loan-weighted means, while the figure sits between them, with what the second has while most of it has a high VS4 or a low LTV. Then what is left with 20 points off VS4, and what the FICO gap could explain instead, while it is at least half the figure. off20: _off20_words(). curve: _curve_gap(). part: the chart's share of the row's loans."""
    upper, lower = _blend(number)
    if dot is None or upper is None or lower is None or not np.isfinite(share) or not min(upper, lower) - 0.5 <= dot <= max(upper, lower) + 0.5:
        return None, None
    mostly = f" (mostly VS4 {NO_STAKE_VS}-819 or LTV {NO_STAKE_LTV} or under)" if share >= 0.5 else ""
    chart = f"VS4 {SCORE_CUTS[0]}-819"
    where = f"{chart} is about {part:.0%} of {_the_number(dot)}'s loans:" if part is not None and np.isfinite(part) else f"On {chart}, {_the_number(dot)} averages"
    two = f"{where} about {_signed(_near(upper))} where the old rule would raise the LLPA and about {_signed(_near(lower))} on the rest{mostly}."
    out = []
    fell = bool(off20 and off20[1])
    if fell:
        out.append(f"Take {VS_OFFSET} points off VS4 and the {_signed(dot)} falls to about {off20[0]}, which fits.")
    elif off20:
        out.append(f"Take {VS_OFFSET} points off VS4 and it is about {off20[0]}.")
    if _curve_holds(curve, dot):
        far, bp = _five(curve[0]), _near(curve[1])
        shown = f"where a FICO shows ({f'loans issued from {_day(GRID_CHANGE)}, ' if curve[3] else ''}{_one_of_these(curve[2], '')}), it averages about {far} below VS4, worth about {bp:g} bp on FICO loans"
        out.append(f"But {shown}, and the data cannot separate the rule from the lower FICO." if fell else f"{shown[0].upper()}{shown[1:]}.")
    return two, f"Is the old rule why? {' '.join(out)}" if out else None


def _number_bands(number, share, like):
    """VS4 820+, while its row has loans and a flag. share and like: _high_share() and _high_like()."""
    over = next(r for r in number if r["key"] == "over820")
    if not over["pool"] or not over.get("flag"):
        return None
    return f"Left out: VS4 820+, {share}, {like}."


def _equivalent_caption(bands, top, top_share):
    """What the equivalent is and is not, the first sentence while its guard holds. top, top_share: _top_two()."""
    if all(r["eq"] is None for r in bands):
        return None
    out = []
    band = next(r for r in bands if r["band"] == EQ_BAND)
    if band["fico_rare"] is not None and band["fico_mean"] is not None and band["fico_rare"] - band["fico_mean"] >= EQ_RUNS_HIGH:
        who = _and(top) if len(top) == 2 and top_share >= 0.9 else "these lenders"
        out.append(f"VS4 loans at {who} sit well above FICO: a VS4 of {EQ_BAND} goes with a FICO near {_whole(band['fico_mean']):.0f} there and near {_whole(band['fico_rare']):.0f} at lenders that rarely use VS4.")
    out.append("This is how these lenders have priced, not a conversion.")
    return " ".join(out)


def _llpa_less(s, fee=None, within=None):
    """How much lower the LLPA is where VS4 lowers it, in bp of balance: the grid is in percent of balance. fee: the LLPA VS4 lands, if not the grid since GRID_CHANGE's. within: one lender and channel."""
    m = s.tv & s.lower if within is None else s.tv & s.lower & within
    return _mean(s.fee_f[m] - (s.fee_v if fee is None else fee)[m]) * 100


def _llpa_by_lender(s, rows):
    """Rocket's retail channel and UWM's broker channel where VS4 lowers the LLPA: the rate's range, and the LLPA on the old rule in bp of rate. Nothing unless both read and their ranges do not touch."""
    out = []
    for seller, channel in ((ROCKET, "R"), (UWM, "B")):
        r = next((x for x in rows if x["key"] == f"{seller}|{channel}|all"), None)
        on = _llpa_less(s, s.fee_20, (s.seller == seller) & (s.channel == channel)) / RATE_MULT
        if not r or r["lower_lo"] is None or r["lower_hi"] is None or not np.isfinite(on):
            return []
        out.append((r["label"], r["lower_lo"], r["lower_hi"], on))
    return out if out[0][2] < out[1][1] or out[1][2] < out[0][1] else []


def _llpa_sum(x, then, closed, lower_llpa, by_lender=()):
    """The sum an analyst will do, for the LLPA fold and the workbook's Fees sheet; no rate figure above the fold reads it. x and then: _llpa_less() on the grid since GRID_CHANGE and on the old rule before it. closed: the share of these rates set by ANNOUNCED's month, past half of which the old rule gets its clause and the lenders theirs. by_lender: _llpa_by_lender()."""
    lo, hi = lower_llpa["lo"], lower_llpa["hi"]
    if not x > 0 or lo is None or hi is None:
        return None
    old = f"; on the old rule in force when most of these rates were likely set, about {_near(then):g} bp, about {_near(then / RATE_MULT):g} bp of rate" if closed > 0.5 and np.isfinite(then) else ""
    out = (f"Where VS4 lowers the LLPA, the LLPA is about {_near(x):g} bp of balance lower on today's grid, about {_near(x / RATE_MULT):g} bp of rate at the rule of thumb of {RATE_MULT} bp of LLPA to 1 bp of rate{old}. "
           f"The rate itself differs by about {_range(lo, hi)} bp. The files cannot tell where any difference goes: points, lender credits or the lender's margin.")
    if len(by_lender) == 2 and closed > 0.5:
        (a, a_lo, a_hi, a_on), (b, b_lo, b_hi, b_on) = by_lender
        out += f" By lender it is not even: {a} {_range(a_lo, a_hi)} against an old-rule LLPA gap worth about {_near(a_on):g} bp of rate, {b} {_range(b_lo, b_hi)} against about {_near(b_on):g}."
    return out


def _llpa_share(s):
    """Of loans issued from GRID_CHANGE showing both scores, whichever priced them, the share where VS4's LLPA is lower."""
    m = s.after & s.has_f & s.has_v & ~s.rc
    return f"VS4's LLPA is lower on about {_mean(s.fee_v[m] < s.fee_f[m]):.0%} of all loans showing both scores, whichever score priced them." if m.sum() >= MIN_ROW else None


def _lock_reads(s, book=None):
    """The same comparison on the old rule, on loans closed by ANNOUNCED's month: where it would have put the LLPA below that of the loan's FICO and where it would have matched it; where it would have matched it, also that lender and channel and the rest. Each on all three methods and MIN_ROW+ matched loans, else None."""
    t = s.tv & (s.close <= ANNOUNCED)
    c = s.fic & ~s.rc

    def reads(m):
        r5, rt = _gap(s.bp, m, c, s.cell_f5), _gap(s.bp, m, c, s.cell_ft)
        model = _mean(s.gap_fico[m & ~np.isnan(s.gap_fico)])
        if len(_finite(r5["est"], rt["est"], model)) < 3 or min(r5["n"], rt["n"]) < MIN_ROW:
            return None
        return {"cell5": r5["est"], "tier": rt["est"], "model": model, "n": int(m.sum()), "read5": r5["n"], "read_tier": rt["n"]}

    lower, same = t & (s.fee_20 < s.fee_f), t & (s.fee_20 == s.fee_f)
    out = {"lower": reads(lower), "same": reads(same), "book": None, "rest": None}
    if book:
        out["book"], out["rest"] = reads(same & (s.lc == book["lc"])), reads(same & (s.lc != book["lc"]))
    return out


def _rule_at_lock(s, closed, book=None, rows=None):
    """_lock_reads() in words. closed: the share of the same-FICO loans closed by ANNOUNCED's month, past half or nothing is said. book: _book(). rows: _read_rows(): the split looks the same only while the old rule's lower midpoint sits 3+ bp below its same midpoint, today's lower dot 3+ bp below today's same dot, and the two splits within three bp of each other."""
    if not closed > 0.5:
        return None
    lock = _lock_reads(s, book)
    if not lock["lower"] or not lock["same"]:
        return None
    span = lambda r: _half_span([r["cell5"], r["tier"], r["model"]])  # noqa: E731
    mid = lambda r: (r["cell5"] + r["tier"]) / 2  # noqa: E731
    now = (rows["lower_llpa"]["dot"], rows["same_llpa"]["dot"]) if rows else (None, None)
    alike = ", so the split looks much the same" if None not in now and now[0] <= now[1] - 3 and mid(lock["lower"]) <= mid(lock["same"]) - 3 and abs((now[1] - now[0]) - (mid(lock["same"]) - mid(lock["lower"]))) <= 3 else ""
    out = f"On the old rule, in force when most of these rates were likely set: on loans closed by {_month(ANNOUNCED)}, about {span(lock['lower'])} where it would have put the LLPA below its FICO's and about {span(lock['same'])} where it would have matched it{alike}."
    if lock["book"] and lock["rest"]:
        out += f" Where it would have matched it: {book['label']} about {span(lock['book'])}, the rest about {span(lock['rest'])}."
    return out


def _rc_shares(s):
    """Rocket correspondent's shares of loans at a low rate, VS4 loans then FICO loans, and the reason it has its own row. None while the two sit under RC_APART apart."""
    v, f = s.rc & s.is_v, s.rc & s.fic
    if v.sum() < MIN_ROW or f.sum() < MIN_ROW:
        return None
    on_v, on_f = _mean(s.y[v] <= LOW_RATE), _mean(s.y[f] <= LOW_RATE)
    if abs(on_v - on_f) < RC_APART:
        return None
    return on_v, on_f, f"{_pct(on_f)} of its FICO loans carry a rate of {LOW_RATE:g}% or lower, against {_pct(on_v)} of its VS4 loans"


def _stamp(agencies=("FNMA", "FHLMC"), has_rc=True):
    """What VS4 loans are set against. agencies: the sample's GSEs. has_rc: whether the sample holds any Rocket correspondent loan."""
    gses = [name for code, name in (("FNMA", "Fannie"), ("FHLMC", "Freddie")) if code in agencies]
    return f"VS4 loans (those priced on VS4{', Rocket correspondent left out' if has_rc else ''}) are compared with FICO loans of the same lender, channel, week first disclosed, closing month, GSE, purpose, LTV range and score (within 5 points or one LLPA tier), where a match exists, on 30-year fixed {f'{gses[0]} ' if len(gses) == 1 else ''}loans."


def _newest_file(con):
    return con.execute("SELECT max(file_date) FROM loan_records WHERE kind = 'intraday'").fetchone()[0]


def _behind(s, rows, cells, split, book, at_book, rest, loans, plain, match, expected, lock, priced, blend, curve, rc_tops=None, mix=None):
    """One row per figure that exists only in words, for the workbook: which line prints it, or "Workbook only" where none does now, what it is, and its reads, loans and range where it has them. A row with no figure stays out. Each argument is what its line printed from: None or empty where the line did not print."""
    out = []
    fields = ("cell5", "tier", "model", "mid", "n", "read5", "read_tier", "value", "lo", "hi")

    def add(key, sentence, what, **got):
        got = {k: None if v is None else _num(v) if k not in ("n", "read5", "read_tier") else int(v) for k, v in got.items()}
        if any(got.get(k) is not None for k in ("cell5", "tier", "model", "mid", "value", "lo", "hi")):
            out.append({"view": "behind", "order": len(out), "key": key, "sentence": sentence, "what": what, **dict.fromkeys(fields), **got})

    def three(r5, rt, model=None):
        mid = _finite(r5["est"], rt["est"])
        return {"cell5": r5["est"], "tier": rt["est"], "model": model, "mid": sum(mid) / len(mid) if mid else None, "read5": r5["n"], "read_tier": rt["n"]}

    def at_loans(m):
        r5, rt = cells["same_fico"]
        reach = lambda g: g[m & ~np.isnan(g)]  # noqa: E731
        a, b = reach(r5["g"]), reach(rt["g"])
        mid = _finite(_mean(a), _mean(b))
        return {"cell5": _mean(a), "tier": _mean(b), "model": _mean(s.gap_fico[m & ~np.isnan(s.gap_fico)]), "mid": sum(mid) / len(mid) if mid else None, "n": int(m.sum()), "read5": len(a), "read_tier": len(b)}

    if rows["same_llpa"]["sentence"] != TOO_FEW and _split_words(split):
        for key, name, head, label in (("high", "from_780", "What to quote, same LLPA", f"Same LLPA, FICO {SCORE_CUTS[-1]}+"), ("under", "under_640", "Workbook only", f"Same LLPA, FICO under {SCORE_CUTS[0]}, part of the figure under {SCORE_CUTS[-1]}")):
            if key in split["reads"]:
                add(f"same_llpa_{name}", head, label, **split["reads"][key])
    if _book_grows(book, at_book):
        for r in at_book:
            add(f"book_{r['key']}", "Same FICO", f"{book['label']}, {r['label']}", **{k: r[k] for k in ("cell5", "tier", "model", "mid", "n", "read5", "read_tier")})
        for r in rest:
            if r["dot"] is not None:
                add(f"rest_{r['key']}", "The further VS4 sits above FICO", f"All but {book['label']}, {r['label']}", **{k: r[k] for k in ("cell5", "tier", "model", "mid", "n", "read5", "read_tier")})
    if loans:
        head = "VS4 loans under 820 that show a FICO"
        r5, rt, gap, tl, th = loans["at_fico"]
        add("same_loans_fico", head, "Those loans at the same FICO, with the 95% range", **three(r5, rt, gap), n=int(loans["t"].sum()), lo=tl, hi=th)
        if loans["at_number"]:
            n5, nt, gap = loans["at_number"]
            add("same_loans_number", head, "Those loans at the same score number", **three(n5, nt, gap), n=int(loans["t"].sum()))
    if book and book["closed"]:
        t = s.tv & (s.lc == book["lc"])
        for m, _, _ in book["closed"]:
            add(f"book_closed_{m[:7]}", "Over time", f"{book['label']}, closed in {_month(m)}", **at_loans(t & (s.close == m)))
        if book["rest"]:
            add("book_rest", "Over time", "All other lenders and channels together", **at_loans(s.tv & ~t))
    if book and mix:
        t = s.tv & (s.lc == book["lc"])
        add("book_refi", "On rate, at the same FICO", f"{book['label']}, refinances", **at_loans(t & s.refi))
        add("book_purchase", "On rate, at the same FICO", f"{book['label']}, purchases", **at_loans(t & ~s.refi))
    if plain:
        add("method_plain", "Controls", "Same FICO with only lender, channel, week, GSE and FICO held", value=plain[0])
        add("method_regression", "Controls", "Same FICO in a simple regression", value=plain[1])
    if match:
        add("match_with", "Workbook only", "Model, on loans with a FICO loan within 5 points", value=match[0], n=match[1])
        add("match_without", "Workbook only", "Model, on loans without one", value=match[2], n=match[3])
    if expected:
        add("expected_credit", "How much to expect", "The gap below FICO 780 at full credit for the VS4 number", value=expected[0], n=expected[1])
    if lock:
        for key, what in (("lower", "Old rule would have put the LLPA below its FICO's"), ("same", "Old rule would have matched it"), ("book", f"Matched it, {book['label'] if book else ''}"), ("rest", "Matched it, the rest")):
            if lock[key]:
                r = lock[key]
                add(f"lock_{key}", "On the old rule", what, **r, mid=(r["cell5"] + r["tier"]) / 2)
    if priced:
        add("crossing", "Points below the VS4 number", "Points below its number a VS4 loan has priced, with the 95% range", value=priced["point"], lo=priced["whole"][2], hi=priced["whole"][3])
        for label, r in priced["by_lender"]:
            add(f"crossing_{label.lower().replace(' ', '_')}", "Which FICO pays the same", f"The same at {label}", lo=r[2], hi=r[3])
        if priced["per_bp"]:
            add("crossing_per_bp", "Which FICO pays the same", "Points that one bp of gap moves it", value=priced["per_bp"])
    if blend:
        add("blend_stake", f"VS4 {SCORE_CUTS[0]}-819", "Same score number where the old rule would raise the LLPA", value=blend[0])
        add("blend_rest", f"VS4 {SCORE_CUTS[0]}-819", "Same score number on the rest", value=blend[1])
    if curve:
        add("curve_points", "Is the old rule why?", "Points VS4 sits above FICO where a FICO shows", value=curve[0])
        add("curve_bp", "Is the old rule why?", "What that is worth on FICO loans, in bp", value=curve[1])
    for key, head, label in (("same_fico", "What to quote, same FICO", "same FICO"), ("lower_llpa", "The thin line", "lower LLPA"), ("same_llpa", "What to quote, same LLPA", "same LLPA")):
        if rc_tops and rows[key]["dot"] is not None and rows[key]["th"] is not None:
            add(f"rc_back_{key}", head, f"With Rocket correspondent back, 95% high, {label}", hi=rc_tops[key])
    return out


def build_rates(con, closing=None) -> list[dict]:
    s = _sample(con)
    if s.train.sum() < MIN_N:
        return []  # too few FICO loans to fit a model
    s.fits = _fit_all(s)
    names = dict(con.execute("SELECT id, short FROM entity_names").fetchall())
    rows, cells = _read_rows(s)
    book = _book(s, names, rows, cells)
    at_book, rest = (_by_gap(s, s.lc == book["lc"], GAP_BANDS[1:]), _by_gap(s, s.lc != book["lc"], GAP_BANDS)) if book else ([], [])
    bands = _equivalent(s, s.fits)
    cuts = _cut(s, names)
    gaps = _fico_gap(s)
    beside = _milliman(con, s, names)
    steps, number, checks = _steps(s), _same_number(s, _in_share(con, s, closing)), _checks(s, rows)
    lenders = _lender(s, names)
    llpa_rows = _llpa_rate(s, names)
    follows = _follows(s, names)
    as_of = str(np.unique(s.first_date)[-1])
    by_key = {r["key"]: r for r in beside}
    mid = lambda r: sum(_finite(r["cell5"], r["tier"])) / max(len(_finite(r["cell5"], r["tier"])), 1)  # noqa: E731
    milliman_line = said = None
    if _finite(by_key["window"]["cell5"], by_key["window"]["tier"]) and _finite(by_key["from_oct"]["cell5"], by_key["from_oct"]["tier"]):
        now = _and([names.get(x, x) for x in (ROCKET, UWM) if (s.is_v & (s.seller == x)).any()])
        late = by_key["window_late"]
        back = f" (about {_signed(_near(mid(late)))} on those first disclosed from {_day(WEEKLY_START)}, where the other figures here start)" if _finite(late["cell5"], late["tier"]) else f" (which reaches back before {_day(WEEKLY_START)})" if by_key["window"]["reaches_back"] else ""
        basis = (f"Not the same comparison: Milliman takes 20 points off VS4 first and holds the LLPA. On that basis, with channel and finer score bands held, about {_signed(_near(mid(by_key['window'])))} on loans closed and issued May to August, its window{back}, "
                 f"and about {_signed(_near(mid(by_key['from_oct'])))} on {now} loans issued from {_day(GRID_CHANGE)}.")
        milliman_line = basis
        if _finite(by_key["window_plain"]["cell5"], by_key["window_plain"]["tier"]):
            milliman_line += f" Without channel, with VS4 820+{' and Rocket correspondent' if by_key['window_plain']['rc_kept'] else ''} kept, about {_signed(_near(mid(by_key['window_plain'])))} in its window; any gap left to its figure is not explained here."
        if rows["same_number"]["dot"] is not None:
            said = f"{basis} Same score number under 820 is about {_signed(rows['same_number']['dot'])} bp, data through {_day(as_of)}. See Rates."
    newest = _newest_file(con)
    closed = _mean(s.close[s.tv] <= ANNOUNCED)
    rc = _rc_shares(s)
    top, top_share = _top_two(s, names)
    line_rows, line = _rocket_line(s, names)
    past_rows = _past(s, names)
    top_slope = _top_slope(s)
    split = _llpa_split(s, top_slope)
    between = _between(s, rows)
    clause = _lender_clause(s, names, rows["same_number"]["dot"], [r for r in lenders if r["scope"] == "group" and not r.get("not_like_for_like")])
    plain = _method_reads(s)
    follow = next((r for r in follows if r["scope"] == "all"), {})
    answer = _answer(rows, book, clause, between, gaps, split, plain, at_book)
    priced = _priced_line(s, names) if rows["same_number"]["sentence"] != TOO_FEW else None
    less20 = next(r for r in number if r["scope"] == "less20")
    off20 = _off20_words(less20, rows["same_number"]["dot"])
    curve = _curve_gap(s)
    v_under = s.is_v & ~s.rc & (s.vs < 820)
    number_blend, number_why = _number_lines(number, rows["same_number"]["dot"], _no_stake_share(s), off20, curve, (v_under & (s.vs >= SCORE_CUTS[0])).sum() / max(v_under.sum(), 1))
    loans = _same_loans(s, rows) if between else None
    rc_tops = _rc_tops(s)
    limits = _limits(s, rows, cells, book, names, line, _past_line(past_rows, names), loans, plain, closed, rc_tops)
    limit = {r["key"]: r["text"] for r in limits}
    expected, rule_at_lock = _expected(s, top_slope, rows["same_llpa_low"]), _rule_at_lock(s, closed, book, rows)
    test_line = _test_line(next(r for r in checks if r["key"] == "rare_high_vs4"))
    lender_rates = _lender_rates(lenders, book)
    mix = _refi_mix(s, book, cells, lender_rates["dot"]) if lender_rates else None
    meta = {"view": "meta", "shape": RATES_SHAPE, "as_of": as_of, "answer": " ".join(t for _, t in answer), "stamp": _stamp(set(s.agency), bool(s.rc.any())), "rc_reason": rc[2] if rc else None, "sample": _sample_line(s),
            "stamp_more": ("Three methods: exact match with a 5-point score band; exact match with one LLPA tier as the band (20 points under 640); and a model fitted on FICO loans, by lender and channel where possible, that also controls for "
                           f"{MODEL_HOLDS}. The dot is the midpoint of the first two and the bar the range across all three. Closing month is estimated from the first payment date. The grid matches Fannie Mae's matrix of {_day(GRID_MATRIX, True)}."),
            "dated": f"Data through {_day(as_of, True)}.", "changed": f"Replaces the rate figures shown here before {_day(RATES_CHANGED)}, which blended two comparisons, and restates the dated figures of {_day(RATES_CHANGED)} with Rocket correspondent out of every all-lender row, the LLPA tier split under {SCORE_CUTS[0]} and the 95% range on the estimate.", "said_check": said, "milliman_line": milliman_line,
            "expected": expected, "rule_at_lock": rule_at_lock, "test_line": test_line, "offset_tail": ", though most of these rates were likely set before it" if closed > 0.5 else None,
            "score_lead": "Each test below stops short." if any((follow.get("sentence"), limit.get("same_loans"), limit.get("line"), limit.get("past"), expected, rule_at_lock, test_line)) else None,
            "number_blend": number_blend, "number_why": number_why, "number_caption": " ".join(t for t in (number_blend, number_why) if t) or None, "number_bands": _number_bands(number, _high_share(s), _high_like(s)), "gap_line": _gap_line(gaps, number, book, at_book, rest), "lender_line": _lender_line(lenders), "lender_rates": _lender_rates_line(lender_rates, mix),
            "equivalent_stat": priced["stat"] if priced else None, "equivalent_more": priced["more"] if priced else None, "equivalent_caption": _equivalent_caption(bands, top, top_share),
            "llpa_sum": _llpa_sum(_llpa_less(s), _llpa_less(s, s.fee_20), closed, rows["lower_llpa"], _llpa_by_lender(s, llpa_rows)), "llpa_share": _llpa_share(s),
            "provisional_from": newest.isoformat() if newest else as_of, "n_loans": s.n, "n_vs4": int(s.is_v.sum()), "n_vs4_fico": int((s.is_v & s.has_f).sum()), "n_under_820": int((s.is_v & (s.vs < 820)).sum()), "n_lender_channels": s.n_own}
    quotes = _quote(s, rows, book, priced, clause, split, plain, closed, _mean(s.close[s.tv & s.same] <= ANNOUNCED), rc_tops, loans["dot"] if loans else None, curve, lender_rates, _out95(*loans["at_fico"][3:]) if loans else None, mix, not (s.tv & s.lower & (s.fico >= SCORE_CUTS[-1])).any())
    lock = _lock_reads(s, book) if rule_at_lock else None
    behind = _behind(s, rows, cells, split, book, at_book, rest, loans, plain if limit.get("method") else None, _match_reads(s, cells), _full_value(s) if expected else None, lock, priced, _blend(number) if number_blend else None, curve if _curve_holds(curve, rows["same_number"]["dot"]) and number_why else None, rc_tops, mix)
    out = [meta, *rows.values(), *({"view": "answer", "order": i, "key": k, "text": t} for i, (k, t) in enumerate(answer)), *limits, *line_rows, *past_rows, *steps, *number, *gaps, *bands, *lenders, *cuts, *checks, *beside, *follows, *llpa_rows, *quotes, *behind]
    keys = sorted({k for r in out for k in r})
    return [{k: r.get(k) for k in keys} for r in out]
