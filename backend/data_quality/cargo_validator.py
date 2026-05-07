"""Re-validate cargo (LK3) raw_row dimensions / cargo amounts.

The inaportnet.dephub.go.id LK3 export is HTML scraped with pandas.read_html;
many cells contain operator-typed values where decimal points were dropped
(e.g. ``UKURAN.DWT='1600000000'`` instead of ``1600``,
``BONGKAR.TON='7934208000'`` instead of ``7934.208``,
``DRAFT.MAX='105075'`` instead of ``10.5075``). When the dashboard reads
those rows verbatim, single bad cells distort port totals by tens of
millions of tonnes.

This module runs after the cargo scrape, identifies suspect numeric cells
inside ``cargo_snapshot.raw_row``, attempts to recover the correct
magnitude by re-inserting a missing decimal, writes the corrected JSON
back, and logs every change to ``cargo_validation_log``.

Algorithm
---------
For each suspect cell we generate decimal-shift candidates
(``v / 10, v / 100, v / 1000 ...``), filter to candidates inside the
absolute plausibility envelope, prefer the one closest to a sibling-derived
expected value (e.g. UKURAN.GT anchors UKURAN.DWT ≈ 2 × GT, UKURAN.LOA
anchors DRAFT.MAX ≤ LOA / 12, UKURAN.DWT anchors BONGKAR.TON ≤ 2 × DWT).
Multiple in-range candidates fall back to the gentlest divisor.

Performance
-----------
2.4M+ rows per snapshot — far too many to scan in Python row-by-row. We use
SQLite's ``json_extract`` to pre-filter suspect rows in a single SELECT
(typically ~30k matches, all conditions OR-ed together) and then process
just those rows in a thread pool. Updates are batched via
``executemany``. Total runtime on the 2026-05 snapshot is < 2 minutes
even though the table itself has > 2.4M rows.

Usage::

    python -m backend.data_quality.cargo_validator                  # latest snapshot
    python -m backend.data_quality.cargo_validator --snapshot 2026-05
    python -m backend.data_quality.cargo_validator --dry-run        # report only
    python -m backend.data_quality.cargo_validator --all
    python -m backend.data_quality.cargo_validator --workers 4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.config import DB_URL, build_logger

log = build_logger("cargo_validator")


# Tuple-style raw_row JSON keys (the LK3 export uses MultiIndex columns
# stringified as Python tuples, hence the unusual key names).
K_DWT    = "('UKURAN', 'DWT')"
K_GT     = "('UKURAN', 'GT')"
K_LOA    = "('UKURAN', 'LOA')"
K_DRMAX  = "('DRAFT', 'MAX')"
K_DRF    = "('DRAFT', 'DEPAN')"
K_DRA    = "('DRAFT', 'BELAKANG')"
K_DRT    = "('DRAFT', 'TENGAH')"
K_BTON   = "('BONGKAR', 'TON')"
K_BUN    = "('BONGKAR', 'UNIT')"
K_BM3    = "('BONGKAR', 'M3')"
K_MTON   = "('MUAT', 'TON')"
K_MUN    = "('MUAT', 'UNIT')"
K_MM3    = "('MUAT', 'M3')"

# Plausibility envelopes.
PLAUSIBLE: dict[str, tuple[float, float]] = {
    K_DWT:    (10.0,    700_000.0),
    K_GT:     (5.0,     250_000.0),
    K_LOA:    (3.0,     500.0),
    K_DRMAX:  (0.3,     25.0),
    K_DRF:    (0.3,     25.0),
    K_DRA:    (0.3,     25.0),
    K_DRT:    (0.3,     25.0),
    K_BTON:   (0.001,   500_000.0),
    K_BUN:    (0.0,     50_000.0),
    K_BM3:    (0.0,     500_000.0),
    K_MTON:   (0.001,   500_000.0),
    K_MUN:    (0.0,     50_000.0),
    K_MM3:    (0.0,     500_000.0),
}

DIVISORS = (1, 10, 100, 1_000, 10_000, 100_000, 1_000_000,
            10_000_000, 100_000_000, 1_000_000_000)

# Aspect ratios used to derive an expected magnitude when a sibling field is
# trusted. These are coarse — meant to disambiguate between two candidates
# that both satisfy the absolute envelope, not to act as bounds.
RATIO_DWT_PER_GT      = 1.7    # DWT typically 1.5–2.5× GT for merchant ships
RATIO_GT_FROM_LOA_CUBED = 0.04 # GT ≈ 0.04 × LOA³ (rough)
RATIO_LOA_PER_BEAM    = 5.0
RATIO_LOA_PER_DRAFT   = 12.0   # LOA typically 10–15× max draft
RATIO_TON_PER_DWT_MAX = 2.0    # cargo ≤ 2× DWT (allow some slack)


@dataclass
class CargoFix:
    row_id: int
    field: str
    original: float
    corrected: float
    rule: str   # e.g. "/100;anchor=UKURAN.DWT"


def _to_num(v) -> float | None:
    """Best-effort numeric coercion. Returns None on '-', '', None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ("", "-"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _expected(field: str, trust: dict[str, float]) -> float | None:
    """Magnitude implied by trusted siblings, or None if no anchor."""
    if field == K_DWT and K_GT in trust:
        return trust[K_GT] * RATIO_DWT_PER_GT
    if field == K_GT and K_DWT in trust:
        return trust[K_DWT] / RATIO_DWT_PER_GT
    if field == K_GT and K_LOA in trust:
        return trust[K_LOA] ** 3 * RATIO_GT_FROM_LOA_CUBED
    if field == K_LOA:
        if K_GT in trust:
            return (trust[K_GT] / RATIO_GT_FROM_LOA_CUBED) ** (1.0 / 3.0)
        if K_DRMAX in trust:
            return trust[K_DRMAX] * RATIO_LOA_PER_DRAFT
    if field in (K_DRMAX, K_DRF, K_DRA, K_DRT):
        if K_LOA in trust:
            return trust[K_LOA] / RATIO_LOA_PER_DRAFT
        # All draft fields converge — use any other trusted draft as anchor.
        for k in (K_DRMAX, K_DRF, K_DRA, K_DRT):
            if k in trust and k != field:
                return trust[k]
    # Cargo amounts (TON / UNIT / M3) have no useful "expected" formula —
    # cargo varies enormously by trip and commodity. Fall back on the
    # gentlest-divisor rule, which is what _best_divisor does when expected
    # is None. Hard upper bounds come from _passes_geometry (TON ≤ 2×DWT).
    return None


def _passes_geometry(field: str, value: float,
                     trust: dict[str, float]) -> bool:
    """Reject candidates that break ship-geometry / cargo-vs-DWT invariants."""
    if field in (K_DRMAX, K_DRF, K_DRA, K_DRT):
        # Draft must be ≤ LOA/3 (extremely lenient).
        if K_LOA in trust and value > trust[K_LOA] / 3.0:
            return False
    if field == K_LOA:
        # LOA must accommodate any trusted draft.
        for k in (K_DRMAX, K_DRF, K_DRA, K_DRT):
            if k in trust and value < trust[k] * 3.0:
                return False
    if field in (K_BTON, K_MTON):
        if K_DWT in trust and value > trust[K_DWT] * RATIO_TON_PER_DWT_MAX:
            return False
    return True


def _best_divisor(v: float, field: str,
                  trust: dict[str, float]) -> tuple[float, int] | None:
    """Pick the most plausible decimal shift for v."""
    if v is None or v <= 0:
        return None
    lo, hi = PLAUSIBLE[field]
    cand: list[tuple[int, float]] = []
    for d in DIVISORS:
        s = v / d
        if not (lo <= s <= hi):
            continue
        if not _passes_geometry(field, s, trust):
            continue
        cand.append((d, s))
    if not cand:
        return None
    expected = _expected(field, trust)
    if expected and expected > 0:
        in_range = [(d, s) for d, s in cand
                    if expected / 5 <= s <= expected * 5]
        if in_range:
            d, s = max(in_range, key=lambda c: c[1])
        else:
            d, s = min(cand, key=lambda c: abs(c[1] - expected))
    else:
        d, s = min(cand, key=lambda c: c[0])
    return s, d


# Order matters: vessel-size fields anchor everything else; resolve them
# first. Then drafts (anchored on LOA), then cargo amounts (anchored on DWT).
FIELD_ORDER = (K_GT, K_DWT, K_LOA, K_DRMAX, K_DRF, K_DRA, K_DRT,
               K_BTON, K_BUN, K_BM3, K_MTON, K_MUN, K_MM3)


def _classify(values: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    trust: dict[str, float] = {}
    suspect: dict[str, float] = {}
    for f, v in values.items():
        if v is None or v <= 0:
            continue
        lo, hi = PLAUSIBLE[f]
        if lo <= v <= hi:
            trust[f] = v
        else:
            suspect[f] = v
    # Demote a trusted GT/DWT pair when they disagree wildly (factor > 5).
    if K_GT in trust and K_DWT in trust:
        ratio = max(trust[K_GT], trust[K_DWT]) / max(min(trust[K_GT], trust[K_DWT]), 1e-9)
        if ratio > 5.0:
            # Trust the smaller one only if it fits the LOA anchor.
            if K_LOA in trust:
                expect_gt = trust[K_LOA] ** 3 * RATIO_GT_FROM_LOA_CUBED
                far_gt = abs(trust[K_GT] - expect_gt) / max(expect_gt, 1.0)
                far_dwt = abs(trust[K_DWT] - expect_gt * RATIO_DWT_PER_GT) / max(expect_gt * RATIO_DWT_PER_GT, 1.0)
                bad = K_GT if far_gt > far_dwt else K_DWT
                suspect[bad] = trust.pop(bad)
    # Draft fields ≤ 1/3 LOA — demote drafts that violate.
    if K_LOA in trust:
        for k in (K_DRMAX, K_DRF, K_DRA, K_DRT):
            if k in trust and trust[k] > trust[K_LOA] / 3.0:
                suspect[k] = trust.pop(k)
    # Cargo amounts ≤ 2× DWT — demote violators.
    if K_DWT in trust:
        for k in (K_BTON, K_MTON):
            if k in trust and trust[k] > trust[K_DWT] * RATIO_TON_PER_DWT_MAX:
                suspect[k] = trust.pop(k)
    return trust, suspect


def _detect_fixes(row_id: int, values: dict[str, float]) -> list[CargoFix]:
    trust, suspect = _classify(values)
    if not suspect:
        return []
    fixes: list[CargoFix] = []
    for _ in range(2):
        progress = False
        for f in FIELD_ORDER:
            if f not in suspect:
                continue
            r = _best_divisor(suspect[f], f, trust)
            if r is None:
                continue
            new, d = r
            if d == 1:
                trust[f] = new
                suspect.pop(f)
                progress = True
                continue
            anchor = None
            for k in (K_LOA, K_GT, K_DWT, K_DRMAX):
                if k in trust and k != f and _expected(f, {k: trust[k]}) is not None:
                    anchor = k
                    break
            anchor_short = (anchor.split(",")[1].strip()[1:-1]
                            if anchor else "")
            rule = f"/{d}" + (f";anchor={anchor_short}" if anchor else ";abs")
            existing = next((x for x in fixes if x.field == f), None)
            if existing:
                existing.corrected = new
                existing.rule = rule
            else:
                fixes.append(CargoFix(row_id, f, suspect[f], new, rule))
            trust[f] = new
            suspect.pop(f)
            progress = True
        if not progress:
            break
    return fixes


# ---------------------------------------------------------------------------
# Worker fn (top-level so it pickles for ProcessPoolExecutor)
# ---------------------------------------------------------------------------

def _process_chunk(rows: list[tuple[int, str]]) -> list[tuple]:
    """Worker: return [(row_id, new_raw_row, new_hash, [fixes...]), ...]."""
    out: list[tuple] = []
    for row_id, raw_row in rows:
        try:
            obj = json.loads(raw_row)
        except (TypeError, json.JSONDecodeError):
            continue
        values = {k: _to_num(obj.get(k)) for k in PLAUSIBLE}
        fixes = _detect_fixes(row_id, values)
        if not fixes:
            continue
        # Apply fixes in-place to a copy of the JSON object.
        # Preserve original numeric type (int → int, float → float).
        for f in fixes:
            corrected = f.corrected
            old = obj.get(f.field)
            if isinstance(old, int) and corrected.is_integer():
                obj[f.field] = int(corrected)
            elif isinstance(old, str):
                # Mirror the original textual representation as best we can.
                obj[f.field] = (str(int(corrected))
                                if corrected.is_integer() else f"{corrected:g}")
            else:
                obj[f.field] = corrected
        new_raw = json.dumps(obj, ensure_ascii=False, default=str)
        new_hash = hashlib.sha256(new_raw.encode("utf-8")).hexdigest()
        out.append((row_id, new_raw, new_hash, fixes))
    return out


# ---------------------------------------------------------------------------
# DB plumbing
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    if not DB_URL.startswith("sqlite"):
        raise RuntimeError(f"Only sqlite supported (got {DB_URL!r})")
    return Path(DB_URL.replace("sqlite:///", "", 1))


def _ensure_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cargo_validation_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_month  TEXT NOT NULL,
            cargo_row_id    INTEGER NOT NULL,
            field           TEXT NOT NULL,
            original_value  REAL,
            corrected_value REAL,
            rule            TEXT,
            applied_at      TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_cvl_snap "
        "ON cargo_validation_log(snapshot_month)"
    )


def _suspect_select(snapshot_month: str) -> tuple[str, tuple]:
    """One pass over cargo_snapshot to collect candidate-row ids+raw_row.

    The WHERE clause OR-s every outlier condition so we touch the table just
    once. Anything that *might* need fixing comes back; the Python side does
    the deeper geometric analysis.
    """
    def num(j: str) -> str:
        return f"CAST(NULLIF(NULLIF({j}, '-'), '') AS REAL)"

    j = lambda k: f'''json_extract(raw_row, '$."{k.replace("'", "''")}"')'''
    where = " OR ".join([
        f"{num(j(K_DWT))}   > {PLAUSIBLE[K_DWT][1]}",
        f"{num(j(K_GT))}    > {PLAUSIBLE[K_GT][1]}",
        f"{num(j(K_LOA))}   > {PLAUSIBLE[K_LOA][1]}",
        f"{num(j(K_DRMAX))} > {PLAUSIBLE[K_DRMAX][1]}",
        f"{num(j(K_DRF))}   > {PLAUSIBLE[K_DRF][1]}",
        f"{num(j(K_DRA))}   > {PLAUSIBLE[K_DRA][1]}",
        f"{num(j(K_DRT))}   > {PLAUSIBLE[K_DRT][1]}",
        f"{num(j(K_BTON))}  > {PLAUSIBLE[K_BTON][1]}",
        f"{num(j(K_BUN))}   > {PLAUSIBLE[K_BUN][1]}",
        f"{num(j(K_BM3))}   > {PLAUSIBLE[K_BM3][1]}",
        f"{num(j(K_MTON))}  > {PLAUSIBLE[K_MTON][1]}",
        f"{num(j(K_MUN))}   > {PLAUSIBLE[K_MUN][1]}",
        f"{num(j(K_MM3))}   > {PLAUSIBLE[K_MM3][1]}",
        # Relational: TON > 2 × DWT (when DWT plausible)
        f"({num(j(K_BTON))} > 2*{num(j(K_DWT))} AND {num(j(K_DWT))} > 100)",
        f"({num(j(K_MTON))} > 2*{num(j(K_DWT))} AND {num(j(K_DWT))} > 100)",
        # Relational: draft > LOA/3
        f"({num(j(K_DRMAX))} > {num(j(K_LOA))}/3.0 AND {num(j(K_LOA))} > 0)",
    ])
    sql = (f"SELECT id, raw_row FROM cargo_snapshot "
           f"WHERE snapshot_month = ? AND ({where})")
    return sql, (snapshot_month,)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_snapshot(snapshot_month: str, dry_run: bool = False,
                      workers: int | None = None,
                      chunk_size: int = 5000) -> dict:
    db_path = _db_path()
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    workers = workers or max(1, (os.cpu_count() or 4) - 1)
    t0 = time.time()
    log.info("snapshot=%s workers=%d chunk_size=%d",
             snapshot_month, workers, chunk_size)

    with sqlite3.connect(db_path) as conn:
        _ensure_log_table(conn)
        sql, params = _suspect_select(snapshot_month)
        log.info("Selecting suspect rows…")
        suspects = conn.execute(sql, params).fetchall()
        log.info("Suspect rows: %d (in %.1fs)", len(suspects), time.time() - t0)

        # Chunk for the worker pool
        chunks: list[list[tuple[int, str]]] = []
        for i in range(0, len(suspects), chunk_size):
            chunks.append(suspects[i:i + chunk_size])

        results: list[tuple] = []
        if not chunks:
            pass
        elif workers == 1 or len(suspects) < 2 * chunk_size:
            # Sequential is faster than spinning up processes for small jobs.
            for ch in chunks:
                results.extend(_process_chunk(ch))
        else:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                for sub in ex.map(_process_chunk, chunks):
                    results.extend(sub)
        log.info("Detected %d rows-to-fix in %.1fs",
                 len(results), time.time() - t0)

        all_fixes: list[CargoFix] = []
        for _, _, _, fixes in results:
            all_fixes.extend(fixes)

        applied = 0
        if not dry_run and results:
            now = datetime.utcnow().isoformat(timespec="seconds")
            update_args = [(new_raw, new_hash, rid)
                           for (rid, new_raw, new_hash, _) in results]
            conn.executemany(
                "UPDATE cargo_snapshot SET raw_row = ?, row_hash = ? "
                "WHERE id = ?",
                update_args,
            )
            log_args = [(snapshot_month, f.row_id, f.field, f.original,
                         f.corrected, f.rule, now) for f in all_fixes]
            conn.executemany(
                "INSERT INTO cargo_validation_log "
                "(snapshot_month, cargo_row_id, field, original_value, "
                " corrected_value, rule, applied_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                log_args,
            )
            conn.commit()
            applied = len(all_fixes)
            log.info("Wrote %d row updates + %d log entries in %.1fs",
                     len(update_args), applied, time.time() - t0)

        return {
            "snapshot_month": snapshot_month,
            "suspects": len(suspects),
            "rows_affected": len(results),
            "fixes_total": len(all_fixes),
            "fixes_applied": applied,
            "dry_run": dry_run,
            "elapsed_s": round(time.time() - t0, 1),
            "fixes": all_fixes,
        }


def _format_fixes(fixes: list[CargoFix], limit: int = 80) -> str:
    out: list[str] = []
    for i, f in enumerate(fixes):
        if i >= limit:
            out.append(f"  ... ({len(fixes)} total, showing first {limit})")
            break
        # Strip noisy tuple-string brackets in display only.
        pretty = f.field.replace("('", "").replace("')", "").replace("', '", ".")
        out.append(
            f"  row#{f.row_id:<8d} {pretty:<14s} "
            f"{f.original:>18,.4f} -> {f.corrected:>14,.4f}  [{f.rule}]"
        )
    return "\n".join(out)


def _list_snapshots() -> list[str]:
    with sqlite3.connect(_db_path()) as conn:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT snapshot_month FROM cargo_snapshot "
            "ORDER BY snapshot_month DESC")]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshot", help="Snapshot month YYYY-MM (default: latest)")
    p.add_argument("--all", action="store_true",
                   help="Process every snapshot in cargo_snapshot")
    p.add_argument("--dry-run", action="store_true",
                   help="Report fixes without writing")
    p.add_argument("--workers", type=int, default=None,
                   help="Parallel worker processes (default: CPU-1)")
    p.add_argument("--chunk-size", type=int, default=5000,
                   help="Rows per worker chunk (default: 5000)")
    args = p.parse_args()

    snapshots = _list_snapshots()
    if not snapshots:
        log.error("cargo_snapshot is empty")
        return 1

    targets = snapshots if args.all else [args.snapshot or snapshots[0]]
    grand_total = 0
    for m in targets:
        res = validate_snapshot(m, dry_run=args.dry_run,
                                workers=args.workers,
                                chunk_size=args.chunk_size)
        grand_total += res["fixes_total"]
        verb = "would-fix" if args.dry_run else "fixed"
        log.info(
            "[%s] suspects=%d rows_affected=%d fixes_%s=%d (%.1fs)",
            m, res["suspects"], res["rows_affected"], verb,
            res["fixes_total"], res["elapsed_s"],
        )
        if res["fixes"]:
            print(_format_fixes(res["fixes"]))
    log.info("Grand total fixes %s: %d",
             "(dry-run)" if args.dry_run else "applied", grand_total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
