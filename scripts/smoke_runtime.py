"""Opt-in GPU checks. Synthetic requests only; never part of the normal unit suite."""

import argparse
import time
import uuid
from threading import Event, Timer

from PIL import Image

from moru.config import ModelPaths, application_root
from moru.desktop import configure_logging
from moru.domain import GenerationSettings, PromptSettings
from moru.errors import MoruError
from moru.prompting import LlamaPrompts
from moru.worker_client import ImageWorker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", action="store_true")
    parser.add_argument("--context-size", type=int, default=2048)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reasoning-level", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--cancel-prompt", action="store_true")
    parser.add_argument("--image", choices=("turbo", "aesthetic"))
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--cfg", type=float)
    parser.add_argument("--cancel-restart", action="store_true")
    options = parser.parse_args()
    root = application_root()
    configure_logging(root)
    paths = ModelPaths(root)
    prompts = LlamaPrompts(paths)
    worker = ImageWorker(paths, root / "vendor/comfyui")
    prompt = "1girl, silver hair, blue eyes, convenience store, eating noodles, night, anime"
    started = time.perf_counter()
    try:
        if options.prompt:
            prompt_settings = PromptSettings(
                context_size=options.context_size,
                max_tokens=options.max_tokens,
                thinking=options.thinking,
                reasoning_level=options.reasoning_level,
            )
            prompt = prompts.create("은발 소녀가 편의점 앞에서 컵라면을 먹는 장면", prompt_settings)
            if not prompt.strip() or "Thinking Process:" in prompt or "<think>" in prompt:
                raise AssertionError("create did not return a finished image prompt")
            print("prompt_create_ok", flush=True)
            prompt = prompts.refine(prompt, "밤으로 바꾸고 비가 조금 오게 해줘", prompt_settings)
            if not prompt.strip() or "Thinking Process:" in prompt or "<think>" in prompt:
                raise AssertionError("refine did not return a finished image prompt")
            print("prompt_refine_ok", flush=True)
        if options.cancel_prompt:
            # Warm the model so cancellation is exercised during generation, not loading.
            prompts.create("검은 고양이를 그려줘", PromptSettings(thinking=False))
            cancelled = Event()
            timer = Timer(0.5, cancelled.set)
            timer.start()
            try:
                prompts.create(
                    "별이 가득한 밤하늘 아래 검은 고양이",
                    PromptSettings(thinking=True),
                    cancelled=cancelled,
                )
            except MoruError as exc:
                assert exc.code == "GENERATION_CANCELLED", exc.code
                print("prompt_cancel_ok", flush=True)
            else:
                raise AssertionError("prompt generation was not cancelled")
            finally:
                timer.cancel()
                timer.join()
            assert prompts.create("검은 고양이", PromptSettings(thinking=False)).strip()
            print("prompt_retry_after_cancel_ok", flush=True)
        if options.image:
            settings = GenerationSettings(
                model_id=f"anima-{options.image}-v1.1",
                width=options.width,
                height=options.height,
                steps=options.steps,
                cfg=options.cfg,
                seed=123,
            )
            output = root / "data/images" / f"smoke-{uuid.uuid4().hex}.png"

            def progress(state, step, total):
                print(state, step, total, flush=True)

            if options.cancel_restart:
                cancelled = Event()

                def cancel_on_first_step(state, step, total):
                    if state == "generating" and step == 1:
                        cancelled.set()

                try:
                    worker.generate(prompt, settings, output, cancel_on_first_step, cancelled)
                except MoruError as exc:
                    assert exc.code == "GENERATION_CANCELLED", exc.code
                else:
                    raise AssertionError("generation was not cancelled")
                assert not output.exists()
                assert not output.with_suffix(".png.part").exists()
                print("worker_cancel_ok", flush=True)
            worker.generate(prompt, settings, output, progress, Event())
            with Image.open(output) as image:
                assert image.size == (settings.width, settings.height)
                image.verify()
            print("image_generation_ok", output, flush=True)
    finally:
        worker.close()
        prompts.unload()
        print(f"elapsed_seconds={time.perf_counter() - started:.2f}", flush=True)


if __name__ == "__main__":
    main()
