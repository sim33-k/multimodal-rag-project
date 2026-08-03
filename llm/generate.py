"""Answer generation with Gemini, grounded in the retrieved context.

The prompt constrains the model to the supplied context and tells it to say so
when the context does not cover the question. That is the whole point of the RAG
setup: the answer should be traceable to rows the retrievers actually returned,
not to whatever the model happens to know about Sri Lanka.

If the API is unavailable the module falls back to composing an answer directly
from the retrieved rows. The result is plainer, but it is still grounded in real
retrieval output, so the pipeline stays demonstrable without a working key.
"""

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


def _model_names() -> list[str]:
    """Models to try in order for answer generation.

    The first is the better writer and is what the answers should normally come
    from. Its free-tier daily quota is small, so a lite model backs it up: once
    the allowance is used, answers get slightly plainer instead of dropping to the
    non-LLM fallback. Only if both are exhausted does the template path run.
    """
    return [
        os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest"),
    ]


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return "" if key == "your_key_here" else key


def is_configured() -> bool:
    """Whether a usable-looking key is present. The API is only tried if so."""
    return bool(_api_key())


def fallback_answer(query: str, rows: list[dict]) -> str:
    """Compose an answer from the retrieved rows without calling the LLM.

    Used when the API key is missing or the call fails. It is intentionally
    template-based and says which attractions were retrieved, so it is obvious to
    the reader that this is the degraded path rather than a generated response.
    """
    if not rows:
        return (
            "No attractions in the database matched that query. Try broadening the "
            "filters, or rephrasing the question."
        )

    names = [row["name"] for row in rows[:5]]
    if len(names) == 1:
        lead = f"The closest match for \"{query}\" is {names[0]}."
    else:
        lead = (
            f"The closest matches for \"{query}\" are "
            f"{', '.join(names[:-1])} and {names[-1]}."
        )

    details = []
    for row in rows[:3]:
        parts = [f"{row['name']} is in {row.get('district', 'Sri Lanka')}"]
        if row.get("best_season"):
            parts.append(f"best visited {row['best_season']}")
        if row.get("entrance_fee"):
            parts.append(f"entrance {row['entrance_fee'].lower()}")
        if row.get("accessibility"):
            parts.append(f"{row['accessibility']} to reach")
        details.append(", ".join(parts) + ".")

    note = (
        "\n\n(Generated without the language model - no Gemini API key is "
        "configured, so this summary is composed directly from the retrieved "
        "database rows.)"
    )
    return lead + "\n\n" + " ".join(details) + note


def generate_answer(query: str, context: str, rows: list[dict] | None = None) -> dict:
    """Generate the final answer. Returns the text plus which path produced it."""
    rows = rows or []

    if not is_configured():
        return {"answer": fallback_answer(query, rows), "source": "fallback"}

    prompt = SYSTEM_PROMPT.format(context=context, query=query)

    for model_name in _model_names():
        try:
            import google.generativeai as genai

            genai.configure(api_key=_api_key())
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
            # Most commonly a 429 once the model's daily allowance is gone. Try the
            # next model rather than dropping straight to the non-LLM path.
            print(f"[generate] {model_name} unavailable ({str(error)[:120]})")

    return {"answer": fallback_answer(query, rows), "source": "fallback"}
