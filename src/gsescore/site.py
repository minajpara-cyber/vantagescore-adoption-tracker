"""Build the public static site in docs/ (GitHub Pages serves main:/docs), and a private preview.

The dashboard page (site/dashboard/index.html) is written for the claude.ai Dashboard type, which
supplies a `dash` object and theme tokens. site/standalone/ holds a stand-in for both, so a page
source runs as a plain static site too. Only aggregate datasets are copied.

The public site is pinned to its own copy of the page (site/public/) and dataset list: new analysis
goes to the private claude.ai dashboard first and reaches the public site only once the dashboard
page is copied there and its datasets added below (last done Nov 2, 2026, with every tab and
dataset, the rate read included). `build_preview()` builds the full dashboard page as a static site
under build/preview/ (git-ignored) for checking it locally.

reference/public_contract.json lists each public file's fields and views, names only. A test holds the
builders to it on planted data, and `contract_warnings()` reads the real docs/data for the weekly report.
"""
import hashlib
import json
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

from . import paths
from .pricing import check_warnings

# What the public page reads; keep it to datasets cleared for the public site.
PUBLIC_DATASETS = ["monthly", "weekly", "summary", "events", "sellers", "seller_monthly", "seller_weekly",
                   "seller_splits", "adoption", "adopters", "series", "borrowers", "borrower_profile",
                   "rates", "choice", "ceiling", "outlook", "rules", "score_mix", "lender_stage", "statements", "fees",
                   "week_note", "assumptions", "lender_mix", "closing", "whole_market", "private_label", "ginnie_va"]
# What the claude.ai dashboard page reads; data/dashboard_uploads.json records the version of each it has.
DASHBOARD_DATASETS = ["monthly", "weekly", "summary", "events", "sellers", "seller_monthly", "seller_weekly",
                      "seller_splits", "adoption", "adopters", "series", "borrowers", "borrower_profile",
                      "rates", "choice", "ceiling", "outlook", "rules", "score_mix", "lender_stage", "statements", "fees",
                      "week_note", "assumptions", "lender_mix", "closing", "whole_market", "private_label", "ginnie_va", "market_size", "front", "vs4_only", "pl_hmda", "vs_watch"]
# Fields the public copy of a dataset leaves out: "field" on every row, "view.field" on that view's rows, and "view.*" that view's rows. fees: the yearly
# figure "if every lender took the lower fee", withdrawn Oct 31, 2026, and what reads or scales to it. private_label: the VS4 loans naming no FICO model and
# those by year of credit report (Nov 19, 2026), which the private dashboard reads first; to publish them, take them off here and add them to the contract.
PUBLIC_DROP = {"fees": ["option_annual_usd", "option_usd", "annual_upb", "upb", "market.option_bp", "market.est_usd", "market.one_loans", "lender.option_bp", "lender.est_usd", "lender.one_loans"],
               "private_label": ["vs4_no_fico_n", "vs4_year.*"]}
RATE_READ_DAYS = 14  # the weekly report warns once the rate read's data is older than this
UPLOADS = paths.DATA / "dashboard_uploads.json"
CONTRACT = paths.REPO / "reference" / "public_contract.json"
DOCS = paths.ROOT / "docs"
PREVIEW = paths.ROOT / "build" / "preview"
STANDALONE = paths.ROOT / "site" / "standalone"
PUBLIC_PAGE = paths.ROOT / "site" / "public" / "index.html"
DASHBOARD_PAGE = paths.ROOT / "site" / "dashboard" / "index.html"


def public_rows(name: str, rows: list[dict]) -> list[dict]:
    """A dataset's rows as the public site carries them, without its fields and views in PUBLIC_DROP."""
    drop = PUBLIC_DROP.get(name, [])
    everywhere = {d for d in drop if "." not in d}
    views = {d[:-2] for d in drop if d.endswith(".*")}
    in_view = {tuple(d.split(".")) for d in drop if "." in d and not d.endswith(".*")}
    return [{k: v for k, v in r.items() if k not in everywhere and (r.get("view"), k) not in in_view} for r in rows if r.get("view") not in views]


def _build(out: Path, page: Path, datasets: list[str], public: bool = False) -> list[str]:
    template = (STANDALONE / "template.html").read_text()
    assert template.count("<!--PAGE-->") == 1
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(template.replace("<!--PAGE-->", page.read_text()))
    shutil.copyfile(STANDALONE / "dash-shim.js", out / "dash-shim.js")
    for extra in [*page.parent.glob("*.js"), *page.parent.glob("*.css")]:  # a page's other files (the claude.ai store holds them as files/<name>)
        shutil.copyfile(extra, out / extra.name)
    (out / ".nojekyll").write_text("")
    for name in datasets:
        if public and name in PUBLIC_DROP:
            rows = public_rows(name, json.loads((paths.SITE_DATA / f"{name}.json").read_text())["rows"])
            (out / "data" / f"{name}.json").write_text(json.dumps({"rows": rows}, separators=(",", ":")))
        else:
            shutil.copyfile(paths.SITE_DATA / f"{name}.json", out / "data" / f"{name}.json")
    for old in (out / "data").glob("*.json"):  # a dataset the page no longer reads
        if old.stem not in datasets:
            old.unlink()
    return sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())


