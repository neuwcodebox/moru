"""Explicit GPU smoke for text-only region editing and Anima masked sampling."""

import argparse
import tempfile
from threading import Event

from PIL import Image, ImageDraw

from moru.config import ModelPaths, application_root
from moru.domain import GenerationSettings, PromptSettings
from moru.images.client import ImageWorker
from moru.prompts.local import LlamaPrompts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("turbo", "aesthetic"), default="turbo")
    options = parser.parse_args()
    root = application_root()
    from pathlib import Path

    output_root = Path(tempfile.mkdtemp(prefix="moru-region-smoke-"))
    original = output_root / "data/images/region-smoke-source.png"
    mask_path = output_root / "data/masks/region-smoke-mask.png"
    original.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (512, 512), (225, 210, 185))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 330, 512, 512), fill=(140, 100, 65))
    draw.rounded_rectangle((170, 180, 310, 345), radius=20, fill="white", outline="gray", width=5)
    draw.ellipse((270, 205, 355, 300), outline="white", width=20)
    image.save(original)
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).rectangle((160, 170, 365, 355), fill=255)
    mask.save(mask_path)
    paths = ModelPaths(root)
    prompts = LlamaPrompts(paths)
    worker_paths = ModelPaths(output_root)
    for asset in ("anima-turbo-v1.1", "anima-aesthetic-v1.1", "text_encoder", "vae"):
        worker_paths.set(asset, paths.get(asset))
    worker = ImageWorker(worker_paths, root / "vendor/comfyui")
    cancelled = Event()
    settings = PromptSettings(context_size=4096, max_tokens=1024, thinking=False)
    try:
        pair = prompts.edit_region(
            "A white ceramic cup sits on a brown wooden table against a beige wall.",
            "이 컵을 파란색으로 바꿔",
            settings,
            cancelled,
        )
        print("PROMPTS:", pair, flush=True)
        prompts.unload()
        output = output_root / "data/images/region-smoke-result.png"
        output.unlink(missing_ok=True)
        generation = GenerationSettings(
            model_id=f"anima-{options.model}-v1.1", width=512, height=512, seed=42,
        )
        worker.inpaint(
            pair.region_prompt,
            generation,
            output,
            lambda stage, step, total: print(stage, step, total, flush=True),
            cancelled,
            original,
            mask_path,
        )
        import numpy as np

        with Image.open(output) as result:
            before, after = np.asarray(image), np.asarray(result)
            outside = np.asarray(mask) == 0
            assert np.array_equal(before[outside], after[outside])
        print("PASSED: output dimensions and unselected pixels preserved", output, flush=True)
    finally:
        prompts.unload()
        worker.close()


if __name__ == "__main__":
    main()
