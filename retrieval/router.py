"""Query router: decide which retrievers to run and extract structured filters.

The primary path asks Gemini to return a JSON object conforming to a fixed
schema, so intent classification and filter extraction happen in one call and the
result is parsed rather than pattern-matched. A keyword heuristic stands behind
it and takes over whenever the API key is missing, the quota is exhausted or the
response fails to parse, which keeps the system demonstrable offline.
"""

import json
import os
import re

from dotenv import load_dotenv

from db.connection import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

QUERY_TYPES = ["structured", "semantic", "image", "hybrid"]

CATEGORY_KEYWORDS = {
    "beach": ["beach", "beaches", "coast", "coastal", "seaside", "surf", "swim", "sand"],
    "mountain": ["mountain", "peak", "hike", "hiking", "trek", "trekking", "climb", "summit"],
    "national_park": ["park", "safari", "wildlife", "animal", "leopard", "elephant", "bird"],
    "historical_site": [
        "historical", "history", "ancient", "temple", "fort", "ruin", "ruins",
        "heritage", "unesco", "archaeological", "monument",
    ],
}

STRUCTURED_HINTS = [
    "in ", "district", "free", "under", "over", "cheapest", "list", "show me all",
    "which", "how many", "filter",
]

IMAGE_HINTS = [
    "looks like", "look like", "similar image", "visually", "photo of", "picture of",
    "image of", "resembl",
]

# Response schema for Gemini's structured output mode. Kept deliberately flat -
# nested objects raise the chance of a malformed response for very little gain.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "query_type": {"type": "string", "enum": QUERY_TYPES},
        "category": {
            "type": "string",
            "enum": ["beach", "mountain", "national_park", "historical_site", "any"],
        },
        "district": {"type": "string"},
        "accessibility": {
            "type": "string",
            "enum": ["easy", "moderate", "difficult", "any"],
        },
        "keywords": {"type": "string"},
        "free_entry": {"type": "boolean"},
        "unesco_only": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": ["query_type", "category", "keywords"],
}

ROUTER_PROMPT = """You route user queries for a Sri Lankan tourism search system.

Classify the query as exactly one of:
- structured: asks for records matching concrete attributes (a category, a
  district, a price, an accessibility level). Answerable by a SQL filter.
- semantic: describes what the user wants in their own words, with no concrete
  filter to match on. Needs meaning-based matching against descriptions.
- image: asks about what somewhere looks like, or refers to a photo.
- hybrid: mixes a concrete filter with a descriptive element, or is broad enough
  that more than one retrieval strategy would help. Prefer this when unsure.

Also extract any filters present. Use "any" for a category or accessibility that
the query does not constrain, and leave district as an empty string if none is
named. Put the meaning-bearing words of the query into "keywords".

The four categories are beach, mountain, national_park and historical_site.
Districts are Sri Lankan administrative districts, e.g. Matale, Galle, Kandy.

Query: {query}"""


def _model_name() -> str:
    """Routing deliberately uses a lite model, not the one used for answers.

    Classification into four labels plus a few filters is an easy task that a lite
    model does just as well, and it carries a much larger free-tier daily quota.
    The flagship model's allowance is small enough that spending it on routing
    would exhaust it long before the answers did - and routing runs on every
    single query.
    """
    return os.getenv("GEMINI_ROUTER_MODEL", "gemini-flash-lite-latest")


def _blank_route() -> dict:
    return {
        "query_type": "hybrid",
        "category": None,
        "district": None,
        "accessibility": None,
        "keywords": "",
        "free_entry": False,
        "unesco_only": False,
        "reasoning": "",
        "source": "heuristic",
    }


def _normalise(raw: dict, source: str) -> dict:
    """Turn a raw route dict into the shape the API layer expects.

    "any" and empty strings are collapsed to None so downstream filter code can
    simply test truthiness rather than special-casing sentinel values.
    """
    route = _blank_route()
    route.update(
        {
            "query_type": raw.get("query_type")
            if raw.get("query_type") in QUERY_TYPES
            else "hybrid",
            "category": raw.get("category") or None,
            "district": (raw.get("district") or "").strip() or None,
            "accessibility": raw.get("accessibility") or None,
            "keywords": (raw.get("keywords") or "").strip(),
            "free_entry": bool(raw.get("free_entry")),
            "unesco_only": bool(raw.get("unesco_only")),
            "reasoning": (raw.get("reasoning") or "").strip(),
            "source": source,
        }
    )
    if route["category"] == "any":
        route["category"] = None
    if route["accessibility"] == "any":
        route["accessibility"] = None
    return route


def heuristic_route(query: str, has_image: bool = False) -> dict:
    """Keyword fallback. Deliberately simple - it only has to be reasonable.

    This is what runs when Gemini is unavailable, so the demo never hard-fails on
    a network problem. It is not the primary path and is not meant to be.
    """
    route = _blank_route()
    lowered = (query or "").lower()
    route["keywords"] = query or ""

    if has_image:
        route["query_type"] = "image"
        route["reasoning"] = "An image was uploaded, so visual search is used."
        return route

    for category, words in CATEGORY_KEYWORDS.items():
        if any(word in lowered for word in words):
            route["category"] = category
            break

    if "unesco" in lowered:
        route["unesco_only"] = True
    if "free" in lowered:
        route["free_entry"] = True
    for level in ("easy", "moderate", "difficult"):
        if level in lowered:
            route["accessibility"] = level
            break

    # A capitalised word after "in"/"near" is very likely a place name.
    match = re.search(r"\b(?:in|near|around|at)\s+([A-Z][a-zA-Z]+)", query or "")
    if match:
        route["district"] = match.group(1)

    visual = any(hint in lowered for hint in IMAGE_HINTS)
    structured = any(hint in lowered for hint in STRUCTURED_HINTS) or route["district"]

    if visual:
        route["query_type"] = "image"
        route["reasoning"] = "Query refers to appearance, so image search is used."
    elif structured and route["category"]:
        route["query_type"] = "hybrid"
        route["reasoning"] = "Query names a filter and a topic, so retrievers are combined."
    elif structured:
        route["query_type"] = "structured"
        route["reasoning"] = "Query names concrete filters, so SQL is used."
    else:
        route["query_type"] = "semantic"
        route["reasoning"] = "Query is descriptive, so embedding search is used."

    return route


def gemini_route(query: str) -> dict | None:
    """Ask Gemini to classify and extract filters. Returns None on any failure."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(_model_name())
        response = model.generate_content(
            ROUTER_PROMPT.format(query=query),
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
                "temperature": 0.0,
            },
        )
        return _normalise(json.loads(response.text), "gemini")
    except Exception as error:
        # Logged rather than raised: a routing failure should degrade to the
        # heuristic, not take the whole request down.
        print(f"[router] Gemini routing unavailable, using heuristic ({error})")
        return None


def route_query(query: str, has_image: bool = False) -> dict:
    """Classify a query and extract its filters, Gemini first, heuristic second."""
    if has_image:
        route = heuristic_route(query, has_image=True)
        route["source"] = "rule"
        return route

    return gemini_route(query) or heuristic_route(query)
