"""Local CUDA prompt writing with canonical state and bounded conversational context."""

import ctypes
import gc
import importlib.util
import logging
import os
import sys
from pathlib import Path
from threading import Event, RLock

from moru.cancellation import check_cancelled
from moru.config import ModelPaths
from moru.domain import PromptSettings, PromptTurn
from moru.errors import MoruError
from moru.memory_budget import prompt_memory_required
from moru.models import image_model
from moru.ports import PromptProgress
from moru.prompts.completion import PromptParagraph, ThinkingBudget, read_completion
from moru.prompts.instructions import (
    CREATE_SYSTEM,
    NATURAL_CREATE_SYSTEM,
    NATURAL_REFINE_SYSTEM,
    REFINE_SYSTEM,
)
from moru.prompts.tag_search import (
    QUERY_SYSTEM,
    REFERENCE_TOKENS,
    TagSearch,
    add_tag_references,
    parse_queries,
)
from moru.prompts.text import (
    ANSWER_PREFIX,
    conversation_messages,
)

log = logging.getLogger(__name__)


def prompt_messages(
    text: str,
    base_prompt: str | None = None,
    history: tuple[PromptTurn, ...] = (),
    model_id: str = "anima-turbo-v1.1",
) -> list[dict[str, str]]:
    model = image_model(model_id)
    if model.natural_prompt:
        system = NATURAL_CREATE_SYSTEM if base_prompt is None else NATURAL_REFINE_SYSTEM
    else:
        system = CREATE_SYSTEM if base_prompt is None else REFINE_SYSTEM
    system += model.prompt_suffix
    return [
        {"role": "system", "content": system},
        *conversation_messages(text, base_prompt, history),
    ]


def fit_messages(messages, count_tokens, input_limit):
    messages = list(messages)
    while count_tokens(messages) > input_limit:
        if len(messages) <= 2:
            raise MoruError("PROMPT_CONTEXT_TOO_LONG")
        del messages[1:3]  # Drop complete oldest turns; never truncate canonical state.
    return messages


