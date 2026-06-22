"""Unit tests for the pyrosm normalizer (no .pbf / pyrosm import needed)."""

import geopandas as gpd
from shapely.geometry import Point

from restspots.pbf import normalize_pyrosm


def _fake_pyrosm():
    # Mimics pyrosm output: promoted tag columns + a `tags` JSON string + metadata.
    return gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "osm_type": ["node", "way"],
            "highway": ["services", "rest_area"],
            "name": ["Autohof Bremen", None],
            "version": [3, 1],
            "tags": ['{"toilets":"yes","playground":"yes"}', '{"toilets":"yes"}'],
        },
        geometry=[Point(8.8, 53.0), Point(8.9, 53.1)],
        crs=4326,
    )


def test_normalize_merges_promoted_and_json_tags():
    out = normalize_pyrosm(_fake_pyrosm())
    assert list(out.columns) >= ["tags", "type", "id"]  # required shape
    t0 = out.iloc[0]["tags"]
    # Promoted columns and JSON-string tags are merged into one dict.
    assert t0["highway"] == "services"
    assert t0["name"] == "Autohof Bremen"
    assert t0["toilets"] == "yes"
    assert t0["playground"] == "yes"
    assert out.iloc[0]["type"] == "node"
    # version is metadata, not a tag.
    assert "version" not in t0


def test_normalize_empty():
    empty = gpd.GeoDataFrame({"tags": []}, geometry=[], crs=4326)
    out = normalize_pyrosm(empty)
    assert len(out) == 0
    assert "tags" in out.columns
