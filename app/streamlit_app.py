"""Streamlit frontend for the SL Tourism multimodal RAG system.

This talks to the FastAPI backend over HTTP and never opens a database or
ChromaDB connection itself. Every tab posts to its own endpoint, so what the user
sees here is exactly what the API returns and nothing is computed client-side.

Run with:  streamlit run app/streamlit_app.py
"""

import os
import sys
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

# Allow `streamlit run app/streamlit_app.py` from the repo root without the
# package needing to be installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.components.cards import render_answer, render_results  # noqa: E402
from app.components.gallery import render_gallery  # noqa: E402
from app.components.map_view import render_map  # noqa: E402
from app.ui_theme import apply_theme, hero  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 120.0

st.set_page_config(
    page_title="Sri Lanka Tourism Explorer",
    page_icon="🌴",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


def post(path: str, payload: dict) -> dict | None:
    """POST JSON to the API, surfacing failures as UI messages rather than traces."""
    try:
        response = httpx.post(
            f"{API_BASE}{path}", json=payload, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        st.error(
            f"Cannot reach the API at {API_BASE}. Start it with "
            "`uvicorn api.main:app --reload --port 8000`."
        )
    except httpx.HTTPStatusError as error:
        st.error(f"API returned {error.response.status_code}: {error.response.text}")
    except httpx.RequestError as error:
        st.error(f"Request failed: {error}")
    return None


def post_file(path: str, files: dict, data: dict) -> dict | None:
    try:
        response = httpx.post(
            f"{API_BASE}{path}", files=files, data=data, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        st.error(f"Cannot reach the API at {API_BASE}.")
    except httpx.HTTPStatusError as error:
        st.error(f"API returned {error.response.status_code}: {error.response.text}")
    except httpx.RequestError as error:
        st.error(f"Request failed: {error}")
    return None


@st.cache_data(ttl=60)
def get_health() -> dict | None:
    try:
        return httpx.get(f"{API_BASE}/health", timeout=15.0).json()
    except httpx.RequestError:
        return None


@st.cache_data(ttl=300)
def get_filters() -> dict:
    """Dropdown values come from the API so they always match the loaded data."""
    try:
        return httpx.get(f"{API_BASE}/filters", timeout=15.0).json()
    except httpx.RequestError:
        return {"categories": [], "districts": [], "accessibility": []}


CATEGORY_LABELS = {
    "beach": "Beaches",
    "mountain": "Mountains",
    "national_park": "National Parks",
    "historical_site": "Historical Sites",
}


def render_output(payload: dict, gallery: bool = False) -> None:
    """Render one API response: answer, cards, map and the retrieval evidence.

    `gallery` switches the image tab to a photo grid, since for a visual query the
    images are the result rather than an illustration of it.
    """
    render_answer(payload.get("answer"), payload.get("answer_source"))

    route = payload.get("route")
    retrievers = payload.get("retrievers_used") or []
    if route or retrievers:
        bits = []
        if route:
            bits.append(f"Router classified this as **{route['query_type']}** "
                        f"(via {route['source']})")
            if route.get("reasoning"):
                bits.append(route["reasoning"])
        if retrievers:
            bits.append(f"Retrievers run: **{', '.join(retrievers)}**")
        st.caption(" · ".join(bits))

    results = payload.get("results") or []
    st.markdown(f"**{len(results)} result{'s' if len(results) != 1 else ''}**")

    if not results:
        st.info("Nothing matched. Try relaxing the filters or rephrasing the query.")
        return

    if gallery:
        render_gallery(results, API_BASE)
        st.divider()

    cards, map_column = st.columns([1.35, 1])
    with cards:
        render_results(results, API_BASE)
    with map_column:
        render_map(results)

    # The brief asks for the retrieved context to be visible, not just the answer,
    # so it is one click away rather than hidden.
    with st.expander("Retrieved context passed to the language model"):
        st.markdown(
            f'<div class="evidence">{payload.get("context", "")}</div>',
            unsafe_allow_html=True,
        )


# --- Sidebar ---------------------------------------------------------------

with st.sidebar:
    st.markdown("### Filters")

    options = get_filters()
    category_values = [None] + options.get("categories", [])
    category = st.selectbox(
        "Category",
        category_values,
        format_func=lambda value: "All categories" if value is None
        else CATEGORY_LABELS.get(value, value),
    )

    district_values = [None] + options.get("districts", [])
    district = st.selectbox(
        "District",
        district_values,
        format_func=lambda value: "All districts" if value is None else value,
    )

    accessibility_values = [None] + options.get("accessibility", [])
    accessibility = st.selectbox(
        "Accessibility",
        accessibility_values,
        format_func=lambda value: "Any" if value is None else value.capitalize(),
    )

    limit = st.slider("Maximum results", 3, 20, 6)
    generate = st.toggle(
        "Generate an answer",
        value=True,
        help="Turn off to see raw retrieval output without an LLM call.",
    )

    st.divider()
    st.markdown("### System")
    health = get_health()
    if not health:
        st.error("API unreachable")
        st.caption(f"Expected at {API_BASE}")
    else:
        st.write("Database", "connected" if health["database"] else "unavailable")
        st.write("Text embeddings", f"{health['text_collection']} vectors")
        st.write("Image embeddings", f"{health['image_collection']} vectors")
        st.write(
            "Gemini",
            "configured" if health["gemini_configured"] else "not configured",
        )
        if not health["gemini_configured"]:
            st.caption(
                "Answers fall back to a summary built from the retrieved rows."
            )

# --- Main ------------------------------------------------------------------

hero(
    "Sri Lanka Tourism Explorer",
    "Structured, semantic, visual and hybrid retrieval over beaches, mountains, "
    "national parks and historical sites.",
)

structured_tab, semantic_tab, image_tab, hybrid_tab = st.tabs(
    ["Structured", "Semantic", "Image", "Hybrid"]
)

with structured_tab:
    st.markdown(
        "Filter the database by concrete attributes. This runs SQL against the "
        "`attractions_full` view, plus Postgres full-text search when a keyword "
        "is supplied."
    )
    keyword = st.text_input(
        "Keyword (optional)", placeholder="e.g. Sigiriya, Galle, whale",
        key="structured_keyword",
    )
    free_only, unesco_only = st.columns(2)
    with free_only:
        free_entry = st.checkbox("Free entry only")
    with unesco_only:
        unesco = st.checkbox("UNESCO listed only")

    if st.button("Search", key="structured_button"):
        with st.spinner("Querying the database..."):
            payload = post(
                "/query/structured",
                {
                    "query": keyword,
                    "category": category,
                    "district": district,
                    "accessibility": accessibility,
                    "free_entry": free_entry,
                    "unesco_only": unesco,
                    "limit": limit,
                    "generate": generate,
                },
            )
        if payload:
            render_output(payload)

with semantic_tab:
    st.markdown(
        "Describe what you are looking for in your own words. The query is "
        "embedded with MiniLM and matched against attraction descriptions by "
        "meaning rather than keyword."
    )
    semantic_query = st.text_area(
        "Your query",
        placeholder="e.g. somewhere quiet to watch birds near a lagoon",
        height=90,
        key="semantic_query",
    )

    if st.button("Search", key="semantic_button"):
        if not semantic_query.strip():
            st.warning("Enter a query first.")
        else:
            with st.spinner("Embedding the query and searching..."):
                payload = post(
                    "/query/semantic",
                    {
                        "query": semantic_query,
                        "category": category,
                        "district": district,
                        "limit": limit,
                        "generate": generate,
                    },
                )
            if payload:
                render_output(payload)

with image_tab:
    st.markdown(
        "Search by appearance using CLIP embeddings. Upload a photograph to find "
        "visually similar attractions, or describe a scene to match against the "
        "images themselves rather than their descriptions."
    )
    upload_column, text_column = st.columns(2)

    with upload_column:
        st.markdown("**Upload an image**")
        uploaded = st.file_uploader(
            "Photograph", type=["jpg", "jpeg", "png", "webp"],
            label_visibility="collapsed",
        )
        if uploaded is not None:
            st.image(uploaded, width=260)
        search_upload = st.button("Find similar", key="image_upload_button")

    with text_column:
        st.markdown("**Or describe what it looks like**")
        visual_query = st.text_input(
            "Description",
            placeholder="e.g. golden sand with palm trees",
            label_visibility="collapsed",
            key="image_text_query",
        )
        search_text = st.button("Search images", key="image_text_button")

    if search_upload:
        if uploaded is None:
            st.warning("Upload an image first.")
        else:
            with st.spinner("Encoding the image with CLIP..."):
                payload = post_file(
                    "/query/image/upload",
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    data={
                        "limit": str(limit),
                        "category": category or "",
                        "generate": str(generate).lower(),
                    },
                )
            if payload:
                render_output(payload, gallery=True)

    if search_text:
        if not visual_query.strip():
            st.warning("Describe what you are looking for first.")
        else:
            with st.spinner("Matching against image embeddings..."):
                payload = post(
                    "/query/image",
                    {
                        "query": visual_query,
                        "category": category,
                        "limit": limit,
                        "generate": generate,
                    },
                )
            if payload:
                render_output(payload, gallery=True)

with hybrid_tab:
    st.markdown(
        "Ask anything. The router classifies the query and extracts filters, then "
        "the relevant retrievers run and their rankings are merged with "
        "Reciprocal Rank Fusion."
    )
    hybrid_query = st.text_area(
        "Your question",
        placeholder="e.g. which UNESCO sites in Matale are worth a day trip?",
        height=90,
        key="hybrid_query",
    )

    if st.button("Ask", key="hybrid_button"):
        if not hybrid_query.strip():
            st.warning("Enter a question first.")
        else:
            with st.spinner("Routing, retrieving and fusing results..."):
                payload = post(
                    "/query/hybrid",
                    {
                        "query": hybrid_query,
                        "category": category,
                        "district": district,
                        "accessibility": accessibility,
                        "limit": limit,
                        "generate": generate,
                    },
                )
            if payload:
                render_output(payload)
