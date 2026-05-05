"""Vessel registry scraper (kapal.dephub.go.id)."""
from __future__ import annotations

import hashlib
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.config import (
    FLEET_WORKERS, KAPAL_HEADERS, KAPAL_URL, PAGE_SIZE, RAW_DIR,
    SEARCH_CODES, build_logger, current_snapshot_month,
)
from backend.db.database import session_scope, engine
from backend.db.models import VesselSnapshot
from backend.scrapers.http_client import post

log = build_logger("kapal")


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _vessel_key(rec: dict) -> str:
    cs = (rec.get("CallSign") or "").strip()
    if cs:
        return f"CS:{cs.upper()}"
    nk = (rec.get("NamaKapal") or "").strip().upper()
    th = (rec.get("Tahun") or "").strip()
    return f"NM:{nk}|{th}"


def _hash_record(rec: dict) -> str:
    keys = [
        "NamaKapal", "EksNamaKapal", "CallSign", "JenisKapal", "NamaPemilik",
        "Tpk", "Panjang", "Lebar", "Dalam", "LengthOfAll", "GT",
        "IsiBersih", "Imo", "Tahun",
    ]
    norm = {k: (str(rec.get(k)).strip() if rec.get(k) is not None else "") for k in keys}
    j = json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(j.encode("utf-8")).hexdigest()


def _fetch_page(code: str, offset: int) -> dict | None:
    payload = {
        "nama_kapal": "",
        "no_tanda_pendaftaran": code,
        "start": str(offset),
        "length": str(PAGE_SIZE),
    }
    resp = post(KAPAL_URL, KAPAL_HEADERS, payload, target=f"kapal/{code}@{offset}")
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception as exc:
        log.warning("JSON decode failed for %s@%d: %s", code, offset, exc)
        return None


def _persist_records(records: list[dict], code: str, snapshot_month: str) -> int:
    if not records:
        return 0
    rows = []
    now = datetime.utcnow()
    for r in records:
        rows.append(dict(
            snapshot_month=snapshot_month,
            vessel_key=_vessel_key(r),
            search_code=code,
            nama_kapal=r.get("NamaKapal"),
            eks_nama_kapal=r.get("EksNamaKapal"),
            call_sign=r.get("CallSign"),
            jenis_kapal=r.get("JenisKapal"),
            nama_pemilik=r.get("NamaPemilik"),
            tpk=r.get("Tpk"),
            panjang=_to_float(r.get("Panjang")),
            lebar=_to_float(r.get("Lebar")),
            dalam=_to_float(r.get("Dalam")),
            length_of_all=_to_float(r.get("LengthOfAll")),
            gt=_to_float(r.get("GT")),
            isi_bersih=_to_float(r.get("IsiBersih")),
            imo=r.get("Imo"),
            tahun=r.get("Tahun"),
            raw_data=json.dumps(r, ensure_ascii=False),
            content_hash=_hash_record(r),
            scraped_at=now,
        ))

    # Deduplicate within this batch by (snapshot_month, vessel_key) — keep last
    by_key: dict[tuple, dict] = {}
    for row in rows:
        by_key[(row["snapshot_month"], row["vessel_key"])] = row
    rows = list(by_key.values())

    inserted = 0
    with engine.begin() as conn:
        stmt = sqlite_insert(VesselSnapshot.__table__).values(rows)
        update_cols = {c.name: stmt.excluded[c.name] for c in VesselSnapshot.__table__.columns
                       if c.name not in ("id", "snapshot_month", "vessel_key")}
        stmt = stmt.on_conflict_do_update(
            index_elements=["snapshot_month", "vessel_key"],
            set_=update_cols,
        )
        result = conn.execute(stmt)
        inserted = result.rowcount or len(rows)
    return inserted


def scrape_code(code: str, snapshot_month: str | None = None,
                save_raw: bool = True) -> tuple[int, int, str | None]:
    """Scrape all pages for one search code. Returns (records, pages, error_message)."""
    snapshot_month = snapshot_month or current_snapshot_month()
    raw_dir = RAW_DIR / snapshot_month / "fleet"
    raw_dir.mkdir(parents=True, exist_ok=True)
    offset = 0
    total = 0
    pages = 0
    all_records: list[dict] = []
    last_err: str | None = None
    while True:
        time.sleep(random.uniform(0.3, 0.8))
        page = _fetch_page(code, offset)
        if page is None:
            last_err = f"page fetch failed at offset {offset}"
            break
        recs = page.get("data") or []
        records_filtered = page.get("recordsFiltered")
        if not recs:
            break
        try:
            n = _persist_records(recs, code, snapshot_month)
            total += n
            all_records.extend(recs)
        except Exception as exc:
            last_err = f"persist error: {exc}"
            log.exception("persist failed for %s@%d", code, offset)
            break
        pages += 1
        offset += PAGE_SIZE
        if records_filtered is not None:
            try:
                if offset >= int(records_filtered):
                    break
            except (TypeError, ValueError):
                pass
        if len(recs) < PAGE_SIZE:
            break
        # gentle pacing between pages
        time.sleep(random.uniform(0.3, 0.8))

    if save_raw and all_records:
        try:
            (raw_dir / f"{code}.json").write_text(
                json.dumps(all_records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("save_raw failed for %s: %s", code, exc)

    return total, pages, last_err


def scrape_all(snapshot_month: str | None = None,
               codes: list[str] | None = None,
               max_workers: int = FLEET_WORKERS) -> dict:
    snapshot_month = snapshot_month or current_snapshot_month()
    codes = codes or SEARCH_CODES
    log.info("Scraping %d codes with %d workers (snapshot=%s)",
             len(codes), max_workers, snapshot_month)
    results: dict[str, dict] = {}
    failed: list[str] = []
    succeeded: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut2code = {}
        for i, code in enumerate(codes):
            # stagger task submission to avoid simultaneous initial requests
            time.sleep(random.uniform(0.05, 0.2))
            fut2code[ex.submit(scrape_code, code, snapshot_month)] = code
        for fut in as_completed(fut2code):
            code = fut2code[fut]
            try:
                total, pages, err = fut.result()
                results[code] = {"records": total, "pages": pages, "error": err}
                if err:
                    failed.append(code)
                else:
                    succeeded.append(code)
                log.info("[%s] records=%d pages=%d err=%s", code, total, pages, err)
            except Exception as exc:
                results[code] = {"records": 0, "pages": 0, "error": str(exc)}
                failed.append(code)
                log.exception("Worker failed for %s", code)
    summary = {
        "snapshot_month": snapshot_month,
        "total_codes": len(codes),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "failed_codes": failed,
        "total_records": sum(r["records"] for r in results.values()),
        "details": results,
    }
    log.info("Fleet scrape done: %s", {k: v for k, v in summary.items() if k != "details"})
    return summary
