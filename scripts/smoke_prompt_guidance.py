"""Opt-in CUDA prompt samples for human review; no image generation or user history."""

import argparse
import json
from pathlib import Path

from moru.config import ModelPaths, application_root
from moru.domain import PromptSettings
from moru.prompting import LlamaPrompts

CASES = (
    ("animals", "당근 옆에서 흰 토끼 세 마리가 자고 있어. 사람 없이.", None),
    (
        "people",
        "왼쪽의 분홍 머리 여자는 노란 우비를, 오른쪽의 갈색 머리 남자는 초록 재킷을 "
        "입었어. 여자가 남자에게 우산을 건네줘.",
        None,
    ),
    ("medium", "사람 없는 안개 낀 호수와 소나무 숲. 수채화로.", None),
    ("roles_objects", "빨간 코트를 입은 성인 마녀가 빗자루 옆에서 바이올린을 연주해.", None),
    (
        "clothes",
        "성인 여성의 패션 카탈로그. 검은 재킷과 검은 스타킹, 흰 브라를 입었어. 정면 전신 사진.",
        None,
    ),
    (
        "refine",
        "소파 색만 파란색으로 바꾸고 나머지는 그대로.",
        "no humans, cat, sleeping, sofa. Two black cats sleep on a green sofa.",
    ),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    defaults = PromptSettings()
    parser.add_argument("--context-size", type=int, default=defaults.context_size)
    parser.add_argument("--max-tokens", type=int, default=defaults.max_tokens)
    parser.add_argument("--output", type=Path, default=Path("build/prompt-guidance-samples.json"))
    options = parser.parse_args()
    settings = PromptSettings(context_size=options.context_size, max_tokens=options.max_tokens)
    prompts = LlamaPrompts(ModelPaths(application_root()))
    samples = []
    try:
        for name, request, base in CASES:
            prompt = (
                prompts.create(request, settings)
                if base is None
                else prompts.refine(base, request, settings)
            )
            samples.append({"case": name, "request": request, "base": base, "prompt": prompt})
            options.output.parent.mkdir(parents=True, exist_ok=True)
            options.output.write_text(
                json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(name, prompt, flush=True)
    finally:
        prompts.unload()


if __name__ == "__main__":
    main()
