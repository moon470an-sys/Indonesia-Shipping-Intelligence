"""Unified commodity taxonomy — single source of truth.

Two tiers:

* **Tier-1 buckets** (~40, granular) — surfaced by cv-app (Demand 탭의
  항만별 물동량 인포그래픽 commodity 필터). Examples: ``CPO``,
  ``PERTALITE``, ``LPG``, ``BATU BARA``, ``NICKEL ORE``.
* **Tier-2 categories** (~17, aggregated) — surfaced by the cat-details
  panel and the timeseries stacked bar chart. Examples: ``Palm Oil``,
  ``Petroleum Product``, ``Coal``, ``Mineral Ore``.

Every Tier-1 bucket maps to exactly one Tier-2 category, so the sum of
the buckets that map to a category equals the category total.
Consumers can therefore reconcile cv-app commodity totals with
cat-details category totals down to the ton.

Classification is purely from the KOMODITI text (BONGKAR + MUAT). The
prior vessel-type-based bucketing (which placed CPO under "Product" or
"Chemical" depending on tanker subclass) is no longer used for cargo
category derivations.
"""
from __future__ import annotations

import re
from typing import Iterable

# ---------------------------------------------------------------------------
# Tier-1: granular commodity buckets.
# Order matters — first match wins. More specific patterns must come first.
# Each entry: (bucket_name, (keyword, ...)).
# Keywords are matched case-insensitively as substrings of the uppercase
# KOMODITI text. Spaces inside a keyword count; "BATU BARA" matches
# "MUAT BATU BARA" but not "BATUBARA" (separate keyword).
# ---------------------------------------------------------------------------
COMMODITY_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # --- Crude / condensate -------------------------------------------------
    # NOTE: "CRUDE PALM OIL" contains "CRUDE" but NOT "CRUDE OIL" (PALM in
    # between), so the palm-oil branch below catches it first via "PALM OIL".
    # We still keep "CRUDE OIL" + "CRUDE OIL IN BULK" early because crude
    # cargoes commonly use those exact tokens.
    ("CRUDE OIL",            ("CRUDE OIL", "MINYAK MENTAH", "CRUDE OIL IN BULK")),
    ("OMAN BLEND CRUDE OIL", ("OMAN BLEND",)),
    ("CONDENSATE",           ("CONDENSATE", "NAPHTHA", "NAFTA", "NAPTHA")),
    # --- Palm-oil family (BEFORE the refined-product branch so CRUDE PALM
    #     OIL etc. never falls into a generic "OIL" bucket) -----------------
    ("RBD PALM OLEIN",       ("RBD PALM OLEIN", "RBD OLEIN")),
    ("RBD PALM OIL",         ("RBD PALM OIL", "RBD OIL")),
    ("PFAD",                 ("PFAD", "PALM FATTY ACID")),
    ("PKO/CPKO",             ("CPKO", "PALM KERNEL OIL", "PKO")),
    ("STEARIN",              ("STEARIN",)),
    ("OLEIN",                ("OLEIN",)),
    ("PALM KERNEL",          ("PALM KERNEL", "CANGKANG", "BIJI SAWIT",
                                "TANDAN KOSONG", "KERNEL SHELL")),
    ("CPO",                  ("CPO", "CRUDE PALM OIL", "PALM OIL", "MINYAK SAWIT")),
    # --- Biodiesel ----------------------------------------------------------
    ("FAME",                 ("FAME", "BIODIESEL", "METIL ESTER", "METHYL ESTER")),
    # --- Other vegetable oils ----------------------------------------------
    ("COCONUT OIL",          ("CNO", "COCONUT OIL", "KOPRA", "COPRA")),
    # --- Refined petroleum products ----------------------------------------
    ("PERTALITE",            ("PERTALITE",)),
    ("PERTAMAX",             ("PERTAMAX", "PERTADEX")),
    ("AVTUR",                ("AVTUR", "JET A", "JET FUEL")),
    ("HSD",                  ("HSD", "HIGH SPEED DIESEL")),
    ("SOLAR",                ("BIO SOLAR", "BIOSOLAR", "SOLAR")),
    ("MFO/HSFO",             ("MFO", "HSFO", "FUEL OIL", "MARINE FUEL")),
    ("KEROSENE",             ("KEROSENE", "KEROSEN", "MINYAK TANAH")),
    ("ASPAL/BITUMEN",        ("ASPAL", "BITUMEN", "ASPHALT")),
    ("BBM (기타)",            ("BBM", "BUCO", "GASOLINE", "PREMIUM", "MOGAS", "AVGAS")),
    # --- Gases --------------------------------------------------------------
    ("LPG",                  ("LPG", "ELPIJI", "LIQUEFIED PETROLEUM",
                                "PROPANE", "BUTANE", "PROPYLENE", "ETHYLENE")),
    ("LNG",                  ("LNG", "LIQUEFIED NATURAL", "NATURAL GAS",
                                "LIQUIFEID NATURAL", "LIQUID NATURAL")),
    # --- Chemicals ----------------------------------------------------------
    ("METHANOL",             ("METHANOL",)),
    ("AMMONIA",              ("AMMONIA", "AMONIA")),
    ("SULFUR",               ("SULFUR", "BELERANG", "SULPHUR")),
    ("CHEMICAL (기타)",       ("CHEMICAL", "KIMIA", "ACID", "ASAM",
                                "ETHANOL", "CAUSTIC", "LATEX")),
    # --- Dry bulk ----------------------------------------------------------
    ("BATU BARA",            ("BATU BARA", "BATUBARA", "STEAM COAL", "COAL",
                                "BARU BARA", "BATU  BARA", "COKE", "KOKAS")),
    ("NICKEL ORE",           ("NICKEL", "NICKLE", "NIKEL", "BIJIH NIKEL")),
    ("BAUXITE",              ("BAUXITE", "BAUKSIT")),
    ("IRON ORE",             ("IRON ORE", "BIJIH BESI")),
    ("LIMESTONE",            ("LIMESTONE", "BATU GAMPING", "BATU KAPUR")),
    ("GYPSUM",               ("GYPSUM", "GIPSUM")),
    ("SEMEN CURAH",          ("SEMEN CURAH", "CEMENT BULK")),
    ("SEMEN",                ("SEMEN", "CEMENT", "KLINKER", "CLINKER")),
    ("PUPUK",                ("PUPUK", "FERTILIZER", "UREA")),
    ("GRAIN",                ("WHEAT", "GANDUM", "BERAS", "RICE",
                                "CORN", "JAGUNG", "SOYBEAN", "SOYABEAN",
                                "KEDELAI", "GRAIN", "SUGAR", "GULA",
                                "BUNGKIL", "SBM ")),
    ("WOOD/TIMBER",          ("WOOD CHIP", "SERBUK KAYU", "PULP",
                                "LOG", "KAYU", "TIMBER", "PLYWOOD",
                                "VENEER", "EUCALYPTUS")),
    ("SAND/STONE",           ("PASIR", " SAND", "STONES", "STONE",
                                "BATU GUNUNG", "BATU SPLIT", "BATU PECAH",
                                "GRANITE", "GRANIT")),
    ("SALT",                 ("SALT", "GARAM")),
    # --- Container / general / vehicles / etc. -----------------------------
    ("CONTAINER",            ("CONTAINER", "PETIKEMAS", "PETI KEMAS",
                                "KONTAINER", "TEU")),
    ("GENERAL CARGO",        ("GENERAL CARGO", "BARANG UMUM", "MUATAN UMUM",
                                "BARANG CAMPURAN", "BREAK BULK", "BREAKBULK",
                                "MIXED CARGO", "GENCAR", "GEN CAR", "GEN.CAR")),
    ("MOBIL/TRUK/MOTOR",     ("MOBIL", "TRUK", "TRUCK", "MOTOR",
                                "VEHICLE", "KENDARAAN", "BUS ",
                                "ALAT BERAT", "HEAVY EQUIPMENT", "MATERIAL")),
    ("IKAN",                 ("IKAN", "FISH")),
    ("TERNAK",               ("TERNAK", "LIVESTOCK")),
    ("WATER",                ("AIR BERSIH", "AIR TAWAR", "FRESH WATER")),
    # --- BARANG is very generic ("goods") — last-resort general-cargo tag --
    ("BARANG (기타)",         ("BARANG",)),
)

