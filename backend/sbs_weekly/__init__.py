"""SBS Weekly Marketing Report → market.json automation pipeline.

Modules:
    state    — `.processed.json` tracking (sha256 dedup)
    parser   — pdfplumber text extraction + PyMuPDF page rendering
    merger   — apply parsed delta to docs/data/market.json with freshness guards

CLI: `python -m backend.sbs_weekly --inbox` selects the newest unprocessed PDF
in `data/raw/sbs_weekly/`; `--pdf <path>` targets a specific file.
See `docs/sbs_weekly_inbox_setup.md` for the upstream Outlook → OneDrive flow
and `MARKET_REFRESH_PLAYBOOK.md` for source/tier rules.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INBOX_DIR = PROJECT_ROOT / "data" / "raw" / "sbs_weekly"
STATE_FILE = INBOX_DIR / ".processed.json"
MARKET_JSON = PROJECT_ROOT / "docs" / "data" / "market.json"
PNG_CACHE_PREFIX = ".png_cache_"  # appended with report-week date
