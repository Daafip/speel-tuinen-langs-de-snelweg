# Rest Stops with Playgrounds — Data Pipeline Implementation Plan

**Goal:** Build a reproducible, free-to-run Python pipeline that finds highway rest stops with playgrounds and exports a single, clean dataset that drops straight into a Google Maps layer. Start with Germany; design every component so adding a new country is a config change, not a rewrite.

**Design principles**

1. **OpenStreetMap is the universal backbone.** It has the same tags in every country, a free query API, and full geometry. Everything else is *optional enrichment* layered on top.
2. **Reproducible by construction.** Every external call is a version-controlled query or a dated snapshot. Raw responses are cached so transforms can be re-run offline and deterministically.
3. **One canonical schema, many export formats.** The internal model never changes; only the serializer differs per Google product.
4. **Country-agnostic core + pluggable per-country connectors.** Germany ships first; the same core produces a working dataset for any other country on day one (OSM only), with official national sources bolted on later.

---

## 1. Architecture overview

```
                 ┌─────────────────────────────────────────────┐
                 │            EXTRACT  (per country)            │
                 │                                              │
   OSM ──────────┤  A) Overpass API   (quick, iterative)        │
   (backbone)    │  B) Geofabrik .pbf (dated, offline, scales)  │
                 │                                              │
   National ─────┤  DE: Autobahn GmbH API (parking_lorry)       │
   enrichment    │  NL: RWS/NDW · AT: ASFINAG · FR: data.gouv … │
                 └───────────────────────┬─────────────────────┘
                                         │  raw/  (bronze: dated JSON/pbf)
                                         ▼
                 ┌─────────────────────────────────────────────┐
                 │   NORMALIZE → SPATIAL JOIN → ENRICH          │
                 │   • rest areas + playgrounds → GeoDataFrame  │
                 │   • metric CRS, buffer, sjoin                │
                 │   • has_playground / count / match_type      │
                 │   • attach motorway ref + official name      │
                 └───────────────────────┬─────────────────────┘
                                         │  interim/ (silver: per-source GeoJSON)
                                         ▼
                 ┌─────────────────────────────────────────────┐
                 │   MERGE → CANONICAL SCHEMA → DEDUP           │
                 └───────────────────────┬─────────────────────┘
                                         │  processed/ (gold: final dataset)
                                         ▼
                 ┌─────────────────────────────────────────────┐
                 │   EXPORT                                     │
                 │   • GeoJSON  → Maps JS Data layer / Datasets │
                 │   • KML      → My Maps / Google Earth        │
                 │   • CSV+WKT  → My Maps / spreadsheets        │
                 └─────────────────────────────────────────────┘
```

The bronze/silver/gold layering is what makes the whole thing reproducible: re-running the join or changing the buffer radius never re-hits an API, and a result can always be traced back to a dated raw snapshot.

---

## 2. Data sources

| Source | Provides | Access | Reproducible | License | Role |
|---|---|---|---|---|---|
| **OSM via Overpass API** | `highway=services`, `highway=rest_area`, `leisure=playground` with geometry + tags | Free REST, no key | Pin the `.overpassql` query; cache raw JSON | ODbL | **Primary** — finds both the stops and the playgrounds, everywhere |
| **OSM via Geofabrik extract** | Same data, as a dated `germany-latest.osm.pbf` | Free download | The dated `.pbf` *is* the snapshot | ODbL | Production / offline / scales to all of Europe; no rate limits |
| **Autobahn GmbH API** | Official Rastplätze per motorway (name, coords, road ref), plus EV chargers, webcams | Free REST, no key, CORS on. Base: `https://verkehr.autobahn.de/o/autobahn` | Endpoints are stable; cache responses | German federal open data (verify current terms, attribute) | **DE enrichment** — official name + motorway ref to attach to OSM stops |
| **Wikidata (SPARQL)** | Some named service areas, operators, Wikipedia links | Free SPARQL endpoint | Pin the SPARQL query | CC0 | Optional enrichment (names, operators) |
| **National sources (expansion)** | NL: RWS/NDW *verzorgingsplaatsen*; AT: ASFINAG; FR: data.gouv / APRR *aires*; CH: opendata.swiss | Mostly free/open | Per-source caching | Varies — check each | Per-country enrichment, added incrementally |

