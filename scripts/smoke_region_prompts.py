"""Opt-in local CUDA evaluation of region prompt editing; no image generation or history writes."""

import argparse
import json
from dataclasses import dataclass
from threading import Event
from time import perf_counter

from moru.config import ModelPaths, application_root
from moru.domain import PromptSettings
from moru.errors import MoruError
from moru.prompts.local import LlamaPrompts


@dataclass(frozen=True)
class Case:
    name: str
    scene: str
    change_request: str
    preserved: tuple[str, ...]
    removed: tuple[str, ...]
    concepts: tuple[tuple[str, ...], ...]
    suite: str = "core"
    region_preserved: tuple[str, ...] = ()


CASES = (
    Case(
        "latest_request_overrides_before_state",
        "1girl, blonde hair, purple eyes, school uniform, blue skirt, white shirt, forest, "
        "sunlight, medium shot, anime style, dappled light. A young girl with long blonde hair "
        "and purple eyes stands in a sunlit forest clearing. She wears a blue skirt and white "
        "blouse under the bright morning sky. Sunlight filters through the trees behind her "
        "onto the mossy ground. The scene is serene and peaceful with no other subjects visible.",
        "눈을 빨간색으로",
        ("blonde hair", "blue skirt", "white shirt", "forest", "dappled light"),
        ("purple eyes",), (("red eyes",),), "fresh",
    ),
    Case(
        "held_object",
        "1girl, camera, orange scarf, holding camera. A girl holds a black camera in both "
        "hands on a city street at sunset. Soft warm lighting, detailed anime illustration.",
        '들고 있는 카메라를 휴대용 게임기로 바꿔',
        ("orange scarf", "city street at sunset", "Soft warm lighting", "anime illustration"),
        ("camera",), (("game console", "gaming console", "handheld console",
                       "game device", "gaming device", "game controller"),),
    ),
    Case(
        "color_preserves_other_attributes",
        "A red ceramic cup with a gold rim stands beside a white plate on a dark oak table.",
        '이 컵을 파란색으로 바꿔',
        ("ceramic", "gold rim", "white plate", "dark oak table"), ("red",), (("blue",),),
        region_preserved=("ceramic", "gold rim"),
    ),
    Case(
        "part_only",
        "A white porcelain mug has a round red handle. A purple napkin lies beside it.",
        '하얀 머그잔의 손잡이를 파란색으로 바꿔',
        ("white porcelain mug", "round", "purple napkin"), ("red",), (("blue",), ("handle",)),
        region_preserved=("round",),
    ),
    Case(
        "one_of_repeated_objects",
        "A woman holds a red balloon in her left hand and a red balloon in her right hand. "
        "She wears a yellow raincoat.",
        '왼손에 든 풍선을 파란색으로 바꿔',
        ("red balloon in her right hand", "yellow raincoat"), ("red balloon in her left hand",),
        (("blue balloon",),),
    ),
    Case(
        "absent_target",
        "A woman sits by a window under soft daylight. Watercolor illustration.",
        '여성이 들고 있는 흰 컵을 빨간 사과로 바꿔',
        ("sits", "by a window under soft daylight", "Watercolor illustration."),
        ("cup",), (("red apple",), ("hold", "held", "hand")),
    ),
    Case(
        "count_and_type",
        "Three yellow flowers stand in a blue glass vase on a stone windowsill. Morning light.",
        '꽃병에 꽂힌 노란 꽃 세 송이를 빨간 튤립 세 송이로 바꿔',
        ("blue glass vase", "stone windowsill", "Morning light"), ("yellow",),
        (("tulip",), ("three", "3"), ("red",)),
    ),
    Case(
        "addition_conflicts_with_absence",
        "no humans, quiet snowy park, bare trees. A deserted path leads toward a wooden bench.",
        '길 앞쪽의 빈 공간에 빨간 코트를 입은 여성을 추가해',
        ("quiet snowy park", "bare trees", "wooden bench"), ("no humans", "deserted"),
        (("woman", "female"), ("red coat",)),
    ),
    Case(
        "removal_reveals_surface",
        "A silver key rests on a wooden desk beside a closed blue notebook. Warm lamplight.",
        '책상 위 은색 열쇠를 없애고 빈 나무 책상 표면으로 채워',
        ("wooden desk", "closed blue notebook", "Warm lamplight"), ("key",),
        (("wood",), ("surface", "desk", "tabletop")),
    ),
    Case(
        "shared_color",
        "1girl, red hair, red jacket. A red-haired woman wears a red jacket and black jeans "
        "beside a brick wall.",
        '여성이 입은 빨간 재킷을 하얀색으로 바꿔',
        ("red hair", "red-haired", "black jeans", "brick wall"), ("red jacket",),
        (("white jacket",),), "extended",
    ),
    Case(
        "singular_to_plural",
        "A small brown dog sits on a green sofa beside a red cushion. Pencil sketch.",
        '소파 위 갈색 개를 검은 고양이 두 마리로 바꿔',
        ("green sofa", "red cushion", "Pencil sketch"), ("dog", "brown"),
        (("black",), ("cats", "felines"), ("two", "2")), "extended",
    ),
    Case(
        "nested_part",
        "A woman wears a navy coat with silver buttons and a leather belt. "
        "She carries a beige bag in a misty forest.",
        '남색 코트의 은색 단추를 금색으로 바꿔',
        ("navy coat", "leather belt", "beige bag", "misty forest"), ("silver",),
        (("gold", "golden"), ("button",)), "extended",
    ),
    Case(
        "matching_objects",
        "A white cat sleeps beside a black cat on a blue blanket. "
        "The black cat wears a green collar.",
        '목줄 없는 하얀 고양이를 작은 갈색 토끼로 바꿔',
        ("black cat", "blue blanket", "green collar"), ("white cat",),
        (("brown",), ("rabbit", "bunny")), "extended",
    ),
    Case(
        "new_background_object",
        "A black bicycle leans against a red brick wall. Overcast daylight, oil painting.",
        '자전거 왼쪽 빈 바닥에 노란 꽃이 핀 작은 화분을 놓아줘',
        ("black bicycle", "red brick wall", "Overcast daylight", "oil painting"), (),
        (("yellow flowers", "yellow blossoms", "yellow blooms", "yellow-flowered"),
         ("pot", "potted")), "extended",
    ),
    Case(
        "changed_affordance",
        "1woman, reading, book. A woman reads an open book held in both hands "
        "beside a fireplace. She wears round glasses and a knitted sweater.",
        '양손에 들고 있는 펼친 책을 김이 나는 차 한 잔으로 바꿔',
        ("fireplace", "round glasses", "knitted sweater"), ("book", "reading", "reads"),
        (("tea",), ("steam", "hot")), "extended",
    ),
    Case(
        "quoted_lettering",
        'A black sign reads "OPEN" above a green door. Evening light.',
        '검은 간판의 "OPEN" 글자를 "CLOSED"로 바꿔',
        ("black sign", "green door", "Evening light"), ("open",),
        (("closed",),), "escaping",
    ),
    Case(
        "fresh_material",
        "A small round wooden table stands on a blue rug beside a striped chair. Charcoal drawing.",
        '이 나무 테이블을 유리 재질로 바꿔',
        ("small", "round", "blue rug", "striped chair", "Charcoal drawing"), ("wooden",),
        (("glass",), ("table",)), "fresh", region_preserved=("small", "round"),
    ),
    Case(
        "fresh_other_person",
        "A man in a blue vest stands beside a woman in a blue dress. "
        "She carries a brown bag. Soft studio lighting.",
        '남자가 입은 파란 조끼를 주황색으로 바꿔',
        ("woman in a blue dress", "brown bag", "Soft studio lighting"), ("blue vest",),
        (("orange vest", "orange waistcoat"),), "fresh",
    ),
    Case(
        "fresh_absence_constraint",
        "no animals, a blue rowboat floats on a still lake beside tall reeds. Soft morning mist.",
        '배 옆 빈 물 위에 하얀 백조를 추가해',
        ("blue rowboat", "still lake", "tall reeds", "Soft morning mist"), ("no animals",),
        (("white swan",),), "fresh",
    ),
    Case(
        "additional_nested_attributes",
        "A square red velvet cushion rests on a gray sofa above a wooden floor. Watercolor.",
        '빨간 쿠션을 노란 꽃무늬가 있는 파란 쿠션으로 바꿔',
        ("square", "velvet", "gray sofa", "wooden floor", "Watercolor"), ("red",),
        (("blue",), ("yellow floral", "yellow flower", "yellow blossom"), ("cushion",)),
        "additional", region_preserved=("square", "velvet"),
    ),
    Case(
        "additional_other_holder",
        "umbrella, A woman holds a red umbrella. "
        "A man holds a blue umbrella beside her. Light rain.",
        '여성이 든 빨간 우산을 초록색으로 바꿔',
        ("A man holds a blue umbrella beside her", "Light rain"), ("red umbrella",),
        (("green umbrella",),), "additional",
    ),
    Case(
        "additional_local_removal",
        "A black framed photograph hangs above a shelf holding books and a vase. "
        "Cream wallpaper, warm side lighting.",
        '선반 위에 걸린 검은 액자를 사진과 함께 없애고 크림색 벽지로 채워',
        ("shelf", "books", "vase", "warm side lighting"), ("photograph", "black frame"),
        (("cream",), ("wallpaper",)), "additional",
    ),
    Case(
        "additional_selective_absence",
        "no text, no people, a blank white T-shirt hanging on a wooden hanger. Gray background.",
        '흰 티셔츠의 빈 앞면에 검은색으로 HELLO라고 써줘',
        ("no people", "white T-shirt", "wooden hanger", "Gray background"),
        ("no text", "blank"), (("black",), ("hello",)), "additional",
    ),
)


