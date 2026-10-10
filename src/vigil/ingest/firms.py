import logging
import httpx
from vigil.ingest.base import BaseIngestor
from vigil.models.aoi import AreaOfInterest
from vigil.models.events import FireDetection, Confidence, DayNight

logger = logging.getLogger(__name__)

_FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/json"
_DEFAULT_SOURCE = "VIIRS_SNPP_NRT"
_DAY_RANGE = 1  # look back 1 day — we poll frequently, no need for more


class FIRMSIngestor(BaseIngestor):
    """
    Fetches active fire detections from NASA FIRMS API.
    Uses VIIRS_SNPP_NRT at ~375m resolution by default.

    Requires a free API key from:
    https://firms.modaps.eosdis.nasa.gov/api/map_key/
    """

    def __init__(
        self,
        aoi: AreaOfInterest,
        api_key: str,
        source: str = _DEFAULT_SOURCE,
    ) -> None:
        super().__init__(aoi=aoi, api_key=api_key)
        self.source = source

    @property
    def source_name(self) -> str:
        return f"NASA FIRMS {self.source}"

    async def fetch(self) -> list[FireDetection]:
        """
        Fetches fire detections for the AOI bounding box from FIRMS.
        Returns an empty list on any network or API error.
        """
        from datetime import date

        today = date.today().isoformat()
        url = (
            f"{_FIRMS_BASE_URL}/{self.api_key}"
            f"/{self.source}"
            f"/{self.aoi.firms_bbox_str}"
            f"/{_DAY_RANGE}"
            f"/{today}"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                raw_detections: list[dict] = response.json()
        except httpx.HTTPError as e:
            logger.error("FIRMS API request failed: %s", e)
            return []
        except Exception as e:
            logger.error("Unexpected error fetching FIRMS data: %s", e)
            return []

        detections: list[FireDetection] = []
        for raw in raw_detections:
            try:
                detection = FireDetection(
                    latitude=float(raw["latitude"]),
                    longitude=float(raw["longitude"]),
                    frp=float(raw.get("frp", 0.0)),
                    confidence=_parse_confidence(raw.get("confidence", "nominal")),
                    acq_date=raw["acq_date"],
                    acq_time=raw["acq_time"],
                    satellite=str(raw.get("satellite", "")),
                    daynight=DayNight(raw.get("daynight", "D")),
                    bright_ti4=_safe_float(raw.get("bright_ti4")),
                    source=self.source,
                )
                # Final AOI polygon check — FIRMS returns bbox results,
                # but our AOI might be a more precise polygon
                if self.aoi.contains_point(detection.latitude, detection.longitude):
                    detections.append(detection)
            except Exception as e:
                logger.warning("Could not parse FIRMS detection: %s — %s", raw, e)
                continue

        logger.info(
            "%s: fetched %d detections in AOI %s",
            self.source_name,
            len(detections),
            self.aoi,
        )
        return detections


def _parse_confidence(raw: str) -> Confidence:
    """
    FIRMS VIIRS returns numeric confidence (0-100) or string.
    MODIS returns 'low', 'nominal', 'high'.
    We normalize both to our Confidence enum.
    """
    raw = str(raw).lower().strip()
    if raw in ("low", "l"):
        return Confidence.LOW
    if raw in ("high", "h"):
        return Confidence.HIGH
    # Numeric VIIRS confidence
    try:
        val = int(raw)
        if val < 30:
            return Confidence.LOW
        if val >= 65:
            return Confidence.HIGH
        return Confidence.NOMINAL
    except ValueError:
        return Confidence.NOMINAL


def _safe_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None