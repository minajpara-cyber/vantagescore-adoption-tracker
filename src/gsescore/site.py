"""Build the public static site in docs/ (GitHub Pages serves main:/docs), and a private preview.

The dashboard page (site/dashboard/index.html) is written for the claude.ai Dashboard type, which
supplies a `dash` object and theme tokens. site/standalone/ holds a stand-in for both, so a page
source runs as a plain static site too. Only aggregate datasets are copied.

The public site is pinned to its own page (site/public/index.html) and dataset list: new analysis
goes to the private claude.ai dashboard first and reaches the public site only once the dashboard
page is copied there and its datasets added below (last done Oct 29, 2026). `build_preview()` builds
the full dashboard page as a static site under build/preview/ (git-ignored) for checking it locally.
"""
import hashlib
import json
import re
import shutil
from pathlib import Path

from . import paths

# What the public page reads; keep it to datasets cleared for the public site.
PUBLIC_DATASETS = ["monthly", "weekly", "composition", "profile", "summary", "events", "sellers", "seller_monthly",
                   "seller_weekly", "seller_splits", "adoption", "adopters", "series", "highlights", "asof"]
# What the claude.ai dashboard page reads; data/dashboard_uploads.json records the version of each it has.
DASHBOARD_DATASETS = ["monthly", "weekly", "summary", "events", "sellers", "seller_monthly", "seller_weekly",
                      "seller_splits", "adoption", "adopters", "series", "asof", "borrowers", "borrower_profile",
                      "pricing", "choice", "ceiling", "outlook", "rules", "score_mix", "lender_stage", "statements", "fees",
                      "week_note", "assumptions"]
UPLOADS = paths.DATA / "dashboard_uploads.json"
DOCS = paths.ROOT / "docs"
PREVIEW = paths.ROOT / "build" / "preview"
STANDALONE = paths.ROOT / "site" / "standalone"
PUBLIC_PAGE = paths.ROOT / "site" / "public" / "index.html"
DASHBOARD_PAGE = paths.ROOT / "site" / "dashboard" / "index.html"


def _build(out: Path, page: Path, datasets: list[str]) -> list[str]:
    template = (STANDALONE / "template.html").read_text()
    assert template.count("<!--PAGE-->") == 1
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(template.replace("<!--PAGE-->", page.read_text()))
    shutil.copyfile(STANDALONE / "dash-shim.js", out / "dash-shim.js")
    for script in page.parent.glob("*.js"):  # a page's other files (the claude.ai store holds them as files/<name>)
        shutil.copyfile(script, out / script.name)
    (out / ".nojekyll").write_text("")
    for name in datasets:
        shutil.copyfile(paths.SITE_DATA / f"{name}.json", out / "data" / f"{name}.json")
    for old in (out / "data").glob("*.json"):  # a dataset the page no longer reads
        if old.stem not in datasets:
            old.unlink()
    return sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())


def build_site() -> list[str]:
    return _build(DOCS, PUBLIC_PAGE, PUBLIC_DATASETS)


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