# Catch-all bucket for KOMODITI text that matches no keyword.
BUCKET_OTHER = "기타"


# ---------------------------------------------------------------------------
# Tier-2 categories: 17 buckets that group the granular commodities into
# strategically meaningful classes for the cat-details panel and timeseries
# stack chart.
# ---------------------------------------------------------------------------
BUCKET_TO_CATEGORY: dict[str, str] = {
    # Crude
    "CRUDE OIL":             "Crude Oil",
    "OMAN BLEND CRUDE OIL":  "Crude Oil",
    "CONDENSATE":            "Crude Oil",
    # Petroleum
    "PERTALITE":             "Petroleum Product",
    "PERTAMAX":              "Petroleum Product",
    "AVTUR":                 "Petroleum Product",
    "HSD":                   "Petroleum Product",
    "SOLAR":                 "Petroleum Product",
    "MFO/HSFO":              "Petroleum Product",
    "KEROSENE":              "Petroleum Product",
    "BBM (기타)":             "Petroleum Product",
    "ASPAL/BITUMEN":         "Petroleum Product",
    # Gases
    "LPG":                   "LPG / Gas",
    "LNG":                   "LNG",
    # Chemicals
    "METHANOL":              "Chemical",
    "AMMONIA":               "Chemical",
    "SULFUR":                "Chemical",
    "CHEMICAL (기타)":        "Chemical",
    # Palm oil family
    "CPO":                   "Palm Oil",
    "RBD PALM OIL":          "Palm Oil",
    "RBD PALM OLEIN":        "Palm Oil",
    "OLEIN":                 "Palm Oil",
    "STEARIN":               "Palm Oil",
    "PKO/CPKO":              "Palm Oil",
    "PFAD":                  "Palm Oil",
    "PALM KERNEL":           "Palm Oil",
    # Biodiesel
    "FAME":                  "Biodiesel (FAME)",
    # Other vegetable oils
    "COCONUT OIL":           "Other Vegetable Oil",
    # Dry bulk
    "BATU BARA":             "Coal",
    "NICKEL ORE":            "Mineral Ore",
    "BAUXITE":               "Mineral Ore",
    "IRON ORE":              "Mineral Ore",
    "LIMESTONE":             "Other Dry Bulk",
    "GYPSUM":                "Other Dry Bulk",
    "WOOD/TIMBER":           "Wood / Timber",
    "SAND/STONE":            "Other Dry Bulk",
    "SALT":                  "Other Dry Bulk",
    "SEMEN":                 "Cement",
    "SEMEN CURAH":           "Cement",
    "PUPUK":                 "Fertilizer",
    "GRAIN":                 "Grain / Food",
    # Container / General / Vehicles / etc
    "CONTAINER":             "Container",
    "GENERAL CARGO":         "General Cargo",
    "BARANG (기타)":          "General Cargo",
    "MOBIL/TRUK/MOTOR":      "Vehicles",
    "IKAN":                  "Fish & Livestock",
    "TERNAK":                "Fish & Livestock",
    "WATER":                 "Water",
    # 기타 fallback maps to "Other"
    BUCKET_OTHER:            "Other",
}