def build_site() -> list[str]:
    return _build(DOCS, PUBLIC_PAGE, PUBLIC_DATASETS, public=True)


def build_preview() -> list[str]:
    if PREVIEW.exists():
        shutil.rmtree(PREVIEW)
    return _build(PREVIEW, DASHBOARD_PAGE, DASHBOARD_DATASETS)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dashboard_changes() -> list[dict]:
    """Dashboard datasets whose file differs from the version last uploaded (url is that upload)."""
    done = json.loads(UPLOADS.read_text()) if UPLOADS.exists() else {}
    out = []
    for name in DASHBOARD_DATASETS:
        path = paths.SITE_DATA / f"{name}.json"
        if not path.exists():
            continue
        sha = _sha256(path)
        if done.get(name, {}).get("sha256") != sha:
            out.append({"id": name, "path": str(path), "sha256": sha, "uploaded_url": done.get(name, {}).get("url")})
    return out


def dashboard_record(urls: dict[str, str]) -> dict:
    """Records that each dataset's current file is now on the dashboard at the given /_blob/ url."""
    done = json.loads(UPLOADS.read_text()) if UPLOADS.exists() else {}
    for name, url in urls.items():
        if name not in DASHBOARD_DATASETS or not re.fullmatch(r"/_blob/[0-9a-f]{32}", url):
            raise ValueError(f"not a dashboard dataset and /_blob/ url: {name}={url}")
        done[name] = {"sha256": _sha256(paths.SITE_DATA / f"{name}.json"), "url": url}
    UPLOADS.write_text(json.dumps(done, indent=1, sort_keys=True))
    return done


def _contract_gaps(name: str, want: dict, rows: list[dict]) -> list[str]:
    if not rows:
        return [f"{name}: the public file has no rows"]
    out = []
    missing = [k for k in want["fields"] if not any(k in r for r in rows)]
    if missing:
        out.append(f"{name}: fields missing: {', '.join(missing)}")
    extra = sorted({k for r in rows for k in r} - set(want["fields"]))
    if extra:
        out.append(f"{name}: fields outside the contract: {', '.join(extra)}")
    other = sorted({r["view"] for r in rows if r.get("view") is not None} - set(want["views"])) if want["views"] else []
    if other:
        out.append(f"{name}: views outside the contract: {', '.join(other)}")
    if any(r.get("kind") == "rate" for r in rows):
        out.append(f"{name}: has a rate line, withdrawn Oct 31, 2026")
    for view, keys in want["views"].items():
        mine = [r for r in rows if r.get("view") == view]
        if not mine:
            out.append(f"{name}: view missing: {view}")
            continue
        empty = [k for k in keys if k not in missing and all(r.get(k) is None for r in mine)]
        if empty:
            out.append(f"{name}: view {view} has nothing in: {', '.join(empty)}")
    return out


def contract_warnings() -> list[str]:
    """Plain-text warnings for a view or field of the public contract missing from docs/data, one outside it, or a withdrawn rate line. Never raises: a thin view dropping out must not stop a weekly run."""
    try:
        contract = list(json.loads(CONTRACT.read_text()).items())
    except Exception as e:
        return [f"public contract: could not read {CONTRACT.name}: {e}"]
    out = []
    for name, want in contract:
        try:
            out += _contract_gaps(name, want, json.loads((DOCS / "data" / f"{name}.json").read_text())["rows"])
        except Exception as e:
            out.append(f"{name}: could not read the public file: {e}")
    return out


def rate_read_status(today: date | None = None) -> tuple[str | None, list[str]]:
    """The date of the rate read (rates.json's meta row), a warning if it is old, missing or unreadable, and one for each build check that missed. Never raises."""
    try:
        rows = json.loads((paths.SITE_DATA / "rates.json").read_text())["rows"]
        as_of = next(r["as_of"] for r in rows if r.get("view") == "meta")
        age = (today or date.today()) - date.fromisoformat(as_of)
        checks = check_warnings(rows)
    except Exception as e:
        return None, [f"rate read: could not read the date in site/data/rates.json: {e!r}"]
    if age > timedelta(days=RATE_READ_DAYS):
        return as_of, [f"rate read: data through {as_of} is {age.days} days old, past the {RATE_READ_DAYS}-day limit", *checks]
    return as_of, checks


def front_warnings() -> list[str]:
    """The first screen's checks that missed, and a build that stopped, as plain text for the weekly report. Never raises: these files are private, and a thin week must not stop a run."""
    out = []
    try:
        error = json.loads((paths.SITE_DATA / "meta.json").read_text()).get("front_error")
        if error:
            out.append(f"first screen: it did not build, so the last good files stay: {error}")
        rows = json.loads((paths.SITE_DATA / "vs4_only.json").read_text())["rows"]
    except Exception as e:
        return [*out, f"first screen: could not read its files in site/data: {e!r}"]
    return out + [f"first screen check: {r['label']}. {r.get('detail') or ''}".strip() for r in rows if r.get("view") == "check" and not r.get("pass")]
