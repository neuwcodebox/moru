"""Opt-in WebView2/clipboard checks with synthetic history, no models or network."""

import hashlib
import json
import shutil
import uuid
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from PIL import Image as PngImage

from moru.api import Api, endpoint
from moru.clipboard import copy_image, copy_text
from moru.config import application_root
from moru.domain import GenerationSettings, Image, Project, Request
from moru.repository import Repository
from moru.service import Application


def synthetic_history(repository, data_dir, root):
    source = root / "build/aesthetic-review/data/images/aesthetic-recommended-final.png"
    directory = data_dir / "images"
    directory.mkdir(parents=True)
    fixture = directory / "fixture.png"
    if source.is_file():
        shutil.copy2(source, fixture)
    else:
        PngImage.new("RGBA", (512, 512), (55, 115, 175, 180)).save(fixture)
    with PngImage.open(fixture) as picture:
        width, height = picture.size
    settings = GenerationSettings(width=width, height=height, seed=123)
    timestamp = "2026-10-04T08:00:00Z"
    repository.create_project(Project("ui-project", timestamp))
    parent = None
    for number in range(1, 4):
        original = Request(
            f"r{number}",
            "ui-project",
            f"장면 {number} · 눈 내리는 밤거리",
            timestamp,
            parent,
            "create" if parent is None else "refine",
            settings,
        )
        for version in (1, 2):
            image_id = f"i{number}v{version}"
            request = (
                original
                if version == 1
                else replace(
                    original,
                    id=f"r{number}v2",
                    kind="manual",
                    base_image_id=parent,
                    turn_id=original.id,
                )
            )
            repository.add_request(request)
            repository.complete_generation(
                Image(
                    image_id,
                    "ui-project",
                    request.id,
                    parent,
                    "1girl, silver hair, blue eyes, red scarf, snowy street at night, "
                    f"scene {number}, "
                    f"version {version}, warm street lighting, anime illustration",
                    "images/fixture.png",
                    settings,
                    timestamp,
                    request.kind,
                )
            )
            parent = image_id
    return fixture, [width, height]


def main():
    import webview

    root = application_root()
    review = root / "build" / f"ui-review-{uuid.uuid4().hex[:8]}"
    review.mkdir(parents=True)
    repository = Repository(review / "data/anima.db")
    fixture, image_size = synthetic_history(repository, review / "data", root)

    def forbidden(*args, **kwargs):
        raise AssertionError("UI smoke must not run inference")

    application = Application(
        repository,
        SimpleNamespace(create=forbidden, refine=forbidden, unload=lambda: None),
        SimpleNamespace(generate=forbidden, close=lambda: None),
        review / "data",
    )

    class TestApi(Api):
        @endpoint
        def mark_stage(self, name):
            with (review / "stages.txt").open("a", encoding="utf-8") as progress:
                progress.write(f"{name}\n")

        @endpoint
        def clipboard_snapshot(self):
            from System import Action
            from System.Windows.Forms import Clipboard

            snapshots = []

            def read():
                picture = Clipboard.GetImage()
                try:
                    png = Clipboard.GetData("PNG")
                    snapshots.append(
                        {
                            "size": [picture.Width, picture.Height]
                            if picture is not None
                            else None,
                            "png_sha256": hashlib.sha256(bytes(png.ToArray())).hexdigest()
                            if png is not None
                            else None,
                            "text": Clipboard.GetText(),
                            "icon_size": [window.native.Icon.Width, window.native.Icon.Height],
                        }
                    )
                finally:
                    if picture is not None:
                        picture.Dispose()

            window.native.Invoke(Action(read))
            return snapshots[0]

        @endpoint
        def capture_view(self, name):
            from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
            from System import Func, Object
            from System.IO import FileMode, FileStream

            if name not in ("hover", "copy", "viewer", "fork"):
                raise ValueError("unexpected capture name")
            stream = FileStream(str(review / f"{name}.png"), FileMode.Create)
            try:
                task = window.native.Invoke(
                    Func[Object](
                        lambda: window.native.browser.webview.CoreWebView2.CapturePreviewAsync(
                            CoreWebView2CapturePreviewImageFormat.Png,
                            stream,
                        )
                    )
                )
                if not task.Wait(15000):
                    raise RuntimeError("capture did not finish")
            finally:
                stream.Dispose()

    window = webview.create_window(
        "Moru UI smoke",
        html=files("moru").joinpath("web/index.html").read_text("utf-8"),
        js_api=TestApi(
            application,
            copy_to_clipboard=lambda text: copy_text(window, text),
            copy_image_to_clipboard=lambda content: copy_image(window, content),
        ),
        width=1080,
        height=900,
        hidden=True,
    )
    results, errors, original_clipboard = [], [], []
    completed = Event()

    def verify():
        from System import Action
        from System.Drawing import Point
        from System.Windows.Forms import Clipboard

        try:
            if not window.events.loaded.wait(30):
                raise RuntimeError("WebView2 did not load")
            window.native.Invoke(
                Action(lambda: original_clipboard.append(Clipboard.GetDataObject()))
            )

            def render_offscreen():
                # CapturePreview requires a visible control; keep the test outside all screens.
                window.native.ShowInTaskbar = False
                window.native.Location = Point(-20000, -20000)
                window.native.Show()

            window.native.Invoke(Action(render_offscreen))
            window.evaluate_js(
                Path(__file__).with_suffix(".js").read_text(encoding="utf-8"),
                callback=lambda result: (results.append(result), completed.set()),
            )
            if not completed.wait(60):
                stages = (review / "stages.txt").read_text("utf-8")
                raise RuntimeError(f"UI interactions did not finish; stages:\n{stages}")
            report = results[0]
            (review / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
            )
            assert report["ok"], report
            assert report["imageClipboard"]["size"] == image_size
            assert (
                report["imageClipboard"]["png_sha256"]
                == hashlib.sha256(fixture.read_bytes()).hexdigest()
            )
            assert report["imageClipboard"]["icon_size"][0] > 0
            assert all(
                report[field]
                for field in (
                    "textClipboardMatches",
                    "stableCopyLayout",
                    "hoverPrompt",
                    "keyboardConversation",
                    "keyboardViewer",
                    "forkFeedback",
                    "newSession",
                    "logo",
                )
            )
            assert report["forkedRows"] == 2 and report["originalRows"] == 3
        except Exception as exc:
            errors.append(exc)
        finally:
            try:
                if original_clipboard:
                    window.native.Invoke(
                        Action(
                            lambda: (
                                Clipboard.SetDataObject(original_clipboard[0], True)
                                if original_clipboard[0] is not None
                                else Clipboard.Clear()
                            )
                        )
                    )
            finally:
                window.destroy()

    try:
        webview.start(
            verify,
            gui="edgechromium",
            http_server=False,
            storage_path=str(review / "webview"),
            icon=str(files("moru").joinpath("assets/icon.ico")),
        )
        if errors:
            raise errors[0]
        print(f"native_ui_interactions_ok report={review / 'report.json'}", flush=True)
    finally:
        application.close()


if __name__ == "__main__":
    main()