class LlamaPrompts:
    def __init__(self, paths: ModelPaths, *, load_llama=None, tag_search: TagSearch | None = None):
        self._paths = paths
        self._load_llama = load_llama
        self._tag_search = tag_search
        self._llm = None
        self._loaded_path = None
        self._context_size = None
        self._thinking_handlers = {}
        self._formatters = {}
        self._lock = RLock()
        self._dll_directories = []
        self._cuda_libraries = []

    def _can_reuse(self, path: Path, context_size: int) -> bool:
        return (
            self._llm is not None
            and path == self._loaded_path
            and context_size == self._context_size
        )

    def memory_required(self, settings: PromptSettings) -> int:
        path = self._paths.get("prompt")
        if not path.is_file():
            raise MoruError("PROMPT_MODEL_NOT_FOUND")
        with self._lock:
            if self._can_reuse(path, settings.context_size):
                return 0
            return prompt_memory_required(path, settings)

    def _load(self, settings: PromptSettings):
        path = self._paths.get("prompt")
        if not path.is_file():
            raise MoruError("PROMPT_MODEL_NOT_FOUND")
        if self._can_reuse(path, settings.context_size):
            return self._llm
        self.unload()
        try:
            if self._load_llama is None:
                # CUDA wheels share the bundled PyTorch CUDA runtime; users need no toolkit.
                if sys.platform == "win32" and not self._dll_directories:
                    torch_spec = importlib.util.find_spec("torch")
                    if torch_spec is not None and torch_spec.origin:
                        library_dir = Path(torch_spec.origin).parent / "lib"
                        if library_dir.is_dir():
                            self._dll_directories.append(os.add_dll_directory(str(library_dir)))
                            self._cuda_libraries = [
                                ctypes.WinDLL(str(library_dir / name))
                                for name in (
                                    "cudart64_12.dll",
                                    "cublasLt64_12.dll",
                                    "cublas64_12.dll",
                                )
                            ]
                import llama_cpp

                if not llama_cpp.llama_supports_gpu_offload():
                    raise MoruError("MODEL_LOAD_FAILED")
                factory = llama_cpp.Llama
            else:
                factory = self._load_llama
            self._llm = factory(
                model_path=str(path), n_gpu_layers=-1, n_ctx=settings.context_size, verbose=False
            )
            self._loaded_path = path
            self._context_size = settings.context_size
            log.info("prompt model loaded on CUDA")
            return self._llm
        except MoruError:
            raise
        except Exception as exc:
            raise MoruError("MODEL_LOAD_FAILED") from exc

    def _configure_thinking(self, llm, enabled: bool):
        template = llm.metadata.get("tokenizer.chat_template")
        if not isinstance(template, str) or "enable_thinking" not in template:
            if not enabled:
                raise MoruError("THINKING_UNSUPPORTED")
            return
        if enabled not in self._thinking_handlers:
            from llama_cpp.llama_chat_format import Jinja2ChatFormatter

            eos = llm.token_eos()
            bos = llm.token_bos()
            # llama-cpp's completion API does not pass enable_thinking to the template.
            formatter = Jinja2ChatFormatter(
                template="{% set enable_thinking = " + str(enabled).lower() + " %}\n" + template,
                eos_token=llm.detokenize([eos], special=True).decode() if eos != -1 else "",
                bos_token=llm.detokenize([bos], special=True).decode() if bos != -1 else "",
                stop_token_ids=[eos] if eos != -1 else None,
            )
            self._thinking_handlers[enabled] = formatter.to_chat_handler()
            self._formatters[enabled] = formatter
        llm.chat_handler = self._thinking_handlers[enabled]

    def _complete(
        self,
        messages,
        settings: PromptSettings,
        cancelled: Event,
        progress: PromptProgress | None,
        on_ready=None,
        *,
        search_tags=False,
        on_source=None,
        on_stage=None,
    ) -> str:
        with self._lock:
            check_cancelled(cancelled)
            llm = self._load(settings)
            try:
                check_cancelled(cancelled)
                self._configure_thinking(llm, settings.thinking)

                def count_tokens(items):
                    return self._count_tokens(llm, items, settings.thinking)

                input_limit = settings.context_size - settings.max_tokens
                use_search = search_tags and self._tag_search is not None
                reserve = 0
                if use_search:
                    # Reserve lookup space before planning so both passes see the same history.
                    core_tokens = count_tokens([messages[0], messages[-1]])
                    reserve = min(REFERENCE_TOKENS, max(0, input_limit - core_tokens))
                messages = fit_messages(messages, count_tokens, input_limit - reserve)
                check_cancelled(cancelled)
                if on_ready is not None:
                    on_ready()
                if use_search:
                    references, found_count = self._search(
                        llm,
                        messages,
                        settings,
                        cancelled,
                        on_source,
                        on_stage,
                    )
                    base_tokens = count_tokens(messages)
                    messages = add_tag_references(messages, references, count_tokens, input_limit)
                    log.info(
                        "local tag references found_tags=%d added_tokens=%d",
                        found_count,
                        max(0, count_tokens(messages) - base_tokens),
                    )
                    check_cancelled(cancelled)
                    if on_stage is not None:
                        on_stage("prompting", found_count)
                check_cancelled(cancelled)
                return self._infer(llm, messages, settings, cancelled, progress)
            except MoruError:
                raise
            except Exception as exc:
                raise MoruError("PROMPT_LLM_FAILED") from exc

    def _count_tokens(self, llm, messages, thinking):
        formatter = self._formatters.get(thinking)
        if formatter is not None:
            rendered = formatter(messages=messages)
            return len(
                llm.tokenize(
                    rendered.prompt.encode(),
                    add_bos=not rendered.added_special,
                    special=True,
                )
            )
        return sum(len(llm.tokenize(item["content"].encode())) + 16 for item in messages)

    def _search(self, llm, messages, settings, cancelled, on_source, on_stage):
        if on_stage is not None:
            on_stage("searching_tags", 0)
        check_cancelled(cancelled)
        queries_input = [{"role": "system", "content": QUERY_SYSTEM}, *messages[1:]]
        try:
            if self._count_tokens(llm, queries_input, settings.thinking) > (
                settings.context_size - settings.max_tokens
            ):
                raise MoruError("PROMPT_CONTEXT_TOO_LONG")
            reply = self._infer(llm, queries_input, settings, cancelled, None)
        except MoruError as exc:
            if exc.code not in (
                "PROMPT_OUTPUT_TOO_LONG",
                "PROMPT_CONTEXT_TOO_LONG",
                "PROMPT_EMPTY_RESPONSE",
                "PROMPT_INVALID_RESPONSE",
                "PROMPT_NON_ENGLISH_RESPONSE",
            ):
                raise
            check_cancelled(cancelled)
            log.warning("local tag query plan rejected code=%s", exc.code)
            return (), 0
        try:
            queries = parse_queries(reply)
        except ValueError:
            log.warning("local tag query plan rejected code=invalid_query_format")
            return (), 0
        check_cancelled(cancelled)
        log.info("local tag search planned query_count=%d", len(queries))
        return self._tag_search.lookup(queries, cancelled, on_source, on_stage)

    def _infer(self, llm, messages, settings, cancelled, progress):
        processors = []
        if settings.thinking:
            end_tokens = llm.tokenize(b"</think>", add_bos=False, special=True)
            suffix = f"\n\n{ANSWER_PREFIX}\n".encode()
            suffix_tokens = llm.tokenize(suffix, add_bos=False)
            processors.append(
                ThinkingBudget(
                    end_tokens,
                    max(0, settings.thinking_budget - len(end_tokens) - len(suffix_tokens)),
                    suffix_tokens,
                )
            )
        eos = llm.token_eos()
        if isinstance(eos, int) and eos >= 0:
            processors.append(PromptParagraph(llm.detokenize, eos, settings.thinking))
        check_cancelled(cancelled)
        response = llm.create_chat_completion(
            messages=messages,
            temperature=0.6 if settings.thinking else 0.7,
            top_p=0.95 if settings.thinking else 0.8,
            top_k=20,
            min_p=0.0,
            repeat_penalty=1.1,
            max_tokens=settings.max_tokens,
            stream=True,
            logits_processor=processors or None,
        )
        return read_completion(response, cancelled, settings.thinking, progress)

    def create(
        self,
        text: str,
        settings: PromptSettings | None = None,
        cancelled: Event | None = None,
        progress: PromptProgress | None = None,
        *,
        history: tuple[PromptTurn, ...] = (),
        model_id: str = "anima-turbo-v1.1",
        on_ready=None,
        on_source=None,
        on_stage=None,
    ) -> str:
        return self._complete(
            prompt_messages(text, history=history, model_id=model_id),
            settings or PromptSettings(),
            cancelled or Event(),
            progress,
            on_ready,
            search_tags=not image_model(model_id).natural_prompt,
            on_source=on_source,
            on_stage=on_stage,
        )

    def refine(
        self,
        prompt: str,
        text: str,
        settings: PromptSettings | None = None,
        cancelled: Event | None = None,
        progress: PromptProgress | None = None,
        *,
        history: tuple[PromptTurn, ...] = (),
        model_id: str = "anima-turbo-v1.1",
        on_ready=None,
        on_source=None,
        on_stage=None,
    ) -> str:
        return self._complete(
            prompt_messages(text, prompt, history, model_id),
            settings or PromptSettings(),
            cancelled or Event(),
            progress,
            on_ready,
            search_tags=not image_model(model_id).natural_prompt,
            on_source=on_source,
            on_stage=on_stage,
        )

    def unload(self):
        with self._lock:
            if self._llm is None:
                return
            self._llm.close()
            self._llm = None
            self._loaded_path = None
            self._context_size = None
            self._thinking_handlers.clear()
            self._formatters.clear()
            gc.collect()
            log.info("prompt model unloaded")