### Defining "a rest stop with a playground"

A feature qualifies if **any** of the following holds (recorded in `match_type` so you can audit/filter later):

- **tag** — the rest area itself carries `playground=yes` (authoritative but rare).
- **contained** — a `leisure=playground` geometry falls inside the rest area polygon (strong; available where the stop is mapped as an area).
- **proximity** — a playground lies within a small buffer of a rest area that is only mapped as a point (the common case; record the distance so urban false-positives can be screened).

Two relevant OSM stop types: `highway=services` are the large Autobahn service areas (fuel, restaurant) and are the most likely to have a playground; `highway=rest_area` (Rastplatz) are simpler stops that sometimes do. Capture both.

---

## 3. Environment (Pixi)

Pixi/conda-forge is recommended over plain pip here because the geospatial stack (GDAL, GEOS, PROJ behind GeoPandas/pyrosm) installs cleanly from conda-forge and the `pixi.lock` file pins the *exact* environment — a big reproducibility win.

```toml
# pixi.toml
[project]
name = "restspots-playgrounds"
channels = ["conda-forge"]
platforms = ["linux-64", "win-64", "osx-arm64"]

[dependencies]
python      = ">=3.11"
geopandas   = "*"        # shapely, pyproj, fiona/pyogrio, GDAL come with it
shapely     = "*"
pyproj      = "*"
pandas      = "*"
requests    = "*"
pyrosm      = "*"        # offline .pbf parsing (Path B)
osm2geojson = "*"        # Overpass JSON -> GeoJSON
simplekml   = "*"        # reliable KML writer
pyyaml      = "*"
osmnx       = "*"        # optional convenience wrapper for Overpass
tqdm        = "*"

[tasks]
fetch    = "python -m restspots.pipeline fetch    --country DE"
build    = "python -m restspots.pipeline build    --country DE"
export   = "python -m restspots.pipeline export   --country DE"
validate = "python -m restspots.pipeline validate --country DE"
all      = { depends-on = ["fetch", "build", "export", "validate"] }
```

`simplekml` is preferred for KML over GeoPandas' KML driver, which is inconsistent across GDAL builds.

---

## 4. Repository layout

```
restspots-playgrounds/
├── pixi.toml / pixi.lock
├── README.md
├── LICENSE / ATTRIBUTION.md          # OSM ODbL + per-source attributions
├── config/
│   └── countries.yml                 # bbox/area, tags, buffers, enrichment toggles
├── queries/
│   ├── rest_and_playgrounds_DE.overpassql
│   └── service_areas.sparql          # optional Wikidata
├── data/
│   ├── raw/        # bronze: dated API dumps + .pbf snapshots
│   ├── interim/    # silver: normalized per-source GeoJSON
│   └── processed/  # gold: final merged outputs (the deliverables)
├── src/restspots/
│   ├── config.py      # load countries.yml
│   ├── overpass.py     # Path A: query + cache
│   ├── pbf.py          # Path B: pyrosm extract
│   ├── autobahn.py     # DE enrichment connector
│   ├── enrich/         # one module per country connector
│   ├── join.py         # spatial join → has_playground
│   ├── schema.py       # canonical schema + validation
│   ├── export.py       # GeoJSON / KML / CSV writers
│   └── pipeline.py     # CLI orchestration
├── tests/
└── notebooks/          # QA / map previews
```

Config-driven so a new country is a YAML block:

```yaml
# config/countries.yml
DE:
  iso: DE
  osm_area: '["ISO3166-1"="DE"][admin_level=2]'
  geofabrik_url: https://download.geofabrik.de/europe/germany-latest.osm.pbf
  stop_tags:
    highway: [services, rest_area]
  playground_proximity_m: 200      # buffer for point-mapped stops
  playground_contained_buffer_m: 50
  enrichment: [autobahn_api]
NL:
  iso: NL
  osm_area: '["ISO3166-1"="NL"][admin_level=2]'
  geofabrik_url: https://download.geofabrik.de/europe/netherlands-latest.osm.pbf
  stop_tags:
    highway: [services, rest_area]
  playground_proximity_m: 200
  playground_contained_buffer_m: 50
  enrichment: [rws_ndw]            # added in a later phase; OSM core works now
```

