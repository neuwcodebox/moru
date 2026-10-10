"""Run the real application pipeline and verify persisted create/refine/Fork behavior."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from moru.config import ModelPaths, application_root
from moru.desktop import configure_logging
from moru.domain import GenerationSettings
from moru.images.client import ImageWorker
from moru.prompts.local import LlamaPrompts
from moru.repository import Repository
from moru.service import Application


def main():
    root = application_root()
    configure_logging(root)
    paths = ModelPaths(root)
    with TemporaryDirectory(dir=root / "data", prefix="application-smoke-") as temporary:
        data_dir = Path(temporary)
        executor = ThreadPoolExecutor(max_workers=1)
        app = Application(
            Repository(data_dir / "test.db"),
            LlamaPrompts(paths),
            ImageWorker(paths, root / "vendor/comfyui"),
            root / "data",
            executor=executor,
        )
        records = []

        def finish(job):
            executor.submit(lambda: None).result(timeout=600)
            result = app.get_job(job.id)
            assert result.state == "completed", result
            image = app.repository.get_image(result.image_id)
            records.append(
                {
                    "kind": image.generation_method,
                    "prompt": image.prompt,
                    "seed": image.settings.seed,
                    "parent": image.parent_image_id,
                    "id": image.id,
                }
            )
            print(f"{image.generation_method}_persisted_ok", flush=True)
            return image

        try:
            app.update_settings(GenerationSettings())
            project = app.create_project()
            first = finish(
                app.submit_request(project.id, "은발 단발 소녀가 편의점 앞에서 컵라면을 먹는 장면")
            )
            second = finish(app.submit_request(project.id, "밤으로 바꾸고 비가 조금 오게 해줘"))
            assert second.parent_image_id == first.id
            copied = app.fork(project.id, first.id)
            copied_root = app.repository.conversation(copied.id)[0][1]
            sibling = finish(app.submit_request(copied.id, "햇살이 따뜻한 아침으로 바꿔줘"))
            assert sibling.parent_image_id == copied_root.id
            manual = finish(
                app.generate_from_prompt(first.id, first.prompt + ", watercolor painting")
            )
            assert manual.parent_image_id == first.id
            app.select_version(project.id, second.id)
            assert app.repository.active_path(project.id) == [first, second]
            app.close()
            restored = Repository(data_dir / "test.db")
            try:
                assert restored.active_path(project.id) == [first, second]
                assert len(restored.conversation(project.id)) == 2
                assert len(restored.conversation(project.id)[0][2]) == 2
                assert len(restored.conversation(copied.id)) == 2
            finally:
                restored.close()
            report = root / "data/application-smoke-report.json"
            report.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            print("application_tree_and_restart_ok", flush=True)
        finally:
            app.close()


if __name__ == "__main__":
    main()
