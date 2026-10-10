from unittest.mock import Mock

import pytest
from test_conversation import generate

from moru.api import Api
from moru.config import ModelPaths
from moru.domain import GenerationSettings, PromptSettings
from moru.downloads import ModelDownloads
from moru.prompt_providers import PromptProviders
from moru.prompting import LlamaPrompts


@pytest.mark.parametrize("reload_reason", ["first_request", "chatgpt_switch", "context_change"])
def test_prompt_loading_is_reported_until_inference_and_resident_models_skip_it(
    app, tmp_path, reload_reason
):
    from conftest import FakePrompts
    from test_prompting import completion

    paths = ModelPaths(tmp_path)
    paths.get("prompt").parent.mkdir(parents=True, exist_ok=True)
    paths.get("prompt").write_bytes(b"fake gguf")
    api = Api(app)
    loading, inference = [], []
    llm = Mock(metadata={}, tokenize=lambda *args, **kwargs: [0], token_eos=lambda: -1)

    def load(**kwargs):
        loading.append(api.get_job(job.id)["value"]["state"])
        return llm

    def infer(**kwargs):
        inference.append(api.get_job(job.id)["value"]["state"])
        return completion("night, girl")

    llm.create_chat_completion.side_effect = infer
    app.prompts = PromptProviders(LlamaPrompts(paths, load_llama=load), FakePrompts())
    project = app.create_project()
    if reload_reason != "first_request":
        job = app.submit_request(project.id, "girl")
        app.scheduler.run_next()
        if reload_reason == "chatgpt_switch":
            app.update_settings(
                app.get_settings(), PromptSettings(provider="chatgpt", chatgpt_model="gpt")
            )
            job = app.submit_request(project.id, "daytime")
            app.scheduler.run_next()
            app.update_settings(app.get_settings(), PromptSettings())
        else:
            app.update_settings(app.get_settings(), PromptSettings(context_size=8192))
        loading.clear()
        inference.clear()

    job = app.submit_request(project.id, "night")
    app.scheduler.run_next()
    assert loading == ["loading_prompt_model"]
    assert inference == ["prompting"]
    assert app.get_job(job.id).state == "completed"

    loading.clear()
    inference.clear()
    job = app.submit_request(project.id, "rain")
    app.scheduler.run_next()
    assert loading == []
    assert inference == ["prompting"]
    assert app.get_job(job.id).state == "completed"


@pytest.mark.parametrize(
    "model_id, page_url, filename",
    [
        (
            "prompt",
            "https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/"
            "blob/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e/"
            "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf",
            "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf",
        ),
        *[
            (
                model_id,
                "https://huggingface.co/circlestone-labs/Anima/"
                f"blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/{relative_path}",
                filename,
            )
            for model_id, relative_path, filename in [
                (
                    "anima-turbo-v1.1",
                    "diffusion_models/anima-turbo-v1.1.safetensors",
                    "anima-turbo-v1.1.safetensors",
                ),
                (
                    "anima-aesthetic-v1.1",
                    "diffusion_models/anima-aesthetic-v1.1.safetensors",
                    "anima-aesthetic-v1.1.safetensors",
                ),
                (
                    "text_encoder",
                    "text_encoders/qwen_3_06b_base.safetensors",
                    "qwen_3_06b_base.safetensors",
                ),
                ("vae", "vae/qwen_image_vae.safetensors", "qwen_image_vae.safetensors"),
            ]
        ],
    ],
)
def test_model_setup_provides_exact_file_pages_and_names_without_network_access(
    app, tmp_path, model_id, page_url, filename
):
    downloads = ModelDownloads(ModelPaths(tmp_path), executor=app.scheduler)
    api = Api(app, downloads=downloads)

    for models in (api.bootstrap()["value"]["models"], api.get_model_status()["value"]):
        model = next(item for item in models if item["id"] == model_id)
        assert model["manual_download"] == {"url": page_url, "filename": filename}
        assert model["filename"] is None


def test_main_conversation_view_hides_prompt_and_generation_metadata(app):
    api = Api(app)
    project = app.create_project()
    image = generate(app, project.id)
    view = api.get_project(project.id)["value"]["images"][0]
    assert view["request_text"] == "소녀를 그려줘"
    assert (view["width"], view["height"]) == (image.settings.width, image.settings.height)
    assert "prompt" not in view
    assert "settings" not in view
    assert "image_path" not in view
    details = api.get_image_details(image.id)["value"]
    assert details["prompt"] == image.prompt
    assert details["settings"]["seed"] == "42"


