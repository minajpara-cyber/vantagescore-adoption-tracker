"""The GSEs' upfront fee grid: reference/llpa.csv, from Freddie Mac Guide Exhibit 19 (Bulletin 2026-K)."""
import csv

from . import paths

GRID_CSV = paths.REPO / "reference" / "llpa.csv"
FEE_WAIVED = ("F", "H", "R")  # HFA, HomeReady / Home Possible, RefiNow / Refi Possible: credit fee caps generally cover them


def load_grid() -> dict[tuple[str, int, int], float]:
    with GRID_CSV.open(newline="") as f:
        return {(r["grid"], int(r["score_bucket"]), int(r["ltv_bucket"])): float(r["fee_pct"]) for r in csv.DictReader(f)}
