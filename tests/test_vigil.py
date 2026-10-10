import pytest
import respx
import httpx
from datetime import datetime, timezone, timedelta
from vigil.models.aoi import AreaOfInterest
from vigil.models.events import FireDetection, Confidence, DayNight
from vigil.storage.database import get_connection, upsert_detections, query_fires_in_bbox
from vigil.ingest.firms import FIRMSIngestor
from vigil.tools.fire import get_active_fires, get_fire_summary, assess_fire_risk


def _now() -> datetime:
    """
    Naive UTC 'now', matching the naive datetimes stored in DuckDB TIMESTAMP columns.
    IMPORTANT: never hardcode absolute dates in time-window tests — DuckDB's NOW()
    is always the real current time, so a fixed past date silently falls outside
    any query window as time passes. Always generate test timestamps relative to
    the moment the test runs.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def spain_aoi() -> AreaOfInterest:
    return AreaOfInterest(bbox=[-10.0, 35.0, 5.0, 44.0])


@pytest.fixture
def sample_firms_response() -> list[dict]:
    """
    Realistic FIRMS API response — no real API call needed.
    Dates here don't need to be relative: the ingestor's fetch() only does
    geometric AOI filtering, not time-window filtering. Time-window filtering
    happens later, in DuckDB queries.
    """
    return [
        {
            "latitude": "39.5",
            "longitude": "-1.2",
            "frp": "85.3",
            "confidence": "high",
            "acq_date": "2026-04-24",
            "acq_time": "1423",
            "satellite": "N",
            "daynight": "D",
            "bright_ti4": "342.1",
        },
        {
            "latitude": "40.1",
            "longitude": "-2.8",
            "frp": "22.0",
            "confidence": "nominal",
            "acq_date": "2026-04-24",
            "acq_time": "1100",
            "satellite": "1",
            "daynight": "D",
            "bright_ti4": "320.5",
        },
        {
            "latitude": "38.9",
            "longitude": "-0.5",
            "frp": "12.0",
            "confidence": "low",
            "acq_date": "2026-04-24",
            "acq_time": "0830",
            "satellite": "N",
            "daynight": "D",
            "bright_ti4": None,
        },
    ]


@pytest.fixture
def db_conn():
    """In-memory DuckDB connection for tests."""
    conn = get_connection(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def detections() -> list[FireDetection]:
    """Detections timestamped relative to 'now' so time-window queries find them."""
    now = _now()
    return [
        FireDetection(
            latitude=39.5,
            longitude=-1.2,
            frp=85.3,
            confidence=Confidence.HIGH,
            acq_datetime=now - timedelta(hours=2),
            satellite="N",
            daynight=DayNight.DAY,
            bright_ti4=342.1,
        ),
        FireDetection(
            latitude=40.1,
            longitude=-2.8,
            frp=22.0,
            confidence=Confidence.NOMINAL,
            acq_datetime=now - timedelta(hours=5),
            satellite="1",
            daynight=DayNight.DAY,
        ),
    ]


# ── Model tests ───────────────────────────────────────────────────────────────

class TestAreaOfInterest:
    def test_bbox_creates_polygon(self, spain_aoi):
        assert spain_aoi.polygon is not None
        assert spain_aoi.firms_bbox_str == "-10.0,35.0,5.0,44.0"

    def test_contains_point_inside(self, spain_aoi):
        assert spain_aoi.contains_point(lat=40.4, lon=-3.7)  # Madrid

    def test_contains_point_outside(self, spain_aoi):
        assert not spain_aoi.contains_point(lat=48.8, lon=2.3)  # Paris

    def test_wkt_polygon(self):
        aoi = AreaOfInterest(wkt_str="POLYGON((-5 36, 5 36, 5 44, -5 44, -5 36))")
        assert aoi.polygon is not None

    def test_invalid_bbox_raises(self):
        with pytest.raises(ValueError):
            AreaOfInterest(bbox=[5.0, 36.0, -5.0, 44.0])  # west > east

    def test_missing_aoi_raises(self):
        with pytest.raises(ValueError):
            AreaOfInterest()


class TestFireDetection:
    def test_datetime_parsed_from_firms_fields(self):
        # This test checks parsing logic only, not time-window filtering —
        # an absolute date here is fine, it never touches NOW().
        d = FireDetection(
            latitude=39.5, longitude=-1.2, frp=50.0,
            confidence=Confidence.HIGH,
            acq_date="2026-04-24", acq_time="1423",
            satellite="N", daynight=DayNight.DAY,
        )
        assert d.acq_datetime == datetime(2026, 4, 24, 14, 23)

    def test_high_intensity_flag(self):
        now = _now()
        high = FireDetection(
            latitude=39.5, longitude=-1.2, frp=100.0,
            confidence=Confidence.HIGH,
            acq_datetime=now,
            satellite="N", daynight=DayNight.DAY,
        )
        low = FireDetection(
            latitude=39.5, longitude=-1.2, frp=10.0,
            confidence=Confidence.NOMINAL,
            acq_datetime=now,
            satellite="N", daynight=DayNight.DAY,
        )
        assert high.is_high_intensity is True
        assert low.is_high_intensity is False


# ── Storage tests ─────────────────────────────────────────────────────────────

class TestDatabase:
    def test_upsert_and_query(self, db_conn, detections, spain_aoi):
        inserted = upsert_detections(db_conn, detections)
        assert inserted == 2

        w, s, e, n = spain_aoi.bounds
        rows = query_fires_in_bbox(db_conn, w, s, e, n, hours=240)
        assert len(rows) == 2

    def test_upsert_deduplication(self, db_conn, detections):
        upsert_detections(db_conn, detections)
        upsert_detections(db_conn, detections)  # same data again

        w, s, e, n = -10.0, 35.0, 5.0, 44.0
        rows = query_fires_in_bbox(db_conn, w, s, e, n, hours=240)
        assert len(rows) == 2  # still 2, not 4

    def test_confidence_filter(self, db_conn, detections, spain_aoi):
        upsert_detections(db_conn, detections)
        w, s, e, n = spain_aoi.bounds

        all_rows = query_fires_in_bbox(db_conn, w, s, e, n, hours=240, min_confidence="low")
        high_only = query_fires_in_bbox(db_conn, w, s, e, n, hours=240, min_confidence="high")

        assert len(all_rows) == 2
        assert len(high_only) == 1
        assert high_only[0]["confidence"] == "high"


# ── Ingestor tests (mocked HTTP) ──────────────────────────────────────────────

class TestFIRMSIngestor:
    @respx.mock
    async def test_fetch_returns_detections(self, spain_aoi, sample_firms_response):
        ingestor = FIRMSIngestor(aoi=spain_aoi, api_key="test-key")

        # NOTE: respx changed its matching API — 'url__contains' no longer exists.
        # 'url__regex' is the correct lookup for partial URL matching now.
        respx.get(url__regex=r".*firms\.modaps\.eosdis\.nasa\.gov.*").mock(
            return_value=httpx.Response(200, json=sample_firms_response)
        )

        detections = await ingestor.fetch()

        # All 3 are inside Spain bbox — all should be returned
        # Low confidence is still ingested (filtered at query time, not fetch time)
        assert len(detections) == 3
        assert all(isinstance(d, FireDetection) for d in detections)

    @respx.mock
    async def test_fetch_handles_api_error_gracefully(self, spain_aoi):
        ingestor = FIRMSIngestor(aoi=spain_aoi, api_key="test-key")

        respx.get(url__regex=r".*firms\.modaps\.eosdis\.nasa\.gov.*").mock(
            return_value=httpx.Response(500)
        )

        detections = await ingestor.fetch()
        assert detections == []  # empty list, no exception raised


# ── Tools tests ───────────────────────────────────────────────────────────────

class TestFireTools:
    def test_get_active_fires_empty(self, db_conn, spain_aoi):
        result = get_active_fires(db_conn, spain_aoi)
        assert result["total_detections"] == 0
        assert result["detections"] == []

    def test_get_fire_summary_with_data(self, db_conn, detections, spain_aoi):
        upsert_detections(db_conn, detections)
        result = get_fire_summary(db_conn, spain_aoi, hours=240)

        assert result["total_detections"] == 2
        assert result["risk_level"] in ("NONE", "MEDIUM", "HIGH", "CRITICAL")
        assert "summary" in result
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)

    def test_assess_fire_risk_high_intensity(self, db_conn, spain_aoi):
        now = _now()
        high = FireDetection(
            latitude=39.5, longitude=-1.2, frp=200.0,
            confidence=Confidence.HIGH,
            acq_datetime=now - timedelta(hours=1),
            satellite="N", daynight=DayNight.DAY,
        )
        upsert_detections(db_conn, [high])

        result = assess_fire_risk(db_conn, spain_aoi, hours=24)
        assert result["risk_level"] in ("HIGH", "CRITICAL")
        assert result["high_intensity_count"] == 1