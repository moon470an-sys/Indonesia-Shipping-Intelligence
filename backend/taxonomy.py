"""Vessel-type taxonomy.

Classifies vessel-type labels into a 3-tier taxonomy:

    Tier 1 (sector)        Tier 2 (vessel_class)
    --------------------------------------------------
    PASSENGER              Passenger Ship | Ferry
    CARGO                  Container | Bulk Carrier | Tanker | General Cargo | Other Cargo
    FISHING                Fishing Vessel
    OFFSHORE_SUPPORT       Tug/OSV/AHTS | Dredger/Special
    NON_COMMERCIAL         Government/Navy/Other

Two label dialects are seen in the project:

* ``vessels_snapshot.raw_data['JenisDetailKet']`` — short English label
  ("Tug Boat", "Bulk Carrier", "Fishing Boat", ~100 distinct values).
* ``cargo_snapshot.raw_row['JENIS KAPAL']`` — long Indonesian/English label
  ("KAPAL MOTOR TUNDA (TUG BOAT)", "TONGKANG / BARGE", ~60+ distinct values).

Both label sets resolve to the same taxonomy via ordered keyword rules.
The first matching rule wins; rules are ordered so more specific patterns
(e.g. "fish carrier") sit above broader ones (e.g. "cargo").

Tanker subclasses (Crude / Product / Chemical / LPG / LNG / FAME) are
inferred separately by `classify_tanker_subclass`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# ---------- canonical sector / vessel_class labels ----------
SECTOR_PASSENGER = "PASSENGER"
SECTOR_CARGO = "CARGO"
SECTOR_FISHING = "FISHING"
SECTOR_OFFSHORE = "OFFSHORE_SUPPORT"
SECTOR_NONCOMM = "NON_COMMERCIAL"
SECTOR_UNMAPPED = "UNMAPPED"

# vessel_class values — kept stable for downstream consumers.
CLS_PASSENGER_SHIP = "Passenger Ship"
CLS_FERRY = "Ferry"
CLS_CONTAINER = "Container"
CLS_BULK = "Bulk Carrier"
CLS_TANKER = "Tanker"
CLS_GENERAL = "General Cargo"
CLS_OTHER_CARGO = "Other Cargo"
CLS_FISHING = "Fishing Vessel"
CLS_TUG_OSV = "Tug/OSV/AHTS"
CLS_DREDGER_SPECIAL = "Dredger/Special"
CLS_NONCOMM = "Government/Navy/Other"
CLS_UNMAPPED = "UNMAPPED"

# Stable color palette per sector for the dashboard.
SECTOR_PALETTE = {
    SECTOR_PASSENGER: "#0d9488",   # teal
    SECTOR_CARGO:     "#1e3a8a",   # navy
    SECTOR_FISHING:   "#d97706",   # amber
    SECTOR_OFFSHORE:  "#475569",   # slate
    SECTOR_NONCOMM:   "#6b7280",   # gray
    SECTOR_UNMAPPED:  "#dc2626",   # red — visible audit signal
}

ALL_SECTORS = (
    SECTOR_PASSENGER, SECTOR_CARGO, SECTOR_FISHING,
    SECTOR_OFFSHORE, SECTOR_NONCOMM,
)
ALL_CLASSES = (
    CLS_PASSENGER_SHIP, CLS_FERRY,
    CLS_CONTAINER, CLS_BULK, CLS_TANKER, CLS_GENERAL, CLS_OTHER_CARGO,
    CLS_FISHING,
    CLS_TUG_OSV, CLS_DREDGER_SPECIAL,
    CLS_NONCOMM,
)


# ---------- normalization ----------
_WS = re.compile(r"\s+")
_PUNCT_TO_SPACE = re.compile(r"[/\\\-_().,]+")


def normalize(s: str | None) -> str:
    """Uppercase + strip + collapse whitespace + soften punctuation.

    Punctuation that varies between dialects (slashes, parentheses,
    hyphens) is replaced with a single space so contains-checks work
    regardless of formatting.
    """
    if not s:
        return ""
    out = _PUNCT_TO_SPACE.sub(" ", str(s).upper())
    out = _WS.sub(" ", out).strip()
    return out


# ---------- rule table ----------
# Each rule: (keyword pattern, sector, vessel_class).
# Patterns are matched against the *normalized* label via substring or word
# boundary regex. First match wins — order matters.
@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern
    sector: str
    vessel_class: str
    note: str = ""


def _kw(p: str) -> re.Pattern:
    """Compile a whitespace-tolerant keyword regex (case already normalized)."""
    return re.compile(rf"(?:^|\s){re.escape(p.upper())}(?:\s|$)")


def _contains(p: str) -> re.Pattern:
    """Compile a substring regex (no word boundary)."""
    return re.compile(re.escape(p.upper()))


# Rules are ordered most-specific first. Comments tag which dialect each rule
# is meant to capture (V = vessels JenisDetailKet, L = LK3 JENIS KAPAL).
RULES: tuple[Rule, ...] = (
    # --- FISHING (specific carriers / boats) ---
    Rule(_contains("FISH CARRIER"),                     SECTOR_FISHING, CLS_FISHING),  # V
    Rule(_contains("LIVE FISH CARRIER"),                SECTOR_FISHING, CLS_FISHING),  # V
    Rule(_contains("REFRIGERATED FISH"),                SECTOR_FISHING, CLS_FISHING),  # V
    Rule(_contains("FISH REEFER"),                      SECTOR_FISHING, CLS_FISHING),  # L
    Rule(_contains("FISHERY"),                          SECTOR_FISHING, CLS_FISHING),  # V
    Rule(_contains("PENGANGKUT IKAN"),                  SECTOR_FISHING, CLS_FISHING),  # L
    Rule(_contains("KAPAL IKAN"),                       SECTOR_FISHING, CLS_FISHING),  # L
    Rule(_contains("FISHING"),                          SECTOR_FISHING, CLS_FISHING),  # V/L
    Rule(_contains("PURSE SEINER"),                     SECTOR_FISHING, CLS_FISHING),
    Rule(_contains("LIVESTOCK"),                        SECTOR_FISHING, CLS_FISHING),  # V/L (livestock vessels grouped here)
    Rule(_contains("TERNAK"),                           SECTOR_FISHING, CLS_FISHING),  # L

    # --- OFFSHORE / SUPPORT (Tug / OSV / AHTS) ---
    Rule(_contains("AHTS"),                             SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("ANCHOR HANDLING"),                  SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("PLATFORM SUPPLY"),                  SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("OFFSHORE PLATFORM"),                SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("PSV"),                              SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("SUPPLY"),                           SECTOR_OFFSHORE, CLS_TUG_OSV),  # V — broad, sits below specific
    Rule(_contains("TUG BOAT"),                         SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("HARBOUR TUG"),                      SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("PUSHER TUG"),                       SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("PUSHER BOAT"),                      SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("MOTOR TUNDA"),                      SECTOR_OFFSHORE, CLS_TUG_OSV),  # L
    Rule(_kw("TUG"),                                    SECTOR_OFFSHORE, CLS_TUG_OSV),
    Rule(_contains("CREW BOAT"),                        SECTOR_OFFSHORE, CLS_TUG_OSV),

    # --- OFFSHORE / SUPPORT (Dredger / Special) ---
    Rule(_contains("DREDGER"),                          SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("DREDGING"),                         SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("HOPPER"),                           SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("SUCTION"),                          SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("CRANE"),                            SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("CABLE LAYING"),                     SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("PIPE LAYING"),                      SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("SEISMIC"),                          SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("RESEARCH"),                         SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("FLOATING STORAGE"),                 SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),
    Rule(_contains("KAPAL HISAP"),                      SECTOR_OFFSHORE, CLS_DREDGER_SPECIAL),

    # --- CARGO (Tanker — comes BEFORE container/bulk because some tanker
    # labels also contain "barge" or "cargo" tokens) ---
    Rule(_contains("OIL TANKER"),                       SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("CHEMICAL TANKER"),                  SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("OIL AND CHEMICAL"),                 SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("OIL CHEMICAL"),                     SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("ASPHALT TANKER"),                   SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("WATER TANKER"),                     SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("LIQUEFIED PETROLEUM"),              SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("LIQUEFIED NATURAL"),                SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("LIQUEFIED GAS TANKER"),             SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("GAS CARRIER"),                      SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("PENGANGKUT GAS"),                   SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("VEGETABLE OIL"),                    SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("MINYAK NABATI"),                    SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("OIL BARGE"),                        SECTOR_CARGO, CLS_TANKER),  # V/L
    Rule(_contains("CHEMICAL BARGE"),                   SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("OIL AND CHEMICAL BARGE"),           SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("SPOB"),                             SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("SELF PROPELLED OIL"),               SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("TANGKI MINYAK"),                    SECTOR_CARGO, CLS_TANKER),
    Rule(_contains("TANGKI KIMIA"),                     SECTOR_CARGO, CLS_TANKER),
    Rule(_kw("TANKER"),                                 SECTOR_CARGO, CLS_TANKER),

    # --- CARGO (Container) ---
    Rule(_contains("CONTAINER SHIP"),                   SECTOR_CARGO, CLS_CONTAINER),
    Rule(_contains("PETI KEMAS"),                       SECTOR_CARGO, CLS_CONTAINER),
    Rule(_contains("PETIKEMAS"),                        SECTOR_CARGO, CLS_CONTAINER),
    Rule(_contains("PENGANGKUT CONTAINER"),             SECTOR_CARGO, CLS_CONTAINER),
    Rule(_kw("CONTAINER"),                              SECTOR_CARGO, CLS_CONTAINER),

    # --- CARGO (Bulk) ---
    Rule(_contains("BULK CARRIER"),                     SECTOR_CARGO, CLS_BULK),
    Rule(_contains("CEMENT CARRIER"),                   SECTOR_CARGO, CLS_BULK),
    Rule(_contains("WOOD CHIP"),                        SECTOR_CARGO, CLS_BULK),
    Rule(_contains("OBO"),                              SECTOR_CARGO, CLS_BULK),
    Rule(_kw("CURAH"),                                  SECTOR_CARGO, CLS_BULK),
    Rule(_contains("CAR CARRIER"),                      SECTOR_CARGO, CLS_BULK),  # PCC = Pure Car Carrier; treat as bulk-like specialist

    # --- CARGO (General / Multi-purpose) ---
    Rule(_contains("GENERAL CARGO"),                    SECTOR_CARGO, CLS_GENERAL),
    Rule(_contains("MULTI PURPOSE"),                    SECTOR_CARGO, CLS_GENERAL),
    Rule(_contains("MULTIPURPOSE"),                     SECTOR_CARGO, CLS_GENERAL),
    Rule(_contains("MOTORIZED SAILING"),                SECTOR_CARGO, CLS_GENERAL),
    Rule(_contains("LAYAR MOTOR"),                      SECTOR_CARGO, CLS_GENERAL),

    # --- CARGO (Ro-ro cargo — must precede the broad "RO RO" passenger-ferry rule) ---
    Rule(_contains("RO RO CARGO FERRY"),                SECTOR_CARGO,     CLS_OTHER_CARGO),
    Rule(_contains("RO RO CARGO"),                      SECTOR_CARGO,     CLS_OTHER_CARGO),

    # --- PASSENGER (Ferry — first because "passenger ferry" should be Ferry, not Passenger Ship) ---
    Rule(_contains("ROLL ON ROLL OFF"),                 SECTOR_PASSENGER, CLS_FERRY),
    Rule(_contains("ROLL ON"),                          SECTOR_PASSENGER, CLS_FERRY),
    Rule(_contains("RO RO FERRY"),                      SECTOR_PASSENGER, CLS_FERRY),
    Rule(_contains("CAR FERRY"),                        SECTOR_PASSENGER, CLS_FERRY),
    Rule(_contains("PASSENGER FERRY"),                  SECTOR_PASSENGER, CLS_FERRY),
    Rule(_contains("RO RO PENUMPANG"),                  SECTOR_PASSENGER, CLS_FERRY),
    Rule(_contains("PASSENGER RO RO"),                  SECTOR_PASSENGER, CLS_FERRY),
    Rule(_contains("RO RO"),                            SECTOR_PASSENGER, CLS_FERRY),  # catch-all
    Rule(_kw("FERRY"),                                  SECTOR_PASSENGER, CLS_FERRY),
    Rule(_kw("KAPAL CEPAT"),                            SECTOR_PASSENGER, CLS_FERRY),

    # --- PASSENGER (Passenger Ship — incl. cruise + traditional) ---
    Rule(_contains("CARGO PASSENGER"),                  SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_contains("PASSENGER HSC"),                    SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_contains("CRUISE"),                           SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_contains("KAPAL PENUMPANG"),                  SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_contains("TRADITIONAL PASSENGER"),            SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_contains("WATER BUS"),                        SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_contains("CATAMARAN"),                        SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_kw("PASSENGER"),                              SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    Rule(_kw("PENUMPANG"),                              SECTOR_PASSENGER, CLS_PASSENGER_SHIP),

    # --- CARGO (Other Cargo: barges, LCT, pontoons, ro-ro cargo) ---
    Rule(_contains("RO RO CARGO"),                      SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("LANDING CRAFT"),                    SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_kw("LCT"),                                    SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("DECK BARGE"),                       SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("WORK BARGE"),                       SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("WORK BOAT"),                        SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("ACCOMMODATION"),                    SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("FLOATING CRANE"),                   SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("SELF PROPELLED BARGE"),             SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_kw("SPB"),                                    SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("TONGKANG"),                         SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_kw("BARGE"),                                  SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_kw("PONTOON"),                                SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_kw("PERAMBUAN"),                              SECTOR_CARGO, CLS_OTHER_CARGO),
    Rule(_contains("UTILITY"),                          SECTOR_CARGO, CLS_OTHER_CARGO),

    # --- NON-COMMERCIAL ---
    Rule(_contains("PATROL"),                           SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("PATROLI"),                          SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("KAPAL PERANG"),                     SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_kw("NAVY"),                                   SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_kw("MILITARY"),                               SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_kw("YACHT"),                                  SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_kw("RECREATIONAL"),                           SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_kw("WISATA"),                                 SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("PILOT BOAT"),                       SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("MOORING BOAT"),                     SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("MEDICAL"),                          SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("AMBULANCE"),                        SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("RESCUE"),                           SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("KAPAL BANK"),                       SECTOR_NONCOMM, CLS_NONCOMM),
    Rule(_contains("HIGH SPEED OUTBOARD"),              SECTOR_NONCOMM, CLS_NONCOMM),

    # --- Generic CARGO fallback (must be last cargo rule) ---
    Rule(_kw("CARGO"),                                  SECTOR_CARGO, CLS_OTHER_CARGO),
)


# ---------- Tanker subclass (R2 detail) ----------
TANKER_SUBCLASS_RULES: tuple[tuple[re.Pattern, str], ...] = (
    (_contains("CRUDE"),                "Crude Oil"),
    (_contains("LIQUEFIED NATURAL"),    "LNG"),
    (_contains("LNG"),                  "LNG"),
    (_contains("LIQUEFIED PETROLEUM"),  "LPG"),
    (_contains("LPG"),                  "LPG"),
    (_contains("VEGETABLE OIL"),        "FAME / Vegetable Oil"),
    (_contains("MINYAK NABATI"),        "FAME / Vegetable Oil"),
    (_contains("FAME"),                 "FAME / Vegetable Oil"),
    (_contains("BIODIESEL"),            "FAME / Vegetable Oil"),
    (_contains("CHEMICAL"),             "Chemical"),
    (_contains("KIMIA"),                "Chemical"),
    (_contains("ASPHALT"),              "Product"),
    (_contains("WATER TANKER"),         "Water"),
    (_contains("OIL"),                  "Product"),
    (_contains("MINYAK"),               "Product"),
    (_contains("GAS"),                  "LPG"),  # generic gas-carrier fallback
)


def classify_vessel_type(label: str | None) -> tuple[str, str]:
    """Classify a single vessel-type label.

    Returns ``(sector, vessel_class)``. Both are ``UNMAPPED`` if no rule
    matched. Empty / null inputs return ``UNMAPPED`` quietly.
    """
    norm = normalize(label)
    if not norm:
        return SECTOR_UNMAPPED, CLS_UNMAPPED
    for rule in RULES:
        if rule.pattern.search(norm):
            return rule.sector, rule.vessel_class
    return SECTOR_UNMAPPED, CLS_UNMAPPED


def classify_tanker_subclass(label: str | None) -> str:
    """Best-effort tanker subclass label.

    Returns one of: ``Crude Oil``, ``Product``, ``Chemical``, ``LPG``,
    ``LNG``, ``FAME / Vegetable Oil``, ``Water``, or ``UNKNOWN``. Caller
    is expected to gate on ``classify_vessel_type(...) == (CARGO, Tanker)``
    before invoking.
    """
    norm = normalize(label)
    if not norm:
        return "UNKNOWN"
    for pat, sub in TANKER_SUBCLASS_RULES:
        if pat.search(norm):
            return sub
    return "UNKNOWN"


# ---------- Convenience helpers ----------

def classify_many(labels: Iterable[str | None]) -> list[tuple[str, str]]:
    """Vectorized classify_vessel_type."""
    return [classify_vessel_type(l) for l in labels]


def coverage(labels: Iterable[tuple[str | None, int]]) -> dict:
    """Compute coverage stats for a stream of (label, weight) pairs.

    Weight can be row count or tonnage. Returns a dict with totals,
    per-sector counts, and the unmapped tail (sorted by weight desc).
    """
    sector_w: dict[str, float] = {s: 0.0 for s in (*ALL_SECTORS, SECTOR_UNMAPPED)}
    class_w: dict[str, float] = {}
    unmapped: dict[str, float] = {}
    total = 0.0
    for label, w in labels:
        w = float(w or 0)
        total += w
        sector, vclass = classify_vessel_type(label)
        sector_w[sector] = sector_w.get(sector, 0.0) + w
        class_w[vclass] = class_w.get(vclass, 0.0) + w
        if sector == SECTOR_UNMAPPED:
            key = (label or "").strip() or "(empty)"
            unmapped[key] = unmapped.get(key, 0.0) + w
    return {
        "total": total,
        "by_sector": sector_w,
        "by_class": class_w,
        "unmapped_pct": (sector_w[SECTOR_UNMAPPED] / total * 100.0) if total else 0.0,
        "unmapped_tail": sorted(unmapped.items(), key=lambda kv: -kv[1]),
    }
