# Expansion Plans — 🇬🇧 UK · 🇩🇰 Denmark · 🇪🇸 Spain · 🇮🇹 Italy

**How this fits:** these extend **§11 (Expansion roadmap)** of the main plan. Nothing in the
core changes — `highway=services` / `rest_area` and `leisure=playground` are global OSM tags, so
the OSM backbone produces a working dataset for each country the moment its YAML block is added.
National connectors below are *optional enrichment* (official names + road refs) layered on top,
exactly as the Autobahn connector is for Germany.

**Assumptions (stated inline so you can override):**

- **"UK" = ISO `GB`** — England, Scotland, Wales **and** Northern Ireland. Overpass treats this as
  one area; Geofabrik does **not** (see UK §, Path B).
- Project CRS stays **EPSG:3035** throughout for clean multi-country merges; a national grid is
  noted per country only as a single-country alternative.
- Canonical schema, buffers (`200 m` proximity / `50 m` contained), export formats and the
  bronze/silver/gold layering are unchanged.

---

## A. Updated expansion roadmap (replaces the §11 table)

| Country | OSM core | Official enrichment | Enrichment quality | Local term |
|---|---|---|---|---|
| 🇩🇪 Germany | ✅ shipped | Autobahn GmbH API (`parking_lorry`) | **High** — names + road ref, free REST | Raststätte / Rastplatz |
| 🇳🇱 Netherlands | works now | RWS / NDW open data | Medium | verzorgingsplaats |
| 🇦🇹 Austria | works now | ASFINAG open data | Medium | Raststation / Rastplatz |
| 🇫🇷 France | works now | data.gouv.fr / APRR / Sanef | Medium | aire de repos / aire de service |
| 🇨🇭 Switzerland | works now | opendata.swiss / ASTRA | Medium | Raststätte / Rastplatz |
| 🇧🇪 Belgium | works now | regional open-data portals | Low–Medium | parking / aire |
| 🇬🇧 **United Kingdom** | **works now** | National Highways Open Data (England SRN) + OSM | **Low** for names, Medium for refs (England) | motorway services / MSA |
| 🇩🇰 **Denmark** | **works now** | Vejdirektoratet API/SDK + opendata.dk | Low–Medium | rasteplads / serviceanlæg |
| 🇪🇸 **Spain** | **works now** | MITMS *áreas de servicio* lists + IGN IGR-RT geometry | **Medium–High** (IGN has geometry) | área de servicio / área de descanso |
| 🇮🇹 **Italy** | **works now** | ANAS grafo + ART / concessionaire data | **Low** (fragmented) | area di servizio / area di sosta |

---

## B. Cross-cutting additions (apply to several of the four)

Three small, config-driven changes cover the awkward bits. None require touching the core logic.

**B1 — Rest stops are not only on motorways.** In the UK especially (and sometimes IT/ES), service
areas sit on **trunk** roads, not just motorways. Make the nearest-ref join's road class
configurable instead of hard-coding `highway=motorway`:

```yaml
# new per-country key in countries.yml; defaults to [motorway] if omitted
ref_road_tags: [motorway, trunk]
```

```python
# §7 ref-join, generalised
road_filter = {"highway": cfg.get("ref_road_tags", ["motorway"])}
ref = gpd.sjoin_nearest(rest_m, roads[roads_match(road_filter)][["ref", "geometry"]],
                        how="left", max_distance=300, distance_col="d_road")
```

**B2 — Spain's official inventory is km-points, not coordinates.** The MITMS lists give
`Vía + P.K. (punto kilométrico)`, not lat/lon. Two options (pick per the toggle):

```yaml
enrichment_pk_geocode: true   # interpolate the P.K. along the OSM/IGN road geometry to a point
```

…or skip geocoding and match official **names** to OSM stops by `ref` + nearest (simpler, slightly
lossier). Prefer the **IGN IGR-RT** layer where possible — it ships geometries directly and avoids
the P.K. problem entirely.

