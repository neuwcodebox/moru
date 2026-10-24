"""Application use cases and a single cancellable background generation slot."""

import logging
import os
import secrets
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, RLock

from moru.cancellation import check_cancelled
from moru.domain import GenerationSettings, Image, Project, PromptSettings, PromptTurn, Request
from moru.errors import MoruError
from moru.images.files import verify_png
from moru.language import SUPPORTED_LANGUAGES, saved_language
from moru.models import image_model
from moru.ports import ImageGenerator, PromptGenerator
from moru.regions import decode_mask
from moru.repository import Repository

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    id: str
    request_id: str
    project_id: str
    width: int
    height: int
    state: str = "queued"
    step: int | None = None
    total: int | None = None
    image_id: str | None = None
    error_code: str | None = None
    thinking_enabled: bool = False
    prompt_text: str = ""
    scene_prompt_text: str = ""
    region_edit: bool = False
    turn_id: str | None = None
    found_tag_count: int = 0


class Application:
    def __init__(
        self,
        repository: Repository,
        prompts: PromptGenerator,
        images: ImageGenerator,
        data_dir: Path,
        *,
        executor: Executor | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(),
        new_seed: Callable[[], int] = lambda: secrets.randbelow(2**63),
    ):
        self.repository = repository
        self.prompts = prompts
        self.images = images
        self.data_dir = data_dir
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="generation"
        )
        self._new_id, self._now, self._new_seed = new_id, now, new_seed
        self._lock = RLock()
        self._jobs: dict[str, Job] = {}
        self._active_job: str | None = None
        self._cancelled = Event()
        self._closed = False

    def _available(self):
        if self._closed:
            raise MoruError("APP_CLOSED")
        if self._active_job is not None:
            raise MoruError("GENERATION_BUSY")

    def run_when_idle(self, action):
        with self._lock:
            self._available()
            return action()

    def create_project(self) -> Project:
        with self._lock:
            self._available()
            project = Project(self._new_id(), self._now())
            self.repository.create_project(project)
            return project

    def current_project(self) -> Project:
        with self._lock:
            project_id = self.repository.get_preference("current_project")
            return self.repository.get_project(project_id) if project_id else self.create_project()

    def open_project(self, project_id: str) -> Project:
        with self._lock:
            self._available()
            self.repository.set_current_project(project_id)
            return self.repository.get_project(project_id)

    def fork(self, project_id: str, image_id: str) -> Project:
        with self._lock:
            self._available()
            project = Project(self._new_id(), self._now())
            self.repository.copy_session(project, project_id, image_id, self._new_id)
            return self.repository.get_project(project.id)

    def select_version(self, project_id: str, image_id: str):
        with self._lock:
            self._available()
            self.repository.select_version(project_id, image_id)

    def get_settings(self) -> GenerationSettings:
        return GenerationSettings(**self.repository.get_preference("settings", {}))

    def get_prompt_settings(self) -> PromptSettings:
        return PromptSettings(**self.repository.get_preference("prompt_settings", {}))

    def get_language(self) -> str:
        return saved_language(self.repository.get_preference("language", "ko"))

    def set_language(self, language: str) -> str:
        with self._lock:
            if self._closed:
                raise MoruError("APP_CLOSED")
            if not isinstance(language, str) or language not in SUPPORTED_LANGUAGES:
                raise MoruError("INVALID_SETTINGS")
            self.repository.set_preference("language", language)
            return language

    def update_settings(
        self, settings: GenerationSettings, prompt_settings: PromptSettings | None = None
    ):
        with self._lock:
            if self._closed:
                raise MoruError("APP_CLOSED")
            image_model(settings.model_id)
            values = {"settings": asdict(settings)}
            if prompt_settings is not None:
                values["prompt_settings"] = asdict(prompt_settings)
            self.repository.set_preferences(values)

    def submit_request(self, project_id: str, text: str) -> Job:
        with self._lock:
            self._available()
            if not isinstance(text, str) or not text.strip():
                raise MoruError("INVALID_REQUEST")
            project = self.repository.get_project(project_id)
            base = project.active_leaf_id
            request = Request(
                self._new_id(),
                project_id,
                text.strip(),
                self._now(),
                base,
                "refine" if base else "create",
                self.get_settings(),
            )
            self.repository.add_request(request)
            return self._enqueue(request)

    def generate_from_prompt(self, image_id: str, prompt: str) -> Job:
        with self._lock:
            self._available()
            if not isinstance(prompt, str) or not prompt.strip():
                raise MoruError("INVALID_REQUEST")
            image = self.repository.get_image(image_id)
            request = Request(
                self._new_id(),
                image.project_id,
                prompt.strip(),
                self._now(),
                image.id,
                "manual",
                self.get_settings(),
                turn_id=self.repository.image_turn(image.id),
            )
            self.repository.add_request(request)
            return self._enqueue(request)

    def edit_region(self, image_id: str, content: str, mask: str) -> Job:
        with self._lock:
            self._available()
            if not isinstance(content, str) or not content.strip() or len(content) > 8000:
                raise MoruError("INVALID_REQUEST")
            if self.get_prompt_settings().provider == "direct":
                raise MoruError("REGION_PROMPT_WRITER_REQUIRED")
            image = self.repository.get_image(image_id)
            settings = self.get_settings()
            if image_model(settings.model_id).family != "anima":
                raise MoruError("REGION_UNSUPPORTED")
            pixels = decode_mask(mask, (image.settings.width, image.settings.height))
            settings = replace(settings, width=image.settings.width, height=image.settings.height)
            request_id = self._new_id()
            relative = Path("masks") / f"{request_id}.png"
            target = self.data_dir / relative
            created = False
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    created = True
                    output.write(pixels)
                    output.flush()
                    os.fsync(output.fileno())
                request = Request(
                    request_id, image.project_id, content.strip(), self._now(), image.id,
                    "region", settings, turn_id=self.repository.image_turn(image.id),
                    mask_path=relative.as_posix(), source_image_path=image.image_path,
                )
                self.repository.add_request(request)
            except Exception as exc:
                if created:
                    target.unlink(missing_ok=True)
                if isinstance(exc, OSError):
                    raise MoruError("IMAGE_SAVE_FAILED") from exc
                raise
            return self._enqueue(request)

    def get_edit_tab(self) -> str:
        tab = self.repository.get_preference("edit_tab", "prompt")
        return tab if tab in ("prompt", "region") else "prompt"

    def set_edit_tab(self, tab: str):
        if tab not in ("prompt", "region"):
            raise MoruError("INVALID_SETTINGS")
        self.repository.set_preference("edit_tab", tab)

    def regenerate(self, image_id: str) -> Job:
        image = self.repository.get_image(image_id)
        return self.generate_from_prompt(image_id, image.full_prompt)

    def retry_request(self, request_id: str) -> Job:
        with self._lock:
            self._available()
            request = self.repository.get_request(request_id)
            if request.status not in ("failed", "cancelled"):
                raise MoruError("INVALID_REQUEST")
            image_model(request.settings.model_id)
            self.repository.set_request_status(request_id, "pending")
            return self._enqueue(replace(request, status="pending", error_code=None))

    def _enqueue(self, request: Request) -> Job:
        job = Job(
            self._new_id(),
            request.id,
            request.project_id,
            width=request.settings.width,
            height=request.settings.height,
            turn_id=request.turn_id,
            region_edit=request.kind == "region",
        )
        self._jobs[job.id] = job
        self._active_job = job.id
        self._cancelled = Event()
        try:
            prompt_settings = self.get_prompt_settings()
            job = replace(
                job,
                thinking_enabled=(request.kind != "region" and prompt_settings.provider == "local"
                                  and prompt_settings.thinking),
            )
            self._jobs[job.id] = job
            self._executor.submit(self._generate, job.id, request, self._cancelled, prompt_settings)
        except Exception as exc:
            self._active_job = None
            self.repository.set_request_status(request.id, "failed", "GENERATION_FAILED")
            self._jobs[job.id] = replace(job, state="failed", error_code="GENERATION_FAILED")
            raise MoruError("GENERATION_FAILED") from exc
        return job

    def get_job(self, job_id: str) -> Job:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise MoruError("NOT_FOUND") from exc

    def cancel_job(self, job_id: str):
        with self._lock:
            self.get_job(job_id)
            if job_id == self._active_job:
                self._cancelled.set()

    def _progress(self, job_id: str, state: str, step=None, total=None):
        with self._lock:
            self._jobs[job_id] = replace(self._jobs[job_id], state=state, step=step, total=total)

    def _prompt_stage(self, job_id, stage, found_tag_count):
        with self._lock:
            self._jobs[job_id] = replace(
                self._jobs[job_id],
                state=stage,
                found_tag_count=found_tag_count,
                step=None,
                total=None,
            )

    def _generate(
        self, job_id: str, request: Request, cancelled: Event, prompt_settings: PromptSettings
    ):
        output_path: Path | None = None
        try:
            log.info("generation started id=%s", job_id)
            check_cancelled(cancelled)
            sources = []
            scene_prompt = None
            if request.kind == "region":
                prepared = self._prepare_region(
                    job_id, request, prompt_settings, cancelled, sources.append,
                )
                prompt, scene_prompt = prepared.region_prompt, prepared.scene_prompt
            else:
                prompt = self._prepare_prompt(
                    job_id,
                    request,
                    prompt_settings,
                    cancelled,
                    sources.append,
                )
            check_cancelled(cancelled)
            settings = request.settings
            if settings.seed is None:
                settings = settings.resolve_seed(self._new_seed())
            image_id = self._new_id()
            relative_path = Path("images") / f"{image_id}.png"
            if (self.data_dir / relative_path).exists():
                raise MoruError("IMAGE_SAVE_FAILED")
            output_path = self.data_dir / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._progress(job_id, "loading_model")

            def progress(state, step=None, total=None):
                self._progress(job_id, state, step, total)

            self._write_image(prompt, request, settings, output_path, progress, cancelled)
            check_cancelled(cancelled)
            image = Image(
                image_id,
                request.project_id,
                request.id,
                request.base_image_id,
                prompt,
                relative_path.as_posix(),
                settings,
                self._now(),
                request.kind,
                sources=tuple(sources),
                scene_prompt=scene_prompt,
            )
            # Cancellation and persistence share a lock: committed success stays successful.
            with self._lock:
                check_cancelled(cancelled)
                self.repository.complete_generation(image)
                self._jobs[job_id] = replace(
                    self._jobs[job_id],
                    state="completed",
                    image_id=image.id,
                    prompt_text="",
                    scene_prompt_text="",
                )
            output_path = None
            log.info("generation completed id=%s", job_id)
        except Exception as exc:
            code = exc.code if isinstance(exc, MoruError) else "GENERATION_FAILED"
            log.exception("generation failed id=%s code=%s", job_id, code)
            state = "cancelled" if code == "GENERATION_CANCELLED" else "failed"
            try:
                self.repository.set_request_status(request.id, state, code)
            except MoruError:
                code = "DATABASE_FAILED"
                log.exception("request failure could not be saved id=%s", request.id)
            with self._lock:
                self._jobs[job_id] = replace(
                    self._jobs[job_id],
                    state=state,
                    error_code=code,
                    prompt_text="",
                    scene_prompt_text="",
                )
        finally:
            if output_path is not None:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    log.exception("incomplete generation file cleanup failed id=%s", job_id)
            with self._lock:
                self._active_job = None

    def _prepare_region(self, job_id, request, settings, cancelled, on_source):
        if settings.provider == "direct":
            raise MoruError("REGION_PROMPT_WRITER_REQUIRED")
        base = self.repository.get_image(request.base_image_id)
        self._reserve_prompt_memory(job_id, settings, cancelled, "prompting")
        prepared = self.prompts.edit_region(
            base.full_prompt, request.text, settings, cancelled,
            on_ready=lambda: self._progress(job_id, "writing_region_prompt"),
            on_progress=lambda stage, region, scene: self._region_progress(
                job_id, stage, region, scene,
            ),
            on_source=on_source,
            on_stage=lambda stage, count: self._prompt_stage(
                job_id, "searching_tags" if stage == "searching_tags" else "writing_region_prompt",
                count,
            ),
        )
        self._region_progress(job_id, "scene", prepared.region_prompt, prepared.scene_prompt)
        return prepared

    def _region_progress(self, job_id, stage, region, scene):
        with self._lock:
            self._jobs[job_id] = replace(
                self._jobs[job_id],
                state="writing_region_prompt" if stage == "region" else "writing_scene_prompt",
                prompt_text=region[-65536:], scene_prompt_text=scene[-65536:],
            )

    def _prepare_prompt(self, job_id, request, settings, cancelled, on_source) -> str:
        if request.kind == "manual":
            base = self.repository.get_image(request.base_image_id)
            if request.text == base.full_prompt:
                for source in base.sources:
                    on_source(source)
            self._prompt_progress(job_id, request.text)
            return request.text
        if settings.provider == "direct":
            self.prompts.unload()
            self._prompt_progress(job_id, request.text)
            return request.text
        ready_state = "thinking" if settings.provider == "chatgpt" else "prompting"
        self._reserve_prompt_memory(job_id, settings, cancelled, ready_state)

        def progress(_thinking, prompt):
            self._prompt_progress(job_id, prompt)

        context = {
            "history": self._prompt_history(request, settings.history_turns),
            "model_id": request.settings.model_id,
            "on_ready": lambda: self._progress(job_id, ready_state),
            "on_stage": lambda stage, count: self._prompt_stage(job_id, stage, count),
            "on_source": on_source,
        }

        if request.base_image_id:
            base = self.repository.get_image(request.base_image_id)
            prompt = self.prompts.refine(
                base.full_prompt,
                request.text,
                settings,
                cancelled,
                progress,
                **context,
            )
        else:
            prompt = self.prompts.create(
                request.text,
                settings,
                cancelled,
                progress,
                **context,
            )
        if not isinstance(prompt, str) or not prompt.strip():
            raise MoruError("PROMPT_EMPTY_RESPONSE")
        self._prompt_progress(job_id, prompt)
        return prompt

    def _reserve_prompt_memory(self, job_id, settings, cancelled, ready_state):
        required = self.prompts.memory_required(settings)
        self._progress(job_id, "loading_prompt_model" if required else ready_state)
        if settings.provider == "local" or required:
            self.images.reserve_memory(required, cancelled)
        check_cancelled(cancelled)

    def _prompt_history(self, request: Request, limit: int) -> tuple[PromptTurn, ...]:
        if not limit or request.base_image_id is None:
            return ()
        base = self.repository.get_image(request.base_image_id)
        base_turn = self.repository.image_turn(base.id)
        history = []
        for original, selected, _ in self.repository.conversation(request.project_id):
            # A retry keeps its original base even if the selected version has since changed.
            if original.id == base_turn:
                selected = base
            history.append(PromptTurn(original.text, selected.full_prompt))
            if original.id == base_turn:
                break
        return tuple(history[-limit:])

    def _prompt_progress(self, job_id, prompt):
        with self._lock:
            self._jobs[job_id] = replace(self._jobs[job_id], prompt_text=prompt[-65536:])

    def _write_image(self, prompt, request, settings, output_path, progress, cancelled):
        def generate():
            if request.kind == "region":
                self.images.inpaint(
                    prompt, settings, output_path, progress, cancelled,
                    self.data_dir / request.source_image_path, self.data_dir / request.mask_path,
                )
            else:
                self.images.generate(prompt, settings, output_path, progress, cancelled)

        if self.images.needs_prompt_unload(settings, cancelled):
            log.info("releasing prompt model before image loading: VRAM budget exceeded")
            self.prompts.unload()
        check_cancelled(cancelled)
        try:
            generate()
        except MoruError as exc:
            if exc.code != "CUDA_OOM":
                raise
            check_cancelled(cancelled)
            log.info("releasing prompt model for image generation")
            self.prompts.unload()
            generate()
        check_cancelled(cancelled)
        verify_png(output_path, settings.width, settings.height)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancelled.set()
        try:
            self.images.close()
        finally:
            self._executor.shutdown(wait=True)
            try:
                self.prompts.unload()
            finally:
                self.repository.close()
