"""Shared response assembly for the four query routes.

All four follow the same final three steps once retrieval is done: build the LLM
context from the rows, generate an answer, and package everything into the same
response shape. Keeping that here means the individual route modules contain only
their own retrieval strategy.
"""

from functools import lru_cache

from api.schemas import QueryResponse
from llm.context_builder import build_context
from llm.generate import generate_answer


@lru_cache(maxsize=1)
def _descriptions() -> dict[str, str]:
    """Descriptions are static per process, so read them from disk only once."""
    from llm.context_builder import load_descriptions

    return load_descriptions()


def build_response(
    query: str,
    query_type: str,
    rows: list[dict],
    retrievers_used: list[str],
    route: dict | None = None,
    generate: bool = True,
) -> QueryResponse:
    """Assemble the API response, optionally running answer generation.

    `generate` is exposed on every request model so the retrieval layer can be
    exercised and timed on its own, without an LLM call in the loop.
    """
    context = build_context(rows, _descriptions())

    answer = None
    answer_source = None
    if generate:
        result = generate_answer(query, context, rows)
        answer = result["answer"]
        answer_source = result["source"]

    return QueryResponse(
        query=query,
        query_type=query_type,
        route=route,
        results=rows,
        answer=answer,
        answer_source=answer_source,
        retrievers_used=retrievers_used,
        context=context,
        result_count=len(rows),
    )
