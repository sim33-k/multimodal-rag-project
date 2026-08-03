# writes the final answer with gemini using only the context we retrieved so it cant just make stuff up from what it already knows about sri lanka
# if the API isnt working we put together an answer from the rows ourselves so the rest of the pipeline can still be demoed

import os

from dotenv import load_dotenv

from db.connection import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

SYSTEM_PROMPT = """You are a knowledgeable guide to tourist attractions in Sri Lanka.

Answer the user's question using only the numbered context below. Follow these rules:
- Ground every factual claim in the context. Do not add attractions that are not listed.
- If the context does not answer the question, say so plainly rather than guessing.
- Refer to attractions by name, and mention practical details such as entrance fee,
  best season or accessibility when the user's question makes them relevant.
- Write two to four short paragraphs in a warm, direct tone. No bullet lists.

Context:
{context}

Question: {query}"""


def is_configured():
    key = os.getenv("GEMINI_API_KEY", "")
    key = key.strip()
    if key == "your_key_here":
        key = ""
    return key != ""


def generate_answer(query, context, rows=None):
    if rows is None:
        rows = []

    if not is_configured():
        # no LLM so just describe what we found and say so at the bottom
        if not rows:
            answer = ("No attractions in the database matched that query. Try broadening "
                       "the filters, or rephrasing the question.")
        else:
            names = []
            for row in rows[:5]:
                names.append(row["name"])

            if len(names) == 1:
                lead = 'The closest match for "' + query + '" is ' + names[0] + "."
            else:
                lead = ('The closest matches for "' + query + '" are ' +
                        ", ".join(names[:-1]) + " and " + names[-1] + ".")

            details = []
            for row in rows[:3]:
                parts = []
                parts.append(row["name"] + " is in " + row.get("district", "Sri Lanka"))
                if row.get("best_season"):
                    parts.append("best visited " + row["best_season"])
                if row.get("entrance_fee"):
                    parts.append("entrance " + row["entrance_fee"].lower())
                if row.get("accessibility"):
                    parts.append(row["accessibility"] + " to reach")
                details.append(", ".join(parts) + ".")

            note = ("\n\n(Generated without the language model - no Gemini API key is "
                    "configured, so this summary is composed directly from the retrieved "
                    "database rows.)")
            answer = lead + "\n\n" + " ".join(details) + note

        return {"answer": answer, "source": "fallback"}

    prompt = SYSTEM_PROMPT.format(context=context, query=query)

    # try the good model first then the lite one since the good one only allows about 20 requests a day on the free tier
    model_names = [
        os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest"),
    ]

    key = os.getenv("GEMINI_API_KEY", "")
    key = key.strip()
    if key == "your_key_here":
        key = ""

    for model_name in model_names:
        try:
            import google.generativeai as genai

            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.4, "max_output_tokens": 2048},
            )
            text = response.text
            if text is None:
                text = ""
            text = text.strip()
            if text == "":
                raise ValueError("empty response")
            return {"answer": text, "source": "gemini", "model": model_name}
        except Exception as error:
            # normally a 429 once the daily allowance is gone so try the next model first
            print("[generate] " + model_name + " not available (" +
                  str(error)[:120] + ")")

    # every model failed so fall back to describing the rows ourselves again
    if not rows:
        answer = ("No attractions in the database matched that query. Try broadening "
                   "the filters, or rephrasing the question.")
    else:
        names = []
        for row in rows[:5]:
            names.append(row["name"])

        if len(names) == 1:
            lead = 'The closest match for "' + query + '" is ' + names[0] + "."
        else:
            lead = ('The closest matches for "' + query + '" are ' +
                    ", ".join(names[:-1]) + " and " + names[-1] + ".")

        details = []
        for row in rows[:3]:
            parts = []
            parts.append(row["name"] + " is in " + row.get("district", "Sri Lanka"))
            if row.get("best_season"):
                parts.append("best visited " + row["best_season"])
            if row.get("entrance_fee"):
                parts.append("entrance " + row["entrance_fee"].lower())
            if row.get("accessibility"):
                parts.append(row["accessibility"] + " to reach")
            details.append(", ".join(parts) + ".")

        note = ("\n\n(Generated without the language model - YOU DONT EVEN HAVE A Gemini API key "
                "configured, so this summary is composed directly from the retrieved "
                "database rows.)")
        answer = lead + "\n\n" + " ".join(details) + note

    return {"answer": answer, "source": "fallback"}
