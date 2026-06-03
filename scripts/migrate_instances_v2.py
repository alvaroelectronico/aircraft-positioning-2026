"""
migrate_instances_v2.py — one-shot migration that augments every instance
JSON under ``data/instances_202605/`` with the paper-#2 optional fields:

    Top level:        mu, delta, eta
    Per job:          interruptible

The default values match the documented paper-#2 defaults; they are chosen so
that paper-#1 code paths are unaffected:

    DEFAULT_MU             = 1.0    # Mode-B inter-job pause (days)
    DEFAULT_DELTA          = 2.0    # Mode-C job extension (days)
    DEFAULT_ETA            = 1.0    # strict-inequality granularity (days)
    DEFAULT_INTERRUPTIBLE  = False  # every job non-interruptible by default

The migration is **idempotent**: if a field is already present, it is left
untouched.  Running the script twice produces no further changes.

Usage
-----
    python scripts/migrate_instances_v2.py
    python scripts/migrate_instances_v2.py --dry-run        # report only
    python scripts/migrate_instances_v2.py --root data/...  # custom root
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MU            = 1.0
DEFAULT_DELTA         = 2.0
DEFAULT_ETA           = 1.0
DEFAULT_INTERRUPTIBLE = False


def augment_instance(data: dict) -> tuple[dict, list[str]]:
    """Return a copy of *data* with the paper-#2 fields filled in.

    Returns
    -------
    (augmented_data, changes_log) — the second item lists which fields were
    added (empty if no change was needed).
    """
    changes: list[str] = []
    out = dict(data)

    if "mu" not in out:
        out["mu"] = DEFAULT_MU
        changes.append("mu")
    if "delta" not in out:
        out["delta"] = DEFAULT_DELTA
        changes.append("delta")
    if "eta" not in out:
        out["eta"] = DEFAULT_ETA
        changes.append("eta")

    new_jobs = []
    n_jobs_modified = 0
    for j in out.get("jobs", []):
        nj = dict(j)
        if "interruptible" not in nj:
            nj["interruptible"] = DEFAULT_INTERRUPTIBLE
            n_jobs_modified += 1
        new_jobs.append(nj)
    if n_jobs_modified:
        out["jobs"] = new_jobs
        changes.append(f"interruptible (×{n_jobs_modified} jobs)")

    return out, changes


def _write_json(path: Path, data: dict) -> None:
    """Write *data* as pretty-printed JSON, two-space indentation."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def migrate(root: Path, dry_run: bool) -> int:
    """Walk *root* and migrate every scn_*.json found.

    Returns the number of files that needed (or would need) modification.
    """
    files = sorted(root.glob("scn_*/scn_*.json"))
    if not files:
        print(f"No scn_*.json files under {root}", file=sys.stderr)
        return 0

    modified = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        augmented, changes = augment_instance(data)
        if not changes:
            continue
        modified += 1
        if dry_run:
            print(f"[dry-run] {path.relative_to(root)} would add: {changes}")
        else:
            _write_json(path, augmented)
            print(f"updated  {path.relative_to(root)}  +{changes}")
    print(
        f"\n{modified} / {len(files)} file(s) "
        f"{'would be' if dry_run else ''} updated."
    )
    return modified


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "instances_202605",
        help="Root folder containing scn_*/scn_*.json (default: data/instances_202605).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which files would be modified without writing.",
    )
    args = ap.parse_args()
    migrate(args.root, args.dry_run)


if __name__ == "__main__":
    main()
