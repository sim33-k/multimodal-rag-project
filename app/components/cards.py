"""Result card rendering.

A card shows the thumbnail, the name, the handful of facts that matter for that
category, and - for fused results - which retrievers found it. That last part is
deliberate: the assignment asks for the retrieved context to be visible, not just
the final answer.
"""

import html

import streamlit as st

# Which detail fields to surface per category, and how to label them. Anything
# not listed stays out of the card to keep it readable.
CARD_FIELDS = {
    "beach": [("activity_type", "Activities"), ("water_quality", "Water")],
    "mountain": [("height_m", "Height"), ("trekking_difficulty", "Trek")],
    "national_park": [("area_sq_km", "Area"), ("notable_wildlife", "Wildlife")],
    "historical_site": [
        ("historical_period", "Period"),
        ("unesco_status", "UNESCO"),
    ],
}

CATEGORY_LABELS = {
    "beach": "Beach",
    "mountain": "Mountain",
    "national_park": "National Park",
    "historical_site": "Historical Site",
}


def image_url(api_base: str, file_path: str) -> str:
    """Convert a stored path like data/images/beaches/x.jpg into an API URL.

    The frontend never reads image files off disk - it asks the API for them, so
    the two services stay independent.
    """
    relative = file_path.replace("data/images/", "").replace("\\", "/")
    return f"{api_base.rstrip('/')}/images/{relative}"


def _chips(row: dict) -> str:
    chips = [
        f'<span class="chip">{CATEGORY_LABELS.get(row.get("category"), row.get("category", ""))}</span>'
    ]
    if row.get("district"):
        chips.append(f'<span class="chip">{html.escape(str(row["district"]))}</span>')
    if row.get("accessibility"):
        chips.append(f'<span class="chip">{html.escape(str(row["accessibility"]))}</span>')

    if row.get("similarity") is not None:
        chips.append(f'<span class="chip accent">similarity {row["similarity"]:.3f}</span>')
    if row.get("retrievers"):
        joined = " + ".join(row["retrievers"])
        chips.append(f'<span class="chip accent">matched by {html.escape(joined)}</span>')

    return "".join(chips)


def _facts(row: dict) -> str:
    parts = []
    if row.get("entrance_fee"):
        parts.append(f"<b>Entry</b> {html.escape(str(row['entrance_fee']))}")
    if row.get("best_season"):
        parts.append(f"<b>Season</b> {html.escape(str(row['best_season']))}")

    for field, label in CARD_FIELDS.get(row.get("category"), []):
        value = row.get(field)
        if value in (None, ""):
            continue
        if field == "height_m":
            value = f"{value:,.0f} m"
        elif field == "area_sq_km":
            value = f"{value:,.0f} km²"
        parts.append(f"<b>{label}</b> {html.escape(str(value))}")

    return " &nbsp;·&nbsp; ".join(parts)


def render_card(row: dict, api_base: str) -> None:
    """Render one attraction as a card with its thumbnail beside the details."""
    images = row.get("images") or []

    with st.container():
        if images:
            thumbnail, body = st.columns([1, 2.4])
            with thumbnail:
                st.image(image_url(api_base, images[0]["file_path"]),
                         use_container_width=True)
        else:
            body = st.container()

        with body:
            st.markdown(
                f"""
                <div class="card">
                    <h3>{html.escape(row.get('name', 'Unnamed'))}</h3>
                    <div class="sub">{html.escape(str(row.get('location') or ''))}</div>
                    <div>{_chips(row)}</div>
                    <div class="blurb">{_facts(row)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_results(rows: list[dict], api_base: str) -> None:
    if not rows:
        st.info("No attractions matched that query. Try relaxing the sidebar filters.")
        return
    for row in rows:
        render_card(row, api_base)


def render_answer(answer: str | None, source: str | None) -> None:
    """Show the generated response, labelled with which path produced it."""
    if not answer:
        return

    label = "Generated answer" if source == "gemini" else "Answer (retrieval only)"
    body = html.escape(answer).replace("\n\n", "</p><p>").replace("\n", "<br>")
    st.markdown(
        f'<div class="answer"><div class="label">{label}</div><p>{body}</p></div>',
        unsafe_allow_html=True,
    )