def test_live_prompt_is_available_but_reasoning_never_crosses_the_ui_bridge(app):
    api = Api(app)
    snapshots = []
    project = app.create_project()
    app.update_settings(app.get_settings(), PromptSettings(thinking=True))

    def create(text, settings, cancelled, progress, **context):
        progress("choosing a scene", "")
        snapshots.append(api.get_job(job.id)["value"])
        progress("choosing a scene", "night, girl")
        snapshots.append(api.get_job(job.id)["value"])
        return "night, girl"

    app.prompts.create = create
    job = app.submit_request(project.id, "girl")
    app.scheduler.run_next()
    assert "thinking_text" not in snapshots[0]
    assert snapshots[0]["prompt_text"] == ""
    assert snapshots[0]["thinking_enabled"] is True
    assert snapshots[1]["prompt_text"] == "night, girl"
    assert "thinking_text" not in snapshots[1]
    completed = api.get_job(job.id)["value"]
    assert "thinking_text" not in completed
    assert completed["prompt_text"] == ""
    assert api.get_image_details(completed["image_id"])["value"]["prompt"] == "night, girl"


def test_generation_job_keeps_the_requested_image_size_when_settings_change(app):
    api = Api(app)
    project = app.create_project()
    app.update_settings(GenerationSettings(width=832, height=1216))
    job = api.submit_request(project.id, "portrait")["value"]
    assert (job["width"], job["height"]) == (832, 1216)
    app.update_settings(GenerationSettings(width=1216, height=832))
    app.scheduler.run_next()
    completed = api.get_job(job["id"])["value"]
    assert (completed["width"], completed["height"]) == (832, 1216)


@pytest.mark.parametrize("failure_stage", ["prompt", "image"])
def test_failed_placeholder_keeps_original_request_dimensions(app, failure_stage):
    from moru.errors import MoruError

    api = Api(app)
    project = app.create_project()
    app.update_settings(GenerationSettings(width=832, height=1216))
    if failure_stage == "prompt":
        def fail_prompt(*args, **kwargs):
            raise MoruError("PROMPT_LLM_FAILED")

        app.prompts.create = fail_prompt
    else:
        app.images.failures = ["GENERATION_FAILED"]
    job = app.submit_request(project.id, "portrait")
    app.scheduler.run_next()
    app.update_settings(GenerationSettings(width=1216, height=832))

    request = api.get_project(project.id)["value"]["unfinished_requests"][0]
    assert request["id"] == job.request_id
    assert request["status"] == "failed"
    assert (request["width"], request["height"]) == (832, 1216)


@pytest.mark.parametrize("code", [
    "PROMPT_EMPTY_RESPONSE",
    "PROMPT_INVALID_RESPONSE",
    "PROMPT_NON_ENGLISH_RESPONSE",
    "PROMPT_OUTPUT_TOO_LONG",
    "PROMPT_RESPONSE_INTERRUPTED",
])
def test_prompt_failure_cause_is_preserved_and_the_same_request_can_be_retried(app, code):
    from moru.errors import MESSAGES, MoruError

    api = Api(app)
    project = app.create_project()
    original_create = app.prompts.create

    def fail_prompt(text, settings, cancelled, progress, **context):
        progress("private reasoning", "partial prompt")
        raise MoruError(code)

    app.prompts.create = fail_prompt
    job = app.submit_request(project.id, "portrait")
    app.scheduler.run_next()

    failed = api.get_job(job.id)["value"]
    assert failed["error_code"] == code
    assert failed["message"] == MESSAGES[code]
    assert failed["prompt_text"] == ""
    request = api.get_project(project.id)["value"]["unfinished_requests"][0]
    assert request["error_code"] == code
    assert request["message"] == MESSAGES[code]
    assert app.images.inputs == []

    app.prompts.create = original_create
    retry = app.retry_request(job.request_id)
    app.scheduler.run_next()
    assert retry.request_id == job.request_id
    assert api.get_job(retry.id)["value"]["state"] == "completed"
    assert api.get_project(project.id)["value"]["unfinished_requests"] == []


@pytest.mark.parametrize("response", [None, "", "   "])
def test_missing_prompt_from_the_engine_reports_an_empty_response(app, response):
    api = Api(app)
    project = app.create_project()
    app.prompts.create = lambda *args, **kwargs: response

    job = app.submit_request(project.id, "portrait")
    app.scheduler.run_next()

    assert api.get_job(job.id)["value"]["error_code"] == "PROMPT_EMPTY_RESPONSE"
    assert app.images.inputs == []


