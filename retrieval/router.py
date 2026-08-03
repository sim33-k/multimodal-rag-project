# works out what kind of query the user typed and pulls filters out of it
# asks gemini for JSON matching a fixed schema and if that fails falls back to keyword matching so the app still works offline

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

STRUCTURED_HINTS = ["in ", "district", "free", "under", "over", "cheapest", "list", "show me all", "which", "how many", "filter"]

IMAGE_HINTS = ["looks like", "look like", "similar image", "visually", "photo of", "picture of", "image of", "resembl"]

# kept flat on purpose since nested objects made gemini return broken JSON more often
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


def get_model_name():
    # lite model on purpose since routing runs on every query and the big model would burn the free quota fast
    return os.getenv("GEMINI_ROUTER_MODEL", "gemini-flash-lite-latest")


def blank_route():
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


def normalise(raw, source):
    # turn "any" and "" into None so the filter code can just check truthiness
    route = blank_route()

    query_type = raw.get("query_type")
    if query_type not in QUERY_TYPES:
        query_type = "hybrid"

    district = raw.get("district") or ""
    keywords = raw.get("keywords") or ""
    reasoning = raw.get("reasoning") or ""

    route["query_type"] = query_type
    route["category"] = raw.get("category") or None
    route["district"] = district.strip() or None
    route["accessibility"] = raw.get("accessibility") or None
    route["keywords"] = keywords.strip()
    route["free_entry"] = bool(raw.get("free_entry"))
    route["unesco_only"] = bool(raw.get("unesco_only"))
    route["reasoning"] = reasoning.strip()
    route["source"] = source

    if route["category"] == "any":
        route["category"] = None
    if route["accessibility"] == "any":
        route["accessibility"] = None
    return route


def heuristic_route(query, has_image=False):
    # the fallback deliberately dumb it just has to be good enough for a demo when the API is down
    route = blank_route()
    lowered = (query or "").lower()
    route["keywords"] = query or ""

    if has_image:
        route["query_type"] = "image"
        route["reasoning"] = "An image was uploaded, so visual search is used."
        return route

    for category in CATEGORY_KEYWORDS:
        found = False
        for word in CATEGORY_KEYWORDS[category]:
            if word in lowered:
                found = True
                break
        if found:
            route["category"] = category
            break

    if "unesco" in lowered:
        route["unesco_only"] = True
    if "free" in lowered:
        route["free_entry"] = True
    for level in ["easy", "moderate", "difficult"]:
        if level in lowered:
            route["accessibility"] = level
            break

    # a capitalised word after in/near/at is probably a place name
    match = re.search(r"\b(?:in|near|around|at)\s+([A-Z][a-zA-Z]+)", query or "")
    if match:
        route["district"] = match.group(1)

    visual = False
    for hint in IMAGE_HINTS:
        if hint in lowered:
            visual = True
            break

    structured = route["district"] is not None
    if not structured:
        for hint in STRUCTURED_HINTS:
            if hint in lowered:
                structured = True
                break

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


def gemini_route(query):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(get_model_name())
        response = model.generate_content(
            ROUTER_PROMPT.format(query=query),
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
                "temperature": 0.0,
            },
        )
        return normalise(json.loads(response.text), "gemini")
    except Exception as error:
        # do not blow up the whole request just because routing failed
        print("[router] Gemini not available, using heuristic (" + str(error) + ")")
        return None


def route_query(query, has_image=False):
    if has_image:
        route = heuristic_route(query, has_image=True)
        route["source"] = "rule"
        return route

    route = gemini_route(query)
    if route is None:
        route = heuristic_route(query)
    return route
