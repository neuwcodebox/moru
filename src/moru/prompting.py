"""Local CUDA prompt writing with canonical state and bounded conversational context."""

import ctypes
import gc
import importlib.util
import logging
import os
import sys
import unicodedata
from contextlib import closing
from pathlib import Path
from threading import Event, RLock

from moru.config import ModelPaths
from moru.domain import PromptSettings, PromptTurn
from moru.errors import MoruError
from moru.ports import PromptProgress

log = logging.getLogger(__name__)
CREATE_SYSTEM = (
    "Convert the user's visual request into one complete English positive image prompt. "
    "Include only requested subjects; never add people to an animal-only scene. "
    "Output only one paragraph of prompt text, without explanations, markdown, quotes, "
    "command flags or negative prompts. "
    "The existing prompt is the current visual state. The latest request takes priority; "
    "use history only to resolve references. Preserve requested details and each subject's "
    "appearance, actions and position. Do not invent unrelated subjects or styles. "
    "Combine short visual sentences with relevant comma-separated booru tags. "
    "Use lowercase tags with spaces, except score_* tags. "
    "Use human-count tags only for requested people; prefix requested artist tags with @. "
    "Add rating tags only when requested. Do not include field labels or metadata. "
    "Never repeat tags or stack quality tags."
)
REFINE_SYSTEM = (
    CREATE_SYSTEM + " Revise the provided existing image prompt according to the user's "
    "change request. Preserve all details not affected by the requested change. Return the "
    "entire revised prompt, never a patch or a list of changes."
)
PROMPT_PREFIX = "Final image prompt:"


def prompt_messages(
    text: str,
    base_prompt: str | None = None,
    history: tuple[PromptTurn, ...] = (),
    model_id: str = "anima-turbo-v1.1",
) -> list[dict[str, str]]:
    system = CREATE_SYSTEM if base_prompt is None else REFINE_SYSTEM
    if "aesthetic" in model_id:
        system += " Omit score_* tags. Quality tags are optional."
    messages = [{"role": "system", "content": system}]
    for turn in history:
        messages.extend(
            [{"role": "user", "content": turn.text}, {"role": "assistant", "content": turn.prompt}]
        )
    content = (
        text
        if base_prompt is None
        else (f"Existing image prompt:\n{base_prompt}\n\nChange request:\n{text}")
    )
    messages.append({"role": "user", "content": content})
    return messages


def fit_messages(messages, count_tokens, input_limit):
    messages = list(messages)
    while count_tokens(messages) > input_limit:
        if len(messages) <= 2:
            raise MoruError("PROMPT_CONTEXT_TOO_LONG")
        del messages[1:3]  # Drop complete oldest turns; never truncate canonical state.
    return messages


def final_prompt(content: str) -> str:
    # Templates may prefill the opening tag outside the generated content.
    prompt = answer_text(content.rsplit("</think>", 1)[-1]).partition("\n")[0]
    if not prompt or "<think>" in prompt or prompt.startswith("Thinking Process:"):
        raise MoruError("PROMPT_LLM_FAILED")
    if any(char.isalpha() and "LATIN" not in unicodedata.name(char, "") for char in prompt):
        raise MoruError("PROMPT_LLM_FAILED")
    return prompt


def answer_text(content: str) -> str:
    content = content.strip()
    if PROMPT_PREFIX.startswith(content):
        return ""
    return content.removeprefix(PROMPT_PREFIX).strip()


def check_cancelled(cancelled: Event):
    if cancelled.is_set():
        raise MoruError("GENERATION_CANCELLED")


class ThinkingBudget:
    """End reasoning at its token allowance without truncating the final prompt."""

    def __init__(self, end_tokens: list[int], budget: int, suffix_tokens: list[int] | None = None):
        if not end_tokens:
            raise MoruError("THINKING_UNSUPPORTED")
        self._end_tokens = end_tokens
        self._closing_tokens = end_tokens + (suffix_tokens or [])
        self._budget = budget
        self._input_length: int | None = None
        self._forcing = False

    def __call__(self, input_ids, scores):
        if self._input_length is None:
            self._input_length = len(input_ids)
        generated = list(input_ids[self._input_length :])
        end_length = len(self._end_tokens)
        if not self._forcing and any(
            generated[index : index + end_length] == self._end_tokens
            for index in range(len(generated) - end_length + 1)
        ):
            return scores
        forced_index = len(generated) - self._budget
        if 0 <= forced_index < len(self._closing_tokens):
            self._forcing = True
            scores[:] = float("-inf")
            scores[self._closing_tokens[forced_index]] = 0.0
        return scores


class PromptParagraph:
    """Finish at the answer's paragraph boundary before the model resumes explaining."""

    def __init__(self, detokenize, eos: int, thinking: bool):
        self._detokenize = detokenize
        self._eos = eos
        self._thinking = thinking
        self._input_length: int | None = None

    def __call__(self, input_ids, scores):
        if self._input_length is None:
            self._input_length = len(input_ids)
        generated = list(input_ids[self._input_length :])
        content = self._detokenize(generated, special=True).decode("utf-8", errors="ignore")
        _, marker, answer = content.partition("</think>")
        prompt = answer_text(answer if marker else content) if marker or not self._thinking else ""
        if prompt and (
            "\n" in prompt
            or b"\n" in self._detokenize([int(scores.argmax())], special=True)
        ):
            scores[:] = float("-inf")
            scores[self._eos] = 0.0
        return scores


