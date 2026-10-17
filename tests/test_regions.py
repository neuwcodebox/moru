import base64
from io import BytesIO
from threading import Event

import pytest
from PIL import Image as Pixels
from PIL import ImageChops, ImageDraw
from support.application import generate

from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.prompts.region import RegionPrompts
from moru.regions import composite_region, decode_mask, prepare_inpaint_crop


def mask_url(size=(64, 64), box=(10, 12, 40, 48)):
    mask = Pixels.new("L", size)
    if box:
        ImageDraw.Draw(mask).rectangle(box, fill=255)
    output = BytesIO()
    mask.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


def prepare_region(app):
    app.update_settings(GenerationSettings(width=64, height=64))
    project = app.create_project()
    base = generate(app, project.id)
    app.prompts.edit_region = lambda *_, **__: RegionPrompts(
        "blue ceramic cup", "A silver-haired woman holds a blue ceramic cup at night."
    )
    app.images.inpaint = lambda prompt, settings, path, progress, cancelled, *_: (
        app.images.generate(prompt, settings, path, progress, cancelled)
    )
    return project, base


def test_region_edit_adds_a_version_and_followup_uses_its_entire_scene(app):
    project, base = prepare_region(app)
    job = app.edit_region(base.id, "blue ceramic cup", mask_url())
    app.scheduler.run_next()
    result = app.repository.get_image(app.get_job(job.id).image_id)
    rows = app.repository.conversation(project.id)
    assert len(rows) == 1
    assert [image.id for image in rows[0][2]] == [base.id, result.id]
    assert result.prompt == "blue ceramic cup"
    assert result.full_prompt == "A silver-haired woman holds a blue ceramic cup at night."
    generate(app, project.id, "make the room darker")
    assert app.prompts.inputs[-1][1] == result.full_prompt
    assert app.prompts.contexts[-1]["history"][-1].prompt == result.full_prompt


def test_regenerate_after_region_edit_recreates_the_entire_scene(app):
    project, base = prepare_region(app)
    job = app.edit_region(base.id, "blue ceramic cup", mask_url())
    app.scheduler.run_next()
    result = app.repository.get_image(app.get_job(job.id).image_id)
    repeat = app.regenerate(result.id)
    app.scheduler.run_next()
    image = app.repository.get_image(app.get_job(repeat.id).image_id)
    assert image.prompt == result.full_prompt
    assert image.generation_method == "manual"
    assert len(app.repository.conversation(project.id)) == 1


def test_fork_preserves_region_prompts_and_mask_relationship(app):
    project, base = prepare_region(app)
    job = app.edit_region(base.id, "blue ceramic cup", mask_url())
    app.scheduler.run_next()
    result = app.repository.get_image(app.get_job(job.id).image_id)
    forked = app.fork(project.id, result.id)
    copy = app.repository.get_image(forked.active_leaf_id)
    request = app.repository.get_request(copy.request_id)
    assert copy.prompt == result.prompt
    assert copy.full_prompt == result.full_prompt
    assert (app.data_dir / request.mask_path).is_file()
    assert (app.data_dir / request.source_image_path).is_file()


@pytest.mark.parametrize("failure", ["PROMPT_LLM_FAILED", "REGION_INVALID_RESPONSE", "CUDA_OOM"])
def test_failed_region_edit_preserves_selected_image_and_scene(app, failure):
    project, base = prepare_region(app)

    def fail(*_, **__):
        raise MoruError(failure)

    app.prompts.edit_region = fail
    job = app.edit_region(base.id, "blue cup", mask_url())
    app.scheduler.run_next()
    assert app.get_job(job.id).error_code == failure
    assert app.repository.get_project(project.id).active_leaf_id == base.id
    assert len(app.repository.conversation(project.id)[0][2]) == 1


def test_cancelled_region_edit_preserves_its_retry_mask(app):
    project, base = prepare_region(app)
    job = app.edit_region(base.id, "blue cup", mask_url())
    app.cancel_job(job.id)
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "cancelled"
    request = app.repository.get_request(job.request_id)
    assert (app.data_dir / request.mask_path).is_file()
    assert app.repository.get_project(project.id).active_leaf_id == base.id


