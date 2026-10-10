"""Explicit pywebview bridge. No filesystem paths or tracebacks cross the boundary."""

import base64
import logging
from dataclasses import asdict
from functools import wraps
from pathlib import Path

from moru.config import ModelPaths
from moru.domain import GenerationSettings, PromptSettings
from moru.downloads import ModelDownloads
from moru.errors import MESSAGES, MoruError
from moru.models import MODEL_DEFAULTS, RETIRED_MODELS, image_model, image_model_catalog
from moru.service import Application

log = logging.getLogger(__name__)


def endpoint(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return {"ok": True, "value": function(*args, **kwargs)}
        except MoruError as exc:
            return {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
        except Exception:
            log.exception("bridge call failed endpoint=%s", function.__name__)
            return {
                "ok": False,
                "error": {
                    "code": "GENERATION_FAILED",
                    "message": MESSAGES["GENERATION_FAILED"],
                },
            }

    return call


def settings_to_wire(settings: GenerationSettings) -> dict:
    values = asdict(settings)
    # JavaScript numbers cannot represent every persisted 63-bit seed exactly.
    values["seed"] = str(settings.seed) if settings.seed is not None else None
    return values


class Api:
    def __init__(
        self,
        application: Application,
        models: ModelPaths | None = None,
        downloads: ModelDownloads | None = None,
        choose_file=None,
        copy_to_clipboard=None,
        copy_image_to_clipboard=None,
        chatgpt_auth=None,
        chatgpt_prompts=None,
    ):
        self._app = application
        self._models = models
        self._downloads = downloads
        self._choose_file = choose_file
        self._copy_to_clipboard = copy_to_clipboard
        self._copy_image_to_clipboard = copy_image_to_clipboard
        self._chatgpt_auth = chatgpt_auth
        self._chatgpt_prompts = chatgpt_prompts

    @endpoint
    def copy_prompt(self, text):
        if not isinstance(text, str):
            raise MoruError("INVALID_REQUEST")
        if self._copy_to_clipboard is None:
            raise MoruError("CLIPBOARD_FAILED")
        try:
            self._copy_to_clipboard(text)
        except Exception as exc:
            log.exception("prompt clipboard copy failed")
            raise MoruError("CLIPBOARD_FAILED") from exc

    @endpoint
    def copy_image(self, image_id):
        content = self._image_bytes(image_id)
        if self._copy_image_to_clipboard is None:
            raise MoruError("CLIPBOARD_FAILED")
        try:
            self._copy_image_to_clipboard(content)
        except Exception as exc:
            log.exception("image clipboard copy failed")
            raise MoruError("CLIPBOARD_FAILED") from exc

    @endpoint
    def get_language(self):
        return self._app.get_language()

    @endpoint
    def bootstrap(self):
        project = self._app.current_project()
        return {
            "language": self._app.get_language(),
            "project": self._project_view(project.id),
            "projects": self._projects_view(),
            "settings": settings_to_wire(self._app.get_settings()),
            "generation_defaults": MODEL_DEFAULTS,
            "image_models": image_model_catalog(),
            "prompt_settings": asdict(self._app.get_prompt_settings()),
            "models": self._model_status(),
            "chatgpt": self._chatgpt_auth.status() if self._chatgpt_auth else None,
        }

    def _account_service(self):
        if self._chatgpt_auth is None:
            raise MoruError("CHATGPT_UNAVAILABLE")
        return self._chatgpt_auth

    @endpoint
    def get_chatgpt_status(self):
        return self._account_service().status()

    @endpoint
    def login_chatgpt(self, account_id=None):
        return self._app.run_when_idle(lambda: self._account_service().login(account_id))

    @endpoint
    def cancel_chatgpt_login(self):
        return self._account_service().cancel_login()

    @endpoint
    def logout_chatgpt(self):
        return self._app.run_when_idle(lambda: self._account_service().logout())

    @endpoint
    def select_chatgpt_account(self, account_id):
        return self._app.run_when_idle(lambda: self._account_service().select_account(account_id))

    @endpoint
    def dismiss_chatgpt_welcome(self):
        return self._account_service().dismiss_welcome()

    @endpoint
    def get_chatgpt_models(self):
        if self._chatgpt_prompts is None:
            raise MoruError("CHATGPT_UNAVAILABLE")
        return self._chatgpt_prompts.models()

    @endpoint
    def select_prompt_provider(self, provider):
        from dataclasses import replace

        def select():
            settings = replace(self._app.get_prompt_settings(), provider=provider)
            self._validate_prompt_provider(settings)
            self._app.update_settings(self._app.get_settings(), settings)
            return asdict(settings)

        return self._app.run_when_idle(select)

    @endpoint
    def configure_prompt_writer(self, values):
        from dataclasses import replace

        if not isinstance(values, dict) or "provider" in values:
            raise MoruError("INVALID_SETTINGS")

        def configure():
            try:
                settings = replace(self._app.get_prompt_settings(), **values)
            except TypeError as exc:
                raise MoruError("INVALID_SETTINGS") from exc
            # Preparation can precede files/sign-in; activation validates readiness separately.
            self._app.update_settings(self._app.get_settings(), settings)
            return asdict(settings)

        return self._app.run_when_idle(configure)

    def _validate_prompt_provider(self, settings):
        if settings.provider == "chatgpt":
            status = self._account_service().status()
            if status["login_state"] == "waiting":
                raise MoruError("GENERATION_BUSY")
            if not status["connected"]:
                raise MoruError("CHATGPT_SIGN_IN_REQUIRED")
            if not status["plan_enabled"]:
                raise MoruError("CHATGPT_NOT_ELIGIBLE")
        elif self._models is not None:
            path = self._models.get("prompt")
            if not path.is_file() or not path.stat().st_size:
                raise MoruError("PROMPT_MODEL_NOT_FOUND")

    def _model_status(self):
        if self._downloads is not None:
            return [
                {
                    **item,
                    "download": {
                        **item["download"],
                        "message": MESSAGES.get(item["download"]["error_code"]),
                    }
                    if item["download"]
                    else None,
                }
                for item in self._downloads.status()
            ]
        return self._models.status() if self._models is not None else []

    @endpoint
    def get_model_status(self):
        return self._model_status()

    @endpoint
    def select_local_model(self, model_id):
        if self._models is None or self._choose_file is None:
            raise MoruError("MODEL_LOAD_FAILED")
        selected = self._choose_file(model_id)
        if selected:
            self._models.set(model_id, Path(selected))
        return self._model_status()

    @endpoint
    def download_model(self, model_id):
        if self._downloads is None:
            raise MoruError("MODEL_DOWNLOAD_FAILED")
        self._downloads.start(model_id)
        return self._model_status()

    @endpoint
    def cancel_model_download(self, model_id):
        if self._downloads is not None:
            self._downloads.cancel(model_id)
        return self._model_status()

    def _projects_view(self):
        return [asdict(project) for project in self._app.repository.list_projects()]

    @endpoint
    def list_projects(self):
        return self._projects_view()

    @endpoint
    def create_project(self):
        return self._project_view(self._app.create_project().id)

    @endpoint
    def open_project(self, project_id):
        return self._project_view(self._app.open_project(project_id).id)

    @endpoint
    def get_project(self, project_id):
        return self._project_view(project_id)

    def _project_view(self, project_id):
        repository = self._app.repository
        project = repository.get_project(project_id)
        images = []
        for request, image, versions in repository.conversation(project_id):
            images.append(
                {
                    "id": image.id,
                    "width": image.settings.width,
                    "height": image.settings.height,
                    "turn_id": request.id,
                    "request_text": request.text if request.kind != "manual" else None,
                    "created_at": image.created_at,
                    "parent_image_id": image.parent_image_id,
                    "versions": [version.id for version in versions],
                }
            )
        unfinished = [
            {
                "id": request.id,
                "width": request.settings.width,
                "height": request.settings.height,
                "turn_id": request.turn_id,
                "text": request.text if request.kind != "manual" else None,
                "status": request.status,
                "error_code": request.error_code,
                "message": MESSAGES.get(request.error_code),
            }
            for request in repository.unfinished_requests(project_id)
            if request.turn_id
            or request.base_image_id == project.active_leaf_id
            or request.status == "pending"
        ]
        return {**asdict(project), "images": images, "unfinished_requests": unfinished}

    @endpoint
    def fork(self, project_id, image_id):
        return self._project_view(self._app.fork(project_id, image_id).id)

    @endpoint
    def select_version(self, project_id, image_id):
        self._app.select_version(project_id, image_id)
        return self._project_view(project_id)

    @endpoint
    def regenerate(self, image_id):
        return asdict(self._app.regenerate(image_id))

    @endpoint
    def submit_request(self, project_id, text):
        def submit():
            self._check_chatgpt_login()
            return asdict(self._app.submit_request(project_id, text))

        return self._app.run_when_idle(submit)

    @endpoint
    def generate_from_prompt(self, image_id, prompt):
        return asdict(self._app.generate_from_prompt(image_id, prompt))

    @endpoint
    def retry_request(self, request_id):
        def retry():
            if self._app.repository.get_request(request_id).kind != "manual":
                self._check_chatgpt_login()
            return asdict(self._app.retry_request(request_id))

        return self._app.run_when_idle(retry)

    def _check_chatgpt_login(self):
        if self._app.get_prompt_settings().provider == "chatgpt":
            if self._account_service().status()["login_state"] == "waiting":
                raise MoruError("GENERATION_BUSY")

    @endpoint
    def get_job(self, job_id):
        job = self._app.get_job(job_id)
        return {**asdict(job), "message": MESSAGES.get(job.error_code)}

    @endpoint
    def cancel_job(self, job_id):
        self._app.cancel_job(job_id)

    @endpoint
    def get_settings(self):
        return settings_to_wire(self._app.get_settings())

    @endpoint
    def get_prompt_settings(self):
        return asdict(self._app.get_prompt_settings())

    @endpoint
    def set_language(self, language):
        return self._app.set_language(language)

    @endpoint
    def update_settings(self, values, prompt_values=None):
        try:
            if not isinstance(values, dict):
                raise ValueError("settings must be an object")
            values = dict(values)
            seed = values.get("seed")
            if isinstance(seed, str):
                if not seed.isascii() or not seed.isdecimal():
                    raise ValueError("invalid seed")
                values["seed"] = int(seed)
            settings = GenerationSettings(**values)
            if prompt_values is not None and not isinstance(prompt_values, dict):
                raise ValueError("prompt settings must be an object")
            prompt_settings = PromptSettings(**prompt_values) if prompt_values is not None else None
        except (TypeError, ValueError) as exc:
            raise MoruError("INVALID_SETTINGS") from exc
        if prompt_settings is not None:
            self._validate_prompt_provider(prompt_settings)
        self._app.update_settings(settings, prompt_settings)
        return settings_to_wire(settings)

    @endpoint
    def get_image_details(self, image_id):
        image = self._app.repository.get_image(image_id)
        return {
            "id": image.id,
            "prompt": image.prompt,
            "model_name": (
                RETIRED_MODELS[image.settings.model_id]["name"]
                if image.settings.model_id in RETIRED_MODELS
                else image_model(image.settings.model_id).name
            ),
            "settings": settings_to_wire(image.settings),
        }

    @endpoint
    def get_image_source(self, image_id):
        content = self._image_bytes(image_id)
        return "data:image/png;base64," + base64.b64encode(content).decode("ascii")

    def _image_bytes(self, image_id):
        image = self._app.repository.get_image(image_id)
        root = self._app.data_dir.resolve()
        path = (root / image.image_path).resolve()
        if not path.is_relative_to(root):
            raise MoruError("IMAGE_SAVE_FAILED")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise MoruError("IMAGE_SAVE_FAILED") from exc
        return content
