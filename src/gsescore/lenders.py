"""Seller-level datasets: who delivers VS4 loans, since when, and how much of the market they are.

Sellers are matched across the two GSEs by a normalized name (upper case, punctuation and corporate
suffixes dropped). reference/sellers.csv, kept by hand, gives the larger sellers a display name, a
short label, the parent company and its ticker; any other seller shows its own name. A parent with
several sellers (Rocket Companies: Rocket Mortgage and Nationstar) also gets rows of its own.

  sellers         one row per seller (the SELLER_TOP largest over the recent window, plus every seller
                  with a VS4 loan) and per parent with several sellers: market and VS4 share over the
                  last RECENT_MONTHS issue months, VS4 loans, first month under each adoption
                  definition, first VS4 disclosure date, channel mix
  seller_monthly  those rows' VS4 share and market share by issue month and GSE (+ All)
  seller_weekly   VS4 share by week of first disclosure, for rows with WEEKLY_MIN_VS4+ VS4 loans
  seller_splits   VS4 share by channel and by purpose since SPLITS_START, larger sellers and adopters
  adoption        breadth x depth by issue month and GSE: adopters under each definition, new
                  adopters and their volume, VS4 share within adopters, sellers active this month,
                  the share of loans from sellers outside the `sellers` rows (none has a VS4 loan),
                  and each month's change in VS4 share split into new adopters, deeper use at
                  existing adopters and the shift in lender mix
  adopters        each seller's first issue month under each adoption definition, by GSE scope, for
                  sellers that have delivered a VS4 loan
  series          clean comparisons by month and by week: actual VS4 share, at a fixed lender mix
                  (FIXED_BASE), and without the two largest VS4 sellers
  highlights      one row: sellers whose first VS4 loan was disclosed in the last 7 and 30 days (issue
                  month for loans before the intraday history), and the seller whose VS4 share rose
                  most from the prior month

Adoption definitions (by issue month, within the GSE scope): "any" a first VS4 loan, "ten" 10+ VS4
loans in a month, "pct5" VS4 at 5%+ of the seller's scored loans in a month with 20+ scored loans.
"""
import csv
import re
from datetime import date, timedelta

from . import paths

SELLERS_CSV = paths.REPO / "reference" / "sellers.csv"
SELLER_TOP = 100
RECENT_MONTHS = 3
SPLITS_START = "2026-05-01"
SPLITS_TOP = 25
SPLITS_MIN_VS4 = 10
WEEKLY_MIN_VS4 = 50
# Lender mix for the fixed-mix series: each seller's share of scored loans issued Jan-Jun 2026.
FIXED_BASE = ("2026-01-01", "2026-06-01")
MOVER_MIN_LOANS = 300
DEFS = {"any": "v >= 1", "ten": "v >= 10", "pct5": "n >= 20 AND v >= 0.05 * n"}

_SUFFIXES = "LLC|L L C|INC|NA|N A|NATIONAL ASSOCIATION|CORPORATION|CORP|COMPANY|CO|LP|L P|LIMITED PARTNERSHIP|FSB|LTD"
KEY_SQL = ("trim(regexp_replace(regexp_replace(regexp_replace(upper(replace(coalesce(s, ''), '&', ' AND ')), "
           f"'[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g'), '( ({_SUFFIXES}))+ *$', ''))")
_SMALL = {"AND", "OF", "THE", "FOR", "A", "AN", "IN", "ON", "AT", "BY", "TO"}
_UPPER = {"USA", "USAA", "SSB", "FCU", "II", "III"}


def _titleish(key: str) -> str:
    out = []
    for i, w in enumerate(key.split()):
        if w in _UPPER or any(c.isdigit() for c in w) or not set(w) & set("AEIOUY"):
            out.append(w)  # acronyms such as CMG, NFM, SWBC
        elif i and w in _SMALL:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _reference() -> dict[str, dict]:
    with SELLERS_CSV.open(newline="") as f:
        return {r["key"]: r for r in csv.DictReader(f)}