**B3 — The UK is two Geofabrik extracts.** For Path B (offline `.pbf`), fetch **both**
`great-britain` (England/Scotland/Wales) and the NI slice inside
`ireland-and-northern-ireland`, then clip NI by the GB boundary. Path A (Overpass) needs no
special handling — `ISO3166-1=GB` covers all four nations in one query.

---

## C. Per-country plans

### 🇬🇧 United Kingdom

**At a glance:** OSM core works today. The catch is institutional, not technical — there is **no
single official feed of service-area locations**, because the network is split across four national
authorities and the service areas themselves are **commercial**.

**Network & terminology**

- Operators of the road network: **National Highways** (England's Strategic Road Network — the
  former Highways England, rebranded 2021); **Transport Scotland**; **Welsh Government / Traffic
  Wales**; **DfI Roads** (Northern Ireland).
- Service areas (MSAs) are run by private operators — Moto, Welcome Break, RoadChef, Extra,
  Westmorland, EG Group — *not* by the road authority. So official "Rastplatz-style" name/coord
  lists like Germany's don't exist; OSM is the realistic primary for both location and name.
- Road refs: motorways `M1`, `M6`, `M25`; hybrid `A1(M)`; many services sit on **trunk A-roads**
  (`highway=trunk`, refs like `A1`, `A14`) → set `ref_road_tags: [motorway, trunk]` (B1). In OSM,
  UK MSAs are usually `highway=services` polygons carrying `operator`/`brand`; `highway=rest_area`
  is comparatively rare.

**Official enrichment**

| Source | Provides | Access / format | Role |
|---|---|---|---|
| **National Highways Open Data Portal** (`opendata.nationalhighways.co.uk`) | **Network Model** — England SRN geometry, road names/numbers, lanes/widths; emergency areas | Free; GeoJSON / CSV / KML / Shapefile + GeoServices / WMS / WFS APIs | **Ref attachment for England** (authoritative SRN geometry) |
| **data.gov.uk** | Mirrors of National Highways datasets, roadworks, network layers | Free download / API | Secondary / discovery |
| OSM `operator` + Wikidata | MSA names, operator/brand | Free | **Names** (no official source exists) |

License: National Highways open data is **Open Government Licence (OGL) v3.0** — attribute
*"Contains National Highways data © Crown copyright and database right"* (confirm current wording on
the portal). OSM ODbL still governs the core.

**OSM acquisition**

- Overpass area selector: `["ISO3166-1"="GB"][admin_level=2]` (all four nations, one query).
- Geofabrik (Path B): `great-britain-latest.osm.pbf` **plus**
  `ireland-and-northern-ireland-latest.osm.pbf` → clip NI by boundary (B3).

```yaml
# config/countries.yml
GB:
  iso: GB
  osm_area: '["ISO3166-1"="GB"][admin_level=2]'
  geofabrik_url:                          # UK spans two extracts (B3)
    - https://download.geofabrik.de/europe/great-britain-latest.osm.pbf
    - https://download.geofabrik.de/europe/ireland-and-northern-ireland-latest.osm.pbf
  stop_tags:
    highway: [services, rest_area]
  ref_road_tags: [motorway, trunk]        # services also sit on trunk A-roads (B1)
  playground_proximity_m: 200
  playground_contained_buffer_m: 50
  enrichment: [national_highways]         # England SRN refs; OSM/Wikidata for names
```

**Caveats**

- **Playground reality:** UK MSAs are large indoor-led commercial sites; outdoor play areas exist
  mainly at family-oriented ones (the Westmorland sites Tebay & Gloucester are the well-known
  examples; some Moto / Welcome Break sites too). Expect **modest counts, mostly `contained`**
  (sites mapped as polygons).
- The National Highways Network Model covers **England only** — Scotland/Wales/NI refs come from
  OSM. Don't expect official enrichment to be uniform across the UK.

---

### 🇩🇰 Denmark

**At a glance:** small country, clean OSM, single national operator. Official data leans toward live
*traffic/roadwork events* rather than a static rest-area inventory, so OSM stays primary; the
official sources mostly help confirm names/refs.

