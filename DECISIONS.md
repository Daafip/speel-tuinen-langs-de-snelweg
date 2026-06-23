# Decisions, Improvements & Outlook

Companion to [`plan.md`](plan.md) and [`expansion_plans_UK_DK_ES_IT.md`](expansion_plans_UK_DK_ES_IT.md).
This records *what was actually built and why* — especially where reality diverged from the
original plan — plus improvements made and what to watch next.

**Status:** OSM-only core shipped for **10 countries**, all validating. Counts (stops with a
playground, current snapshot):

| | stops | | stops | | stops |
|---|---|---|---|---|---|
| 🇫🇷 FR | 384 | 🇩🇰 DK | 61 | 🇳🇱 NL | 31 |
| 🇩🇪 DE | 340 | 🇬🇧 GB | 44 | 🇦🇹 AT | 31 |
| 🇪🇸 ES | 131 | | | 🇨🇭 CH | 29 |
| 🇮🇹 IT | 114 | | | 🇧🇪 BE | 20 |

≈ **1,185** rest stops with playgrounds. Each exported to GeoJSON / KML / CSV in
[`data/processed/`](data/processed/) with `run_metadata_<C>.json` for provenance.

---

## Decisions

ADR-style: each is *context → decision → why*. Numbered for reference.

### D1 — Parser: `pyosmium` (streaming), not `pyrosm`
The plan specified `pyrosm` for Path B. In practice `pyrosm` materialises the whole PBF in
memory: **~25 GB peak to parse a single German state**, and it crashed outright on the 4.8 GB
Germany extract (took the IDE down with it). **Switched to `pyosmium`**, which streams with a
compact node-location index and filters tags in C++ (`osmium.filter.KeyFilter`). Result: all of
Germany in one pass at **~1–3 GB peak**. `pyrosm` was removed from the environment.
See [`src/restspots/pbf.py`](src/restspots/pbf.py).

### D2 — Extraction path: Path B (`.pbf`) is the default for large countries
A single Overpass query for a whole large country **times out** — Germany returned `504`
on the public API *and* the kumi mirror; the Netherlands returned a 200 with an empty body and
a `remark: "Query timed out"`. Per-Bundesland Overpass splitting also throttled out. **Decision:
Path B (dated Geofabrik `.pbf` + pyosmium) is the reliable route for anything country-sized;**
Overpass (Path A) stays the default only for small/iterative use. The CI workflow
([`.github/workflows/refresh.yml`](.github/workflows/refresh.yml)) was switched to `--source pbf`.

### D3 — Relations are skipped
`extract_from_pbf` captures nodes and ways only. Verified on Belgium: just **3** relation-mapped
stops and **39** relation playgrounds out of thousands — not worth the multipolygon-assembly
complexity. Documented as a known, negligible omission.

### D4 — Unnamed stops get a *regional, localized* name
The first fallback used a generic German term ("Rastplatz") for every country — wrong for Dutch
stops. **Decision: name unnamed stops `"<localized term> <nearest town>"`** (e.g.
`Verzorgingsplaats Apeldoorn`, `Rastplatz Aachen`, `Aire de repos Sainte-Marie`). The term comes
from a per-country `labels:` map in [`config/countries.yml`](config/countries.yml); the town is the
nearest OSM `place=` settlement (≤ 15 km) extracted in the same pyosmium pass. Falls back to the
bare term, then to English `Rest area` / `Services` if a country has no labels.
See `_fallback_name` in [`src/restspots/schema.py`](src/restspots/schema.py).

### D5 — `ref_road_tags` is configurable (plan §B1)
Hard-coding `highway=motorway` for the nearest-ref fallback missed stops on **trunk roads**
(common in UK/IT/ES, also DK). Added a per-country `ref_road_tags` (default `[motorway]`;
GB/DK/ES/IT use `[motorway, trunk]`). Original countries keep motorway-only so their validated
outputs are unchanged. Confirmed working (DK picked up trunk ref `501`; GB picked up `A58`/`A605`).

