"""ChatGPT writes image prompts; rendering and history stay local."""

from moru.chatgpt_http import ChatGPTHttpError, response_error
from moru.chatgpt_options import validate_chatgpt_options
from moru.errors import MoruError
from moru.models import image_model
from moru.prompt_text import check_cancelled, conversation_messages, final_prompt


def chatgpt_messages(text, base_prompt=None, history=(), model_id="anima-turbo-v1.1"):
    model = image_model(model_id)
    style = (
        "Write a descriptive English image prompt in natural language for FLUX.2."
        if model.natural_prompt
        else "Write an English image-generation prompt for Anima using Danbooru tags "
        "and concise visual descriptions."
    )
    instructions = (
        style + " Return only the complete prompt in one paragraph, without explanations. "
        "Preserve the user's subjects, composition and requested style. "
        "For revisions, use the existing prompt as the current state, apply the latest "
        "change and preserve unrelated details. History only provides context."
        + model.prompt_suffix
    )
    return instructions, conversation_messages(text, base_prompt, history)


class ChatGPTPrompts:
    def __init__(self, auth, http):
        self.auth, self.http = auth, http

    def create(
        self, text, settings, cancelled, progress, *, history=(), model_id="anima-turbo-v1.1",
        on_ready=None,
    ):
        return self._write(text, None, settings, cancelled, progress, history, model_id, on_ready)

    def refine(
        self,
        prompt,
        text,
        settings,
        cancelled,
        progress,
        *,
        history=(),
        model_id="anima-turbo-v1.1",
        on_ready=None,
    ):
        return self._write(text, prompt, settings, cancelled, progress, history, model_id, on_ready)

    def _write(self, text, base, settings, cancelled, progress, history, model_id, on_ready):
        check_cancelled(cancelled)
        if not settings.chatgpt_model:
            raise MoruError("INVALID_SETTINGS")
        validate_chatgpt_options(settings)
        instructions, messages = chatgpt_messages(text, base, history, model_id)
        payload = {
            "model": settings.chatgpt_model,
            "instructions": instructions,
            "input": messages,
            "store": False,
            "stream": True,
        }
        if settings.chatgpt_reasoning_effort != "default":
            payload["reasoning"] = {"effort": settings.chatgpt_reasoning_effort}
        token = self.auth.access_token()
        check_cancelled(cancelled)
        if on_ready is not None:
            on_ready()
        for attempt in range(2):
            try:
                return self._consume(token, payload, cancelled, progress)
            except ChatGPTHttpError as exc:
                # Only admission 401 is retried; never replay a partially consumed stream.
                if exc.status != 401 or attempt:
                    raise
                check_cancelled(cancelled)
                token = self.auth.access_token(rejected_token=token)
        raise MoruError("CHATGPT_UNAVAILABLE")

    def _consume(self, token, payload, cancelled, progress):
        text = ""
        completed = False
        with self.http.stream(token, payload, cancelled) as events:
            for event in events:
                check_cancelled(cancelled)
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    delta = event.get("delta")
                    if not isinstance(delta, str):
                        raise MoruError("PROMPT_INVALID_RESPONSE")
                    text += delta
                    if len(text) > 65536:
                        raise MoruError("PROMPT_OUTPUT_TOO_LONG")
                    progress("", text)
                elif kind in ("response.refusal.delta", "response.refusal.done"):
                    raise MoruError("CHATGPT_REFUSED")
                elif kind in ("response.failed", "error"):
                    body = event.get("response", event)
                    error = response_error(0, body)
                    raise MoruError(error.code)
                elif kind == "response.incomplete":
                    raise MoruError("PROMPT_RESPONSE_INTERRUPTED")
                elif kind == "response.completed":
                    if event.get("response", {}).get("status", "completed") != "completed":
                        raise MoruError("PROMPT_RESPONSE_INTERRUPTED")
                    for item in event.get("response", {}).get("output", []):
                        if any(part.get("type") == "refusal" for part in item.get("content", [])):
                            raise MoruError("CHATGPT_REFUSED")
                    completed = True
                    break
        check_cancelled(cancelled)
        if not completed:
            raise MoruError("PROMPT_RESPONSE_INTERRUPTED")
        return final_prompt(text)

    def models(self):
        token = self.auth.access_token()
        try:
            result = self.http.json("https://api.openai.com/v1/models", token=token)
        except ChatGPTHttpError as exc:
            if exc.status != 401:
                raise
            token = self.auth.access_token(rejected_token=token)
            result = self.http.json("https://api.openai.com/v1/models", token=token)
        try:
            return [
                {"slug": item["slug"], "display_name": item["display_name"]}
                for item in result["models"]
                if item.get("visibility") == "list"
                and isinstance(item["slug"], str)
                and isinstance(item["display_name"], str)
            ]
        except (KeyError, TypeError):
            raise MoruError("CHATGPT_UNAVAILABLE") from None

    def memory_required(self, settings):
        return 0

    def unload(self):
        pass
