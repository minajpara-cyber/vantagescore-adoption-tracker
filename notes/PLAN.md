# VantageScore adoption tracker: plan

Goal: measure how fast VantageScore 4.0 (VS4) is displacing Classic FICO in Fannie Mae and Freddie Mac
MBS issuance, then add analytical layers (pricing spread, borrower mix, lender penetration, forecast).

## 1. The data (confirmed from the GSE disclosure specs)

Both GSEs publish the same UMBS-aligned, pipe-delimited files with a header row, on near-identical
portals (`fanniemae.mbs-securities.com` = PoolTalk, `freddiemac.mbs-securities.com`). Login required.

| File (portal name) | Cadence | Use here |
|---|---|---|
| MBS Intraday Issuance Loan Level File (`L1_INTRADAY_ISSUANCE_LOAN_LEVEL`, Freddie `flYYMMDD[_N]`) | 4x per business day (6:30, 10:30, 1:30, 3:30 ET), not cumulative | Daily adoption series |
| MBS Month-end Issuance Loan Level (`L1_MONTHLY_CUMMULATIVE_ISSUANCE_LOAN_LEVEL`) | Monthly | Clean monthly snapshot; backfill |
| MBS Loan Level Issuance Correction File | Monthly | Corrections |
| MBS Monthly Loan Level File (`L1_MONTHLY_ONGOING_LOAN_LEVEL`, Freddie `fuYYMMDD`) | 4th business day | Backfill beyond month-end retention; picks up back-filled Pricing Indicator |
| Intraday / month-end security files | Same | Issue month, pool-level checks |

Retention (checked on the portals Oct 27, 2026): intraday loan files go back to Jul 1, 2026 (about
four months), month-end issuance files to Dec 2025. Collecting weekly is enough; daily history older
than the intraday window cannot be rebuilt.

What the real files showed:
- Intraday files are not one record per loan: a loan is republished in many files (3-6 times on
  average, for up to ~3 weeks) and can move between pools before issuance. Loans are keyed by
  (agency, loan id); the first intraday appearance is the disclosure date.
- Many loans are disclosed in the month before their issue month. Issue month = month-end file month,
  else first payment date + (loan age - 1) months, which matches every loan in the month-end files.
- Intraday-only loans in a month that has a month-end file are dropped (pulled or re-pooled).
- Loans disclose both scores only from Oct 19, 2026, the day the Pricing Indicator started; every such
  loan carries the indicator. Fannie Mae prefix I4 pools (re-performing loans) disclose no score.

Credit score fields in the loan file:

| Field | Since | Meaning |
|---|---|---|
| L-023 Classic FICO (was "Borrower Credit Score") | renamed Nov 17, 2025 | 300-850, 9999 = not available |
| L-025 VS4 | Nov 17, 2025 | 300-850; 7777 = not applicable (securities before Dec 2025) |
| L-117 Pricing Indicator | Oct 19, 2026 (Oct 2026 issues) | Which score priced the loan: C = Classic FICO, V = VS4, 9 = n/a |
| L-118 Fannie Score / L-119 Freddie Score | Oct 19, 2026 | GSE internal scores, not used for pricing |

Timeline: FHFA allows VS4 (Jul 8, 2025) -> disclosure fields live (Nov 17, 2025) -> limited lender
rollout, mostly Rocket and UWM (May 1, 2026) -> open to all sellers (Sep 8-10, 2026) -> aligned LLPAs
for both models (Oct 1, 2026 issues) -> Pricing Indicator (Oct 19, 2026).

## 2. Key definition: which model priced the loan

