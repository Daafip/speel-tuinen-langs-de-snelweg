"""Unit tests for the pyosmium-based .pbf helpers (no .pbf file needed)."""

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from restspots.pbf import _to_gdf, _way_geometry


class _FakeNode:
    def __init__(self, lon, lat, valid=True):
        self.location = _Loc(lon, lat, valid)


class _Loc:
    def __init__(self, lon, lat, valid):
        self.lon = lon
        self.lat = lat
        self._valid = valid

    def valid(self):
        return self._valid


class _FakeWay:
    def __init__(self, nodes):
        self.nodes = nodes


def test_way_geometry_closed_ring_is_polygon():
    nodes = [_FakeNode(0, 0), _FakeNode(0, 1), _FakeNode(1, 1), _FakeNode(0, 0)]
    assert isinstance(_way_geometry(_FakeWay(nodes)), Polygon)


def test_way_geometry_open_is_linestring():
    nodes = [_FakeNode(0, 0), _FakeNode(1, 1)]
    assert isinstance(_way_geometry(_FakeWay(nodes)), LineString)


def test_way_geometry_skips_invalid_nodes():
    nodes = [_FakeNode(0, 0, valid=False), _FakeNode(1, 1, valid=False)]
    assert _way_geometry(_FakeWay(nodes)) is None


def test_to_gdf_shape_and_crs():
    rows = [
        {
            "tags": {"highway": "services"},
            "type": "node",
            "id": 1,
            "geometry": Point(8, 53),
        },
        {
            "tags": {"leisure": "playground"},
            "type": "way",
            "id": 2,
            "geometry": Point(9, 54),
        },
    ]
    gdf = _to_gdf(rows)
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert list(gdf.columns) >= ["tags", "type", "id"]
    assert gdf.crs.to_epsg() == 4326
    assert gdf.iloc[0]["tags"]["highway"] == "services"


def test_to_gdf_empty():
    gdf = _to_gdf([])
    assert len(gdf) == 0
    assert "tags" in gdf.columns
