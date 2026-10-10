"""Opt-in CUDA query samples; final writing, network lookup and image generation are bypassed."""

import argparse
import json
from time import monotonic

from moru.config import ModelPaths, application_root
from moru.domain import PromptSettings, PromptTurn
from moru.prompts.local import LlamaPrompts
from moru.prompts.tag_search import QUERY_SYSTEM, TagSearch

CASES = (
    ("create", "빨간 코트를 입은 성인 마녀가 빗자루 옆에서 바이올린을 연주해.", None, ()),
    (
        "color_only",
        "소파 색만 파란색으로 바꾸고 나머지는 그대로.",
        "no humans, cat, sleeping, sofa. Two black cats sleep on a green sofa.",
        (),
    ),
    (
        "history_reference",
        "그때 말한 우비로 바꿔줘. 머리색은 그대로.",
        "1girl, solo, pink hair, black jacket, city street.",
        (
            PromptTurn(
                "분홍 머리 여자가 노란 우비를 입고 거리에 있어.",
                "1girl, solo, pink hair, yellow raincoat, city street.",
            ),
            PromptTurn(
                "우비 대신 검은 재킷으로 바꿔줘.",
                "1girl, solo, pink hair, black jacket, city street.",
            ),
        ),
    ),
    ("animals", "당근 옆에서 흰 토끼 세 마리가 자고 있어. 사람 없이.", None, ()),
)


class EmptyCatalog:
    def search_tags(self, query, limit, cancelled):
        return []


class QuerySamples(LlamaPrompts):
    def _infer(self, llm, messages, settings, cancelled, progress):
        if messages[0]["content"] == QUERY_SYSTEM:
            return super()._infer(llm, messages, settings, cancelled, progress)
        return "Query-only smoke; final writing bypassed."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=True)
    options = parser.parse_args()
    if options.repeat < 1:
        parser.error("--repeat must be positive")
    paths = ModelPaths(application_root())
    print("model:", paths.get("prompt").name, flush=True)
    prompts = QuerySamples(paths, tag_search=TagSearch(EmptyCatalog()))
    settings = PromptSettings(thinking=options.thinking)
    try:
        for iteration in range(options.repeat):
            for name, request, base, history in CASES:
                queries = []
                started = monotonic()
                context = dict(
                    settings=settings,
                    history=history,
                    on_source=lambda source, queries=queries: queries.append(source.query),
                )
                if base is None:
                    prompts.create(request, **context)
                else:
                    prompts.refine(base, request, **context)
                print(
                    json.dumps(
                        {
                            "case": name,
                            "run": iteration + 1,
                            "queries": queries,
                            "seconds": round(monotonic() - started, 2),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                if not queries:
                    raise RuntimeError(f"{name}: no valid queries produced; inspect plan warnings")
    finally:
        prompts.unload()


if __name__ == "__main__":
    main()
