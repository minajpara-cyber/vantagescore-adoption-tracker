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
3. Next: recurring refresh (weekly is enough given retention): pull new intraday files and each new
   month-end file (published the first business day of the month), unpack, ingest, build, re-upload.

**Phase 2: analytical layers**
- Spread: note-rate spread of VS4 vs FICO loans within matched cells (month x purpose x LTV x score
  bucket x loan size), and after Oct 2026 aligned LLPAs.
- Borrower composition: score, LTV, DTI, FTHB, purpose, occupancy, geography by model; VS4-vs-FICO
  crosswalk on loans that disclose both (Oct 2026 onward).
- Lender penetration: VS4 share by seller over time, adoption curves, concentration of VS4 volume.
- Forecast: logistic / Bass diffusion fit on aggregate and per-lender penetration, with scenarios for
  large-lender switching.

## 5. Open items
- Freddie "Daily Issuance Loan Level File 2" (`al*` files, Jan - Mar 2026 only): not collected.
- Month-end loan correction files (`*_RILLD_*`): not collected yet; apply once corrections matter.
- Pricing Indicator codes: the portal app maps 9, C, V, N = Fannie Score, R = Freddie Score; the pipeline accepts all of them.
- Redistribution: Fannie charges for commercial redistribution of issuance files; keep the site to
  aggregates and private sharing unless that is cleared.
