"""CLI entrypoint for the SBS Weekly auto-ingest pipeline.

Examples:

    # Dry-run on the newest unprocessed PDF in data/raw/sbs_weekly/
    python -m backend.sbs_weekly --inbox --dry-run

    # Merge a specific file and write market.json
    python -m backend.sbs_weekly --pdf "data/raw/sbs_weekly/[SBS] Weekly Marketing Report 2026.05.15.pdf"

    # Inbox + commit (state file updated, market.json written, no git)
    python -m backend.sbs_weekly --inbox

The Phase 3 skill `/market-refresh-from-pdf` shells out to this module,
inspects the dry-run delta, fills proper Korean summaries via Claude, then
re-runs without --dry-run and follows up with the git commit + push.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python -m backend.sbs_weekly` from the repo root.
_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.sbs_weekly import state as st
from backend.sbs_weekly.merger import merge
from backend.sbs_weekly.parser import parse


def _resolve_pdf(args: argparse.Namespace) -> Path | None:
    if args.pdf:
        return Path(args.pdf)
    if args.inbox:
        s = st.load_state()
        return st.pick_unprocessed(s)
    return None


def _print_delta(parsed, result) -> None:
    print(f"PDF       : {parsed.pdf_path.name}")
    print(f"Header    : {parsed.report_header}")
    print(f"Date      : {parsed.report_date}  (ISO week W{parsed.iso_week})")
    print(f"News      : {len(parsed.news)} items")
    for n in parsed.news:
        print(f"  · [{n.category:8s}] {n.published_date} {n.source_name}")
    print(f"Overview added : {result.overview_added}")
    print(f"News added     : {result.total_news()}  ({result.news_added})")
    print(f"Indices replaced: {result.indices_replaced}")
    print(f"Meta updated   : {result.meta_updated}")
    if result.skipped:
        print(f"Skipped ({len(result.skipped)}):")
        for s in result.skipped[:10]:
            print(f"  - {s}")
        if len(result.skipped) > 10:
            print(f"  ... +{len(result.skipped) - 10} more")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m backend.sbs_weekly",
        description="Merge SBS Weekly PDF into docs/data/market.json.",
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="Path to a specific SBS Weekly PDF.")
    src.add_argument("--inbox", action="store_true",
                     help="Pick newest unprocessed PDF from data/raw/sbs_weekly/.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and report the delta without touching market.json.")
    ap.add_argument("--no-render", action="store_true",
                    help="Skip PNG rendering of p1/p2 (faster, no vision input).")
    ap.add_argument("--force", action="store_true",
                    help="Re-process even if sha256 already in .processed.json.")
    args = ap.parse_args()

    pdf = _resolve_pdf(args)
    if pdf is None:
        print("No unprocessed PDF found in inbox.", file=sys.stderr)
        return 0
    if not pdf.exists():
        print(f"PDF not found: {pdf}", file=sys.stderr)
        return 2

    state = st.load_state()
    sha = st.sha256_of(pdf)
    if st.is_processed(state, sha) and not args.force:
        print(f"Already processed (sha256 {sha[:12]}…) — use --force to re-run.")
        return 0

    parsed = parse(pdf, render_images=not args.no_render)
    new_market, result = merge(parsed, dry_run=args.dry_run)

    _print_delta(parsed, result)

    if args.dry_run:
        print("(dry-run — market.json untouched)")
        return 0

    # Persist state file (only on real merge).
    record = st.ProcessedRecord(
        filename=pdf.name,
        sha256=sha,
        size_bytes=pdf.stat().st_size,
        report_week=new_market.get("report_week", ""),
        build_run_id=new_market.get("build_run_id", ""),
        merged_at_kst=st.now_kst_iso(),
        merge_summary=result.to_summary(),
        notes="auto via backend.sbs_weekly CLI",
    )
    st.append_record(state, record)
    st.save_state(state)
    print(f"State updated: {st.STATE_FILE.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
