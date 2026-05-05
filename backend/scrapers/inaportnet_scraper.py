"""Cargo (LK3) scraper for inaportnet.dephub.go.id."""
from __future__ import annotations

import hashlib
import io
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.config import (
    CARGO_KINDS, CARGO_LOOKBACK_MONTHS, CARGO_WORKERS,
    INAPORT_HEADERS, INAPORT_LIST_URL, INAPORT_LK3_URL,
    RAW_DIR, SAVE_RAW_CARGO, build_logger, current_snapshot_month, now_kst,
)
from backend.db.database import engine, session_scope
from backend.db.models import CargoSnapshot, Port
from backend.scrapers.http_client import get

log = build_logger("inaport")


def _hash_row(row: dict) -> str:
    j = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(j.encode("utf-8")).hexdigest()


def _previous_months(n: int) -> list[tuple[int, int]]:
    """Return last n months including the current calendar month, oldest first."""
    today = now_kst()
    y, m = today.year, today.month
    out = []
    for i in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    out.reverse()
    return out


def list_ports(year: int, month: int) -> list[dict]:
    url = INAPORT_LIST_URL.format(year=year, month=month)
    resp = get(url, INAPORT_HEADERS, target=f"list/{year}/{month:02d}")
    if resp is None:
        return []
    try:
        body = resp.json()
    except Exception as exc:
        log.warning("list ports JSON decode failed %s/%02d: %s", year, month, exc)
        return []
    return body.get("data", []) or []


