"""Path B — Geofabrik ``.osm.pbf`` extract: versioned, offline, scales to all of Europe.

The dated ``.pbf`` *is* the reproducible snapshot — no rate limits, no API drift. We
import ``pyrosm`` lazily so the rest of the package (and the test suite) does not require
the heavy offline-parsing stack to be installed.
"""

from __future__ import annotations

import json
import pathlib
import urllib.request

import geopandas as gpd
import pandas as pd

from .config import CountryConfig

# pyrosm columns that are metadata, not OSM tags.
_META_COLS = {
    "lat",
    "lon",
    "visible",
    "changeset",
    "timestamp",
    "version",
    "geometry",
    "osm_type",
    "id",
    "tags",
}


def download_extract(
    cfg: CountryConfig, raw_dir: str | pathlib.Path = "data/raw"
) -> pathlib.Path:
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


def extract_from_pbf(pbf_path: str | pathlib.Path, cfg: CountryConfig):
    """Parse rest stops and playgrounds out of a ``.pbf`` with pyrosm.

    Returns ``(rest, play)`` as raw pyrosm GeoDataFrames; pass each through
    :func:`normalize_pyrosm` to get the source-agnostic shape used downstream.
    """
    from pyrosm import OSM  # lazy: optional heavy dependency

    osm = OSM(str(pbf_path))
    highway_values = cfg.stop_tags.get("highway", ["services", "rest_area"])
    rest = osm.get_data_by_custom_criteria(
        custom_filter={"highway": list(highway_values)},
        filter_type="keep",
        keep_nodes=True,
        keep_ways=True,
        keep_relations=True,
    )
    play = osm.get_data_by_custom_criteria(
        custom_filter={"leisure": ["playground"]},
        filter_type="keep",
        keep_nodes=True,
        keep_ways=True,
        keep_relations=True,
    )
    return rest, play


def _row_tags(row, promoted: list[str]) -> dict:
    """Reconstruct a single OSM tag dict from pyrosm's promoted columns + ``tags`` JSON."""
    tags: dict = {}
    raw = row.get("tags")
    if isinstance(raw, str):
        try:
            tags.update(json.loads(raw))
        except (ValueError, TypeError):
            pass
    elif isinstance(raw, dict):
        tags.update(raw)
    for key in promoted:
        val = row.get(key)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        tags[key] = val
    return tags


def normalize_pyrosm(gdf) -> gpd.GeoDataFrame:
    """Reshape a pyrosm GeoDataFrame to the ``[tags, type, id, geometry]`` shape that
    :mod:`restspots.join` / :mod:`restspots.schema` expect (matching the Overpass path).
    """
    if gdf is None or len(gdf) == 0:
        return gpd.GeoDataFrame(
            {"tags": [], "type": [], "id": []}, geometry=[], crs=4326
        )
    promoted = [c for c in gdf.columns if c not in _META_COLS]
    tags = [_row_tags(row, promoted) for _, row in gdf.iterrows()]
    return gpd.GeoDataFrame(
        {"tags": tags, "type": gdf["osm_type"].to_numpy(), "id": gdf["id"].to_numpy()},
        geometry=gdf.geometry.to_numpy(),
        crs=gdf.crs or 4326,
    )
