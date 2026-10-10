"""Check the actual hidden WebView2 shell and JS bridge without loading any models."""

from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import webview

from moru.api import Api
from moru.config import ModelPaths, application_root
from moru.downloads import ModelDownloads
from moru.images.client import ImageWorker
from moru.prompts.local import LlamaPrompts
from moru.repository import Repository
from moru.service import Application


def main():
    root = application_root()
    (root / "data").mkdir(exist_ok=True)
    with TemporaryDirectory(dir=root / "data", prefix="desktop-smoke-") as temporary:
        data_dir = Path(temporary)
        paths = ModelPaths(root)
        downloads = ModelDownloads(paths)
        app = Application(
            Repository(data_dir / "test.db"),
            LlamaPrompts(paths),
            ImageWorker(paths, root / "vendor/comfyui"),
            data_dir,
        )
        window = webview.create_window(
            "Moru shell smoke",
            html=files("moru").joinpath("web/index.html").read_text("utf-8"),
            js_api=Api(app, paths, downloads),
            hidden=True,
        )
        completed = Event()
        result = []
        errors = []

        def verify():
            try:
                if not window.events.loaded.wait(30):
                    from System import Func, Object

                    task = window.native.Invoke(
                        Func[Object](
                            lambda: window.native.browser.webview.EnsureCoreWebView2Async(None)
                        )
                    )
                    if task.Wait(10000):
                        raise RuntimeError("WebView2 initialized but did not load the UI")
                    raise RuntimeError("WebView2 initialization did not finish")
                window.evaluate_js(
                    """
                    new Promise(resolve => {
                        const check = () => {
                            const input = document.querySelector(
                                'textarea[aria-label="이미지 요청"]');
                            if (input && !input.disabled) {
                                resolve({ready: true, title: document.title,
                                    hasComposer: !!document.querySelector('.composer'),
                                    hasEmptyState: !!document.querySelector('.empty'),
                                    bridge: typeof window.pywebview.api.submit_request});
                                return true;
                            }
                            return false;
                        };
                        if (!check()) {
                            const observer = new MutationObserver(() => {
                                if (check()) observer.disconnect();
                            });
                            observer.observe(document.body,
                                {childList:true, subtree:true, attributes:true});
                        }
                    })
                """,
                    callback=lambda value: (result.append(value), completed.set()),
                )
                if not completed.wait(30):
                    raise RuntimeError("React did not initialize through the bridge")
            except Exception as exc:
                errors.append(exc)
            finally:
                window.destroy()

        try:
            webview.start(
                verify,
                gui="edgechromium",
                http_server=False,
                storage_path=str(data_dir / "webview"),
            )
            if errors:
                raise errors[0]
            assert result == [
                {
                    "ready": True,
                    "title": "Moru",
                    "hasComposer": True,
                    "hasEmptyState": True,
                    "bridge": "function",
                }
            ], result
            print("desktop_bridge_and_react_ok", flush=True)
        finally:
            downloads.close()
            app.close()


if __name__ == "__main__":
    main()
