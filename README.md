# GSE credit score tracker

Tracks VantageScore 4.0 vs Classic FICO adoption in Fannie Mae and Freddie Mac MBS issuance, from the
GSEs' loan-level issuance disclosure files. Plan and definitions: [notes/PLAN.md](notes/PLAN.md).
Site: https://minajpara-cyber.github.io/vantagescore-adoption-tracker/ (served from docs/, refreshed weekly).

## Layout

```
data/raw/<FNMA|FHLMC>/<intraday|monthend>/<stem>/<file>.zip   portal files, untouched, one folder each
data/collections/*.json                    what each collection pulled (portal document ids, publish dates)
data/warehouse/{loan,security}/...         one parquet per ingested file (all columns, as text)
data/warehouse/manifest.jsonl              what was ingested, with header and row counts
data/gse.duckdb                            DuckDB with the views below, for ad-hoc SQL
site/data/*.json                           aggregates the dashboard reads
site/dashboard/index.html                  the dashboard page (claude.ai Dashboard type)
site/standalone/                           template + `dash` stand-in that turn that page into a static site
docs/                                      the public site (GitHub Pages serves main:/docs), aggregates only
collector/collect.js                       browser-side collector run in a signed-in portal tab
src/gsescore/                              layouts, unpack, ingest, views, aggregates, site, CLI
```

`data/`, `site/data/` and `.venv/` are git-ignored: loan-level files never leave this computer.

Views: `loan_records` (every row, typed), `loans` (one row per agency + loan id, with `score_model`,
`pricing_score`, `issue_month`, `first_intraday_date`, `upb`), `security_records`, `securities`.

## Collecting files

The portals (fanniemae.mbs-securities.com, freddiemac.mbs-securities.com) need your login. With you
signed in, in Chrome, the portal's own API lists files (`/api/report/{fannie|freddie}/list/1/{year}`) and
serves them (`/api/report/download/{id}/{name}`). The collector fetches the loan-level issuance files in
the page, packs each portal's files into one zip with a manifest (sizes and CRCs), and saves it to
Downloads. Then:

```bash
.venv/bin/python -I -m gsescore.cli have                  # file names already collected (the collector skips them)
.venv/bin/python -I -m gsescore.cli unpack <bundle.zip>   # verifies every file, files it under data/raw
.venv/bin/python -I -m gsescore.cli refresh               # bundles in ~/Downloads -> unpack -> ingest -> build -> docs/
.venv/bin/python -I -m gsescore.cli publish               # commit docs/ and push; GitHub Pages redeploys
```

The weekly refresh is a scheduled task in the Claude app (Mondays 9:00): it opens both portals in
Chrome, asks you to sign in if needed, runs the collector, then `refresh`, updates the claude.ai
dashboard's data files, and `publish`.

Files on the portal (Oct 2026): intraday loan files `fl{YYMMDD}[_N].zip` / `FNM_ILLD_{YYYYMMDD}_{N}.zip`
back to Jul 1, 2026 (about four months kept); month-end files `FRE_ILLD_{YYYYMM}.zip` /
`FNM_ILLD_{YYYYMM}.zip` back to Dec 2025.

## Usage

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -I -m gsescore.cli ingest data/raw     # idempotent; skips files already ingested
.venv/bin/python -I -m gsescore.cli status
.venv/bin/python -I -m gsescore.cli build               # writes site/data/*.json and data/gse.duckdb
.venv/bin/python -I -m gsescore.cli sql "SELECT issue_month, score_model, count(*) FROM loans GROUP BY ALL ORDER BY ALL"
.venv/bin/python -I tests/test_pipeline.py              # synthetic end-to-end check
```
