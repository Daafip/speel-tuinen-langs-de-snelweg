import datetime as dt

import geopandas as gpd
from shapely.geometry import Point

from restspots.schema import CANONICAL_FIELDS, attach_geometry, to_canonical


def test_unnamed_stop_gets_regional_name():
    gdf = gpd.GeoDataFrame(
        {
            "tags": [{"highway": "rest_area"}, {"highway": "rest_area"}],
            "type": ["node", "node"],
            "id": [1, 2],
            "place_name": ["Apeldoorn", None],  # one near a place, one not
        },
        geometry=[Point(5.9, 52.2), Point(6.0, 52.3)],
        crs=4326,
    )
    labels = {"rest_area": "Verzorgingsplaats"}
    df = to_canonical(gdf, "NL", labels=labels).sort_values("id").reset_index(drop=True)
    # Regional name when a place is nearby; plain localized term otherwise.
    assert df.iloc[0]["name"] == "Verzorgingsplaats Apeldoorn"
    assert df.iloc[1]["name"] == "Verzorgingsplaats"
    # Never the German term for a Dutch stop.
    assert "Rastplatz" not in set(df["name"])


def test_unnamed_stop_default_label_when_no_config():
    gdf = gpd.GeoDataFrame(
        {"tags": [{"highway": "services"}], "type": ["node"], "id": [1]},
        geometry=[Point(9.0, 51.0)],
        crs=4326,
    )
    df = to_canonical(gdf, "XX")
    assert df.iloc[0]["name"] == "Services"


def _joined():
    return gpd.GeoDataFrame(
        {
            "tags": [
                {
                    "highway": "services",
                    "name": "B Area",
                    "toilets": "yes",
                    "fuel": "yes",
                },
                {"highway": "rest_area", "name": "A Area", "toilets": "no"},
            ],
            "type": ["way", "node"],
            "id": [222, 111],
            "has_playground": [True, True],
            "playground_count": [2, 1],
            "match_type": ["contained", "proximity"],
        },
        geometry=[Point(6.0, 52.2), Point(7.0, 51.0)],
        crs=4326,
    )


def test_to_canonical_fields_and_sorting():
    df = to_canonical(_joined(), "DE", retrieved_at=dt.date(2026, 6, 22))
    assert list(df.columns) == CANONICAL_FIELDS
    # Sorted by id: node/111 before way/222
    assert df.iloc[0]["id"] == "node/111"
    assert df.iloc[1]["id"] == "way/222"


def test_to_canonical_amenities_and_urls():
    df = to_canonical(_joined(), "DE", retrieved_at=dt.date(2026, 6, 22))
    bnode = df[df["id"] == "way/222"].iloc[0]
    assert bool(bnode["toilets"]) is True
    assert bool(bnode["fuel"]) is True
    assert bnode["feature_type"] == "services"
    assert bnode["osm_url"] == "https://www.openstreetmap.org/way/222"
    assert bnode["country"] == "DE"
    anode = df[df["id"] == "node/111"].iloc[0]
    assert bool(anode["toilets"]) is False


def test_attach_geometry_roundtrip():
    df = to_canonical(_joined(), "DE")
    gdf = attach_geometry(df, _joined())
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert gdf.geometry.notna().all()
    assert gdf.crs.to_epsg() == 4326


def test_attach_geometry_empty_keeps_crs():
    empty = gpd.GeoDataFrame({"tags": [], "type": [], "id": []}, geometry=[], crs=4326)
    df = to_canonical(empty, "DE")
    gdf = attach_geometry(df, empty)
    assert len(gdf) == 0
    assert gdf.crs.to_epsg() == 4326
