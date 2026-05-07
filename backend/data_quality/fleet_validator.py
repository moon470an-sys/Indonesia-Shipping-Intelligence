"""Re-validate vessels_snapshot dimensions/tonnage and correct upstream typos.

The kapal.dephub.go.id API occasionally returns dimension fields with the
decimal point dropped (e.g. ``Panjang='81053'`` for an 81.053 m vessel,
``Lebar='7890'`` for 7.890 m). The scraper stores these values verbatim, so
the Fleet dashboard sees ships hundreds of kilometres long.

This module scans vessels_snapshot for implausible values, attempts to
restore the correct magnitude by re-inserting the missing decimal, and
writes the corrections back. Every change is logged to
``vessels_validation_log`` so the operation is auditable and reversible.

Algorithm
---------
For each row we compute a "trusted" set of dimensions — fields whose values
already fall inside the absolute plausibility envelope (e.g. lebar in
[0.3, 80] m). For each suspect field we generate decimal-shift candidates
(``v/10, v/100, v/1000 ...``), filter out candidates that violate either
the absolute envelope or geometric invariants (length ≥ beam ≥ depth, two
length fields within ±factor of 3), and finally pick the candidate closest
to the value implied by trusted siblings. Without an anchor we fall back to
the gentlest divisor.

Usage::

    python -m backend.data_quality.fleet_validator                  # latest snapshot, apply
    python -m backend.data_quality.fleet_validator --snapshot 2026-05
    python -m backend.data_quality.fleet_validator --dry-run        # report only
    python -m backend.data_quality.fleet_validator --all            # every snapshot
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from backend.config import DB_URL, build_logger

log = build_logger("fleet_validator")


# Absolute plausibility envelope. Tuned against the largest realistic
# Indonesia-flagged vessels (VLCCs / FSRUs ~330 m LOA, ~60 m beam).
PLAUSIBLE = {
    "panjang":       (0.5, 500.0),
    "length_of_all": (0.5, 500.0),
    "lebar":         (0.3,  80.0),
    "dalam":         (0.2,  40.0),
}

# Decimal-shift candidates we'll try when a value looks like it lost its
# decimal point. 1 is included so the original passes through if it's already
# inside any geometric constraint.
DIVISORS = (1, 10, 100, 1000, 10000, 100000)

# Typical aspect ratios used to derive an "expected" magnitude when only
# some sibling fields are trusted. These are coarse guides, not strict bounds.
RATIO_LEN_BEAM  = 5.0   # length ≈ beam × 5
RATIO_LEN_DEPTH = 12.0  # length ≈ depth × 12
RATIO_BEAM_DEPTH = 3.0  # beam   ≈ depth × 3


@dataclass
class Fix:
    vessel_key: str
    field: str
    original: float
    corrected: float
    rule: str   # e.g. "/100;anchor=lebar" or "/10;abs"


def _length_plausible_for_gt(length: float, gt: float | None) -> bool | None:
    """True if `length` (m) is consistent with the row's gross tonnage.

    GT scales roughly with hull volume (≈ L³), but for the floor we want a
    very lenient check: a real ship of length L should at minimum carry
    ``GT ≥ L²/8`` — derived empirically from the largest L-to-GT mismatches in
    the snapshot. Returns None when GT is missing so the caller can fall back.
    """
    if gt is None or gt <= 0:
        return None
    return gt >= (length * length) / 8.0


def _expected(field: str, trusted: dict[str, float]) -> float | None:
    """Magnitude we expect for `field` given trusted siblings."""
    if field in ("panjang", "length_of_all"):
        other = "length_of_all" if field == "panjang" else "panjang"
        if other in trusted:
            return trusted[other]
        if "lebar" in trusted:
            return trusted["lebar"] * RATIO_LEN_BEAM
        if "dalam" in trusted:
            return trusted["dalam"] * RATIO_LEN_DEPTH
    elif field == "lebar":
        if "panjang" in trusted:
            return trusted["panjang"] / RATIO_LEN_BEAM
        if "length_of_all" in trusted:
            return trusted["length_of_all"] / RATIO_LEN_BEAM
        if "dalam" in trusted:
            return trusted["dalam"] * RATIO_BEAM_DEPTH
    elif field == "dalam":
        if "lebar" in trusted:
            return trusted["lebar"] / RATIO_BEAM_DEPTH
        if "panjang" in trusted:
            return trusted["panjang"] / RATIO_LEN_DEPTH
        if "length_of_all" in trusted:
            return trusted["length_of_all"] / RATIO_LEN_DEPTH
    return None


def _passes_geometry(field: str, value: float, trusted: dict[str, float]) -> bool:
    """Reject candidates that break length ≥ beam ≥ depth or length≈length."""
    if field in ("panjang", "length_of_all"):
        if "lebar" in trusted and value < trusted["lebar"]:
            return False
        if "dalam" in trusted and value < trusted["dalam"]:
            return False
        other = "length_of_all" if field == "panjang" else "panjang"
        if other in trusted:
            t = trusted[other]
            ratio = max(value, t) / min(value, t)
            if ratio > 3.0:
                return False
    elif field == "lebar":
        for L in ("panjang", "length_of_all"):
            if L in trusted and value > trusted[L]:
                return False
        if "dalam" in trusted and value < trusted["dalam"]:
            return False
    elif field == "dalam":
        if "lebar" in trusted and value > trusted["lebar"]:
            return False
        for L in ("panjang", "length_of_all"):
            if L in trusted and value > trusted[L]:
                return False
    return True


def _best_divisor(v: float, field: str,
                  trusted: dict[str, float]) -> tuple[float, int] | None:
    """Pick the most plausible decimal shift for v.

    Returns (corrected_value, divisor) or None if no divisor produces a value
    that passes both the absolute envelope and the geometric constraints.
    """
    if v is None or v <= 0:
        return None
    lo, hi = PLAUSIBLE[field]
    candidates: list[tuple[int, float]] = []
    for d in DIVISORS:
        s = v / d
        if not (lo <= s <= hi):
            continue
        if not _passes_geometry(field, s, trusted):
            continue
        candidates.append((d, s))
    if not candidates:
        return None
    expected = _expected(field, trusted)
    if expected is not None and expected > 0:
        # Within ±factor-of-3 of expected (one decimal of slack), prefer the
        # *largest* candidate — i.e. the gentlest correction. This avoids
        # over-shrinking a borderline value when both ÷10 and ÷100 land near
        # an under-the-water expected magnitude (e.g. small fishing boats
        # where typical depth ≈ 1 m straddles 0.3 / 3.0).
        in_range = [(d, s) for d, s in candidates if expected / 3 <= s <= expected * 3]
        if in_range:
            d, s = max(in_range, key=lambda c: c[1])
        else:
            d, s = min(candidates, key=lambda c: abs(c[1] - expected))
    else:
        # No anchor — pick the gentlest fix (smallest divisor).
        d, s = min(candidates, key=lambda c: c[0])
    return s, d


# Order matters: fixing the longer dimensions first gives later passes a
# better anchor set. We also re-fix length_of_all using the freshly-fixed
# panjang as an anchor (and vice versa).
FIELD_ORDER = ("panjang", "length_of_all", "lebar", "dalam")


# Triggers for soft (in-envelope) geometric violations. We only flag a field
# when the violation is so large that the divide-by-10 candidate clearly
# beats the original. Ratios closer to 1× (e.g. depth ≈ beam) are left alone
# because either field could be the typo, and silently overwriting can hide
# real bugs in the *other* field.
GEOM_TRIGGER_BEAM_OVER_LEN   = 2.0   # lebar > 2× length → lebar is the typo
GEOM_TRIGGER_BEAM_UNDER_LEN  = 10.0  # length > 10× beam → beam might be a typo
GEOM_TRIGGER_DEPTH_OVER_BEAM = 2.0   # dalam > 2× lebar  → dalam is the typo
GEOM_TRIGGER_DEPTH_OVER_LEN  = 0.7   # dalam > 0.7× length → impossible


def _demote_geometry_violators(trusted: dict[str, float],
                               suspect: dict[str, float],
                               gt: float | None = None) -> None:
    """Move trusted fields that break length≥beam≥depth into the suspect set.

    Order matters: demote the *length* fields first, because the kapal API
    sometimes stores a placeholder (``1`` / ``0``) in length_of_all while the
    real beam sits in lebar. Anchoring on that placeholder length would
    incorrectly shrink the true beam.
    """
    # 1) Length must be >= beam. A length below the trusted beam is almost
    #    certainly a placeholder (raw values like '1' or '1.20').
    if "lebar" in trusted:
        for L in ("panjang", "length_of_all"):
            if L in trusted and trusted[L] < trusted["lebar"]:
                suspect[L] = trusted.pop(L)
    # 2) The two length fields should agree within ±factor of 3. If they
    #    differ wildly, the bogus side is whichever fails the GT plausibility
    #    check (or, if both fail, both are demoted).
    if "panjang" in trusted and "length_of_all" in trusted:
        a, b = trusted["panjang"], trusted["length_of_all"]
        if max(a, b) / max(min(a, b), 1e-9) > 3.0:
            for k in ("panjang", "length_of_all"):
                if _length_plausible_for_gt(trusted[k], gt) is False:
                    suspect[k] = trusted.pop(k)
            # Still both? Demote whichever is farther from the beam-anchored
            # expected length.
            if "panjang" in trusted and "length_of_all" in trusted:
                a, b = trusted["panjang"], trusted["length_of_all"]
                expect = trusted.get("lebar", 0) * RATIO_LEN_BEAM
                if expect > 0:
                    far = "panjang" if abs(a - expect) > abs(b - expect) else "length_of_all"
                    suspect[far] = trusted.pop(far)
                else:
                    suspect["length_of_all"] = trusted.pop("length_of_all")
    # 3) Length / beam disagreement.
    #    - lebar > 2× shortest length → lebar is the typo.
    #    - length > 10× lebar → either length or beam is the typo. Decide by
    #      magnitude: when beam looks normal (≥5 m) and length is large
    #      (>50 m), the length almost certainly lost a decimal; otherwise
    #      blame beam.
    if "lebar" in trusted:
        L_items = {k: trusted[k] for k in ("panjang", "length_of_all") if k in trusted}
        if L_items:
            beam = trusted["lebar"]
            if beam > GEOM_TRIGGER_BEAM_OVER_LEN * min(L_items.values()):
                suspect["lebar"] = trusted.pop("lebar")
            else:
                long_offenders = {k: v for k, v in L_items.items()
                                  if v > GEOM_TRIGGER_BEAM_UNDER_LEN * beam}
                if long_offenders:
                    # GT-implausible lengths point clearly at a length typo;
                    # GT-plausible lengths with normal beam point at a beam
                    # typo (real long-narrow boats register large GT).
                    impl = {k: v for k, v in long_offenders.items()
                            if _length_plausible_for_gt(v, gt) is False}
                    if impl:
                        for k in impl:
                            suspect[k] = trusted.pop(k)
                    elif beam < 5.0:
                        # Suspiciously narrow beam paired with normal length.
                        suspect["lebar"] = trusted.pop("lebar")
                    # Otherwise we lack confidence to blame either side; leave
                    # both alone rather than introduce a false positive.
    # 4) Depth checks: only flag when *much* deeper than beam, or beyond
    #    realistic depth-to-length ratio.
    if "dalam" in trusted:
        beam = trusted.get("lebar")
        if beam is not None and trusted["dalam"] > GEOM_TRIGGER_DEPTH_OVER_BEAM * beam:
            suspect["dalam"] = trusted.pop("dalam")
        else:
            anchors = [trusted[k] for k in ("panjang", "length_of_all") if k in trusted]
            if anchors and trusted["dalam"] > GEOM_TRIGGER_DEPTH_OVER_LEN * min(anchors):
                suspect["dalam"] = trusted.pop("dalam")


def _detect_fixes(row: sqlite3.Row) -> list[Fix]:
    # Initial trusted set: any field already inside its absolute envelope.
    trusted: dict[str, float] = {}
    suspect: dict[str, float] = {}
    for f in FIELD_ORDER:
        v = row[f]
        if v is None or v <= 0:
            continue
        lo, hi = PLAUSIBLE[f]
        if lo <= v <= hi:
            trusted[f] = float(v)
        else:
            suspect[f] = float(v)
    # Even in-envelope values can violate ship geometry. GT helps decide
    # whether a borderline length is legitimately big or just a typo.
    gt = float(row["gt"]) if row["gt"] not in (None, 0) else None
    _demote_geometry_violators(trusted, suspect, gt)

    if not suspect:
        return []

    fixes: list[Fix] = []
    # Two passes — pass 1 uses initial trusted set, pass 2 may use values
    # corrected during pass 1.
    for _ in range(2):
        progress = False
        for f in FIELD_ORDER:
            if f not in suspect:
                continue
            result = _best_divisor(suspect[f], f, trusted)
            if result is None:
                continue
            new, d = result
            # If divisor is 1, the original was already plausible given new
            # sibling info — drop the suspect tag and don't record a fix.
            if d == 1:
                trusted[f] = new
                suspect.pop(f)
                progress = True
                continue
            anchor = next(
                (k for k in ("length_of_all", "panjang", "lebar", "dalam")
                 if k in trusted and k != f),
                None,
            )
            rule = f"/{d}" + (f";anchor={anchor}" if anchor else ";abs")
            existing = next((x for x in fixes if x.field == f), None)
            if existing:
                existing.corrected = new
                existing.rule = rule
            else:
                fixes.append(Fix(row["vessel_key"], f, suspect[f], new, rule))
            trusted[f] = new
            suspect.pop(f)
            progress = True
        if not progress:
            break
    return fixes


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vessels_validation_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_month  TEXT NOT NULL,
            vessel_key      TEXT NOT NULL,
            field           TEXT NOT NULL,
            original_value  REAL,
            corrected_value REAL,
            rule            TEXT,
            applied_at      TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_vvl_snap "
        "ON vessels_validation_log(snapshot_month)"
    )


def _db_path() -> Path:
    if not DB_URL.startswith("sqlite"):
        raise RuntimeError(f"Only sqlite is supported (got {DB_URL!r})")
    return Path(DB_URL.replace("sqlite:///", "", 1))


def _fetch_rows(conn: sqlite3.Connection, snapshot_month: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    sql = ("SELECT id, snapshot_month, vessel_key, nama_kapal, "
           "panjang, lebar, dalam, length_of_all, gt "
           "FROM vessels_snapshot WHERE snapshot_month = ?")
    return conn.execute(sql, (snapshot_month,)).fetchall()


def validate_snapshot(snapshot_month: str, dry_run: bool = False) -> dict:
    db_path = _db_path()
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    with sqlite3.connect(db_path) as conn:
        _ensure_log_table(conn)
        rows = _fetch_rows(conn, snapshot_month)
        log.info("snapshot=%s rows=%d", snapshot_month, len(rows))

        all_fixes: list[Fix] = []
        rows_affected = 0
        for r in rows:
            fixes = _detect_fixes(r)
            if not fixes:
                continue
            rows_affected += 1
            all_fixes.extend(fixes)

        per_row: dict[str, list[Fix]] = {}
        for f in all_fixes:
            per_row.setdefault(f.vessel_key, []).append(f)

        applied = 0
        if not dry_run and per_row:
            now = datetime.utcnow().isoformat(timespec="seconds")
            for vk, group in per_row.items():
                set_clause = ", ".join(f"{f.field} = ?" for f in group)
                params = [f.corrected for f in group]
                params.extend([snapshot_month, vk])
                conn.execute(
                    f"UPDATE vessels_snapshot SET {set_clause} "
                    f"WHERE snapshot_month = ? AND vessel_key = ?",
                    params,
                )
                latest = conn.execute(
                    "SELECT snapshot_month_latest FROM vessels_current "
                    "WHERE vessel_key = ?", (vk,)
                ).fetchone()
                if latest and latest[0] == snapshot_month:
                    cur_set = ", ".join(
                        f"{f.field} = ?" for f in group if f.field != "length_of_all"
                    )
                    cur_params = [f.corrected for f in group if f.field != "length_of_all"]
                    if cur_set:
                        cur_params.append(vk)
                        conn.execute(
                            f"UPDATE vessels_current SET {cur_set} "
                            f"WHERE vessel_key = ?",
                            cur_params,
                        )
                conn.executemany(
                    "INSERT INTO vessels_validation_log "
                    "(snapshot_month, vessel_key, field, original_value, "
                    " corrected_value, rule, applied_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(snapshot_month, f.vessel_key, f.field,
                      f.original, f.corrected, f.rule, now) for f in group],
                )
                applied += len(group)
            conn.commit()

        return {
            "snapshot_month": snapshot_month,
            "rows_scanned": len(rows),
            "rows_affected": rows_affected,
            "fixes_total": len(all_fixes),
            "fixes_applied": applied,
            "dry_run": dry_run,
            "fixes": all_fixes,
        }


def _format_fixes(fixes: list[Fix], limit: int = 200) -> str:
    out = []
    for i, f in enumerate(fixes):
        if i >= limit:
            out.append(f"  ... ({len(fixes)} total, showing first {limit})")
            break
        out.append(
            f"  {f.vessel_key:<35s} {f.field:<14s} "
            f"{f.original:>12.4f} -> {f.corrected:>10.4f}  [{f.rule}]"
        )
    return "\n".join(out)


def _list_snapshots() -> list[str]:
    with sqlite3.connect(_db_path()) as conn:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT snapshot_month FROM vessels_snapshot "
            "ORDER BY snapshot_month DESC")]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshot", help="Snapshot month YYYY-MM (default: latest)")
    p.add_argument("--all", action="store_true",
                   help="Process every snapshot in vessels_snapshot")
    p.add_argument("--dry-run", action="store_true",
                   help="Report fixes without writing")
    args = p.parse_args()

    snapshots = _list_snapshots()
    if not snapshots:
        log.error("vessels_snapshot is empty")
        return 1

    targets = snapshots if args.all else [args.snapshot or snapshots[0]]
    grand_total = 0
    for m in targets:
        res = validate_snapshot(m, dry_run=args.dry_run)
        grand_total += res["fixes_total"]
        verb = "would-fix" if args.dry_run else "fixed"
        log.info(
            "[%s] scanned=%d rows_affected=%d fixes_%s=%d",
            m, res["rows_scanned"], res["rows_affected"], verb, res["fixes_total"],
        )
        if res["fixes"]:
            print(_format_fixes(res["fixes"]))
    log.info("Grand total fixes %s: %d",
             "(dry-run)" if args.dry_run else "applied", grand_total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
