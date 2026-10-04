import pytest

from moru.domain import GenerationSettings, PromptSettings
from moru.errors import MoruError


def test_generation_defaults_use_ten_steps_and_cfg_one_with_auto_seed():
    settings = GenerationSettings()
    assert settings.steps == 10
    assert settings.cfg == 1.0
    assert settings.seed is None


@pytest.mark.parametrize(
    "values",
    [
        {"model_id": "other"},
        {"width": 0},
        {"height": 1000},
        {"width": True},
        {"height": 5000},
        {"steps": 0},
        {"steps": 151},
        {"steps": 10.5},
        {"cfg": -1},
        {"cfg": float("nan")},
        {"cfg": float("inf")},
        {"cfg": True},
        {"seed": -1},
        {"seed": 2**63},
        {"seed": 1.5},
        {"seed": False},
    ],
)
def test_invalid_settings_are_rejected(values):
    with pytest.raises(MoruError) as error:
        GenerationSettings(**values)
    assert error.value.code == "INVALID_SETTINGS"


@pytest.mark.parametrize(
    "width,height", [(1024, 1024), (832, 1216), (1216, 832), (768, 1344), (1344, 768), (512, 768)]
)
def test_resolution_presets_and_valid_custom_dimensions_are_accepted(width, height):
    assert GenerationSettings(width=width, height=height).width == width


def test_resolving_seed_preserves_explicit_seed():
    assert GenerationSettings(seed=9).resolve_seed(42).seed == 9


def test_prompt_defaults_enable_low_reasoning_with_compact_context_and_output():
    settings = PromptSettings()
    assert settings.context_size == 2048
    assert settings.max_tokens == 1024
    assert settings.thinking is True
    assert settings.reasoning_level == "low"
    assert settings.thinking_budget == 128


def test_aesthetic_defaults_use_full_sampling_and_preserve_explicit_settings():
    settings = GenerationSettings(model_id="anima-aesthetic-v1.1")
    assert settings.steps == 40
    assert settings.cfg == 4.5
    explicit = GenerationSettings(model_id="anima-aesthetic-v1.1", steps=35, cfg=4)
    assert explicit.steps == 35
    assert explicit.cfg == 4


@pytest.mark.parametrize("level,budget", [("low", 128), ("medium", 256), ("high", 512)])
def test_reasoning_levels_leave_room_for_the_final_prompt(level, budget):
    assert PromptSettings(reasoning_level=level).thinking_budget == budget
    assert PromptSettings(reasoning_level=level, max_tokens=100).thinking_budget == 50


@pytest.mark.parametrize(
    "values",
    [
        {"context_size": 1023},
        {"context_size": 32769},
        {"context_size": True},
        {"context_size": 8192.5},
        {"max_tokens": 0},
        {"max_tokens": 8192},
        {"max_tokens": True},
        {"max_tokens": 1.5},
        {"thinking": "false"},
        {"thinking": 0},
        {"reasoning_level": "extreme"},
        {"reasoning_level": None},
        {"reasoning_level": []},
    ],
)
def test_invalid_prompt_limits_and_non_boolean_thinking_are_rejected(values):
    with pytest.raises(MoruError) as error:
        PromptSettings(**values)
    assert error.value.code == "INVALID_SETTINGS"


def test_prompt_settings_apply_to_next_job_without_changing_an_accepted_request(app):
    project = app.create_project()
    original = PromptSettings()
    changed = PromptSettings(
        context_size=4096, max_tokens=2048, thinking=False, reasoning_level="high"
    )
    app.submit_request(project.id, "girl")
    app.update_settings(app.get_settings(), changed)
    app.scheduler.run_next()
    app.submit_request(project.id, "night")
    app.scheduler.run_next()
    assert app.prompts.settings == [original, changed]


def test_failed_prompt_settings_read_leaves_a_retryable_request_and_releases_generation_slot(
    app, monkeypatch
):
    from unittest.mock import Mock

    project = app.create_project()
    original = app.get_prompt_settings
    monkeypatch.setattr(app, "get_prompt_settings", Mock(side_effect=MoruError("DATABASE_FAILED")))
    with pytest.raises(MoruError):
        app.submit_request(project.id, "girl")
    request = app.repository.unfinished_requests(project.id)[0]
    assert request.status == "failed"
    assert request.error_code == "GENERATION_FAILED"
    monkeypatch.setattr(app, "get_prompt_settings", original)
    app.retry_request(request.id)
    app.scheduler.run_next()
    assert app.repository.get_request(request.id).status == "completed"


def test_prompt_settings_are_restored_after_application_restart(app, tmp_path):
    from conftest import FakeImages, FakePrompts, ManualExecutor

    from moru.repository import Repository
    from moru.service import Application

    changed = PromptSettings(context_size=4096, max_tokens=2048, thinking=False)
    app.update_settings(GenerationSettings(steps=12), changed)
    app.close()
    restored = Application(
        Repository(tmp_path / "anima.db"),
        FakePrompts(),
        FakeImages(),
        tmp_path,
        executor=ManualExecutor(),
    )
    try:
        assert restored.get_prompt_settings() == changed
        assert restored.get_settings().steps == 12
    finally:
        restored.close()


@pytest.mark.parametrize(
    "stored,expected",
    [
        (
            {"context_size": 8192, "max_tokens": 4096, "thinking": True},
            PromptSettings(context_size=8192, max_tokens=4096, thinking=True),
        ),
        (
            {"context_size": 4096, "max_tokens": 1536, "thinking": True},
            PromptSettings(context_size=4096, max_tokens=1536, thinking=True),
        ),
    ],
)
def test_stored_prompt_settings_are_preserved_without_default_migrations(
    tmp_path, stored, expected
):
    from conftest import FakeImages, FakePrompts, ManualExecutor

    from moru.repository import Repository
    from moru.service import Application

    database = tmp_path / "anima.db"
    repository = Repository(database)
    repository.set_preference("prompt_settings", stored)
    application = Application(
        repository, FakePrompts(), FakeImages(), tmp_path, executor=ManualExecutor()
    )
    assert application.get_prompt_settings() == expected
    assert repository.get_preference("prompt_defaults_version") is None
    explicit_old_values = PromptSettings(context_size=8192, max_tokens=4096, thinking=True)
    application.update_settings(application.get_settings(), explicit_old_values)
    application.close()
    restored = Application(
        Repository(database), FakePrompts(), FakeImages(), tmp_path, executor=ManualExecutor()
    )
    try:
        assert restored.get_prompt_settings() == explicit_old_values
    finally:
        restored.close()