def issues(case, result):
    scene, region = result.scene_prompt.lower(), result.region_prompt.lower()
    failures = [f"lost: {text}" for text in case.preserved if text.lower() not in scene]
    failures += [
        f"lost region attribute: {text}" for text in case.region_preserved
        if text.lower() not in region
    ]
    failures += [f"stale scene: {text}" for text in case.removed if text.lower() in scene]
    failures += [f"stale region: {text}" for text in case.removed if text.lower() in region]
    for variants in case.concepts:
        for field, value in (("scene", scene), ("region", region)):
            if not any(variant.lower() in value for variant in variants):
                failures.append(f"missing {field} concept: {' / '.join(variants)}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite", choices=("core", "extended", "escaping", "fresh", "additional", "all"),
        default="all",
    )
    parser.add_argument("--case", nargs="+", choices=[case.name for case in CASES])
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-thinking", action="store_true")
    options = parser.parse_args()
    if options.repeat < 1:
        parser.error("--repeat must be positive")
    cases = [case for case in CASES if (
        (options.suite == "all" or case.suite == options.suite)
        and (options.case is None or case.name in options.case)
    )]
    if not cases:
        parser.error("no cases match the selected suite and names")
    settings = PromptSettings(thinking=not options.no_thinking)
    prompts = LlamaPrompts(ModelPaths(application_root()))
    reply = prompts._infer
    raw = None
    sample_seed = options.seed
    writer_calls = 0

    def capture(llm, *args, **kwargs):
        nonlocal raw, writer_calls
        writer_calls += 1
        complete = llm.create_chat_completion

        def seeded(**completion_options):
            return complete(**{**completion_options, "seed": sample_seed})

        llm.create_chat_completion = seeded
        try:
            raw = reply(llm, *args, **kwargs)
            return raw
        finally:
            llm.create_chat_completion = complete

    # Capture malformed responses for diagnosis while exercising the production editing path.
    prompts._infer = capture
    passed = total = 0
    try:
        for case in cases:
            for attempt in range(options.repeat):
                sample_seed = options.seed + attempt
                raw = None
                writer_calls = 0
                started = perf_counter()
                row = {"case": case.name, "attempt": attempt + 1, "seed": sample_seed}

                def progress(stage, region, scene, *, row=row, started=started):
                    if region and "region_first_seconds" not in row:
                        row["region_first_seconds"] = round(perf_counter() - started, 2)
                    if scene and "scene_first_seconds" not in row:
                        row["scene_first_seconds"] = round(perf_counter() - started, 2)

                try:
                    result = prompts.edit_region(
                        case.scene, case.change_request, settings, Event(),
                        on_progress=progress,
                    )
                    row.update(region=result.region_prompt, scene=result.scene_prompt)
                    row["issues"] = issues(case, result)
                    if writer_calls != 2:
                        row["issues"].append(f"writer calls: {writer_calls}, expected 2")
                except MoruError as exc:
                    row.update(issues=[exc.code], raw=raw)
                row["seconds"] = round(perf_counter() - started, 2)
                row["writer_calls"] = writer_calls
                total += 1
                passed += not row["issues"]
                print(json.dumps(row, ensure_ascii=False), flush=True)
        print(
            f"Invariant checks: {passed}/{total}. Review wording and semantics separately.",
            flush=True,
        )
    finally:
        prompts.unload()


if __name__ == "__main__":
    main()
