"""CLI orchestration — ``fetch -> build -> export -> validate`` per country.

Bronze/silver/gold layering keeps the pipeline reproducible: ``build`` runs entirely
off cached raw snapshots (no network), so changing a buffer radius never re-hits an API.
Run via ``pixi run all`` or ``python -m restspots.pipeline <cmd> --country DE``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

from . import export as export_mod
from . import join, schema, validate as validate_mod
from .config import CountryConfig, get_country


# --------------------------------------------------------------------------- paths
def _paths(args) -> dict[str, pathlib.Path]:
    return {
        "raw": pathlib.Path(args.raw_dir),
        "interim": pathlib.Path(args.interim_dir),
        "processed": pathlib.Path(args.processed_dir),
    }


def _gold_path(processed: pathlib.Path, country: str) -> pathlib.Path:
    return processed / f"rest_stops_playgrounds_{country}.gold.geojson"


def _latest_raw(raw: pathlib.Path, country: str) -> pathlib.Path:
    """Most recent cached Overpass snapshot for a country (dates sort lexically)."""
    matches = sorted(raw.glob(f"osm_{country}_*.json"))
    if not matches:
        raise FileNotFoundError(
            f"No cached OSM snapshot for {country} in {raw}/. Run `fetch` first."
        )
    return matches[-1]


# ---------------------------------------------------------------------- enrichment
def _gather_enrichment(cfg: CountryConfig, raw_dir: pathlib.Path):
    """Fetch + point-ify every configured connector into one GeoDataFrame, or None."""
    import pandas as pd

    from .enrich import CONNECTORS

    frames = []
    for key in cfg.enrichment:
        if key not in CONNECTORS:
            print(
                f"  ! unknown enrichment connector {key!r}, skipping", file=sys.stderr
            )
            continue
        fetch_fn, to_points = CONNECTORS[key]
        pts = to_points(fetch_fn(str(raw_dir)))
        if len(pts):
            pts = pts.rename(columns={"name": "official_name", "ref": "official_ref"})
            frames.append(pts[["official_name", "official_ref", "geometry"]])
    if not frames:
        return None
    import geopandas as gpd

    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326)


def _gather_facilities(cfg: CountryConfig, raw_dir: pathlib.Path):
    """Fetch + point-ify every configured facility connector into one GeoDataFrame, or None."""
    import geopandas as gpd
    import pandas as pd

    from .enrich import FACILITY_CONNECTORS

    frames = []
    for key in cfg.facilities:
        if key not in FACILITY_CONNECTORS:
            print(f"  ! unknown facility connector {key!r}, skipping", file=sys.stderr)
            continue
        fetch_fn, to_points = FACILITY_CONNECTORS[key]
        pts = to_points(fetch_fn(str(raw_dir)))
        if len(pts):
            frames.append(pts)
    if not frames:
        return None
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326)


# ------------------------------------------------------------------------ commands
def cmd_fetch(args) -> int:
    cfg = get_country(args.country, args.config)
    p = _paths(args)

    if getattr(args, "source", "overpass") == "pbf":
        from . import pbf

        print(f"[fetch] downloading Geofabrik extract for {cfg.iso} -> {p['raw']}/")
        dest = pbf.download_extract(cfg, p["raw"])
        print(f"[fetch] OSM snapshot: {dest}")
    else:
        from . import overpass

        mode = f"{len(cfg.regions)} regions" if cfg.regions else "single query"
        print(f"[fetch] OSM for {cfg.iso} ({mode}) -> {p['raw']}/ via {args.endpoint}")
        _, data = overpass.fetch_country(
            cfg,
            raw_dir=p["raw"],
            endpoint=args.endpoint,
            query_timeout=args.query_timeout,
            read_timeout=args.read_timeout,
        )
        print(f"[fetch] OSM snapshot: {len(data.get('elements', []))} elements")

    if cfg.enrichment:
        print(f"[fetch] enrichment connectors: {', '.join(cfg.enrichment)}")
        _gather_enrichment(cfg, p["raw"])  # warms the per-source caches
    print("[fetch] done.")
    return 0


def _load_layers(args, cfg, p):
    """Return ``(rest, play, motorways, places, snapshot_path, retrieved_at)``.

    Both sources yield rest/play GeoDataFrames with the same ``[tags, type, id, geometry]``
    shape, so everything downstream is source-agnostic. ``motorways`` and ``places`` are
    only available from Path B (used for ref/regional-name fallbacks); both are ``None``
    for the Overpass path.
    """
    if getattr(args, "source", "overpass") == "pbf":
        from . import pbf

        if getattr(args, "pbf", None):
            pbf_path = pathlib.Path(args.pbf)
        else:
            print(f"[build] ensuring Geofabrik extract for {cfg.iso} (large download)")
            pbf_path = pbf.download_extract(cfg, p["raw"])
        print(f"[build] streaming {pbf_path} with pyosmium")
        rest, play, motorways, places = pbf.extract_from_pbf(pbf_path, cfg)
        return rest, play, motorways, places, pbf_path, dt.date.today()

    raw_file = _latest_raw(p["raw"], cfg.iso)
    print(f"[build] reading {raw_file}")
    gdf = join.to_gdf(json.loads(raw_file.read_text()))
    rest, play = join.split_features(gdf)
    return rest, play, None, None, raw_file, _snapshot_date(raw_file)


def cmd_build(args) -> int:
    cfg = get_country(args.country, args.config)
    p = _paths(args)
    rest, play, motorways, places, raw_file, retrieved_at = _load_layers(args, cfg, p)
    print(f"[build] {len(rest)} rest stops, {len(play)} playgrounds")

    stops = join.attach_playgrounds(
        rest,
        play,
        contained_buf=cfg.playground_contained_buffer_m,
        proximity_buf=cfg.playground_proximity_m,
    )
    print(f"[build] {len(stops)} stops with a playground")

    if len(stops):
        import pandas as pd

        ref = pd.Series(pd.NA, index=stops.index, dtype=object)
        # 1) official ref from a national connector (e.g. Autobahn parking_lorry).
        points = _gather_enrichment(cfg, p["raw"]) if cfg.enrichment else None
        if points is not None:
            stops = join.attach_nearest(
                stops, points, ["official_name", "official_ref"], 300.0
            )
            ref = ref.fillna(stops["official_ref"])
        # 2) fallback: ref of the nearest OSM motorway centreline (country-agnostic).
        if motorways is not None and len(motorways):
            stops = join.attach_nearest(
                stops, motorways[["ref", "geometry"]], ["ref"], 300.0, suffix="_osm"
            )
            ref = ref.fillna(stops["ref_osm"])
            n_filled = int(stops["ref_osm"].notna().sum())
            print(f"[build] nearest-motorway ref filled for {n_filled} stops")
        stops["motorway_ref"] = ref

        # Regional name for stops OSM leaves unnamed: the nearest settlement (within 15 km).
        if places is not None and len(places):
            stops = join.attach_nearest(
                stops, places[["place_name", "geometry"]], ["place_name"], 15000.0
            )

    # Authoritative facility seed (e.g. UK indoor soft play): confirm/promote/add stops the
    # OSM spatial join can't see. Runs on the full rest-stop set, so it works even if no OSM
    # playground matched at all.
    if cfg.facilities:
        seed = _gather_facilities(cfg, p["raw"])
        if seed is not None:
            before = len(stops)
            stops = join.apply_facility_seed(rest, stops, seed)
            print(
                f"[build] facility seed: {len(seed)} listings -> stops {before} -> {len(stops)}"
            )

    df = schema.to_canonical(
        stops, cfg.iso, retrieved_at=retrieved_at, labels=cfg.labels
    )
    gold = schema.attach_geometry(df, stops)

    # silver (per-source) and gold (final) outputs.
    p["interim"].mkdir(parents=True, exist_ok=True)
    if len(stops):
        stops.to_file(p["interim"] / f"stops_{cfg.iso}.geojson", driver="GeoJSON")
    p["processed"].mkdir(parents=True, exist_ok=True)
    gold_path = _gold_path(p["processed"], cfg.iso)
    if len(gold):
        gold.to_file(gold_path, driver="GeoJSON")
    else:  # write an empty but valid file so downstream steps don't crash
        gold_path.write_text('{"type":"FeatureCollection","features":[]}')

    _write_metadata(p["processed"], cfg, raw_file, retrieved_at, len(df))
    print(f"[build] wrote gold dataset -> {gold_path} ({len(df)} rows)")
    return 0


def cmd_export(args) -> int:
    cfg = get_country(args.country, args.config)
    p = _paths(args)
    import geopandas as gpd

    gold_path = _gold_path(p["processed"], cfg.iso)
    if not gold_path.exists():
        raise FileNotFoundError(f"{gold_path} missing. Run `build` first.")
    gdf = gpd.read_file(gold_path)
    df = gdf.drop(columns="geometry") if "geometry" in gdf.columns else gdf
    paths = export_mod.write_all(gdf, df, p["processed"], cfg.iso)
    for fmt, path in paths.items():
        print(f"[export] {fmt:8s} -> {path}")
    return 0


def cmd_validate(args) -> int:
    cfg = get_country(args.country, args.config)
    p = _paths(args)
    import geopandas as gpd

    gold_path = _gold_path(p["processed"], cfg.iso)
    if not gold_path.exists():
        raise FileNotFoundError(f"{gold_path} missing. Run `build` first.")
    gdf = gpd.read_file(gold_path)
    df = gdf.drop(columns="geometry") if "geometry" in gdf.columns else gdf
    report = validate_mod.validate(gdf, df, cfg.iso)
    print(json.dumps(report, indent=2, default=str))
    if not report["passed"]:
        print("[validate] FAILED", file=sys.stderr)
        return 1
    print("[validate] OK")
    return 0


# ------------------------------------------------------------------------- helpers
def _snapshot_date(raw_file: pathlib.Path) -> dt.date:
    """Recover the OSM snapshot date from the cached filename, falling back to today."""
    parts = raw_file.stem.split("_")  # osm_DE_2026-06-22_abcd1234
    try:
        return dt.date.fromisoformat(parts[2])
    except (IndexError, ValueError):
        return dt.date.today()


def _write_metadata(processed, cfg, raw_file, retrieved_at, n_rows) -> None:
    meta = {
        "country": cfg.iso,
        "osm_snapshot_date": retrieved_at.isoformat(),
        "raw_source": str(raw_file),
        "enrichment": cfg.enrichment,
        "rows": n_rows,
        "crs_project": join.PROJ,
        "proximity_m": cfg.playground_proximity_m,
        "contained_buffer_m": cfg.playground_contained_buffer_m,
    }
    (processed / f"run_metadata_{cfg.iso}.json").write_text(json.dumps(meta, indent=2))


COMMANDS = {
    "fetch": cmd_fetch,
    "build": cmd_build,
    "export": cmd_export,
    "validate": cmd_validate,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="restspots", description=__doc__)
    parser.add_argument("command", choices=list(COMMANDS), help="pipeline stage to run")
    parser.add_argument(
        "--country", default="DE", help="ISO country code (default: DE)"
    )
    parser.add_argument("--config", default=None, help="path to countries.yml")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--interim-dir", default="data/interim")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Overpass endpoint (default: public API; use 'mirror' for the kumi mirror)",
    )
    parser.add_argument(
        "--query-timeout",
        type=int,
        default=300,
        help="server-side Overpass [timeout:N] in seconds (default: 300)",
    )
    parser.add_argument(
        "--read-timeout",
        type=int,
        default=360,
        help="client HTTP read timeout in seconds; should exceed --query-timeout",
    )
    parser.add_argument(
        "--source",
        choices=["overpass", "pbf"],
        default="overpass",
        help="extraction path: 'overpass' (API, default) or 'pbf' (offline Geofabrik)",
    )
    parser.add_argument(
        "--pbf",
        default=None,
        help="path to a specific .osm.pbf for --source pbf (skips the download)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from .overpass import ENDPOINT, MIRROR

    if args.endpoint is None:
        args.endpoint = ENDPOINT
    elif args.endpoint == "mirror":
        args.endpoint = MIRROR
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
