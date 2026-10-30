"""Why lenders differ: where each stands on the way to pricing on VS4, and what goes with it.

From every record that carries the Pricing Indicator (scw, scores.py). Some lenders show both scores far less often at
Freddie Mac, so a lender's share with both scores is read at Fannie Mae where it has MIN_N+ loans.

Stages, for each seller:
  pricing  prices on VS4 at least half the time VS4 is higher (MIN_N+ such loans)
  some     at least a tenth of the time
  both     shows both scores on STAGE_BOTH+ of its loans but rarely prices on VS4
  trace    shows one score, with a few VS4 loans
  fico     shows only Classic FICO
Its rule, from its loans with both scores (MIN_N+ loans in each band): whenever, priced on VS4 at least RULE_HIGH of the
time with VS4 1-19 points above FICO in the latest weeks; moving, at least RULE_HIGH at 20+ points and up RULE_MOVE or more
below the line; line, at least RULE_HIGH at 20+ points; some, at least a tenth at 20+; rare, less.

  lender_stage  view lender: the LENDER_TOP largest sellers and every seller past the first stages with MIN_LIST+ loans, with the split of
                its loans (FICO only, both priced on FICO, both priced on VS4, VS4 only) overall and at each GSE.
                view stage, kind (ownership: reference/sellers.csv, else from the name), lead (the channel with half or
                more of its loans): lenders, share of loans, share with both scores, VS4's share.
                view channel: by channel, the two largest VS4 sellers apart from the rest.
                view trait: the share priced on VS4 among loans with VS4 above FICO, by loan trait, for all lenders, the
                two largest VS4 sellers and the rest: how much a trait matters inside a lender.
  statements    reference/statements.csv: what companies and analysts have said, with links
  lender_mix    the same lenders by GSE (+ All) and by week first disclosed (from WEEK_FROM) or issue month: loans, with Classic FICO only (fo), both priced on FICO (bf),
                both priced on VS4 (bv), VS4 only (vo)
"""
import csv
import re
from datetime import timedelta

from . import paths
from .lenders import SELLERS_CSV
from .scores import WEEK_FROM

RECENT_WEEKS = 2
MIN_N = 20
MIN_LIST = 100
LENDER_TOP = 60
STAGE_BOTH = 0.05
RULE_HIGH = 0.6
RULE_MOVE = 0.05
STATEMENTS_CSV = paths.REPO / "reference" / "statements.csv"
STAGES = [("pricing", "Uses VS4 most of the time its score is higher"), ("some", "Uses VS4 some of the time its score is higher"),
          ("both", "Shows both scores, rarely uses VS4"), ("trace", "Shows one score, a few VS4 loans"),
          ("fico", "Shows only Classic FICO")]
CHANNELS = {"R": "Retail", "B": "Broker", "C": "Correspondent"}
PURPOSES = {"P": "Purchase", "C": "Cash-out refinance", "R": "No cash-out refinance"}
KIND_ORDER = ["Bank", "Nonbank", "Builder", "Credit union", "Housing agency"]


def _kind(name: str, listed: str | None) -> str:
    if listed:
        return listed
    n = name.upper()
    if re.search(r"CREDIT UNION|\bFCU\b", n):
        return "Credit union"
    if re.search(r"HOUSING|\bHFA\b", n):
        return "Housing agency"
    if re.search(r"\bBANK\b|\bSSB\b|\bFSB\b|BANCORP|TRUST\b", n):
        return "Bank"
    return "Nonbank"


def _share(a, b, least=1):
    return a / b if b >= least else None


def _r(v):
    return round(v, 6) if isinstance(v, float) else v


