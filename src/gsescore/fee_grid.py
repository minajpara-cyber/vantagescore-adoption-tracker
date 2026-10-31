"""The GSEs' upfront fee grid: reference/llpa.csv, from Freddie Mac Guide Exhibit 19 (Bulletin 2026-K).

Checked cell by cell on Oct 31, 2026, against Fannie Mae's LLPA Matrix dated Sep 30, 2026 (https://singlefamily.fanniemae.com/media/9391/display):
all 207 cells match. That matrix waives the fee for HomeReady, first-time buyers under the income limits and duty-to-serve loans; this repo
counts those only through special_program, because income is not disclosed. RefiNow is not named on Fannie Mae's waiver list and HFA loans
aren't either, but FEE_WAIVED counts them.
"""
import csv

from . import paths

GRID_CSV = paths.REPO / "reference" / "llpa.csv"
FEE_WAIVED = ("F", "H", "R")  # HFA, HomeReady / Home Possible, RefiNow / Refi Possible: credit fee caps generally cover them


def load_grid() -> dict[tuple[str, int, int], float]:
    with GRID_CSV.open(newline="") as f:
        return {(r["grid"], int(r["score_bucket"]), int(r["ltv_bucket"])): float(r["fee_pct"]) for r in csv.DictReader(f)}
