"""Cargo scope filter — 4-class scope assignment for the Cargo×Fleet site.

Maps every vessel / cargo-row to one of:
    cargo        — commercial cargo ship (main charts include)
    auxiliary    — Tug/Tugboat (main charts include, separate "Cargo 보조선" label)
    excluded     — passenger, fishing, patrol, yacht, dredger, OSV (main charts hide)
    unclassified — taxonomy UNMAPPED with no LK3 cargo activity

Authoritative spec: docs/cargo_scope_definition.md. Update both files together.

The function ``cargo_scope`` takes the result of
``backend.taxonomy.classify_vessel_type`` plus the raw label and optional
LK3 ton activity, and returns a (scope, ui_class) tuple.
"""
from __future__ import annotations

import re

from backend.taxonomy import (
    CLS_BULK, CLS_CONTAINER, CLS_DREDGER_SPECIAL, CLS_FERRY, CLS_FISHING,
    CLS_GENERAL, CLS_NONCOMM, CLS_OTHER_CARGO, CLS_PASSENGER_SHIP,
    CLS_TANKER, CLS_TUG_OSV, CLS_UNMAPPED, SECTOR_CARGO, SECTOR_FISHING,
    SECTOR_NONCOMM, SECTOR_OFFSHORE, SECTOR_PASSENGER, SECTOR_UNMAPPED,
    classify_vessel_type, normalize,
)

# Scope literals
SCOPE_CARGO = "cargo"
SCOPE_AUXILIARY = "auxiliary"
SCOPE_EXCLUDED = "excluded"
SCOPE_UNCLASSIFIED = "unclassified"

ALL_SCOPES = (SCOPE_CARGO, SCOPE_AUXILIARY, SCOPE_EXCLUDED, SCOPE_UNCLASSIFIED)

# UI labels (Korean) — used by chart legends and Explorer rows.
SCOPE_LABEL = {
    SCOPE_CARGO:        "화물선",
    SCOPE_AUXILIARY:    "Cargo 보조선 (Tug)",
    SCOPE_EXCLUDED:     "제외",
    SCOPE_UNCLASSIFIED: "분류 미정",
}

# Stable palette per scope. Cargo uses the existing sector navy; auxiliary
# is a distinct slate (mid-tone so it reads as supportive, not primary).
SCOPE_PALETTE = {
    SCOPE_CARGO:        "#1e3a8a",   # navy (same as SECTOR_CARGO)
    SCOPE_AUXILIARY:    "#64748b",   # slate-500 — clearly auxiliary
    SCOPE_EXCLUDED:     "#cbd5e1",   # slate-300 — washed-out (Explorer only)
    SCOPE_UNCLASSIFIED: "#dc2626",   # red — audit signal
}

# UI-facing vessel_class for cargo + auxiliary scopes. Anything in
# scope=cargo keeps its original vessel_class; scope=auxiliary collapses
# to a single "Cargo 보조선 (Tug)" label so the legend stays small.
AUXILIARY_UI_CLASS = "Cargo 보조선 (Tug)"

# All cargo vessel_class labels (UI side — Tug is auxiliary, not cargo).
CARGO_UI_CLASSES = (
    CLS_CONTAINER, CLS_BULK, CLS_TANKER, CLS_GENERAL, CLS_OTHER_CARGO,
)


# ---------- raw-label sub-classifier for OFFSHORE_SUPPORT ----------
# The taxonomy collapses Tug + AHTS + PSV + Supply + Crew Boat into
# vessel_class=Tug/OSV/AHTS. For cargo scope we split:
#   Tug / Tunda / Pusher  →  auxiliary
#   AHTS / PSV / Supply / Crew Boat / Anchor Handling  →  excluded
_TUG_PATTERNS = (
    "TUG BOAT", "HARBOUR TUG", "PUSHER TUG", "PUSHER BOAT",
    "MOTOR TUNDA", "TUGBOAT",
)
_TUG_KW = re.compile(r"(?:^|\s)TUG(?:\s|$)")
_TUNDA_KW = re.compile(r"(?:^|\s)TUNDA(?:\s|$)")
_OSV_PATTERNS = (
    "AHTS", "ANCHOR HANDLING", "PLATFORM SUPPLY",
    "OFFSHORE PLATFORM", "PSV", "SUPPLY", "CREW BOAT",
)


def _is_tug_label(norm_label: str) -> bool:
    """True iff a normalized JenisDetailKet / JENIS KAPAL string names a Tug."""
    if not norm_label:
        return False
    for p in _TUG_PATTERNS:
        if p in norm_label:
            return True
    if _TUG_KW.search(norm_label) or _TUNDA_KW.search(norm_label):
        return True
    return False


