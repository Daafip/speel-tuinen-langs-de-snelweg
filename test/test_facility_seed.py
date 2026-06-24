"""Tests for the authoritative facility seed (UK indoor-soft-play reconciliation)."""

import datetime as dt

import geopandas as gpd
from shapely.geometry import Point

from restspots.enrich import uk
from restspots.join import apply_facility_seed
from restspots.schema import to_canonical


def _rest_all():
    return gpd.GeoDataFrame(
        {
            "tags": [
                {"highway": "rest_area", "name": "Existing"},
                {"highway": "services"},
            ],
            "type": ["node", "node"],
            "id": [1, 2],
        },
        geometry=[Point(6.0, 52.2), Point(7.0, 51.0)],
        crs=4326,
    )


def _stops():
    # Only id=1 was flagged via OSM (contained); id=2 was not.
    return gpd.GeoDataFrame(
        {
            "tags": [{"highway": "rest_area", "name": "Existing"}],
            "type": ["node"],
            "id": [1],
            "has_playground": [True],
            "playground_count": [1],
            "match_type": ["contained"],
        },
        geometry=[Point(6.0, 52.2)],
        crs=4326,
    )


def _seed():
    return gpd.GeoDataFrame(
        {
            "name": ["Existing", "Promoted Services", "Lonely Services"],
            "ref": ["A1", "M2", "M3"],
            "side": ["both", "NB", "both"],
            "play_type": ["both", "indoor_soft_play", "indoor_soft_play"],
            "verified_source": ["operator", "operator", "operator"],
            "seed_id": ["GB-0", "GB-1", "GB-2"],
            "last_verified": [dt.date(2026, 6, 1)] * 3,
        },
        geometry=[Point(6.0001, 52.2), Point(7.0001, 51.0), Point(10.0, 49.0)],
        crs=4326,
    )


def test_seed_annotate_promote_add():
    out = apply_facility_seed(_rest_all(), _stops(), _seed(), max_distance=2000)
    # 1 existing (annotated) + 1 promoted (id 2) + 1 synthetic = 3
    assert len(out) == 3
    by_id = {r["id"]: r for _, r in out.iterrows()}

    # annotated: existing OSM stop now also operator-verified, play_type from seed
    assert by_id[1]["match_type"] == "contained"
    assert "operator" in by_id[1]["verified_source"]
    assert "osm" in by_id[1]["verified_source"]
    assert by_id[1]["play_type"] == "both"

    # promoted: OSM stop that had no playground is now confirmed via the listing
    assert by_id[2]["has_playground"]
    assert by_id[2]["match_type"] == "operator_listed"
    assert by_id[2]["play_type"] == "indoor_soft_play"

    # synthetic: no OSM stop nearby -> a new seed-located stop
    synth = [r for k, r in by_id.items() if str(k).startswith("GB-")]
    assert synth and synth[0]["match_type"] == "operator_listed"


def test_seed_flows_to_canonical():
    out = apply_facility_seed(_rest_all(), _stops(), _seed(), max_distance=2000)
    df = to_canonical(
        out, "GB", labels={"services": "Services", "rest_area": "Rest area"}
    )
    promoted = df[df["match_type"] == "operator_listed"]
    assert (promoted["has_playground"]).all()
    assert set(promoted["play_type"]) <= {"indoor_soft_play"}
    # every row keeps a name
    assert df["name"].notna().all()


def test_uk_seed_to_points_shape():
    g = uk.to_points(uk.SEED)
    assert len(g) == len(uk.SEED)
    assert set(
        ["name", "ref", "side", "play_type", "verified_source", "seed_id"]
    ) <= set(g.columns)
    assert g.crs.to_epsg() == 4326
