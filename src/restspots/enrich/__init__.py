"""Per-country enrichment connectors.

Every connector implements the same tiny interface so it plugs into the country-agnostic
core by nearest-neighbour match:

    fetch(cache_dir) -> raw
    to_points(raw)   -> GeoDataFrame[name, ref, geometry]

Connectors are looked up by the keys listed under a country's ``enrichment:`` in
``config/countries.yml`` via :data:`CONNECTORS`.
"""

from __future__ import annotations

from .. import autobahn


def _autobahn_fetch(cache_dir="data/raw"):
    return autobahn.fetch_all(cache_dir)


# key (matches config enrichment list) -> (fetch fn, to_points fn)
CONNECTORS: dict[str, tuple] = {
    "autobahn_api": (_autobahn_fetch, autobahn.to_points),
}

__all__ = ["CONNECTORS"]