# Stack / display order for Tier-2 categories.
CATEGORY_ORDER: tuple[str, ...] = (
    # Dry bulk family
    "Coal",
    "Mineral Ore",
    "Other Dry Bulk",
    "Wood / Timber",
    "Cement",
    "Fertilizer",
    "Grain / Food",
    # Liquid bulk family
    "Crude Oil",
    "Petroleum Product",
    "LPG / Gas",
    "LNG",
    "Chemical",
    "Palm Oil",
    "Biodiesel (FAME)",
    "Other Vegetable Oil",
    "Water",
    # Discrete cargo family
    "Container",
    "General Cargo",
    "Vehicles",
    "Fish & Livestock",
    "Other",
)

# Stable color palette per Tier-2 category — kept in sync with the JS
# CARGO_CATEGORY_PALETTE so chart legend + cat-details bar match.
CATEGORY_COLORS: dict[str, str] = {
    "Coal":                 "#52525b",
    "Mineral Ore":          "#71717a",
    "Other Dry Bulk":       "#a1a1aa",
    "Wood / Timber":        "#a16207",
    "Cement":               "#94a3b8",
    "Fertilizer":           "#84cc16",
    "Grain / Food":         "#f59e0b",
    "Crude Oil":            "#92400e",
    "Petroleum Product":    "#0284c7",
    "LPG / Gas":            "#d97706",
    "LNG":                  "#7c3aed",
    "Chemical":             "#059669",
    "Palm Oil":             "#16a34a",
    "Biodiesel (FAME)":     "#65a30d",
    "Other Vegetable Oil":  "#bef264",
    "Water":                "#0ea5e9",
    "Container":            "#9333ea",
    "General Cargo":        "#f97316",
    "Vehicles":             "#ef4444",
    "Fish & Livestock":     "#06b6d4",
    "Other":                "#cbd5e1",
}


