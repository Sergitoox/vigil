import duckdb
from datetime import datetime, timezone
from vigil.models.aoi import AreaOfInterest
from vigil.storage.database import query_fires_in_bbox


_RISK_THRESHOLDS = {
    "CRITICAL": 10,   # 10+ detections
    "HIGH": 4,         # 4–9
    "MEDIUM": 1,       # 1–3
    "LOW": 0,          # 0
}

_HIGH_INTENSITY_FRP = 50.0  # MW — above this is considered high intensity


def get_active_fires(
    conn: duckdb.DuckDBPyConnection,
    aoi: AreaOfInterest,
    hours: int = 24,
    min_confidence: str = "nominal",
) -> dict:
    """
    Returns all active fire detections inside the AOI.
    Designed to be called by the MCP tool handler.
    """
    w, s, e, n = aoi.bounds
    rows = query_fires_in_bbox(conn, w, s, e, n, hours, min_confidence)

    detections = [
        {
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "frp_mw": r["frp"],
            "confidence": r["confidence"],
            "acquired_at": r["acq_datetime"].isoformat() if isinstance(r["acq_datetime"], datetime) else str(r["acq_datetime"]),
            "satellite": r["satellite"],
            "daynight": "day" if r["daynight"] == "D" else "night",
            "high_intensity": r["frp"] > _HIGH_INTENSITY_FRP,
        }
        for r in rows
    ]

    return {
        "tool": "get_active_fires",
        "aoi": str(aoi),
        "query_window_hours": hours,
        "min_confidence": min_confidence,
        "total_detections": len(detections),
        "detections": detections,
        "summary": _build_detections_summary(detections, hours),
    }


def get_fire_summary(
    conn: duckdb.DuckDBPyConnection,
    aoi: AreaOfInterest,
    hours: int = 24,
) -> dict:
    """
    Returns a concise intelligence summary of fire activity in the AOI.
    Optimized for direct LLM consumption — includes risk_level and narrative summary.
    """
    w, s, e, n = aoi.bounds
    rows = query_fires_in_bbox(conn, w, s, e, n, hours, min_confidence="low")

    if not rows:
        return {
            "tool": "get_fire_summary",
            "aoi": str(aoi),
            "query_window_hours": hours,
            "risk_level": "NONE",
            "total_detections": 0,
            "summary": f"No fire detections found in the AOI in the last {hours} hours.",
            "recommendations": ["No action required based on available fire data."],
        }

    high = [r for r in rows if r["confidence"] == "high"]
    nominal = [r for r in rows if r["confidence"] == "nominal"]
    low = [r for r in rows if r["confidence"] == "low"]
    high_intensity = [r for r in rows if r["frp"] > _HIGH_INTENSITY_FRP]
    max_frp = max(r["frp"] for r in rows)
    max_frp_row = next(r for r in rows if r["frp"] == max_frp)

    risk_level = _compute_risk_level(len(rows), len(high_intensity), len(high))

    return {
        "tool": "get_fire_summary",
        "aoi": str(aoi),
        "query_window_hours": hours,
        "risk_level": risk_level,
        "total_detections": len(rows),
        "by_confidence": {
            "high": len(high),
            "nominal": len(nominal),
            "low": len(low),
        },
        "high_intensity_count": len(high_intensity),
        "peak_detection": {
            "latitude": max_frp_row["latitude"],
            "longitude": max_frp_row["longitude"],
            "frp_mw": max_frp,
            "confidence": max_frp_row["confidence"],
            "acquired_at": max_frp_row["acq_datetime"].isoformat() if isinstance(max_frp_row["acq_datetime"], datetime) else str(max_frp_row["acq_datetime"]),
        },
        "summary": _build_risk_summary(len(rows), risk_level, max_frp, max_frp_row, hours),
        "recommendations": _build_recommendations(risk_level, len(high_intensity)),
    }


def assess_fire_risk(
    conn: duckdb.DuckDBPyConnection,
    aoi: AreaOfInterest,
    hours: int = 24,
) -> dict:
    """
    Provides a structured risk assessment of fire conditions in the AOI.
    Includes risk factors and actionable recommendations for the agent.
    """
    w, s, e, n = aoi.bounds
    rows = query_fires_in_bbox(conn, w, s, e, n, hours, min_confidence="low")

    risk_factors: list[str] = []
    high_intensity = [r for r in rows if r["frp"] > _HIGH_INTENSITY_FRP]
    high_confidence = [r for r in rows if r["confidence"] == "high"]

    if len(rows) >= 10:
        risk_factors.append(f"High detection density: {len(rows)} detections in AOI")
    if high_intensity:
        risk_factors.append(
            f"{len(high_intensity)} high-intensity detections (FRP > {_HIGH_INTENSITY_FRP} MW)"
        )
    if high_confidence:
        risk_factors.append(f"{len(high_confidence)} high-confidence detections")
    if not rows:
        risk_factors.append("No fire activity detected")

    risk_level = _compute_risk_level(len(rows), len(high_intensity), len(high_confidence))

    return {
        "tool": "assess_fire_risk",
        "aoi": str(aoi),
        "query_window_hours": hours,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "total_detections": len(rows),
        "high_intensity_count": len(high_intensity),
        "high_confidence_count": len(high_confidence),
        "recommendations": _build_recommendations(risk_level, len(high_intensity)),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_risk_level(total: int, high_intensity: int, high_confidence: int) -> str:
    if total == 0:
        return "NONE"
    if total >= _RISK_THRESHOLDS["CRITICAL"] or high_intensity >= 3:
        return "CRITICAL"
    if total >= _RISK_THRESHOLDS["HIGH"] or high_intensity >= 1:
        return "HIGH"
    if total >= _RISK_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def _build_detections_summary(detections: list[dict], hours: int) -> str:
    if not detections:
        return f"No fire detections found in the last {hours} hours."
    hi = sum(1 for d in detections if d["high_intensity"])
    return (
        f"{len(detections)} fire detection(s) in the last {hours} hours. "
        f"{hi} high-intensity (FRP > {_HIGH_INTENSITY_FRP} MW)."
    )


def _build_risk_summary(
    total: int, risk: str, max_frp: float, peak: dict, hours: int
) -> str:
    ts = peak.get("acquired_at", "unknown time")
    return (
        f"Risk level: {risk}. {total} detection(s) in the last {hours} hours. "
        f"Peak intensity: {max_frp:.1f} MW at "
        f"({peak['latitude']:.4f}, {peak['longitude']:.4f}), "
        f"confidence {peak['confidence']}, acquired {ts}."
    )


def _build_recommendations(risk: str, high_intensity_count: int) -> list[str]:
    if risk == "NONE":
        return ["No action required based on available fire data."]
    if risk == "MEDIUM":
        return [
            "Monitor the AOI for new detections in the next 6 hours.",
            "Verify against local ground truth if infrastructure is nearby.",
        ]
    if risk == "HIGH":
        return [
            "Escalate to operational team for review.",
            "Cross-reference with wind data to assess spread direction.",
            "Identify infrastructure and population at risk within 20km of detections.",
        ]
    # CRITICAL
    return [
        "Immediate operational response recommended.",
        "Request updated satellite pass to confirm spread.",
        "Activate contingency protocols for affected infrastructure.",
        f"{high_intensity_count} high-intensity fires detected — prioritize these locations.",
    ]