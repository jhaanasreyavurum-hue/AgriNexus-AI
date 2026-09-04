"""Build the segment × district eligibility matrix (MODELLED analytics backbone).

    python3 scripts/build_segment_matrix.py [--workers 2] [--limit N]

Runs the real KB engines over every district × segment archetype and writes
data/derived/segment_matrix.csv (+ .meta.json with a KB fingerprint).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.kb import load_knowledge_base  # noqa: E402
from core.intelligence.matrix import build_segment_matrix, save_segment_matrix, MATRIX_PATH, plan_jobs  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    kb = load_knowledge_base()
    jobs = plan_jobs(kb)
    print(f"{len(jobs)} district/crop jobs × 11 segments → building with {a.workers} workers …")
    t0 = time.time()

    def prog(i, n):
        if i % 10 == 0 or i == n:
            print(f"  {i}/{n}  ({time.time() - t0:.0f} s)", flush=True)

    df = build_segment_matrix(kb, workers=a.workers, limit=a.limit, progress=prog)
    save_segment_matrix(df)
    err = int(df["error"].notna().sum()) if "error" in df.columns else 0
    print(f"wrote {MATRIX_PATH} — {len(df)} rows, {df.district.nunique()} districts, {err} errors, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
