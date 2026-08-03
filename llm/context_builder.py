"""Turn retrieved rows into the context block handed to the LLM.

The retrievers return whatever the schema holds, which is more than the model
needs and in a shape that wastes tokens. This module flattens each attraction to
a compact labelled block, caps how much goes in, and keeps the numbering stable
so the generated answer can cite results by position and the UI can line those
citations up against the cards it renders.
"""

MAX_CONTEXT_ITEMS = 8
MAX_DESCRIPTION_CHARS = 600

# Field label overrides where the column name would read badly in a prompt.
FIELD_LABELS = {
    "entrance_fee": "Entrance fee",
    "best_season": "Best season",
    "activity_type": "Activities",
    "water_quality": "Water quality",
    "surf_break": "Has surf break",
    "height_m": "Height (m)",
    "trekking_difficulty": "Trekking difficulty",
    "duration_hours": "Typical duration (hours)",
    "conservation_status": "Conservation status",
    "area_sq_km": "Area (sq km)",
    "notable_wildlife": "Notable wildlife",
    "historical_period": "Period",
    "architectural_style": "Architectural style",
    "unesco_status": "UNESCO status",
}

SKIP_FIELDS = {"id", "name", "category", "latitude", "longitude", "images", "similarity",
               "score", "sources", "ranks"}


def _format_row(index: int, row: dict, description: str | None) -> str:
    lines = [
        f"[{index}] {row['name']} ({row.get('category', '').replace('_', ' ')})",
    ]

    for key, value in row.items():
        if key in SKIP_FIELDS or value is None or value == "":
            continue
        label = FIELD_LABELS.get(key, key.replace("_", " ").capitalize())
        lines.append(f"    {label}: {value}")

    if row.get("images"):
        lines.append(f"    Images available: {len(row['images'])}")

    if description:
        trimmed = description.strip()
        if len(trimmed) > MAX_DESCRIPTION_CHARS:
            trimmed = trimmed[:MAX_DESCRIPTION_CHARS].rsplit(" ", 1)[0] + "..."
        lines.append(f"    Description: {trimmed}")

    return "\n".join(lines)


def build_context(
    rows: list[dict],
    descriptions: dict[str, str] | None = None,
    max_items: int = MAX_CONTEXT_ITEMS,
) -> str:
    """Render retrieved rows as a numbered context block.

    Truncated to max_items because relevance drops off quickly past the top few
    and a long tail of weak matches measurably encourages the model to pad its
    answer with attractions the user did not ask about.
    """
    if not rows:
        return "No matching attractions were found in the database."

    descriptions = descriptions or {}
    blocks = [
        _format_row(index, row, descriptions.get(row["id"]))
        for index, row in enumerate(rows[:max_items], start=1)
    ]
    return "\n\n".join(blocks)


def load_descriptions() -> dict[str, str]:
    """Read the description JSONs, so the context can include the prose too.

    Imported lazily inside the function to keep this module free of a hard
    dependency on the embeddings package.
    """
    from embeddings.text_embed import load_descriptions as _load

    return _load()
