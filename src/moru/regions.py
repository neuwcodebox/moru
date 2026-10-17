"""Validated masks and inpainting crops in original image coordinates."""

import base64
import binascii
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from moru.errors import MoruError


def decode_mask(value: str, size: tuple[int, int]) -> bytes:
    if not isinstance(value, str) or len(value) > 32 * 1024 * 1024:
        raise MoruError("REGION_INVALID_MASK")
    prefix = "data:image/png;base64,"
    if not value.startswith(prefix):
        raise MoruError("REGION_INVALID_MASK")
    try:
        raw = base64.b64decode(value[len(prefix) :], validate=True)
        with Image.open(BytesIO(raw)) as image:
            if image.format != "PNG" or image.size != size:
                raise MoruError("REGION_INVALID_MASK")
            mask = image.convert("L")
            if "A" in image.getbands():
                mask = ImageChops.multiply(mask, image.getchannel("A"))
            mask = mask.point(lambda pixel: 255 if pixel >= 128 else 0)
        if not mask.getbbox():
            raise MoruError("REGION_EMPTY_MASK")
        output = BytesIO()
        mask.save(output, format="PNG")
        return output.getvalue()
    except (ValueError, binascii.Error, OSError, Image.DecompressionBombError) as exc:
        raise MoruError("REGION_INVALID_MASK") from exc


@dataclass(frozen=True)
class InpaintCrop:
    bounds: tuple[int, int, int, int]
    image: Image.Image
    noise_mask: Image.Image


def prepare_inpaint_crop(original: Path, mask_path: Path, size: tuple[int, int]) -> InpaintCrop:
    """Give small selections working resolution and surrounding visual context."""
    with Image.open(original) as source, Image.open(mask_path) as selection:
        mask = selection.convert("L")
        box = mask.getbbox()
        if source.size != size or mask.size != size or box is None:
            raise MoruError("REGION_INVALID_MASK")
        padding = max(32, round(max(box[2] - box[0], box[3] - box[1]) / 2))
        bounds = (
            max(0, box[0] - padding), max(0, box[1] - padding),
            min(source.width, box[2] + padding), min(source.height, box[3] + padding),
        )
        crop = source.convert("RGB").crop(bounds)
        scale = min(size[0] / crop.width, size[1] / crop.height)
        working_size = (
            max(64, int(crop.width * scale) // 32 * 32),
            max(64, int(crop.height * scale) // 32 * 32),
        )
        crop = crop.resize(working_size, Image.Resampling.LANCZOS)
        # Anchor the seam during generation, across a band measured in original pixels.
        noise_mask = _inward_feather(mask, maximum_width=32).crop(bounds).resize(
            working_size, Image.Resampling.BILINEAR,
        )
        return InpaintCrop(bounds, crop, noise_mask)


def _inward_feather(mask: Image.Image, *, maximum_width: int = 8) -> Image.Image:
    box = mask.getbbox()
    if box is None:
        raise MoruError("REGION_EMPTY_MASK")
    width = min(maximum_width, max(1, min(box[2] - box[0], box[3] - box[1]) // 4))
    feathered = Image.new("L", mask.size)
    eroded = mask
    # Distance rings start at a low alpha, rather than clipping off half a Gaussian ramp.
    for step in range(1, width + 1):
        level = round(255 * step / width)
        ring = eroded.point([0] + [level] * 255)
        feathered = ImageChops.lighter(feathered, ring)
        eroded = eroded.filter(ImageFilter.MinFilter(3))
    return feathered


def composite_region(
    original: Path, generated: Image.Image, mask_path: Path,
    bounds: tuple[int, int, int, int] | None = None,
):
    """Preserve every unselected pixel; feather only inside the explicit mask."""
    with Image.open(original) as source, Image.open(mask_path) as selection:
        if source.size != selection.size:
            raise MoruError("REGION_INVALID_MASK")
        source = source.convert("RGB")
        if bounds is None:
            if source.size != generated.size:
                raise MoruError("REGION_INVALID_MASK")
            bounds = (0, 0, source.width, source.height)
        patch = generated.resize(
            (bounds[2] - bounds[0], bounds[3] - bounds[1]), Image.Resampling.LANCZOS,
        )
        restored = source.copy()
        restored.paste(patch, bounds[:2])
        result = Image.composite(restored, source, _inward_feather(selection.convert("L")))
    return result
