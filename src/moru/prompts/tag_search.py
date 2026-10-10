"""Single-batch local query planning, optional lookup and bounded tag references."""

import json
import logging
from threading import Event

from moru.cancellation import check_cancelled
from moru.danbooru.http import TagLookupError
from moru.danbooru.tags import tag_name
from moru.domain import PromptSource
from moru.ports import PromptStageProgress, SourceProgress, TagSearcher

log = logging.getLogger(__name__)
MAX_QUERIES = 5
SEARCH_LIMIT = 8
REFERENCE_TOKENS = 256
TagReferences = tuple[tuple[str, tuple[str, ...]], ...]
QUERY_SYSTEM = (
    "Prepare Danbooru tag search terms for the latest image request. "
    "Output one line of up to 5 short English concepts separated by commas, or none "
    "if no lookup is useful. Five is an upper limit, not a target. "
    "Use tag names or simple tag fragments, not full descriptions or invented compound tags. "
    "Each concept is at most 80 characters. Do not invent scene content or search filters. "
    "For a new scene, select the main requested visual concepts. "
    "For an edit, select only concepts being changed or added, "
    "excluding preserved or removed details. "
    "The existing image prompt is current state; history resolves references. "
    "Examples of search planning (not conversation history): "
    "New: a wooden boat beneath stars. Output: boat, wood, star. "
    "Current: silver necklace, red dress. Edit: make only the necklace gold. "
    "Output: necklace, gold. "
    "History: orange hat. Current: green hat, black hair. Edit: restore the earlier hat, "
    "keep the hair. Output: hat, orange. "
    "Write only the comma-separated search concepts on one line."
)
REFERENCE_HEADER = (
    " SEARCHED TAG OPTIONS (candidates; use only what fits the request and current scene):"
)


def parse_queries(content: str) -> tuple[str, ...]:
    answer = content.strip().removesuffix(".")
    if not answer or answer.lower() == "none":
        return ()
    if answer.startswith(("[", "{", "```", "<think>")):
        raise ValueError("expected comma-separated search concepts")
    selected = []
    for query in answer.split(","):
        query = query.strip()
        if not query.isascii() or len(query) > 80 or any(ord(char) < 32 for char in query):
            raise ValueError("invalid query")
        name = tag_name(query)
        if name not in selected:
            selected.append(name)
        if len(selected) == MAX_QUERIES:
            break
    return tuple(selected)


class TagSearch:
    def __init__(self, searcher: TagSearcher):
        self._searcher = searcher

    def lookup(
        self,
        queries: tuple[str, ...],
        cancelled: Event,
        on_source: SourceProgress | None,
        on_stage: PromptStageProgress | None,
    ) -> tuple[TagReferences, int]:
        references = []
        found = set()
        for query in queries:
            check_cancelled(cancelled)
            unavailable = False
            try:
                names = self._search_names(query, cancelled)
                source_result = names
            except (TagLookupError, ValueError):
                check_cancelled(cancelled)
                log.warning("optional Danbooru lookup unavailable tool=search_tags")
                source_result = {"error": "lookup_unavailable"}
                names = []
                unavailable = True
            found.update(names)
            if on_stage is not None:
                on_stage("searching_tags", len(found))
            check_cancelled(cancelled)
            if on_source is not None:
                on_source(
                    PromptSource(
                        "search_tags", query, json.dumps(source_result, ensure_ascii=False)
                    )
                )
            check_cancelled(cancelled)
            if unavailable:
                break  # Avoid repeated waits after the optional catalog becomes unavailable.
            references.append((query, tuple(names)))
        return tuple(references), len(found)

    def _search_names(self, query: str, cancelled: Event) -> list[str]:
        names = self._searcher.search_tags(query, SEARCH_LIMIT, cancelled)
        check_cancelled(cancelled)
        if not isinstance(names, list) or any(
            not isinstance(name, str) or not name or tag_name(name) != name for name in names
        ):
            raise TagLookupError()
        return list(dict.fromkeys(names))[:SEARCH_LIMIT]


def add_tag_references(
    messages, references, count_tokens, input_limit, *, max_tokens=REFERENCE_TOKENS
):
    """Keep canonical input intact; admit complete candidates using the real template budget."""
    baseline = count_tokens(messages)
    selected = [[] for _ in references]
    used = set()
    accepted = messages
    # Give every concept a candidate before filling any one concept's list.
    for position in range(SEARCH_LIMIT):
        for index, (_query, names) in enumerate(references):
            if position >= len(names) or names[position] in used:
                continue
            proposal = [list(group) for group in selected]
            proposal[index].append(names[position])
            lines = [
                json.dumps(concept) + ": " + json.dumps(group)
                for (concept, _), group in zip(references, proposal, strict=True)
                if group
            ]
            system = messages[0]["content"] + REFERENCE_HEADER + "\n" + "\n".join(lines)
            augmented = [{**messages[0], "content": system}, *messages[1:]]
            tokens = count_tokens(augmented)
            if tokens <= input_limit and tokens - baseline <= max_tokens:
                selected = proposal
                used.add(names[position])
                accepted = augmented
    return accepted