def build_datasets(con) -> dict[str, list[dict]]:
    """Needs scw (scores.py) and seller_map and entity_names (lenders.py)."""
    last = con.execute("SELECT max(week) FROM scw").fetchone()[0]
    statements = []
    with STATEMENTS_CSV.open(newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            statements.append({"order": i, **{k: v or None for k, v in r.items()}})
    if last is None:
        return {"lender_stage": [], "statements": statements, "lender_mix": []}
    late = (last - timedelta(days=7 * (RECENT_WEEKS - 1))).isoformat()
    with SELLERS_CSV.open(newline="") as f:
        listed_by_key = {r["key"]: r.get("kind") or None for r in csv.DictReader(f)}
    listed = {sid: listed_by_key.get(key) for key, sid in con.execute("SELECT key, id FROM seller_map").fetchall() if listed_by_key.get(key)}
    both, fn, fh = "has_fico AND has_vs4", "agency = 'FNMA'", "agency = 'FHLMC'"
    cur = con.execute(f"""
        WITH b AS (SELECT *, week >= DATE '{late}' AS late FROM scw)
        SELECT b.seller_id AS id, e.short, e.name, e.ticker, count(*) AS n, sum(upb)::DOUBLE AS u, count(*) FILTER (WHERE is_v) AS v,
               coalesce(sum(upb) FILTER (WHERE is_v), 0)::DOUBLE AS vu, count(*) FILTER (WHERE {both}) AS both_n,
               count(*) FILTER (WHERE has_vs4 AND NOT has_fico) AS vo, count(*) FILTER (WHERE {both} AND is_v) AS bv, count(*) FILTER (WHERE has_fico AND NOT has_vs4) AS fo,
               count(*) FILTER (WHERE {fn} AND has_vs4 AND NOT has_fico) AS fn_vo, count(*) FILTER (WHERE {fn} AND {both} AND is_v) AS fn_bv,
               count(*) FILTER (WHERE {fn} AND has_fico AND NOT has_vs4) AS fn_fo, count(*) FILTER (WHERE {fh}) AS fh_n, count(*) FILTER (WHERE {fh} AND {both}) AS fh_both,
               count(*) FILTER (WHERE {fh} AND has_vs4 AND NOT has_fico) AS fh_vo, count(*) FILTER (WHERE {fh} AND {both} AND is_v) AS fh_bv,
               count(*) FILTER (WHERE {fh} AND has_fico AND NOT has_vs4) AS fh_fo,
               count(*) FILTER (WHERE {fn}) AS fn_n, count(*) FILTER (WHERE {fn} AND {both}) AS fn_both,
               count(*) FILTER (WHERE {fn} AND NOT late) AS fe_n, count(*) FILTER (WHERE {fn} AND NOT late AND {both}) AS fe_b,
               count(*) FILTER (WHERE {fn} AND late) AS fl_n, count(*) FILTER (WHERE {fn} AND late AND {both}) AS fl_b,
               count(*) FILTER (WHERE NOT late) AS e_n, count(*) FILTER (WHERE NOT late AND {both}) AS e_b, count(*) FILTER (WHERE NOT late AND is_v) AS e_v,
               count(*) FILTER (WHERE late) AS l_n, count(*) FILTER (WHERE late AND {both}) AS l_b, count(*) FILTER (WHERE late AND is_v) AS l_v,
               count(*) FILTER (WHERE gap > 0) AS hi_n, count(*) FILTER (WHERE gap > 0 AND is_v) AS hi_v,
               count(*) FILTER (WHERE gap BETWEEN 1 AND 19 AND NOT late) AS be_n, count(*) FILTER (WHERE gap BETWEEN 1 AND 19 AND NOT late AND is_v) AS be_v,
               count(*) FILTER (WHERE gap BETWEEN 1 AND 19 AND late) AS bl_n, count(*) FILTER (WHERE gap BETWEEN 1 AND 19 AND late AND is_v) AS bl_v,
               count(*) FILTER (WHERE gap >= 20) AS a_n, count(*) FILTER (WHERE gap >= 20 AND is_v) AS a_v,
               count(*) FILTER (WHERE channel = 'R') AS ch_r, count(*) FILTER (WHERE channel = 'B') AS ch_b, count(*) FILTER (WHERE channel = 'C') AS ch_c,
               count(*) FILTER (WHERE purpose = 'P') AS purchase, avg(fico) AS avg_fico
        FROM b JOIN entity_names e ON e.id = b.seller_id GROUP BY ALL ORDER BY n DESC, id""")
    cols = [c[0] for c in cur.description]
    sellers = [dict(zip(cols, r)) for r in cur.fetchall()]
    n_all, u_all = sum(s["n"] for s in sellers), sum(s["u"] for s in sellers)
    stage_order = {k: i for i, (k, _) in enumerate(STAGES)}
    for i, s in enumerate(sellers):
        uses = _share(s["hi_v"], s["hi_n"], MIN_N)
        s["both_read"] = s["fn_both"] / s["fn_n"] if s["fn_n"] >= MIN_N else s["both_n"] / s["n"]
        s["stage"] = ("pricing" if uses is not None and uses >= 0.5 else "some" if uses is not None and uses >= 0.1 else
                      "both" if s["both_read"] >= STAGE_BOTH else "trace" if s["v"] > 0 else "fico")
        s["uses"], s["rank"] = uses, i + 1
        below_e, below_l, above = _share(s["be_v"], s["be_n"], MIN_N), _share(s["bl_v"], s["bl_n"], MIN_N), _share(s["a_v"], s["a_n"], MIN_N)
        s["below_early"], s["below_late"], s["above"] = below_e, below_l, above
        s["rule"] = (None if above is None and below_l is None else "whenever" if (below_l or 0) >= RULE_HIGH else
                     "moving" if (above or 0) >= RULE_HIGH and below_l is not None and below_e is not None and below_l - below_e >= RULE_MOVE else
                     "line" if (above or 0) >= RULE_HIGH else "some" if (above or 0) >= 0.1 else "rare")
        s["kind"] = _kind(s["name"], listed.get(s["id"]))
        top = max((("Retail", s["ch_r"]), ("Broker", s["ch_b"]), ("Correspondent", s["ch_c"])), key=lambda x: x[1])
        s["lead"] = top[0] if top[1] >= 0.5 * s["n"] else "Mixed"

    out = []
    for s in sellers:
        if s["rank"] > LENDER_TOP and not (s["stage"] in ("pricing", "some", "both") and s["n"] >= MIN_LIST):
            continue
        fannie = s["fe_n"] >= MIN_N and s["fl_n"] >= MIN_N

        def mix(prefix, n, fo, both_n, bv, vo):
            """The four-part split of a lender's loans, overall or at one GSE (MIN_N+ loans)."""
            if n < MIN_N:
                return {f"{prefix}_{k}": None for k in ("fico_only", "both_fico", "both_vs", "vs_only")}
            return {f"{prefix}_fico_only": fo / n, f"{prefix}_both_fico": (both_n - bv) / n, f"{prefix}_both_vs": bv / n, f"{prefix}_vs_only": vo / n}

        out.append({"view": "lender", "id": s["id"], "short": s["short"], "ticker": s["ticker"], "kind": s["kind"], "lead": s["lead"],
                    "stage": s["stage"], "order": stage_order[s["stage"]], "rule": s["rule"], "rank": s["rank"], "loans": s["n"],
                    "share": s["n"] / n_all, "share_upb": s["u"] / u_all if u_all else None, "vs4_share": s["v"] / s["n"],
                    "vs4_upb_share": s["vu"] / s["u"] if s["u"] else None, "recent_share": _share(s["l_v"], s["l_n"], MIN_N),
                    "both_share": s["both_read"], "vs_only_share": s["vo"] / s["n"], "uses_higher": s["uses"], "higher_loans": s["hi_n"],
                    "below_early": s["below_early"], "below_late": s["below_late"], "above": s["above"],
                    "both_early": s["fe_b"] / s["fe_n"] if fannie else _share(s["e_b"], s["e_n"], MIN_N),
                    "both_late": s["fl_b"] / s["fl_n"] if fannie else _share(s["l_b"], s["l_n"], MIN_N), "both_at": "FNMA" if fannie else "All",
                    "vs4_early": _share(s["e_v"], s["e_n"], MIN_N), "retail_share": s["ch_r"] / s["n"], "broker_share": s["ch_b"] / s["n"],
                    "corr_share": s["ch_c"] / s["n"], "purchase_share": s["purchase"] / s["n"], "avg_fico": s["avg_fico"],
                    "fnma_loans": s["fn_n"], "fhlmc_loans": s["fh_n"], **mix("mix", s["n"], s["fo"], s["both_n"], s["bv"], s["vo"]),
                    **mix("fnma", s["fn_n"], s["fn_fo"], s["fn_both"], s["fn_bv"], s["fn_vo"]), **mix("fhlmc", s["fh_n"], s["fh_fo"], s["fh_both"], s["fh_bv"], s["fh_vo"])})

    def group(view, key, label, order, members):
        n, u = sum(s["n"] for s in members), sum(s["u"] for s in members)
        out.append({"view": view, "key": key, "label": label, "order": order, "lenders": len(members), "loans": n, "share": n / n_all,
                    "share_upb": u / u_all if u_all else None, "both_share": sum(s["both_read"] * s["n"] for s in members) / n,
                    "vs4_share": sum(s["v"] for s in members) / n, "vs4_upb_share": sum(s["vu"] for s in members) / u if u else None,
                    "using": sum(s["stage"] in ("pricing", "some") for s in members)})

    for i, (key, label) in enumerate(STAGES):
        members = [s for s in sellers if s["stage"] == key]
        if members:
            group("stage", key, label, i, members)
    for i, kind in enumerate(KIND_ORDER):
        members = [s for s in sellers if s["kind"] == kind]
        if members:
            group("kind", kind, kind, i, members)
    for i, lead in enumerate(["Retail", "Broker", "Correspondent", "Mixed"]):
        members = [s for s in sellers if s["lead"] == lead]
        if members:
            group("lead", lead, f"{lead}-led" if lead != "Mixed" else "Mixed", i, members)

    top2 = [r[0] for r in con.execute("SELECT seller_id FROM scw WHERE is_v GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 2").fetchall()]
    names = dict(con.execute("SELECT id, short FROM entity_names").fetchall())
    for i, (ch, top, n, b, v) in enumerate(con.execute(f"""
            SELECT channel, list_contains(?::VARCHAR[], seller_id) AS top, count(*), count(*) FILTER (WHERE {both}), count(*) FILTER (WHERE is_v)
            FROM scw WHERE channel IN ('R', 'B', 'C') GROUP BY 1, 2 ORDER BY 2 DESC, 1""", [top2]).fetchall()):
        out.append({"view": "channel", "key": f"{ch}_{'top' if top else 'rest'}", "scope": "top" if top else "rest", "label": CHANNELS[ch], "order": i,
                    "loans": n, "share": n / n_all, "both_share": b / n, "vs4_share": v / n})
    ltv = "CASE WHEN ltv <= 60 THEN '60 or less' WHEN ltv <= 80 THEN '61-80' WHEN ltv <= 90 THEN '81-90' WHEN ltv <= 95 THEN '91-95' ELSE 'Over 95' END"
    dims = [("mi", "CASE WHEN mi THEN 'With mortgage insurance' ELSE 'No mortgage insurance' END"),
            ("purpose", "CASE purpose WHEN 'P' THEN 'Purchase' WHEN 'C' THEN 'Cash-out refinance' ELSE 'No cash-out refinance' END"),
            ("channel", "CASE channel WHEN 'R' THEN 'Retail' WHEN 'B' THEN 'Broker' WHEN 'C' THEN 'Correspondent' END"), ("ltv", ltv),
            ("program", "CASE program WHEN 'H' THEN 'HomeReady, Home Possible' WHEN 'F' THEN 'HFA programs' WHEN 'R' THEN 'RefiNow, Refi Possible' ELSE 'No special program' END")]
    scopes = [("All", "true", "All lenders")] + [(sid, f"seller_id = '{sid}'", names.get(sid, sid)) for sid in top2]
    if top2:
        scopes.append(("rest", f"NOT list_contains({top2!r}::VARCHAR[], seller_id)", "Other lenders"))
    for dim, case in dims:
        for scope, cond, label in scopes:
            for key, n, v in con.execute(f"""
                    SELECT {case} AS k, count(*), count(*) FILTER (WHERE is_v) FROM scw WHERE gap > 0 AND ({cond}) GROUP BY 1 HAVING k IS NOT NULL ORDER BY 1""").fetchall():
                if n >= MIN_N:
                    out.append({"view": "trait", "dim": dim, "key": key, "scope": scope, "label": label, "loans": n, "vs4_share": v / n})
    keys = sorted({k for r in out for k in r})
    listed_ids = [r["id"] for r in out if r["view"] == "lender"]
    mix_rows = [{"view": view, "id": sid, "agency": agency, "start": start.isoformat(), "n": n, "fo": fo, "bf": bf, "bv": bv, "vo": vo}
                for view, col, when in (("week", "week", f"week >= DATE '{WEEK_FROM}'"), ("month", "month", "true"))
                for sid, agency, start, n, fo, bf, bv, vo in con.execute(f"""
                    SELECT seller_id, coalesce(agency, 'All'), {col}, count(*), count(*) FILTER (WHERE has_fico AND NOT has_vs4), count(*) FILTER (WHERE has_fico AND has_vs4 AND NOT is_v),
                           count(*) FILTER (WHERE has_fico AND has_vs4 AND is_v), count(*) FILTER (WHERE has_vs4 AND NOT has_fico)
                    FROM scw WHERE {when} AND list_contains(?::VARCHAR[], seller_id) GROUP BY seller_id, {col}, ROLLUP(agency) ORDER BY 1, 3, 2""", [listed_ids]).fetchall()]
    return {"lender_stage": [{k: _r(r.get(k)) for k in keys} for r in out], "statements": statements, "lender_mix": mix_rows}
