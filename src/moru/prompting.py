"""Local CUDA prompt writing with only the canonical image prompt as context."""

import ctypes
import gc
import importlib.util
import logging
import os
import sys
from contextlib import closing
from pathlib import Path
from threading import Event, RLock

from moru.config import ModelPaths
from moru.domain import PromptSettings
from moru.errors import MoruError

log = logging.getLogger(__name__)
CREATE_SYSTEM = (
    "You write prompts for Anima, an anime text-to-image model. Convert the user's request "
    "into one complete English image prompt. Describe subjects, appearance, clothing, pose, "
    "expression, setting, lighting and composition as requested. Preserve specific details. "
    "Use clear visual descriptions and helpful comma-separated tags. Return only the finished "
    "prompt, without explanations, markdown, quotes, reasoning or tool calls."
)
REFINE_SYSTEM = (
    CREATE_SYSTEM + " Revise the provided existing image prompt according to the user's "
    "change request. Preserve all details not affected by the requested change. Return the "
    "entire revised prompt, never a patch or a list of changes."
)


def prompt_messages(text: str, base_prompt: str | None = None) -> list[dict[str, str]]:
    if base_prompt is None:
        return [{"role": "system", "content": CREATE_SYSTEM}, {"role": "user", "content": text}]
    return [
        {"role": "system", "content": REFINE_SYSTEM},
        {
            "role": "user",
            "content": f"Existing image prompt:\n{base_prompt}\n\nChange request:\n{text}",
        },
    ]


def final_prompt(content: str) -> str:
    # Templates may prefill the opening tag outside the generated content.
    prompt = content.rsplit("</think>", 1)[-1].strip()
    if not prompt or "<think>" in prompt or prompt.startswith("Thinking Process:"):
        raise MoruError("PROMPT_LLM_FAILED")
    return prompt


def check_cancelled(cancelled: Event):
    if cancelled.is_set():
        raise MoruError("GENERATION_CANCELLED")


def read_completion(chunks, cancelled: Event) -> str:
    content = []
    finished = False
    with closing(chunks):
        for chunk in chunks:
            check_cancelled(cancelled)
            choice = chunk["choices"][0]
            if choice.get("finish_reason") == "length":
                raise MoruError("PROMPT_LLM_FAILED")
            finished = choice.get("finish_reason") == "stop"
            content.append(choice["delta"].get("content") or "")
        check_cancelled(cancelled)
    if not finished:
        raise MoruError("PROMPT_LLM_FAILED")
    return final_prompt("".join(content))


class LlamaPrompts:
    def __init__(self, paths: ModelPaths, *, load_llama=None):
        self._paths = paths
        self._load_llama = load_llama
        self._llm = None
        self._loaded_path = None
        self._context_size = None
        self._thinking_handlers = {}
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
        llm.chat_handler = self._thinking_handlers[enabled]

    def _complete(self, messages, settings: PromptSettings, cancelled: Event) -> str:
        with self._lock:
            check_cancelled(cancelled)
            llm = self._load(settings)
            try:
                check_cancelled(cancelled)
                self._configure_thinking(llm, settings.thinking)
                response = llm.create_chat_completion(
                    messages=messages,
                    temperature=0.6,
                    top_p=0.95,
                    top_k=20,
                    min_p=0.0,
                    max_tokens=settings.max_tokens,
                    stream=True,
                )
                return read_completion(response, cancelled)
            except MoruError:
                raise
            except Exception as exc:
                raise MoruError("PROMPT_LLM_FAILED") from exc

    def create(
        self, text: str, settings: PromptSettings | None = None, cancelled: Event | None = None
    ) -> str:
        return self._complete(
            prompt_messages(text), settings or PromptSettings(), cancelled or Event()
        )

    def refine(
        self,
        prompt: str,
        text: str,
        settings: PromptSettings | None = None,
        cancelled: Event | None = None,
    ) -> str:
        return self._complete(
            prompt_messages(text, prompt), settings or PromptSettings(), cancelled or Event()
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
            gc.collect()
            log.info("prompt model unloaded")
