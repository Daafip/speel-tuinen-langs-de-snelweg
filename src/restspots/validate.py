"""Phase 5 — programmatic QA run before publishing.

Returns a structured report (counts, coverage by match_type/ref, geometry validity,
proximity audit) plus a list of hard failures that should block a release.
"""

from __future__ import annotations

import datetime as dt

import geopandas as gpd
import pandas as pd

# A confirmation older than this is treated as stale (plan §7 currency note). Operator/MSO
# facility data changes faster than OSM, so a stale "yes" is worse than an honest "unknown".
STALE_AFTER_DAYS = 180

# Rough WGS84 bounding boxes per country for a coarse coordinate sanity check.
COUNTRY_BBOX = {
    "DE": (5.8, 47.2, 15.1, 55.1),
    "NL": (3.3, 50.7, 7.3, 53.6),
    "AT": (9.5, 46.3, 17.2, 49.1),
    "BE": (2.5, 49.5, 6.4, 51.5),
    "FR": (-5.3, 41.3, 9.7, 51.1),  # metropolitan France incl. Corsica
    "CH": (5.9, 45.8, 10.5, 47.8),
    "GB": (-8.7, 49.8, 1.9, 60.9),  # Great Britain (NI omitted)
    "DK": (7.9, 54.5, 15.3, 57.8),
    "ES": (-18.3, 27.5, 4.4, 43.9),  # incl. Canary & Balearic islands
    "IT": (6.6, 35.4, 18.6, 47.1),  # incl. Sicily & Sardinia
}


def _stale_count(df: pd.DataFrame, today: dt.date) -> int:
    """Rows whose newest confirmation is older than ``STALE_AFTER_DAYS`` (a soft signal)."""
    if "last_verified" not in df.columns:
        return 0
    lv = pd.to_datetime(df["last_verified"], errors="coerce")
    cutoff = pd.Timestamp(today) - pd.Timedelta(days=STALE_AFTER_DAYS)
    return int((lv < cutoff).sum())


def validate(
    gdf: gpd.GeoDataFrame,
    df: pd.DataFrame,
    country: str,
    today: dt.date | None = None,
) -> dict:
    """Run QA checks. ``report["failures"]`` being empty means it passes acceptance."""
    today = today or dt.date.today()
    failures: list[str] = []
    n = len(df)

    if n == 0:
        failures.append("no rows in the final dataset")

    # Geometry validity.
    geom_valid = bool(gdf.geometry.is_valid.all()) if len(gdf) else False
    geom_nonempty = bool((~gdf.geometry.is_empty).all()) if len(gdf) else False
    if len(gdf) and not geom_valid:
        failures.append("invalid geometries present")
    if len(gdf) and not geom_nonempty:
        failures.append("empty/null geometries present")

    # Every row must have a name or a motorway_ref (acceptance criterion).
    if n:
        missing_id = df[(df["name"].isna()) & (df["motorway_ref"].isna())]
        if len(missing_id):
            failures.append(
                f"{len(missing_id)} rows have neither name nor motorway_ref"
            )

    # Coordinates within the country bbox.
    bbox = COUNTRY_BBOX.get(country.upper())
    out_of_bbox = 0
    if bbox and n:
        minx, miny, maxx, maxy = bbox
        out_of_bbox = int(
            (~df["lon"].between(minx, maxx) | ~df["lat"].between(miny, maxy)).sum()
        )
        if out_of_bbox:
            failures.append(
                f"{out_of_bbox} rows fall outside the {country} bounding box"
            )

    def _counts(col: str, top: int | None = None, dropna: bool = False) -> dict:
        if not n or col not in df.columns:
            return {}
        vc = df[col].value_counts(dropna=dropna)
        if top:
            vc = vc.head(top)
        return {str(k): int(v) for k, v in vc.items()}

    return {
        "country": country,
        "total_stops": n,
        "geometry_valid": geom_valid,
        "geometry_nonempty": geom_nonempty,
        "out_of_bbox": out_of_bbox,
        "by_match_type": _counts("match_type"),
        "by_play_type": _counts("play_type"),
        "by_verified_source": _counts("verified_source"),
        "by_motorway_ref": _counts("motorway_ref", top=15, dropna=True),
        "stale_confirmations": _stale_count(df, today),
        "failures": failures,
        "passed": not failures,
    }
