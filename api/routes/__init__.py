# Shared bit of the four routes. Once retrieval is done they all do the same
# three things: build the context, generate an answer, package it up.

from functools import lru_cache

from api.schemas import QueryResponse
from llm.context_builder import build_context
from llm.generate import generate_answer


@lru_cache(maxsize=1)
def get_descriptions():
    # the json files don't change while the server is running, so read once
    from llm.context_builder import load_descriptions

    return load_descriptions()


def build_response(query, query_type, rows, retrievers_used, route=None, generate=True):
    # generate=False skips the LLM call, handy for testing retrieval on its own
    context = build_context(rows, get_descriptions())

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
