#!/usr/bin/env python3
"""Convert a policy CSV feed into LifePass benefit JSON.

Usage:
    python scripts/ingest_policy_feed.py input.csv --out data/imported_benefits.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.policy_ingestion import benefits_from_dataframe, save_imported_benefits  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--out", default=str(ROOT / "data" / "imported_benefits.json"))
    args = parser.parse_args()
    df = pd.read_csv(args.csv_path)
    benefits, warnings = benefits_from_dataframe(df)
    out = save_imported_benefits(benefits, args.out)
    print(f"saved {len(benefits)} benefits to {out}")
    for warning in warnings:
        print("WARNING:", warning)


if __name__ == "__main__":
    main()
