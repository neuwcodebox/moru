"""Local completion stopping, streamed reasoning and final answer validation."""

from contextlib import closing
from threading import Event

from moru.cancellation import check_cancelled
from moru.errors import MoruError
from moru.ports import PromptProgress
from moru.prompts.text import answer_text, final_prompt


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
            "\n" in prompt or b"\n" in self._detokenize([int(scores.argmax())], special=True)
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
                raise MoruError("PROMPT_OUTPUT_TOO_LONG")
            finished = choice.get("finish_reason") == "stop"
            content += choice["delta"].get("content") or ""
            if progress is not None:
                progress(*stream_text(content, thinking))
        check_cancelled(cancelled)
    if not finished:
        raise MoruError("PROMPT_RESPONSE_INTERRUPTED")
    return final_prompt(content)
