"""Komoditi → vessel-class fallback heuristics.

The primary cargo-by-sector pipeline reads ``('JENIS KAPAL', 'JENIS KAPAL')``
directly from each LK3 row and runs it through ``backend.taxonomy``. This
file is the *fallback*: when a row's vessel-type field is missing or an
audit caller wants to spot-check whether a komoditi looks well-served by
its declared vessel type, we map the komoditi text to the vessel_class
that most plausibly carries it.

Patterns are deliberately broad. Audit-caller responsibility is to surface
``OTHER`` (no pattern matched) so the rules can be tuned.
"""
from __future__ import annotations

import re
from typing import Iterable

from backend.taxonomy import (
    CLS_BULK, CLS_CONTAINER, CLS_GENERAL, CLS_OTHER_CARGO, CLS_TANKER,
    normalize,
)

# (pattern, vessel_class). First match wins; ordered most-specific first.
KOMODITI_RULES: tuple[tuple[re.Pattern, str], ...] = (
    # --- Tanker (Liquid bulk) ---
    (re.compile(r"\bCRUDE\b"),                 CLS_TANKER),
    (re.compile(r"\bMINYAK MENTAH\b"),         CLS_TANKER),
    (re.compile(r"\bGASOLIN(E)?\b"),           CLS_TANKER),
    (re.compile(r"\bDIESEL\b"),                CLS_TANKER),
    (re.compile(r"\bSOLAR\b"),                 CLS_TANKER),
    (re.compile(r"\bPERTAMAX\b"),              CLS_TANKER),
    (re.compile(r"\bPERTALITE\b"),             CLS_TANKER),
    (re.compile(r"\bBENZIN(E)?\b"),            CLS_TANKER),
    (re.compile(r"\bAVTUR\b"),                 CLS_TANKER),
    (re.compile(r"\bJET A\b"),                 CLS_TANKER),
    (re.compile(r"\bJET FUEL\b"),              CLS_TANKER),
    (re.compile(r"\bBBM\b"),                   CLS_TANKER),
    (re.compile(r"\bMINYAK\s+(BUMI|TANAH|MENTAH|MENTAH)\b"), CLS_TANKER),
    (re.compile(r"\bASPHALT\b|\bASPAL\b"),     CLS_TANKER),
    (re.compile(r"\bCHEMICAL\b|\bKIMIA\b"),    CLS_TANKER),
    (re.compile(r"\bMETHANOL\b"),              CLS_TANKER),
    (re.compile(r"\bETHANOL\b"),               CLS_TANKER),
    (re.compile(r"\bACID\b|\bASAM\b"),         CLS_TANKER),
    (re.compile(r"\bAMMONIA\b"),               CLS_TANKER),
    (re.compile(r"\bLPG\b"),                   CLS_TANKER),
    (re.compile(r"\bLNG\b"),                   CLS_TANKER),
    (re.compile(r"\bGAS ALAM\b|\bNATURAL GAS\b"), CLS_TANKER),
    (re.compile(r"\bELPIJI\b"),                CLS_TANKER),
    (re.compile(r"\bCPO\b|\bPALM OIL\b|\bMINYAK SAWIT\b"), CLS_TANKER),
    (re.compile(r"\bPALM KERNEL\b"),           CLS_TANKER),
    # Palm-oil derivatives (RBD = Refined Bleached Deodorized; PKO/CPKO/PKS
    # = palm kernel oil/cake; STEARIN = solid fraction). All ship as liquid
    # bulk → Tanker.
    (re.compile(r"\bRBD\b"),                   CLS_TANKER),
    (re.compile(r"\bOLEIN\b|\bSTEARIN\b"),     CLS_TANKER),
    (re.compile(r"\bPKO\b|\bCPKO\b"),          CLS_TANKER),
    (re.compile(r"\bPKS\b"),                   CLS_TANKER),  # palm kernel shell — biofuel cargo, liquid/dry mixed; Tanker is closer
    (re.compile(r"\bMINYAK NABATI\b|\bVEGETABLE OIL\b"),    CLS_TANKER),
    (re.compile(r"\bFAME\b|\bMETHYL ESTER\b|\bMETIL ESTER\b"), CLS_TANKER),
    (re.compile(r"\bBIODIESEL\b"),             CLS_TANKER),
    (re.compile(r"\bMOLASES\b|\bMOLASSES\b"),  CLS_TANKER),
    (re.compile(r"\bLATEX\b|\bGETAH\b"),       CLS_TANKER),
    (re.compile(r"\bCURAH CAIR\b"),            CLS_TANKER),
    (re.compile(r"\bAIR (BERSIH|TAWAR)\b"),    CLS_TANKER),
    (re.compile(r"\bFUEL OIL\b"),              CLS_TANKER),
    (re.compile(r"\bGASOIL\b|\bGAS OIL\b"),    CLS_TANKER),
    (re.compile(r"\bNAPHTHA\b|\bNAFTA\b"),     CLS_TANKER),
    (re.compile(r"\bKEROSENE\b|\bKEROSEN\b"),  CLS_TANKER),
    (re.compile(r"\bMARINE FUEL\b|\bBUNKER\b"),CLS_TANKER),
    (re.compile(r"\bCNO\b"),                   CLS_TANKER),  # coconut oil
    (re.compile(r"\bKOPRA(H)?\b|\bCOPRA\b"),   CLS_TANKER),  # copra
    (re.compile(r"\bPFAD\b"),                  CLS_TANKER),  # palm fatty acid distillate
    (re.compile(r"\bBIOSOLAR\b"),              CLS_TANKER),
    (re.compile(r"\bPROPYLENE\b|\bETHYLENE\b"),CLS_TANKER),
    (re.compile(r"\bNAPTHA\b"),                CLS_TANKER),  # spelling variant w/o H
    (re.compile(r"\bUNCONVERTED OIL\b|\bUO\b"),CLS_TANKER),
    (re.compile(r"\bAVGAS\b|\bMOGAS\b"),       CLS_TANKER),

    # --- Container ---
    (re.compile(r"\bCONTAINER\b"),             CLS_CONTAINER),
    (re.compile(r"\bPETI\s*KEMAS\b"),          CLS_CONTAINER),
    (re.compile(r"\bPETIKEMAS\b"),             CLS_CONTAINER),

    # --- Bulk (Dry bulk) ---
    (re.compile(r"\bBATU\s*BARA\b|\bBATUBARA\b|\bCOAL\b"),   CLS_BULK),
    (re.compile(r"\bNICKEL\b|\bNIKEL\b"),                    CLS_BULK),
    (re.compile(r"\bBAUXITE\b|\bBAUKSIT\b"),                 CLS_BULK),
    (re.compile(r"\bIRON ORE\b|\bBIJIH BESI\b"),             CLS_BULK),
    (re.compile(r"\bORE\b|\bBIJIH\b"),                       CLS_BULK),
    (re.compile(r"\bCEMENT\b|\bSEMEN\b"),                    CLS_BULK),
    (re.compile(r"\bKLINKER\b|\bCLINKER\b"),                 CLS_BULK),
    (re.compile(r"\bGYPSUM\b|\bGIPSUM\b"),                   CLS_BULK),
    (re.compile(r"\bWHEAT\b|\bGANDUM\b"),                    CLS_BULK),
    (re.compile(r"\bRICE\b|\bBERAS\b|\bPADI\b"),             CLS_BULK),
    (re.compile(r"\bCORN\b|\bJAGUNG\b"),                     CLS_BULK),
    (re.compile(r"\bSOYBEAN\b|\bKEDELAI\b"),                 CLS_BULK),
    (re.compile(r"\bGRAIN\b"),                               CLS_BULK),
    (re.compile(r"\bSUGAR\b|\bGULA\b"),                      CLS_BULK),
    (re.compile(r"\bPUPUK\b|\bFERTILI[SZ]ER\b"),             CLS_BULK),
    (re.compile(r"\bUREA\b"),                                CLS_BULK),
    (re.compile(r"\bSULFUR\b|\bBELERANG\b"),                 CLS_BULK),
    (re.compile(r"\bWOOD CHIP\b|\bSERBUK KAYU\b"),           CLS_BULK),
    (re.compile(r"\bCOKE\b|\bKOKAS\b"),                      CLS_BULK),
    (re.compile(r"\bCURAH KERING\b"),                        CLS_BULK),
    (re.compile(r"\bLIME ?STONES?\b|\bBATU GAMPING\b"),      CLS_BULK),
    (re.compile(r"\bSTONES?\b|\bBATU\b"),                    CLS_BULK),
    (re.compile(r"\bSALT\b|\bGARAM\b"),                      CLS_BULK),
    (re.compile(r"\bCLAY\b|\bTANAH\b|\bLEMPUNG\b"),          CLS_BULK),
    (re.compile(r"\bSAND\b|\bPASIR\b"),                      CLS_BULK),
    (re.compile(r"\bIRON\b|\bSTEEL\b|\bBAJA\b"),             CLS_BULK),
    (re.compile(r"\bCOIL\b"),                                CLS_BULK),  # steel coils
    (re.compile(r"\bCOPPER\b|\bTEMBAGA\b"),                  CLS_BULK),
    (re.compile(r"\bBAUXIT\b"),                              CLS_BULK),  # spelling variant
    (re.compile(r"\bCONCENTRATE\b|\bKONSENTRAT\b"),          CLS_BULK),
    (re.compile(r"\bSLAG\b"),                                CLS_BULK),
    (re.compile(r"\bPULP\b|\bDISSOLVING\b"),                 CLS_BULK),  # paper pulp ships in bulk
    (re.compile(r"\bEUCALYPTUS\b"),                          CLS_BULK),
    (re.compile(r"\bPALAWIJA\b"),                            CLS_BULK),  # secondary food crops

    # --- General Cargo ---
    (re.compile(r"\bGENERAL CARGO\b|\bBARANG UMUM\b"),       CLS_GENERAL),
    (re.compile(r"\bBARANG CAMPURAN\b|\bMIXED\b"),           CLS_GENERAL),
    (re.compile(r"\bBREAKBULK\b|\bBREAK BULK\b"),            CLS_GENERAL),
    (re.compile(r"\bPLYWOOD\b|\bVENEER\b|\bKAYU LAPIS\b"),   CLS_GENERAL),
    (re.compile(r"\bLOG\b|\bKAYU\b|\bTIMBER\b|\bLUMBER\b"),  CLS_GENERAL),
    (re.compile(r"\bPIPE\b|\bPIPA\b"),                       CLS_GENERAL),

    # --- Other Cargo / Vehicles / Equipment ---
    (re.compile(r"\bKENDARAAN\b|\bVEHICLE\b|\bMOBIL\b|\bMOTOR\b"), CLS_OTHER_CARGO),
    (re.compile(r"\bUNIT\b"),                                CLS_OTHER_CARGO),
    (re.compile(r"\bSPARE PARTS?\b|\bEQUIPMENT\b|\bALAT BERAT\b|\bMACHINERY\b|\bMESIN\b"),
                                                              CLS_OTHER_CARGO),
    (re.compile(r"\bMATERIAL\b"),                            CLS_OTHER_CARGO),
)