### D6 — Two ref/name fallbacks, in order
For each stop: (1) official ref/name from a national connector (Germany's Autobahn `parking_lorry`),
then (2) the `ref` of the nearest OSM road in `ref_road_tags` (≤ 300 m, country-agnostic). DE
ref coverage went 274/340 via the OSM-motorway fallback alone.

### D7 — UK = `great-britain` only; Northern Ireland omitted
The plan (§B3) wanted GB = `great-britain` **+** `ireland-and-northern-ireland`, clipped to the
GB boundary. Pulling the Ireland extract **without** boundary-clipping would contaminate the
dataset with the Republic of Ireland. **Decision: use `great-britain` only and document NI as a
known omission** (few MSAs, not worth the boundary-clip machinery yet). Cleaner than wrong data.

### D8 — No national enrichment connectors were built (beyond Germany's Autobahn)
The plan lists optional connectors for NL/AT/FR/CH/BE/GB/DK/ES/IT. Research found that **the open
datasets do not carry the playground signal**:
- **France** — VINCI Autoroutes publishes only *carpool* parkings on data.gouv.fr; amenity data
  ("aire de jeux") lives on operator route-planner sites, not open/redistributable.
- **Belgium** — AWV (Flanders) / SPW (Wallonia) publish road/truck-parking layers, no playground.
- **UK** — National Highways open data is road-network geometry (England-only); its facilities
  list is non-geocoded with no playground field. Geocoded MSA lists exist only commercially
  (ScrapeHero/LocationsCloud — not ODbL-compatible).
**Decision: stay OSM-only.** Connectors could still add official *names/refs*, but not density.
The one genuinely high-value connector remaining is **ES IGN IGR-RT** (ships real geometry) — see Outlook.

### D9 — Wikidata for the UK: checked, rejected
Tested directly (the user asked to verify before implementing). Wikidata has **97 UK MSAs, all
with coordinates, but no playground attribute**. Anchoring on those coordinates surfaces an OSM
playground for only **11** (within 200 m) / 19 (300 m) — a *subset* of our existing **44**. So it
adds names we mostly already have and **zero** density. **Not implemented.**

### D10 — "name OR motorway_ref" is a hard validation rule
Acceptance requires every row to have a name or a ref. D4's regional naming guarantees a name, so
this now always passes — but the rule is kept (not softened) so a future regression that drops
naming is caught.

### D11 — Environment fix: pin `sqlite` to match `libsqlite`
The solved env had `sqlite 3.32.3` (2020) shadowing `libsqlite 3.53` — its stale `libsqlite3.so`
lacked symbols GDAL/pyogrio/`_sqlite3` needed, breaking all file I/O and `pytest-cov`. Pinned
`sqlite >=3.53` in [`pixi.toml`](pixi.toml).

---

## Improvements delivered

Beyond the milestone features, these hardening changes came out of running on real data:

- **Streaming parser (D1)** — the difference between "crashes the machine" and "runs in one pass".
- **Nearest-OSM-motorway ref fallback (D6, plan §3)** — recovered refs for the majority of
  otherwise-unlabeled stops.
- **Regional naming (D4)** — every pin is labeled and language-appropriate.
- **Robustness fixes found via real data:**
  - `_clean()` in schema treats `NaN`/`pd.NA`/blank as missing — pandas fills unmatched joins with
    `float('nan')`, which is *truthy*, so a naïve `a or b` fallback was leaking `NaN` into pydantic
    string fields and crashing the build.
  - `run_overpass` now raises on a timeout/error `remark` (HTTP 200 + empty body) instead of
    caching an empty "0 results" snapshot — and does **not** cache the failure, so a retry works.
  - `attach_geometry` wraps geometry in a `GeoSeries` so an **empty** result still carries a CRS
    (a bare `[]` raised "Assigning CRS … without a geometry column").
- **Config-driven expansion** — each of the 7 added countries was a YAML block, no core code change
  (the plan's central thesis, now proven 7×).
- **Test suite: 25 tests, network-free** (synthetic geometries + monkeypatched Overpass), ruff clean.
- **CI** rebuilt monthly via Path B; per-country artifacts uploaded.
- **Data licence** travels with the exports: [`data/processed/LICENSE.md`](data/processed/LICENSE.md)
  (ODbL "© OpenStreetMap contributors" + non-ownership disclaimer).

---

## Outlook / watch-list

Ordered roughly by value. Nothing here is required for the current deliverable.

### Highest payoff
1. **ES IGN IGR-RT connector.** Spain's IGN publishes service areas *with geometry* under INSPIRE
   (CC-BY) — the one open source of the four researched that could approach Germany-level
   enrichment (official names + refs, possibly `zona infantil`). The connector interface already
   exists (`fetch → to_points`, see [`src/restspots/enrich/`](src/restspots/enrich/)).
2. **EU merge file.** Per-country gold files already share EPSG:3035, ISO codes and the canonical
   schema, so `rest_stops_playgrounds_EU.geojson` is a concatenation with no reconciliation. Add a
   `merge` CLI command.

### Quality / correctness
3. **Per-direction duplicate names.** Divided-highway stops produce duplicate labels (e.g.
   "Rastplatz Prilly" ×3). They are distinct pins (distinct OSM ids/coords) and intentionally kept,
   but a direction suffix or a grouped "site" view would read better in My Maps.
4. **Region-aware labels for multilingual countries.** CH uses German terms even for
   French/Italian-region stops ("Rastplatz Prilly"); BE uses the bilingual-safe "Parking". A
   canton/language-area lookup could pick Raststätte/Aire/Area per stop. Town names are already
   localized.
5. **Proximity false positives.** Buffer sensitivity (Belgium) showed widening past ~300 m mostly
   adds nearby-*town* playgrounds, not on-site ones. Current 200 m / 50 m-edge is deliberately
   conservative; a 300 m bump for point-mapped stops is the only safe widening. Audit `proximity`
   matches near settlements.
6. **Relations (D3)** — revisit if a country turns out to map service areas as multipolygons at
   scale (none of the 10 do meaningfully).

### Operational
7. **`.pbf` snapshot dating.** Geofabrik's `-latest` URL is mutable; `run_metadata` records the
   download date, but storing the dated filename (e.g. `germany-260621.osm.pbf`) would make
   provenance exact and reruns byte-reproducible.
8. **Memory ceiling.** pyosmium handled France (5 GB) fine, but an all-Europe extract would need
   per-region splitting or a disk-backed osmium index — don't assume one-pass scales unbounded.
9. **UK Northern Ireland (D7).** Add NI by fetching the Ireland extract and clipping to the GB
   admin boundary, if UK completeness matters.
10. **GitHub Pages hosting.** Publish `data/processed/*.geojson` for a stable `loadGeoJson()` URL
    (the only unfinished bit of plan M5); the CI workflow has the hook commented in.
11. **My Maps row cap.** All countries are well under 2,000 rows individually; only relevant if the
    EU merge (item 2) is loaded into a single My Maps layer — split per country there.

### Standing caveat (unchanged from the plan)
**OSM playground tagging is incomplete — absence is not proof of absence.** This is a *positive
list* ("known to have a playground per current OSM data"), refreshed monthly. The cross-country
research (D8/D9) confirmed there is **no open dataset that carries the playground signal**, so OSM
completeness is the ceiling on density; sparse countries (BE/CH/UK) reflect genuine reality
(fewer family-equipped stops + tagging gaps), not a pipeline defect.
