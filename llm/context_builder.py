# turns the rows we got back into the block of text we give to gemini numbered so the answer can point at results by position

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

# things the model shouldnt see since fusion_score and retrievers get added by the hybrid route and would look like facts about the place otherwise
SKIP_FIELDS = ["id", "name", "category", "latitude", "longitude", "images", "similarity", "score", "sources", "ranks", "fusion_score", "retrievers"]


def build_context(rows, descriptions=None, max_items=MAX_CONTEXT_ITEMS):
    # stop after max_items since a long list just makes the model pad the answer with places nobody asked about
    if not rows:
        return "No matching attractions were found in the database."

    if descriptions is None:
        descriptions = {}

    blocks = []
    index = 1
    for row in rows[:max_items]:
        description = descriptions.get(row["id"])

        # underscores look bad in a sentence so swap them for spaces
        category = row.get("category", "")
        category = category.replace("_", " ")

        lines = []
        lines.append("[" + str(index) + "] " + row["name"] + " (" + category + ")")

        # one line per remaining field on the row
        for key in row:
            if key in SKIP_FIELDS:
                continue
            value = row[key]
            if value is None or value == "":
                continue

            if key in FIELD_LABELS:
                label = FIELD_LABELS[key]
            else:
                label = key.replace("_", " ").capitalize()

            lines.append("    " + label + ": " + str(value))

        if row.get("images"):
            lines.append("    Images available: " + str(len(row["images"])))

        if description:
            trimmed = description.strip()
            if len(trimmed) > MAX_DESCRIPTION_CHARS:
                # cut at the char limit then back off to the last full word
                trimmed = trimmed[:MAX_DESCRIPTION_CHARS]
                trimmed = trimmed.rsplit(" ", 1)[0] + "..."
            lines.append("    Description: " + trimmed)

        blocks.append("\n".join(lines))
        index = index + 1

    return "\n\n".join(blocks)


def load_descriptions():
    # imported in here so this file doesnt depend on the embeddings package just to read some json
    from embeddings.text_embed import load_descriptions as loader

    return loader()