def test_empty_selection_does_not_create_request_or_mask(app):
    project, base = prepare_region(app)
    with pytest.raises(MoruError) as failure:
        app.edit_region(base.id, "blue cup", mask_url(box=None))
    assert failure.value.code == "REGION_EMPTY_MASK"
    assert app.repository.unfinished_requests(project.id) == []
    assert not (app.data_dir / "masks").exists()


@pytest.mark.parametrize("value", ["bad", "data:image/png;base64,!!!", mask_url((32, 64))])
def test_selection_must_be_a_png_in_original_image_coordinates(value):
    with pytest.raises(MoruError) as failure:
        decode_mask(value, (64, 64))
    assert failure.value.code == "REGION_INVALID_MASK"


def test_region_edit_receives_the_latest_request_and_full_scene_without_old_region_text(app):
    _, base = prepare_region(app)
    first = app.edit_region(base.id, "Make the cup blue", mask_url())
    app.scheduler.run_next()
    edited = app.repository.get_image(app.get_job(first.id).image_id)
    received = []

    def write(scene, request, *_, **__):
        received.append((scene, request))
        return RegionPrompts("red cup", "A silver-haired woman holds a red ceramic cup at night.")

    app.prompts.edit_region = write
    job = app.edit_region(edited.id, "이 컵을 빨간색으로", mask_url())
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    assert received == [(
        "A silver-haired woman holds a blue ceramic cup at night.", "이 컵을 빨간색으로",
    )]


def test_region_progress_shows_region_then_scene_before_image_sampling(app):
    from moru.api import Api

    _, base = prepare_region(app)
    api = Api(app)
    stages = []

    def write(*_, on_ready, on_progress, **__):
        on_ready()
        stages.append(api.get_job(job.id)["value"])
        on_progress("region", "blue", "")
        stages.append(api.get_job(job.id)["value"])
        on_progress("scene", "blue ceramic cup", "A woman holds")
        stages.append(api.get_job(job.id)["value"])
        return RegionPrompts("blue ceramic cup", "A woman holds a blue ceramic cup.")

    def inpaint(prompt, settings, path, progress, cancelled, *_):
        stages.append(api.get_job(job.id)["value"])
        app.images.generate(prompt, settings, path, progress, cancelled)

    app.prompts.edit_region = write
    app.images.inpaint = inpaint
    job = app.edit_region(base.id, "Change the cup to blue", mask_url())
    app.scheduler.run_next()
    assert [stage["state"] for stage in stages] == [
        "writing_region_prompt", "writing_region_prompt", "writing_scene_prompt", "loading_model",
    ]
    assert stages[0]["prompt_text"] == ""
    assert stages[1]["prompt_text"] == "blue"
    assert stages[1]["scene_prompt_text"] == ""
    assert stages[2]["scene_prompt_text"] == "A woman holds"
    assert stages[3]["scene_prompt_text"] == "A woman holds a blue ceramic cup."
    assert stages[3]["region_edit"] is True
    assert api.get_job(job.id)["value"]["prompt_text"] == ""
    assert api.get_job(job.id)["value"]["scene_prompt_text"] == ""


@pytest.mark.parametrize("failure", ["REGION_INVALID_RESPONSE", "GENERATION_CANCELLED"])
def test_region_progress_is_cleared_when_prompt_writing_fails_or_is_cancelled(app, failure):
    _, base = prepare_region(app)

    def fail(*_, on_progress, **__):
        on_progress("scene", "blue cup", "A woman holds")
        assert app.get_job(job.id).scene_prompt_text == "A woman holds"
        raise MoruError(failure)

    app.prompts.edit_region = fail
    job = app.edit_region(base.id, "blue cup", mask_url())
    app.scheduler.run_next()
    finished = app.get_job(job.id)
    assert finished.state == ("cancelled" if failure == "GENERATION_CANCELLED" else "failed")
    assert finished.prompt_text == ""
    assert finished.scene_prompt_text == ""
    assert len(app.images.inputs) == 1  # Only the original image, no sampling from a preview.


def test_last_edit_tab_survives_application_restart(make_app, tmp_path):
    database = tmp_path / "history.db"
    first = make_app(database=database)
    first.set_edit_tab("region")
    second = make_app(database=database)
    assert second.get_edit_tab() == "region"
    second.repository.set_preference("edit_tab", "unknown")
    assert second.get_edit_tab() == "prompt"


