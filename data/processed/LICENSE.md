# Data licence & attribution — rest stops with playgrounds

**Disclaimer of ownership.** The datasets in this folder
(`rest_stops_playgrounds_*.geojson` / `.kml` / `.csv` and the `*.gold.geojson`
intermediates) are **derived works**. The author/publisher of this repository does **not
own** the underlying geographic data and makes **no ownership claim** over it. This
project merely **processes, filters, and reformats** openly licensed source data into a
convenient form. All rights and obligations remain with the original data providers below.

---

## Primary source — OpenStreetMap (ODbL)

The locations, names, and tags originate from **OpenStreetMap**.

> **© OpenStreetMap contributors**

- Licence: **Open Database License (ODbL) v1.0** — <https://opendatacommons.org/licenses/odbl/1-0/>
- The ODbL is **share-alike**: if you publicly use or redistribute this derived
  database, you must keep the **"© OpenStreetMap contributors"** attribution and license
  any redistributed derived database under compatible terms.
- When displayed on a map, the credit must be visible in the map UI.

## Enrichment source — Autobahn GmbH (German federal open data)

Official Rastplatz names and motorway references for Germany come from the
**Autobahn GmbH** API (`https://verkehr.autobahn.de/o/autobahn`), published as German
federal open data. Attribute Autobahn GmbH accordingly; verify the current terms on the
API page before redistribution.

---

## What this dataset is (and is not)

- It is a **positive list**: stops **known to have a playground** per current OSM and
  official data, at the snapshot date recorded in `run_metadata_*.json`.
- **Absence is not proof of absence** — OSM playground tagging is incomplete, so a stop
  missing here may still have a playground that simply isn't mapped yet.
- Some matches use a proximity rule (see the `match_type` field); treat `proximity`
  entries near settlements with appropriate caution.

See the repository's top-level [`ATTRIBUTION.md`](../../ATTRIBUTION.md) for the full list
of sources and the project [`LICENSE`](../../LICENSE) (GNU GPL-3) covering the code.
