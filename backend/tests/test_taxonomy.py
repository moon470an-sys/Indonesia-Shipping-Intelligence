"""Unit tests for backend.taxonomy + backend.cargo_classification.

Run with: ``python -m pytest backend/tests/test_taxonomy.py``.

Tests focus on:
* Idempotency of normalize().
* Determinism + coverage of classify_vessel_type for both label dialects.
* Sanity of classify_tanker_subclass.
* Determinism of classify_komoditi.
* Coverage helpers return well-formed dicts.
"""
from __future__ import annotations

import pytest

from backend.taxonomy import (
    CLS_BULK, CLS_CONTAINER, CLS_FERRY, CLS_FISHING, CLS_GENERAL,
    CLS_NONCOMM, CLS_OTHER_CARGO, CLS_PASSENGER_SHIP, CLS_TANKER,
    CLS_TUG_OSV, CLS_DREDGER_SPECIAL,
    SECTOR_CARGO, SECTOR_FISHING, SECTOR_OFFSHORE, SECTOR_PASSENGER,
    SECTOR_NONCOMM, SECTOR_UNMAPPED,
    classify_many, classify_tanker_subclass, classify_vessel_type,
    coverage, normalize,
)
from backend.cargo_classification import (
    classify_komoditi, coverage_komoditi,
)


# ---------------------------------------------------------------- normalize
@pytest.mark.parametrize("raw,expected", [
    (None, ""),
    ("", ""),
    ("  ", ""),
    ("Tug Boat", "TUG BOAT"),
    ("Oil/Chemical Tanker", "OIL CHEMICAL TANKER"),
    ("KAPAL MOTOR TUNDA (TUG BOAT)", "KAPAL MOTOR TUNDA TUG BOAT"),
    ("RO-RO\tFERRY", "RO RO FERRY"),
    ("BULK CARRIER / CURAH", "BULK CARRIER CURAH"),
])
def test_normalize_basic(raw, expected):
    assert normalize(raw) == expected


def test_normalize_idempotent():
    samples = [
        "Tug Boat", "OIL/CHEMICAL TANKER",
        "KAPAL PENUMPANG TRADISIONAL",
        "  General  Cargo  ", "RO-RO FERRY",
    ]
    for s in samples:
        once = normalize(s)
        assert normalize(once) == once


