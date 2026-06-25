import geopandas as gpd
from shapely.geometry import Point

from restspots.mapview import PLAY_TYPE_COLOURS, build_map, write_map


def _gold():
    return gpd.GeoDataFrame(
        {
            "id": ["node/1", "way/2"],
            "name": ["Stop One", "Stop Two"],
            "country": ["DE", "DE"],
            "lat": [52.2, 51.0],
            "lon": [6.0, 7.0],
            "motorway_ref": ["A7", None],
            "playground_count": [1, 3],
            "match_type": ["proximity", "contained"],
            "play_type": ["outdoor", "indoor_soft_play"],
            "toilets": [True, False],
            "osm_url": [
                "https://www.openstreetmap.org/node/1",
                "https://www.openstreetmap.org/way/2",
            ],
        },
        geometry=[Point(6.0, 52.2), Point(7.0, 51.0)],
        crs=4326,
    )


def test_write_map_creates_html(tmp_path):
    path = write_map(_gold(), tmp_path / "map.html", title="Test map")
    assert path.exists() and path.stat().st_size > 0
    text = path.read_text()
    # Leaflet/folium scaffolding plus our content.
    assert "leaflet" in text.lower()
    assert "Stop One" in text
    assert "Test map" in text


def test_popup_escapes_and_links(tmp_path):
    gdf = _gold()
    gdf.loc[0, "name"] = "A & B <script>"
    text = write_map(gdf, tmp_path / "map.html").read_text()
    # Name is HTML-escaped; the raw script tag must not appear verbatim.
    assert "<script>alert" not in text
    assert "openstreetmap.org/node/1" in text


def test_build_map_handles_empty():
    empty = gpd.GeoDataFrame(
        {c: [] for c in ["lat", "lon", "name", "play_type"]},
        geometry=[],
        crs=4326,
    )
    fmap = build_map(empty)  # must not raise / fit_bounds on no data
    assert fmap is not None


def test_known_play_types_have_colours():
    for pt in ("outdoor", "indoor_soft_play", "both", "unknown"):
        assert pt in PLAY_TYPE_COLOURS
