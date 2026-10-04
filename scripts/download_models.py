"""Developer setup using the exact same verified downloads as the desktop UI."""

import argparse
from threading import Event

from moru.config import DEFAULT_MODEL_FILES, ModelPaths, application_root
from moru.downloads import download_model, model_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("models", choices=tuple(DEFAULT_MODEL_FILES), nargs="+")
    options = parser.parse_args()
    root = application_root()
    paths = ModelPaths(root)
    manifest = model_manifest()
    for model_id in options.models:
        previous_percent = -5

        def progress(received, total, current_model_id=model_id):
            nonlocal previous_percent
            percent = int(received * 100 / total)
            if percent >= previous_percent + 5:
                print(f"{current_model_id}: {percent}%", flush=True)
                previous_percent = percent

        target = root / "models" / DEFAULT_MODEL_FILES[model_id][0]
        download_model(manifest[model_id], target, progress, Event())
        paths.set(model_id, target)
        print(f"{model_id}: verified", flush=True)


if __name__ == "__main__":
    main()
