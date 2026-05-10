"""Blacklist lint per INSTRUCTIONS.md section 7.3.

Fails (exit 1) if any of the value-judgment terms appear in the
user-facing surface. Scope:

    docs/index.html
    docs/derived/*.json
    docs/derived/*.html
    data/*.md
    i18n/*.json   (if present)

INSTRUCTIONS.md is excluded — it defines the rules and necessarily
quotes the banned terms.

Run from the repo root:
    python scripts/lint_language.py
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

# Console on Windows defaults to cp949 — force UTF-8 for our em-dashes etc.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

# Blacklist per INSTRUCTIONS.md section 7.3. Match is case-insensitive
# for ASCII; Korean terms are matched as exact substrings.
BLACKLIST: tuple[str, ...] = (
    "Sweet Spot",
    "Watchlist",
    "투자 테제",
    "Investment Thesis",
    "Hot Sector",
    "Top Pick",
    "유망",
    "매력적",
    "기회",
    "추천",
    "주목할 만한",
    "놓치지 말아야",
    "공급 부족",
    "수요 충격",
    "주의 요망",
    "Risk Alert",
    "Investor Signal",
)

# File globs to scan. Each pattern is repo-rooted.
SCAN_GLOBS: tuple[str, ...] = (
    "docs/index.html",
    "docs/derived/*.json",
    "docs/derived/*.html",
    "data/*.md",
    "i18n/*.json",
)

# Files we deliberately exclude from the blacklist scan because they
# define / quote the banned terms by design.
EXCLUDE_NAMES: frozenset[str] = frozenset({
    "INSTRUCTIONS.md",
})


def _iter_files() -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for pat in SCAN_GLOBS:
        for p in ROOT.glob(pat):
            if not p.is_file():
                continue
            if p.name in EXCLUDE_NAMES:
                continue
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
    return sorted(out)


def _scan_file(p: Path) -> list[tuple[str, int, str]]:
    """Return [(banned_term, lineno, line_excerpt), ...]."""
    hits: list[tuple[str, int, str]] = []
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits
    lines = text.splitlines()
    for term in BLACKLIST:
        # ASCII terms get case-insensitive matching; Korean terms are
        # matched verbatim (re.IGNORECASE is a no-op for non-ASCII).
        pat = re.compile(re.escape(term), re.IGNORECASE)
        for i, line in enumerate(lines, start=1):
            if pat.search(line):
                excerpt = line.strip()
                if len(excerpt) > 120:
                    excerpt = excerpt[:117] + "…"
                hits.append((term, i, excerpt))
    return hits


def main() -> int:
    files = _iter_files()
    print(f"Lint scope: {len(files)} files")
    for p in files:
        print(f"  {p.relative_to(ROOT)}")

    total_hits = 0
    for p in files:
        hits = _scan_file(p)
        if not hits:
            continue
        total_hits += len(hits)
        rel = p.relative_to(ROOT)
        print(f"\n❌ {rel}")
        for term, lineno, excerpt in hits:
            print(f"    L{lineno}: «{term}» — {excerpt}")

    print()
    if total_hits == 0:
        print(f"✅ Lint passed: 0 banned terms across {len(files)} files.")
        return 0
    print(f"❌ Lint failed: {total_hits} hits across files. "
          f"Replace value-judgment language with fact statements per INSTRUCTIONS.md §1.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
