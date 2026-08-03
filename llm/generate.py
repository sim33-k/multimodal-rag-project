# Generates the final answer with Gemini, using only the retrieved context.
#
# The prompt tells it to stick to the context and to say when the context
# doesn't cover the question. That's the whole point of RAG here - the answer
# should come from rows we actually retrieved, not from whatever the model
# happens to know about Sri Lanka.
#
# If the API isn't available we build a plain answer from the rows instead, so
# the pipeline can still be demoed without a working key.

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


def get_model_names():
    # try the good model first, then the lite one. the good one only allows
    # about 20 requests a day on the free tier, so once that's gone the answers
    # get a bit plainer instead of disappearing completely
    return [
        os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest"),
    ]


def get_api_key():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key == "your_key_here":
        return ""
    return key


def is_configured():
    return bool(get_api_key())


def fallback_answer(query, rows):
    # no LLM - just describe what we retrieved. says so at the end so it's
    # obvious this isn't the generated version
    if not rows:
        return ("No attractions in the database matched that query. Try broadening "
                "the filters, or rephrasing the question.")

    names = [row["name"] for row in rows[:5]]
    if len(names) == 1:
        lead = 'The closest match for "' + query + '" is ' + names[0] + "."
    else:
        lead = ('The closest matches for "' + query + '" are ' +
                ", ".join(names[:-1]) + " and " + names[-1] + ".")

    details = []
    for row in rows[:3]:
        parts = [row["name"] + " is in " + row.get("district", "Sri Lanka")]
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
    return lead + "\n\n" + " ".join(details) + note


def generate_answer(query, context, rows=None):
    if rows is None:
        rows = []

    if not is_configured():
        return {"answer": fallback_answer(query, rows), "source": "fallback"}

    prompt = SYSTEM_PROMPT.format(context=context, query=query)

    for model_name in get_model_names():
        try:
            import google.generativeai as genai

            genai.configure(api_key=get_api_key())
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.4, "max_output_tokens": 800},
            )
            text = (response.text or "").strip()
            if not text:
                raise ValueError("empty response")
            return {"answer": text, "source": "gemini", "model": model_name}
        except Exception as error:
            # usually a 429 once the daily allowance is used up, so try the
            # next model before giving up on the LLM entirely
            print("[generate] " + model_name + " not available (" + str(error)[:120] + ")")

    return {"answer": fallback_answer(query, rows), "source": "fallback"}
