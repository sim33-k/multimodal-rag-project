# Turns the rows we retrieved into the block of text we hand to Gemini.
# Numbered so the answer can refer to results by position.

MAX_CONTEXT_ITEMS = 8
MAX_DESCRIPTION_CHARS = 600

# nicer labels for the columns whose names read badly in a prompt
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

# stuff the model shouldn't see. fusion_score and retrievers are added by the
# hybrid route for the UI, and without them listed here they end up in the
# prompt looking like facts about the place
SKIP_FIELDS = {
    "id", "name", "category", "latitude", "longitude", "images", "similarity",
    "score", "sources", "ranks", "fusion_score", "retrievers",
}


def format_row(index, row, description):
    category = row.get("category", "").replace("_", " ")
    lines = ["[" + str(index) + "] " + row["name"] + " (" + category + ")"]

    for key in row:
        value = row[key]
        if key in SKIP_FIELDS or value is None or value == "":
            continue
        label = FIELD_LABELS.get(key, key.replace("_", " ").capitalize())
        lines.append("    " + label + ": " + str(value))

    if row.get("images"):
        lines.append("    Images available: " + str(len(row["images"])))

    if description:
        trimmed = description.strip()
        if len(trimmed) > MAX_DESCRIPTION_CHARS:
            trimmed = trimmed[:MAX_DESCRIPTION_CHARS].rsplit(" ", 1)[0] + "..."
        lines.append("    Description: " + trimmed)

    return "\n".join(lines)


def build_context(rows, descriptions=None, max_items=MAX_CONTEXT_ITEMS):
    # cut off after max_items - relevance drops fast after the top few and a
    # long tail just makes the model pad the answer with places nobody asked
    # about
    if not rows:
        return "No matching attractions were found in the database."

    if descriptions is None:
        descriptions = {}

    blocks = []
    index = 1
    for row in rows[:max_items]:
        blocks.append(format_row(index, row, descriptions.get(row["id"])))
        index += 1

    return "\n\n".join(blocks)


def load_descriptions():
    # imported in here so this module doesn't hard depend on the embeddings
    # package just to read some json
    from embeddings.text_embed import load_descriptions as loader

    return loader()
