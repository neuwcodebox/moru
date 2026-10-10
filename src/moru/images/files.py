"""PNG validation and reads at the local image-file boundary."""

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from moru.errors import MoruError


def verify_png(path: Path, width: int, height: int) -> None:
    try:
        with Image.open(path) as png:
            if png.format != "PNG" or png.size != (width, height):
                raise MoruError("IMAGE_SAVE_FAILED")
            png.verify()
    except (OSError, UnidentifiedImageError, SyntaxError) as exc:
        raise MoruError("IMAGE_SAVE_FAILED") from exc


def read_image(data_dir: Path, image_path: str) -> bytes:
    root = data_dir.resolve()
    path = (root / image_path).resolve()
    if not path.is_relative_to(root):
        raise MoruError("IMAGE_SAVE_FAILED")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise MoruError("IMAGE_SAVE_FAILED") from exc
