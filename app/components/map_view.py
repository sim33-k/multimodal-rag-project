"""Map of retrieved attractions, drawn with pydeck.

Colour encodes category so a mixed hybrid result set is readable at a glance, and
the view auto-centres on whatever was retrieved rather than sitting on a fixed
frame of the whole island.
"""

import pandas as pd
import pydeck as pdk
import streamlit as st

# RGB, matching the categories to a palette consistent with the page theme.
CATEGORY_COLOURS = {
    "beach": [20, 160, 160],
    "mountain": [7, 59, 58],
    "national_park": [76, 140, 74],
    "historical_site": [199, 91, 57],
}

DEFAULT_COLOUR = [120, 120, 120]


def render_map(rows: list[dict]) -> None:
    """Plot attractions that have coordinates. Silent when none do."""
    points = [
        {
            "name": row.get("name", ""),
            "category": (row.get("category") or "").replace("_", " "),
            "district": row.get("district") or "",
            "lat": row["latitude"],
            "lon": row["longitude"],
            "colour": CATEGORY_COLOURS.get(row.get("category"), DEFAULT_COLOUR),
        }
        for row in rows
        if row.get("latitude") is not None and row.get("longitude") is not None
    ]

    if not points:
        st.caption("No coordinates available for these results.")
        return

    frame = pd.DataFrame(points)

    # Centre on the results, and zoom out a little when they are spread across
    # the island so everything stays in frame.
    lat_span = frame["lat"].max() - frame["lat"].min()
    lon_span = frame["lon"].max() - frame["lon"].min()
    span = max(lat_span, lon_span)
    zoom = 11 if span < 0.15 else 9 if span < 0.6 else 7.5 if span < 2 else 6.6

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(frame["lat"].mean()),
                longitude=float(frame["lon"].mean()),
                zoom=zoom,
                pitch=0,
            ),
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data=frame,
                    get_position="[lon, lat]",
                    get_fill_color="colour",
                    get_radius=2600,
                    radius_min_pixels=6,
                    radius_max_pixels=22,
                    pickable=True,
                    opacity=0.85,
                )
            ],
            tooltip={"text": "{name}\n{category} · {district}"},
        )
    )