def _is_osv_label(norm_label: str) -> bool:
    """True iff a normalized label names an OSV (AHTS/PSV/Supply/Crew Boat)."""
    if not norm_label:
        return False
    return any(p in norm_label for p in _OSV_PATTERNS)


# ---------- main classifier ----------

def cargo_scope(
    label: str | None,
    *,
    sector: str | None = None,
    vessel_class: str | None = None,
    lk3_ton: float = 0.0,
) -> tuple[str, str]:
    """Return ``(scope, ui_class)`` for a vessel-type label.

    Parameters
    ----------
    label : str | None
        Raw label — ``JenisDetailKet`` (vessels) or ``JENIS KAPAL`` (LK3).
    sector, vessel_class : str | None
        Optional pre-computed taxonomy result. When omitted, the label
        is classified on the fly via ``backend.taxonomy.classify_vessel_type``.
    lk3_ton : float
        Sum of LK3 cargo activity (Bongkar + Muat) for the vessel. Used to
        promote ``UNMAPPED`` rows that actually carry cargo to ``cargo``.

    Returns
    -------
    (scope, ui_class)
        ``scope`` ∈ {cargo, auxiliary, excluded, unclassified}.
        ``ui_class`` is the legend-facing class — collapsed to
        ``"Cargo 보조선 (Tug)"`` for auxiliary, original vessel_class
        for cargo, original vessel_class for excluded / unclassified
        (callers usually drop them anyway).
    """
    if sector is None or vessel_class is None:
        sector, vessel_class = classify_vessel_type(label)
    norm = normalize(label)

    # 1) FISHING + Livestock → cargo override (spec §scope=cargo)
    #    Livestock carriers are cargo per the site scope, even though
    #    the taxonomy buckets them under FISHING (legacy grouping with
    #    fish carriers because both ship live animals).
    if sector == SECTOR_FISHING and ("LIVESTOCK" in norm or "TERNAK" in norm):
        return SCOPE_CARGO, CLS_OTHER_CARGO

    # 2) CARGO sector → cargo
    if sector == SECTOR_CARGO and vessel_class in CARGO_UI_CLASSES:
        return SCOPE_CARGO, vessel_class

    # 3) OFFSHORE_SUPPORT → split by raw label
    if sector == SECTOR_OFFSHORE:
        if vessel_class == CLS_DREDGER_SPECIAL:
            return SCOPE_EXCLUDED, CLS_DREDGER_SPECIAL
        # Tug/OSV/AHTS — disambiguate via label
        if _is_tug_label(norm):
            return SCOPE_AUXILIARY, AUXILIARY_UI_CLASS
        if _is_osv_label(norm):
            return SCOPE_EXCLUDED, CLS_TUG_OSV
        # Ambiguous OFFSHORE_SUPPORT label that did not hit any pattern.
        # Default to excluded (conservative — only confirmed tugs are
        # surfaced in main charts).
        return SCOPE_EXCLUDED, CLS_TUG_OSV

    # 4) PASSENGER / NON_COMMERCIAL → excluded
    if sector == SECTOR_PASSENGER:
        return SCOPE_EXCLUDED, vessel_class or CLS_PASSENGER_SHIP
    if sector == SECTOR_NONCOMM:
        return SCOPE_EXCLUDED, vessel_class or CLS_NONCOMM

    # 5) FISHING (non-livestock) → excluded
    if sector == SECTOR_FISHING:
        return SCOPE_EXCLUDED, vessel_class or CLS_FISHING

    # 6) UNMAPPED + has LK3 activity → promote to cargo (Other Cargo)
    if sector == SECTOR_UNMAPPED:
        if lk3_ton and lk3_ton > 0:
            return SCOPE_CARGO, CLS_OTHER_CARGO
        return SCOPE_UNCLASSIFIED, CLS_UNMAPPED

    # 7) Fallback — sector mapped but unknown class. Treat as unclassified
    #    so it's surfaced in the audit, not silently hidden.
    return SCOPE_UNCLASSIFIED, vessel_class or CLS_UNMAPPED


def scope_counts(rows):
    """Aggregate ``(scope, ui_class, count)`` from an iterable of
    ``(label, sector, vessel_class, lk3_ton)`` tuples. Returns a dict
    suitable for the meta-strip ("화물선 n / 보조선 k / 제외 m") shown
    above each tab."""
    out = {s: 0 for s in ALL_SCOPES}
    for label, sec, vc, ton in rows:
        scope, _ = cargo_scope(label, sector=sec, vessel_class=vc, lk3_ton=ton or 0.0)
        out[scope] += 1
    return out