def _register_sellers(con) -> None:
    """seller_map: normalized key -> seller id and names; entity_names: display names for every row id."""
    con.execute(f"CREATE OR REPLACE TEMP MACRO seller_key(s) AS {KEY_SQL}")
    ref = _reference()
    sellers = {}
    keys = []
    for (key,) in con.execute("SELECT DISTINCT seller_key(seller) FROM loans").fetchall():
        r = ref.get(key, {})
        name = r.get("name") or (_titleish(key) if key else "Seller not disclosed")
        parent = r.get("parent") or name
        sid = _slug(name) or "not-disclosed"
        sellers[sid] = {"name": name, "short": r.get("short") or name, "parent": parent,
                        "ticker": r.get("ticker") or None}
        keys.append((key, sid))
    by_parent: dict[str, list[str]] = {}
    for sid, s in sellers.items():
        by_parent.setdefault(s["parent"], []).append(sid)
    parents = {}
    for parent, members in by_parent.items():
        if len(members) < 2:
            continue
        pid = _slug(parent)
        if pid in sellers:
            pid += "-group"
        tickers = {sellers[m]["ticker"] for m in members} - {None}
        parents[parent] = pid
        sellers_named = ", ".join(sorted(sellers[m]["short"] for m in members))
        sellers[pid] = {"name": parent, "short": parent, "parent": parent,
                        "ticker": tickers.pop() if len(tickers) == 1 else None, "members": sellers_named}
    con.execute("CREATE OR REPLACE TEMP TABLE seller_map (key VARCHAR, id VARCHAR, parent_id VARCHAR)")
    con.executemany("INSERT INTO seller_map VALUES (?, ?, ?)",
                    [(k, sid, parents.get(sellers[sid]["parent"])) for k, sid in keys])
    con.execute("""CREATE OR REPLACE TEMP TABLE entity_names (id VARCHAR, level VARCHAR, name VARCHAR, short VARCHAR,
                   parent VARCHAR, ticker VARCHAR, members VARCHAR)""")
    con.executemany("INSERT INTO entity_names VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(i, "parent" if "members" in s else "seller", s["name"], s["short"], s["parent"], s["ticker"],
                      s.get("members")) for i, s in sellers.items()])