def upsert_ports(ports: list[dict]) -> int:
    if not ports:
        return 0
    now = datetime.utcnow()
    rows = []
    seen = set()
    for p in ports:
        code = (p.get("kode_pelabuhan") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append(dict(
            kode_pelabuhan=code,
            nama_pelabuhan=p.get("nama_pelabuhan"),
            last_seen=now,
        ))
    if not rows:
        return 0
    with engine.begin() as conn:
        stmt = sqlite_insert(Port.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["kode_pelabuhan"],
            set_={
                "nama_pelabuhan": stmt.excluded.nama_pelabuhan,
                "last_seen": stmt.excluded.last_seen,
            },
        )
        conn.execute(stmt)
    return len(rows)


def seed_ports() -> int:
    """Use the most recent month available to seed/refresh the ports table."""
    today = now_kst()
    candidates = [(today.year, today.month)]
    m, y = today.month - 1, today.year
    if m == 0:
        m, y = 12, y - 1
    candidates.append((y, m))
    for y, m in candidates:
        ports = list_ports(y, m)
        if ports:
            n = upsert_ports(ports)
            log.info("Seeded %d ports from %s-%02d", n, y, m)
            return n
    log.warning("No ports could be seeded from list API")
    return 0


def _parse_lk3(content: bytes) -> pd.DataFrame | None:
    """LK3 endpoint returns HTML-table 'xls'. Try parser stack."""
    text = content.decode("utf-8", errors="ignore")
    if not text.strip():
        return None
    # If pure HTML table, read_html
    try:
        tables = pd.read_html(io.StringIO(text))
        if tables:
            # find biggest
            tables.sort(key=lambda d: d.shape[0] * d.shape[1], reverse=True)
            return tables[0]
    except Exception:
        pass
    # Try as real xls (xlrd)
    try:
        return pd.read_excel(io.BytesIO(content), engine="xlrd")
    except Exception:
        pass
    # Try as xlsx (openpyxl)
    try:
        return pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception:
        pass
    return None


def _persist_lk3(df: pd.DataFrame, port_code: str, year: int, month: int,
                 kind: str, snapshot_month: str) -> int:
    if df is None or df.empty:
        return 0
    # normalize columns to strings
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    # drop fully-empty rows
    df = df.dropna(how="all")
    if df.empty:
        return 0
    now = datetime.utcnow()
    rows = []
    for idx, row in df.reset_index(drop=True).iterrows():
        d = {k: (None if pd.isna(v) else (v if isinstance(v, (int, float, str)) else str(v)))
             for k, v in row.items()}
        rows.append(dict(
            snapshot_month=snapshot_month,
            kode_pelabuhan=port_code,
            data_year=year,
            data_month=month,
            kind=kind,
            row_index=int(idx),
            raw_row=json.dumps(d, ensure_ascii=False, default=str),
            row_hash=_hash_row(d),
            scraped_at=now,
        ))
    if not rows:
        return 0
    with engine.begin() as conn:
        stmt = sqlite_insert(CargoSnapshot.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["snapshot_month", "kode_pelabuhan", "data_year",
                            "data_month", "kind", "row_index"],
            set_={
                "raw_row": stmt.excluded.raw_row,
                "row_hash": stmt.excluded.row_hash,
                "scraped_at": stmt.excluded.scraped_at,
            },
        )
        conn.execute(stmt)
    return len(rows)


def fetch_lk3(port: str, kind: str, year: int, month: int,
              snapshot_month: str, save_raw: bool = SAVE_RAW_CARGO) -> tuple[int, str | None]:
    url = INAPORT_LK3_URL.format(port=port, kind=kind, year=year, month=month)
    resp = get(url, INAPORT_HEADERS, target=f"lk3/{port}/{kind}/{year}/{month:02d}")
    if resp is None:
        return 0, "http_failed"
    content = resp.content
    if not content or len(content) < 64:
        return 0, "empty_response"
    if save_raw:
        try:
            raw_dir = RAW_DIR / snapshot_month / "cargo" / port
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{kind}_{year}-{month:02d}.xls").write_bytes(content)
        except Exception as exc:
            log.warning("save_raw failed %s/%s: %s", port, kind, exc)
    df = _parse_lk3(content)
    if df is None:
        return 0, "parse_failed"
    n = _persist_lk3(df, port, year, month, kind, snapshot_month)
    return n, None


def _all_ports() -> list[str]:
    with session_scope() as s:
        return [p.kode_pelabuhan for p in s.query(Port).order_by(Port.kode_pelabuhan).all()]


def scrape_all(snapshot_month: str | None = None,
               ports: list[str] | None = None,
               months: list[tuple[int, int]] | None = None,
               kinds: list[str] | None = None,
               max_workers: int = CARGO_WORKERS,
               progress_cb=None) -> dict:
    snapshot_month = snapshot_month or current_snapshot_month()
    if ports is None:
        ports = _all_ports()
    if months is None:
        months = _previous_months(CARGO_LOOKBACK_MONTHS)
    kinds = kinds or CARGO_KINDS

    targets = [(p, y, m, k) for p in ports for (y, m) in months for k in kinds]
    log.info("LK3 scrape targets=%d (ports=%d, months=%d, kinds=%d, workers=%d)",
             len(targets), len(ports), len(months), len(kinds), max_workers)

    succeeded = 0
    failed: list[dict] = []
    empty: list[dict] = []
    total_rows = 0

    def _run(t):
        port, y, m, k = t
        time.sleep(random.uniform(0.05, 0.2))
        try:
            return t, *fetch_lk3(port, k, y, m, snapshot_month)
        except Exception as exc:
            return t, 0, f"exception: {exc}"

    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_run, t) for t in targets]
        for fut in as_completed(futs):
            t, n, err = fut.result()
            completed += 1
            port, y, m, k = t
            total_rows += n
            if err == "empty_response":
                empty.append({"port": port, "year": y, "month": m, "kind": k})
            elif err:
                failed.append({"port": port, "year": y, "month": m, "kind": k, "error": err})
            else:
                succeeded += 1
            if progress_cb and completed % 50 == 0:
                progress_cb(completed, len(targets), total_rows)

    summary = {
        "snapshot_month": snapshot_month,
        "ports": len(ports),
        "months": len(months),
        "kinds": len(kinds),
        "total_targets": len(targets),
        "succeeded": succeeded,
        "empty": len(empty),
        "failed": len(failed),
        "total_rows": total_rows,
        "failed_targets": failed[:200],
    }
    log.info("LK3 scrape done: %s", {k: v for k, v in summary.items() if k != "failed_targets"})
    return summary
