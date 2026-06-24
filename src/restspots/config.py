"""Load and validate per-country configuration from ``config/countries.yml``.

Keeping every parameter (bbox/area, tags, buffers, enrichment toggles) in YAML is
what makes "add a country" a config change rather than a code change.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field


def project_root() -> pathlib.Path:
    """Repository root (two levels up from this file: src/restspots/ -> repo)."""
    return pathlib.Path(__file__).resolve().parents[2]


def default_config_path() -> pathlib.Path:
    return project_root() / "config" / "countries.yml"


class CountryConfig(BaseModel):
    """Validated configuration for a single country."""

    iso: str
    osm_area: str
    geofabrik_url: str | None = None
    stop_tags: dict[str, list[str]] = Field(default_factory=dict)
    playground_proximity_m: float = 200.0
    playground_contained_buffer_m: float = 50.0
    enrichment: list[str] = Field(default_factory=list)
    # Authoritative facility connectors (playground confirmations folded in via
    # apply_facility_seed) — e.g. the UK indoor-soft-play seed.
    facilities: list[str] = Field(default_factory=list)
    # Optional Overpass area selectors to fetch the country in pieces (one query each,
    # merged into a single snapshot). Large countries exceed the public servers' limits
    # as a single query, so we split them — e.g. by ISO3166-2 state.
    regions: list[str] = Field(default_factory=list)
    # Localized term per feature_type for stops OSM leaves unnamed (e.g. NL uses
    # "Verzorgingsplaats", DE "Rastplatz"/"Raststätte"). Combined with the nearest place
    # name to form a regional label like "Verzorgingsplaats Apeldoorn".
    labels: dict[str, str] = Field(default_factory=dict)
    # OSM highway classes whose `ref` is used for the nearest-road fallback. Many stops
    # (UK/IT/ES especially) sit on trunk roads, not just motorways.
    ref_road_tags: list[str] = Field(default_factory=lambda: ["motorway"])


def load_countries(path: str | pathlib.Path | None = None) -> dict[str, CountryConfig]:
    """Parse the YAML config into validated :class:`CountryConfig` objects, keyed by code."""
    path = pathlib.Path(path) if path is not None else default_config_path()
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping of country code -> config")
    return {code: CountryConfig(**block) for code, block in raw.items()}


def get_country(code: str, path: str | pathlib.Path | None = None) -> CountryConfig:
    """Return the config for one country code (e.g. ``"DE"``), raising if unknown."""
    countries = load_countries(path)
    code = code.upper()
    if code not in countries:
        known = ", ".join(sorted(countries))
        raise KeyError(f"Unknown country {code!r}. Configured: {known}")
    return countries[code]