def test_manual_prompt_stays_in_details_instead_of_appearing_as_user_chat(app):
    api = Api(app)
    project = app.create_project()
    image = generate(app, project.id)
    app.generate_from_prompt(image.id, "private manual prompt")
    app.scheduler.run_next()
    view = api.get_project(project.id)["value"]
    assert len(view["images"]) == 1
    assert view["images"][0]["request_text"] == "소녀를 그려줘"
    assert len(view["images"][0]["versions"]) == 2
    assert "private manual prompt" not in str(view)


def test_bridge_preserves_large_seeds_without_javascript_precision_loss(app):
    api = Api(app)
    seed = str(2**63 - 1)
    result = api.update_settings({"seed": seed})
    assert result["ok"]
    assert result["value"]["seed"] == seed
    assert app.get_settings().seed == 2**63 - 1


def test_invalid_bridge_settings_have_stable_korean_error(app):
    api = Api(app)
    result = api.update_settings({"unknown": 1})
    assert result == {
        "ok": False,
        "error": {
            "code": "INVALID_SETTINGS",
            "message": "생성 설정을 확인해 주세요.",
        },
    }


def test_bootstrap_exposes_prompt_defaults_and_restores_saved_values(app):
    api = Api(app)
    assert api.bootstrap()["value"]["prompt_settings"] == {
        "context_size": 4096,
        "max_tokens": 2048,
        "thinking": True,
        "history_turns": 4,
        "reasoning_level": "medium",
        "provider": "local",
        "chatgpt_model": "",
    }
    values = {
        "context_size": 8192, "max_tokens": 4096, "thinking": False,
        "history_turns": 2, "reasoning_level": "high",
        "provider": "local", "chatgpt_model": "",
    }
    assert api.update_settings({"steps": 12}, values)["ok"]
    assert api.get_prompt_settings()["value"] == values
    assert api.bootstrap()["value"]["prompt_settings"] == values


def test_model_defaults_exposed_to_the_ui_match_partial_settings_and_actual_generation(app):
    api = Api(app)
    defaults = api.bootstrap()["value"]["generation_defaults"]["anima-aesthetic-v1.1"]
    saved = api.update_settings({"model_id": "anima-aesthetic-v1.1"})["value"]
    assert saved["steps"] == defaults["steps"] == 40
    assert saved["cfg"] == defaults["cfg"] == 4.5
    project = app.create_project()
    image = generate(app, project.id)
    assert image.settings.steps == 40
    assert image.settings.cfg == 4.5


@pytest.mark.parametrize(
    "values",
    [
        {"max_tokens": 8192},
        {"thinking": "false"},
        {"unknown": 1},
        [],
    ],
)
def test_invalid_prompt_settings_do_not_partially_save_image_settings(app, values):
    result = Api(app).update_settings({"steps": 12}, values)
    assert result["error"]["code"] == "INVALID_SETTINGS"
    assert app.get_settings() == GenerationSettings()
    assert app.get_prompt_settings() == PromptSettings()


def test_model_catalog_describes_alternative_variants_and_their_shared_assets(app):
    catalog = {model["id"]: model for model in Api(app).bootstrap()["value"]["image_models"]}
    turbo, aesthetic = catalog["anima-turbo-v1.1"], catalog["anima-aesthetic-v1.1"]
    assert turbo["family"] == aesthetic["family"] == "anima"
    assert (turbo["variant_name"], aesthetic["variant_name"]) == ("Turbo", "Aesthetic")
    assert turbo["asset_ids"] == ["anima-turbo-v1.1", "text_encoder", "vae"]
    assert aesthetic["asset_ids"] == ["anima-aesthetic-v1.1", "text_encoder", "vae"]
    assert turbo["defaults"] == {"steps": 10, "cfg": 1.0}
    assert aesthetic["defaults"] == {"steps": 40, "cfg": 4.5}


def test_retired_sdxl_is_absent_from_selection_and_downloads(app, tmp_path):
    downloads = ModelDownloads(ModelPaths(tmp_path), executor=app.scheduler)
    api = Api(app, downloads=downloads)
    result = api.bootstrap()["value"]
    assert {model["id"] for model in result["image_models"]} == {
        "anima-turbo-v1.1", "anima-aesthetic-v1.1", "flux2-klein-4b",
    }
    assert all(model["id"] != "sdxl-base-1.0" for model in result["models"])
    assert api.update_settings({"model_id": "sdxl-base-1.0"})["error"]["code"] == "INVALID_SETTINGS"
    assert api.download_model("sdxl-base-1.0")["error"]["code"] == "INVALID_SETTINGS"


