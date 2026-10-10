"""ChatGPT writes image prompts; rendering and history stay local."""

import json
import logging
from uuid import uuid4

from moru.cancellation import check_cancelled
from moru.chatgpt.diagnostics import label, output_structure, tool_result_metadata
from moru.chatgpt.http import ERROR_CODES, ChatGPTHttpError
from moru.chatgpt.instructions import TAG_GUIDANCE, prompt_messages
from moru.chatgpt.options import REASONING_EFFORTS, validate_chatgpt_options
from moru.chatgpt.stream import read_prompt_reply
from moru.chatgpt.tool_session import MAX_LOOKUP_ROUNDS, TagToolSession
from moru.chatgpt.tools import found_tag_names
from moru.errors import MoruError
from moru.models import image_model
from moru.prompts.text import final_prompt

logger = logging.getLogger(__name__)


class ChatGPTPrompts:
    def __init__(self, auth, http, *, tag_tools=None):
        self.auth, self.http = auth, http
        self.tag_tools = tag_tools

    def create(
        self,
        text,
        settings,
        cancelled,
        progress,
        *,
        history=(),
        model_id="anima-turbo-v1.1",
        on_ready=None,
        on_source=None,
        on_stage=None,
    ):
        return self._write(
            text,
            None,
            settings,
            cancelled,
            progress,
            history,
            model_id,
            on_ready,
            on_source,
            on_stage,
        )

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
        on_source=None,
        on_stage=None,
    ):
        return self._write(
            text,
            prompt,
            settings,
            cancelled,
            progress,
            history,
            model_id,
            on_ready,
            on_source,
            on_stage,
        )

    def _write(
        self,
        text,
        base,
        settings,
        cancelled,
        progress,
        history,
        model_id,
        on_ready,
        on_source,
        on_stage,
    ):
        check_cancelled(cancelled)
        if not settings.chatgpt_model:
            raise MoruError("INVALID_SETTINGS")
        validate_chatgpt_options(settings)
        instructions, messages = prompt_messages(text, base, history, model_id)
        payload = {
            "model": settings.chatgpt_model,
            "instructions": instructions,
            "input": messages,
            "store": False,
            "stream": True,
        }
        if settings.chatgpt_reasoning_effort != "default":
            payload["reasoning"] = {"effort": settings.chatgpt_reasoning_effort}
        use_tools = (
            settings.tag_search_enabled
            and self.tag_tools is not None
            and not image_model(model_id).natural_prompt
        )
        if use_tools:
            payload["tools"] = self.tag_tools.definitions()
            payload["include"] = ["reasoning.encrypted_content"]
            payload["instructions"] += TAG_GUIDANCE
        request_id = uuid4().hex
        logger.info(
            "ChatGPT prompt request=%s operation=%s model=%s reasoning=%s tools=%s input_items=%d",
            request_id,
            "refine" if base is not None else "create",
            label(settings.chatgpt_model, REASONING_EFFORTS),
            settings.chatgpt_reasoning_effort,
            use_tools,
            len(messages),
        )
        token = self.auth.access_token()
        check_cancelled(cancelled)
        if on_ready is not None:
            on_ready()
        stage = None
        found_tags = set()

        def report_stage(next_stage):
            nonlocal stage
            check_cancelled(cancelled)
            current = (next_stage, len(found_tags))
            if current != stage and on_stage is not None:
                on_stage(*current)
            stage = current
            check_cancelled(cancelled)

        def record_source(source):
            result = json.loads(source.result_json)
            found_tags.update(found_tag_names(source.tool, result))
            report_stage("searching_tags")
            if on_source is not None:
                on_source(source)

        tool_session = TagToolSession(self.tag_tools, cancelled, record_source)
        for round_number in range(MAX_LOOKUP_ROUNDS + 1):
            trace = f"{request_id}:{round_number + 1}"
            reply, token = self._request(token, payload, cancelled, progress, trace, report_stage)
            calls = [item for item in reply.output if item.get("type") == "function_call"]
            if not calls:
                try:
                    prompt = final_prompt(reply.text)
                except MoruError as exc:
                    logger.warning(
                        "ChatGPT final prompt rejected trace=%s code=%s text_chars=%d "
                        "blank=%s calls_used=%d",
                        trace,
                        exc.code,
                        len(reply.text),
                        not reply.text.strip(),
                        tool_session.calls_used,
                    )
                    raise
                logger.info(
                    "ChatGPT prompt completed trace=%s prompt_chars=%d calls_used=%d",
                    trace,
                    len(prompt),
                    tool_session.calls_used,
                )
                report_stage("prompting")
                if use_tools and payload.get("tool_choice") != "none":
                    progress("", prompt)
                check_cancelled(cancelled)
                return prompt
            if not use_tools or payload.get("tool_choice") == "none":
                raise MoruError("PROMPT_INVALID_RESPONSE")
            report_stage("searching_tags")
            results = tool_session.execute_calls(calls)
            logger.info(
                "ChatGPT tools trace=%s requested=%d calls_used=%d stopped=%s results=%s",
                trace,
                len(calls),
                tool_session.calls_used,
                tool_session.stop_reason,
                json.dumps(tool_result_metadata(calls, results), sort_keys=True),
            )
            payload = {**payload, "input": [*payload["input"], *reply.output, *results]}
            if tool_session.exhausted or round_number >= MAX_LOOKUP_ROUNDS - 1:
                payload["tool_choice"] = "none"
                payload["instructions"] += (
                    " No further lookups are available for this request. "
                    "Return the final image prompt using the information already available."
                )
        raise MoruError("PROMPT_INVALID_RESPONSE")

    def _request(self, token, payload, cancelled, progress, trace, on_stage):
        for attempt in range(2):
            try:
                attempt_trace = f"{trace}:{attempt + 1}"
                logger.info(
                    "ChatGPT request trace=%s tool_choice=%s input=%s",
                    attempt_trace,
                    label(payload.get("tool_choice"), {"none", "auto", "required"}),
                    json.dumps(output_structure(payload["input"]), sort_keys=True),
                )
                return read_prompt_reply(
                    self.http,
                    token,
                    payload,
                    cancelled,
                    progress,
                    trace=attempt_trace,
                    on_stage=on_stage,
                ), token
            except ChatGPTHttpError as exc:
                logger.warning(
                    "ChatGPT admission failed trace=%s status=%d code=%s remote_code=%s "
                    "refresh_retry=%s",
                    attempt_trace,
                    exc.status,
                    exc.code,
                    label(exc.remote_code, ERROR_CODES),
                    exc.status == 401 and attempt == 0,
                )
                # Only admission 401 is retried; tool outputs are reused unchanged.
                if exc.status != 401 or attempt:
                    raise
                check_cancelled(cancelled)
                token = self.auth.access_token(rejected_token=token)
        raise MoruError("CHATGPT_UNAVAILABLE")

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
