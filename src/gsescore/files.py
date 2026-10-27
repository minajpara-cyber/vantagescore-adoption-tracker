"""Identify agency, file kind, date and intraday sequence from a disclosure file's path.

Freddie Mac names (Disclosure Guide v6.3):
  flYYMMDD[_N]  daily issuance loan file, intraday #N (6:30am, 10:30am, 1:30pm, 3:30pm ET; not cumulative)
  dnYYMMDD[_N]  daily issuance security file      wfYYMMDD[_N]  daily issuance supplemental file
  fuYYMMDD      monthly loan file                  fdYYMMDD      monthly security file
Fannie Mae names (PoolTalk): FNM_ILLD_YYYYMMDD[_N] intraday issuance loan file; other names are
classified from their folder (raw/<AGENCY>/<kind>/) plus the header row.
"""
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

KINDS = ("intraday", "monthend", "monthly")

_FREDDIE = {
    "fl": ("loan", "intraday"), "dn": ("security", "intraday"), "wf": ("supplemental", "intraday"),
    "fu": ("loan", "monthly"), "fd": ("security", "monthly"), "fq": ("supplemental", "monthly"),
}


@dataclass
class FileInfo:
    agency: str | None
    kind: str | None
    level_hint: str | None
    file_date: date | None
    seq: int


def _ymd(token: str) -> date | None:
    try:
        if len(token) == 8:
            return date(int(token[:4]), int(token[4:6]), int(token[6:]))
        if len(token) == 6:
            return date(2000 + int(token[:2]), int(token[2:4]), int(token[4:]))
    except ValueError:
        return None
    return None


def classify(path: Path) -> FileInfo:
    name = path.name
    parts = [p.upper() for p in path.parts]
    agency = "FNMA" if "FNMA" in parts else "FHLMC" if "FHLMC" in parts else None
    kind = next((p.lower() for p in parts if p.lower() in KINDS), None)

    m = re.match(r"^(fl|dn|wf|fu|fd|fq)(\d{6})(?:_(\d+))?\b", name, re.I)
    if m:
        level, k = _FREDDIE[m.group(1).lower()]
        return FileInfo(agency or "FHLMC", kind or k, level, _ymd(m.group(2)), int(m.group(3) or 1))

    if name.upper().startswith("FNM"):
        agency = agency or "FNMA"
    m = re.search(r"(?<!\d)(\d{8})(?:_(\d+))?(?!\d)", name)
    d = _ymd(m.group(1)) if m else None
    if d is None:
        m6 = re.search(r"(?<!\d)(\d{6})(?!\d)", name)
        d = _ymd(m6.group(1)) if m6 else None
        if d is None and m6:  # YYYYMM monthly stamp
            t = m6.group(1)
            try:
                d = date(int(t[:4]), int(t[4:]), 1)
            except ValueError:
                d = None
    seq = int(m.group(2)) if m and m.group(2) else 1
    level = "loan" if re.search(r"LLD|LOAN", name, re.I) else None
    if kind is None and re.search(r"_ILLD_|_IS_", name, re.I):
        kind = "intraday"
    return FileInfo(agency, kind, level, d, seq)