`score_model` per loan:
1. If the Pricing Indicator is present, use it (C, V, or the portal's N = Fannie Score, R = Freddie Score).
2. Before Oct 2026 issuance: VS4 populated and Classic FICO not -> V; the reverse -> C
   (lenders could not mix models on one loan).
3. Both populated with no indicator -> B (ambiguous); neither -> X.

Adoption share = V / loans with a valid score (everything but X), by count and by UPB. The datasets
carry B and X counts so the denominator is visible.

## 3. Pipeline

```
portal (browser session) -> data/raw/<AGENCY>/<kind>/      untouched downloads
  -> gsescore ingest   -> data/warehouse/{loan,security}/   one parquet per file, all columns kept
  -> DuckDB views       -> loans (one row per loan, typed, score_model derived)
  -> gsescore build    -> site/data/*.json                 aggregates only
  -> dashboard           (private claude.ai page; share it when ready)
```

Loan-level data stays local. Only aggregates are published.

## 4. Phases

**Phase 1: collect, organize, publish**
1. Done Oct 27, 2026: month-end issuance loan files Dec 2025 - Sep 2026 and intraday loan files
   Jul 1 - Oct 27, 2026, both GSEs (680 files, 158 MB, 2.05M loans).
2. Done: dashboard v1 (monthly and weekly adoption by GSE, count vs balance, sellers, borrower mix).
3. Done: weekly refresh, a scheduled task in the Claude app (gse-weekly-refresh, Mondays 9:00 ET):
   check portal sign-in (the user signs in), collector/collect.js, `refresh`, update the claude.ai
   dashboard's files, `publish` to GitHub Pages (https://minajpara-cyber.github.io/vantagescore-adoption-tracker/).

**Phase 2: analytical layers** (agreed Oct 27, 2026; new views go to the private claude.ai dashboard
first, and to the public site only once cleared; the build plan for items 2-5, with early findings, stays
local in notes/ANALYTICS_PLAN.md)
1. Done Oct 27, 2026: lenders and adoption. Seller list matched across GSEs with parents and tickers
   (reference/sellers.csv); seller explorer (VS4 share by month and GSE, volume, weekly, channel and
   purpose); heat table of the largest sellers; adopters under three thresholds (first VS4 loan, 10+ in a
   month, 5%+ of a month's loans) and the largest sellers not yet over them; breadth x depth with each
   month's change split exactly into new adopters, existing adopters and lender mix; clean series at a
   fixed Jan-Jun 2026 lender mix and without the two largest VS4 sellers; latest highlights. Published
   on the public site Oct 29, 2026, with the current-month range and the seller share-of-loans views.
2. Score choice and FICO exposure, from loans with both scores (Oct 19 onward). Done Oct 29, 2026 on the
   private dashboard: which scores loans carry, by GSE and week (the GSEs differ because of what each
   collects or discloses, not the lenders), and the score-group toggle (all loans / both scores /
   VantageScore only) on the Borrowers and Pricing tabs. Also done Oct 29 (src/gsescore/scores.py, Score
   choice tab): the rule lenders use to pick a score, by how many LLPA buckets VS4 sits above or below
   FICO, for all lenders and each large one; and the ceiling, VS4's share if every lender priced on the
   better score (or wherever VS4 is no worse), with loans that carry only a Classic FICO given the rate
   measured on loans with both scores like them. Both-score groups use every record that carries the
   Pricing Indicator, including loans first disclosed before Oct 19 and republished. Months made up of
   records that show only one score are estimates (Oct 30, 2026): a lender that delivered a VS4 loan that
   month takes its own ceiling from records with every score, since counting its VS4 loans as better and
   its FICO loans at the market rate overstates a lender already choosing between scores.
3. Pricing. Done Oct 29, 2026 on the private dashboard (src/gsescore/pricing.py): a model of FICO-priced
   30-year fixed loans' note rates (additive effects for lender and channel by week, LLPA cell, loan and
   borrower traits; fitted on four in five, checked on the fifth) gives each VS4 loan the rate a FICO
   loan like it would carry, at the same headline score and, with both scores, at the borrower's own
   Classic FICO; by week, seller and loan type. Upfront fees: see Phase 3, item 4. Next: note rate minus
   pass-through rate (retained servicing). Points and lender credits are not disclosed.
4. Borrowers. Done Oct 29, 2026 on the private dashboard (src/gsescore/borrowers.py): 19 breakdowns by
   score group, each VS4 share next to the share expected from its lenders' own FICO loans, and averages
   by score group. Next: where the VS4 lift over FICO is largest, and the valuation and special-program
   codes once mapped from the disclosure spec.
5. Outlook. Done Oct 29, 2026 on the private dashboard (src/gsescore/outlook.py, Outlook tab), as
   scenarios rather than a fitted forecast: each lender's share of loans, VS4 share and ceiling (from 2)
   in the latest two issue months; the depth the deep lenders reach (VS4 share over ceiling); VS4's share
   as groups of lenders go that deep, up to the ceiling; how fast the deep lenders ramped and how fast
   others are starting; three paths by month (no change, today's users go deep, and others also start at
   the recent pace); and a lender table to add up any set of lenders.

Items 2-5 were on the public site briefly on Oct 30, 2026 and came off the same morning; they are on the
private dashboard only.

**Phase 3: built for covering the companies** (agreed Oct 30, 2026; private dashboard only)
1. Done Oct 30, 2026: the framing. For MBS issued before Oct 1, 2026, FICO's fee tiers applied to VS4 at 20
   points higher; one grid since. Lender rules are now read in score points by week (src/gsescore/scores.py,
   dataset rules), the scenarios are rules on the one grid (saves a fee, score higher, no worse), the outlook is
   rebuilt on them, and the rate model compares in the same fee tier, adds seller x purpose, and shows how much of
   a better tier reaches the rate.
2. Done Oct 30, 2026: the front page. Which scores loans carry (FICO only, both priced either way, VS4 only) by
   GSE and week (dataset score_mix), Classic FICO on the loan, the latest weeks' pace, what changed, calendar quarters. Loans carrying VS4 runs back to April by issue month and to July by week as
   VS4-priced loans, a floor until the files show every score, with the same weeks at a steady mix of lenders.
3. Done Oct 30, 2026: why lenders choose (src/gsescore/why.py, datasets lender_stage, lender_mix and statements). A cost-or-rate test: what lenders with both scores pick by what VS4 does
   to the fee (src/gsescore/fees.py, views choice and option). Each lender's score split by week and issue month. Each lender's stage (pricing on VS4,
   some, both scores shown, a trace, FICO only), its rule, an early-warning list of lenders whose both-score share is rising, lender types by
   hand in reference/sellers.csv, use inside a lender by loan trait, and dated company statements with links (reference/statements.csv), each
   checked against the loan files where it can be.
4. Done Oct 30, 2026: pricing and economics (src/gsescore/fees.py, src/gsescore/fee_grid.py, dataset fees). How much of a lower fee reaches the rate is measured against each lender and channel's
   own FICO-priced loans with both scores (src/gsescore/pricing.py, view value). The grid in reference/llpa.csv is
   Freddie Mac Guide Exhibit 19 (Bulletin 2026-K); Fannie Mae's matrix is taken to match it, unchecked. Fee saved per loan and in dollars by
   lender; what lenders with both scores left; an estimate for loans with only a Classic FICO; the same scaled to a year's balance; the fee
   against what reaches the rate; the GSEs' own scores on these loans.
5. Done Oct 30, 2026: analyst tools. On the Lenders tab, a read for each company with a row of tickers: its score split by GSE, its rule, fees, rates, questions
   to ask and what it has said. On the Outlook tab, your scenario by lender and FICO's exposure on GSE loans (src/gsescore/exposure.py, reference/assumptions.csv, in
   site/dashboard/tools.js). On the Overview, this week's note with an archive (src/gsescore/notes.py, `gsescore note`). The Excel workbook (src/gsescore/export.py,
   exports/, git-ignored) has the tables and the calculator as live formulas; Sources on the dashboard gives any dataset as CSV. Longer sections fold away, and the Borrowers
   tab's table of which scores loans carry gave way to the front page's split.
