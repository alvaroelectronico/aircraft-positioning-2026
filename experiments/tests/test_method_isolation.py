"""test_method_isolation.py -- enforce the cross-method visibility rules.

For every ``methods/<X>/<paper>/`` subtree, scan each ``.py`` file (skipping
archive snapshots under ``iterations/``) and assert that it does not reach
into another method, into ``papers/``, or into ``literature_review/``.

We check two channels by which a Python file can pull such code in:

1.  Top-level ``import`` / ``from ... import`` statements.  Any dotted name
    starting with ``methods.<Y>.``, ``papers.``, or ``literature_review.``
    is a violation (where ``Y != X``).
2.  ``sys.path.insert(...)`` calls whose argument is a literal string or
    a path expression that embeds ``methods/<Y>/``, ``papers/``, or
    ``literature_review/``.  Because the current codebase uses flat
    (non-package) imports, the sys.path manipulation is where leakage
    would actually start.

Run from the repo root:
    py -3 experiments/tests/test_method_isolation.py

Exit status 0 means the contract holds, 1 means at least one violation.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_ROOT     = Path(__file__).resolve().parents[2]
_METHODS  = _ROOT / "methods"

# Methods that legitimately read another method's code, with the reason.
# Each entry is keyed by the relative-to-repo path of the file allowed
# to reach across.  The value is the cross-method prefix it may touch.
_ALLOWLIST: dict[str, str] = {
    # (empty — the only historical entry, autoresearch's baseline helper,
    # moved to retired_heuristics/ with the 2026-07 refocus.)
}

_FORBIDDEN_PKG_PREFIXES = ("papers", "literature_review")


def _iter_method_files() -> list[tuple[str, str, Path]]:
    """Yield (method_name, paper_name, file_path) for every .py to check."""
    out: list[tuple[str, str, Path]] = []
    for method_dir in sorted(p for p in _METHODS.iterdir() if p.is_dir()):
        method = method_dir.name
        for paper_dir in sorted(p for p in method_dir.iterdir() if p.is_dir()):
            paper = paper_dir.name
            for py in sorted(paper_dir.rglob("*.py")):
                # Skip archive snapshots -- they are immutable history.
                if "iterations" in py.parts:
                    continue
                out.append((method, paper, py))
    return out


def _module_violations(method: str, file_path: Path, source: str) -> list[str]:
    """Return human-readable violations from import statements."""
    violations: list[str] = []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        return [f"{file_path}: cannot parse ({exc})"]

    rel = file_path.relative_to(_ROOT).as_posix()
    allowed_prefix = _ALLOWLIST.get(rel)
    # Allowed prefix in dotted form, e.g. "methods.manual.jobs".
    allowed_dotted = allowed_prefix.replace("/", ".") if allowed_prefix else None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            continue

        for name in names:
            parts = name.split(".")
            # papers / literature_review -- always forbidden in methods/
            if parts[0] in _FORBIDDEN_PKG_PREFIXES:
                violations.append(
                    f"{rel}: imports '{name}' (forbidden top-level package "
                    f"'{parts[0]}')"
                )
                continue
            # methods.<Y>.<...> where Y != current method
            if parts[0] == "methods" and len(parts) >= 2 and parts[1] != method:
                # Allow only if file is allowlisted AND prefix matches.
                if allowed_dotted and name.startswith(allowed_dotted):
                    continue
                violations.append(
                    f"{rel}: imports '{name}' "
                    f"(cross-method into methods/{parts[1]}/)"
                )
    return violations


def _pathstring_violations(method: str, file_path: Path, source: str) -> list[str]:
    """Return violations from sys.path manipulations and embedded path strings.

    Because the methods today use flat (non-package) imports such as
    ``from milp_jobs_v2_solver import ...``, the way one method leaks
    another is by inserting the other method's folder onto sys.path.
    """
    violations: list[str] = []
    rel = file_path.relative_to(_ROOT).as_posix()
    allowed_prefix = _ALLOWLIST.get(rel)

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []  # already reported by _module_violations

    def _string_constants(call_node: ast.Call) -> list[str]:
        """Pull every string literal that appears anywhere in the call args."""
        out: list[str] = []
        for arg in call_node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append(sub.value)
        return out

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        # Match attribute call ending in .insert / .append / .extend on what
        # *might* be sys.path -- we only flag if the literal string clearly
        # references a forbidden path segment, so a false positive is rare.
        if node.func.attr not in {"insert", "append", "extend"}:
            continue
        for s in _string_constants(node):
            norm = s.replace("\\", "/")
            for bad in ("papers/", "literature_review/"):
                if bad in norm:
                    violations.append(
                        f"{rel}: sys.path-like call references '{bad}' in literal '{s}'"
                    )
            # Cross-method directory references.
            for other in (p.name for p in _METHODS.iterdir() if p.is_dir() and p.name != method):
                marker = f"methods/{other}/"
                if marker in norm:
                    if allowed_prefix and allowed_prefix in norm:
                        continue
                    violations.append(
                        f"{rel}: sys.path-like call references '{marker}' "
                        f"in literal '{s}' (cross-method)"
                    )

    return violations


def main() -> int:
    files = _iter_method_files()
    all_violations: list[str] = []
    for method, _paper, py in files:
        try:
            source = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source = py.read_text(encoding="utf-8", errors="replace")
        all_violations.extend(_module_violations(method, py, source))
        all_violations.extend(_pathstring_violations(method, py, source))

    n_files = len(files)
    print(f"Scanned {n_files} .py files under methods/ "
          f"(excluding iterations/ archive snapshots).")
    if _ALLOWLIST:
        print("Allowlisted cross-method readers:")
        for path_, target in _ALLOWLIST.items():
            print(f"  {path_}  ->  {target}/")

    if all_violations:
        print(f"\n{len(all_violations)} ISOLATION VIOLATION(S):")
        for v in all_violations:
            print(f"  - {v}")
        return 1
    print("\nNo isolation violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
