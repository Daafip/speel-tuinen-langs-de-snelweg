"""Path B — Geofabrik ``.osm.pbf`` extract: versioned, offline, scales to all of Europe.

The dated ``.pbf`` *is* the reproducible snapshot — no rate limits, no API drift.

Parsing is done with **pyosmium**, which streams the file with a compact node-location
index. Peak memory stays around ~1 GB for a German state and only a few GB for the whole
4.8 GB Germany extract — unlike fully-materialising parsers, which need tens of GB. Tag
filtering happens in C++ (``osmium.filter.KeyFilter``) so only the handful of tagged
features ever reach Python.
"""

from __future__ import annotations

import pathlib
import urllib.request

import geopandas as gpd

from .config import CountryConfig

STOP_HIGHWAY = {"services", "rest_area"}


def download_extract(cfg: CountryConfig, raw_dir: str | pathlib.Path = "data/raw") -> pathlib.Path:
    """Download the country's Geofabrik extract if not already present; return its path.

    The filename carries no date — Geofabrik's ``-latest`` URL is mutable — so record the
    download date in run metadata (see :mod:`restspots.pipeline`) to keep provenance.
    """
    if not cfg.geofabrik_url:
        raise ValueError(f"No geofabrik_url configured for {cfg.iso}")
    raw_dir = pathlib.Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / pathlib.Path(cfg.geofabrik_url).name
    if not dest.exists():
        urllib.request.urlretrieve(cfg.geofabrik_url, dest)  # noqa: S310 (trusted host)
    return dest


def _way_geometry(way):
    """Build a shapely geometry for a way from its (located) nodes; None if unusable."""
    from shapely.geometry import LineString, Point, Polygon

    coords = [(n.location.lon, n.location.lat) for n in way.nodes if n.location.valid()]
    if len(coords) >= 4 and coords[0] == coords[-1]:
        return Polygon(coords)
    if len(coords) >= 2:
        return LineString(coords)
    if coords:
        return Point(coords[0])
    return None


def extract_from_pbf(pbf_path: str | pathlib.Path, cfg: CountryConfig):
    """Stream a ``.pbf`` and return ``(rest, play, motorways)`` GeoDataFrames (WGS84).

    ``rest`` / ``play`` have columns ``[tags, type, id, geometry]`` — identical to the
    Overpass path's output, so everything downstream is source-agnostic. ``motorways`` is
    ``[ref, geometry]`` for ``highway=motorway`` ways carrying a ``ref``; it feeds the
    country-agnostic nearest-motorway fallback for stops without an official ref. Nodes
    and ways are captured; relations (rare for these tags) are skipped.
    """
    import osmium
    from shapely.geometry import Point

    highway_values = set(cfg.stop_tags.get("highway", list(STOP_HIGHWAY)))
    rest_rows: list[dict] = []
    play_rows: list[dict] = []
    motorway_rows: list[dict] = []

    fp = (
        osmium.FileProcessor(str(pbf_path))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("highway", "leisure"))
    )
    for obj in fp:
        tags = dict(obj.tags)
        highway = tags.get("highway")

        # Motorway centrelines (ways) for the nearest-ref fallback.
        if highway == "motorway" and obj.is_way():
            ref = tags.get("ref")
            geom = _way_geometry(obj) if ref else None
            if ref and geom is not None:
                motorway_rows.append({"ref": ref.replace(" ", ""), "geometry": geom})
            continue

        is_stop = highway in highway_values
        is_play = tags.get("leisure") == "playground"
        if not (is_stop or is_play):
            continue
        if obj.is_node():
            geom = Point(obj.location.lon, obj.location.lat)
            otype = "node"
        elif obj.is_way():
            geom = _way_geometry(obj)
            otype = "way"
        else:
            continue
        if geom is None:
            continue
        (rest_rows if is_stop else play_rows).append(
            {"tags": tags, "type": otype, "id": obj.id, "geometry": geom}
        )

    motorways = (
        _to_gdf(motorway_rows)
        if not motorway_rows
        else gpd.GeoDataFrame(
            {"ref": [r["ref"] for r in motorway_rows]},
            geometry=[r["geometry"] for r in motorway_rows],
            crs=4326,
        )
    )
    return _to_gdf(rest_rows), _to_gdf(play_rows), motorways


def _to_gdf(rows: list[dict]) -> gpd.GeoDataFrame:
    if not rows:
        return gpd.GeoDataFrame({"tags": [], "type": [], "id": []}, geometry=[], crs=4326)
    geoms = [r.pop("geometry") for r in rows]
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=4326)
