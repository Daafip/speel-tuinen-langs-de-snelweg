"""Phase 2/3 — normalize Overpass JSON, spatially join playgrounds, attach enrichment.

Project CRS is **EPSG:3035** (LAEA Europe, equal-area) so multi-country merges stay
consistent. A rest stop qualifies via one of three rules, recorded in ``match_type``:

* ``tag``        — the stop itself carries ``playground=yes`` (authoritative, rare)
* ``contained``  — a playground falls inside the stop polygon (areas only)
* ``proximity``  — a playground lies within a buffer of a point-mapped stop (common)
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from osm2geojson import json2geojson

PROJ = 3035  # pan-European equal-area metric CRS
STOP_HIGHWAY = {"services", "rest_area"}


def to_gdf(overpass_json: dict) -> gpd.GeoDataFrame:
    """Convert raw Overpass JSON to a WGS84 GeoDataFrame (tags under the ``tags`` column)."""
    fc = json2geojson(overpass_json)
    gdf = gpd.GeoDataFrame.from_features(fc["features"], crs=4326)
    if "tags" not in gdf.columns:
        gdf["tags"] = [{} for _ in range(len(gdf))]
    return gdf


def _tag(tags, key: str):
    return tags.get(key) if isinstance(tags, dict) else None


def split_features(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Split a combined extract into (rest stops, playgrounds) by their tags."""
    is_play = gdf["tags"].apply(lambda t: _tag(t, "leisure") == "playground")
    is_rest = gdf["tags"].apply(lambda t: _tag(t, "highway") in STOP_HIGHWAY)
    return gdf[is_rest].copy(), gdf[is_play].copy()


def attach_playgrounds(
    rest: gpd.GeoDataFrame,
    play: gpd.GeoDataFrame,
    contained_buf: float = 50.0,
    proximity_buf: float = 200.0,
) -> gpd.GeoDataFrame:
    """Flag rest stops that have a playground; keep only those, in WGS84.

    Adds ``playground_count``, ``has_playground`` and ``match_type``. Area-mapped stops
    get a small edge buffer (``contained``); point/line stops get a larger one
    (``proximity``) — the distinction is preserved in ``match_type`` for later QA.
    """
    rest_m = rest.to_crs(PROJ).copy()
    rest_m = rest_m.reset_index(drop=True)

    is_poly = rest_m.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    buf_dist = [
        contained_buf if p else proximity_buf for p in is_poly
    ]  # per-row distance
    zone_geom = rest_m.geometry.buffer(buf_dist)
    zones = gpd.GeoDataFrame({"_rid": rest_m.index}, geometry=zone_geom, crs=PROJ)

    if len(play):
        play_pts = play.to_crs(PROJ).copy()
        play_pts["geometry"] = play_pts.geometry.centroid  # point-in-zone test
        hits = gpd.sjoin(play_pts, zones, predicate="within", how="inner")
        counts = hits.groupby("_rid").size()
    else:
        counts = pd.Series(dtype="int64")

    rest_m["playground_count"] = counts.reindex(rest_m.index).fillna(0).astype(int)
    tagged = rest_m["tags"].apply(lambda t: _tag(t, "playground") == "yes")
    rest_m["has_playground"] = (rest_m["playground_count"] > 0) | tagged

    has_count = rest_m["playground_count"] > 0
    match_type = pd.Series(pd.NA, index=rest_m.index, dtype="object")
    match_type[has_count & ~is_poly] = "proximity"
    match_type[has_count & is_poly] = "contained"
    match_type[tagged] = "tag"  # authoritative tag wins
    rest_m["match_type"] = match_type

    kept = rest_m[rest_m["has_playground"]].copy()
    return kept.to_crs(4326)


def attach_nearest(
    gdf: gpd.GeoDataFrame,
    points: gpd.GeoDataFrame,
    fields: list[str],
    max_distance: float = 300.0,
    suffix: str = "",
) -> gpd.GeoDataFrame:
    """Attach the named fields from the nearest ``points`` feature within ``max_distance``.

    Used both to attach a motorway ``ref`` (nearest ``highway=motorway`` way,
    country-agnostic) and an official name/ref from a national connector (e.g. Autobahn).
    Operates in EPSG:3035 so ``max_distance`` is in metres.
    """
    if points is None or len(points) == 0:
        for f in fields:
            gdf[f"{f}{suffix}"] = pd.NA
        return gdf

    left = gdf.to_crs(PROJ).copy()
    right = points.to_crs(PROJ)[fields + ["geometry"]].copy()
    joined = gpd.sjoin_nearest(
        left, right, how="left", max_distance=max_distance, distance_col="_dist"
    )
    # sjoin_nearest can duplicate rows on ties; keep the first (closest) per original row.
    joined = joined[~joined.index.duplicated(keep="first")]
    for f in fields:
        gdf[f"{f}{suffix}"] = joined[f].values
    return gdf


