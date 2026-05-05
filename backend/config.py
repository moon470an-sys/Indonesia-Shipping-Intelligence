"""Project-wide configuration."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"
for _d in (DATA_DIR, RAW_DIR, LOG_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv("DB_URL", f"sqlite:///{(DATA_DIR / 'shipping_bi.db').as_posix()}")

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def current_snapshot_month() -> str:
    return now_kst().strftime("%Y-%m")


# Vessel type search codes (56 codes)
SEARCH_CODES: list[str] = [
    "AAa", "Ab", "Ba", "BBb", "Bc", "Be", "CCa", "Da", "DDa", "Ft",
    "Ga", "GGa", "GGe", "HHa", "IIa", "IIb", "IId", "IIk", "IIm", "IIp",
    "Ka", "Kb", "KKa", "KKb", "KKc", "KKh", "KKi", "LLa", "LLo", "LLq",
    "LLr", "MMa", "MMc", "MMe", "MMj", "MMk", "MMq", "Mp", "Na", "OOk",
    "OOm", "OOn", "Pa", "Pd", "PPa", "PPf", "PPh", "PPj", "PPm", "Pst",
    "Qa", "QQb", "QQc", "QQm", "RRc", "SSd",
]

CARGO_LOOKBACK_MONTHS = 24
CARGO_KINDS = ["dn", "ln"]

FLEET_WORKERS = 5
CARGO_WORKERS = 8

PAGE_SIZE = 100

# HTTP
KAPAL_URL = "https://kapal.dephub.go.id/ditkapel_service/data_kapal/api-kapal.php"
INAPORT_LIST_URL = "https://monitoring-inaportnet.dephub.go.id/list/{year}/{month:02d}"
INAPORT_LK3_URL = "https://monitoring-inaportnet.dephub.go.id/report/lk3/{port}/{kind}/{year}/{month:02d}"

KAPAL_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://kapal.dephub.go.id",
    "Referer": "https://kapal.dephub.go.id/ditkapel_service/data_kapal/",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
}

INAPORT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://monitoring-inaportnet.dephub.go.id/",
}

REQUEST_TIMEOUT = 60
HTTP_RETRY_DELAYS = [2, 4, 8, 16]  # exponential backoff seconds

# Persist raw downloads to data/raw/. Disabled for cargo by default — LK3 .xls files
# are large (millions of rows × 24 months × 267 ports) and quickly fill the disk.
SAVE_RAW_FLEET = True
SAVE_RAW_CARGO = False


def build_logger(name: str = "shipping_bi") -> logging.Logger:
    log_path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d')}.log"
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger
