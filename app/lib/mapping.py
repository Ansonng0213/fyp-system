"""Shared pydeck map helpers so Pages 1/2/4 render stations and borders the same
way (DESIGN.md semantic colors).

Station dots are pickable, carry their own `tip`, and are drawn LAST (above the
hex layer) with a large enough pixel radius that hovering a dot reliably picks
the station — deck.gl's picking buffer lets the last-drawn layer win each pixel,
so a station tooltip takes priority over the hex tooltip on a dot.
"""
from __future__ import annotations

import pandas as pd
import pydeck as pdk

from lib import theme

# columns a station layer needs to build its tooltip
_STATION_COLS = ["longitude", "latitude", "station_name", "operator", "status",
                 "is_public_facing", "total_ports", "ports_imputed",
                 "max_power_kw", "power_known"]


def _esc(s) -> str:
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
    return (f"<b>{_esc(r['station_name'])}</b><br/>"
            f"{_esc(op)} · {access}<br/>"
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
