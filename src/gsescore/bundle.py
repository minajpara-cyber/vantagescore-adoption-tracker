"""Unpack a collection bundle into data/raw.

The browser collector packs each portal's files into one zip so a single download carries them:

  manifest.json                     {source, collected_at, files: [{agency, kind, name, id, report,
                                     effectiveDate, bytes, crc32}]}
  <AGENCY>/<intraday|monthend>/<name>   the file exactly as the portal served it

Each file is checked against the portal's size and the CRC computed in the browser, then written to
data/raw/<AGENCY>/<kind>/<stem>/<name> (one directory per file). The manifest is kept under
data/collections/ for provenance (portal document ids and publication dates).
"""
import hashlib
import io
import json
import re
import zipfile
import zlib
from pathlib import Path

from . import paths

AGENCIES = {"FHLMC", "FNMA"}
KINDS = {"intraday", "monthend", "monthly"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def unpack_bundle(bundle: Path) -> dict:
    bundle = Path(bundle)
    out = {"bundle": bundle.name, "written": 0, "unchanged": 0, "conflicts": [], "errors": [], "bytes": 0}
    with zipfile.ZipFile(bundle) as z:
        manifest = json.loads(z.read("manifest.json"))
        members = set(z.namelist())
        for f in manifest["files"]:
            agency, kind, name = f["agency"], f["kind"], f["name"]
            if agency not in AGENCIES or kind not in KINDS or not SAFE_NAME.match(name) or ".." in name:
                out["errors"].append(f"unsafe entry: {agency}/{kind}/{name}")
                continue
            member = f"{agency}/{kind}/{name}"
            if member not in members:
                out["errors"].append(f"missing from bundle: {member}")
                continue
            data = z.read(member)
            if len(data) != f["bytes"] or zlib.crc32(data) != f["crc32"]:
                out["errors"].append(f"size/CRC mismatch: {member}")
                continue
            if name.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as inner:
                        bad = inner.testzip()
                        if bad is not None:
                            raise zipfile.BadZipFile(f"corrupt member {bad}")
                except zipfile.BadZipFile as e:
                    out["errors"].append(f"bad zip {member}: {e}")
                    continue
            stem = name[:-4] if name.lower().endswith(".zip") else name
            dest = paths.RAW / agency / kind / stem / name
            if dest.exists():
                if _sha256(dest.read_bytes()) == _sha256(data):
                    out["unchanged"] += 1
                else:
                    out["conflicts"].append(member)  # never overwrite raw data silently
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            out["written"] += 1
            out["bytes"] += len(data)
    coll = paths.DATA / "collections"
    coll.mkdir(parents=True, exist_ok=True)
    record = coll / f"{bundle.stem}.json"
    n = 1
    while record.exists():  # a second bundle the same day: keep both records
        record = coll / f"{bundle.stem}_{n}.json"
        n += 1
    record.write_text(json.dumps(manifest, indent=1))
    out["files_in_manifest"] = len(manifest["files"])
    out["source"] = manifest.get("source")
    out["collected_at"] = manifest.get("collected_at")
    return out
