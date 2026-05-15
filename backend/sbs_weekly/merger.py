"""Apply a `ParsedPdf` delta to `docs/data/market.json`.

Honest-minimum merge policy (per Phase 1 (B) decision, 2026-05-16):

    meta              — always overwrite (report_week, reference_pdf, ...)
    overview          — append cards from PDF news (skip if duplicate headline)
    commodity_news    — append per-category (skip if duplicate title)
    events            — append upcoming events from p5 (skip if duplicate name)
    international_freight.indices  — only replace when PDF as_of > existing
    domestic_vessel_pricing        — Phase 3 OCR territory, no-op here
    domestic_fuel_scrap            — Phase 3 OCR territory, no-op here

All PDF-sourced rows carry: source_tier="broker", source_url=null,
status="indicative", source_name="SBS Weekly Marketing Report YYYY.MM.DD".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import MARKET_JSON
from .parser import NewsItem, ParsedPdf

# ISO weekday names so we don't depend on locale
_ENG_MONTH_KO = {
    1: "1월", 2: "2월", 3: "3월", 4: "4월", 5: "5월", 6: "6월",
    7: "7월", 8: "8월", 9: "9월", 10: "10월", 11: "11월", 12: "12월",
}


@dataclass
class MergeResult:
    overview_added: int = 0
    news_added: dict[str, int] = field(default_factory=dict)
    events_added: int = 0
    indices_replaced: int = 0
    meta_updated: bool = False
    skipped: list[str] = field(default_factory=list)

    def total_news(self) -> int:
        return sum(self.news_added.values())

    def to_summary(self) -> dict[str, int]:
        return {
            "overview_added": self.overview_added,
            "news_added": self.total_news(),
            "events_added": self.events_added,
            "indices_replaced": self.indices_replaced,
            "vessel_pricing_changed": 0,  # Phase 3
        }


# ---------- public API ----------

def merge(parsed: ParsedPdf, *, dry_run: bool = False,
          market_path: Path = MARKET_JSON) -> tuple[dict[str, Any], MergeResult]:
    """Return (new_market_dict, MergeResult). Writes to disk only if not dry_run."""
    market = json.loads(market_path.read_text(encoding="utf-8"))
    result = MergeResult()

    sbs_src = _sbs_source_name(parsed.pdf_path.name)

    _merge_meta(market, parsed, result)
    _merge_overview(market, parsed, sbs_src, result)
    _merge_news(market, parsed, sbs_src, result)
    # events.upcoming additions need PDF p5 layout parsing — defer to vision.
    # When the Phase 3 skill produces structured event candidates from the
    # PNG render, it should call _merge_events directly with that list.

    if not dry_run:
        market_path.write_text(
            json.dumps(market, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return market, result


def merge_events(market: dict[str, Any], events: list[dict[str, Any]],
                 sbs_src: str, *, write_to: Path | None = None) -> int:
    """Append new events to market['events']['upcoming'], dedup by name.

    Returns count of newly added events. `events` items must already follow
    the upcoming-event schema (name/date/location/category/note). This is a
    separate entry point because event extraction needs vision (multi-column
    p5 layout doesn't roundtrip through pdfplumber cleanly).
    """
    upcoming = market.setdefault("events", {}).setdefault("upcoming", [])
    existing_names = {e.get("name", "").strip().lower() for e in upcoming}
    added = 0
    for ev in events:
        name = ev.get("name", "").strip()
        if not name or name.lower() in existing_names:
            continue
        ev.setdefault("source_name", f"{sbs_src} (PDF p.5)")
        ev.setdefault("source_url", None)
        ev.setdefault("status", "indicative")
        upcoming.append(ev)
        existing_names.add(name.lower())
        added += 1
    if write_to is not None and added > 0:
        write_to.write_text(
            json.dumps(market, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return added


# ---------- internal mergers ----------

def _sbs_source_name(filename: str) -> str:
    """'[SBS] Weekly Marketing Report 2026.05.15.pdf' → 'SBS Weekly Marketing Report 2026.05.15'"""
    stem = Path(filename).stem
    return stem.replace("[SBS] ", "")


def _next_monday(iso_date: str) -> str:
    y, m, d = (int(x) for x in iso_date.split("-"))
    return (date(y, m, d) + timedelta(days=7)).isoformat()


def _report_week_label(report_date_iso: str) -> str:
    """ISO date → '3rd Week of May 2026 (May 14 ~ May 20)'.

    'Nth Week of <Month>' is week-of-month based on first Monday convention.
    """
    y, m, d = (int(x) for x in report_date_iso.split("-"))
    rd = date(y, m, d)
    first = date(y, m, 1)
    # week number within month (1-indexed); week starts Monday
    week_no = ((rd - first).days + first.weekday()) // 7 + 1
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(
        week_no if week_no < 20 else week_no % 10, "th")
    # Display week range: Mon..Sun containing rd
    monday = rd - timedelta(days=rd.weekday())
    sunday = monday + timedelta(days=6)
    eng_month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1]
    return (f"{week_no}{suffix} Week of {eng_month} {y} "
            f"({eng_month} {monday.day} ~ {eng_month} {sunday.day})")


def _merge_meta(market: dict[str, Any], parsed: ParsedPdf,
                result: MergeResult) -> None:
    market["report_week"] = _report_week_label(parsed.report_date)
    today_iso = date.today().isoformat()
    market["checked_date"] = today_iso
    market["last_updated"] = today_iso
    market["next_scheduled"] = _next_monday(today_iso)
    market["build_run_id"] = f"sbs-pdf-w{parsed.iso_week}-auto"
    market["reference_pdf"] = parsed.pdf_path.name
    result.meta_updated = True


def _merge_overview(market: dict[str, Any], parsed: ParsedPdf,
                    sbs_src: str, result: MergeResult) -> None:
    overview = market.setdefault("overview", [])
    existing_heads = {c.get("headline", "").strip().lower() for c in overview}

    # Build candidate cards from news. We surface ALL 5 news items as overview
    # cards — the Market 탭 UI already paginates, and surfacing fewer means
    # users have to dig into commodity_news for the same info.
    cards: list[dict[str, Any]] = []
    for n in parsed.news:
        head = _english_to_korean_headline(n)
        if head.strip().lower() in existing_heads:
            result.skipped.append(f"overview: dup '{head[:40]}…'")
            continue
        cards.append({
            "headline": head,
            "detail_ko": _english_body_to_korean_summary(n, parsed),
            "source_name": f"{sbs_src} ({n.source_name} 인용)",
            "source_tier": "broker",
            "source_url": None,
            "as_of": n.published_date,
            "category": n.overview_category,
        })
        existing_heads.add(head.strip().lower())

    if cards:
        market["overview"] = cards + overview
        result.overview_added = len(cards)


def _merge_news(market: dict[str, Any], parsed: ParsedPdf,
                sbs_src: str, result: MergeResult) -> None:
    cnews = market.setdefault("commodity_news", {})
    for n in parsed.news:
        bucket = cnews.setdefault(n.category, [])
        # Dedup against existing titles (loose: Korean-translated title match)
        ko_title = _english_to_korean_headline(n)
        existing_titles = {e.get("title", "").strip().lower() for e in bucket}
        if ko_title.strip().lower() in existing_titles:
            result.skipped.append(f"news[{n.category}]: dup '{ko_title[:40]}…'")
            continue
        bucket.insert(0, {
            "title": ko_title,
            "summary_ko": _english_body_to_korean_summary(n, parsed),
            "source_name": f"{sbs_src} ({n.source_name} {_short_date(n.published_date)} 인용)",
            "source_tier": "broker",
            "source_url": None,
            "published_date": n.published_date,
            "status": "indicative",
        })
        result.news_added[n.category] = result.news_added.get(n.category, 0) + 1


# ---------- placeholder Korean adapters ----------
#
# In Phase 2 we surface the English body verbatim with a "[자동 인입]" prefix.
# Phase 3 (the /market-refresh-from-pdf skill, run inside Claude) will re-run
# this merge with proper Korean summaries written by the model. Keeping the
# stub here means the parser/merger can be unit-tested without an LLM call.

def _english_to_korean_headline(n: NewsItem) -> str:
    """Stub headline generator — Phase 3 skill replaces this."""
    cat_label = {
        "shipping": "Shipping",
        "coal": "석탄",
        "nickel": "니켈",
        "cpo": "CPO",
        "power": "Power",
    }.get(n.category, n.category.title())
    first_sentence = n.body_en.split(".")[0].strip()
    if len(first_sentence) > 100:
        first_sentence = first_sentence[:97] + "…"
    return f"[자동 인입] {cat_label} — {first_sentence}"


def _english_body_to_korean_summary(n: NewsItem, parsed: ParsedPdf) -> str:
    """Stub summary — Phase 3 skill replaces this with a proper KO translation."""
    return (
        f"[자동 인입 — Phase 2 stub, KO 요약 미완성]\n\n"
        f"{n.body_en}\n\n"
        f"출처: {n.source_name} {_short_date(n.published_date)} (via {parsed.pdf_path.name} p.3)"
    )


def _short_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{_ENG_MONTH_KO[m]} {d}일"