---

## 5. Phase 1 — Acquire (Germany)

### Path A — Overpass API (fast, iterative)

Pre-filtering playgrounds to those near a rest area (`around.rest:300`) keeps the query light instead of pulling every playground in Germany.

```overpassql
/* queries/rest_and_playgrounds_DE.overpassql */
[out:json][timeout:300];
area["ISO3166-1"="DE"][admin_level=2]->.de;
(
  nwr["highway"="services"](area.de);
  nwr["highway"="rest_area"](area.de);
)->.rest;
(
  nwr["leisure"="playground"](around.rest:300);
)->.play;
.rest out geom;
.play out geom;
```

```python
# src/restspots/overpass.py
import datetime as dt, hashlib, json, pathlib, requests

ENDPOINT = "https://overpass-api.de/api/interpreter"   # or a mirror
HEADERS  = {"User-Agent": "restspots-playgrounds/0.1 (contact: you@example.com)"}

def run_overpass(query: str, country: str, raw_dir="data/raw") -> dict:
    """POST a query, cache the raw JSON under a dated, content-hashed name."""
    stamp = dt.date.today().isoformat()
    qhash = hashlib.sha1(query.encode()).hexdigest()[:8]
    out = pathlib.Path(raw_dir) / f"osm_{country}_{stamp}_{qhash}.json"
    if out.exists():                       # idempotent: never re-hit if cached
        return json.loads(out.read_text())
    resp = requests.post(ENDPOINT, data={"data": query}, headers=HEADERS, timeout=360)
    resp.raise_for_status()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(resp.text)
    return resp.json()
```

Etiquette: set a descriptive `User-Agent`, keep a generous `timeout`, and don't loop the public endpoint. If you query repeatedly, use a mirror (`https://overpass.kumi.systems/api/interpreter`) or switch to Path B.

### Path B — Geofabrik extract (versioned, offline, scales)

For production and for the eventual all-Europe run, download a dated `.osm.pbf` and parse it locally with `pyrosm`. The file *is* the reproducible snapshot — no rate limits, no API drift.

```python
# src/restspots/pbf.py
from pyrosm import OSM

def extract_from_pbf(pbf_path: str):
    osm = OSM(pbf_path)
    rest = osm.get_data_by_custom_criteria(
        custom_filter={"highway": ["services", "rest_area"]},
        filter_type="keep", keep_nodes=True, keep_ways=True, keep_relations=True,
    )
    play = osm.get_data_by_custom_criteria(
        custom_filter={"leisure": ["playground"]},
        filter_type="keep", keep_nodes=True, keep_ways=True, keep_relations=True,
    )
    return rest, play   # already GeoDataFrames
```

Record the Geofabrik file's date in the run metadata so any output is traceable to a specific OSM snapshot.

### Autobahn GmbH API (DE enrichment)

The road list comes from the base endpoint; `…/services/parking_lorry` returns the official Rastplätze for each road, which we later match spatially to the OSM stops to attach an official name + motorway ref.

```python
# src/restspots/autobahn.py
import requests
BASE = "https://verkehr.autobahn.de/o/autobahn"

def list_roads() -> list[str]:
    return requests.get(f"{BASE}/", timeout=30).json()["roads"]

def rest_areas(road: str) -> list[dict]:
    r = requests.get(f"{BASE}/{road}/services/parking_lorry", timeout=30)
    return r.json().get("parking_lorry", []) if r.ok else []
```