# ---------------------------------------------------------------------------
# Lookup functions
# ---------------------------------------------------------------------------
def normalize(label: str | None) -> str:
    """Uppercase + collapse internal whitespace. Returns ``""`` for null."""
    if not label:
        return ""
    return re.sub(r"\s+", " ", str(label).upper()).strip()


def classify_commodity_bucket(label: str | None) -> str:
    """Map a KOMODITI text to its Tier-1 bucket. Returns ``기타`` on no match."""
    s = normalize(label)
    if not s:
        return BUCKET_OTHER
    for bucket, kws in COMMODITY_BUCKETS:
        for kw in kws:
            if kw in s:
                return bucket
    return BUCKET_OTHER


def classify_commodity_category(label: str | None) -> str:
    """Map a KOMODITI text directly to its Tier-2 category."""
    return BUCKET_TO_CATEGORY.get(classify_commodity_bucket(label), "Other")


def all_bucket_names() -> list[str]:
    """Tier-1 bucket names in declaration order, with ``기타`` appended."""
    return [b for b, _ in COMMODITY_BUCKETS] + [BUCKET_OTHER]


def bucket_keyword_export() -> list[dict]:
    """Serializable form of the bucket → keyword table (for JSON _notes)."""
    return [{"bucket": b, "kws": list(kws)} for b, kws in COMMODITY_BUCKETS]


def coverage_buckets(stream: Iterable[tuple[str | None, float]]) -> dict:
    """Bucket-weighted coverage stats. ``stream`` is ``(label, ton)`` pairs."""
    by_bucket: dict[str, float] = {}
    by_category: dict[str, float] = {}
    other_tail: dict[str, float] = {}
    total = 0.0
    for label, ton in stream:
        ton = float(ton or 0)
        total += ton
        bucket = classify_commodity_bucket(label)
        by_bucket[bucket] = by_bucket.get(bucket, 0.0) + ton
        cat = BUCKET_TO_CATEGORY.get(bucket, "Other")
        by_category[cat] = by_category.get(cat, 0.0) + ton
        if bucket == BUCKET_OTHER:
            key = normalize(label) or "(empty)"
            other_tail[key] = other_tail.get(key, 0.0) + ton
    return {
        "total_ton":   total,
        "by_bucket":   by_bucket,
        "by_category": by_category,
        "other_pct":   (by_bucket.get(BUCKET_OTHER, 0.0) / total * 100.0) if total else 0.0,
        "other_tail":  sorted(other_tail.items(), key=lambda kv: -kv[1]),
    }
