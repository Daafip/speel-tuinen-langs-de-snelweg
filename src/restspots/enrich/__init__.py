"""Per-country enrichment connectors.

Two kinds, both using the same tiny ``fetch(cache_dir) -> raw`` / ``to_points(raw) -> GeoDataFrame``
interface, looked up by the keys in a country's config:

* :data:`CONNECTORS` (``enrichment:``) — nearest-neighbour *name/ref* attachment to OSM stops
  (e.g. Germany's Autobahn ``parking_lorry``). ``to_points`` -> ``[name, ref, geometry]``.
* :data:`FACILITY_CONNECTORS` (``facilities:``) — authoritative *playground confirmations* folded
  in via :func:`restspots.join.apply_facility_seed` (can mark a stop has_playground / add a stop).
  ``to_points`` -> ``[name, ref, side, play_type, verified_source, seed_id, geometry]``.
"""

from __future__ import annotations

from .. import autobahn
from . import uk


def _autobahn_fetch(cache_dir="data/raw"):
    return autobahn.fetch_all(cache_dir)


# key (matches config `enrichment:`) -> (fetch fn, to_points fn)
CONNECTORS: dict[str, tuple] = {
    "autobahn_api": (_autobahn_fetch, autobahn.to_points),
}

# key (matches config `facilities:`) -> (fetch fn, to_points fn)
FACILITY_CONNECTORS: dict[str, tuple] = {
    "uk_facilities": (uk.fetch, uk.to_points),
}

__all__ = ["CONNECTORS", "FACILITY_CONNECTORS"]
