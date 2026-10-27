"""Project directory layout. Override the root with GSESCORE_HOME."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("GSESCORE_HOME", Path(__file__).resolve().parents[2]))
DATA = ROOT / "data"
RAW = DATA / "raw"              # downloaded files, untouched: raw/{FNMA,FHLMC}/{intraday,monthend,monthly}/
WAREHOUSE = DATA / "warehouse"  # one parquet per ingested file: warehouse/{loan,security}/{agency}/{kind}/
MANIFEST = WAREHOUSE / "manifest.jsonl"
DB = DATA / "gse.duckdb"
SITE_DATA = ROOT / "site" / "data"
