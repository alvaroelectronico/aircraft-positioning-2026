"""
clean_solutions.py — Keep results.csv and solution JSONs in sync.

Rules:
  - Remove CSV rows whose JSON file does not exist.
  - Remove JSON files that have no matching row in the CSV.

The link between a CSV row and a JSON file is the triple
(instance, solver, timestamp), which forms the JSON filename:
    <instance>__<solver>__<timestamp>.json

Usage
-----
    python scripts/clean_solutions.py              # dry-run (shows what would change)
    python scripts/clean_solutions.py --apply      # apply changes
    python scripts/clean_solutions.py --dir path/to/solutions
"""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DIR = _ROOT / "data" / "solutions"


def _json_name(row: dict) -> str:
    return f"{row['instance']}__{row['solver']}__{row['timestamp']}.json"


def clean(solutions_dir: Path, apply: bool) -> None:
    csv_path = solutions_dir / "results.csv"

    if not csv_path.exists():
        print("No results.csv found — nothing to do.")
        return

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys()) if rows else []

    existing_jsons: set[str] = {p.name for p in solutions_dir.glob("*.json")}
    csv_json_names: set[str] = {_json_name(r) for r in rows}

    # --- orphan CSV rows (JSON missing) ---
    kept_rows = [r for r in rows if _json_name(r) in existing_jsons]
    dropped_rows = [r for r in rows if _json_name(r) not in existing_jsons]

    # --- orphan JSONs (CSV row missing) ---
    orphan_jsons = [
        solutions_dir / name
        for name in existing_jsons
        if name not in csv_json_names
    ]

    # --- report ---
    print(f"\nSolutions dir : {solutions_dir}")
    print(f"CSV rows      : {len(rows)}  ->  keeping {len(kept_rows)}, dropping {len(dropped_rows)}")
    print(f"JSON files    : {len(existing_jsons)}  ->  removing {len(orphan_jsons)} orphans")

    if dropped_rows:
        print("\n  CSV rows to drop (JSON not found):")
        for r in dropped_rows:
            print(f"    - {_json_name(r)}")

    if orphan_jsons:
        print("\n  JSON files to delete (no CSV row):")
        for p in sorted(orphan_jsons):
            print(f"    - {p.name}")

    if not dropped_rows and not orphan_jsons:
        print("\n  Everything is in sync — nothing to clean.")
        return

    if not apply:
        print("\n  Dry-run mode: no changes made. Use --apply to apply.")
        return

    # --- apply ---
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)
    print(f"\n  results.csv rewritten ({len(kept_rows)} rows kept).")

    for p in orphan_jsons:
        p.unlink()
        print(f"  Deleted: {p.name}")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync results.csv with solution JSON files.")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--dir", default=str(_DEFAULT_DIR), help="Solutions directory")
    args = parser.parse_args()

    clean(Path(args.dir), apply=args.apply)
