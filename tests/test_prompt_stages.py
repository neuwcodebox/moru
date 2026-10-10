from threading import Event

import pytest
from support.chatgpt import SETTINGS, Auth, Responses, Tools, call, completed, delta, final_turn

from moru.chatgpt.prompts import ChatGPTPrompts
from moru.errors import MoruError
from moru.prompts.providers import PromptProviders


def record_phase_changes(stages):
    def record(stage, _count):
        if not stages or stages[-1] != stage:
            stages.append(stage)

    return record


@pytest.mark.parametrize("operation", ["create", "refine"])
def test_lookup_selection_and_execution_show_searching_until_final_answer_starts(operation):
    stages, progress = [], []
    function = call()

    class CheckingTools(Tools):
        def execute(self, *args):
            assert stages[-1] == "searching_tags"
            return super().execute(*args)

    def search_turn():
        yield {"type": "response.output_item.added", "item": function}
        assert stages == ["searching_tags"]
        yield completed(function)

    def answer_turn():
        assert stages == ["searching_tags"]
        yield {"type": "response.created", "response": {"status": "in_progress"}}
        assert stages == ["searching_tags"]
        yield {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "phase": "final_answer",
                "content": [],
            },
        }
        assert stages == ["searching_tags", "prompting"]
        assert progress == []
        yield from final_turn()

    prompts = ChatGPTPrompts(
        Auth(), Responses(search_turn(), answer_turn()), tag_tools=CheckingTools()
    )
    args = ("girl", SETTINGS, Event(), lambda *p: progress.append(p))
    kwargs = {"on_stage": record_phase_changes(stages)}
    result = (
        prompts.create(*args, **kwargs)
        if operation == "create"
        else prompts.refine("original", *args, **kwargs)
    )
    assert result == "1girl, crossed_arms, grey_hair"
    assert stages == ["searching_tags", "prompting"]
    assert progress == [("", result)]


def test_intermediate_commentary_does_not_report_final_prompt_generation():
    stages = []
    commentary = {
        "type": "message",
        "phase": "commentary",
        "content": [{"type": "output_text", "text": "I will verify tags."}],
    }

    def first_turn():
        yield {"type": "response.output_item.added", "item": commentary}
        yield delta("I will verify tags.")
        yield {"type": "response.output_item.done", "item": commentary}
        assert stages == []
        yield completed(commentary, call())

    http = Responses(first_turn(), final_turn())
    ChatGPTPrompts(Auth(), http, tag_tools=Tools()).create(
        "girl", SETTINGS, Event(), lambda *_: None, on_stage=record_phase_changes(stages)
    )
    assert stages == ["searching_tags", "prompting"]
    assert http.calls[1][1]["input"][-3]["phase"] == "commentary"


def test_each_additional_lookup_keeps_search_status_and_failure_can_still_finish_prompt():
    stages = []
    http = Responses([completed(call())], [completed(call(call_id="call_2"))], final_turn())

    class SecondLookupFails(Tools):
        def execute(self, *args):
            assert stages == ["searching_tags"]
            result = super().execute(*args)
            return {"error": "lookup_unavailable"} if len(self.calls) == 2 else result

    ChatGPTPrompts(Auth(), http, tag_tools=SecondLookupFails()).create(
        "girl", SETTINGS, Event(), lambda *_: None, on_stage=record_phase_changes(stages)
    )
    assert stages == ["searching_tags", "prompting"]
    assert http.calls[-1][1]["tool_choice"] == "none"


def test_job_state_and_bridge_follow_actual_lookup_and_answer_events(app):
    from moru.api import Api

    states = []
    api = Api(app)

    def state():
        return api.get_job(job.id)["value"]["state"]

    def search_turn():
        states.append(state())
        yield {"type": "response.output_item.added", "item": call()}
        states.append(state())
        yield completed(call())

    class CheckingTools(Tools):
        def execute(self, *args):
            states.append(state())
            return super().execute(*args)

    def answer_turn():
        states.append(state())
        yield {"type": "response.output_item.added", "item": {"type": "message"}}
        states.append(state())
        yield from final_turn()

    cloud = ChatGPTPrompts(
        Auth(), Responses(search_turn(), answer_turn()), tag_tools=CheckingTools()
    )
    app.prompts = PromptProviders(app.prompts, cloud)
    app.update_settings(app.get_settings(), SETTINGS)
    job = app.submit_request(app.create_project().id, "girl")
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    assert states == ["thinking", "searching_tags", "searching_tags", "searching_tags", "prompting"]


