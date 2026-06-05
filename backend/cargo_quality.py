"""Cargo data-quality helpers shared by build_static and build_derived.

The LK3 feed (monitoring-inaportnet.dephub.go.id) contains data-entry errors
where a single port-call cargo row reports a tonnage far larger than the
carrying vessel could physically hold — e.g. 400,000 t of CPO on a 2,300 GT
barge, or 486,400 t of *empty* containers. These inflate monthly aggregates
(observed: FAME/Veg-oil 2025-11 and 2026-05 spikes were each a single bogus
~400k t CPO row at port IDRGT / KUALA CINAKU).

Physical bound: a ship's cargo cannot exceed its deadweight, and deadweight is
at most ~2× gross tonnage (GT) for the heaviest ship types. Every cargo row
carries the vessel's GT in raw_row, so we treat any row whose ton exceeds
GT × GT_OVERLOAD_FACTOR as invalid and zero it out. The factor 3 is a
conservative cut: the largest *real* cargoes observed sit at ~1.8–2.7× GT
(VLCC crude, Capesize coal), all kept, while the error rows are 10–220× GT.

Applied uniformly at the SQL ton-extraction layer so every cargo aggregate
(monthly trend, port map, category details, balance breakdown) is consistent.
"""
from __future__ import annotations

# raw_row JSON key for the vessel's gross tonnage.
GT_KEY = "('UKURAN', 'GT')"
# A single cargo row with ton > GT × this factor is a data-entry error.
GT_OVERLOAD_FACTOR = 3


def _sql_path(key: str) -> str:
    """SQL-literal-safe JSON path for a raw_row key (single quotes doubled).

    Matches the encoding used by build_static._sql_path / build_derived._p,
    so the produced expression embeds cleanly inside an SQL string literal.
    """
    return ('$."' + key + '"').replace("'", "''")


_GT_PATH = _sql_path(GT_KEY)


def capped_ton_sql(ton_path: str, *, coalesce: bool = True) -> str:
    """SQL expression for a cargo ton value, zeroed when physically impossible.

    ``ton_path`` is the already-SQL-encoded JSON path for the TON field
    (e.g. produced by build_static._sql_path("('MUAT', 'TON')")). The result
    is a drop-in replacement for the previous
    ``COALESCE(CAST(NULLIF(json_extract(raw_row, '<path>'), '-') AS REAL), 0)``.

    Set ``coalesce=False`` to keep NULL passthrough (matches the old ``ton_x``
    helper that omitted the COALESCE wrapper).
    """
    gt = f"CAST(NULLIF(json_extract(raw_row, '{_GT_PATH}'), '-') AS REAL)"
    raw = f"CAST(NULLIF(json_extract(raw_row, '{ton_path}'), '-') AS REAL)"
    expr = f"CASE WHEN {gt} > 0 AND {raw} > {gt} * {GT_OVERLOAD_FACTOR} THEN 0 ELSE {raw} END"
    return f"COALESCE({expr}, 0)" if coalesce else expr
