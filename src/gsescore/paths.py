"""Project directory layout. Override the root with GSESCORE_HOME."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # code and hand-kept reference files, whatever the data root
ROOT = Path(os.environ.get("GSESCORE_HOME", REPO))
DATA = ROOT / "data"
RAW = DATA / "raw"              # downloaded files, untouched: raw/{FNMA,FHLMC}/{intraday,monthend,monthly}/
WAREHOUSE = DATA / "warehouse"  # one parquet per ingested file: warehouse/{loan,security}/{agency}/{kind}/
MANIFEST = WAREHOUSE / "manifest.jsonl"
HMDA = DATA / "hmda"              # the federal mortgage record, one parquet per year
GINNIE = DATA / "ginnie"          # counts from Ginnie Mae's monthly loan files, one parquet per issue month
DB = DATA / "gse.duckdb"
SITE_DATA = ROOT / "site" / "data"
