"""Command line: gsescore {have,unpack,refresh,ingest,status,build,site,publish,sql}."""
import argparse
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from . import paths

# Bundles saved by collector/collect.js; Chrome may add " (1)" to a repeated name.
BUNDLE = re.compile(r"^(freddie|fannie)_loan_files_\d{4}-\d{2}-\d{2}( \(\d+\))?\.zip$")


def cmd_have(args):
    print(json.dumps(sorted({p.name for p in paths.RAW.rglob("*.zip")})))


def cmd_refresh(args):
    """Bundles in Downloads -> data/inbox -> unpack -> ingest -> build -> docs/."""
    from .aggregate import build
    from .bundle import unpack_bundle
    from .ingest import ingest_paths
    from .site import build_site
    from .warehouse import refresh_db
    report = {"bundles": [], "kept_in_inbox": []}
    for b in sorted(p for p in args.downloads.glob("*.zip") if BUNDLE.match(p.name)):
        box = paths.DATA / "inbox" / b.stem.replace(" ", "_")
        box.mkdir(parents=True)  # a new, empty folder per bundle
        moved = Path(shutil.move(str(b), box / b.name))
        r = unpack_bundle(moved)
        report["bundles"].append({k: r[k] for k in ("bundle", "files_in_manifest", "written", "unchanged", "conflicts", "errors")})
        if r["errors"] or r["conflicts"]:
            report["kept_in_inbox"].append(str(moved.relative_to(paths.ROOT)))
        else:
            moved.unlink()
            box.rmdir()
    ingested = [r for r in ingest_paths([paths.RAW]) if r["status"] == "ingested"]
    report["ingested_files"] = len(ingested)
    report["ingested_rows"] = sum(r["rows"] for r in ingested)
    meta = build()
    refresh_db()
    build_site()
    report.update({k: meta[k] for k in ("loans", "last_issue_month", "last_disclosed")})
    print(json.dumps(report, indent=1))


def cmd_site(args):
    from .site import build_site
    print("\n".join(build_site()))


def cmd_publish(args):
    """Commit docs/ (the public site) and push it; GitHub Pages redeploys from main:/docs."""
    def git(*a, check=True):
        return subprocess.run(["git", "-C", str(paths.ROOT), *a], check=check, capture_output=True, text=True)
    git("add", "docs")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("nothing to publish")
        return
    summary = json.loads((paths.ROOT / "docs" / "data" / "summary.json").read_text())["rows"]
    through = next((r["data_through"] for r in summary if r["agency"] == "All"), "unknown")
    git("commit", "-m", f"Refresh data through {through}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    print(git("push", "origin", "HEAD").stderr.strip() or "pushed")


def cmd_unpack(args):
    from .bundle import unpack_bundle
    for b in args.bundles:
        r = unpack_bundle(b)
        print(f"{r['bundle']}: {r['files_in_manifest']} files from {r['source']} ({r['collected_at']}); "
              f"wrote {r['written']} ({r['bytes'] / 1e6:.1f} MB), unchanged {r['unchanged']}, "
              f"conflicts {len(r['conflicts'])}, errors {len(r['errors'])}")
        for line in r["conflicts"] + r["errors"]:
            print("   !", line)


def cmd_ingest(args):
    from .ingest import ingest_paths
    results = ingest_paths(args.paths or [paths.RAW], force=args.force)
    counts = Counter(r["status"] for r in results)
    for r in results:
        if r["status"] == "ingested":
            print(f"  + {r['agency']}/{r['kind']}/{r['level']} {r['member']}: {r['rows']:,} rows"
                  + (f"  ({r['note']})" if r.get("note") else ""))
    print(f"ingested {counts['ingested']}, skipped {counts['skipped']} (already in manifest)")


def cmd_status(args):
    from .warehouse import connect
    con = connect()
    print(con.sql("""SELECT agency, kind, count(DISTINCT source_file) AS files, min(file_date) AS first,
                     max(file_date) AS last, count(*) AS records FROM loan_records GROUP BY ALL ORDER BY ALL"""))
    print(con.sql("""SELECT agency, issue_month, score_model, count(*) AS loans, round(sum(upb)/1e9, 2) AS upb_bn
                     FROM loans GROUP BY ALL ORDER BY ALL"""))


def cmd_build(args):
    from .aggregate import build
    from .warehouse import refresh_db
    meta = build()
    refresh_db()
    print(json.dumps({k: meta[k] for k in ("loans", "first_issue_month", "last_issue_month", "first_disclosed", "last_disclosed", "datasets")}, indent=1))


def cmd_sql(args):
    from .warehouse import connect
    print(connect().sql(args.query))


def main():
    p = argparse.ArgumentParser(prog="gsescore")
    sub = p.add_subparsers(required=True)
    sub.add_parser("have", help="list the file names already collected (JSON)").set_defaults(fn=cmd_have)
    s = sub.add_parser("unpack", help="verify a browser collection bundle and file it under data/raw")
    s.add_argument("bundles", nargs="+", type=Path)
    s.set_defaults(fn=cmd_unpack)
    s = sub.add_parser("refresh", help="unpack new bundles from Downloads, ingest, build, rebuild docs/")
    s.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    s.set_defaults(fn=cmd_refresh)
    sub.add_parser("site", help="rebuild the public site in docs/").set_defaults(fn=cmd_site)
    sub.add_parser("publish", help="commit docs/ and push to GitHub").set_defaults(fn=cmd_publish)
    s = sub.add_parser("ingest", help="parse raw files into the parquet warehouse")
    s.add_argument("paths", nargs="*", type=Path)
    s.add_argument("--force", action="store_true", help="re-ingest files already in the manifest")
    s.set_defaults(fn=cmd_ingest)
    sub.add_parser("status", help="show warehouse coverage").set_defaults(fn=cmd_status)
    sub.add_parser("build", help="build site/data/*.json and data/gse.duckdb").set_defaults(fn=cmd_build)
    s = sub.add_parser("sql", help="run a query against the views")
    s.add_argument("query")
    s.set_defaults(fn=cmd_sql)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
