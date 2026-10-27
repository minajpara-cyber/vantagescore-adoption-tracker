"""Parse raw disclosure files (zip or txt, pipe-delimited) into one parquet file per member.

Every column is stored as a string with canonical names; typing and derivations happen in the
DuckDB views (warehouse.py) so a layout change never breaks ingestion. A JSONL manifest records
each ingested member (keyed by sha256) so re-running ingest is idempotent.
"""
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from . import paths
from .files import classify
from .layout import detect_level, map_header, positional_header

BATCH_BYTES = 64 << 20


def _sha256(data_or_path) -> str:
    h = hashlib.sha256()
    if isinstance(data_or_path, Path):
        with open(data_or_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    else:
        h.update(data_or_path)
    return h.hexdigest()


def load_manifest() -> dict[str, dict]:
    if not paths.MANIFEST.exists():
        return {}
    out = {}
    for line in paths.MANIFEST.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["key"]] = rec
    return out


def _append_manifest(rec: dict) -> None:
    paths.MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(paths.MANIFEST, "a") as f:
        f.write(json.dumps(rec) + "\n")


def _members(path: Path):
    """Yield (member_name, opener) for each text file inside a zip, or the file itself."""
    if zipfile.is_zipfile(path):
        zf = zipfile.ZipFile(path)
        for info in zf.infolist():
            if not info.is_dir() and not info.filename.startswith("__MACOSX"):
                yield info.filename, (lambda i=info: zf.open(i))
    else:
        yield path.name, (lambda: open(path, "rb"))


def _encoding(sample: bytes) -> str:
    try:
        sample.decode("utf-8")
        return "utf8"
    except UnicodeDecodeError:
        return "latin1"


def ingest_file(path: Path, manifest: dict, force: bool = False) -> list[dict]:
    path = Path(path).resolve()
    info = classify(path)
    results = []
    for member, opener in _members(path):
        with opener() as fh:
            raw = fh.read()
        key = f"{_sha256(raw)}:{member}"
        if key in manifest and not force:
            results.append({**manifest[key], "status": "skipped"})
            continue
        minfo = classify(Path(*path.parts[:-1], member)) if member != path.name else info
        rec = _parse_member(path, member, raw, minfo, key)
        if rec:
            _append_manifest(rec)
            manifest[key] = rec
            results.append({**rec, "status": "ingested"})
    return results


def _parse_member(path: Path, member: str, raw: bytes, info, key: str) -> dict | None:
    first_line = raw.split(b"\n", 1)[0].decode("latin1").rstrip("\r")
    first_row = first_line.split("|")
    level, has_header = detect_level(first_row)
    level = level or info.level_hint
    if level not in ("loan", "security"):
        return {"key": key, "source": str(path), "member": member, "level": level or "unknown",
                "agency": info.agency, "kind": info.kind, "rows": 0, "note": "skipped: unrecognized layout",
                "ingested_at": datetime.now(timezone.utc).isoformat()}
    cols = map_header(level, first_row) if has_header else positional_header(level, len(first_row))
    body = (raw.split(b"\n", 1)[1] if b"\n" in raw else b"") if has_header else raw
    if body.strip() == b"":  # intraday files are published even when no pools issued
        table = pa.table({c: pa.array([], pa.string()) for c in cols if not c.startswith("_drop_")})
    else:
        table = pacsv.read_csv(
            io.BytesIO(raw),
            read_options=pacsv.ReadOptions(column_names=cols, skip_rows=1 if has_header else 0,
                                           encoding=_encoding(raw[:1_000_000]), block_size=BATCH_BYTES),
            parse_options=pacsv.ParseOptions(delimiter="|", quote_char=False),
            convert_options=pacsv.ConvertOptions(column_types={c: pa.string() for c in cols},
                                                 strings_can_be_null=False),
        )
        table = table.select([c for c in table.column_names if not c.startswith("_drop_")])

    stem = Path(member).name.rsplit(".", 1)[0]
    meta = {
        "agency": info.agency, "kind": info.kind, "file_date": info.file_date.isoformat() if info.file_date else None,
        "file_seq": info.seq, "source_file": f"{path.name}:{member}" if member != path.name else path.name,
    }
    n = table.num_rows
    for col, val in meta.items():
        typ = pa.int32() if col == "file_seq" else pa.string()
        table = table.append_column(col, pa.array([val] * n, typ))
    out = paths.WAREHOUSE / level / (info.agency or "UNKNOWN") / (info.kind or "unknown") / f"{stem}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out, compression="zstd")
    return {"key": key, "source": str(path), "member": member, "level": level, **meta,
            "has_header": has_header, "columns": len(cols), "rows": n, "out": str(out.relative_to(paths.ROOT)),
            "header": first_row if has_header else None,
            "ingested_at": datetime.now(timezone.utc).isoformat()}


def ingest_paths(targets: list[Path], force: bool = False) -> list[dict]:
    manifest = load_manifest()
    files = []
    for t in map(Path, targets):
        files += sorted(p for p in t.rglob("*") if p.is_file()) if t.is_dir() else [t]
    results = []
    for f in files:
        if f.name.startswith(".") or f.suffix.lower() not in (".zip", ".txt", ""):
            continue
        results += ingest_file(f, manifest, force=force)
    return results