(Cache each road's response under `data/raw/` exactly as with Overpass. Note the list contains a combined `"A1/A59"` entry that the per-road endpoints reject — skip it.)

---

## 6. Phase 2 — Normalize & spatial join

Convert Overpass JSON to GeoJSON (`osm2geojson`), load both layers into GeoPandas, reproject to a metric CRS, buffer, and join. **Project CRS: EPSG:3035** (LAEA Europe, equal-area) so multi-country merges later stay consistent; EPSG:25832 (UTM32N) is fine if you stay strictly inside Germany.

```python
# src/restspots/join.py
import geopandas as gpd
from osm2geojson import json2geojson

PROJ = 3035  # pan-European metric CRS

def to_gdf(overpass_json) -> gpd.GeoDataFrame:
    fc = json2geojson(overpass_json)
    return gpd.GeoDataFrame.from_features(fc["features"], crs=4326)

def attach_playgrounds(rest: gpd.GeoDataFrame, play: gpd.GeoDataFrame,
                       contained_buf=50, proximity_buf=200) -> gpd.GeoDataFrame:
    rest_m = rest.to_crs(PROJ).copy()
    play_m = play.to_crs(PROJ).copy()

    # Polygons get a small edge buffer; point-mapped stops get a larger one.
    def buf(g):
        return g.buffer(contained_buf) if g.geom_type in ("Polygon", "MultiPolygon") \
               else g.buffer(proximity_buf)
    rest_m["_zone"] = rest_m.geometry.apply(buf)

    zones = rest_m.set_geometry("_zone")[["_zone"]]
    play_pts = play_m.copy()
    play_pts["geometry"] = play_pts.geometry.centroid           # point-in-zone test

    hits = gpd.sjoin(play_pts, zones, predicate="within", how="inner")
    counts = hits.groupby(hits.index_right).size()

    rest_m["playground_count"] = counts.reindex(rest_m.index).fillna(0).astype(int)
    tagged = rest_m["tags"].apply(lambda t: isinstance(t, dict) and t.get("playground") == "yes")
    rest_m["has_playground"] = (rest_m["playground_count"] > 0) | tagged
    rest_m["match_type"] = rest_m.apply(
        lambda r: "tag" if tagged[r.name]
                  else ("contained" if r.geometry.geom_type.endswith("Polygon") and r.playground_count
                        else ("proximity" if r.playground_count else None)),
        axis=1,
    )
    return rest_m[rest_m["has_playground"]].to_crs(4326)
```

Keep only `has_playground` rows for the final product, but retain `match_type` and (optionally) the nearest-playground distance so urban false-positives from the proximity rule can be screened during QA.

---

## 7. Phase 3 — Enrich & canonical schema

**Attach motorway ref** with a nearest-feature join to `highway=motorway` ways (country-agnostic), and **attach official name/ref** with a nearest match to the Autobahn `parking_lorry` points (DE only):

```python
ref = gpd.sjoin_nearest(rest_m, motorways[["ref", "geometry"]],
                        how="left", max_distance=300, distance_col="d_road")
```

### Canonical schema (`src/restspots/schema.py`)

| Field | Type | Notes |
|---|---|---|
| `id` | str | Stable OSM id, e.g. `way/12345` |
| `name` | str | OSM name, falling back to Autobahn official name |
| `country` | str | ISO 3166-1 alpha-2 |
| `lat`, `lon` | float | WGS84 centroid (for CSV/Maps point placement) |
| `feature_type` | str | `services` / `rest_area` |
| `motorway_ref` | str | e.g. `A7` |
| `has_playground` | bool | Always `true` in the deliverable |
| `playground_count` | int | Distinct playgrounds matched |
| `match_type` | str | `tag` / `contained` / `proximity` |
| `toilets`, `restaurant`, `fuel`, `cafe`, `picnic`, `wheelchair` | bool | Parsed from tags (family-relevant amenities) |
| `source` | str | `osm` (+ `autobahn` / `wikidata` if enriched) |
| `osm_url` | str | `https://www.openstreetmap.org/{type}/{id}` |
| `data_retrieved_at` | date | OSM snapshot date (provenance) |

**Dedup / grouping:** a divided motorway often has two physically separate stops (one per direction) — keep both, but you can group by normalized `name + motorway_ref` for a "site" view. Drop exact-duplicate ids from any `services`/`rest_area` overlap.

---

## 8. Phase 4 — Export & Google Maps integration

This is the step where the Google-product split matters. **My Maps does not accept GeoJSON.** Produce all three formats so any consumption path works:

| Format | File | Consumes into |
|---|---|---|
| **GeoJSON** (RFC 7946) | `rest_stops_playgrounds_DE.geojson` | Maps **JavaScript API** Data layer; Maps **Datasets API**; Leaflet/Mapbox/GIS |
| **KML** | `rest_stops_playgrounds_DE.kml` | Google **My Maps**; Google **Earth** |
| **CSV + WKT** | `rest_stops_playgrounds_DE.csv` | Google **My Maps**; spreadsheets |

Google limits to respect: **My Maps** — ≤ 2,000 rows per layer, KML/KMZ ≤ 5 MB, CSV ≤ 40 MB; column must be named `WKT` (or supply `latitude`/`longitude`). **Datasets API** — up to 500 MB, no 3-D/`Z` geometries. For Germany the count of stops *with playgrounds* is well under 2,000, so a single My Maps layer is fine; for the all-Europe expansion, split CSV/KML by country or region to stay under the row cap.

```python
# src/restspots/export.py
import simplekml

def write_geojson(gdf, path):                       # for JS API / Datasets API
    gdf.to_file(path, driver="GeoJSON")

def write_csv_wkt(gdf, path):                       # for My Maps / sheets
    df = gdf.copy()
    df["WKT"] = df.geometry.apply(lambda g: g.wkt)  # column MUST be named "WKT"
    df["latitude"], df["longitude"] = df.geometry.centroid.y, df.geometry.centroid.x
    df.drop(columns="geometry").to_csv(path, index=False)

def write_kml(gdf, path):                           # for My Maps / Earth
    k = simplekml.Kml()
    for _, r in gdf.iterrows():
        p = k.newpoint(name=r["name"] or "Rest stop", coords=[(r["lon"], r["lat"])])
        p.description = (f"Motorway: {r['motorway_ref']}\n"
                         f"Playgrounds: {r['playground_count']}\n"
                         f"Type: {r['feature_type']}\n{r['osm_url']}")
    k.save(path)   # KML uses lon,lat order — handled here
```

**Consumption recipes**

*My Maps (no code):* New layer → Import → upload the **KML** or **CSV** (tick the `WKT` column if CSV) → style by `feature_type` or `motorway_ref`.

*Maps JavaScript API (hosted GeoJSON):*

```js
map.data.loadGeoJson('https://<your-username>.github.io/restspots/rest_stops_playgrounds_DE.geojson');
map.data.setStyle(f => ({
  title: f.getProperty('name'),
  icon: f.getProperty('playground_count') > 1 ? bigIcon : smallIcon,
}));
```

Publishing the GeoJSON to **GitHub Pages** (next phase) gives it a stable URL for `loadGeoJson`. *Maps Datasets API:* upload the same GeoJSON as a dataset and reference its dataset ID in a styled data-driven layer.

---

## 9. Phase 5 — Validation & QA

Programmatic checks before publishing:

- **Counts & coverage** — total stops, % with playgrounds, breakdown by `match_type` and `motorway_ref`; flag anomalies (e.g. a sudden drop vs. the previous run signals upstream tag changes).
- **Geometry validity** — `gdf.geometry.is_valid.all()`, no empty/null geometries, coordinates within the country bbox.
- **Proximity audit** — list `match_type == proximity` rows sorted by distance; eyeball the closest-to-settlement ones for false positives.
- **Spot checks** — verify a handful of known family service areas appear (cross-check against the Autobahn `parking_lorry` list).
- **Map preview** — render to an interactive map in a notebook before export.

**Acceptance criteria for v1 (DE):** geometries valid; every row has `name` or `motorway_ref`; ≥ 1 export per format opens cleanly in its target product; a manual sample of 10 stops is correct.

**Standing caveat (document it in the README):** OSM playground tagging is incomplete, so *absence of a playground is not proof there is none*. The dataset is "known to have a playground per current OSM/official data," not an exhaustive negative.

---

## 10. Phase 6 — Automation & reproducibility

- **Orchestration:** `pixi run all` chains fetch → build → export → validate; the CLI takes `--country`.
- **Scheduled refresh (GitHub Actions, monthly):**

```yaml
# .github/workflows/refresh.yml
name: refresh-restspots
on:
  schedule: [{ cron: "0 3 1 * *" }]   # 1st of each month
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: prefix-dev/setup-pixi@v0
      - run: pixi run all
      - uses: actions/upload-artifact@v4
        with: { name: restspots-DE, path: data/processed/ }
      # optionally publish data/processed/*.geojson to GitHub Pages for a stable URL
```

- **Data versioning:** raw snapshots are dated; record the OSM snapshot date and source endpoints in a `run_metadata.json` beside each output. (Add DVC later if you want to version the large `.pbf`/processed files outside git.)
- **Determinism:** sort rows by `id` before writing, pin the env via `pixi.lock`, and keep all parameters in `countries.yml` so a re-run on the same snapshot is byte-stable.

---

## 11. Phase 7 — Expansion roadmap

The OSM core already works for any country the moment you add a YAML block — `highway=services` / `rest_area` and `leisure=playground` are global tags. National connectors are added incrementally only to improve names/refs.

| Country | OSM core | Official enrichment | Local term |
|---|---|---|---|
| 🇩🇪 Germany | ✅ shipped | Autobahn GmbH API (`parking_lorry`) | Raststätte / Rastplatz |
| 🇳🇱 Netherlands | works now | RWS / NDW open data | verzorgingsplaats |
| 🇦🇹 Austria | works now | ASFINAG open data | Raststation / Rastplatz |
| 🇫🇷 France | works now | data.gouv.fr / APRR / Sanef | aire de repos / aire de service |
| 🇨🇭 Switzerland | works now | opendata.swiss / ASTRA | Raststätte / Rastplatz |
| 🇧🇪 Belgium | works now | regional open-data portals | parking / aire |

Each connector implements the same tiny interface — `fetch(country) -> raw`, `to_points(raw) -> GeoDataFrame[name, ref, geometry]` — and is matched to OSM stops by nearest-neighbour. Because everything shares EPSG:3035, ISO country codes, and the canonical schema, the per-country gold files concatenate into one `rest_stops_playgrounds_EU.geojson` with no reconciliation work. (At EU scale, switch the default extraction to Path B and split the My Maps exports per country to respect the 2,000-row limit.)

---

## 12. Licensing & attribution

- **OSM is ODbL.** Any published map or derived dataset must show **"© OpenStreetMap contributors"**, and the share-alike clause can apply to a redistributed derived *database* — keep an `ATTRIBUTION.md` and add the credit to the map UI.
- **Autobahn GmbH data** is German federal open data; confirm the current licence on the API page and attribute accordingly.
- **Wikidata is CC0** (no attribution required, but nice to note).
- Verify each national source's licence as you add it; record all of them in one file.

---

## 13. Risks, limitations, mitigations

| Risk | Mitigation |
|---|---|
| OSM playgrounds under-tagged → missed stops | Treat output as a positive list, not exhaustive; refresh monthly; cross-check official sources |
| Proximity rule false-positives near towns | Keep buffer ≤ 200 m; record distance + `match_type`; QA the closest-to-settlement matches |
| Overpass rate limits / timeouts | Cache raw responses; use a mirror; switch to dated Geofabrik `.pbf` for production |
| Divided-highway duplicate stops | Keep per-direction features but expose a grouped "site" view by name + ref |
| Inconsistent names across sources | Prefer official name where matched; normalize before grouping |
| Google My Maps row/size limits | Single layer for DE (well under 2,000); split per country/region at EU scale |
| GeoJSON rejected by My Maps | Always ship KML + CSV alongside GeoJSON |

---

## 14. Suggested milestones

1. **M1 — Skeleton:** repo, `pixi.toml`, `countries.yml` (DE), Overpass query committed; `fetch` caches raw OSM + Autobahn JSON.
2. **M2 — Core join:** normalize → buffer → sjoin → `has_playground`; produces a silver GeoJSON for DE.
3. **M3 — Enrich + schema:** motorway ref + official names; canonical gold dataset.
4. **M4 — Exports:** GeoJSON / KML / CSV all opening cleanly in their targets; My Maps + JS-API recipes verified.
5. **M5 — QA + automation:** validation suite, monthly GitHub Action, GitHub Pages-hosted GeoJSON.
6. **M6 — Expansion:** add NL (OSM core + RWS/NDW connector) as the proof that a new country is a config + one connector.
