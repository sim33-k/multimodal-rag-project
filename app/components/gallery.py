"""Image gallery for visual search results.

The result cards show one thumbnail each, which is the right density when the
answer is about places. For an image query the photographs *are* the result, so
this renders them as a grid instead: every stored image of every retrieved
attraction, at a size where visual similarity can actually be judged.
"""

import streamlit as st

from app.components.cards import image_url


def render_gallery(rows: list[dict], api_base: str, columns: int = 3) -> None:
    """Lay retrieved attractions' images out in a grid, best match first.

    Attractions with no image on disk are skipped rather than rendered as a gap,
    since the image set is still being completed.
    """
    tiles = [
        (row, image)
        for row in rows
        for image in (row.get("images") or [])
    ]

    if not tiles:
        st.caption(
            "No images stored for these results yet. Run "
            "`python -m data.fetch_images` to download them."
        )
        return

    grid = st.columns(columns)
    for index, (row, image) in enumerate(tiles):
        with grid[index % columns]:
            st.image(image_url(api_base, image["file_path"]), use_container_width=True)

            similarity = row.get("similarity")
            caption = row["name"]
            if similarity is not None:
                caption += f" · {similarity:.3f}"
            st.caption(caption)


def render_query_image(uploaded) -> None:
    """Show the image being searched with, beside its results.

    Worth displaying during a demo: the comparison only makes sense when the query
    image and the matches are visible together.
    """
    if uploaded is None:
        return
    st.image(uploaded, caption="Query image", width=240)