def test_transparent_pixels_do_not_become_selected_from_their_hidden_color():
    mask = Pixels.new("RGBA", (64, 64), (255, 255, 255, 0))
    stream = BytesIO()
    mask.save(stream, format="PNG")
    with pytest.raises(MoruError) as failure:
        decode_mask(
            "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode(),
            (64, 64),
        )
    assert failure.value.code == "REGION_EMPTY_MASK"


def test_region_prompts_and_original_source_survive_restart(make_app, tmp_path):
    database = tmp_path / "history.db"
    first = make_app(database=database)
    _, base = prepare_region(first)
    job = first.edit_region(base.id, "blue cup", mask_url())
    first.scheduler.run_next()
    image_id = first.get_job(job.id).image_id
    second = make_app(database=database)
    image = second.repository.get_image(image_id)
    request = second.repository.get_request(image.request_id)
    assert image.prompt == "blue ceramic cup"
    assert image.full_prompt == "A silver-haired woman holds a blue ceramic cup at night."
    assert request.source_image_path == base.image_path
    assert (second.data_dir / request.mask_path).is_file()


def test_region_request_captures_original_dimensions_and_generation_settings(app):
    _, base = prepare_region(app)
    job = app.edit_region(base.id, "blue cup", mask_url())
    app.update_settings(GenerationSettings(width=512, height=768, steps=20))
    app.scheduler.run_next()
    image = app.repository.get_image(app.get_job(job.id).image_id)
    assert (image.settings.width, image.settings.height, image.settings.steps) == (64, 64, 10)


def test_region_writer_gets_only_the_scene_and_change_request_without_images_or_dialogue(app):
    _, base = prepare_region(app)
    received = []

    def write(*inputs, **_):
        received.append(inputs)
        return RegionPrompts("blue cup", "A woman holds a blue cup.")

    app.prompts.edit_region = write
    app.edit_region(base.id, "Make the cup blue", mask_url())
    app.scheduler.run_next()
    assert len(received) == 1
    assert received[0][:2] == (base.full_prompt, "Make the cup blue")
    assert len(received[0]) == 4


def test_oom_retry_keeps_the_region_and_scene_prompt_pair(app):
    _, base = prepare_region(app)
    app.images.failures.append("CUDA_OOM")
    job = app.edit_region(base.id, "blue cup", mask_url())
    app.scheduler.run_next()
    result = app.get_job(job.id)
    assert result.state == "completed"
    assert app.repository.get_image(result.image_id).full_prompt.endswith("at night.")
    assert len(app.images.inputs) == 3  # initial image, failed region sample, successful retry


@pytest.mark.parametrize("failures", [("CUDA_OOM", "CUDA_OOM"), ("GENERATION_FAILED",)])
def test_region_sampling_failure_retries_only_one_oom_and_preserves_the_selected_version(
    app, failures,
):
    project, base = prepare_region(app)
    app.images.failures.extend(failures)
    job = app.edit_region(base.id, "Make the cup blue", mask_url())
    app.scheduler.run_next()
    assert app.get_job(job.id).error_code == failures[-1]
    assert len(app.images.inputs) == 1 + len(failures)
    assert app.prompts.unloads == len(failures) - 1
    assert app.repository.get_project(project.id).active_leaf_id == base.id
    assert len(app.repository.conversation(project.id)[0][2]) == 1


def test_cancellation_during_region_preflight_stops_before_sampling(app):
    project, base = prepare_region(app)

    def cancel(settings, cancelled):
        cancelled.set()
        return False

    app.images.needs_prompt_unload = cancel
    job = app.edit_region(base.id, "Make the cup blue", mask_url())
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "cancelled"
    assert len(app.images.inputs) == 1
    assert app.repository.get_project(project.id).active_leaf_id == base.id


def test_region_storage_failure_removes_output_without_changing_the_dialogue(app, monkeypatch):
    project, base = prepare_region(app)

    def fail(_):
        raise MoruError("DATABASE_FAILED")

    monkeypatch.setattr(app.repository, "complete_generation", fail)
    job = app.edit_region(base.id, "blue cup", mask_url())
    app.scheduler.run_next()
    assert app.get_job(job.id).error_code == "DATABASE_FAILED"
    assert app.repository.get_project(project.id).active_leaf_id == base.id
    assert list((app.data_dir / "images").glob("*.png")) == [app.data_dir / base.image_path]


