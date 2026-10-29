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
   fixed Jan-Jun 2026 lender mix and without the two largest VS4 sellers; latest highlights.
2. Next: score choice and FICO exposure, from loans with both scores (Oct 19 onward): the rule lenders
   use to pick a score (by how many LLPA buckets VS4 sits above or below FICO), a same-borrower
   crosswalk, a ceiling (VS4 share if every lender priced on the higher score, reweighted to the whole
   market), and a series of loans delivered with no Classic FICO (the two GSEs differ here; explain
   that first).
3. Pricing: 30-yr fixed note rate VS4 vs FICO raw, matched within seller x month x purpose x occupancy
   x LTV x score bucket x size, and at the same Classic FICO (Oct 19 onward); upfront LLPA saved per VS4
   loan from the published grids and how much reaches the rate; note rate minus pass-through rate
   (retained servicing). Points and lender credits are not disclosed.
4. Borrowers: within-lender and lender-mix-adjusted comparisons, distributions rather than averages,
   where the VS4 lift is largest.
5. Forecast: diffusion fit on breadth (adopters' share of volume) x depth (toward the ceiling in 2), with
   lender scenarios.

## 5. Open items
- Seller is not originator: correspondent aggregators (AmeriHome, PennyMac) deliver loans other lenders
  made. Nationstar (Mr. Cooper) delivered under its own name only through January 2026, so Rocket
  Companies' recent figures equal Rocket Mortgage's.
- Freddie "Daily Issuance Loan Level File 2" (`al*` files, Jan - Mar 2026 only): not collected.
- Month-end loan correction files (`*_RILLD_*`): not collected yet; apply once corrections matter.
- Pricing Indicator codes: the portal app maps 9, C, V, N = Fannie Score, R = Freddie Score; the pipeline accepts all of them.
- Redistribution: Fannie charges for commercial redistribution of issuance files; keep the site to
  aggregates and private sharing unless that is cleared.