**Network & terminology**

- Operator: **Vejdirektoratet** (Danish Road Directorate) for state roads and motorways.
- Terms: **rasteplads** (rest area); **serviceanlæg** (the larger facilities with fuel/food);
  plural *rastepladser*.
- Road refs: Danish motorways are commonly signed by **European route numbers** (`E20`, `E45`,
  `E47`) and/or national motorway numbers; OSM `ref` reflects the signage.

**Official enrichment**

| Source | Provides | Access / format | Role |
|---|---|---|---|
| **Vejdirektoratet API / SDK** (`github.com/Vejdirektoratet/sdk-web`, `…/sdk-ios`) | Live traffic & roadwork events by map region | Free **API key** (free account) | Operational context, not static inventory |
| **opendata.dk → Vejdirektoratet** | Traffic counts (Mastra), noise-calc figures | Free download | Secondary |
| **Vejdirektoratet "Rastepladser" theme + list** (`vejdirektoratet.dk/tema/rastepladser-din-pause-paa-turen`) | Curated rest-area list/PDF | Web / PDF | Name cross-check |
| **Datafordeler / SDFI (Dataforsyningen)** | National road-network geometry | Free (registration) | Optional ref attachment |

License: OSM **ODbL** governs the core; Vejdirektoratet API terms to confirm under the free-key
account.

**OSM acquisition**

- Overpass area selector: `["ISO3166-1"="DK"][admin_level=2]` (metropolitan Denmark only — Greenland
  `GL` and the Faroes `FO` are separate ISO codes, so excluded automatically).
- Geofabrik (Path B): `denmark-latest.osm.pbf` (small — Path A is perfectly fine here too).

```yaml
# config/countries.yml
DK:
  iso: DK
  osm_area: '["ISO3166-1"="DK"][admin_level=2]'
  geofabrik_url: https://download.geofabrik.de/europe/denmark-latest.osm.pbf
  stop_tags:
    highway: [services, rest_area]
  ref_road_tags: [motorway, trunk]
  playground_proximity_m: 200
  playground_contained_buffer_m: 50
  enrichment: [vejdirektoratet]          # name/ref cross-check; OSM is primary
```

**Caveats**

- **Playground reality:** larger *serviceanlæg* often have green/play areas; the simple
  *rastepladser* less so — moderate hit rate.
- CRS alternative if working Denmark-only: **EPSG:25832** (UTM32N); Bornholm falls in zone 33
  (25833) — negligible. 3035 stays canonical.

---

### 🇪🇸 Spain

**At a glance:** the **best official enrichment of the four**. The Ministry publishes named
service-area inventories, and IGN publishes the same features **with geometry** under INSPIRE — so
Spain can get close to Germany-level enrichment.

**Network & terminology**

- Network: **Red de Carreteras del Estado** under the **Ministerio de Transportes y Movilidad
  Sostenible (MITMS)**; tolled *autopistas* run by concessionaires; autonomous communities run
  regional roads.
- Terms: **área de servicio** (full service area), **área de descanso** (rest area); the Ministry
  groups them under *"zonas de descanso y servicios."* Look for `zona infantil` / `parque infantil`
  as the playground signal in OSM/official notes.
- Road refs: *autovías* `A-31`, `A-70`; *autopistas de peaje* `AP-7`, `AP-9`; OSM `ref` reflects
  these.

**Official enrichment**

| Source | Provides | Access / format | Role |
|---|---|---|---|
| **MITMS — Áreas de servicio (Autovías)** (`transportes.gob.es/carreteras/zonas-descanso-y-servicios/servicio/autovia`) | Official name, **Vía**, **P.K.**, margen, municipio, provincia | Web list (periodic) | **Names + road ref** (P.K., not coords → B2) |
| **MITMS — Áreas de servicio (Autopistas de Peaje)** (`…/servicio/autopistas`) | Same fields for tolled motorways | Web list | Names + ref for AP- roads |
| **IGN — Redes de Transporte (IGR-RT)** (via CNIG / IDEE, INSPIRE) | **Names *and* geometries** of service areas (autovías, autopistas, conventional state roads) | Free download / INSPIRE services | **Best enrichment — has geometry** (avoids the P.K. problem) |

