"""UK facility seed — authoritative *enumerate-then-verify* enrichment.

The dominant UK play format at services is **indoor soft play**, which OSM does not tag as
``leisure=playground`` — so the spatial join is structurally blind to it
(see ``uk_playground_recall_plan.md``). No open, redistributable, machine-readable source
carries the playground signal either (Motorway Services Online / operator pages are
hobbyist/commercial; National Highways is road geometry). So instead of scraping, this is a
small, **hand-curated, attributed** list of well-documented play-equipped UK services.

Each entry is a *fact* ("service X has a play area", citeable to the operator). Coordinates are
approximate and used only to match the nearest OSM rest stop (whose geometry is then kept); the
seed location is the pin only for a site OSM has not mapped at all. Entries are
**documentation-seeded and must be re-confirmed** — see the quarterly refresh note in the plan.
``last_verified`` reflects when this list was compiled, not an independent per-site check.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

# Compilation date of this seed (conservative; drives the staleness downgrade in QA).
SEED_DATE = dt.date(2026, 6, 1)

# name, ref, lat, lon, side, play_type, source
# source: "operator" (operator facility pages) / "mso" (Motorway Services Online listing).
SEED: list[dict] = [
    # Westmorland — indoor AND outdoor play (documented).
    {
        "name": "Tebay Services (northbound)",
        "ref": "M6",
        "lat": 54.4432,
        "lon": -2.5793,
        "side": "NB",
        "play_type": "both",
        "source": "operator",
    },
    {
        "name": "Tebay Services (southbound)",
        "ref": "M6",
        "lat": 54.4358,
        "lon": -2.5862,
        "side": "SB",
        "play_type": "both",
        "source": "operator",
    },
    {
        "name": "Gloucester Services (northbound)",
        "ref": "M5",
        "lat": 51.9466,
        "lon": -2.2336,
        "side": "NB",
        "play_type": "both",
        "source": "operator",
    },
    {
        "name": "Gloucester Services (southbound)",
        "ref": "M5",
        "lat": 51.9386,
        "lon": -2.2447,
        "side": "SB",
        "play_type": "both",
        "source": "operator",
    },
    {
        "name": "Killington Lake Services",
        "ref": "M6",
        "lat": 54.3247,
        "lon": -2.6905,
        "side": "SB",
        "play_type": "both",
        "source": "operator",
    },
    {
        "name": "Cairn Lodge Services",
        "ref": "M74",
        "lat": 55.5004,
        "lon": -3.8003,
        "side": "single",
        "play_type": "both",
        "source": "operator",
    },
    {
        "name": "Gretna Green Services",
        "ref": "A74(M)",
        "lat": 55.0316,
        "lon": -3.0700,
        "side": "single",
        "play_type": "both",
        "source": "operator",
    },
    # Moto — indoor soft play (documented).
    {
        "name": "Leigh Delamere Services (west)",
        "ref": "M4",
        "lat": 51.4993,
        "lon": -2.1583,
        "side": "SB",
        "play_type": "indoor_soft_play",
        "source": "operator",
    },
    {
        "name": "Donington Park Services",
        "ref": "M1",
        "lat": 52.8316,
        "lon": -1.3170,
        "side": "both",
        "play_type": "indoor_soft_play",
        "source": "operator",
    },
    # A-road / other documented.
    {
        "name": "Cornwall Services",
        "ref": "A30",
        "lat": 50.3897,
        "lon": -4.8038,
        "side": "single",
        "play_type": "indoor_soft_play",
        "source": "operator",
    },
    {
        "name": "Chieveley Services",
        "ref": "M4",
        "lat": 51.4736,
        "lon": -1.2876,
        "side": "both",
        "play_type": "indoor_soft_play",
        "source": "mso",
    },
    # Extra — play areas across the chain (documented).
    {
        "name": "Cambridge Services",
        "ref": "A14",
        "lat": 52.2900,
        "lon": -0.0500,
        "side": "both",
        "play_type": "outdoor",
        "source": "operator",
    },
    {
        "name": "Beaconsfield Services",
        "ref": "M40",
        "lat": 51.6087,
        "lon": -0.6360,
        "side": "both",
        "play_type": "outdoor",
        "source": "operator",
    },
    {
        "name": "Cobham Services",
        "ref": "M25",
        "lat": 51.3210,
        "lon": -0.3940,
        "side": "both",
        "play_type": "outdoor",
        "source": "operator",
    },
    {
        "name": "Peterborough Services",
        "ref": "A1(M)",
        "lat": 52.5300,
        "lon": -0.2400,
        "side": "both",
        "play_type": "outdoor",
        "source": "operator",
    },
    {
        "name": "Baldock Services",
        "ref": "A1(M)",
        "lat": 51.9900,
        "lon": -0.1900,
        "side": "both",
        "play_type": "outdoor",
        "source": "operator",
    },
    {
        "name": "Leeds Skelton Lake Services",
        "ref": "M1",
        "lat": 53.7780,
        "lon": -1.4660,
        "side": "both",
        "play_type": "both",
        "source": "operator",
    },
]


def fetch(cache_dir: str | pathlib.Path = "data/raw") -> list[dict]:
    """Return the curated seed; also write a dated snapshot under ``data/raw`` for provenance."""
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    snap = cache_dir / f"uk_facilities_{SEED_DATE.isoformat()}.json"
    if not snap.exists():
        snap.write_text(json.dumps(SEED, indent=2))
    return SEED


def to_points(seed: list[dict]):
    """Convert the seed to the facility GeoDataFrame consumed by ``apply_facility_seed``.

    Columns: ``name, ref, side, play_type, verified_source, seed_id, geometry`` (WGS84).
    """
    import geopandas as gpd
    from shapely.geometry import Point

    records, geoms = [], []
    for i, s in enumerate(seed):
        records.append(
            {
                "name": s["name"],
                "ref": s.get("ref"),
                "side": s.get("side", "unknown"),
                "play_type": s.get("play_type", "unknown"),
                "verified_source": s.get("source", "operator"),
                "seed_id": f"GB-{i}",
                "last_verified": SEED_DATE,
            }
        )
        geoms.append(Point(s["lon"], s["lat"]))
    return gpd.GeoDataFrame(records, geometry=geoms, crs=4326)