6. Deeper data. Done Oct 30, 2026: which lenders show fewer scores at Freddie Mac, and which factors do not explain it (the cause is still unknown), and FHA (it accepts VS4 for
   case numbers from January 1, 2027). Waiting: the monthly loan file (L1_MONTHLY_ONGOING_LOAN_LEVEL, Freddie fuYYMMDD), whose origination score fields (L-097, L-099) and
   back-filled Pricing Indicator may give both scores on earlier loans and replace the estimates for those months. The first file with the new fields should come about
   Nov 5, 2026. The weekly refresh lists its name and size from then (`__gseListMonthly`); then decide how to collect it, since the browser collector holds files in memory, and
   how much to keep (loans issued since VS4 opened, not the whole book). SFTP stays deferred until the user wants it.

## 5. Open items
- Seller is not originator: correspondent aggregators (AmeriHome, PennyMac) deliver loans other lenders
  made. Nationstar (Mr. Cooper) delivered under its own name only through January 2026, so Rocket
  Companies' recent figures equal Rocket Mortgage's.
- Freddie "Daily Issuance Loan Level File 2" (`al*` files, Jan - Mar 2026 only): not collected.
- Month-end loan correction files (`*_RILLD_*`): not collected yet; apply once corrections matter.
- Pricing Indicator codes: the portal app maps 9, C, V, N = Fannie Score, R = Freddie Score; the pipeline accepts all of them.
- Redistribution: Fannie charges for commercial redistribution of issuance files; keep the site to
  aggregates and private sharing unless that is cleared.
