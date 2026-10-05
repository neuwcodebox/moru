"""UI language preferences and the small native shell outside the React UI."""

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from moru.errors import MESSAGES, MoruError

SUPPORTED_LANGUAGES = ("ko", "en")

_STARTUP_MESSAGES_EN = {
    "APP_ALREADY_RUNNING": (
        "Moru is already running from this folder. Please use the existing window."
    ),
    "DATABASE_FAILED": "Could not save or load the project history.",
    "MODEL_LOAD_FAILED": "Could not load the model.",
}
_STARTUP_FAILED = {
    "ko": "앱을 시작할 수 없습니다. 앱 파일과 WebView2 Runtime을 확인해 주세요.",
    "en": "Could not start the app. Please check the app files and WebView2 Runtime.",
}


def saved_language(value: object = "ko") -> str:
    """Existing users keep Korean; unsupported stored values use the English fallback."""
    return value if isinstance(value, str) and value in SUPPORTED_LANGUAGES else "en"


def startup_language(root: Path) -> str:
    """Read the preference without opening the repository or recovering another instance's jobs."""
    database = root / "data/anima.db"
    try:
        if not database.is_file():
            return "ko"
        with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as db:
            row = db.execute("SELECT value FROM preferences WHERE key='language'").fetchone()
        return saved_language(json.loads(row[0])) if row else "ko"
    except (OSError, sqlite3.Error, ValueError):
        # This is only the emergency startup dialog; never prevent it with a second failure.
        logging.getLogger(__name__).warning("startup language preference could not be read")
        return "en"


def startup_message(error: Exception, language: str) -> str:
    language = saved_language(language)
    if isinstance(error, MoruError) and error.code in _STARTUP_MESSAGES_EN:
        return MESSAGES[error.code] if language == "ko" else _STARTUP_MESSAGES_EN[error.code]
    return _STARTUP_FAILED[language]


def model_file_filter(model_id: str, language: str) -> str:
    label = "모델 파일" if saved_language(language) == "ko" else "Model files"
    extension = "gguf" if model_id == "prompt" else "safetensors"
    return f"{label} (*.{extension})"
