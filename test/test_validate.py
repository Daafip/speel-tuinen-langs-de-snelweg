"""Tests for the QA validation report."""

import datetime as dt

import geopandas as gpd
from shapely.geometry import Point

from restspots.schema import to_canonical
from restspots.validate import validate


def _gold(country="DE"):
    gdf = gpd.GeoDataFrame(
        {
            "tags": [
                {"highway": "services", "name": "A", "toilets": "yes"},
                {"highway": "rest_area", "name": "B"},
            ],
            "type": ["node", "node"],
            "id": [1, 2],
            "has_playground": [True, True],
            "playground_count": [1, 0],
            "match_type": ["proximity", "operator_listed"],
            "play_type": ["outdoor", "indoor_soft_play"],
            "verified_source": ["osm", "operator"],
            "last_verified": [dt.date(2026, 6, 20), dt.date(2025, 1, 1)],  # 2nd is stale
        },
        geometry=[Point(8.0, 50.0), Point(9.0, 51.0)],
        crs=4326,
    )
    df = to_canonical(gdf, country, retrieved_at=dt.date(2026, 6, 24))
    return gdf, df


def test_report_has_new_breakdowns():
    gdf, df = _gold()
    rep = validate(gdf, df, "DE", today=dt.date(2026, 6, 24))
    assert rep["passed"]
    assert rep["by_play_type"] == {"outdoor": 1, "indoor_soft_play": 1}
    assert "operator" in rep["by_verified_source"]
    assert "operator_listed" in rep["by_match_type"]


def test_stale_confirmation_counted():
    gdf, df = _gold()
    rep = validate(gdf, df, "DE", today=dt.date(2026, 6, 24))
    # The 2025-01-01 confirmation is older than 180 days -> flagged (but not a hard failure).
    assert rep["stale_confirmations"] == 1
    assert rep["passed"]


def test_out_of_bbox_fails():
    gdf, df = _gold()
    rep = validate(gdf, df, "NL", today=dt.date(2026, 6, 24))  # DE coords, NL bbox
    assert not rep["passed"]
    assert any("bounding box" in f for f in rep["failures"])