def test_old_sdxl_images_remain_readable_and_keep_their_original_settings(app):
    from dataclasses import replace

    project = app.create_project()
    original = generate(app, project.id)
    settings = GenerationSettings(model_id="sdxl-base-1.0", seed=42, allow_retired=True)
    archived = replace(
        original, id="archived", request_id="archived-request", parent_image_id=original.id,
        settings=settings, generation_method="manual",
    )
    from moru.domain import Request

    app.repository.add_request(Request(
        "archived-request", project.id, "a cat", original.created_at, original.id,
        "manual", settings,
    ))
    app.repository.complete_generation(archived)
    api = Api(app)
    details = api.get_image_details("archived")["value"]
    assert details["model_name"] == "SDXL Base 1.0"
    assert details["settings"]["model_id"] == "sdxl-base-1.0"
    assert details["settings"]["steps"] == 30
    assert details["settings"]["cfg"] == 7
    assert api.get_project(project.id)["ok"]
    assert api.fork(project.id, "archived")["ok"]
    regenerated = api.regenerate("archived")
    assert regenerated["ok"]
    app.scheduler.run_next()
    assert app.images.inputs[-1][1].model_id == "anima-turbo-v1.1"
    assert api.get_image_details("archived")["value"] == details


def test_retired_model_settings_cannot_be_saved_or_retried(app):
    from moru.domain import Request
    from moru.errors import MoruError

    project = app.create_project()
    settings = GenerationSettings(model_id="sdxl-base-1.0", allow_retired=True)
    with pytest.raises(MoruError) as error:
        app.update_settings(settings)
    assert error.value.code == "INVALID_SETTINGS"
    request = Request("old", project.id, "a cat", project.created_at, None, "create", settings)
    app.repository.add_request(request)
    app.repository.set_request_status(request.id, "failed", "GENERATION_FAILED")
    result = Api(app).retry_request(request.id)
    assert result["error"]["code"] == "INVALID_SETTINGS"
    assert app.repository.get_request(request.id).status == "failed"

def test_image_details_keep_the_model_name_from_the_record_after_switching_models(app):
    project = app.create_project()
    image = generate(app, project.id)
    app.update_settings(GenerationSettings(model_id="anima-aesthetic-v1.1"))
    details = Api(app).get_image_details(image.id)["value"]
    assert details["model_name"] == "Anima Turbo"
    assert details["settings"]["model_id"] == "anima-turbo-v1.1"


def test_images_are_supplied_without_exposing_local_paths_or_running_a_server(app):
    project = app.create_project()
    image = generate(app, project.id)
    source = Api(app).get_image_source(image.id)
    assert source["ok"]
    assert source["value"].startswith("data:image/png;base64,")


def test_failed_requests_from_another_branch_are_not_shown_in_selected_conversation(app):
    project = app.create_project()
    root = generate(app, project.id)
    app.images.failures = ["GENERATION_FAILED"]
    job = app.submit_request(project.id, "실패한 밤 장면")
    app.scheduler.run_next()
    assert (
        Api(app).get_project(project.id)["value"]["unfinished_requests"][0]["id"] == job.request_id
    )
    latest = generate(app, project.id, "성공한 낮 장면")
    assert latest.parent_image_id == root.id
    assert Api(app).get_project(project.id)["value"]["unfinished_requests"] == []
    assert app.repository.get_request(job.request_id).status == "failed"


def test_prompt_copy_uses_native_clipboard_without_changing_image_history(app):
    copied = []
    api = Api(app, copy_to_clipboard=copied.append)
    result = api.copy_prompt("은발 소녀, 밤, rain")
    assert result["ok"]
    assert copied == ["은발 소녀, 밤, rain"]


def test_image_copy_writes_the_original_png_without_changing_history(app):
    project = app.create_project()
    image = generate(app, project.id)
    before = app.repository.conversation(project.id)
    copied = []
    api = Api(app, copy_image_to_clipboard=copied.append)
    assert api.copy_image(image.id)["ok"]
    assert copied == [(app.data_dir / image.image_path).read_bytes()]
    assert copied[0].startswith(b"\x89PNG")
    assert app.repository.conversation(project.id) == before