def test_requests_without_lookups_report_writing_when_text_starts():
    stages = []
    ChatGPTPrompts(Auth(), Responses(final_turn())).create(
        "girl",
        SETTINGS,
        Event(),
        lambda *_: None,
        on_stage=record_phase_changes(stages),
        model_id="flux2-klein-4b",
    )
    assert stages == ["prompting"]


def test_cancelling_during_search_selection_does_not_lookup_or_report_final_writing():
    cancelled, tools, stages = Event(), Tools(), []

    def stage(value, _count):
        stages.append(value)
        cancelled.set()

    with pytest.raises(MoruError) as error:
        ChatGPTPrompts(
            Auth(),
            Responses(
                [
                    {"type": "response.output_item.added", "item": call()},
                    completed(call()),
                ]
            ),
            tag_tools=tools,
        ).create("girl", SETTINGS, cancelled, lambda *_: None, on_stage=stage)
    assert error.value.code == "GENERATION_CANCELLED"
    assert stages == ["searching_tags"] and tools.calls == []


@pytest.mark.parametrize("operation", ["create", "refine"])
def test_search_progress_counts_distinct_returned_names_after_each_lookup(operation):
    progress = []

    class CatalogTools(Tools):
        def __init__(self):
            super().__init__()
            self.results = iter(
                [
                    ["grey_hair", "long_hair", "grey_hair"],
                    {"name": "grey_hair", "description": "A description."},
                    {
                        "cooccurring": ["long_hair", "white_hair"],
                        "wiki_links": ["white_hair", "silver_hair"],
                    },
                ]
            )

        def execute(self, *args):
            return next(self.results)

    http = Responses(
        [
            completed(
                call(),
                call("get_tag_info", {"name": "gray_hair"}, call_id="call_2"),
                call("get_related_tags", {"name": "grey_hair", "limit": 20}, call_id="call_3"),
            )
        ],
        final_turn(),
    )
    writer = ChatGPTPrompts(Auth(), http, tag_tools=CatalogTools())
    args = ("girl", SETTINGS, Event(), lambda *_: None)
    kwargs = {"on_stage": lambda stage, count: progress.append((stage, count))}
    if operation == "create":
        writer.create(*args, **kwargs)
    else:
        writer.refine("original", *args, **kwargs)
    assert progress == [
        ("searching_tags", 0),
        ("searching_tags", 2),
        ("searching_tags", 4),
        ("prompting", 4),
    ]


@pytest.mark.parametrize(
    "name,result",
    [
        ("search_tags", []),
        ("get_tag_info", {"name": None, "description": "Wiki mentions [[some_tag]]."}),
        ("search_tags", {"error": "lookup_unavailable"}),
    ],
)
def test_empty_or_failed_results_do_not_count_query_names_or_wiki_mentions(name, result):
    progress = []
    arguments = {"query": "missing"} if name == "search_tags" else {"name": "missing"}
    http = Responses([completed(call(name, arguments))], final_turn())
    ChatGPTPrompts(Auth(), http, tag_tools=Tools(result)).create(
        "girl",
        SETTINGS,
        Event(),
        lambda *_: None,
        on_stage=lambda stage, count: progress.append((stage, count)),
    )
    assert progress == [("searching_tags", 0), ("prompting", 0)]


def test_bridge_updates_tag_count_while_searching_and_starts_each_job_at_zero(app):
    from moru.api import Api

    api = Api(app)
    during_search, before_search = [], []

    def tool_turn():
        before_search.append(api.get_job(job.id)["value"]["found_tag_count"])
        yield completed(call())

    def answer_turn():
        during_search.append(api.get_job(job.id)["value"])
        yield from final_turn()

    cloud = ChatGPTPrompts(
        Auth(),
        Responses(
            tool_turn(),
            answer_turn(),
            tool_turn(),
            answer_turn(),
        ),
        tag_tools=Tools(["grey_hair", "long_hair"]),
    )
    app.prompts = PromptProviders(app.prompts, cloud)
    app.update_settings(app.get_settings(), SETTINGS)
    project = app.create_project()
    for _ in range(2):
        job = app.submit_request(project.id, "girl")
        app.scheduler.run_next()
        assert app.get_job(job.id).state == "completed"
    assert before_search == [0, 0]
    assert [snapshot["state"] for snapshot in during_search] == ["searching_tags"] * 2
    assert [snapshot["found_tag_count"] for snapshot in during_search] == [2, 2]
