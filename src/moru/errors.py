"""Stable boundary errors; engine details belong in logs, never the UI."""

MESSAGES = {
    "CLIPBOARD_FAILED": "클립보드에 복사할 수 없습니다. 다시 시도해 주세요.",
    "INVALID_SETTINGS": "생성 설정을 확인해 주세요.",
    "INVALID_REQUEST": "요청 내용을 입력해 주세요.",
    "NOT_FOUND": "작업 또는 이미지를 찾을 수 없습니다.",
    "GENERATION_BUSY": "진행 중인 생성이 끝난 뒤 다시 시도해 주세요.",
    "GENERATION_CANCELLED": "생성이 취소되었습니다.",
    "GENERATION_INTERRUPTED": "앱 종료로 생성이 중단되었습니다. 다시 시도해 주세요.",
    "GENERATION_FAILED": "이미지 생성에 실패했습니다. 다시 시도해 주세요.",
    "PROMPT_MODEL_NOT_FOUND": "프롬프트 모델을 준비해 주세요.",
    "PROMPT_LLM_FAILED": "프롬프트 준비에 실패했습니다. 다시 시도해 주세요.",
    "PROMPT_EMPTY_RESPONSE": (
        "프롬프트 모델이 최종 프롬프트를 반환하지 않았습니다. 다시 시도해 주세요."
    ),
    "PROMPT_INVALID_RESPONSE": (
        "프롬프트 모델이 최종 프롬프트 대신 사고 과정을 반환했습니다. 다시 시도해 주세요."
    ),
    "PROMPT_NON_ENGLISH_RESPONSE": (
        "생성된 프롬프트에 영어 외 문자가 포함되었습니다. 다시 시도해 주세요."
    ),
    "PROMPT_OUTPUT_TOO_LONG": (
        "출력 토큰 한도에 도달해 프롬프트가 중단되었습니다. "
        "재시도하거나 고급 설정에서 출력 한도를 늘리거나 추론 수준을 낮춰 주세요."
    ),
    "PROMPT_RESPONSE_INTERRUPTED": (
        "프롬프트 모델의 응답이 완료되기 전에 중단되었습니다. 다시 시도해 주세요."
    ),
    "PROMPT_CONTEXT_TOO_LONG": (
        "요청과 기준 프롬프트가 너무 깁니다. 컨텍스트를 늘리거나 출력 한도를 줄여 주세요."
    ),
    "THINKING_UNSUPPORTED": "선택한 프롬프트 모델은 thinking 끄기를 지원하지 않습니다.",
    "IMAGE_MODEL_NOT_FOUND": "이미지 모델을 준비해 주세요.",
    "IMAGE_WORKER_START_FAILED": "이미지 생성 엔진을 시작할 수 없습니다.",
    "MODEL_LOAD_FAILED": "모델을 불러올 수 없습니다.",
    "CUDA_OOM": "GPU 메모리가 부족합니다. 이미지 크기를 줄여 주세요.",
    "IMAGE_SAVE_FAILED": "이미지를 저장할 수 없습니다. 저장 공간을 확인해 주세요.",
    "DATABASE_FAILED": "작업 기록을 저장하거나 불러올 수 없습니다.",
    "APP_CLOSED": "앱이 종료 중입니다.",
    "APP_ALREADY_RUNNING": "이 폴더의 Moru가 이미 실행 중입니다. 기존 창을 사용해 주세요.",
    "MODEL_DOWNLOAD_FAILED": "모델 다운로드에 실패했습니다. 연결과 저장 공간을 확인해 주세요.",
    "MODEL_CHECKSUM_FAILED": "모델 파일 검증에 실패했습니다. 다시 다운로드해 주세요.",
    "MODEL_DOWNLOAD_CANCELLED": "모델 다운로드가 취소되었습니다.",
}


class MoruError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(MESSAGES[code])
