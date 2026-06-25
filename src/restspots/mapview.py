"""Phase 5 (optional) — an interactive folium/Leaflet HTML map of the gold dataset.

A browser-openable companion to the Google exports: one self-contained ``.html`` per
country (or one combined map for ``ALL``), with clustered markers coloured by
``play_type`` and a popup carrying the same fields the KML export shows. It reads the
gold GeoJSON only — no network, no API — so it stays as reproducible as the rest of the
pipeline.
"""

from __future__ import annotations

import html
import pathlib

import geopandas as gpd

# play_type -> marker colour (folium's named Leaflet-AwesomeMarkers palette).
PLAY_TYPE_COLOURS = {
    "outdoor": "green",
    "indoor_soft_play": "blue",
    "both": "purple",
    "unknown": "gray",
}

AMENITY_TAGS = ["toilets", "restaurant", "fuel", "cafe", "picnic", "wheelchair"]


def _popup_html(row) -> str:
    """Build the marker popup — escaped fields, plus a clickable OSM link."""
    name = html.escape(str(row.get("name") or "Rest stop"))
    amenities = ", ".join(t for t in AMENITY_TAGS if bool(row.get(t))) or "—"
    lines = [
        f"<b>{name}</b>",
        f"Motorway: {html.escape(str(row.get('motorway_ref') or '?'))}",
        f"Country: {html.escape(str(row.get('country') or '?'))}",
        f"Playgrounds: {row.get('playground_count', 0)}",
        f"Play type: {html.escape(str(row.get('play_type') or '?'))}",
        f"Match: {html.escape(str(row.get('match_type') or '?'))}",
        f"Amenities: {html.escape(amenities)}",
    ]
    url = row.get("osm_url")
    if url:
        safe = html.escape(str(url), quote=True)
        lines.append(
            f'<a href="{safe}" target="_blank" rel="noopener">OpenStreetMap</a>'
        )
    return "<br>".join(lines)


def build_map(gdf: gpd.GeoDataFrame, title: str = "Rest stops with playgrounds"):
    """Build a folium ``Map`` with one clustered, colour-coded marker per stop.

    Markers use the canonical ``lat``/``lon`` columns (point placement), so a stop mapped
    as a polygon in the gold file still lands on its centroid here.
    """
    import folium
    from folium.plugins import MarkerCluster

    if len(gdf):
        center = [float(gdf["lat"].mean()), float(gdf["lon"].mean())]
    else:
        center = [50.0, 8.0]  # rough centre of the covered region when empty
    fmap = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")

    # One cluster layer per play_type so the LayerControl can toggle each on/off.
    clusters: dict[str, MarkerCluster] = {}
    for play_type, colour in PLAY_TYPE_COLOURS.items():
        clusters[play_type] = MarkerCluster(name=play_type).add_to(fmap)

    for _, row in gdf.iterrows():
        play_type = row.get("play_type") or "unknown"
        cluster = clusters.get(play_type) or clusters["unknown"]
        colour = PLAY_TYPE_COLOURS.get(play_type, "gray")
        folium.Marker(
            location=[float(row["lat"]), float(row["lon"])],
            tooltip=str(row.get("name") or "Rest stop"),
            popup=folium.Popup(_popup_html(row), max_width=300),
            icon=folium.Icon(color=colour, icon="child", prefix="fa"),
        ).add_to(cluster)

    folium.LayerControl(collapsed=False).add_to(fmap)
    if len(gdf):
        # Frame the view to the data extent (lat/lon bounds -> [[s,w],[n,e]]).
        fmap.fit_bounds(
            [
                [float(gdf["lat"].min()), float(gdf["lon"].min())],
                [float(gdf["lat"].max()), float(gdf["lon"].max())],
            ]
        )
    fmap.get_root().html.add_child(
        folium.Element(
            f'<h3 style="position:fixed;top:8px;left:50px;z-index:9999;'
            f"background:white;padding:4px 10px;border-radius:4px;"
            f'font-family:sans-serif">{html.escape(title)} '
            f"({len(gdf)})</h3>"
        )
    )
    return fmap


def write_map(
    gdf: gpd.GeoDataFrame, path: str | pathlib.Path, title: str | None = None
) -> pathlib.Path:
    """Render and save a standalone HTML map; return the path."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fmap = build_map(gdf, title or "Rest stops with playgrounds")
    fmap.save(str(path))
    return path
