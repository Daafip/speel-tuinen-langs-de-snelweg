# Speeltuinen langs de snelweg — rest stops with playgrounds

[Google Maps viewer](https://www.google.com/maps/d/viewer?mid=101KH4j_mj8jng7Xi4PlIGAhmR_01HOU)

[OSM map](https://daafip.github.io/speel-tuinen-langs-de-snelweg/)

Find highway rest stops that have a playground and export them as a clean dataset that
drops straight into a Google Maps layer. Ships with **10 countries** (DE, FR, ES, IT, DK,
GB, NL, AT, CH, BE); adding another is a config change, not a rewrite.

OpenStreetMap is the universal backbone (same tags everywhere, free API, full geometry);
national sources such as the **Autobahn GmbH API** are optional enrichment layered on
top. The pipeline is **reproducible by construction**: every external call is a
version-controlled query or a dated, cached snapshot, so transforms re-run offline and
deterministically.

> **Caveat:** OSM playground tagging is incomplete, so *absence of a playground is not
> proof there is none*. This dataset is "known to have a playground per current OSM /
> official data," not an exhaustive negative.

## How it works

```text
EXTRACT (per country)        NORMALIZE → JOIN → ENRICH       MERGE → SCHEMA        EXPORT
  OSM via Overpass (A)   →    rest areas + playgrounds   →   canonical schema  →   GeoJSON  (Maps JS / Datasets)
  OSM via Geofabrik (B)       metric CRS, buffer, sjoin      dedup, sort by id      KML      (My Maps / Earth)
  DE: Autobahn GmbH API       has_playground / match_type                           CSV+WKT  (My Maps / sheets)
   └ data/raw (bronze)         └ data/interim (silver)         └ data/processed (gold) ─┘
```

The bronze/silver/gold layering is what makes it reproducible: re-running the join or
changing a buffer radius never re-hits an API, and any output traces back to a dated raw
snapshot recorded in `run_metadata_<country>.json`.

A rest stop qualifies via one of these rules, recorded in `match_type` for later QA:
`tag` (the stop carries `playground=yes`), `contained` (a playground polygon falls inside
an area-mapped stop), `proximity` (a playground within a buffer of a point-mapped stop —
the common case), or `operator_listed` / `mso_listed` (an authoritative facility listing,
used where OSM is blind — e.g. UK indoor soft play). The `play_type` field
(`outdoor` / `indoor_soft_play` / `both`) and `verified_source` / `last_verified` record
*what kind* of play and *how it was confirmed*.

## Usage

```bash
pixi install                       # installs the geospatial stack from conda-forge

# Germany: use Path B (pyosmium streams the Geofabrik .pbf). A single Overpass query
# for a whole large country times out, so --source pbf is the reliable route.
pixi run python -m restspots.pipeline fetch    --country DE --source pbf   # ~4.8 GB download
pixi run python -m restspots.pipeline build    --country DE --source pbf   # parse + join + enrich
pixi run python -m restspots.pipeline export   --country DE
pixi run python -m restspots.pipeline validate --country DE

# Small countries: the Overpass API path (the default) works fine, no download:
pixi run python -m restspots.pipeline fetch    --country NL
pixi run python -m restspots.pipeline build    --country NL

# Interactive map: a standalone folium/Leaflet HTML you can open in a browser.
pixi run python -m restspots.pipeline map      --country NL    # one country
pixi run map                                                   # --country ALL combined
```

`pixi run all` chains fetch → build → export → validate for the default country (DE, via
Path B). Outputs land in `data/processed/`:
`rest_stops_playgrounds_<C>.geojson` / `.kml` / `.csv` (+ `run_metadata_<C>.json`).

The optional `map` stage reads the gold dataset and writes a self-contained
`rest_stops_playgrounds_<C>.html` (or `rest_stops_playgrounds_map.html` for `ALL`): an
interactive Leaflet map with clustered markers coloured by `play_type` and a popup per
stop. It's a browser companion to the Google exports — no network, gold file only.

The combined EU map is published to **GitHub Pages** by
[`.github/workflows/pages.yml`](.github/workflows/pages.yml): it serves the committed
`rest_stops_playgrounds_map.html` as `index.html` (no rebuild), alongside the per-country
GeoJSON (stable URLs for the Maps-JS `loadGeoJson()` recipe below). Regenerate the map
locally with `pixi run map` and commit it before pushing. Enable Pages once under
**Settings → Pages → Build and deployment → Source: GitHub Actions**; thereafter every
push to `main` that updates that file refreshes the live page.

**Extraction paths**: `--source overpass` (default) hits the Overpass API — quick and
download-free, best for small/medium areas; `--source pbf` parses a dated Geofabrik
`.osm.pbf` with pyosmium — offline, no rate limits, and the only practical route for a
country the size of Germany.

### Adding a country

Add a block to [`config/countries.yml`](config/countries.yml) — the OSM core works
immediately. National enrichment connectors live in
[`src/restspots/enrich/`](src/restspots/enrich/) and implement one tiny interface
(`fetch → raw`, `to_points → GeoDataFrame[name, ref, geometry]`), matched to OSM stops by
nearest neighbour.

## Consuming in Google products

**My Maps does not accept GeoJSON**, so all three formats are produced. My Maps limits:
≤ 2,000 rows/layer, KML/KMZ ≤ 5 MB, CSV ≤ 40 MB (geometry column must be named `WKT`).

- **My Maps (no code):** New layer → Import → upload the **KML** or **CSV** → style by
  `feature_type` or `motorway_ref`.
- **Maps JavaScript API:** host the GeoJSON (e.g. GitHub Pages) and
  `map.data.loadGeoJson('…/rest_stops_playgrounds_DE.geojson')`.
- **Datasets API:** upload the same GeoJSON as a dataset and reference its ID in a
  data-driven layer.

## Licensing

Data is derived from OpenStreetMap (**ODbL** — "© OpenStreetMap contributors", share-alike
may apply) and national open data. See [ATTRIBUTION.md](ATTRIBUTION.md) before publishing.

## Development with Pixi

The environment is managed with [Pixi](https://pixi.sh); `pixi.lock` pins the exact
geospatial stack (GDAL/GEOS/PROJ via conda-forge) for reproducibility.

<details>
<summary>Install Pixi</summary>

```bash
# Linux/Mac
curl -fsSL https://pixi.sh/install.sh | bash
# Windows (PowerShell)
iwr -useb https://pixi.sh/install.ps1 | iex
```

</details>

```bash
pixi install        # create the environment from pixi.lock
pixi run test       # run the test suite (pytest)
pixi run pre-commit # lint/format via pre-commit
```

This Speeltuinen langs de snelweg is developed by David Haasnoot, based heavily on other
open source projects, and is published under the GNU GPL-3 license.