def build_datasets(con, in_range: str, weekly_start: str, rows) -> dict[str, list[dict]]:
    """Needs the `monthly` temp view from aggregate.build(); `rows(con, sql)` runs a query into row dicts."""
    _register_sellers(con)
    # Every scored loan, with its seller; `in_range` marks the issue months the monthly series cover.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ls AS
        SELECT l.agency, l.issue_month AS month, l.first_intraday_date AS first_date, l.score_model = 'V' AS is_v,
               coalesce(l.upb, 0) AS upb, l.channel, l.purpose, m.id, m.parent_id, ({in_range}) AS in_range
        FROM loans l JOIN seller_map m ON m.key = seller_key(l.seller)
        WHERE l.score_model <> 'X'""")
    # Seller rows, plus parent rows for parents with several sellers.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE le AS
        SELECT 'seller' AS level, id AS eid, agency, month, first_date, is_v, upb, channel, purpose, in_range FROM ls
        UNION ALL
        SELECT 'parent', parent_id, agency, month, first_date, is_v, upb, channel, purpose, in_range FROM ls
        WHERE parent_id IS NOT NULL""")
    last = con.execute("SELECT max(month) FROM ls WHERE in_range").fetchone()[0]
    y, m = divmod(last.year * 12 + last.month - 1 - (RECENT_MONTHS - 1), 12)
    recent_from = date(y, m + 1, 1)
    rf = f"DATE '{recent_from}'"

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE sellers_out AS
        WITH tot AS (SELECT sum(scored_loans) AS n, sum(scored_upb) AS u FROM monthly WHERE agency = 'All' AND month >= {rf}),
        allv AS (SELECT count(*) FILTER (WHERE is_v) AS v FROM ls WHERE in_range),
        sm AS (SELECT level, eid, month, count(*) AS n, count(*) FILTER (WHERE is_v) AS v FROM le WHERE in_range GROUP BY ALL),
        f AS (SELECT level, eid, {", ".join(f"min(month) FILTER (WHERE {c}) AS first_{d}" for d, c in DEFS.items())}
              FROM sm GROUP BY ALL),
        e AS (SELECT level, eid,
                count(*) FILTER (WHERE month >= {rf}) AS scored_recent,
                count(*) FILTER (WHERE month >= {rf} AND is_v) AS vs4_recent,
                sum(upb) FILTER (WHERE month >= {rf}) AS upb_recent,
                sum(upb) FILTER (WHERE month >= {rf} AND is_v) AS vs4_upb_recent,
                count(*) FILTER (WHERE is_v) AS vs4_loans,
                count(*) FILTER (WHERE month >= {rf} AND channel = 'R') AS retail_recent,
                count(*) FILTER (WHERE month >= {rf} AND channel = 'B') AS broker_recent,
                count(*) FILTER (WHERE month >= {rf} AND channel = 'C') AS corr_recent
              FROM le WHERE in_range GROUP BY ALL),
        fd AS (SELECT level, eid, min(coalesce(first_date, month)) AS first_vs4_date FROM le WHERE is_v GROUP BY ALL),
        r AS (SELECT e.*, f.first_any, f.first_ten, f.first_pct5, fd.first_vs4_date,
                CASE WHEN e.level = 'seller' THEN rank() OVER (PARTITION BY e.level ORDER BY e.scored_recent DESC) END AS rank
              FROM e JOIN f USING (level, eid) LEFT JOIN fd USING (level, eid))
        SELECT r.level, r.eid AS id, n.name, n.short, n.parent, n.ticker, n.members, r.rank,
          {rf} AS recent_from, DATE '{last}' AS recent_to,
          r.scored_recent, r.vs4_recent,
          r.scored_recent / tot.n AS mkt_share_recent, r.upb_recent / tot.u AS mkt_share_upb_recent,
          r.vs4_recent / nullif(r.scored_recent, 0) AS vs4_share_recent,
          r.vs4_upb_recent / nullif(r.upb_recent, 0) AS vs4_upb_share_recent,
          r.vs4_loans, r.vs4_loans / allv.v AS share_of_all_vs4,
          r.first_any AS first_vs4_month, r.first_ten AS first_10_month, r.first_pct5 AS first_5pct_month,
          r.first_vs4_date,
          r.retail_recent / nullif(r.scored_recent, 0) AS retail_share_recent,
          r.broker_recent / nullif(r.scored_recent, 0) AS broker_share_recent,
          r.corr_recent / nullif(r.scored_recent, 0) AS corr_share_recent
        FROM r JOIN entity_names n ON n.id = r.eid, tot, allv
        WHERE r.level = 'parent' OR r.rank <= {SELLER_TOP} OR r.vs4_loans > 0
        ORDER BY r.level DESC, r.rank, r.vs4_loans DESC""")

    out = {"sellers": rows(con, "SELECT * FROM sellers_out")}
    out["seller_monthly"] = rows(con, """
        WITH g AS (
          SELECT le.level, le.eid AS id, le.month, COALESCE(le.agency, 'All') AS agency,
                 count(*) AS scored, count(*) FILTER (WHERE is_v) AS vs4,
                 sum(upb) AS scored_upb, sum(upb) FILTER (WHERE is_v) AS vs4_upb
          FROM le JOIN sellers_out s ON s.level = le.level AND s.id = le.eid
          WHERE le.in_range
          GROUP BY GROUPING SETS ((le.level, le.eid, le.month, le.agency), (le.level, le.eid, le.month)))
        SELECT g.level, g.id, g.agency, g.month, g.scored, g.vs4,
               g.vs4 / g.scored AS vs4_share, coalesce(g.vs4_upb, 0) / nullif(g.scored_upb, 0) AS vs4_upb_share,
               g.scored / t.scored_loans AS mkt_share, g.scored_upb / nullif(t.scored_upb, 0) AS mkt_share_upb
        FROM g JOIN monthly t ON t.month = g.month AND t.agency = g.agency
        ORDER BY g.level DESC, g.id, g.agency, g.month""")
    out["seller_weekly"] = rows(con, f"""
        WITH g AS (
          SELECT le.level, le.eid AS id, date_trunc('week', le.first_date)::DATE AS week,
                 count(*) AS scored, count(*) FILTER (WHERE is_v) AS vs4,
                 sum(upb) AS scored_upb, coalesce(sum(upb) FILTER (WHERE is_v), 0) AS vs4_upb
          FROM le JOIN sellers_out s ON s.level = le.level AND s.id = le.eid
          WHERE s.vs4_loans >= {WEEKLY_MIN_VS4} AND le.first_date >= DATE '{weekly_start}'
          GROUP BY ALL)
        SELECT level, id, week, scored, vs4, vs4 / scored AS vs4_share, vs4_upb / nullif(scored_upb, 0) AS vs4_upb_share,
          CASE WHEN count(*) OVER w4 = 4 THEN sum(vs4) OVER w4 / sum(scored) OVER w4 END AS vs4_share_4wk,
          CASE WHEN count(*) OVER w4 = 4 THEN sum(vs4_upb) OVER w4 / sum(scored_upb) OVER w4 END AS vs4_upb_share_4wk,
          week + 7 <= current_date AS complete
        FROM g WINDOW w4 AS (PARTITION BY level, id ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
        ORDER BY level DESC, id, week""")
    split_rows = "SELECT level, id FROM sellers_out WHERE rank <= {} OR vs4_loans >= {}".format(SPLITS_TOP, SPLITS_MIN_VS4)
    splits = []
    for dim, case, order in [
        ("channel", "CASE channel WHEN 'R' THEN 'Retail' WHEN 'B' THEN 'Broker' WHEN 'C' THEN 'Correspondent' END",
         "CASE channel WHEN 'R' THEN 0 WHEN 'B' THEN 1 ELSE 2 END"),
        ("purpose", "CASE WHEN purpose = 'P' THEN 'Purchase' WHEN purpose = 'C' THEN 'Cash-out refinance' "
                    "WHEN purpose IN ('N', 'R') THEN 'No cash-out refinance' END",
         "CASE WHEN purpose = 'P' THEN 0 WHEN purpose = 'C' THEN 1 ELSE 2 END"),
    ]:
        splits.append(f"""
            SELECT le.level, le.eid AS id, le.month, '{dim}' AS dim, {case} AS bucket, {order} AS bucket_order,
                   count(*) AS scored, count(*) FILTER (WHERE is_v) AS vs4, count(*) FILTER (WHERE is_v) / count(*) AS vs4_share
            FROM le JOIN ({split_rows}) u ON u.level = le.level AND u.id = le.eid
            WHERE le.in_range AND le.month >= DATE '{SPLITS_START}' AND {case} IS NOT NULL
            GROUP BY ALL""")
    out["seller_splits"] = rows(con, " UNION ALL ".join(splits) + " ORDER BY level DESC, id, dim, month, bucket_order")

    # Adoption: seller rows only, by GSE scope.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE adopt_sm AS
        SELECT id, month, COALESCE(agency, 'All') AS agency, count(*) AS n, count(*) FILTER (WHERE is_v) AS v,
               sum(upb) AS u, coalesce(sum(upb) FILTER (WHERE is_v), 0) AS vu
        FROM ls WHERE in_range GROUP BY GROUPING SETS ((id, month, agency), (id, month))""")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE adopt_f AS
        SELECT id, agency, {", ".join(f"min(month) FILTER (WHERE {c}) AS f_{d}" for d, c in DEFS.items())}
        FROM adopt_sm GROUP BY id, agency""")
    out["adopters"] = rows(con, f"""
        SELECT id, agency, {", ".join(f"f_{d} AS first_{d}" for d in DEFS)} FROM adopt_f WHERE f_any IS NOT NULL
        ORDER BY id, CASE agency WHEN 'All' THEN 0 ELSE 1 END, agency""")
    per_def = []
    for d in DEFS:
        per_def.append(f"""
          (SELECT count(*) FROM adopt_f f WHERE f.agency = t.agency AND f.f_{d} <= t.month) AS adopters_{d},
          (SELECT count(*) FROM adopt_f f WHERE f.agency = t.agency AND f.f_{d} = t.month) AS new_{d},
          coalesce(v.new_n_{d}, 0) / t.scored_loans AS new_share_{d},
          coalesce(v.new_u_{d}, 0) / t.scored_upb AS new_upb_share_{d},
          coalesce(v.ad_n_{d}, 0) / t.scored_loans AS adopters_share_{d},
          coalesce(v.ad_u_{d}, 0) / t.scored_upb AS adopters_upb_share_{d},
          1 - coalesce(v.ad_n_{d}, 0) / t.scored_loans AS nonadopters_share_{d},
          1 - coalesce(v.ad_u_{d}, 0) / t.scored_upb AS nonadopters_upb_share_{d},
          v.ad_v_{d} / nullif(v.ad_n_{d}, 0) AS vs4_within_{d},
          v.ad_vu_{d} / nullif(v.ad_u_{d}, 0) AS vs4_within_upb_{d}""")
    sums = ",\n".join(
        f"""sum(n) FILTER (WHERE f_{d} <= month) AS ad_n_{d}, sum(v) FILTER (WHERE f_{d} <= month) AS ad_v_{d},
            sum(u) FILTER (WHERE f_{d} <= month) AS ad_u_{d}, sum(vu) FILTER (WHERE f_{d} <= month) AS ad_vu_{d},
            sum(n) FILTER (WHERE f_{d} = month) AS new_n_{d}, sum(u) FILTER (WHERE f_{d} = month) AS new_u_{d}"""
        for d in DEFS)
    # Each month's change in VS4 share, seller by seller: w = share of the month's scored loans, s = VS4
    # share. w1*s1 - w0*s0 = mean(w)*(s1-s0) + mean(s)*(w1-w0) exactly; a seller absent one month takes
    # the other month's s, so its whole change is mix. First-time adopters' change is all "new".
    out["adoption"] = rows(con, f"""
        WITH x AS (SELECT sm.*, {", ".join(f"f.f_{d}" for d in DEFS)},
                          sm.id IN (SELECT id FROM sellers_out WHERE level = 'seller') AS listed
                   FROM adopt_sm sm JOIN adopt_f f USING (id, agency)),
        v AS (SELECT agency, month, count(*) FILTER (WHERE v > 0) AS active,
                     sum(n) FILTER (WHERE v > 0) AS active_n, sum(u) FILTER (WHERE v > 0) AS active_u,
                     count(*) FILTER (WHERE NOT listed) AS rest, sum(n) FILTER (WHERE NOT listed) AS rest_n,
                     sum(u) FILTER (WHERE NOT listed) AS rest_u,
                     {sums}
              FROM x GROUP BY agency, month),
        c AS (SELECT x.id, x.agency, x.month, x.f_any, x.n / t.scored_loans AS w, x.v / x.n AS s,
                     x.u / t.scored_upb AS wu, x.vu / nullif(x.u, 0) AS su
              FROM x JOIN monthly t USING (agency, month)),
        pr AS (SELECT coalesce(c1.agency, c0.agency) AS agency,
                      coalesce(c1.month, (c0.month + INTERVAL 1 MONTH)::DATE) AS month,
                      coalesce(c1.f_any, c0.f_any) AS f_any,
                      coalesce(c1.w, 0) AS w1, coalesce(c0.w, 0) AS w0, coalesce(c1.s, c0.s) AS s1, coalesce(c0.s, c1.s) AS s0,
                      coalesce(c1.wu, 0) AS wu1, coalesce(c0.wu, 0) AS wu0,
                      coalesce(c1.su, c0.su, 0) AS su1, coalesce(c0.su, c1.su, 0) AS su0
               FROM c c1 FULL JOIN c c0 ON c0.id = c1.id AND c0.agency = c1.agency
                                       AND c0.month = (c1.month - INTERVAL 1 MONTH)::DATE),
        dec AS (SELECT agency, month,
                  coalesce(sum(w1 * s1 - w0 * s0) FILTER (WHERE f_any = month), 0) AS d_new,
                  coalesce(sum((w1 + w0) / 2 * (s1 - s0)) FILTER (WHERE f_any < month), 0) AS d_within,
                  coalesce(sum((s1 + s0) / 2 * (w1 - w0)) FILTER (WHERE f_any < month), 0) AS d_mix,
                  coalesce(sum(wu1 * su1 - wu0 * su0) FILTER (WHERE f_any = month), 0) AS d_new_upb,
                  coalesce(sum((wu1 + wu0) / 2 * (su1 - su0)) FILTER (WHERE f_any < month), 0) AS d_within_upb,
                  coalesce(sum((su1 + su0) / 2 * (wu1 - wu0)) FILTER (WHERE f_any < month), 0) AS d_mix_upb
                FROM pr GROUP BY agency, month),
        t AS (SELECT *, vs4_share - lag(vs4_share) OVER (PARTITION BY agency ORDER BY month) AS d_total,
                     vs4_upb_share - lag(vs4_upb_share) OVER (PARTITION BY agency ORDER BY month) AS d_total_upb
              FROM monthly)
        SELECT t.agency, t.month, t.final, t.scored_loans, t.vs4_share, t.vs4_upb_share,
          coalesce(v.active, 0) AS active_sellers,
          coalesce(v.active_n, 0) / t.scored_loans AS active_share, coalesce(v.active_u, 0) / t.scored_upb AS active_upb_share,
          coalesce(v.rest, 0) AS rest_sellers, coalesce(v.rest_n, 0) / t.scored_loans AS rest_share,
          coalesce(v.rest_u, 0) / t.scored_upb AS rest_upb_share,
          {",".join(per_def)},
          t.d_total, CASE WHEN t.d_total IS NOT NULL THEN dec.d_new END AS d_new,
          CASE WHEN t.d_total IS NOT NULL THEN dec.d_within END AS d_within,
          CASE WHEN t.d_total IS NOT NULL THEN dec.d_mix END AS d_mix,
          t.d_total_upb, CASE WHEN t.d_total_upb IS NOT NULL THEN dec.d_new_upb END AS d_new_upb,
          CASE WHEN t.d_total_upb IS NOT NULL THEN dec.d_within_upb END AS d_within_upb,
          CASE WHEN t.d_total_upb IS NOT NULL THEN dec.d_mix_upb END AS d_mix_upb
        FROM t LEFT JOIN v USING (agency, month) LEFT JOIN dec USING (agency, month)
        ORDER BY t.month, CASE t.agency WHEN 'All' THEN 0 ELSE 1 END, t.agency""")

    top2 = con.execute("""
        SELECT n.short FROM ls JOIN entity_names n ON n.id = ls.id WHERE in_range AND is_v
        GROUP BY n.short ORDER BY count(*) DESC LIMIT 2""").fetchall()
    excluded = " and ".join(s for (s,) in top2).replace("'", "''")
    top2_ids = "SELECT ls.id FROM ls WHERE in_range AND is_v GROUP BY ls.id ORDER BY count(*) DESC LIMIT 2"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE adopt_wk AS
        SELECT id, date_trunc('week', first_date)::DATE AS week, COALESCE(agency, 'All') AS agency, count(*) AS n,
               count(*) FILTER (WHERE is_v) AS v, sum(upb) AS u, coalesce(sum(upb) FILTER (WHERE is_v), 0) AS vu
        FROM ls WHERE first_date >= DATE '{weekly_start}'
        GROUP BY GROUPING SETS ((id, date_trunc('week', first_date), agency), (id, date_trunc('week', first_date)))""")
    out["series"] = rows(con, f"""
        WITH base AS (SELECT id, agency, sum(n) AS bn, sum(u) AS bu FROM adopt_sm
                      WHERE month BETWEEN DATE '{FIXED_BASE[0]}' AND DATE '{FIXED_BASE[1]}' GROUP BY ALL),
        fm AS (SELECT agency, month AS start, sum(b.bn * v / n) / sum(b.bn) AS fixed,
                      sum(b.bu * vu / nullif(u, 0)) / sum(b.bu) FILTER (WHERE u > 0) AS fixed_upb
               FROM adopt_sm JOIN base b USING (id, agency) GROUP BY ALL),
        fw AS (SELECT agency, week AS start, sum(b.bn * v / n) / sum(b.bn) AS fixed,
                      sum(b.bu * vu / nullif(u, 0)) / sum(b.bu) FILTER (WHERE u > 0) AS fixed_upb
               FROM adopt_wk JOIN base b USING (id, agency) GROUP BY ALL),
        em AS (SELECT agency, month AS start, sum(v) / sum(n) AS ex_top2, sum(vu) / sum(u) AS ex_top2_upb
               FROM adopt_sm WHERE id NOT IN ({top2_ids}) GROUP BY ALL),
        ew AS (SELECT agency, week AS start, sum(v) / sum(n) AS ex_top2, sum(vu) / sum(u) AS ex_top2_upb
               FROM adopt_wk WHERE id NOT IN ({top2_ids}) GROUP BY ALL),
        tw AS (SELECT agency, week AS start, sum(n) AS n, sum(v) / sum(n) AS actual, sum(vu) / sum(u) AS actual_upb
               FROM adopt_wk GROUP BY ALL),
        months AS (SELECT 'month' AS period, month AS start, agency, final AS complete, scored_loans AS scored,
                          vs4_share AS actual, vs4_upb_share AS actual_upb FROM monthly),
        weeks AS (SELECT 'week' AS period, start, agency, start + 7 <= current_date AS complete, n AS scored, actual, actual_upb FROM tw)
        SELECT m.*, fm.fixed, fm.fixed_upb, em.ex_top2, em.ex_top2_upb, '{excluded}' AS excluded
        FROM months m LEFT JOIN fm USING (agency, start) LEFT JOIN em USING (agency, start)
        UNION ALL
        SELECT w.*, fw.fixed, fw.fixed_upb, ew.ex_top2, ew.ex_top2_upb, '{excluded}' AS excluded
        FROM weeks w LEFT JOIN fw USING (agency, start) LEFT JOIN ew USING (agency, start)
        ORDER BY period, start, CASE agency WHEN 'All' THEN 0 ELSE 1 END, agency""")
    out["highlights"] = [_highlights(con, out)]
    return out


