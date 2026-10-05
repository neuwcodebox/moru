"""Verified atomic model downloads; only fixed manifest URLs reach the network."""

import hashlib
import json
import logging
import os
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from importlib.resources import files
from pathlib import Path
from threading import Event, RLock
from urllib.request import urlopen

from moru.config import DEFAULT_MODEL_FILES, ModelPaths
from moru.errors import MoruError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelAsset:
    url: str
    sha256: str
    size: int

    def __post_init__(self):
        if (
            not self.url.startswith("https://")
            or len(self.sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.sha256)
            or type(self.size) is not int
            or self.size <= 0
        ):
            raise MoruError("MODEL_DOWNLOAD_FAILED")


def model_manifest() -> dict[str, ModelAsset]:
    contents = files("moru").joinpath("model-manifest.json").read_text(encoding="utf-8")
    return {key: ModelAsset(**value) for key, value in json.loads(contents).items()}


def download_model(
    asset: ModelAsset, target: Path, progress, cancelled: Event, *, open_url=urlopen
):
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        if cancelled.is_set():
            raise MoruError("MODEL_DOWNLOAD_CANCELLED")
        target.parent.mkdir(parents=True, exist_ok=True)
        received = 0
        digest = hashlib.sha256()
        progress(0, asset.size)
        with open_url(asset.url, timeout=10) as response, temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                if cancelled.is_set():
                    raise MoruError("MODEL_DOWNLOAD_CANCELLED")
                received += len(block)
                if received > asset.size:
                    raise MoruError("MODEL_CHECKSUM_FAILED")
                digest.update(block)
                output.write(block)
                progress(received, asset.size)
            output.flush()
            os.fsync(output.fileno())
        if cancelled.is_set():
            raise MoruError("MODEL_DOWNLOAD_CANCELLED")
        if received != asset.size or digest.hexdigest() != asset.sha256:
            raise MoruError("MODEL_CHECKSUM_FAILED")
        os.replace(temporary, target)
    except MoruError:
        raise
    except OSError as exc:
        raise MoruError("MODEL_DOWNLOAD_FAILED") from exc
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Download:
    model_id: str
    state: str = "queued"
    received: int = 0
    total: int = 0
    error_code: str | None = None


class ModelDownloads:
    def __init__(
        self,
        paths: ModelPaths,
        *,
        manifest=None,
        executor: Executor | None = None,
        open_url=urlopen,
    ):
        self._paths = paths
        self._manifest = manifest if manifest is not None else model_manifest()
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="models")
        self._open_url = open_url
        self._lock = RLock()
        self._active = None
        self._cancelled = Event()
        self._downloads = {}
        self._closed = False

    def status(self) -> list[dict]:
        with self._lock:
            result = []
            for item in self._paths.status():
                asset = self._manifest.get(item["id"])
                download = self._downloads.get(item["id"])
                result.append({
                    **item,
                    "manual_download": {
                        "url": asset.url.replace("/resolve/", "/blob/", 1),
                        "filename": asset.url.rsplit("/", 1)[1],
                    } if asset else None,
                    "download": asdict(download) if download else None,
                })
            return result

    def start(self, model_id: str) -> Download:
        with self._lock:
            if self._closed:
                raise MoruError("APP_CLOSED")
            if self._active is not None:
                raise MoruError("GENERATION_BUSY")
            if model_id not in self._manifest or model_id not in DEFAULT_MODEL_FILES:
                raise MoruError("INVALID_SETTINGS")
            asset = self._manifest[model_id]
            download = Download(model_id, total=asset.size)
            self._downloads[model_id] = download
            self._active = model_id
            self._cancelled = Event()
            try:
                self._executor.submit(self._run, model_id, asset, self._cancelled)
            except Exception as exc:
                self._active = None
                self._downloads[model_id] = replace(
                    download, state="failed", error_code="MODEL_DOWNLOAD_FAILED"
                )
                raise MoruError("MODEL_DOWNLOAD_FAILED") from exc
            return download

    def _run(self, model_id: str, asset: ModelAsset, cancelled: Event):
        def progress(received, total):
            with self._lock:
                self._downloads[model_id] = replace(
                    self._downloads[model_id], state="downloading", received=received
                )

        try:
            target = self._paths.root / "models" / DEFAULT_MODEL_FILES[model_id][0]
            download_model(asset, target, progress, cancelled, open_url=self._open_url)
            self._paths.set(model_id, target)
            with self._lock:
                self._downloads[model_id] = replace(self._downloads[model_id], state="completed")
            log.info("model download verified id=%s", model_id)
        except Exception as exc:
            code = exc.code if isinstance(exc, MoruError) else "MODEL_DOWNLOAD_FAILED"
            log.exception("model download failed id=%s code=%s", model_id, code)
            with self._lock:
                self._downloads[model_id] = replace(
                    self._downloads[model_id],
                    error_code=code,
                    state="cancelled" if code == "MODEL_DOWNLOAD_CANCELLED" else "failed",
                )
        finally:
            with self._lock:
                self._active = None

    def cancel(self, model_id: str):
        with self._lock:
            if self._active == model_id:
                self._cancelled.set()

    def close(self):
        with self._lock:
            self._closed = True
            self._cancelled.set()
        self._executor.shutdown(wait=True)
