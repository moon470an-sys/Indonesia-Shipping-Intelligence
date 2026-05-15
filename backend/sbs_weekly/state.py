"""SBS Weekly inbox state tracking — `.processed.json`.

Records every PDF that has been merged into `docs/data/market.json`,
keyed by sha256. The CLI uses this to avoid re-processing the same file
when the cron job fires multiple times in the same week.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from . import INBOX_DIR, STATE_FILE

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class ProcessedRecord:
    filename: str
    sha256: str
    size_bytes: int
    report_week: str
    build_run_id: str
    merged_at_kst: str
    merge_summary: dict[str, int]
    notes: str = ""


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "description": (
            "Tracks SBS Weekly PDFs already merged into docs/data/market.json. "
            "The /market-refresh-from-pdf skill (Phase 3) writes here after "
            "successful merge+commit. Do not edit by hand unless re-running a "
            "specific PDF."
        ),
        "processed": [],
    }


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return _empty_state()
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_processed(state: dict[str, Any], sha: str) -> bool:
    return any(r.get("sha256") == sha for r in state.get("processed", []))


def append_record(state: dict[str, Any], record: ProcessedRecord) -> None:
    state.setdefault("processed", []).append({
        "filename": record.filename,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "report_week": record.report_week,
        "build_run_id": record.build_run_id,
        "merged_at_kst": record.merged_at_kst,
        "merge_summary": record.merge_summary,
        "notes": record.notes,
    })


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat()


def list_inbox_pdfs() -> list[Path]:
    """All `.pdf` files in the inbox, sorted newest-mtime first."""
    if not INBOX_DIR.exists():
        return []
    return sorted(
        (p for p in INBOX_DIR.glob("*.pdf") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def pick_unprocessed(state: dict[str, Any]) -> Path | None:
    """Newest PDF whose sha256 isn't in `state.processed[]`."""
    for pdf in list_inbox_pdfs():
        if not is_processed(state, sha256_of(pdf)):
            return pdf
    return None
