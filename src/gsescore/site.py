"""Build the public static site in docs/ (GitHub Pages serves main:/docs).

The dashboard page (site/dashboard/index.html) is written for the claude.ai Dashboard type, which
supplies a `dash` object and theme tokens. site/standalone/ holds a stand-in for both, so the same page
source serves the claude.ai dashboard and the public site. Only the aggregate datasets are copied.
"""
import shutil

from . import paths

DATASETS = ["monthly", "weekly", "lenders", "composition", "profile", "summary", "events"]
DOCS = paths.ROOT / "docs"
STANDALONE = paths.ROOT / "site" / "standalone"
PAGE = paths.ROOT / "site" / "dashboard" / "index.html"


def build_site() -> list[str]:
    template = (STANDALONE / "template.html").read_text()
    assert template.count("<!--PAGE-->") == 1
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(template.replace("<!--PAGE-->", PAGE.read_text()))
    shutil.copyfile(STANDALONE / "dash-shim.js", DOCS / "dash-shim.js")
    (DOCS / ".nojekyll").write_text("")
    for name in DATASETS:
        shutil.copyfile(paths.SITE_DATA / f"{name}.json", DOCS / "data" / f"{name}.json")
    return sorted(str(p.relative_to(DOCS)) for p in DOCS.rglob("*") if p.is_file())