def stream_text(content: str, thinking: bool) -> tuple[str, str]:
    reasoning, marker, prompt = content.partition("</think>")
    if marker:
        return (
            reasoning.removeprefix("<think>").strip(),
            answer_text(prompt).partition("\n")[0],
        )
    # Keep incomplete control tags out of the live text when a tag spans tokens.
    for tag in ("<think>", "</think>"):
        for length in range(1, len(tag)):
            if content.endswith(tag[:length]):
                content = content[:-length]
                break
    if thinking or content.startswith("<think>"):
        return content.removeprefix("<think>").strip(), ""
    return "", answer_text(content).partition("\n")[0]


def read_completion(
    chunks, cancelled: Event, thinking=False, progress: PromptProgress | None = None
) -> str:
    content = ""
    finished = False
    with closing(chunks):
        for chunk in chunks:
            check_cancelled(cancelled)
            choice = chunk["choices"][0]
            if choice.get("finish_reason") == "length":
                raise MoruError("PROMPT_LLM_FAILED")
            finished = choice.get("finish_reason") == "stop"
            content += choice["delta"].get("content") or ""
            if progress is not None:
                progress(*stream_text(content, thinking))
        check_cancelled(cancelled)
    if not finished:
        raise MoruError("PROMPT_LLM_FAILED")
    return final_prompt(content)


class LlamaPrompts:
    def __init__(self, paths: ModelPaths, *, load_llama=None):
        self._paths = paths
        self._load_llama = load_llama
        self._llm = None
        self._loaded_path = None
        self._context_size = None
        self._thinking_handlers = {}
        self._formatters = {}
        self._lock = RLock()
        self._dll_directories = []
        self._cuda_libraries = []

    def _load(self, settings: PromptSettings):
        path = self._paths.get("prompt")
        if not path.is_file():
            raise MoruError("PROMPT_MODEL_NOT_FOUND")
        if (
            self._llm is not None
            and path == self._loaded_path
            and settings.context_size == self._context_size
        ):
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
        self, messages, settings: PromptSettings, cancelled: Event, progress: PromptProgress | None
    ) -> str:
        with self._lock:
            check_cancelled(cancelled)
            llm = self._load(settings)
            try:
                check_cancelled(cancelled)
                self._configure_thinking(llm, settings.thinking)
                formatter = self._formatters.get(settings.thinking)

                def count_tokens(items):
                    if formatter is not None:
                        rendered = formatter(messages=items)
                        return len(
                            llm.tokenize(
                                rendered.prompt.encode(),
                                add_bos=not rendered.added_special,
                                special=True,
                            )
                        )
                    # Unsupported templates with thinking enabled use llama.cpp's handler.
                    return sum(len(llm.tokenize(item["content"].encode())) + 16 for item in items)

                messages = fit_messages(
                    messages, count_tokens, settings.context_size - settings.max_tokens
                )
                processors = None
                if settings.thinking:
                    end_tokens = llm.tokenize(b"</think>", add_bos=False, special=True)
                    # A final-answer cue prevents continuation of an interrupted analysis sentence.
                    suffix_tokens = llm.tokenize(
                        f"\n\n{PROMPT_PREFIX}\n".encode(), add_bos=False
                    )
                    processors = [
                        ThinkingBudget(
                            end_tokens,
                            max(0, settings.thinking_budget - len(end_tokens) - len(suffix_tokens)),
                            suffix_tokens,
                        )
                    ]
                eos = llm.token_eos()
                if isinstance(eos, int) and eos >= 0:
                    processors = (processors or []) + [
                        PromptParagraph(llm.detokenize, eos, settings.thinking)
                    ]
                response = llm.create_chat_completion(
                    messages=messages,
                    temperature=0.6 if settings.thinking else 0.7,
                    top_p=0.95 if settings.thinking else 0.8,
                    top_k=20,
                    min_p=0.0,
                    repeat_penalty=1.1,
                    max_tokens=settings.max_tokens,
                    stream=True,
                    logits_processor=processors,
                )
                return read_completion(response, cancelled, settings.thinking, progress)
            except MoruError:
                raise
            except Exception as exc:
                raise MoruError("PROMPT_LLM_FAILED") from exc

    def create(
        self,
        text: str,
        settings: PromptSettings | None = None,
        cancelled: Event | None = None,
        progress: PromptProgress | None = None,
        *,
        history: tuple[PromptTurn, ...] = (),
        model_id: str = "anima-turbo-v1.1",
    ) -> str:
        return self._complete(
            prompt_messages(text, history=history, model_id=model_id),
            settings or PromptSettings(),
            cancelled or Event(),
            progress,
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
    ) -> str:
        return self._complete(
            prompt_messages(text, prompt, history, model_id),
            settings or PromptSettings(),
            cancelled or Event(),
            progress,
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
