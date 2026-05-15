"""SBS Weekly PDF text extraction + page rendering.

Layout assumptions (verified against W19/W20 PDFs):
    p1 — International freight + start of Domestic. Numbers are images.
    p2 — CPO / SPOB / Oil Tanker / LCT pricing matrices. Numbers are images.
    p3 — News (5 items). Pure selectable text.
    p4 — Monthly Events. Selectable text.
    p5 — Upcoming Events. Selectable text + tabular layout.

This module only extracts what's reliably text-extractable. Image-trapped
numerics (BDI/BCI table, vessel pricing) are left for the Phase 3 skill
to OCR via Claude vision against the PNG renders we emit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from . import PNG_CACHE_PREFIX

# ---------- regex constants ----------

# News section heading on p3.
# Examples: "SHIPPING NEWS", "COMMODITY NEWS: COAL", "POWER PLANT NEWS"
_NEWS_HEADING_RE = re.compile(
    r"^(SHIPPING NEWS|POWER PLANT NEWS|COMMODITY NEWS:\s*[A-Z]+)\s*$",
    re.MULTILINE,
)

# Source line at end of each news item.
# Example: "Source: Kontan Insight May 8th, 2026"
_SOURCE_LINE_RE = re.compile(
    r"Source:\s*(?P<name>[^\n]+?)\s+"
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s*(?P<year>\d{4})",
)

# Page header like "1st Week of April/ 6th May 2026" or "2nd Week of April/ 13th May 2026"
_HEADER_RE = re.compile(
    r"(?P<weekno>\d+)(?:st|nd|rd|th)\s+Week\s+of\s+\w+\s*/\s*"
    r"(?P<day>\d+)(?:st|nd|rd|th)\s+"
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"(?P<year>\d{4})",
)

_MONTH_NUM = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

_NEWS_HEADING_TO_CATEGORY = {
    "SHIPPING NEWS":      ("shipping", "Shipping"),
    "POWER PLANT NEWS":   ("power",    "Policy"),
    "COMMODITY NEWS: COAL":   ("coal",   "Policy"),
    "COMMODITY NEWS: NICKEL": ("nickel", "Commodity"),
    "COMMODITY NEWS: CPO":    ("cpo",    "Commodity"),
}


# ---------- result dataclasses ----------

@dataclass(frozen=True)
class NewsItem:
    """One news entry extracted from p3."""
    heading: str                  # raw "COMMODITY NEWS: COAL"
    category: str                 # commodity_news bucket: coal/nickel/cpo/power/shipping
    overview_category: str        # for overview cards: Shipping/Policy/Commodity
    body_en: str                  # full English paragraph
    source_name: str              # "Kontan Insight"
    published_date: str           # ISO "2026-05-08"


@dataclass(frozen=True)
class ParsedPdf:
    pdf_path: Path
    report_header: str            # "2nd Week of April/ 13th May 2026"
    report_date: str              # ISO date of header (e.g., "2026-05-13")
    iso_week: int                 # ISO week number of report_date
    news: list[NewsItem]
    events_p4_text: str
    events_p5_text: str
    page_image_paths: dict[str, Path] = field(default_factory=dict)  # "p1"/"p2" → PNG path


# ---------- public API ----------

def parse(pdf_path: Path, *, render_images: bool = True) -> ParsedPdf:
    """Extract structured content from a SBS Weekly PDF."""
    pdf_path = Path(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) < 5:
            raise ValueError(f"expected ≥5 pages, got {len(pdf.pages)}")
        header = _extract_header(pdf.pages[0].extract_text() or "")
        report_date_iso, iso_week = _header_to_date(header)
        news = _extract_news(pdf.pages[2].extract_text() or "")
        p4_text = pdf.pages[3].extract_text() or ""
        p5_text = pdf.pages[4].extract_text() or ""

    page_images: dict[str, Path] = {}
    if render_images:
        page_images = _render_pricing_pages(pdf_path, report_date_iso)

    return ParsedPdf(
        pdf_path=pdf_path,
        report_header=header,
        report_date=report_date_iso,
        iso_week=iso_week,
        news=news,
        events_p4_text=p4_text,
        events_p5_text=p5_text,
        page_image_paths=page_images,
    )


# ---------- internal extractors ----------

def _extract_header(p1_text: str) -> str:
    """Return the first matching header line on p1, or '' if not found."""
    for line in p1_text.splitlines():
        line = line.strip()
        if _HEADER_RE.search(line):
            return line
    return ""


def _header_to_date(header: str) -> tuple[str, int]:
    """Parse 'Nth Week of <Month>/ Dth <Month> YYYY' → (ISO date, ISO week).

    SBS headers list TWO months — the first is the data-week label, the
    second is the publication date. We use the publication date.
    """
    m = _HEADER_RE.search(header)
    if not m:
        return "", 0
    d = int(m["day"])
    month = _MONTH_NUM[m["month"][:3].title()]
    y = int(m["year"])
    iso = f"{y:04d}-{month:02d}-{d:02d}"
    week = date(y, month, d).isocalendar().week
    return iso, week


def _extract_news(p3_text: str) -> list[NewsItem]:
    """Split p3 into news items by heading and source-line boundaries."""
    text = p3_text.replace("\r", "")
    # Find all heading match positions
    headings: list[tuple[int, str]] = []
    for m in _NEWS_HEADING_RE.finditer(text):
        headings.append((m.start(), m.group(1).strip()))
    if not headings:
        return []

    items: list[NewsItem] = []
    for idx, (start, heading) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(text)
        block = text[start:end]
        body_lines = block.splitlines()[1:]  # drop the heading line
        block_body = "\n".join(body_lines).strip()

        # Extract Source: line
        sm = _SOURCE_LINE_RE.search(block_body)
        if not sm:
            # SBS occasionally splits "Source:" across a line wrap; skip
            # silently here — Phase 3 vision can handle these edge cases.
            continue
        body_en = block_body[:sm.start()].strip()
        source_name = sm["name"].strip().rstrip(",.")
        month = _MONTH_NUM[sm["month"][:3].title()]
        published_iso = f"{int(sm['year']):04d}-{month:02d}-{int(sm['day']):02d}"

        cat, ovcat = _NEWS_HEADING_TO_CATEGORY.get(
            heading,
            (heading.lower().replace(" ", "_"), "Commodity"),
        )
        items.append(NewsItem(
            heading=heading,
            category=cat,
            overview_category=ovcat,
            body_en=body_en,
            source_name=source_name,
            published_date=published_iso,
        ))
    return items


def _render_pricing_pages(pdf_path: Path, report_date_iso: str) -> dict[str, Path]:
    """Render p1 and p2 to PNG so the Phase 3 skill can OCR via Claude vision.

    Resolution: 2.5x scale ≈ 180 DPI — readable for vision but not bloated.
    """
    out_dir = pdf_path.parent / f"{PNG_CACHE_PREFIX}{report_date_iso or 'unknown'}"
    out_dir.mkdir(parents=True, exist_ok=True)
    mat = fitz.Matrix(2.5, 2.5)
    out: dict[str, Path] = {}
    with fitz.open(pdf_path) as doc:
        for i in (0, 1):
            png = out_dir / f"p{i+1}.png"
            doc[i].get_pixmap(matrix=mat).save(png)
            out[f"p{i+1}"] = png
    return out