def test_bridge_distinguishes_the_scene_prompt_from_actual_region_execution(app, tmp_path):
    from moru.api import Api
    from moru.config import ModelPaths

    _, base = prepare_region(app)
    paths = ModelPaths(tmp_path)
    for asset in ("prompt",):
        file = paths.get(asset)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"prepared")
    api = Api(app, models=paths)
    accepted = api.edit_region(base.id, "blue cup", mask_url())
    assert accepted["ok"]
    app.scheduler.run_next()
    image_id = app.get_job(accepted["value"]["id"]).image_id
    details = api.get_image_details(image_id)["value"]
    assert details["prompt"] == "A silver-haired woman holds a blue ceramic cup at night."
    assert details["execution_prompt"] == "blue ceramic cup"
    assert details["generation_method"] == "region"


def test_region_request_does_not_require_local_vision_files(app, tmp_path):
    from moru.api import Api
    from moru.config import ModelPaths

    _, base = prepare_region(app)
    reply = Api(app, models=ModelPaths(tmp_path)).edit_region(
        base.id, "Change the cup to blue", mask_url(),
    )
    assert reply["ok"]
    app.scheduler.run_next()
    assert app.get_job(reply["value"]["id"]).state == "completed"


def test_mask_id_collision_does_not_remove_an_existing_edit_file(app):
    _, base = prepare_region(app)
    app._new_id = lambda: "existing"
    original = app.data_dir / "masks/existing.png"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"immutable previous mask")
    with pytest.raises(MoruError) as failure:
        app.edit_region(base.id, "blue cup", mask_url())
    assert failure.value.code == "IMAGE_SAVE_FAILED"
    assert original.read_bytes() == b"immutable previous mask"


def test_truncated_prompt_reply_is_rejected():
    from support.llama import completion

    from moru.prompts.completion import read_completion

    with pytest.raises(MoruError) as failure:
        read_completion(completion("blue cup", "length"), Event())
    assert failure.value.code == "PROMPT_OUTPUT_TOO_LONG"


def test_prompt_reply_does_not_accept_an_interrupted_stream():
    from moru.prompts.completion import read_completion

    response = (chunk for chunk in [
        {"choices": [{"delta": {"content": "blue cup"}, "finish_reason": None}]},
    ])
    with pytest.raises(MoruError) as failure:
        read_completion(response, Event())
    assert failure.value.code == "PROMPT_RESPONSE_INTERRUPTED"


def test_region_lookup_progress_and_sources_are_saved_on_the_edited_image(app):
    from moru.domain import PromptSource

    _, base = prepare_region(app)
    source = PromptSource("search_tags", "blue", '["blue_cup"]')
    observed = []

    def write(*_, on_ready, on_progress, on_source, on_stage):
        on_ready()
        on_stage("searching_tags", 1)
        observed.append((app.get_job(job.id).state, app.get_job(job.id).found_tag_count))
        on_source(source)
        on_stage("prompting", 1)
        observed.append(app.get_job(job.id).state)
        on_progress("region", "blue cup", "")
        return RegionPrompts("blue cup", "A woman holds a blue cup.")

    app.prompts.edit_region = write
    job = app.edit_region(base.id, "Make the cup blue", mask_url())
    app.scheduler.run_next()
    finished = app.get_job(job.id)
    assert finished.state == "completed"
    assert observed == [("searching_tags", 1), "writing_region_prompt"]
    assert app.repository.get_image(finished.image_id).sources == (source,)


