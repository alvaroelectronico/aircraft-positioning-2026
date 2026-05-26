"""Merge an "extra" run-experiments log into a main log, then delete the
extra.  Both logs share the same config header (must have identical
experiment list); only the SUMMARY data rows from the extra log are
appended to the main log, and the SUMMARY counter line is updated.

Usage:
    python scripts/merge_logs.py <main_log> <extra_log>

After the merge:
  - main_log absorbs every data row that appears in extra_log.
  - The SUMMARY counter (ok / failed / total) is recomputed.
  - extra_log is deleted.

If a data row already exists in the main log (same instance + experiment),
the extra row replaces it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUMMARY_LINE_RE = re.compile(
    r"^\s*SUMMARY\s+\S\s+(?P<ok>\d+)\s+ok\s+/\s+(?P<fail>\d+)\s+failed\s+/\s+(?P<tot>\d+)\s+total\s*$"
)


def _split_summary(lines: list[str]) -> tuple[int, int, int, int]:
    """Return (i_summary, i_data_start, i_failed_or_end, i_after_failed).

      lines[i_summary]            = the "SUMMARY — X ok / Y failed / Z total" line
      lines[i_data_start:i_failed_or_end] = data rows (each starts with "  scn_")
      lines[i_failed_or_end:i_after_failed] = optional "Failed runs:" block, if present
    """
    i_summary = next(i for i, l in enumerate(lines) if SUMMARY_LINE_RE.match(l))
    # Skip closing "===" of summary section, header row, dashes row.
    i_data_start = i_summary + 4
    # Data rows go until we hit "" (blank), "  Failed runs:", or "===".
    i = i_data_start
    while i < len(lines):
        s = lines[i]
        if s.startswith("  scn_"):
            i += 1
            continue
        break
    i_failed_or_end = i
    return i_summary, i_data_start, i_failed_or_end


def _row_key(line: str) -> tuple[str, str]:
    toks = line.split()
    if len(toks) < 2:
        return ("", "")
    return (toks[0], toks[1])


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <main_log> <extra_log>")
    main_path = Path(sys.argv[1])
    extra_path = Path(sys.argv[2])
    assert main_path.exists(), f"missing: {main_path}"
    assert extra_path.exists(), f"missing: {extra_path}"

    main_lines = main_path.read_text(encoding="utf-8").splitlines(keepends=False)
    extra_lines = extra_path.read_text(encoding="utf-8").splitlines(keepends=False)

    m_summary_i, m_data_start, m_data_end = _split_summary(main_lines)
    e_summary_i, e_data_start, e_data_end = _split_summary(extra_lines)

    main_data = main_lines[m_data_start:m_data_end]
    extra_data = extra_lines[e_data_start:e_data_end]

    # Replace or append: index by (instance, experiment).
    keyed = {_row_key(line): line for line in main_data}
    for line in extra_data:
        keyed[_row_key(line)] = line
    merged_data = list(keyed.values())

    # The original "Failed runs:" block (if any) sits between m_data_end and
    # the closing "===" line.  Preserve it as-is — extra logs typically have
    # no failed runs of their own, but we keep both blocks just in case.
    main_failed_block: list[str] = []
    i = m_data_end
    while i < len(main_lines):
        l = main_lines[i]
        if l.startswith("==="):
            break
        main_failed_block.append(l)
        i += 1
    main_closing = main_lines[i:]   # the "===" closer and anything after

    extra_failed_block: list[str] = []
    j = e_data_end
    while j < len(extra_lines):
        l = extra_lines[j]
        if l.startswith("==="):
            break
        extra_failed_block.append(l)
        j += 1

    # Merge "Failed runs:" sections (concatenate, dedup keys "instance · experiment").
    def _extract_failed_lines(block: list[str]) -> list[str]:
        out = []
        in_block = False
        for l in block:
            if l.lstrip().startswith("Failed runs:"):
                in_block = True
                continue
            if in_block and l.strip().startswith("x "):
                out.append(l)
        return out

    failed_lines = _extract_failed_lines(main_failed_block) + _extract_failed_lines(extra_failed_block)
    # Dedup
    seen: set[str] = set()
    dedup_failed: list[str] = []
    for l in failed_lines:
        if l not in seen:
            seen.add(l)
            dedup_failed.append(l)

    # Recompute counters.
    n_ok = len(merged_data)
    n_failed = len(dedup_failed)
    n_total = n_ok + n_failed
    new_summary_line = f"  SUMMARY  —  {n_ok} ok  /  {n_failed} failed  /  {n_total} total"

    # Reassemble.
    out: list[str] = []
    out.extend(main_lines[:m_summary_i])
    out.append(new_summary_line)
    # Keep the original header rows (closing ===, header, dashes).
    out.extend(main_lines[m_summary_i + 1:m_data_start])
    out.extend(merged_data)
    if dedup_failed:
        out.append("")
        out.append("  Failed runs:")
        out.extend(dedup_failed)
    out.extend(main_closing)

    main_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    extra_path.unlink()
    print(f"Merged {len(extra_data)} extra rows into {main_path.name}")
    print(f"New counters: {n_ok} ok / {n_failed} failed / {n_total} total")
    print(f"Deleted {extra_path}")


if __name__ == "__main__":
    main()