def test_image_clipboard_failure_is_explicit_and_missing_images_are_not_copied(app):
    from unittest.mock import Mock

    project = app.create_project()
    image = generate(app, project.id)
    writer = Mock(side_effect=RuntimeError("private clipboard detail"))
    api = Api(app, copy_image_to_clipboard=writer)
    result = api.copy_image(image.id)
    assert result["error"]["code"] == "CLIPBOARD_FAILED"
    assert "private" not in result["error"]["message"]
    writer.reset_mock()
    assert api.copy_image("missing")["error"]["code"] == "NOT_FOUND"
    writer.assert_not_called()
    assert Api(app).copy_image(image.id)["error"]["code"] == "CLIPBOARD_FAILED"


def test_a_missing_png_is_reported_before_writing_the_clipboard(app):
    from unittest.mock import Mock

    project = app.create_project()
    image = generate(app, project.id)
    (app.data_dir / image.image_path).unlink()
    writer = Mock()
    result = Api(app, copy_image_to_clipboard=writer).copy_image(image.id)
    assert result["error"]["code"] == "IMAGE_SAVE_FAILED"
    writer.assert_not_called()


def test_clipboard_failure_has_a_specific_error_and_does_not_expose_content(app):
    def unavailable(text):
        raise RuntimeError(text)

    result = Api(app, copy_to_clipboard=unavailable).copy_prompt("private prompt")
    assert not result["ok"]
    assert result["error"]["code"] == "CLIPBOARD_FAILED"
    assert "private prompt" not in result["error"]["message"]


def test_bridge_regeneration_and_selection_keep_one_turn_and_use_the_chosen_prompt(app):
    api = Api(app)
    project = app.create_project()
    image = generate(app, project.id)
    accepted = api.regenerate(image.id)
    assert accepted["ok"]
    assert accepted["value"]["turn_id"] == image.request_id
    app.scheduler.run_next()
    view = api.get_project(project.id)["value"]
    assert len(view["images"]) == 1
    assert len(view["images"][0]["versions"]) == 2
    selected = api.select_version(project.id, image.id)["value"]
    assert selected["images"][0]["id"] == image.id
    assert selected["active_leaf_id"] == image.id
    api.submit_request(project.id, "밤으로")
    app.scheduler.run_next()
    assert app.prompts.inputs[-1] == ("refine", image.prompt, "밤으로")


def test_bridge_fork_opens_a_copied_session_and_excludes_later_conversation(app):
    api = Api(app)
    project = app.create_project()
    root = generate(app, project.id, "숲")
    generate(app, project.id, "나중의 밤 장면")
    copied = api.fork(project.id, root.id)["value"]
    assert copied["id"] != project.id
    assert api.bootstrap()["value"]["project"]["id"] == copied["id"]
    assert len(copied["images"]) == 1
    assert copied["images"][0]["request_text"] == "숲"
    assert copied["images"][0]["id"] != root.id
    assert len(api.get_project(project.id)["value"]["images"]) == 2
    assert len(api.list_projects()["value"]) == 2


def test_flux_catalog_downloads_and_saved_selection_use_the_distilled_model(app, tmp_path):
    downloads = ModelDownloads(ModelPaths(tmp_path), executor=app.scheduler)
    api = Api(app, downloads=downloads)
    bootstrap = api.bootstrap()["value"]
    model = next(item for item in bootstrap["image_models"] if item["id"] == "flux2-klein-4b")
    assert (model["family_name"], model["variant_name"]) == ("FLUX.2", "klein 4B")
    assert model["asset_ids"] == ["flux2-klein-4b", "flux2_text_encoder", "flux2_vae"]
    assert model["defaults"] == {"steps": 4, "cfg": 1}
    filenames = {
        "flux2-klein-4b": "flux-2-klein-4b-fp8.safetensors",
        "flux2_text_encoder": "qwen_3_4b_fp4_flux2.safetensors",
        "flux2_vae": "flux2-vae.safetensors",
    }
    for item in bootstrap["models"]:
        if item["id"] in filenames:
            assert item["manual_download"]["filename"] == filenames[item["id"]]
            assert "/blob/main/" not in item["manual_download"]["url"]
    assert api.update_settings({"model_id": "flux2-klein-4b"})["ok"]
    assert api.bootstrap()["value"]["settings"]["model_id"] == "flux2-klein-4b"
