"""
migrate_instances_v2.py — augments instance JSONs with the paper-#2 fields.

Two operating modes:

1. **Default (idempotent)** — adds the optional paper-#2 fields with safe
   defaults, leaving any existing values untouched:

       Top level: min_separation (0.5), mu (1.0), delta (2.0), eta (1.0)
       Per job:   interruptible (False)

   Running the script twice produces no further changes.

2. **Annotation mode** — when ``--interruptible-rate FLOAT`` is supplied,
   every job's ``interruptible`` flag is **rewritten** by a reproducible
   per-instance random draw:

       u ~ Uniform[0, 1)
       interruptible = (u < rate)

   The RNG is seeded with ``(base_seed, instance_stem)``, so the same
   ``--seed`` produces byte-identical files across machines, but each
   instance gets an independent draw sequence.  The top-level
   min_separation / mu / delta / eta are still filled in with defaults
   where absent.  This is the mode used to build the paper-#2
   "with interruptibility" benchmark.

The script is safe to use on instances that came from older versions of
the generator that did not emit ``min_separation`` — that field is added
too when absent so that ``validate_instance()`` accepts the result.

Usage
-----
    # Plain default migration (idempotent)
    python scripts/migrate_instances_v2.py

    # Custom root (e.g. the alternate-benchmark folder)
    python scripts/migrate_instances_v2.py --root data/instances_202605_02

    # Annotate with 30 % random interruptibility, reproducibly
    python scripts/migrate_instances_v2.py \
        --root data/instances_202605_02 \
        --interruptible-rate 0.3 \
        --seed 42

    # Preview changes without writing
    python scripts/migrate_instances_v2.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

DEFAULT_MIN_SEPARATION = 0.5
DEFAULT_MU             = 1.0
DEFAULT_DELTA          = 2.0
DEFAULT_ETA            = 1.0
DEFAULT_INTERRUPTIBLE  = False
DEFAULT_BASE_SEED      = 42


def _seed_for_instance(base_seed: int, instance_stem: str) -> int:
    """Return a reproducible per-instance integer seed."""
    h = hashlib.sha256(f"{base_seed}::{instance_stem}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFF_FFFF


def augment_instance(
    data: dict,
    instance_stem: str,
    interruptible_rate: float | None,
    base_seed: int,
) -> tuple[dict, list[str]]:
    """Return a copy of *data* with the paper-#2 fields filled in.

    Parameters
    ----------
    data
        Raw instance dict (as loaded from JSON).
    instance_stem
        Filename stem (used to derive the per-instance RNG seed).
    interruptible_rate
        If not None, every job's ``interruptible`` flag is OVERWRITTEN by a
        random draw with this probability.  If None, the field is only
        added when missing, defaulting to False.
    base_seed
        Base seed combined with *instance_stem* into the per-instance RNG.

    Returns
    -------
    (augmented_data, changes_log) — *changes_log* lists which fields were
    added or rewritten (empty if no change was needed).
    """
    changes: list[str] = []
    out = dict(data)

    if "min_separation" not in out:
        out["min_separation"] = DEFAULT_MIN_SEPARATION
        changes.append("min_separation")
    if "mu" not in out:
        out["mu"] = DEFAULT_MU
        changes.append("mu")
    if "delta" not in out:
        out["delta"] = DEFAULT_DELTA
        changes.append("delta")
    if "eta" not in out:
        out["eta"] = DEFAULT_ETA
        changes.append("eta")

    # Annotate / fill interruptibility
    rng = random.Random(_seed_for_instance(base_seed, instance_stem))
    new_jobs: list[dict] = []
    n_jobs_modified  = 0
    n_jobs_marked_T  = 0
    for j in out.get("jobs", []):
        nj = dict(j)
        if interruptible_rate is not None:
            new_val = rng.random() < interruptible_rate
            if nj.get("interruptible") != new_val:
                nj["interruptible"] = new_val
                n_jobs_modified += 1
            if new_val:
                n_jobs_marked_T += 1
        else:
            if "interruptible" not in nj:
                nj["interruptible"] = DEFAULT_INTERRUPTIBLE
                n_jobs_modified += 1
        new_jobs.append(nj)
    if n_jobs_modified:
        out["jobs"] = new_jobs
        if interruptible_rate is not None:
            changes.append(
                f"interruptible (rewrote ×{n_jobs_modified} jobs; "
                f"{n_jobs_marked_T} now True, rate~{n_jobs_marked_T/len(new_jobs):.0%})"
            )
        else:
            changes.append(f"interruptible (×{n_jobs_modified} jobs)")

    return out, changes


def _write_json(path: Path, data: dict) -> None:
    """Write *data* as pretty-printed JSON, two-space indentation."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def migrate(
    root:               Path,
    dry_run:            bool,
    interruptible_rate: float | None,
    base_seed:          int,
) -> int:
    """Walk *root* and migrate every scn_*.json found."""
    files = sorted(root.glob("scn_*/scn_*.json"))
    if not files:
        print(f"No scn_*.json files under {root}", file=sys.stderr)
        return 0

    modified = 0
    total_true = 0
    total_jobs = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        augmented, changes = augment_instance(
            data, path.stem, interruptible_rate, base_seed,
        )
        # Track interruptibility stats in the result (even when no change)
        if "jobs" in augmented:
            for j in augmented["jobs"]:
                total_jobs += 1
                if j.get("interruptible") is True:
                    total_true += 1
        if not changes:
            continue
        modified += 1
        if dry_run:
            print(f"[dry-run] {path.relative_to(root)} would add: {changes}")
        else:
            _write_json(path, augmented)
            print(f"updated  {path.relative_to(root)}  +{changes}")

    summary = f"\n{modified} / {len(files)} file(s) "
    summary += "would be " if dry_run else ""
    summary += "updated."
    if interruptible_rate is not None and total_jobs:
        summary += (
            f"  Realised interruptibility: {total_true}/{total_jobs} jobs "
            f"({100*total_true/total_jobs:.1f}% — target {100*interruptible_rate:.0f}%)."
        )
    print(summary)
    return modified


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "instances_202605",
        help="Root folder containing scn_*/scn_*.json "
             "(default: data/instances_202605).",
    )
    ap.add_argument(
        "--interruptible-rate",
        type=float,
        default=None,
        help="If supplied, every job's interruptible flag is REWRITTEN by a "
             "reproducible random draw at this probability "
             "(0.0 ≤ rate ≤ 1.0).  When absent (default), the migration is "
             "idempotent and only fills missing fields with safe defaults.",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_BASE_SEED,
        help=f"Base seed for the per-instance RNG used in annotation mode "
             f"(default: {DEFAULT_BASE_SEED}).  Only relevant with "
             f"--interruptible-rate.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which files would be modified without writing.",
    )
    args = ap.parse_args()

    if args.interruptible_rate is not None and not (
        0.0 <= args.interruptible_rate <= 1.0
    ):
        ap.error("--interruptible-rate must be in [0, 1].")

    migrate(args.root, args.dry_run, args.interruptible_rate, args.seed)


if __name__ == "__main__":
    main()
