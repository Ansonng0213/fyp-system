"""Shared pydeck map helpers so Pages 1/2/4 render stations and borders the same
way (DESIGN.md semantic colors).

Station dots are pickable, carry their own `tip`, and are drawn LAST (above the
hex layer) with a large enough pixel radius that hovering a dot reliably picks
the station — deck.gl's picking buffer lets the last-drawn layer win each pixel,
so a station tooltip takes priority over the hex tooltip on a dot.
"""
from __future__ import annotations

import math

import pandas as pd
import pydeck as pdk

from lib import theme

# columns a station layer needs to build its tooltip
_STATION_COLS = ["longitude", "latitude", "station_name", "operator", "status",
                 "is_public_facing", "total_ports", "ports_imputed",
                 "max_power_kw", "power_known"]


def _esc(s) -> str:
    """Escape HTML-special chars in free text; the tooltip is set via innerHTML."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _station_tip(r) -> str:
    access = "Public" if bool(r["is_public_facing"]) else "Private / restricted"
    if pd.notna(r["total_ports"]):
        n = int(r["total_ports"])
        ports = f"{n} port{'s' if n != 1 else ''}" + (" (est.)" if bool(r["ports_imputed"]) else "")
    else:
        ports = "ports n/a"
    power = (f"{r['max_power_kw']:.0f} kW"
             if bool(r["power_known"]) and pd.notna(r["max_power_kw"]) else "power n/a")
    op = str(r["operator"]).strip() if pd.notna(r["operator"]) and str(r["operator"]).strip() else "—"
    # plain text + \n line breaks (rendered via white-space:pre-line). No <b>/<br/>
    # tags, so it renders identically regardless of pydeck's tooltip HTML handling.
    return (f"{_esc(r['station_name'])}\n"
            f"{_esc(op)} · {access}\n"
            f"{_esc(r['status'])} · {ports} · {power}")


def _dots(df: pd.DataFrame, rgb: list[int], alpha: int, rmin: int, rmax: int, lid: str) -> pdk.Layer:
    d = df[_STATION_COLS].copy()
    d["tip"] = d.apply(_station_tip, axis=1)
    d["z"] = 500  # lift dots above the flat hex plane (z=0) so they win the
    #             depth test → hovering a dot reliably picks the station, not the
    #             hex underneath. Negligible parallax at pitch 0.
    return pdk.Layer(
        "ScatterplotLayer", id=lid, data=d[["longitude", "latitude", "z", "tip"]],
        get_position="[longitude, latitude, z]", get_fill_color=rgb + [alpha],
        get_radius=110, radius_min_pixels=rmin, radius_max_pixels=rmax,
        stroked=True, get_line_color=[12, 15, 24, 200], line_width_min_pixels=0.6,
        pickable=True,
    )


def station_layers(stations: pd.DataFrame, show_public: bool = True,
                   show_private: bool = False) -> list[pdk.Layer]:
    """Cyan public + gray private station dots, each pickable with a hover
    tooltip (name/operator, access, status, ports, power). Dots are sized for
    reliable hovering. Pass stations already filtered to the districts in view;
    add the returned layers LAST so they sit on top of the hex layer."""
    layers = []
    pub = stations[stations["is_public_facing"] & stations["is_operational"]]
    priv = stations[~(stations["is_public_facing"] & stations["is_operational"])]
    if show_public and len(pub):
        layers.append(_dots(pub, theme.PUBLIC_STATION, 240, 3, 7, "pub"))
    if show_private and len(priv):
        layers.append(_dots(priv, theme.PRIVATE_STATION, 200, 3, 6, "priv"))
    return layers


def mask_layer(mask_geo: dict | None) -> list[pdk.Layer]:
    """Semi-transparent dark overlay covering everything OUTSIDE the KV outline
    (processed_data/kv_mask.geojson), so the study area pops by contrast rather
    than by a heavy border. Add these layers FIRST (below the hexes)."""
    if mask_geo is None:
        return []
    return [pdk.Layer(
        "GeoJsonLayer", id="kv_mask", data=mask_geo,
        stroked=False, filled=True, get_fill_color=[6, 8, 16, 150], pickable=False,
    )]


def border_layers(districts_geo: dict, outline_geo: dict | None = None) -> list[pdk.Layer]:
    """Internal district borders (thin, dim) plus a THIN clean outer KV boundary
    line. The KV 'pop' comes from mask_layer(), not from a heavy outline."""
    layers = [pdk.Layer(
        "GeoJsonLayer", id="districts_inner", data=districts_geo,
        stroked=True, filled=False, get_line_color=[255, 255, 255, 95],
        line_width_min_pixels=1, pickable=False,
    )]
    if outline_geo is not None:
        layers.append(pdk.Layer(
            "GeoJsonLayer", id="kv_outer", data=outline_geo,
            stroked=True, filled=False, get_line_color=[235, 240, 250, 150],
            line_width_min_pixels=1.2, pickable=False,
        ))
    return layers


def no_demand_layer(df: pd.DataFrame, lid: str = "no_demand") -> list[pdk.Layer]:
    """Hexes with NO measurable demand (pop_est == 0 AND activity_score == 0),
    drawn in neutral slate with a thin outline instead of on the inferno ramp.

    These are an ABSENCE OF EVIDENCE, not a low score. The dasymetric step gates
    on OSM POIs (CLAUDE.md trap 21), so a hex lands here either because it is
    genuinely empty -- Subang airport, the Bukit Cherakah reserve -- or because
    OSM never tagged it, which is what removes USJ Taipan and Puchong Bandar. On
    the inferno ramp both rendered near-black, i.e. identical to a well-served
    Kuala Lumpur hex, so "nobody lives here" and "everybody here has a charger"
    looked the same.

    Still pickable, and still carrying a `tip` if the caller supplies one: the
    hex inspector already has a low-OSM-coverage warning for exactly these
    hexes, and dropping them out of the picking buffer would have quietly
    orphaned it.
    """
    if not len(df):
        return []
    cols = ["h3_index", "tip"] if "tip" in df.columns else ["h3_index"]
    return [pdk.Layer(
        "H3HexagonLayer", id=lid, data=df[cols],
        get_hexagon="h3_index", get_fill_color=theme.NO_DEMAND_FILL,
        stroked=True, get_line_color=theme.NO_DEMAND_LINE, line_width_min_pixels=0.5,
        filled=True, extruded=False, pickable=True, auto_highlight=True,
    )]


def fit_view_state(lats, lons, width_px: int = 1180, height_px: int = 620,
                   pad_deg: float = 0.012, zoom_min: float = 7.5,
                   zoom_max: float = 12.5, zoom_bleed: float = 0.06) -> pdk.ViewState:
    """A ViewState that FRAMES the given points instead of guessing a zoom.

    The explorer used to centre on the mean hex and pick zoom 9.1 or 10.3 by a
    district count. At 9.1 the frame reached Kuala Kubu Bharu, Bukit Tinggi,
    Karak and Kuala Klawang -- roughly twice the study area, most of it empty
    basemap (review item D7). Fitting the bounds gives ~10.03 for the full grid,
    and it also tracks the district multiselect, which the old heuristic could
    not.

    Standard Web Mercator: the world is 256 * 2**zoom px, so the zoom that makes
    a span exactly fill the viewport is solved per axis and the tighter one wins.
    `pad_deg` covers the hex radius (cell CENTRES are passed in, ~0.006 deg at
    res 8) plus a little breathing room; `zoom_bleed` backs off a fraction of a
    level so nothing is clipped by rounding.

    `width_px` matters for 15 of the 127 district subsets -- the east-west ones
    such as Klang + Hulu Langat, where longitude binds instead of latitude and
    an over-stated width clips the sides by up to 0.39 of a zoom level. Pass the
    container's real width; the caller knows whether the inspector panel is
    taking 28% of the row.
    """
    lat0, lat1 = float(min(lats)) - pad_deg, float(max(lats)) + pad_deg
    lon0, lon1 = float(min(lons)) - pad_deg, float(max(lons)) + pad_deg

    def _merc_y(lat: float) -> float:
        lat = max(-85.0, min(85.0, lat))
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    y0, y1 = _merc_y(lat0), _merc_y(lat1)
    lon_span = max(lon1 - lon0, 1e-6)
    y_span = max(y1 - y0, 1e-9)
    zoom_x = math.log2(width_px * 360.0 / (256.0 * lon_span))
    zoom_y = math.log2(height_px * 2 * math.pi / (256.0 * y_span))
    zoom = max(zoom_min, min(zoom_max, min(zoom_x, zoom_y) - zoom_bleed))

    # centre on the mercator midpoint, not the arithmetic mean of the latitudes:
    # the mean is what left the frame sitting north of the study area
    lat_c = math.degrees(2 * math.atan(math.exp((y0 + y1) / 2)) - math.pi / 2)
    return pdk.ViewState(latitude=lat_c, longitude=(lon0 + lon1) / 2,
                         zoom=zoom, pitch=0, bearing=0)