# ------------------------------------------------- classify_vessel_type — vessels
@pytest.mark.parametrize("label,sector,vclass", [
    # Vessel registry (JenisDetailKet) labels
    ("Tug Boat",                     SECTOR_OFFSHORE,  CLS_TUG_OSV),
    ("Harbour Tug",                  SECTOR_OFFSHORE,  CLS_TUG_OSV),
    ("Anchor Handling Tug Supply",   SECTOR_OFFSHORE,  CLS_TUG_OSV),
    ("Container",                    SECTOR_CARGO,     CLS_CONTAINER),
    ("Bulk Carrier",                 SECTOR_CARGO,     CLS_BULK),
    ("oil tanker",                   SECTOR_CARGO,     CLS_TANKER),
    ("Oil / Chemical Tanker",        SECTOR_CARGO,     CLS_TANKER),
    ("chemical tanker",              SECTOR_CARGO,     CLS_TANKER),
    ("Liquefied Petroleum Gas",      SECTOR_CARGO,     CLS_TANKER),
    ("Liquefied Natural Gas",        SECTOR_CARGO,     CLS_TANKER),
    ("Vegetable Oil Barge",          SECTOR_CARGO,     CLS_TANKER),
    ("oil barge",                    SECTOR_CARGO,     CLS_TANKER),
    ("self propelled oil barge",     SECTOR_CARGO,     CLS_TANKER),
    ("General Cargo",                SECTOR_CARGO,     CLS_GENERAL),
    ("Multi Purpose",                SECTOR_CARGO,     CLS_GENERAL),
    ("Deck Barge",                   SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("Landing Craft Tank",           SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("Ro-ro Cargo",                  SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("Pontoon",                      SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("Fishing Boat",                 SECTOR_FISHING,   CLS_FISHING),
    ("Refrigerated Fish Carrier",    SECTOR_FISHING,   CLS_FISHING),
    ("Live Fish Carrier",            SECTOR_FISHING,   CLS_FISHING),
    ("Passenger",                    SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    ("Traditional Passenger",        SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    ("Cruise",                       SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    ("Cargo Passenger",              SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    ("Passenger Ferry",              SECTOR_PASSENGER, CLS_FERRY),
    ("Ro-ro Ferry",                  SECTOR_PASSENGER, CLS_FERRY),
    ("Car Ferry",                    SECTOR_PASSENGER, CLS_FERRY),
    ("Crew Boat",                    SECTOR_OFFSHORE,  CLS_TUG_OSV),
    ("Cutter Suction Dredger",       SECTOR_OFFSHORE,  CLS_DREDGER_SPECIAL),
    ("Floating Crane Barge",         SECTOR_OFFSHORE,  CLS_DREDGER_SPECIAL),  # CRANE rule precedes BARGE
    ("Patrol Boat",                  SECTOR_NONCOMM,   CLS_NONCOMM),
    ("Yacht",                        SECTOR_NONCOMM,   CLS_NONCOMM),
    ("Pilot Boat",                   SECTOR_NONCOMM,   CLS_NONCOMM),
])
def test_classify_vessels_dialect(label, sector, vclass):
    assert classify_vessel_type(label) == (sector, vclass)


# ------------------------------------------------- classify_vessel_type — LK3
@pytest.mark.parametrize("label,sector,vclass", [
    ("KAPAL MOTOR TUNDA (TUG BOAT)",   SECTOR_OFFSHORE,  CLS_TUG_OSV),
    ("CONTAINER SHIP",                 SECTOR_CARGO,     CLS_CONTAINER),
    ("BULK CARRIER / CURAH",           SECTOR_CARGO,     CLS_BULK),
    ("OIL TANKER / TANGKI MINYAK",     SECTOR_CARGO,     CLS_TANKER),
    ("CHEMICAL TANKER / TANGKI KIMIA", SECTOR_CARGO,     CLS_TANKER),
    ("OIL AND CHEMICAL TANKER",        SECTOR_CARGO,     CLS_TANKER),
    ("LIQUEFIED GAS TANKER - A (LPG)", SECTOR_CARGO,     CLS_TANKER),
    ("LIQUEFIED GAS TANKER - B (LNG)", SECTOR_CARGO,     CLS_TANKER),
    ("VEGETABLE OIL BARGE / TONGKANG MINYAK NABATI", SECTOR_CARGO, CLS_TANKER),
    ("SELF-PROPELLED OIL BARGE (SPOB)",   SECTOR_CARGO,  CLS_TANKER),
    ("GENERAL CARGO",                  SECTOR_CARGO,     CLS_GENERAL),
    ("KAPAL MULTI PURPOSE",            SECTOR_CARGO,     CLS_GENERAL),
    ("MOTORIZED SAILING / LAYAR MOTOR",SECTOR_CARGO,     CLS_GENERAL),
    ("TONGKANG / BARGE",               SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("TONGKANG GELADAK (DECK BARGE)",  SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("KAPAL LANDING CRAFT TANK (LCT)", SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("RO-RO CARGO",                    SECTOR_CARGO,     CLS_OTHER_CARGO),
    ("TONGKANG PENGANGKUT CONTAINER",  SECTOR_CARGO,     CLS_CONTAINER),  # has CONTAINER token first
    ("TONGKANG PENGANGKUT GAS (LPG)",  SECTOR_CARGO,     CLS_TANKER),     # gas carrier rule wins
    ("PASSENGER",                      SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    ("KAPAL PENUMPANG TRADISIONAL",    SECTOR_PASSENGER, CLS_PASSENGER_SHIP),
    ("PASSENGER FERRY",                SECTOR_PASSENGER, CLS_FERRY),
    ("RO-RO FERRY",                    SECTOR_PASSENGER, CLS_FERRY),
    ("RO-RO PENUMPANG DAN BARANG",     SECTOR_PASSENGER, CLS_FERRY),
    ("CAR FERRY",                      SECTOR_PASSENGER, CLS_FERRY),
    ("KAPAL PENGANGKUT IKAN",          SECTOR_FISHING,   CLS_FISHING),
    ("FISHING BOAT",                   SECTOR_FISHING,   CLS_FISHING),
    ("LIVESTOCK CARRIER / TERNAK",     SECTOR_FISHING,   CLS_FISHING),
    ("OFFSHORE/PLATFORM SUPPLY VESSEL",SECTOR_OFFSHORE,  CLS_TUG_OSV),
    ("ANCHOR HANDLING TUG SUPPLY (AHTS)",SECTOR_OFFSHORE,CLS_TUG_OSV),
    ("KAPAL HISAP",                    SECTOR_OFFSHORE,  CLS_DREDGER_SPECIAL),
    ("KAPAL YACHT",                    SECTOR_NONCOMM,   CLS_NONCOMM),
    ("KAPAL WISATA",                   SECTOR_NONCOMM,   CLS_NONCOMM),
])
def test_classify_lk3_dialect(label, sector, vclass):
    assert classify_vessel_type(label) == (sector, vclass)


# ------------------------------------------------- empty / unknown
@pytest.mark.parametrize("label", [None, "", "   ", "ZZZ_UNKNOWN_TYPE_WXY"])
def test_classify_empty_and_unknown(label):
    assert classify_vessel_type(label) == (SECTOR_UNMAPPED, "UNMAPPED")


# ------------------------------------------------- tanker subclass
@pytest.mark.parametrize("label,sub", [
    ("CRUDE OIL TANKER",                "Crude Oil"),
    ("CHEMICAL TANKER",                 "Chemical"),
    ("LIQUEFIED PETROLEUM GAS",         "LPG"),
    ("LIQUEFIED NATURAL GAS",           "LNG"),
    ("LNG CARRIER",                     "LNG"),
    ("VEGETABLE OIL BARGE",             "FAME / Vegetable Oil"),
    ("OIL TANKER",                      "Product"),
    ("OIL AND CHEMICAL TANKER",         "Chemical"),
    ("WATER TANKER",                    "Water"),
    ("ASPHALT TANKER",                  "Product"),
    ("",                                "UNKNOWN"),
])
def test_tanker_subclass(label, sub):
    assert classify_tanker_subclass(label) == sub


# ------------------------------------------------- determinism
def test_determinism():
    label = "OIL AND CHEMICAL TANKER"
    out = {classify_vessel_type(label) for _ in range(20)}
    assert len(out) == 1


# ------------------------------------------------- coverage helper
def test_coverage_returns_well_formed():
    samples = [
        ("Tug Boat", 100), ("Bulk Carrier", 50), ("Container", 200),
        ("UNKNOWN_LABEL", 5), (None, 1),
    ]
    cov = coverage(samples)
    assert cov["total"] == 356
    assert cov["by_sector"][SECTOR_CARGO] == 250
    assert cov["by_sector"][SECTOR_OFFSHORE] == 100
    assert cov["by_sector"][SECTOR_UNMAPPED] == 6
    assert 0 < cov["unmapped_pct"] < 5  # 6/356 ~ 1.7%
    # Tail is sorted by weight desc
    assert cov["unmapped_tail"][0][0].upper() == "UNKNOWN_LABEL"


def test_classify_many_matches_singletons():
    labels = ["Tug Boat", "Bulk Carrier", "Fishing Boat"]
    expected = [classify_vessel_type(l) for l in labels]
    assert classify_many(labels) == expected


# ------------------------------------------------- komoditi fallback
@pytest.mark.parametrize("label,vclass", [
    ("BATU BARA",                CLS_BULK),
    ("BATUBARA",                 CLS_BULK),
    ("COAL",                     CLS_BULK),
    ("NICKEL ORE",               CLS_BULK),
    ("BIJIH BESI",               CLS_BULK),
    ("BAUKSIT",                  CLS_BULK),
    ("CEMENT BAG",               CLS_BULK),
    ("URE A FERTILIZER",         CLS_BULK),
    ("BERAS",                    CLS_BULK),
    ("WHEAT FLOUR",              CLS_BULK),
    ("CRUDE OIL",                CLS_TANKER),
    ("CPO",                      CLS_TANKER),
    ("PALM OIL",                 CLS_TANKER),
    ("LPG",                      CLS_TANKER),
    ("LNG",                      CLS_TANKER),
    ("MINYAK NABATI",            CLS_TANKER),
    ("BBM",                      CLS_TANKER),
    ("ASPAL",                    CLS_TANKER),
    ("CHEMICAL LIQUID",          CLS_TANKER),
    ("CONTAINER 20",             CLS_CONTAINER),
    ("PETIKEMAS 40",             CLS_CONTAINER),
    ("PETI KEMAS",               CLS_CONTAINER),
    ("BARANG UMUM",              CLS_GENERAL),
    ("GENERAL CARGO",            CLS_GENERAL),
    ("BREAKBULK",                CLS_GENERAL),
    ("KENDARAAN",                CLS_OTHER_CARGO),
    ("VEHICLE UNITS",            CLS_OTHER_CARGO),
    ("UNKNOWN_KOMODITI",         "OTHER"),
    ("",                         "OTHER"),
    (None,                       "OTHER"),
])
def test_komoditi_classification(label, vclass):
    assert classify_komoditi(label) == vclass


def test_komoditi_coverage_aggregates():
    samples = [
        ("BATU BARA", 1000), ("CONTAINER", 500), ("CPO", 700),
        ("UNKNOWN_X", 50), (None, 10),
    ]
    cov = coverage_komoditi(samples)
    assert cov["total_ton"] == 2260
    assert cov["by_class_ton"][CLS_BULK] == 1000
    assert cov["by_class_ton"][CLS_CONTAINER] == 500
    assert cov["by_class_ton"][CLS_TANKER] == 700
    assert cov["by_class_ton"]["OTHER"] == 60
    assert 0 < cov["other_pct"] < 5