def _key(row) -> tuple:
    return (row.get("type"), row.get("id"))


def apply_facility_seed(
    rest_all: gpd.GeoDataFrame,
    stops: gpd.GeoDataFrame,
    seed: gpd.GeoDataFrame,
    max_distance: float = 2000.0,
) -> gpd.GeoDataFrame:
    """Fold authoritative facility listings into the stop set (enumerate-then-verify).

    A stop is ``has_playground=True`` if *any* tier confirms it (plan §3 reconciliation).
    Each seed point (an operator-/MSO-confirmed play facility) is matched to the nearest OSM
    rest stop within ``max_distance``:

    * matches an OSM stop **already** flagged  -> annotate play_type/side/verified_source;
    * matches an OSM stop **not** flagged       -> promote it (``has_playground=True``,
      ``match_type=<source>_listed``), keeping the OSM geometry;
    * matches **no** OSM stop                    -> add a synthetic stop at the seed point.

    This is what surfaces indoor soft play — invisible to the OSM spatial join.
    """
    if seed is None or len(seed) == 0:
        return stops

    stops = stops.reset_index(drop=True).copy()
    for col in ("play_type", "side", "verified_source", "last_verified"):
        if col not in stops.columns:
            stops[col] = pd.NA
    by_key = {_key(r): i for i, r in stops.iterrows()}

    rest_all = rest_all.reset_index(drop=True)
    rest_proj = rest_all.to_crs(PROJ)[["geometry"]].copy()
    rest_proj["_ridx"] = range(len(rest_proj))
    seed = seed.reset_index(drop=True)
    nn = gpd.sjoin_nearest(
        seed.to_crs(PROJ), rest_proj, how="left", max_distance=max_distance, distance_col="_d"
    )
    nn = nn[~nn.index.duplicated(keep="first")]

    new_rows: list[dict] = []
    for idx, srow in seed.iterrows():
        s = srow.to_dict()
        source = s.get("verified_source") or "operator"
        mt = f"{source}_listed"
        ridx = nn.loc[idx, "_ridx"] if idx in nn.index else None

        rrow = rest_all.iloc[int(ridx)] if pd.notna(ridx) else None
        # A truck/lorry stop is never the family service a seed listing refers to — don't
        # let an approximate seed coordinate latch onto one; fall through to a synthetic pin.
        if rrow is not None and _is_truckstop(rrow):
            rrow = None

        if rrow is not None:
            key = _key(rrow)
            if key in by_key:  # OSM stop already in the dataset -> annotate
                i = by_key[key]
                cur = stops.at[i, "verified_source"]
                base = cur if isinstance(cur, str) and cur else "osm"  # already OSM-confirmed
                stops.at[i, "play_type"] = s.get("play_type") or "unknown"
                stops.at[i, "side"] = s.get("side") or "unknown"
                stops.at[i, "verified_source"] = _merge_sources(base, source)
                stops.at[i, "last_verified"] = s.get("last_verified")
                continue
            # OSM stop exists but wasn't flagged -> promote it (keep OSM geometry/tags).
            tags = rrow.get("tags") if isinstance(rrow.get("tags"), dict) else {}
            if not tags.get("name") and s.get("name"):
                tags = {**tags, "name": s["name"]}
            new_rows.append(
                {
                    "tags": tags, "type": rrow.get("type"), "id": rrow.get("id"),
                    "geometry": rrow.geometry, "has_playground": True,
                    "playground_count": 0, "match_type": mt,
                    "play_type": s.get("play_type") or "unknown",
                    "side": s.get("side") or "unknown", "verified_source": source,
                    "last_verified": s.get("last_verified"),
                    "motorway_ref": s.get("ref"),
                }
            )
        else:  # no OSM stop nearby -> synthetic stop at the seed location
            new_rows.append(
                {
                    "tags": {"highway": "services", "name": s.get("name")},
                    "type": "seed", "id": s.get("seed_id") or f"{source}-{idx}",
                    "geometry": s["geometry"], "has_playground": True,
                    "playground_count": 0, "match_type": mt,
                    "play_type": s.get("play_type") or "unknown",
                    "side": s.get("side") or "unknown", "verified_source": source,
                    "last_verified": s.get("last_verified"), "motorway_ref": s.get("ref"),
                }
            )

    if new_rows:
        add = gpd.GeoDataFrame(new_rows, geometry="geometry", crs=4326)
        stops = gpd.GeoDataFrame(
            pd.concat([stops, add], ignore_index=True), geometry="geometry", crs=4326
        )
    return stops


def _merge_sources(existing, source: str) -> str:
    have = set() if pd.isna(existing) else {p for p in str(existing).split(";") if p}
    have.add(source)
    return ";".join(sorted(have))


_TRUCKSTOP_HINTS = ("truck", "lorry", "hgv")


def _is_truckstop(row) -> bool:
    tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}
    name = (tags.get("name") or "").lower()
    return any(h in name for h in _TRUCKSTOP_HINTS)
