"""Display helpers for Korean-language tanker investment dashboard.

The conventions here are intentionally narrow: investors read this dashboard
in Korean, the data is Indonesian, and the numerics are mostly large counts
of tons / GT / vessel calls. Pick the right helper at the call site instead
of reformatting strings inline.

* :func:`fmt_int`  — comma-separated integer ("1,234,567")
* :func:`fmt_ton`  — ton with smart magnitude suffix ("12.3M 톤")
* :func:`fmt_gt`   — gross tonnage with same suffix scheme but unit "GT"
* :func:`fmt_pct`  — percentage with sign + 1 decimal
* :func:`fmt_n`    — vessel/row count with "척"/"건" suffix
* :func:`fmt_compact` — generic magnitude formatter (no unit)
"""
from __future__ import annotations

from typing import Any


def _is_num(x: Any) -> bool:
    if x is None:
        return False
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return f == f  # NaN check


def fmt_compact(value: Any, decimals: int = 1) -> str:
    """Magnitude-formatted number ("1.2M", "5.4K"). No unit."""
    if not _is_num(value):
        return "-"
    v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        return f"{sign}{v/1e9:.{decimals}f}B"
    if v >= 1e6:
        return f"{sign}{v/1e6:.{decimals}f}M"
    if v >= 1e3:
        return f"{sign}{v/1e3:.{decimals}f}K"
    return f"{sign}{v:,.0f}"


def fmt_int(value: Any) -> str:
    if not _is_num(value):
        return "-"
    return f"{int(round(float(value))):,}"


def fmt_ton(value: Any, decimals: int = 1) -> str:
    """Tons with magnitude suffix and Korean unit. <100k stays as int."""
    if not _is_num(value):
        return "-"
    v = float(value)
    if abs(v) < 1e5:
        return f"{int(round(v)):,} 톤"
    return f"{fmt_compact(v, decimals)} 톤"


def fmt_gt(value: Any, decimals: int = 1) -> str:
    """Gross tonnage, same magnitude rules as :func:`fmt_ton`."""
    if not _is_num(value):
        return "-"
    v = float(value)
    if abs(v) < 1e5:
        return f"{int(round(v)):,} GT"
    return f"{fmt_compact(v, decimals)} GT"


def fmt_pct(value: Any, decimals: int = 1, signed: bool = False) -> str:
    if not _is_num(value):
        return "-"
    v = float(value)
    sign = ("+" if signed and v > 0 else "")
    return f"{sign}{v:.{decimals}f}%"


def fmt_n(value: Any, suffix: str = "척") -> str:
    """Count with Korean unit suffix (default "척" for vessel count)."""
    if not _is_num(value):
        return "-"
    return f"{int(round(float(value))):,} {suffix}"


def fmt_dwell(hours: Any) -> str:
    """Dwell time. <1 day → '12h'; ≥1 day → '2.5d'."""
    if not _is_num(hours):
        return "-"
    h = float(hours)
    if h < 24:
        return f"{h:.1f}h"
    return f"{h/24:.1f}d"