def classify_komoditi(label: str | None) -> str:
    """Best-effort vessel_class from komoditi text. Returns 'OTHER' on no match."""
    norm = normalize(label)
    if not norm:
        return "OTHER"
    for pat, vclass in KOMODITI_RULES:
        if pat.search(norm):
            return vclass
    return "OTHER"


def coverage_komoditi(labels: Iterable[tuple[str | None, float]]) -> dict:
    """Return ton-weighted komoditi coverage stats.

    ``labels`` is a stream of ``(komoditi, ton)`` pairs. The result has
    total ton, per-class ton, OTHER %, and the OTHER tail (top weights).
    """
    by_class: dict[str, float] = {}
    other: dict[str, float] = {}
    total = 0.0
    for label, ton in labels:
        ton = float(ton or 0)
        total += ton
        cls = classify_komoditi(label)
        by_class[cls] = by_class.get(cls, 0.0) + ton
        if cls == "OTHER":
            key = (label or "").strip() or "(empty)"
            other[key] = other.get(key, 0.0) + ton
    return {
        "total_ton": total,
        "by_class_ton": by_class,
        "other_pct": (by_class.get("OTHER", 0.0) / total * 100.0) if total else 0.0,
        "other_tail": sorted(other.items(), key=lambda kv: -kv[1]),
    }