License: MITMS lists under the **Ministry open-data licence** (commercial + non-commercial reuse,
attribution, keep-same-licence for redistributed data, no misrepresentation). IGN/CNIG data
typically **CC-BY 4.0** — attribute *"© Instituto Geográfico Nacional."* Confirm both as you wire
the connector.

**OSM acquisition**

- Overpass area selector: `["ISO3166-1"="ES"][admin_level=2]` (includes Canaries, Balearics, Ceuta,
  Melilla).
- Geofabrik (Path B): `spain-latest.osm.pbf`.

```yaml
# config/countries.yml
ES:
  iso: ES
  osm_area: '["ISO3166-1"="ES"][admin_level=2]'
  geofabrik_url: https://download.geofabrik.de/europe/spain-latest.osm.pbf
  stop_tags:
    highway: [services, rest_area]
  ref_road_tags: [motorway, trunk]
  playground_proximity_m: 200
  playground_contained_buffer_m: 50
  enrichment: [ign_igr_rt, mitms_areas]  # prefer IGN geometry; MITMS lists for names/ref
  enrichment_pk_geocode: true            # used only if falling back to MITMS P.K. (B2)
```

**Caveats**

- Prefer **IGN IGR-RT geometry** as the enrichment join; reach for the MITMS lists (and B2's P.K.
  geocoding) only when IGN coverage lags for a given road.
- **Playground reality:** some áreas de servicio have a *zona infantil*; coverage is variable — keep
  the standard buffers and audit `proximity` matches near towns as usual.
- CRS alternative (peninsula-only): **EPSG:25830** (UTM30N); Canaries need 28N (25828). 3035 stays
  canonical for the EU merge.

---

### 🇮🇹 Italy

**At a glance:** OSM core works, but **official enrichment is the most fragmented of the four** — the
tolled network is split across ~23 concessionaires, ANAS runs the rest, and ART regulates. There is
**no single national service-area API**, so OSM is strongly primary and enrichment is best-effort.

**Network & terminology**

- Network: most *autostrade* are **tolled** (~82% of the network, ~6,005 km), run by **~23
  concessionaires** under 26 concessions; **ASPI (Autostrade per l'Italia)** is the largest (~48%,
  ~2,855 km). **ANAS** runs the non-tolled state network and publishes the road graph. **ART**
  (Autorità di Regolazione dei Trasporti) regulates, including the *aree di servizio*
  subconcessions.
- Terms: **area di servizio** (full service area — the classic Autogrill/oasi), **area di sosta /
  area di parcheggio** (rest/parking area); some **aree pic-nic**. Playground signal in OSM:
  `area gioco`.
- Road refs: `A1`, `A4`, `A14`; raccordi `RA`; tangenziali. OSM `ref` reflects these.

**Official enrichment**

| Source | Provides | Access / format | Role |
|---|---|---|---|
| **Grafo stradale ANAS** (`dati.mit.gov.it`) | ANAS road-network geometry | ESRI Shapefile (dated snapshots) | Ref attachment for the **ANAS (non-tolled)** network |
| **dati.mit.gov.it — "Gestione rete autostradale"** | Concessionaire ↔ segment mapping (who runs what) | XLSX / open | Context, not service-area coords |
| **ART data portal** (`bdt.autorita-trasporti.it`) | Autostrade datasets, traffic, concessions; regulates *aree di servizio* gestori | Open datasets / reports | Names/operators where published |
| Concessionaire sites (ASPI, etc.) | Each operator's own service-area lists/maps | Per-operator, no unified API | Names where available |

License: ANAS / MIT datasets under **IODL 2.0** (Italian Open Data Licence). OSM **ODbL** governs the
core.

**OSM acquisition**