def _names(rows: list[dict], limit: int = 3) -> str:
    names = [r["short"] + (f" ({r['ticker']})" if r["ticker"] and r["ticker"] not in r["short"] else "") for r in rows]
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def _highlights(con, out: dict) -> dict:
    through = con.execute("SELECT max(first_intraday_date) FROM loans").fetchone()[0]
    sellers = [r for r in out["sellers"] if r["level"] == "seller"]
    h = {"data_through": through.isoformat()}
    for days in (7, 30):
        since = through - timedelta(days=days - 1)
        new = sorted((r for r in sellers if r["first_vs4_date"] and date.fromisoformat(r["first_vs4_date"]) >= since),
                     key=lambda r: (-(r["mkt_share_recent"] or 0), r["name"]))
        h[f"new_{days}d"] = len(new)
        h[f"new_{days}d_names"] = _names(new)
        h[f"new_{days}d_mkt_share"] = round(sum(r["mkt_share_recent"] or 0 for r in new), 6)
    monthly = [r for r in out["seller_monthly"] if r["level"] == "seller" and r["agency"] == "All"]
    months = sorted({r["month"] for r in monthly})
    best = None
    if len(months) >= 2:
        prev = {r["id"]: r for r in monthly if r["month"] == months[-2] and r["scored"] >= MOVER_MIN_LOANS}
        for r in monthly:
            p = prev.get(r["id"])
            if r["month"] == months[-1] and p and r["scored"] >= MOVER_MIN_LOANS:
                change = r["vs4_share"] - p["vs4_share"]
                if best is None or change > best[0]:
                    best = (change, r, p)
    names = {r["id"]: r for r in sellers}
    if best:
        change, r, p = best
        h.update({"mover_id": r["id"], "mover_name": names[r["id"]]["name"], "mover_ticker": names[r["id"]]["ticker"],
                  "mover_from_month": p["month"], "mover_to_month": r["month"], "mover_from": p["vs4_share"],
                  "mover_to": r["vs4_share"], "mover_change": round(change, 6),
                  "mover_change_pts": round(change * 100, 4), "mover_loans": r["scored"]})
    return h
