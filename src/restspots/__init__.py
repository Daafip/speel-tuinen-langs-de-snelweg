"""restspots — find highway rest stops with playgrounds and export them for Google Maps.

OpenStreetMap is the universal backbone; national sources (e.g. Autobahn GmbH for
Germany) are optional enrichment layered on top. The pipeline is reproducible by
construction: every external call is a versioned query or a dated, cached snapshot.
"""

__version__ = "0.0.1"

__all__ = ["__version__"]