def test_small_region_gets_context_and_more_working_pixels_with_a_sampling_gradient(tmp_path):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    image = Pixels.new("RGB", (512, 512), "blue")
    ImageDraw.Draw(image).rectangle((220, 220, 259, 249), fill="red")
    image.save(source)
    mask.write_bytes(decode_mask(mask_url((512, 512), (220, 220, 259, 249)), image.size))

    crop = prepare_inpaint_crop(source, mask, image.size)

    left, top, right, bottom = crop.bounds
    assert left < 220 < 260 < right and top < 220 < 250 < bottom
    assert (right - left) < image.width and (bottom - top) < image.height
    assert crop.image.width > right - left and crop.image.height > bottom - top
    assert crop.image.width % 32 == crop.image.height % 32 == 0
    assert crop.noise_mask.size == crop.image.size
    assert crop.image.getpixel((crop.image.width // 2, crop.image.height // 2)) == (255, 0, 0)
    assert crop.image.getpixel((0, 0)) == (0, 0, 255)
    assert crop.noise_mask.getpixel((0, 0)) == 0
    with Pixels.open(mask) as full_mask:
        selection = full_mask.crop(crop.bounds).resize(crop.image.size, Pixels.Resampling.NEAREST)
    assert any(0 < value < 255 for value in crop.noise_mask.tobytes())
    assert selection.getextrema()[1] == crop.noise_mask.getextrema()[1] == 255


def test_generation_strength_rises_inward_from_the_boundary_in_original_pixels(tmp_path):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    Pixels.new("RGB", (64, 64), "white").save(source)
    mask.write_bytes(decode_mask(mask_url(box=(16, 16, 47, 47)), (64, 64)))
    crop = prepare_inpaint_crop(source, mask, (64, 64))
    assert crop.bounds == (0, 0, 64, 64)
    assert crop.noise_mask.size == (64, 64)
    strength = [crop.noise_mask.getpixel((x, 32)) for x in (15, 16, 18, 22, 24, 32)]
    assert strength[0] == 0
    assert 0 < strength[1] < strength[2] < strength[3] < strength[4] == strength[5] == 255


@pytest.mark.parametrize("box", [(0, 0, 20, 30), (490, 470, 511, 511), (0, 0, 511, 511)])
def test_edge_and_full_image_selections_keep_crop_coordinates_inside_the_source(tmp_path, box):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    Pixels.new("RGB", (512, 512), "white").save(source)
    mask.write_bytes(decode_mask(mask_url((512, 512), box), (512, 512)))
    crop = prepare_inpaint_crop(source, mask, (512, 512))
    left, top, right, bottom = crop.bounds
    assert 0 <= left <= box[0] < box[2] < right <= 512
    assert 0 <= top <= box[1] < box[3] < bottom <= 512
    assert max(crop.image.size) <= 512
    assert crop.noise_mask.getextrema()[1] == 255


def test_final_blend_ramps_inward_without_the_half_opacity_jump(tmp_path):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    Pixels.new("RGB", (64, 64), "black").save(source)
    mask.write_bytes(decode_mask(mask_url(box=(20, 10, 50, 50)), (64, 64)))
    result = composite_region(source, Pixels.new("RGB", (64, 64), "white"), mask)
    ramp = [result.getpixel((x, 30))[0] for x in range(19, 29)]
    assert ramp[0] == 0
    assert 0 < ramp[1] <= 40
    assert ramp == sorted(ramp)
    assert ramp[-1] == 255


def test_crop_restoration_preserves_unselected_pixels_including_holes_and_keeps_alignment(tmp_path):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    original = Pixels.new("RGB", (64, 64), (17, 53, 193))
    original.save(source)
    selected = Pixels.new("L", original.size)
    drawing = ImageDraw.Draw(selected)
    drawing.rectangle((16, 16, 47, 47), fill=255)
    drawing.rectangle((29, 36, 34, 41), fill=0)
    selected.save(mask)
    generated = Pixels.new("RGB", (96, 96), "red")
    ImageDraw.Draw(generated).rectangle((48, 0, 95, 95), fill="blue")

    result = composite_region(source, generated, mask, (8, 8, 56, 56))
    result.save(tmp_path / "result.png")
    with Pixels.open(tmp_path / "result.png") as restored:
        assert restored.size == original.size
        outside = ImageChops.invert(selected)
        for channel in ImageChops.difference(original, restored).split():
            assert ImageChops.multiply(channel, outside).getbbox() is None
        assert restored.getpixel((24, 24)) == (255, 0, 0)
        assert restored.getpixel((40, 24)) == (0, 0, 255)


def test_inpaint_crop_rejects_an_empty_or_mismatched_mask(tmp_path):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    Pixels.new("RGB", (64, 64), "white").save(source)
    for size in ((64, 64), (32, 32)):
        Pixels.new("L", size).save(mask)
        with pytest.raises(MoruError) as failure:
            prepare_inpaint_crop(source, mask, (64, 64))
        assert failure.value.code == "REGION_INVALID_MASK"


def test_cloud_region_edit_uses_selected_writer_without_loading_a_local_model(app):
    from types import SimpleNamespace

    from moru.domain import PromptSettings
    from moru.prompts.providers import PromptProviders

    _, base = prepare_region(app)
    received = []

    def write(*args, **_):
        received.append(args)
        return RegionPrompts("blue cup", "A woman holds a blue cup.")

    cloud = SimpleNamespace(memory_required=lambda _: 0, edit_region=write, unload=lambda: None)
    app.prompts = PromptProviders(app.prompts, cloud)
    app.update_settings(
        app.get_settings(), PromptSettings(provider="chatgpt", chatgpt_model="test-model"),
    )
    reservations = list(app.images.reservations)
    job = app.edit_region(base.id, "이 컵을 파란색으로 바꿔", mask_url())
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    assert len(received) == 1
    assert received[0][:2] == (base.full_prompt, "이 컵을 파란색으로 바꿔")
    assert received[0][2].provider == "chatgpt"
    assert app.images.reservations == reservations


@pytest.mark.parametrize("required_memory", [0, 123])
def test_region_edit_reports_ready_before_inference_for_loaded_or_reused_models(
    app, tmp_path, monkeypatch, required_memory,
):
    from types import SimpleNamespace

    from support.llama import completion

    from moru.config import ModelPaths
    from moru.prompts.local import LlamaPrompts
    from moru.prompts.providers import PromptProviders

    _, base = prepare_region(app)
    calls = []
    responses = iter((
        "</think>blue cup", "</think>silver-haired girl, daytime. A blue cup.",
    ))

    def complete(**_):
        assert app.get_job(job.id).state == (
            "writing_scene_prompt" if calls else "writing_region_prompt"
        )
        calls.append(True)
        return completion(next(responses))

    llm = SimpleNamespace(
        create_chat_completion=complete, close=lambda: None,
        tokenize=lambda text, **_: list(text), token_eos=lambda: -1,
    )
    prompts = LlamaPrompts(ModelPaths(tmp_path))

    def load(_):
        expected = "writing_scene_prompt" if calls else (
            "loading_prompt_model" if required_memory else "prompting"
        )
        assert app.get_job(job.id).state == expected
        return llm

    monkeypatch.setattr(prompts, "memory_required", lambda _: required_memory)
    monkeypatch.setattr(prompts, "_load", load)
    monkeypatch.setattr(prompts, "_configure_thinking", lambda *_: None)
    monkeypatch.setattr(prompts, "_count_tokens", lambda *_: 100)
    app.prompts = PromptProviders(prompts, app.prompts)
    job = app.edit_region(base.id, "Add a blue cup", mask_url())
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    assert calls == [True, True]


@pytest.mark.parametrize("failure", ["load", "context", "cancel"])
def test_region_load_or_validation_failure_does_not_report_ready(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace

    from moru.config import ModelPaths
    from moru.domain import PromptSettings
    from moru.prompts.local import LlamaPrompts

    cancelled, ready = Event(), []
    prompts = LlamaPrompts(ModelPaths(tmp_path))

    def load(_):
        if failure == "load":
            raise MoruError("MODEL_LOAD_FAILED")
        if failure == "cancel":
            cancelled.set()
        return SimpleNamespace()

    monkeypatch.setattr(prompts, "_load", load)
    monkeypatch.setattr(prompts, "_configure_thinking", lambda *_: None)
    monkeypatch.setattr(prompts, "_count_tokens", lambda *_: 4096 if failure == "context" else 100)
    with pytest.raises(MoruError) as error:
        prompts.edit_region(
            "A red cup.", "Make the cup blue", PromptSettings(), cancelled,
            on_ready=lambda: ready.append(True),
        )
    assert error.value.code == {
        "load": "MODEL_LOAD_FAILED", "context": "PROMPT_CONTEXT_TOO_LONG",
        "cancel": "GENERATION_CANCELLED",
    }[failure]
    assert ready == []
