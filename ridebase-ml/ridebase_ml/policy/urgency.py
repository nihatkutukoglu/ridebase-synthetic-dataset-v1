"""Deterministic Maintenance Urgency Score (0–100).

Pure policy calculation — completely independent of machine learning models.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


def calculate_maintenance_urgency(
    progress_ratio: Optional[float],
    km_ratio: Optional[float] = None,
    day_ratio: Optional[float] = None,
    overdue_km: Optional[float] = None,
    overdue_days: Optional[float] = None,
    interval_km: Optional[float] = None,
    interval_days: Optional[float] = None,
    remaining_km: Optional[float] = None,
    remaining_days: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate the deterministic 0–100 maintenance urgency score and severity band."""
    if progress_ratio is None or not math.isfinite(progress_ratio) or progress_ratio < 0:
        return {
            "maintenance_urgency_score": None,
            "maintenance_urgency_score_exact": None,
            "maintenance_urgency_level": "HESAPLANAMADI",
            "maintenance_urgency_reason": "Kişisel servis başlangıç noktası eksik olduğu için bakım aciliyeti hesaplanamadı.",
            "determining_dimension": "UNKNOWN",
            "progress_ratio": None,
            "overdue_km": overdue_km,
            "overdue_days": overdue_days,
        }

    R = float(progress_ratio)

    # 1. Continuous Piecewise-Linear Mapping S(R) in [0, 100]
    if R <= 0.0:
        score = 0.0
    elif R < 0.80:
        score = R * 47.5
    elif R < 1.00:
        score = 38.0 + (R - 0.80) * 60.0
    elif R < 1.50:
        score = 50.0 + (R - 1.00) * 50.0
    elif R < 2.00:
        score = 75.0 + (R - 1.50) * 30.0
    elif R < 5.00:
        score = 90.0 + (R - 2.00) * (10.0 / 3.0)
    else:
        score = 100.0

    score = round(max(0.0, min(100.0, score)), 1)
    score_int = int(round(score))

    # 2. Determining Dimension
    if km_ratio is not None and day_ratio is not None:
        diff = abs(km_ratio - day_ratio)
        if diff <= 0.01:
            dim = "BOTH"
        elif km_ratio > day_ratio:
            dim = "KM"
        else:
            dim = "TIME"
    elif km_ratio is not None:
        dim = "KM"
    elif day_ratio is not None:
        dim = "TIME"
    else:
        dim = "KM"

    # 3. Severity Bands
    if score < 25.0:
        level = "NORMAL"
    elif score < 50.0:
        level = "YAKLAŞIYOR"
    elif score < 75.0:
        level = "GECİKMİŞ"
    elif score < 90.0:
        level = "ÇOK GECİKMİŞ"
    else:
        level = "KRİTİK"

    # Invariant: If progress_ratio >= 1.0, level must never be NORMAL or YAKLAŞIYOR
    if R >= 1.0 and level in ("NORMAL", "YAKLAŞIYOR"):
        level = "GECİKMİŞ"
        score_int = max(50, score_int)

    # 4. Human-Readable Reason
    if R >= 1.0:
        if dim == "KM" and overdue_km is not None and overdue_km > 0:
            reason = f"{overdue_km:,.0f} km gecikmiş (kilometre periyodu {R:.1f}× seviyesinde)".replace(",", ".")
        elif dim == "TIME" and overdue_days is not None and overdue_days > 0:
            reason = f"{overdue_days:.0f} gün gecikmiş (zaman periyodu {R:.1f}× seviyesinde)"
        else:
            reason = f"Bakım periyodu {R:.1f}× seviyesinde aşıldı"
    elif R >= 0.80:
        if dim == "KM" and remaining_km is not None:
            reason = f"Bakım periyoduna {remaining_km:,.0f} km kaldı (%{R*100:.0f} ilerleme)".replace(",", ".")
        elif dim == "TIME" and remaining_days is not None:
            reason = f"Bakım periyoduna {remaining_days:.0f} gün kaldı (%{R*100:.0f} ilerleme)"
        else:
            reason = f"Bakım periyoduna yaklaşıyor (%{R*100:.0f} ilerleme)"
    else:
        if dim == "KM" and remaining_km is not None:
            reason = f"Bakım periyodu içinde — kalan: {remaining_km:,.0f} km (%{R*100:.0f} ilerleme)".replace(",", ".")
        elif dim == "TIME" and remaining_days is not None:
            reason = f"Bakım periyodu içinde — kalan: {remaining_days:.0f} gün (%{R*100:.0f} ilerleme)"
        else:
            reason = f"Bakım periyodu içinde (%{R*100:.0f} ilerleme)"

    return {
        "maintenance_urgency_score": score_int,
        "maintenance_urgency_score_exact": score,
        "maintenance_urgency_level": level,
        "maintenance_urgency_reason": reason,
        "determining_dimension": dim,
        "progress_ratio": round(R, 4),
        "overdue_km": overdue_km,
        "overdue_days": overdue_days,
    }