- Overpass area selector: `["ISO3166-1"="IT"][admin_level=2]`.
- Geofabrik (Path B): `italy-latest.osm.pbf`.

```yaml
# config/countries.yml
IT:
  iso: IT
  osm_area: '["ISO3166-1"="IT"][admin_level=2]'
  geofabrik_url: https://download.geofabrik.de/europe/italy-latest.osm.pbf
  stop_tags:
    highway: [services, rest_area]
  ref_road_tags: [motorway, trunk]       # ANAS strade statali also carry rest stops
  playground_proximity_m: 200
  playground_contained_buffer_m: 50
  enrichment: [anas_grafo]               # refs for ANAS network; OSM primary for names/coords
```

**Caveats**

- **No unified national feed:** treat enrichment as best-effort. OSM tags Italian *aree di servizio*
  fairly well (often polygons with `brand`), which is fortunate given the fragmentation.
- **Playground reality:** some aree di servizio have an *area gioco* or *area pic-nic*; variable.
- CRS alternative (single-region work): **EPSG:25832** (UTM32N, NW) or **EPSG:25833** (UTM33N, centre/
  south); Italy spans zones 32–34. 3035 stays canonical.

---

## D. New risk rows (append to §13)

| Risk | Mitigation |
|---|---|
| **UK** — no single official MSA feed; network split across 4 authorities; MSAs are commercial | Use OSM as primary for location + name; National Highways Network Model for **England** refs only; widen ref-join to trunk roads (B1) |
| **UK** — Geofabrik has no single UK extract | Fetch `great-britain` + `ireland-and-northern-ireland`, clip NI by boundary (B3); Overpass handles `GB` in one query |
| **ES** — official inventory is km-points (P.K.), not coordinates | Prefer IGN IGR-RT geometry; otherwise interpolate the P.K. along the route (B2) or match by `ref` + nearest |
| **IT** — service-area data fragmented across ~23 concessionaires + ANAS + ART | Rely on OSM core; enrich refs from ANAS grafo; accept best-effort names |
| **DK** — official API is event-oriented, not a static inventory | OSM primary; Vejdirektoratet list/PDF + Datafordeler geometry as cross-check |

---

## E. Milestone note (extends §14)

> **M7 — Multi-country breadth:** add 🇬🇧/🇩🇰/🇪🇸/🇮🇹 as YAML blocks (OSM-only on day one), then bolt
> on the four connectors in priority order — **ES first** (IGN geometry → highest payoff), then
> **GB** (England SRN refs), then **DK** and **IT** (name/ref cross-checks). Switch the default
> extraction to **Path B (`.pbf`)** at this scale and **split My Maps exports per country** to stay
> under the 2,000-row layer cap. The per-country gold files concatenate into
> `rest_stops_playgrounds_EU.geojson` with no reconciliation, since everything already shares
> EPSG:3035, ISO codes and the canonical schema.

---

## References (verify licences as you wire each connector)

- National Highways Open Data Portal — `https://opendata.nationalhighways.co.uk/`
- National Highways Developer Portal — `https://developer.data.nationalhighways.co.uk/`
- Vejdirektoratet SDKs — `https://github.com/Vejdirektoratet/sdk-web` · `…/sdk-ios`
- Open Data DK (Vejdirektoratet) — `https://www.opendata.dk/vejdirektoratet`
- MITMS áreas de servicio (autovías) — `https://www.transportes.gob.es/carreteras/zonas-descanso-y-servicios/servicio/autovia`
- MITMS áreas de servicio (autopistas) — `https://www.transportes.gob.es/carreteras/zonas-descanso-y-servicios/servicio/autopistas`
- IGN Redes de Transporte (IGR-RT) — via CNIG / `https://www.idee.es/`
- dati.mit.gov.it (ANAS grafo, gestione rete autostradale) — `https://dati.mit.gov.it/`
- ART data portal (autostrade) — `https://bdt.autorita-trasporti.it/rapporto/autostrade/`
- Geofabrik download server — `https://download.geofabrik.de/europe/`
